"""Site validation status (physics request 2026-11-17): demo sites, fixed rules, everyone may view."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.site_validation.demo import DemoSiteSource
from app.site_validation.models import EquipmentKind, SiteRecord, Validation
from app.site_validation.report import (
    Status,
    build_site_detail,
    build_site_validation,
    next_review,
    status_of,
)

API = "/api/v1/site-validation"
TODAY = date(2026, 11, 17)


def _v(on: date, files: bool = True, review: date | None = None) -> Validation:
    return Validation(equipment=EquipmentKind.PET_CT, isotope="64Cu", validated_by="ARTnet", validated_on=on,
                      files_available=files, next_review=review)  # fmt: skip


def test_review_rules() -> None:
    assert next_review(_v(date(2026, 1, 10))) == date(2027, 1, 10)  # 12 months by default
    assert next_review(_v(date(2024, 2, 29))) == date(2025, 2, 28)
    assert next_review(_v(date(2026, 1, 10), review=date(2026, 6, 1))) == date(2026, 6, 1)  # date given wins
    assert status_of(_v(date(2025, 11, 1)), TODAY) == Status.OVERDUE
    assert status_of(_v(date(2025, 12, 20)), TODAY) == Status.DUE_SOON  # due in 33 days
    assert status_of(_v(date(2026, 5, 1)), TODAY) == Status.IN_DATE
    assert status_of(_v(date(2026, 5, 1), files=False), TODAY) == Status.FILES_MISSING
    assert status_of(_v(date(2025, 11, 1), files=False), TODAY) == Status.OVERDUE  # overdue beats missing


@pytest.fixture
def sites() -> list[SiteRecord]:
    import asyncio

    return asyncio.run(DemoSiteSource("test", today=TODAY).list_sites())


def test_page_figures(sites: list[SiteRecord]) -> None:
    r = build_site_validation(sites, TODAY)
    tiles = {t.key: t.value for t in r.tiles}
    assert tiles["overdue"] == "1" and tiles["missing"] == "1" and tiles["due"] == "3"
    assert tiles["validated"] == "9 of 12"
    assert r.headline.startswith("9 of 12 sites hold an in-date validation.")
    assert "Demo Site 103 · PET/CT 90Y is overdue" in r.headline
    assert r.rows[0].status == Status.OVERDUE  # worst first
    pins = {p.id: p for p in r.sites}
    assert pins["demo-103"].status == Status.OVERDUE and pins["demo-103"].attention
    assert pins["demo-111"].status == Status.NONE and not pins["demo-111"].attention
    assert pins["demo-109"].status == Status.BOOKED  # booked scan, nothing validated yet
    assert pins["demo-101"].equipment == ["PET", "SPECT", "DC", "GC"]
    assert pins["demo-101"].phantoms == 2 and pins["demo-111"].phantoms == 0
    assert all(s.status.value != "Passed" for s in r.scans)
    assert [x.days for x in r.reviews] == sorted(x.days for x in r.reviews)


def test_filters_recolour_the_map(sites: list[SiteRecord]) -> None:
    r = build_site_validation(sites, TODAY, equipment=EquipmentKind.SPECT_CT, isotope="225Ac")
    assert {(x.equipment, x.isotope) for x in r.rows} == {(EquipmentKind.SPECT_CT, "225Ac")}
    pins = {p.id: p for p in r.sites}
    assert pins["demo-103"].status == Status.IN_DATE  # its overdue PET/CT 90Y is filtered out


def test_site_detail_grid(sites: list[SiteRecord]) -> None:
    d = build_site_detail(next(s for s in sites if s.id == "demo-102"), TODAY)
    cells = {(c.equipment, c.isotope): c for c in d.grid}
    assert len(d.grid) == 4 * 5
    assert cells[(EquipmentKind.PET_CT, "64Cu")].state is None  # no PET/CT on site
    assert cells[(EquipmentKind.SPECT_CT, "225Ac")].state == Status.IN_DATE
    assert cells[(EquipmentKind.DOSE_CALIBRATOR, "225Ac")].state == Status.FILES_MISSING
    assert cells[(EquipmentKind.SPECT_CT, "64Cu")].state == Status.NONE
    assert d.missing_equipment == [EquipmentKind.PET_CT, EquipmentKind.GAMMA_COUNTER]
    assert d.licensed == ["225Ac", "177Lu"]


def test_api(client: TestClient) -> None:
    body = client.get(API).json()
    assert body["source"]["mode"] == "demo" and len(body["sites"]) == 12
    assert client.get(API, params={"isotope": "99Tc"}).status_code == 422
    one = client.get(f"{API}/sites/{body['sites'][0]['id']}").json()
    assert one["grid"] and one["qa"] is not None and one["transfer"] is not None
    assert client.get(f"{API}/sites/nope").status_code == 404
    assert client.post(f"{API}/refresh").status_code == 204


def test_export_is_audited(client: TestClient) -> None:
    r = client.get(f"{API}/export.xlsx", params={"equipment": "PET/CT"})
    assert r.status_code == 200 and r.content[:2] == b"PK"
    items = client.get("/api/v1/audit-events").json()["items"]
    assert any(e["entity_id"] == "site-validation" for e in items)


def test_everyone_may_view(make_client) -> None:  # type: ignore[no-untyped-def]
    from app.auth.rbac import Role

    for role in Role:
        assert make_client(role).get(API).status_code == 200, role
