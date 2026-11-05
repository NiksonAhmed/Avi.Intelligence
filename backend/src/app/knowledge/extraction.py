"""Text extraction from SOP files (DOCX, PDF, plain text) into headed sections, then chunks."""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET  # noqa: S405  (stdlib expat: no external entities, billion-laughs guarded)

from pypdf import PdfReader

MAX_FILE_BYTES = 25 * 1024 * 1024
CHUNK_TARGET_CHARS = 1400
DEFAULT_SECTION = "General"

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_NUMBERED_HEADING = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+\S.{0,90}$")
_MD_HEADING = re.compile(r"^#{1,6}\s+(.+)$")


class UnsupportedDocument(Exception):
    pass


@dataclass
class Section:
    heading: str
    paragraphs: list[str] = field(default_factory=list)


@dataclass
class Chunk:
    section: str
    text: str


def _looks_like_heading(line: str) -> bool:
    """Numbered headings ("4.1 Site initiation visit") are short and don't end like sentences."""
    return bool(_NUMBERED_HEADING.match(line)) and not line.rstrip().endswith((".", ";", ":", ","))


def sections_from_lines(lines: list[str]) -> list[Section]:
    sections: list[Section] = []
    current = Section(DEFAULT_SECTION)
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        md = _MD_HEADING.match(line)
        if md or _looks_like_heading(line):
            if current.paragraphs or current.heading != DEFAULT_SECTION:
                sections.append(current)
            current = Section((md.group(1) if md else line)[:300])
            continue
        current.paragraphs.append(line)
    if current.paragraphs or current.heading != DEFAULT_SECTION:
        sections.append(current)
    return [s for s in sections if s.paragraphs]


def _docx_sections(data: bytes) -> list[Section]:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            info = zf.getinfo("word/document.xml")
            if info.file_size > MAX_FILE_BYTES * 4:  # zip-bomb guard
                raise UnsupportedDocument("Word document is too large to index.")
            xml = zf.read(info)
    except (zipfile.BadZipFile, KeyError) as exc:
        raise UnsupportedDocument("File is not a valid Word (.docx) document.") from exc

    root = ET.fromstring(xml)  # noqa: S314
    sections: list[Section] = []
    current = Section(DEFAULT_SECTION)
    for para in root.iter(f"{_W}p"):
        text = "".join(t.text or "" for t in para.iter(f"{_W}t")).strip()
        if not text:
            continue
        style_el = para.find(f"{_W}pPr/{_W}pStyle")
        style = (style_el.get(f"{_W}val") or "") if style_el is not None else ""
        is_heading = style.lower().startswith(("heading", "title")) or _looks_like_heading(text)
        if is_heading and len(text) <= 200:
            if current.paragraphs:
                sections.append(current)
            current = Section(text[:300])
        else:
            current.paragraphs.append(text)
    if current.paragraphs:
        sections.append(current)
    return sections


def _pdf_sections(data: bytes) -> list[Section]:
    try:
        reader = PdfReader(io.BytesIO(data))
        lines: list[str] = []
        for page in reader.pages:
            lines.extend((page.extract_text() or "").splitlines())
    except Exception as exc:  # pypdf raises a variety of errors for damaged/encrypted files
        raise UnsupportedDocument("PDF could not be read (it may be scanned, encrypted or damaged).") from exc
    return sections_from_lines(lines)


def extract_sections(data: bytes, file_name: str, mime_type: str | None) -> list[Section]:
    if len(data) > MAX_FILE_BYTES:
        raise UnsupportedDocument("File is larger than 25 MB.")
    name = file_name.lower()
    mime = (mime_type or "").lower()
    if name.endswith(".docx") or "wordprocessingml" in mime:
        sections = _docx_sections(data)
    elif name.endswith(".pdf") or mime == "application/pdf":
        sections = _pdf_sections(data)
    elif name.endswith((".txt", ".md")) or mime.startswith("text/"):
        sections = sections_from_lines(data.decode("utf-8", errors="replace").splitlines())
    else:
        raise UnsupportedDocument(f"File type not supported for indexing: {file_name}")
    if not sections:
        raise UnsupportedDocument("No text could be extracted (the file may be a scanned image).")
    return sections


def chunk_sections(sections: list[Section], target: int = CHUNK_TARGET_CHARS) -> list[Chunk]:
    """Splits sections into passages of roughly `target` characters, never crossing a section."""
    chunks: list[Chunk] = []
    for section in sections:
        buffer: list[str] = []
        size = 0
        for para in section.paragraphs:
            if buffer and size + len(para) > target:
                chunks.append(Chunk(section.heading, "\n".join(buffer)))
                buffer, size = [], 0
            buffer.append(para)
            size += len(para) + 1
        if buffer:
            chunks.append(Chunk(section.heading, "\n".join(buffer)))
    return chunks
