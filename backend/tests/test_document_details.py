"""Reading document control details from inside an SOP (cover page and change history).

The samples follow the layout of Avion's SOP template; names and text are made up.
"""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from app.api.sops import _with_details, with_document_details
from app.auth.rbac import CurrentUser, Role
from app.connectors.sharepoint.models import (
    ConnectorInfo,
    DocumentDetails,
    SopDocument,
    SopStatus,
    StatusSource,
)
from app.knowledge.document_details import extract_details, parse_date, parse_details
from app.knowledge.models import KnowledgeDocument

USER = CurrentUser(id="u1", name="Test User", email="t@example.com", role=Role.CRA)

# Page 1 in pypdf layout mode (runs of spaces between columns become " | ").
COVER = [
    "Standard Operating Procedure | Document No.: | XX-SOP-001",
    "Version Number: | 2.0",
    "Example Procedure | Effective Date:",
    "Next Review Date: | 10 Nov 2027",
    "Prepared By | Reviewed By | Approved By",
    "Alex Writer | Blair Checker | Casey Approver",
    "Date 09 Oct 2025 | Date 21 Oct 2025 | Date 14 Nov 2025",
    "Signed | Signed | Signed",
]

# Normal text extraction of the last pages: wrapped rows, a page break with the repeated page header,
# a DocuSign date stamp and the certificate page that follows.
BODY = [
    "7 ATTACHMENTS",
    "N/A",
    "8 CHANGE HISTORY",
    "Date of Issue Version List Changes",
    "12 Jan 2022 1.0 New Issue",
    "05 Mar 2021 1.1 ",
    "Updated to refer to new templates:",
    "• Visit Report",
    "Allow 10 business days for review.",
    "11/11/2025",
    "Standard Operating Procedure Document No.: XX-SOP-001 ",
    "Example Procedure ",
    "Version Number:  2.0 ",
    "© Copyright of Avion Medical. Unauthorised disclosure is prohibited Page 5 of 5 ",
    " 2.0 General review and update",
    "APPENDIX A TABLE OF CONTENTS",
    "5.1 Nonclinical Pharmacology",
    "Certificate Of Completion",
]


def test_parse_date_day_first() -> None:
    assert parse_date("10 Nov 2027") == date(2027, 11, 10)
    assert parse_date("14-Nov-2025") == date(2025, 11, 14)
    assert parse_date("11/10/2025") == date(2025, 10, 11)  # 11 October (Australian day-first)
    assert parse_date("17 September 2025") == date(2025, 9, 17)
    assert parse_date("") is None
    assert parse_date("not a date") is None


def test_cover_page() -> None:
    details = parse_details(COVER, [])
    assert details.version == "2.0"
    assert details.effective_date is None  # blank on the cover: not guessed from the approval date
    assert details.review_date == date(2027, 11, 10)
    assert (details.prepared_by, details.reviewed_by, details.approved_by) == (
        "Alex Writer",
        "Blair Checker",
        "Casey Approver",
    )
    assert details.prepared_date == date(2025, 10, 9)
    assert details.approved_date == date(2025, 11, 14)


def test_docusign_stamp_in_the_effective_date_box_is_read_month_first() -> None:
    # The stamp is found by position ("Effective Date: | <stamp>") ahead of the empty layout row.
    stamped = ["Effective Date: | 11/10/2025", *COVER]
    details = parse_details(stamped, [])
    # Approved 14 Nov 2025: 10 Nov (month-first) is closer than 11 Oct (day-first).
    assert details.effective_date == date(2025, 11, 10)
    # Unambiguous typed dates are unaffected.
    assert parse_details(["Effective Date: | 18-Nov-2025", *COVER], []).effective_date == date(2025, 11, 18)


def test_wrapped_labels_and_non_date_values() -> None:
    cover = [
        "Version | 3.0",
        "Number:",
        "Effective Date: | Investigational",  # text picked up beside the label is not a date
        "Product Management | Effective Date: | 30 Oct 2026",
        "Next Review | 29 Oct 2028",
        "Date:",
    ]
    details = parse_details(cover, [])
    assert details.version == "3.0"
    assert details.effective_date == date(2026, 10, 30)
    assert details.review_date == date(2028, 10, 29)


def test_electronically_signed_cover_has_no_names() -> None:
    cover = [
        "Version Number: | 3.0",
        "Effective Date    : | 24 Aug 2026",  # spaces before the colon, as found
        "Next Review Date: | 23 Aug 2028",
        "Prepared By | Reviewed By | Approved By",
        "1 | PURPOSE",
        "The purpose of this SOP is | to describe | the requirements for",
    ]
    details = parse_details(cover, [])
    assert details.effective_date == date(2026, 8, 24)
    assert details.prepared_by is None and details.approved_date is None


def test_change_history() -> None:
    revisions = parse_details([], BODY).revisions
    assert [(r.version, r.issued) for r in revisions] == [
        ("1.0", date(2022, 1, 12)),
        ("1.1", date(2021, 3, 5)),
        ("2.0", None),
    ]
    assert (
        revisions[1].changes
        == "Updated to refer to new templates: • Visit Report Allow 10 business days for review."
    )
    assert revisions[2].changes == "General review and update"


def test_change_history_alternative_heading() -> None:
    body = [
        "Effective Date Version Number Summary of Changes",
        "16 Feb 2021 1 First Version",
        "   2.0   General update",
    ]
    assert [r.version for r in parse_details([], body).revisions] == ["1", "2.0"]


def _docx(document_rows: list[list[str]], header_rows: list[list[str]]) -> bytes:
    w = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'

    def table(rows: list[list[str]]) -> str:
        cells = "".join(
            "<w:tr>" + "".join(f"<w:tc><w:p><w:r><w:t>{c}</w:t></w:r></w:p></w:tc>" for c in row) + "</w:tr>"
            for row in rows
        )
        return f"<w:tbl>{cells}</w:tbl>"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "word/document.xml", f"<w:document {w}><w:body>{table(document_rows)}</w:body></w:document>"
        )
        zf.writestr("word/header2.xml", f"<w:hdr {w}>{table(header_rows)}</w:hdr>")
    return buf.getvalue()


def test_word_document_header_and_history_table() -> None:
    data = _docx(
        document_rows=[
            ["Date of Issue", "Version", "List Changes"],
            ["01 Jul 2026", "1.0", "New Issue as per CC-006"],
        ],
        header_rows=[
            ["", "Standard Operating Procedure", "Document No.:", "XX-SOP-002"],
            ["", "Example", "Version Number:", "1.0"],
            ["", "", "Next Review Date:", "01 Jul 2028"],
        ],
    )
    details = extract_details(data, "XX-SOP-002 Example_1.0.docx", None)
    assert details.version == "1.0"
    assert details.review_date == date(2028, 7, 1)
    assert [(r.version, r.issued, r.changes) for r in details.revisions] == [
        ("1.0", date(2026, 7, 1), "New Issue as per CC-006")
    ]


def test_unreadable_file_gives_empty_details() -> None:
    assert extract_details(b"not a pdf", "x.pdf", "application/pdf").is_empty()


def _sop(**overrides: object) -> SopDocument:
    base: dict[str, object] = {
        "id": "1",
        "title": "Example",
        "file_name": "XX-SOP-001 Example_10_-_Copy.pdf",
        "sop_number": "XX-SOP-001",
        "version": "1.0",
        "version_source": "file-name",
        "status": SopStatus.EFFECTIVE,
        "status_source": StatusSource.FOLDER,
        "effective_date": None,
        "review_date": None,
        "owner": None,
        "department": None,
        "folder_path": "SOPs/Approved",
        "modified_at": None,
        "modified_by": None,
        "web_url": None,
        "size_bytes": None,
        "mime_type": None,
    }
    base.update(overrides)
    return SopDocument.model_validate(base)


def test_document_version_and_dates_fill_in_and_flag_a_wrong_file_name() -> None:
    details = DocumentDetails(version="2.0", review_date=date(2027, 11, 11))
    doc = with_document_details(_sop(), details)
    assert (doc.version, doc.version_source, doc.file_name_version) == ("2.0", "document", "1.0")
    assert doc.review_date is not None and doc.review_date.date() == date(2027, 11, 11)
    assert doc.details == details


def test_details_read_from_an_older_copy_of_the_file_are_not_shown(db_session: Session) -> None:
    read_at = datetime(2025, 11, 14, tzinfo=UTC)
    db_session.add(
        KnowledgeDocument(
            tenant_id=USER.tenant_id,
            source="sharepoint",
            external_id="1",
            title="Example",
            status="Effective",
            source_modified_at=read_at,
            details=DocumentDetails(version="2.0", review_date=date(2027, 11, 11)).model_dump(mode="json"),
        )
    )
    db_session.commit()
    info = ConnectorInfo(mode="live", library="L", field_map={})

    [same_file] = _with_details([_sop(modified_at=read_at)], db_session, USER, info)
    assert same_file.version == "2.0" and same_file.details is not None

    # The file was replaced in SharePoint since it was read: the old reading is not used.
    [changed] = _with_details([_sop(modified_at=datetime(2026, 11, 6, tzinfo=UTC))], db_session, USER, info)
    assert changed.version == "1.0" and changed.details is None and changed.review_date is None


def test_sharepoint_column_keeps_precedence() -> None:
    doc = with_document_details(_sop(version="3.1", version_source="column"), DocumentDetails(version="2.0"))
    assert (doc.version, doc.version_source, doc.file_name_version) == ("3.1", "column", None)
