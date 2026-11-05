from __future__ import annotations

import asyncio
import io
import zipfile

import pytest
from sqlalchemy.orm import Session

from app.connectors.sharepoint.mock import MockSopConnector
from app.knowledge.extraction import (
    UnsupportedDocument,
    chunk_sections,
    extract_sections,
    sections_from_lines,
)
from app.knowledge.indexer import get_search_index, index_sops, index_stats
from app.knowledge.models import KnowledgeDocument
from app.knowledge.search import Bm25Index, Passage, tokenize

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def make_docx(paragraphs: list[tuple[str | None, str]]) -> bytes:
    body = "".join(
        f"<w:p>{f'<w:pPr><w:pStyle w:val={chr(34)}{style}{chr(34)}/></w:pPr>' if style else ''}"
        f"<w:r><w:t>{text}</w:t></w:r></w:p>"
        for style, text in paragraphs
    )
    xml = f'<?xml version="1.0"?><w:document xmlns:w="{W}"><w:body>{body}</w:body></w:document>'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", xml)
    return buf.getvalue()


class TestExtraction:
    def test_docx_sections_follow_heading_styles(self) -> None:
        data = make_docx(
            [
                ("Heading1", "Purpose"),
                (None, "Describes site activation."),
                ("Heading2", "Site initiation visit"),
                (None, "The CRA conducts the SIV."),
                (None, "All staff complete training."),
            ]
        )
        sections = extract_sections(data, "SOP-011.docx", None)
        assert [s.heading for s in sections] == ["Purpose", "Site initiation visit"]
        assert sections[1].paragraphs == ["The CRA conducts the SIV.", "All staff complete training."]

    def test_plain_text_numbered_headings_but_not_sentences(self) -> None:
        sections = sections_from_lines(
            ["Intro line", "4.3 Site initiation visit", "1. Confirm readiness.", "# Records", "Filed in TMF."]
        )
        assert [s.heading for s in sections] == ["General", "4.3 Site initiation visit", "Records"]
        assert sections[1].paragraphs == ["1. Confirm readiness."]

    def test_rejects_unsupported_and_empty(self) -> None:
        with pytest.raises(UnsupportedDocument):
            extract_sections(b"x", "legacy.doc", "application/msword")
        with pytest.raises(UnsupportedDocument):
            extract_sections(b"not a zip", "bad.docx", None)
        with pytest.raises(UnsupportedDocument):
            extract_sections(b"   \n  ", "empty.txt", "text/plain")

    def test_chunks_never_cross_sections_and_respect_size(self) -> None:
        sections = sections_from_lines(["# A", *(["x" * 500] * 5), "# B", "short"])
        chunks = chunk_sections(sections, target=1200)
        assert [c.section for c in chunks] == ["A", "A", "A", "B"]
        assert all(len(c.text) <= 1200 for c in chunks)


class TestSearch:
    def test_tokenize_stems_and_drops_stopwords(self) -> None:
        assert tokenize("What are the reporting timelines for SAEs?") == ["report", "timeline", "sae"]

    def test_bm25_ranks_the_relevant_passage_first(self) -> None:
        def p(i: str, title: str, text: str) -> Passage:
            return Passage(i, f"d{i}", 0, "General", text, title, None)

        index = Bm25Index(
            [
                p("1", "Site Activation", "The CRA conducts the site initiation visit."),
                p("2", "Safety Reporting", "Report SAEs within 24 hours."),
                p("3", "TMF Management", "File documents within 10 working days."),
            ]
        )
        hits = index.search("How fast must an SAE be reported?")
        assert hits[0].passage.chunk_id == "2"
        assert index.search("zzz unknown") == []


class TestIndexer:
    def test_indexes_only_effective_sops_and_skips_unchanged(self, db_session: Session) -> None:
        connector = MockSopConnector("test")
        first = asyncio.run(index_sops(db_session, connector, "avion"))
        assert first.indexed == 11 and not first.failed  # 11 effective demo SOPs
        numbers = {d.sop_number for d in db_session.query(KnowledgeDocument).all()}
        assert "SOP-021" not in numbers  # draft
        assert "SOP-031" not in numbers  # superseded

        second = asyncio.run(index_sops(db_session, connector, "avion"))
        assert second.indexed == 0 and second.unchanged == 11

        stats = index_stats(db_session, "avion")
        assert stats.documents == 11 and stats.passages > 11

    def test_search_index_finds_demo_content(self, db_session: Session) -> None:
        asyncio.run(index_sops(db_session, MockSopConnector("test"), "avion"))
        hits = get_search_index(db_session, "avion").search("site initiation visit checklist")
        assert hits and hits[0].passage.sop_number == "SOP-011"

    def test_tenants_are_isolated(self, db_session: Session) -> None:
        asyncio.run(index_sops(db_session, MockSopConnector("test"), "avion"))
        assert index_stats(db_session, "other-cro").documents == 0
        assert get_search_index(db_session, "other-cro").search("site initiation") == []
