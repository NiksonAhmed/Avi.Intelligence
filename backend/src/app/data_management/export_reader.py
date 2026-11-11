"""Reads a Viedoc export (zip of CSV files) into Data Management records, keeping only what is needed.

Only Queries.csv and Pending_forms.csv are read, and only the columns listed below; the form files
(demographics, clinical values) in the same export are ignored. Viedoc's CSVs carry a second header row
of column IDs (e.g. "QueryState"), which is skipped.

Query history: with query history included, each Validation query has one row per state change
(Query Raised -> Query Resolved -> Query Closed ...). Rows are grouped by the query's study sequence
number and ordered by time; the last row gives the current state. Rows without a sequence number are
"Unconfirmed missing data" (blank fields not yet confirmed by the site) or "Pending form upgrade".
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime

# Viedoc's wording -> who has the query now.
STATE_MAP = {
    "query raised": "open_at_site",
    "query rejected": "open_at_site",
    "query resolved": "awaiting_approval",
    "query approved": "closed",
    "query closed": "closed",
    "query removed": "closed",
}
QUERY_COLUMNS = {
    "number": "Query study sequence number",
    "site_name": "Site name",
    "site_code": "Site code",
    "subject_id": "Subject Id",
    "event_id": "Event Id",
    "event_name": "Event name",
    "form_id": "Form Id",
    "form_name": "Form name",
    "item_id": "Item Id",
    "item_label": "Item",
    "raised_on": "Raised on",
    "query_type": "Query type",
    "edit_check": "Range check OID",
    "query_text": "Query text",
    "state": "Query state",
    "resolution": "Query resolution",
    "user_name": "User name",
    "at": "Date & time (UTC)",
    "user_role": "User role",
}
PENDING_COLUMNS = {
    "site_name": "Site name",
    "site_code": "Site code",
    "subject_id": "Subject Id",
    "event_id": "Event Id",
    "event_name": "Event name",
    "form_id": "Form Id",
    "form_name": "Form name",
    "pending_since": "Pending since",
}


@dataclass
class QueryEvent:
    viedoc_state: str
    at: datetime | None
    user_role: str | None
    user_name: str | None
    resolution: str | None


@dataclass
class QueryRecord:
    number: str
    site_code: str
    site_name: str
    subject_id: str
    event_id: str | None
    event_name: str | None
    form_id: str | None
    form_name: str | None
    item_id: str | None
    item_label: str | None
    query_type: str
    raised_on: str | None
    edit_check: str | None
    query_text: str | None
    events: list[QueryEvent] = field(default_factory=list)

    @property
    def viedoc_state(self) -> str:
        return self.events[-1].viedoc_state if self.events else "Query Raised"

    @property
    def state(self) -> str:
        return STATE_MAP.get(self.viedoc_state.lower(), "open_at_site")

    @property
    def raised_at(self) -> datetime | None:
        return self.events[0].at if self.events else None

    @property
    def state_since(self) -> datetime | None:
        return self.events[-1].at if self.events else None

    @property
    def closed_at(self) -> datetime | None:
        return self.state_since if self.state == "closed" else None

    @property
    def resolution(self) -> str | None:
        return next((e.resolution for e in reversed(self.events) if e.resolution), None)

    @property
    def reopen_count(self) -> int:
        """Times an answer was sent back to the site (awaiting approval -> open at site)."""
        mapped = [STATE_MAP.get(e.viedoc_state.lower(), "open_at_site") for e in self.events]
        return sum(
            1
            for a, b in zip(mapped, mapped[1:], strict=False)
            if a == "awaiting_approval" and b == "open_at_site"
        )

    @property
    def answered_count(self) -> int:
        return sum(1 for e in self.events if e.viedoc_state.lower() == "query resolved")


@dataclass
class MissingItem:
    site_code: str
    subject_id: str
    event_id: str | None
    form_id: str | None
    item_id: str | None
    query_type: str


@dataclass
class PendingForm:
    site_code: str
    site_name: str
    subject_id: str
    event_id: str | None
    event_name: str | None
    form_id: str | None
    form_name: str | None
    pending_since: datetime | None


@dataclass
class ExportData:
    study_code: str
    queries: list[QueryRecord]
    missing: list[MissingItem]
    pending: list[PendingForm]


class ExportFormatError(Exception):
    pass


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _clean(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    text = " ".join(value.split())
    return text[:limit] or None


def _is_id_row(row: dict[str, str]) -> bool:
    """Viedoc's second header row: each value is its column name without spaces (e.g. "QueryState")."""
    values = [(k, v) for k, v in row.items() if k and v]
    if not values:
        return False
    same = sum(
        1 for k, v in values if re.sub(r"[^a-z0-9]", "", k.lower()) == re.sub(r"[^a-z0-9]", "", v.lower())
    )
    return same >= max(2, len(values) // 2)


def _rows(archive: zipfile.ZipFile, suffix: str) -> tuple[str | None, list[dict[str, str]]]:
    name = next((n for n in archive.namelist() if n.lower().endswith(suffix.lower())), None)
    if name is None:
        return None, []
    text = archive.read(name).decode("utf-8-sig", errors="replace")
    rows = [r for r in csv.DictReader(io.StringIO(text)) if not _is_id_row(r)]
    return name, rows


def _get(row: dict[str, str], column: str) -> str:
    return (row.get(column) or "").strip()


def read_export(content: bytes) -> ExportData:
    if not zipfile.is_zipfile(io.BytesIO(content)):
        raise ExportFormatError("The Viedoc export is not a zip file.")
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        query_file, query_rows = _rows(archive, "_Queries.csv")
        _pending_file, pending_rows = _rows(archive, "_Pending_forms.csv")
    if query_file is None:
        raise ExportFormatError("The Viedoc export has no Queries file (was includeQueries set?).")
    match = re.match(r"(.+?)_\d{8}_\d{6}_", query_file.rsplit("/", 1)[-1])
    study_code = match.group(1) if match else "Viedoc study"

    c = QUERY_COLUMNS
    grouped: dict[str, QueryRecord] = {}
    missing: list[MissingItem] = []
    for row in query_rows:
        number = _get(row, c["number"])
        if not number:
            missing.append(
                MissingItem(
                    site_code=_get(row, c["site_code"]),
                    subject_id=_get(row, c["subject_id"]),
                    event_id=_clean(_get(row, c["event_id"]), 64),
                    form_id=_clean(_get(row, c["form_id"]), 64),
                    item_id=_clean(_get(row, c["item_id"]), 100),
                    query_type=_clean(_get(row, c["query_type"]), 64) or "Unknown",
                )
            )
            continue
        record = grouped.get(number)
        if record is None:
            record = grouped[number] = QueryRecord(
                number=number,
                site_code=_get(row, c["site_code"]),
                site_name=_clean(_get(row, c["site_name"]), 300) or "",
                subject_id=_get(row, c["subject_id"]),
                event_id=_clean(_get(row, c["event_id"]), 64),
                event_name=_clean(_get(row, c["event_name"]), 200),
                form_id=_clean(_get(row, c["form_id"]), 64),
                form_name=_clean(_get(row, c["form_name"]), 200),
                item_id=_clean(_get(row, c["item_id"]), 100),
                item_label=_clean(_get(row, c["item_label"]), 300),
                query_type=_clean(_get(row, c["query_type"]), 64) or "Unknown",
                raised_on=_clean(_get(row, c["raised_on"]), 32),
                edit_check=_clean(_get(row, c["edit_check"]), 200),
                query_text=_clean(_get(row, c["query_text"]), 4000),
            )
        state = _clean(_get(row, c["state"]), 64)
        if state:
            record.events.append(
                QueryEvent(
                    viedoc_state=state,
                    at=parse_time(_get(row, c["at"])),
                    user_role=_clean(_get(row, c["user_role"]), 100),
                    user_name=_clean(_get(row, c["user_name"]), 255),
                    resolution=_clean(_get(row, c["resolution"]), 300),
                )
            )
    for record in grouped.values():
        record.events.sort(key=lambda e: e.at or datetime.min.replace(tzinfo=UTC))

    p = PENDING_COLUMNS
    pending = [
        PendingForm(
            site_code=_get(row, p["site_code"]),
            site_name=_clean(_get(row, p["site_name"]), 300) or "",
            subject_id=_get(row, p["subject_id"]),
            event_id=_clean(_get(row, p["event_id"]), 64),
            event_name=_clean(_get(row, p["event_name"]), 200),
            form_id=_clean(_get(row, p["form_id"]), 64),
            form_name=_clean(_get(row, p["form_name"]), 200),
            pending_since=parse_time(_get(row, p["pending_since"])),
        )
        for row in pending_rows
        if _get(row, p["subject_id"])
    ]
    return ExportData(study_code=study_code, queries=list(grouped.values()), missing=missing, pending=pending)
