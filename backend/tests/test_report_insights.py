"""The livelier report tops (user decision 2026-11-16): a headline sentence by fixed rules, and tile
trends from figures saved once a day (all studies only; nothing back-filled)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.reports.insights import TRACKED, number
from app.reports.models import ReportSnapshot
from app.studies.clock import today

API = "/api/v1/reports"
REPORTS = {
    "study-delivery": "study-delivery",
    "deviations": "deviations",
    "risks-issues": "risks-issues",
    "etmf": "etmf",
    "quality": "quality",
    "work-management": "work-management",
}


def test_number_reads_the_first_figure() -> None:
    assert number("71%") == 71 and number("142 of 200") == 142 and number("1,204") == 1204
    assert number("0.8") == 0.8 and number("—") is None


@pytest.mark.parametrize("path", list(REPORTS))
def test_every_report_has_a_headline(client: TestClient, path: str) -> None:
    body = client.get(f"{API}/{path}").json()
    insights = body["insights"]
    assert insights["headline"].endswith(".") and insights["tone"] in ("good", "warn", "bad")
    # The first visit saves today's figures: trends exist for the tracked tiles, but no line yet.
    tracked = set(TRACKED[path])
    assert set(insights["trends"]) <= tracked
    assert all(t["points"] == [] and t["change_text"] is None for t in insights["trends"].values())
    assert insights["history_since"] == today().isoformat()


def test_headlines_say_what_matters(client: TestClient) -> None:
    dev = client.get(f"{API}/deviations").json()["insights"]
    assert "still open" in dev["headline"] or "open" in dev["headline"]
    risks = client.get(f"{API}/risks-issues").json()["insights"]
    assert risks["headline"].startswith(("1 of", "2 of", "3 of")) and "overdue" in risks["headline"]
    etmf = client.get(f"{API}/etmf").json()["insights"]
    assert etmf["headline"].startswith("The eTMF is ") and "complete" in etmf["headline"]


def test_trend_line_and_change_since_a_month_ago(client: TestClient, db_session: Session) -> None:
    client.get(f"{API}/risks-issues")  # saves today's figures
    snap = db_session.scalars(select(ReportSnapshot).where(ReportSnapshot.kind == "tiles:risks-issues")).one()
    now = int(snap.data["open"])
    for weeks, open_n in [(5, now + 3), (3, now + 1)]:
        db_session.add(
            ReportSnapshot(
                tenant_id=snap.tenant_id,
                kind=snap.kind,
                source=snap.source,
                day=today() - timedelta(weeks=weeks),
                data={**snap.data, "open": open_n},
            )
        )
    db_session.commit()
    insights = client.get(f"{API}/risks-issues").json()["insights"]
    trend = insights["trends"]["open"]
    assert trend["points"] == [now + 3, now + 1, now]
    assert trend["change"] == -3 and trend["change_text"].startswith("-3 since ")
    assert trend["tone"] == "good"  # fewer open issues is better
    assert insights["history_since"] == (today() - timedelta(weeks=5)).isoformat()
    # Still one snapshot per day.
    days = db_session.scalars(select(ReportSnapshot.day).where(ReportSnapshot.kind == snap.kind)).all()
    assert len(days) == len(set(days)) == 3


def test_a_filtered_view_shows_no_trend(client: TestClient) -> None:
    study_id = client.get(f"{API}/deviations").json()["study_options"][0]["id"]
    insights = client.get(f"{API}/deviations", params={"study_id": study_id}).json()["insights"]
    assert insights["trends"] == {} and insights["history_since"] is None and insights["headline"]


def test_study_delivery_enrolment_history_from_the_daily_snapshot(client: TestClient) -> None:
    body = client.get(f"{API}/study-delivery").json()
    history = body["enrolment_history"]
    assert len(history) == 1 and history[0]["day"] == today().isoformat()  # the first sync's snapshot
    assert history[0]["enrolled"] >= 0
    study_id = body["study_options"][0]["id"]
    one = client.get(f"{API}/study-delivery", params={"study_id": study_id}).json()["enrolment_history"]
    assert one[0]["enrolled"] <= history[0]["enrolled"]
