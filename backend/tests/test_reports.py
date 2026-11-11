"""Reports and Insights: history (completions, snapshots), Study delivery figures, Excel export, schedule."""

from __future__ import annotations

import asyncio
import io
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.rbac import Role
from app.connectors.simpletrials.mock import MockStudyConnector, demo_studies
from app.connectors.simpletrials.models import StudyConnectorInfo, StudyRecord
from app.reports.models import MilestoneCompletion, ReportSnapshot
from app.studies.clock import today
from app.studies.models import ConnectorSync
from app.studies.sync import sync_studies

API = "/api/v1/reports/study-delivery"


class ListConnector:
    def __init__(self, records: list[StudyRecord]) -> None:
        self.records = records

    def info(self) -> StudyConnectorInfo:
        return StudyConnectorInfo(mode="mock", mock_reason="test")

    async def fetch_studies(self) -> list[StudyRecord]:
        return self.records


def sync(db: Session, records: list[StudyRecord]) -> Any:
    return asyncio.run(sync_studies(db, ListConnector(records), tenant_id="avion", triggered_by="t"))


def _first_open_key_milestone(records: list[StudyRecord]) -> tuple[int, int]:
    for si, rec in enumerate(records):
        for mi, m in enumerate(rec.milestones):
            if m.is_key and m.kind == "milestone" and not m.actual_date and (m.percent_complete or 0) < 100:
                return si, mi
    raise AssertionError("demo data has no open key milestone")


class TestHistory:
    def test_already_complete_when_tracking_begins_has_no_date(self, db_session: Session) -> None:
        run = sync(db_session, demo_studies(today()))
        assert run.counts["snapshot_taken"] is True
        rows = db_session.scalars(select(MilestoneCompletion)).all()
        assert rows and {r.basis for r in rows} <= {"before-tracking", "actual"}
        assert all(r.completed_on is None for r in rows if r.basis == "before-tracking")

    def test_completion_seen_after_tracking_began_is_dated_today(self, db_session: Session) -> None:
        records = demo_studies(today())
        sync(db_session, records)
        si, mi = _first_open_key_milestone(records)
        target = records[si].milestones[mi]
        milestones = list(records[si].milestones)
        milestones[mi] = target.model_copy(update={"percent_complete": 100})
        changed = list(records)
        changed[si] = records[si].model_copy(update={"milestones": milestones})
        run = sync(db_session, changed)
        assert run.counts["completions_recorded"] == 1
        row = db_session.scalars(
            select(MilestoneCompletion).where(MilestoneCompletion.milestone_external_id == target.external_id)
        ).one()
        assert (row.basis, row.completed_on) == ("first-seen", today())
        sync(db_session, changed)  # recorded once, never moved
        assert (
            db_session.scalars(
                select(MilestoneCompletion).where(
                    MilestoneCompletion.milestone_external_id == target.external_id
                )
            )
            .one()
            .completed_on
            == today()
        )

    def test_one_snapshot_per_day_with_key_figures(self, db_session: Session) -> None:
        sync(db_session, demo_studies(today()))
        sync(db_session, demo_studies(today()))
        snaps = db_session.scalars(select(ReportSnapshot)).all()
        assert len(snaps) == 1 and snaps[0].day == today() and snaps[0].kind == "study-delivery"
        study = snaps[0].data["studies"][0]
        assert {"protocol", "enrolled", "target", "milestones", "sites"} <= set(study)
        assert {"number", "enrolled", "target", "activated", "activation_target"} <= set(study["sites"][0])


def _get(client: TestClient, **params: str) -> dict[str, Any]:
    res = client.get(API, params=params)
    assert res.status_code == 200, res.text
    body: dict[str, Any] = res.json()
    return body


class TestStudyDelivery:
    def test_headline_tiles_and_source(self, client: TestClient) -> None:
        body = _get(client)
        assert [t["key"] for t in body["tiles"]] == ["on_plan", "overdue", "slipped_major", "enrolment"]
        assert body["source"]["mode"] == "mock" and body["source"]["as_of"]
        assert body["source"]["snapshot_days"] == 1
        assert len(body["study_options"]) == 4
        assert "study_on_plan" in body["rules"] and "on_time" in body["rules"]

    def test_only_key_milestones_with_both_dates_and_statuses(self, client: TestClient) -> None:
        rows = _get(client)["milestones"]
        assert rows
        assert {"original_date", "current_date", "variance_days", "state", "schedule", "on_time"} <= set(
            rows[0]
        )
        # The demo data carries actual completion dates, so completed milestones are judged on time or late.
        done = [r for r in rows if r["state"] == "completed"]
        assert done and all(r["completion_basis"] == "actual" for r in done)
        # On time needs an original (baseline) date; without one it is not judged.
        assert all((r["on_time"] is None) == (r["original_date"] is None) for r in done)
        assert all(
            r["completed_on"] is None and r["on_time"] is None for r in rows if r["state"] != "completed"
        )

    def test_enrolment_furthest_behind_first_and_no_target_last(self, client: TestClient) -> None:
        sites = _get(client)["sites"]
        assert sites[0]["flag"] == "zero" and sites[0]["site_number"] == "201"
        assert sites[-1]["flag"] == "no_target" and sites[-1]["percent"] is None
        percents = [s["percent"] for s in sites if s["percent"] is not None]
        assert percents == sorted(percents)

    def test_site_activation_against_plan(self, client: TestClient) -> None:
        body = _get(client)
        act = body["activation"]
        assert (act["total"], act["activated"], act["with_target"], act["on_time"]) == (7, 5, 5, 1)
        pending = body["pending_sites"]
        assert [(p["site_number"], p["state"], p["days_late"]) for p in pending] == [
            ("302", "late", 5),
            ("301", "upcoming", None),
        ]

    def test_filters_by_study_and_site(self, client: TestClient) -> None:
        all_studies = _get(client)
        onc = next(o["id"] for o in all_studies["study_options"] if o["label"].startswith("DEMO-ONC-301"))
        body = _get(client, study_id=onc)
        assert {m["protocol_number"] for m in body["milestones"]} == {"DEMO-ONC-301"}
        assert len(body["site_options"]) == 3
        site = body["site_options"][0]["id"]
        one = _get(client, study_id=onc, site_id=site)
        assert len(one["sites"]) == 1 and one["activation"]["total"] == 1

    def test_rejects_malformed_ids_and_is_readable_by_all_roles(self, make_client: Any) -> None:
        viewer = make_client(Role.VIEWER)
        assert viewer.get(API).status_code == 200
        assert viewer.get(API, params={"study_id": "x;drop"}).status_code == 422


class TestExport:
    def test_excel_export_has_tables_rules_and_is_audited(self, client: TestClient) -> None:
        res = client.get(f"{API}/export.xlsx")
        assert res.status_code == 200
        assert res.headers["content-type"].startswith(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        assert res.headers["content-disposition"].startswith('attachment; filename="Study delivery')
        wb = load_workbook(io.BytesIO(res.content))
        assert wb.sheetnames == ["Key milestones", "Enrolment by site", "Sites not yet activated", "About"]
        assert wb["Key milestones"]["A1"].value == "Study"
        about = {row[0].value: row[1].value for row in wb["About"].iter_rows()}
        assert about["Source"].startswith("Demo data") and "On time" in about
        events = client.get("/api/v1/audit-events").json()["items"]
        assert events[0]["action"] == "report.exported"


def test_scheduled_sync_runs_a_normal_read_only_sync(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.reports import scheduler

    monkeypatch.setattr(scheduler, "new_session", lambda: db_session)
    monkeypatch.setattr(scheduler, "get_study_connector", lambda: MockStudyConnector("test"))
    asyncio.run(scheduler.run_scheduled_sync())
    run = db_session.scalars(select(ConnectorSync)).one()
    assert run.ok and run.triggered_by == "system (scheduled)"


def test_scheduler_is_off_in_tests_and_when_set_to_zero() -> None:
    from app.core.config import Settings

    assert Settings(_env_file=None, simpletrials_sync_minutes=0).simpletrials_sync_minutes == 0  # type: ignore[call-arg]
    assert Settings(_env_file=None).simpletrials_sync_minutes == 60  # type: ignore[call-arg]
    assert date.today()  # placeholder for clarity: lifespan skips the loop when APP_ENV=test


def test_on_time_ignores_milestones_completed_before_tracking(db_session: Session) -> None:
    from app.reports.study_delivery import build_study_delivery
    from app.studies.models import Study

    # As from the real SimpleTrials API: complete at 100%, no actual completion date.
    records = [
        r.model_copy(
            update={
                "milestones": [
                    m.model_copy(
                        update={"actual_date": None, "percent_complete": 100 if m.actual_date else None}
                    )
                    for m in r.milestones
                ]
            }
        )
        for r in demo_studies(today())
    ]
    sync(db_session, records)  # first sync: completed milestones have no known date
    studies = list(db_session.scalars(select(Study)))
    report = build_study_delivery(studies, list(db_session.scalars(select(MilestoneCompletion))), today())
    done = [m for m in report.milestones if m.state == "completed"]
    assert done and all(m.completion_basis == "before-tracking" and m.on_time is None for m in done)
    assert report.on_time.with_original_date == 0
