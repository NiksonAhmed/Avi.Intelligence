"""Protocol deviations report (Reports and Insights), on the demo SimpleTrials studies."""

from __future__ import annotations

import io
from datetime import date

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.auth.rbac import Role
from app.connectors.simpletrials.mock import demo_studies, with_demo_deviations
from app.reports.deviations import build_deviations
from app.studies.models import Study, StudyDeviation, StudySite

TODAY = date(2026, 11, 12)


def _studies() -> list[Study]:
    out = []
    for i, rec in enumerate(with_demo_deviations(demo_studies(TODAY), TODAY)):
        study = Study(id=f"s{i}", protocol_number=rec.protocol_number, title=rec.title)
        study.sites = [StudySite(id=f"s{i}-{s.site_number}", **s.model_dump()) for s in rec.sites]
        study.deviations = [StudyDeviation(id=d.external_id, **d.model_dump()) for d in rec.deviations or []]
        out.append(study)
    return out


def test_report_figures() -> None:
    r = build_deviations(_studies(), TODAY)
    tiles = {t.key: t for t in r.tiles}
    assert tiles["total"].value == "8" and tiles["total"].note == "3 in the last 30 days"
    assert tiles["open"].value == "5" and tiles["major"].value == "3"
    assert tiles["major"].note == "3 still open" and tiles["major"].tone == "bad"
    assert [c.label for c in r.by_severity] == ["Critical", "Major", "Minor"]
    assert [c.count for c in r.by_severity] == [1, 2, 5]
    assert r.by_category[0].label == "Visit schedule" and r.by_category[0].count == 3
    assert r.deviations[0].severity == "Critical" and not r.deviations[0].closed  # open, most severe first
    assert all(d.closed for d in r.deviations[-3:])
    assert sum(a.count for a in r.ageing) == 5
    assert sum(m.critical + m.major + m.minor + m.other for m in r.trend) == 8 and len(r.trend) == 12
    first_site = r.by_site[0]
    assert first_site.per_10 == round(first_site.total / (first_site.enrolled or 1) * 10, 1)
    assert tiles["identify"].value == "3.5"  # median of 3, 10, 2, 20, 1, 1, 5, 4


def test_site_filter() -> None:
    studies = _studies()
    site = studies[0].sites[1]
    r = build_deviations(studies, TODAY, study_id=studies[0].id, site_id=site.id)
    assert len(r.deviations) == 3 and {d.where for d in r.deviations} == {f"{site.site_number} · {site.name}"}
    assert [b.id for b in r.study_options] == [s.id for s in studies]


def test_api_and_excel(make_client) -> None:  # type: ignore[no-untyped-def]
    viewer: TestClient = make_client(Role.VIEWER)
    body = viewer.get("/api/v1/reports/deviations").json()
    assert body["has_deviations"] is True and len(body["deviations"]) == 8
    assert body["source"]["mode"] == "mock" and "severity" in body["rules"]
    res = viewer.get("/api/v1/reports/deviations/export.xlsx")
    assert res.status_code == 200 and "Protocol deviations" in res.headers["content-disposition"]
    wb = load_workbook(io.BytesIO(res.content), read_only=True)
    assert wb.sheetnames == ["Deviations", "By site", "By category and severity", "Monthly trend", "About"]
    rows = list(wb["Deviations"].iter_rows(values_only=True))
    assert len(rows) == 9 and rows[0][:3] == ("No.", "Study", "Site")
