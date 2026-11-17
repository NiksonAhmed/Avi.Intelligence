"""Site feasibility (user decision 2026-11-18): demo sites, fixed rules, everyone may view."""

from __future__ import annotations

import asyncio
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.site_feasibility.demo import DemoFeasibilitySource
from app.site_feasibility.models import SCORE_MAX, FeasibilitySite
from app.site_feasibility.report import (
    Recommendation,
    answered,
    build_site_detail,
    build_site_feasibility,
    recommendation_of,
    survey_due,
)

API = "/api/v1/site-feasibility"
TODAY = date(2026, 11, 18)


def _site(**kw: object) -> FeasibilitySite:
    return FeasibilitySite(id="x", name="X", city="Hobart", state="TAS", lat=0, lon=0, **kw)  # type: ignore[arg-type]


def test_rules() -> None:
    assert recommendation_of(_site()) == Recommendation.NOT_ASSESSED
    assert (
        recommendation_of(_site(recommend_diagnostics="Yes", recommend_therapeutics="Yes"))
        == Recommendation.BOTH
    )
    assert recommendation_of(_site(recommend_therapeutics="Yes")) == Recommendation.THERAPEUTICS
    assert recommendation_of(_site(recommend_diagnostics="Yes", recommend_therapeutics="No")) == (
        Recommendation.DIAGNOSTICS
    )
    assert recommendation_of(_site(recommend_diagnostics="No")) == Recommendation.NOT_RECOMMENDED
    assert survey_due(_site(), TODAY)  # never surveyed
    assert survey_due(_site(last_survey=date(2025, 11, 18)), TODAY)  # exactly 12 months
    assert not survey_due(_site(last_survey=date(2025, 11, 19)), TODAY)
    assert answered(_site()) == 0
    assert SCORE_MAX == 40


@pytest.fixture
def sites() -> list[FeasibilitySite]:
    return asyncio.run(DemoFeasibilitySource("test", today=TODAY).list_sites())


def test_page_figures(sites: list[FeasibilitySite]) -> None:
    r = build_site_feasibility(sites, TODAY)
    tiles = {t.key: t.value for t in r.tiles}
    assert tiles == {
        "sites": "12",
        "therapeutics": "7",
        "diagnostics": "9",
        "hrec": "8 wk",
        "surveys_due": "3",
    }
    assert r.headline.startswith("12 sites surveyed: 7 recommended for therapeutics and 9 for diagnostics.")
    assert "Demo Site 109 not accepting new trials" in r.headline
    assert [d.site for d in r.surveys_due] == [
        "Demo Site 109",
        "Demo Site 106",
        "Demo Site 110",
    ]  # oldest first
    assert (
        r.rows[0].recommendation == Recommendation.BOTH
        and r.rows[-1].recommendation == Recommendation.NOT_ASSESSED
    )
    rows = {x.site_id: x for x in r.rows}
    assert rows["demo-103"].score == 39 and rows["demo-108"].score is None
    assert rows["demo-109"].answered < 50 and rows["demo-101"].answered == 100
    # Fastest start-up: recommended, accepting sites only, quickest first.
    assert r.fastest[0].site == "Demo Site 104" and all(f.site_id != "demo-111" for f in r.fastest)
    pins = {p.id: p for p in r.sites}
    assert pins["demo-101"].short == "Diag · Ther" and pins["demo-109"].survey_due


def test_filters(sites: list[FeasibilitySite]) -> None:
    by_isotope = build_site_feasibility(sites, TODAY, isotope="225Ac")
    assert {p.id for p in by_isotope.sites} == {"demo-102", "demo-103", "demo-105", "demo-106", "demo-109"}
    by_indication = build_site_feasibility(sites, TODAY, indication="Melanoma")
    assert {p.id for p in by_indication.sites} == {"demo-101", "demo-108"}
    ther = build_site_feasibility(sites, TODAY, recommendation=Recommendation.THERAPEUTICS)
    assert [p.id for p in ther.sites] == ["demo-106"]
    none = build_site_feasibility(sites, TODAY, isotope="68Ga", indication="Myelofibrosis")
    assert none.sites == [] and none.headline.startswith("No sites match")


def test_site_detail(sites: list[FeasibilitySite]) -> None:
    d = build_site_detail(next(s for s in sites if s.id == "demo-103"), TODAY, "demo-103")
    assert d.recommendation_label == "Diagnostics and therapeutics" and d.validation_site_id == "demo-103"
    assert d.score == 39 and d.score_max == 40 and len(d.score_rows) == 9
    assert d.score_rows[0].criterion == "Time to RGO approval" and d.score_rows[0].max == 3
    assert len(d.experience.by_indication) == 13
    assert d.equipment["ECG"] == "Yes"


def test_api(client: TestClient) -> None:
    body = client.get(API).json()
    assert body["source"]["mode"] == "demo" and len(body["sites"]) == 12
    assert client.get(API, params={"isotope": "99Tc"}).status_code == 422
    assert client.get(API, params={"indication": "Nope"}).status_code == 422
    assert client.get(API, params={"recommendation": "nope"}).status_code == 422
    one = client.get(f"{API}/sites/demo-102").json()
    assert one["validation_site_id"] == "demo-102"  # the same site on Site validation
    assert one["score"] == 17 and one["performance"]["projects"][0]["protocol"] == "DEMO-RD-110"
    assert client.get(f"{API}/sites/nope").status_code == 404
    assert client.post(f"{API}/refresh").status_code == 204


def test_export_is_audited(client: TestClient) -> None:
    r = client.get(f"{API}/export.xlsx", params={"recommendation": "both"})
    assert r.status_code == 200 and r.content[:2] == b"PK"
    items = client.get("/api/v1/audit-events").json()["items"]
    assert any(e["entity_id"] == "site-feasibility" for e in items)


def test_everyone_may_view(make_client) -> None:  # type: ignore[no-untyped-def]
    from app.auth.rbac import Role

    for role in Role:
        assert make_client(role).get(API).status_code == 200, role
