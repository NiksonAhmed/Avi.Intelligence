"""Risks and issues report (Reports and Insights): SimpleTrials action items, on the demo studies."""

from __future__ import annotations

import io
from datetime import date

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.auth.rbac import Role
from app.connectors.simpletrials.mock import demo_studies, with_demo_action_items
from app.reports.risks_issues import build_risks_issues
from app.studies.models import Study, StudyActionItem, StudySite

TODAY = date(2026, 11, 13)
API = "/api/v1/reports/risks-issues"


def _studies() -> list[Study]:
    out = []
    for i, rec in enumerate(with_demo_action_items(demo_studies(TODAY), TODAY)):
        study = Study(id=f"s{i}", protocol_number=rec.protocol_number, title=rec.title)
        study.sites = [StudySite(id=f"s{i}-{s.site_number}", **s.model_dump()) for s in rec.sites]
        study.action_items = [
            StudyActionItem(id=a.external_id, **a.model_dump()) for a in rec.action_items or []
        ]
        out.append(study)
    return out


def test_report_figures() -> None:
    r = build_risks_issues(_studies(), TODAY)
    tiles = {t.key: t for t in r.tiles}
    assert tiles["open"].value == "2" and tiles["open"].note == "3 recorded in all"
    assert tiles["overdue"].value == "1" and tiles["overdue"].note == "Oldest 6 days past due"
    assert tiles["high"].value == "1" and tiles["due_soon"].value == "1"
    assert tiles["closed"].value == "1" and tiles["closed"].note == "Median 28 days to close"
    assert [(p.label, p.count, p.open, p.overdue) for p in r.by_priority] == [
        ("High", 1, 1, 1),
        ("Normal", 2, 1, 0),
    ]
    assert r.by_category[0].label == "Site" and r.by_category[0].count == 3
    assert r.issues[0].days_overdue == 6 and r.issues[-1].closed  # overdue first, closed last
    assert sum(a.count for a in r.ageing) == 2
    assert sum(m.opened for m in r.trend) == 3 and sum(m.closed for m in r.trend) == 1
    assert r.by_site[0].overdue == 1 and r.has_issues


def test_site_filter() -> None:
    studies = _studies()
    site = studies[0].sites[1]
    r = build_risks_issues(studies, TODAY, study_id="s0", site_id=site.id)
    assert [i.where for i in r.issues] == [f"{site.site_number} · {site.name}"]
    assert r.issues[0].closed and {t.key: t for t in r.tiles}["open"].value == "0"


def test_api_and_excel_for_every_role(make_client) -> None:  # type: ignore[no-untyped-def]
    viewer: TestClient = make_client(Role.VIEWER)
    body = viewer.get(API).json()
    assert body["has_issues"] is True and len(body["issues"]) == 3
    assert body["source"]["mode"] == "mock"
    assert viewer.get(API, params={"study_id": "not-an-id"}).status_code == 422
    res = viewer.get(f"{API}/export.xlsx")
    assert res.status_code == 200
    assert res.headers["content-disposition"].startswith('attachment; filename="Risks and issues ')
    book = load_workbook(io.BytesIO(res.content))
    assert book.sheetnames[:4] == ["Issues", "By site", "By priority and category", "Monthly trend"]
    assert len(list(book["Issues"].iter_rows(values_only=True))) == 1 + 3


def test_export_is_audited(client: TestClient) -> None:
    client.get(f"{API}/export.xlsx")
    events = client.get("/api/v1/audit-events").json()["items"]
    assert any(e["action"] == "report.exported" and e["entity_id"] == "risks-issues" for e in events)
