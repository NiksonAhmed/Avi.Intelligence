"""The BD team's conference workbooks in their SharePoint document library, read-only (user decision
2026-11-24).

The library ("Conferences" on the BD site) has a folder per year, "Conferences 2026", "Conferences 2027",
holding Excel schedules such as "Avion_Conferences_H1 2027_Revised_V2.xlsx". For each year:

* files are grouped by half from their name (H1/1H, H2/2H, or the whole year when neither is named);
* in each group the newest file is read, preferring files without "Budget" in the name, so an older
  "Schedule & Budget" copy never brings back conferences that a revised schedule dropped;
* only sheets whose name starts with "Conference" are read ("Conference Schedule", "Conference Budget (2)"),
  never the per-conference cost sheets, "Suggested ..." sheets or planning sheets;
* a sheet's header row (within its first rows) must name "Conference" and "Date"; its columns go through the
  same allowed field names as the SharePoint list (`DEFAULT_FIELDS`), and any column whose header mentions a
  budget or cost is dropped before that, so budgets are never read;
* rows for the same conference (same name in the year, or same start date and city) in several sheets of a
  file are combined (the schedule sheet's website and registration, the other sheet's attendee, priority and
  gov support); across files the newest file wins;
* text dates take the year from the folder; rows without a conference name or a readable date (footnotes,
  totals) are skipped.
"""

from __future__ import annotations

import asyncio
import io
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from openpyxl import load_workbook

from app.connectors.sharepoint.graph_client import GraphClient, site_lookup_path

from .models import ConferenceRecord, ConferenceSourceInfo
from .parsing import attendees_in, tags_in
from .sharepoint import map_item, parse_field_map

_YEAR_FOLDER = re.compile(r"^\s*conferences?\s+(\d{4})\s*$", re.I)
_HALF = (("H1", re.compile(r"\b(h1|1h)\b", re.I)), ("H2", re.compile(r"\b(h2|2h)\b", re.I)))
_NOT_READ = re.compile(r"budget|cost", re.I)
_HEADER_ROWS = 5


@dataclass(frozen=True)
class LibraryFile:
    id: str
    name: str
    year: int
    modified: str
    """ISO time from Graph (compares as text)."""
    web_url: str | None = None


def half_of(name: str) -> str:
    stem = re.sub(r"[_\-.]", " ", name)
    for half, pattern in _HALF:
        if pattern.search(stem):
            return half
    return "year"


def pick_files(files: list[LibraryFile]) -> list[LibraryFile]:
    """The files to read, newest first: per year and half, the newest, preferring non-budget names."""
    groups: dict[tuple[int, str], list[LibraryFile]] = {}
    for f in files:
        if f.name.lower().endswith(".xlsx") and not f.name.startswith("~$"):
            groups.setdefault((f.year, half_of(f.name)), []).append(f)
    chosen = []
    for group in groups.values():
        plain = [f for f in group if not _NOT_READ.search(f.name)] or group
        chosen.append(max(plain, key=lambda f: (f.modified, f.name)))
    return sorted(chosen, key=lambda f: (f.modified, f.name), reverse=True)


def _key(name: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", name.lower()).split())


def _same(a: ConferenceRecord, b: ConferenceRecord) -> bool:
    """The same conference: the same name in the same year, or the same start date in the same city (the
    sheets sometimes name one conference two ways, e.g. "BIO Europe" and "Bio-Europe 2026")."""
    if a.starts_on.year == b.starts_on.year and _key(a.name) == _key(b.name):
        return True
    return a.starts_on == b.starts_on and bool(a.city) and _key(a.city or "") == _key(b.city or "")


def _cell(value: Any) -> str:
    return " ".join(str(value).split()) if value is not None else ""


def _merge(a: ConferenceRecord, b: ConferenceRecord) -> ConferenceRecord:
    """`a` with its empty fields filled from `b` (same conference, another sheet)."""
    filled = {k: v for k, v in b.model_dump().items() if getattr(a, k) in (None, [], "")}
    merged = a.model_copy(update=filled)
    team = merged.team
    return merged.model_copy(
        update={"attendees": attendees_in(team), "tags": tags_in(" ".join(a.tags + b.tags), merged.notes)}
    )


def read_workbook(content: bytes, file: LibraryFile) -> list[ConferenceRecord]:
    fields = parse_field_map(None)
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    found: list[ConferenceRecord] = []
    try:
        for ws in wb.worksheets:
            if not ws.title.strip().lower().startswith("conference"):
                continue
            rows = ws.iter_rows(values_only=True)
            header: list[str] | None = None
            for _ in range(_HEADER_ROWS):
                row = next(rows, None)
                if row is None:
                    break
                names = [_cell(v) for v in row]
                lowered = [n.lower() for n in names]
                if "conference" in lowered and "date" in lowered:
                    header = names
                    break
            if header is None:
                continue
            # "Registration Dates" -> "RegistrationDates", like a list column's internal name.
            keys = [None if not h or _NOT_READ.search(h) else h.replace(" ", "") for h in header]
            for row in rows:
                values = {k: v for k, v in zip(keys, row, strict=False) if k and v not in (None, "")}
                name = _cell(values.get("Conference"))
                if not name:
                    continue
                row_id = f"{file.id.rsplit('/', 1)[-1]}:{_key(name)}"
                item = {"id": row_id, "webUrl": file.web_url, "fields": values}
                record = map_item(item, fields, year=file.year)
                if record is None:
                    continue
                twin = next((i for i, r in enumerate(found) if _same(r, record)), None)
                if twin is None:
                    found.append(record)
                else:
                    found[twin] = _merge(found[twin], record)
    finally:
        wb.close()
    return found


def combine(per_file: list[list[ConferenceRecord]]) -> list[ConferenceRecord]:
    """Files newest first: a conference already read from a newer file of the same year is kept."""
    kept: list[ConferenceRecord] = []
    for records in per_file:
        kept += [r for r in records if not any(_same(k, r) for k in kept)]
    return sorted(kept, key=lambda r: (r.starts_on, r.name))


class LibraryConferenceSource:
    def __init__(self, client: GraphClient, *, site_url: str, library: str, cache_seconds: int) -> None:
        self._client, self._site_url, self._library = client, site_url, library
        self._cache_seconds = cache_seconds
        self._cache: list[ConferenceRecord] | None = None
        self._expires = 0.0
        self._fetched_at: datetime | None = None
        self._files: list[str] = []

    def info(self) -> ConferenceSourceInfo:
        return ConferenceSourceInfo(mode="sharepoint", fetched_at=self._fetched_at, files=self._files)

    async def _files_in_library(self) -> list[LibraryFile]:
        site = await self._client.get(site_lookup_path(self._site_url))
        drives = await self._client.get_all(f"/sites/{site['id']}/drives?$select=id,name")
        drive = next((d for d in drives if d.get("name", "").lower() == self._library.lower()), None)
        if drive is None:
            raise LookupError(f'The SharePoint library "{self._library}" was not found on the site.')
        select = "$select=id,name,folder,file,lastModifiedDateTime,webUrl"
        files: list[LibraryFile] = []
        for folder in await self._client.get_all(f"/drives/{drive['id']}/root/children?{select}"):
            m = _YEAR_FOLDER.match(folder.get("name", ""))
            if "folder" not in folder or not m:
                continue
            children = f"/drives/{drive['id']}/items/{folder['id']}/children?{select}"
            for f in await self._client.get_all(children):
                if "file" in f:
                    files.append(
                        LibraryFile(
                            id=f"{drive['id']}/items/{f['id']}",
                            name=f["name"],
                            year=int(m.group(1)),
                            modified=f.get("lastModifiedDateTime", ""),
                            web_url=f.get("webUrl"),
                        )
                    )
        return files

    async def list_conferences(self, *, force_refresh: bool = False) -> list[ConferenceRecord]:
        if self._cache is not None and not force_refresh and time.monotonic() < self._expires:
            return self._cache
        chosen = pick_files(await self._files_in_library())
        per_file = []
        for f in chosen:
            url = await self._client.download_url(f"/drives/{f.id}/content")
            content = b"".join([chunk async for chunk in self._client.stream_url(url)])
            per_file.append(await asyncio.to_thread(read_workbook, content, f))
        rows = combine(per_file)
        self._cache, self._expires = rows, time.monotonic() + self._cache_seconds
        self._fetched_at, self._files = datetime.now(UTC), sorted(f.name for f in chosen)
        return rows
