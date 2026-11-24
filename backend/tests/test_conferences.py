"""Conferences (BD): demo data, reading the BD schedules' wording, the SharePoint list reader (fake Graph
data), figures (priority, clashes, registration), access and export. Budgets are never read."""

from __future__ import annotations

import asyncio
import io
from collections.abc import AsyncIterator
from datetime import date, datetime
from typing import Any

from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook

from app.auth.rbac import Role
from app.conferences.demo import DemoConferenceSource
from app.conferences.geo import locate
from app.conferences.library import (
    LibraryConferenceSource,
    LibraryFile,
    combine,
    half_of,
    pick_files,
    read_workbook,
)
from app.conferences.models import ConferenceRecord
from app.conferences.parsing import (
    attendees_in,
    date_range,
    gov_support_in,
    priority_of,
    registration_date,
    tags_in,
)
from app.conferences.report import build_conferences
from app.conferences.sharepoint import DEFAULT_FIELDS, map_item, parse_field_map
from app.conferences.source import build_conference_source
from app.core.config import get_settings

API = "/api/v1/conferences"
TODAY = date(2026, 11, 13)


def test_cities_are_placed_without_online_lookups() -> None:
    assert locate("Boston") == (42.36, -71.06)
    assert locate("  boston, MA ") == (42.36, -71.06)
    assert locate("São Paulo") == (-23.55, -46.63)
    assert locate("Washington, D.C.") == locate("Washington, DC") is not None
    for city in ("Chantilly", "Belfast", "Canberra", "Cologne", "Gold Coast"):  # added for the BD schedules
        assert locate(city) is not None, city
    assert locate("Atlantis") is None and locate(None) is None


def test_dates_as_the_schedules_write_them() -> None:
    assert date_range("7-10 Jan", 2027) == (date(2027, 1, 7), date(2027, 1, 10))
    assert date_range("23 - 25 March", 2026) == (date(2026, 3, 23), date(2026, 3, 25))
    assert date_range("29 Apr - 01 May", 2026) == (date(2026, 4, 29), date(2026, 5, 1))
    assert date_range("30 May - 02 June", 2026) == (date(2026, 5, 30), date(2026, 6, 2))
    assert date_range("12 July", 2026) == (date(2026, 7, 12), None)
    assert date_range("2027-04-20T00:00:00Z", None) == (date(2027, 4, 20), None)
    assert date_range(datetime(2027, 1, 7), None) == (date(2027, 1, 7), None)
    assert date_range("7-10 Jan", None) == (None, None)  # no year: not guessed
    assert date_range("TBD", 2026) == (None, None)


def test_registration_as_the_schedules_write_it() -> None:
    start = date(2026, 3, 23)
    assert registration_date("EBR to 30 Jan", start) == date(2026, 1, 30)
    assert registration_date("EBR 10 Apr", date(2026, 10, 7)) == date(2026, 4, 10)
    assert registration_date("EBR to 19 Dec", date(2027, 1, 7)) == date(2026, 12, 19)  # the year before
    assert registration_date("2-Mar-26", start) == date(2026, 3, 2)
    assert registration_date("Feb-26", start) == date(2026, 2, 28)  # a month only: its last day
    assert registration_date("TBD", start) is None and registration_date("TBA", start) is None
    assert registration_date(None, start) is None


def test_people_priority_tags_and_trade_missions() -> None:
    assert attendees_in("JB,MM") == ["JB", "MM"]
    assert attendees_in("MM (JB)") == ["MM", "JB"]
    assert attendees_in("To decide") == [] and attendees_in(None) == []
    assert priority_of("1") == 1 and priority_of(2.0) == 2 and priority_of("Priority 3") == 3
    assert priority_of("High") is None and priority_of(None) is None
    assert tags_in("BIO Partnering, AUS Delegate. Largest Global Biotech Conference.") == [
        "BIO Partnering",
        "AUS Delegate",
    ]
    assert tags_in("Largest North American NM Conference") == []
    assert gov_support_in("Global Vic Trade Mission") == "Global Vic Trade Mission"
    assert gov_support_in("AusBio Trade Mission") == "AusBio Trade Mission"
    assert gov_support_in("Conflict with SNMMI") is None


def test_reads_the_bd_schedule_columns_and_never_a_budget() -> None:
    assert not any("budget" in k.lower() or "cost" in k.lower() for k in DEFAULT_FIELDS)
    fields = parse_field_map(None)
    item = {
        "id": "7",
        "webUrl": "https://example.sharepoint.com/sites/BD/Lists/Conferences/7_.000",
        "fields": {
            "Conference": "Example Biotech Convention", "Date": "22-25 June", "Location": "San Diego, USA",
            "Website": "https://example.org/convention", "RegistrationDates": "EBR to 30 Jan",
            "Attendee": "AB, CD", "Priority": "1", "GovSupport": "AusBio Trade Mission",
            "Comment": "BIO Partnering, AUS Delegate. Largest global biotech conference.",
            "BudgetAUD": 25000,
        },
    }  # fmt: skip
    row = map_item(item, fields, year=2026)
    assert row is not None
    assert (row.name, row.city, row.country) == ("Example Biotech Convention", "San Diego", "USA")
    assert (row.starts_on, row.ends_on) == (date(2026, 6, 22), date(2026, 6, 25))
    assert row.priority == 1 and row.attendees == ["AB", "CD"] and row.team == "AB, CD"
    assert row.tags == ["BIO Partnering", "AUS Delegate"] and row.gov_support == "AusBio Trade Mission"
    assert row.registration == "EBR to 30 Jan" and row.register_by == date(2026, 1, 30)
    assert row.website == "https://example.org/convention" and row.lat is not None
    assert "25000" not in row.model_dump_json()  # the budget is not read
    assert map_item({"id": "8", "fields": {"Title": "No date"}}, fields) is None
    assert map_item({"id": "9", "fields": {"StartDate": "2027-01-01"}}, fields) is None
    # A trade mission written in the comment counts too.
    other = map_item(
        {
            "id": "10",
            "fields": {"Title": "X", "StartDate": "2026-03-23", "Comment": "Global Vic Trade Mission"},
        },
        fields,
    )
    assert other is not None and other.gov_support == "Global Vic Trade Mission"


def test_field_map_names_the_real_columns_first() -> None:
    fields = parse_field_map('{"priority": "BDPriority", "name": ["EventTitle"]}')
    assert fields["priority"][0] == "BDPriority" and fields["name"][0] == "EventTitle"
    row = map_item(
        {"id": "1", "fields": {"EventTitle": "X", "StartDate": "2027-01-01", "BDPriority": 2}}, fields
    )
    assert row is not None and row.priority == 2


def test_demo_until_the_list_is_configured() -> None:
    settings = get_settings().model_copy(
        update={
            "conferences_mode": "auto",
            "conferences_sharepoint_list": None,
            "conferences_sharepoint_library": None,
        }
    )
    source = build_conference_source(settings)
    assert source.info().mode == "demo" and "not connected yet" in (source.info().reason or "")


def _records() -> list[ConferenceRecord]:
    return asyncio.run(DemoConferenceSource("test", today=TODAY).list_conferences())


def test_figures_priority_clashes_and_registration() -> None:
    r = build_conferences(_records(), TODAY, year=2027)
    tiles = {t.key: t for t in r.tiles}
    assert r.year == 2027 and len(r.conferences) == 11 and tiles["total"].value == "11"
    assert tiles["priority"].value == "7" and tiles["priority"].note == "Priority 2: 3 · Priority 3: 1"
    assert tiles["next"].value == "In 80 days" and r.next_id == r.conferences[0].id
    assert r.not_on_map == 0
    assert tiles["register"].value == "1" and r.conferences[0].register_soon  # closes in 25 days
    # Two clashes, both with someone booked twice.
    assert tiles["clashes"].value == "2" and tiles["clashes"].note == "2 with someone booked twice"
    assert [g.shared for g in r.clash_groups] == [["CD"], ["AB", "CD"]]
    assert r.clash_groups[1].names == [
        "Demo Oncology Congress",
        "Demo Nuclear Medicine Meeting",
        "Demo Global Biotech Convention",
    ]
    suzhou = next(c for c in r.conferences if c.city == "Suzhou")
    assert [(k.name, k.shared) for k in suzhou.clashes] == [("Demo Theranostics Conference", ["CD"])]
    assert r.attendees == ["AB", "CD", "EF"] and r.tags == ["BIO Partnering", "AUS Delegate"]


def test_filters_keep_the_clashes() -> None:
    p1 = build_conferences(_records(), TODAY, year=2027, priority=1)
    assert {c.priority for c in p1.conferences} == {1} and len(p1.conferences) == 7
    ab = build_conferences(_records(), TODAY, year=2027, who="AB")
    assert all("AB" in c.attendees for c in ab.conferences) and len(ab.conferences) == 4
    tagged = build_conferences(_records(), TODAY, year=2027, tag="AUS Delegate")
    assert [c.city for c in tagged.conferences] == ["Singapore", "Philadelphia"]
    assert len(tagged.clash_groups) == 2  # clashes are over the whole year, whatever the filter
    past = build_conferences(_records(), TODAY, year=2026)
    assert all(c.past for c in past.conferences) and past.next_id is None


def test_api_view_filter_and_export_without_costs(make_client) -> None:  # type: ignore[no-untyped-def]
    viewer: TestClient = make_client(Role.VIEWER)
    body = viewer.get(API).json()
    assert body["source"]["mode"] == "demo" and "can_see_cost" not in body
    assert all("cost" not in c and "budget" not in c for c in body["conferences"])
    assert viewer.post(f"{API}/refresh").status_code == 204
    res = viewer.get(f"{API}/export.xlsx")
    assert res.status_code == 200
    header = next(load_workbook(io.BytesIO(res.content))["Conferences"].iter_rows(values_only=True))
    assert "Priority" in header and "Date clash with" in header
    assert not any("cost" in str(h).lower() or "budget" in str(h).lower() for h in header)

    admin: TestClient = make_client(Role.ADMIN)
    body = admin.get(API, params={"year": 2027, "priority": 1}).json()
    assert body["conferences"] and all(c["priority"] == 1 for c in body["conferences"])
    assert admin.get(API, params={"priority": 4}).status_code == 422
    assert admin.get(API, params={"tag": "Nope"}).status_code == 422
    assert admin.get(f"{API}/export.xlsx", params={"who": "AB"}).status_code == 200
    events = admin.get("/api/v1/audit-events").json()["items"]
    assert any(e["action"] == "report.exported" and e["entity_id"] == "conferences" for e in events)


def test_switched_off_answers_404(make_client) -> None:  # type: ignore[no-untyped-def]
    client: TestClient = make_client(Role.ADMIN)
    off = get_settings().model_copy(update={"conferences_enabled": False})
    client.app.dependency_overrides[get_settings] = lambda: off  # type: ignore[attr-defined]
    assert client.get(API).status_code == 404


def test_next_conferences_on_the_overview(make_client) -> None:  # type: ignore[no-untyped-def]
    body: dict[str, Any] = make_client(Role.CTA).get("/api/v1/overview").json()
    card = next(s for s in body["sections"] if s["key"] == "conferences")
    assert card["title"] == "Next conferences" and card["link"] == "/conferences"
    assert len(card["rows"]) == 3 and "Demo conferences" in card["notice"]
    assert any("Priority" in r["detail"] for r in card["rows"])


# --- The BD document library: "Conferences YYYY" folders of Excel schedules (fictional workbooks) ---


def _workbook(sheets: dict[str, list[list[Any]]]) -> bytes:
    wb = Workbook()
    wb.remove(wb.active)  # type: ignore[arg-type]
    for title, rows in sheets.items():
        ws = wb.create_sheet(title)
        for row in rows:
            ws.append(row)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


_H1 = _workbook({
    "Conference Budget (2)": [
        ["Avion conferences H1"],
        ["Conference", "Date", "Location", "Attendee", "Budget AUD", "Priority", "Comment"],
        ["Example Theranostics Meeting", "7-10 Jan", "Phoenix, USA", "AB", 98765, 1, "BIO Partnering"],
        ["Example Oncology Forum", "23 – 25 March", "Taipai, Taiwan", "CD,EF", 43210, 2, None],
        [None, None, None, "Total", 142975, None, None],
        ["Footnote: budgets are estimates", None, None, None, None, None, None],
    ],
    "Example Forum costs": [["Expense", "Estimated Cost AB"], ["Flights", 5555]],
})  # fmt: skip
_SCHEDULE = _workbook({
    "Cover Sheet": [],
    "Conference Schedule": [
        ["Schedule"],
        ["Conference", "Date", "Location", "Website", "Registration Dates", "Comments"],
        ["Example Biotech Week", "9-12 Oct", "Salt Lake City", "https://example.org/week",
         "EBR to 30 Aug", None],
    ],
    "Conference Budget": [
        ["Budget"],
        ["Conference", "Date", "Location", "Budget (AUD)", "Gov Support", "Reason"],
        ["Example-Biotech Week 2026", "9 - 12 Oct", "Salt Lake City", 77777, "Example Trade Mission",
         "Partnering"],
    ],
    "Suggested Conference Schedule": [
        ["x"], ["Conference", "Date", "Location"], ["Example Suggestion", "1-2 Nov", "Boston"],
    ],
})  # fmt: skip


def test_library_picks_the_newest_schedule_per_half() -> None:
    names = ("Avion_Conferences_H1 2027.xlsx", "Schedule 2H 2026.xlsx", "Budget_2026.xlsx")
    assert [half_of(n) for n in names] == ["H1", "H2", "year"]
    files = [
        LibraryFile("i/1", "Avion Conference Schedule & Budget_H1_2027.xlsx", 2027, "2026-09-23T06:11:48Z"),
        LibraryFile("i/2", "Avion_Conferences_H1 2027.xlsx", 2027, "2026-09-23T06:12:56Z"),
        LibraryFile("i/3", "Avion_Conferences_H1 2027_Revised_V2.xlsx", 2027, "2026-09-23T22:08:04Z"),
        LibraryFile("i/4", "Avion_Conferences_H2 2027.xlsx", 2027, "2026-11-23T03:36:14Z"),
        LibraryFile("i/5", "Avion Conference List H1 2027.docx", 2027, "2026-12-01T00:00:00Z"),
        LibraryFile("i/6", "Avion Conference Schedule & Budget 2H 2026.xlsx", 2026, "2026-10-13T01:15:59Z"),
        LibraryFile("i/7", "~$Avion_Conferences_H2 2027.xlsx", 2027, "2026-12-02T00:00:00Z"),
    ]
    # A budget copy is read only when it is the only schedule for that half (2026 H2).
    assert [f.id for f in pick_files(files)] == ["i/4", "i/6", "i/3"]
    files.append(LibraryFile("i/8", "Avion Conference Schedule & Budget_H1_2027.xlsx", 2027, "2026-12-03"))
    assert "i/8" not in [f.id for f in pick_files(files)]  # a newer budget copy never replaces the schedule


def test_library_workbook_is_read_without_budgets_costs_or_footnotes() -> None:
    rows = read_workbook(_H1, LibraryFile("drive/items/A1", "Avion_Conferences_H1 2027.xlsx", 2027, "t", "u"))
    assert [r.name for r in rows] == ["Example Theranostics Meeting", "Example Oncology Forum"]
    first, second = rows
    assert (first.starts_on, first.ends_on, first.priority, first.attendees) == (
        date(2027, 1, 7), date(2027, 1, 10), 1, ["AB"])  # fmt: skip
    assert first.city == "Phoenix" and first.lat is not None and first.tags == ["BIO Partnering"]
    assert second.starts_on == date(2027, 3, 23) and second.attendees == ["CD", "EF"]
    assert second.lat is not None  # "Taipai", as spelled in a schedule
    assert first.id == "A1:example theranostics meeting" and first.source_url == "u"
    dumped = "".join(r.model_dump_json() for r in rows)
    assert not any(n in dumped for n in ("98765", "43210", "142975", "5555", "Total", "Footnote"))


def test_library_combines_a_conference_named_two_ways_across_sheets() -> None:
    rows = read_workbook(_SCHEDULE, LibraryFile("d/items/S", "Schedule & Budget 2H 2026.xlsx", 2026, "t"))
    assert len(rows) == 1  # the "Suggested ..." sheet is not the schedule
    week = rows[0]
    assert (week.name, week.starts_on, week.website) == (
        "Example Biotech Week", date(2026, 10, 9), "https://example.org/week")  # fmt: skip
    assert week.register_by == date(2026, 8, 30) and week.gov_support == "Example Trade Mission"
    assert week.notes == "Partnering" and "77777" not in week.model_dump_json()


def test_library_newer_file_wins_and_dropped_conferences_stay_dropped() -> None:
    older = _records()[:3]
    newer = [older[0].model_copy(update={"priority": 3, "id": "new"})]
    rows = combine([newer, older])
    assert len(rows) == 3 and next(r for r in rows if r.name == older[0].name).priority == 3


class _FakeGraph:
    """Answers the few Graph calls the library reader makes (no network)."""

    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = files

    async def get(self, path: str) -> dict[str, Any]:
        return {"id": "site-1"}

    async def get_all(self, path: str) -> list[dict[str, Any]]:
        if path.startswith("/sites/site-1/drives"):
            return [{"id": "other", "name": "Documents"}, {"id": "drv", "name": "Conferences"}]
        if path.startswith("/drives/drv/root/children"):
            return [
                {"id": "f27", "name": "Conferences 2027", "folder": {}},
                {"id": "tpl", "name": "Conference Templates", "folder": {}},
                {"id": "x", "name": "Readme.xlsx", "file": {}},
            ]
        if path.startswith("/drives/drv/items/f27/children"):
            return [
                {"id": "h1", "name": "Avion_Conferences_H1 2027.xlsx", "file": {},
                 "lastModifiedDateTime": "2026-09-23T22:08:04Z", "webUrl": "https://example/h1"},
                {"id": "sub", "name": "ASCO", "folder": {}},
            ]  # fmt: skip
        raise AssertionError(f"unexpected Graph call {path}")

    async def download_url(self, path: str) -> str:
        return path

    async def stream_url(self, url: str) -> AsyncIterator[bytes]:
        yield self.files[url]


def test_library_source_reads_year_folders_through_graph() -> None:
    graph = _FakeGraph({"/drives/drv/items/h1/content": _H1})
    source = LibraryConferenceSource(
        graph,  # type: ignore[arg-type]
        site_url="https://example.sharepoint.com/sites/BD",
        library="conferences",
        cache_seconds=60,
    )
    rows = asyncio.run(source.list_conferences())
    assert len(rows) == 2 and all(r.starts_on.year == 2027 for r in rows)
    info = source.info()
    assert info.mode == "sharepoint" and info.files == ["Avion_Conferences_H1 2027.xlsx"]
    assert info.fetched_at is not None and rows[0].source_url == "https://example/h1"
