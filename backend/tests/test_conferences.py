"""Conferences (BD): demo data, the SharePoint list reader (fake Graph data), figures, access and export."""

from __future__ import annotations

import asyncio
import io
from datetime import date
from typing import Any

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.auth.rbac import Role
from app.conferences.demo import DemoConferenceSource
from app.conferences.geo import locate
from app.conferences.models import AvionRole, ConferenceRecord
from app.conferences.report import build_conferences
from app.conferences.sharepoint import map_item, parse_field_map, role_of
from app.conferences.source import build_conference_source
from app.core.config import get_settings

API = "/api/v1/conferences"
TODAY = date(2026, 11, 13)


def test_cities_are_placed_without_online_lookups() -> None:
    assert locate("Boston") == (42.36, -71.06)
    assert locate("  boston, MA ") == (42.36, -71.06)
    assert locate("São Paulo") == (-23.55, -46.63)
    assert locate("Washington, D.C.") == locate("Washington, DC") is not None
    assert locate("Atlantis") is None and locate(None) is None


def test_reads_likely_column_names_and_skips_unusable_rows() -> None:
    fields = parse_field_map(None)
    item = {
        "id": "7",
        "webUrl": "https://example.sharepoint.com/sites/BD/Lists/Conferences/7_.000",
        "fields": {
            "Title": "Rare Disease Congress", "City": "Boston", "Country": "USA",
            "StartDate": "2027-04-20T00:00:00Z", "EndDate": "2027-04-22T00:00:00Z",
            "Participation": "Speaking slot confirmed", "Attendees": [{"LookupValue": "A. Person"}],
            "BoothNumber": "B12", "RegistrationDeadline": "2027-02-01T00:00:00Z", "Budget": "5100",
        },
    }  # fmt: skip
    row = map_item(item, fields)
    assert row is not None
    assert (row.name, row.city, row.starts_on, row.ends_on) == (
        "Rare Disease Congress",
        "Boston",
        date(2027, 4, 20),
        date(2027, 4, 22),
    )
    assert row.role == AvionRole.SPEAKING and row.team == "A. Person" and row.booth == "B12"
    assert (
        (row.lat, row.lon) == (42.36, -71.06)
        and row.cost == 5100.0
        and row.source_url
        and row.source_url.endswith("7_.000")
    )
    assert map_item({"id": "8", "fields": {"Title": "No date"}}, fields) is None
    assert map_item({"id": "9", "fields": {"StartDate": "2027-01-01"}}, fields) is None


def test_field_map_names_the_real_columns_first() -> None:
    fields = parse_field_map('{"role": "AvionRole", "name": ["EventTitle"]}')
    assert fields["role"][0] == "AvionRole" and fields["name"][0] == "EventTitle"
    row = map_item(
        {"id": "1", "fields": {"EventTitle": "X", "StartDate": "2027-01-01", "AvionRole": "Exhibitor"}},
        fields,
    )
    assert row is not None and row.role == AvionRole.EXHIBITING


def test_role_wording() -> None:
    assert role_of("Exhibiting (booth)") == AvionRole.EXHIBITING
    assert role_of("Presenting a poster") == AvionRole.SPEAKING
    assert role_of("Registered") == AvionRole.ATTENDING
    assert role_of("Maybe") == role_of(None) == AvionRole.CONSIDERING


def test_demo_until_the_list_is_configured() -> None:
    settings = get_settings().model_copy(
        update={"conferences_mode": "auto", "conferences_sharepoint_list": None}
    )
    source = build_conference_source(settings)
    assert source.info().mode == "demo" and "not connected yet" in (source.info().reason or "")


def _records() -> list[ConferenceRecord]:
    return asyncio.run(DemoConferenceSource("test", today=TODAY).list_conferences())


def test_figures_year_role_and_registration_due() -> None:
    r = build_conferences(_records(), TODAY, year=2027, role=None, can_see_cost=False)
    tiles = {t.key: t for t in r.tiles}
    assert r.year == 2027 and len(r.conferences) == 10 and tiles["total"].value == "10"
    assert tiles["next"].value == "In 80 days" and r.next_id == r.conferences[0].id
    assert tiles["stage"].value == "4"  # 2 exhibiting + 2 speaking
    assert all(c.cost is None for c in r.conferences) and r.not_on_map == 0
    assert tiles["register"].value == "1" and r.conferences[0].register_soon  # registration closes in 25 days
    speaking = build_conferences(_records(), TODAY, year=2027, role=AvionRole.SPEAKING, can_see_cost=True)
    assert [c.role for c in speaking.conferences] == [AvionRole.SPEAKING, AvionRole.SPEAKING]
    assert speaking.conferences[0].cost is not None
    past = build_conferences(_records(), TODAY, year=2026, role=None, can_see_cost=False)
    assert all(c.past for c in past.conferences) and past.next_id is None


def test_api_view_cost_and_export(make_client) -> None:  # type: ignore[no-untyped-def]
    viewer: TestClient = make_client(Role.VIEWER)
    body = viewer.get(API).json()
    assert body["source"]["mode"] == "demo" and body["can_see_cost"] is False
    assert all(c["cost"] is None for c in body["conferences"])
    assert viewer.post(f"{API}/refresh").status_code == 204
    res = viewer.get(f"{API}/export.xlsx")
    assert res.status_code == 200
    header = next(load_workbook(io.BytesIO(res.content))["Conferences"].iter_rows(values_only=True))
    assert "Cost" not in header

    admin: TestClient = make_client(Role.ADMIN)
    body = admin.get(API, params={"role": "Exhibiting"}).json()
    assert body["can_see_cost"] is True and all(c["role"] == "Exhibiting" for c in body["conferences"])
    assert any(c["cost"] for c in body["conferences"])
    header = next(
        load_workbook(io.BytesIO(admin.get(f"{API}/export.xlsx").content))["Conferences"].iter_rows(
            values_only=True
        )
    )
    assert "Cost" in header
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
