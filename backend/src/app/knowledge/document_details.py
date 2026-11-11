"""Reads document control details from inside an SOP: the cover page and the change history table.

Avion's SOP template (verified on the live library, 2026-11-06) has on page 1:

    Document No.: CO-SOP-001   Version Number: 2.0   Effective Date: [often blank]
    Next Review Date: 10 Nov 2027
    Prepared By | Reviewed By | Approved By      (names, then "Date dd Mon yyyy" for each)

and a final section "CHANGE HISTORY" with a table: Date of Issue | Version | List Changes.

Only what is written in the document is returned; nothing is inferred. Dates are day-first
(Australian usage: 11/11/2025 is 11 November).
"""

from __future__ import annotations

import io
import re
import zipfile
from datetime import date, datetime
from typing import Any
from xml.etree import ElementTree as ET

from pypdf import PdfReader

from app.connectors.sharepoint.models import DocumentDetails, RevisionEntry

from .extraction import MAX_FILE_BYTES

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_DATE = r"\d{1,2}[\s\-/.](?:[A-Za-z]{3,9}|\d{1,2})[\s\-/.]\d{2,4}"
_DATE_RE = re.compile(_DATE)
_ONLY_DATE = re.compile(rf"^\s*{_DATE}\s*$")
_VERSION = re.compile(r"^\d{1,2}(?:\.\d{1,2})?$")
# "12 Jan 2022 1.0 New Issue", " 2.0 Update to align…", "05 Mar 2021 1.1" (changes on the next lines).
_HISTORY_ROW = re.compile(rf"^\s*(?:({_DATE})\s+)?(\d{{1,2}}(?:\.\d{{1,2}})?)(?:\s+(\S.*))?\s*$")
_HISTORY_HEADER = re.compile(r"(?:date of issue|effective date).*version.*(?:change|summary)", re.IGNORECASE)
_PAGE_FURNITURE = re.compile(
    r"©|copyright|page \d+ of \d+|user.s responsibility to check|most recent issue", re.IGNORECASE
)
_PAGE_HEADER_START = re.compile(r"standard operating procedure\s+document no", re.IGNORECASE)
_PAGE_HEADER_END = re.compile(r"version number\s*:", re.IGNORECASE)
# The end of the table: a numbered section heading ("1 PURPOSE") or the DocuSign certificate page.
_HISTORY_END = re.compile(
    r"^\s*\d+(?:\.\d+)*\.?\s+[A-Z][A-Z ,&/()\-]{3,}\s*$|^\s*APPENDIX\b|(?i:certificate of completion)"
)
_SECTION_HEADING = re.compile(r"^\s*\d+(?:\.\d+)*\.?\s*\|?\s*[A-Z][A-Z ]{3,}")
_FORMATS = ("%d %b %Y", "%d %B %Y", "%d %m %Y", "%d %b %y", "%d %B %y", "%d %m %y")


def parse_date(text: str | None) -> date | None:
    """Parses "10 Nov 2025", "14-Nov-2025", "11/11/2025" (day first). None if not a date."""
    if not text:
        return None
    match = _DATE_RE.search(text)
    if not match:
        return None
    value = re.sub(r"[\s\-/.]+", " ", match.group(0)).strip()
    if m := re.match(r"(\d+) ([A-Za-z]+) (\d+)", value):  # "Sept" and similar long month names
        value = f"{m[1]} {m[2][:3]} {m[3]}"
    for fmt in _FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


# ---- reading the file into rows -----------------------------------------------------------------


def _docx_rows(data: bytes) -> tuple[list[str], list[str]]:
    """(cover rows, body rows). Table rows become "cell | cell | cell"."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            parts = [n for n in zf.namelist() if re.fullmatch(r"word/(?:document|header\d*)\.xml", n)]
            if any(zf.getinfo(n).file_size > MAX_FILE_BYTES * 4 for n in parts):  # zip-bomb guard
                return [], []
            xml = {n: zf.read(n) for n in parts}
    except zipfile.BadZipFile:
        return [], []

    def text_of(el: ET.Element) -> str:
        return "".join(t.text or "" for t in el.iter(f"{_W}t")).strip()

    def rows_of(container: ET.Element) -> list[str]:
        rows: list[str] = []
        for child in container:
            if child.tag == f"{_W}p":
                if t := text_of(child):
                    rows.append(t)
            elif child.tag == f"{_W}tbl":
                for tr in child.iter(f"{_W}tr"):
                    cells = [text_of(tc) for tc in tr.findall(f"{_W}tc")]
                    if any(cells):
                        rows.append(" | ".join(cells))
        return rows

    cover: list[str] = []
    for name in sorted(n for n in xml if "header" in n):
        for row in rows_of(ET.fromstring(xml[name])):  # noqa: S314
            if row not in cover:
                cover.append(row)
    body: list[str] = []
    if "word/document.xml" in xml:
        root = ET.fromstring(xml["word/document.xml"])  # noqa: S314
        container = root.find(f"{_W}body")
        body = rows_of(container) if container is not None else []
    return cover + body[:40], body


_POSITIONED_LABELS = {
    "Version Number": re.compile(r"^version(?:\s+number)?\s*:?$", re.IGNORECASE),
    "Effective Date": re.compile(r"^effective\s+date\s*:?$", re.IGNORECASE),
    "Next Review Date": re.compile(r"^next\s+review(?:\s+date)?\s*:?$", re.IGNORECASE),
}


def _positioned_cover_rows(page: Any) -> list[str]:
    """Cover values found by position: the text to the right of each label on the same line.

    Needed because DocuSign stamps the signing date into the "Effective Date" box as a separate
    layer, and some covers wrap a label over two lines ("Next Review / Date:"); both defeat
    line-by-line reading.
    """
    fragments: list[tuple[float, float, str]] = []

    def visit(text: str, cm: list[float], tm: list[float], _font: Any, _size: Any) -> None:
        if text.strip():
            fragments.append((tm[4] * cm[0] + cm[4], tm[5] * cm[3] + cm[5], text.strip()))

    page.extract_text(visitor_text=visit)
    rows: list[str] = []
    for label, pattern in _POSITIONED_LABELS.items():
        for x, y, text in fragments:
            if not pattern.match(text):
                continue
            right = sorted((fx, t) for fx, fy, t in fragments if abs(fy - y) <= 5 and x + 20 < fx < x + 260)
            value = " ".join(t for _fx, t in right if not _POSITIONED_LABELS_ANY.match(t))
            if value:
                rows.append(f"{label}: | {value}")
            break
    return rows


_POSITIONED_LABELS_ANY = re.compile(r"^(?:version|number|effective|next|review|date)\b", re.IGNORECASE)


def _pdf_rows(data: bytes) -> tuple[list[str], list[str]]:
    try:
        reader = PdfReader(io.BytesIO(data))
        # Layout mode keeps the cover's columns apart; runs of spaces become cell separators.
        first = reader.pages[0].extract_text(extraction_mode="layout") or ""
        layout = [re.sub(r"\s{2,}", " | ", line.strip()) for line in first.splitlines() if line.strip()]
        # Positioned values first: they are what is printed in the box next to each label.
        cover = _positioned_cover_rows(reader.pages[0]) + layout
        body: list[str] = []
        for page in reader.pages:
            body.extend((page.extract_text() or "").splitlines())
    except Exception:  # damaged, encrypted or scanned PDFs: no details rather than a failure
        return [], []
    return cover, body


def read_rows(data: bytes, file_name: str, mime_type: str | None) -> tuple[list[str], list[str]]:
    name, mime = file_name.lower(), (mime_type or "").lower()
    if name.endswith(".docx") or "wordprocessingml" in mime:
        return _docx_rows(data)
    if name.endswith(".pdf") or mime == "application/pdf":
        return _pdf_rows(data)
    if name.endswith((".txt", ".md")) or mime.startswith("text/"):
        lines = data.decode("utf-8", errors="replace").splitlines()
        return lines[:40], lines
    return [], []


# ---- parsing -------------------------------------------------------------------------------------


def _label_values(rows: list[str], label: str) -> list[str]:
    """Every non-empty value written after the label, in order (positioned values come first)."""
    pattern = re.compile(rf"{label}[\s|:]*([^|]*)", re.IGNORECASE)
    return [v for row in rows if (m := pattern.search(row)) and (v := m.group(1).strip())]


def _first_date(rows: list[str], *labels: str, not_before: date | None = None) -> date | None:
    for label in labels:
        for value in _label_values(rows, label):
            if parsed := _parse_cover_date(value, not_before):
                return parsed
    return None


def _parse_cover_date(text: str, not_before: date | None) -> date | None:
    """Like parse_date, but a numeric date that reads both ways ("11/10/2025") takes the reading
    closest to the sign-off date. DocuSign stamps the signing date month-first (US format), while
    typed dates are day-first; the sign-off date tells them apart."""
    parsed = parse_date(text)
    m = re.search(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})\b", text)
    if parsed and m and not_before and int(m[1]) <= 12 and int(m[2]) <= 12:
        year = int(m[3]) + (2000 if len(m[3]) == 2 else 0)
        try:
            month_first = date(year, int(m[1]), int(m[2]))
        except ValueError:
            return parsed
        if abs((month_first - not_before).days) < abs((parsed - not_before).days):
            return month_first
    return parsed


def _cells(row: str) -> list[str]:
    return [c.strip() for c in row.split("|") if c.strip()]


def _sign_off(rows: list[str], details: DocumentDetails) -> None:
    """Prepared / Reviewed / Approved By: names on the next row, then "Date …" for each column."""
    for i, row in enumerate(rows):
        if not re.search(r"prepared by", row, re.IGNORECASE) or not re.search(
            r"approved by", row, re.IGNORECASE
        ):
            continue
        names: list[str] | None = None
        dates: list[date | None] | None = None
        for following in rows[i + 1 : i + 6]:
            if _SECTION_HEADING.match(following):
                break  # signed electronically: no names or dates on the cover, the procedure starts
            if re.search(r"\bdate\b", following, re.IGNORECASE):
                segments = re.split(r"\bdate\b", following, flags=re.IGNORECASE)[1:]
                dates = [parse_date(s) for s in segments]
                break
            cells = [c for c in _cells(following) if not re.fullmatch(r"signed", c, re.IGNORECASE)]
            if names is None and len(cells) == 3 and not any(_DATE_RE.search(c) for c in cells):
                names = cells
        if names:
            details.prepared_by, details.reviewed_by, details.approved_by = names
        if dates and len(dates) == 3:
            details.prepared_date, details.reviewed_date, details.approved_date = dates
        return


def _version_key(version: str) -> tuple[int, int]:
    major, _, minor = version.partition(".")
    return int(major), int(minor or 0)


def _history(body: list[str]) -> list[RevisionEntry]:
    header = None
    for i, line in enumerate(body):
        if _HISTORY_HEADER.search(line.replace("|", " ")):
            header = i
    if header is None:
        return []
    entries: list[RevisionEntry] = []
    in_page_header = False

    def accept(issued: date | None, version: str) -> bool:
        # An undated row must look like a version ("2.0"), so wrapped text such as "10 business days"
        # is not mistaken for one; versions only go up.
        if issued is None and "." not in version:
            return False
        return not entries or _version_key(version) >= _version_key(entries[-1].version)

    for line in body[header + 1 :]:
        if _PAGE_HEADER_START.search(line):
            in_page_header = True  # repeated page header: document number, title, version
            continue
        if in_page_header:
            in_page_header = not _PAGE_HEADER_END.search(line)
            continue
        if _HISTORY_END.search(line):
            break
        if not line.strip() or _ONLY_DATE.match(line) or _PAGE_FURNITURE.search(line):
            continue  # blank lines, signature date stamps and page footers
        if " | " in line:  # Word table row: Date of Issue | Version | List Changes
            cells = [c.strip() for c in line.split("|")]
            if len(cells) >= 2 and _VERSION.match(cells[1]):
                entries.append(
                    RevisionEntry(
                        issued=parse_date(cells[0]), version=cells[1], changes=" ".join(cells[2:]).strip()
                    )
                )
            continue
        m = _HISTORY_ROW.match(line)
        if m and accept(parse_date(m[1]), m[2]):
            entries.append(RevisionEntry(issued=parse_date(m[1]), version=m[2], changes=(m[3] or "").strip()))
        elif entries:  # wrapped text of the previous row's changes
            entries[-1].changes = f"{entries[-1].changes} {line.strip()}".strip()
    return entries


def parse_details(cover: list[str], body: list[str]) -> DocumentDetails:
    details = DocumentDetails()
    # "Version Number: 2.0", or a label wrapped over two lines ("Version | 3.0" / "Number:").
    for value in _label_values(cover, r"version number") + _label_values(cover, r"\bversion\b"):
        if _VERSION.match(value.split()[0]):
            details.version = value.split()[0]
            break
    _sign_off(cover, details)
    signed = details.approved_date or details.reviewed_date or details.prepared_date
    details.effective_date = _first_date(cover, r"effective date", not_before=signed)
    details.review_date = _first_date(cover, r"next review date", r"next review", not_before=signed)
    details.revisions = _history(body)
    return details


def extract_details(data: bytes, file_name: str, mime_type: str | None) -> DocumentDetails:
    """Document control details found in the file; empty fields when the document does not state them."""
    cover, body = read_rows(data, file_name, mime_type)
    return parse_details(cover, body)
