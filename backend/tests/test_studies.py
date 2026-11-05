from __future__ import annotations

import asyncio
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.rbac import Role
from app.connectors.simpletrials.mock import MockStudyConnector, demo_studies
from app.connectors.simpletrials.models import StudyConnectorInfo, StudyRecord
from app.studies.models import Study
from app.studies.rules import (
    MilestoneState,
    enrolment_percent,
    milestone_state,
    risk_rating,
    task_overdue,
    total_enrolled,
)
from app.studies.sync import sync_studies

TODAY = date(2026, 11, 5)


class TestRules:
    def test_milestone_states(self) -> None:
        assert milestone_state(TODAY, TODAY, TODAY) == MilestoneState.COMPLETED
        assert milestone_state(TODAY - timedelta(days=1), None, TODAY) == MilestoneState.OVERDUE
        assert milestone_state(TODAY, None, TODAY) == MilestoneState.DUE_SOON
        assert milestone_state(TODAY + timedelta(days=14), None, TODAY) == MilestoneState.DUE_SOON
        assert milestone_state(TODAY + timedelta(days=15), None, TODAY) == MilestoneState.UPCOMING
        assert milestone_state(None, None, TODAY) == MilestoneState.NOT_PLANNED

    def test_enrolment_never_guessed(self) -> None:
        assert enrolment_percent(30, 120) == 25.0
        assert enrolment_percent(30, None) is None
        assert enrolment_percent(30, 0) is None
        assert enrolment_percent(None, 100) is None
        assert total_enrolled([None, None]) is None
        assert total_enrolled([3, None, 4]) == 7

    def test_risk_rating_bands(self) -> None:
        assert [risk_rating(s) for s in (1, 2, 3, 4, 6, 9)] == [
            "Low",
            "Low",
            "Medium",
            "Medium",
            "High",
            "High",
        ]

    def test_task_overdue(self) -> None:
        yesterday = TODAY - timedelta(days=1)
        assert task_overdue(yesterday, "In progress", TODAY)
        assert not task_overdue(yesterday, "Completed", TODAY)
        assert not task_overdue(yesterday, "Cancelled", TODAY)
        assert not task_overdue(None, "Not started", TODAY)
        assert not task_overdue(TODAY, "Not started", TODAY)


class ListConnector:
    def __init__(self, records: list[StudyRecord]) -> None:
        self.records = records

    def info(self) -> StudyConnectorInfo:
        return StudyConnectorInfo(mode="mock")

    async def fetch_studies(self) -> list[StudyRecord]:
        return self.records


class FailingConnector(ListConnector):
    async def fetch_studies(self) -> list[StudyRecord]:
        raise RuntimeError("SimpleTrials unavailable")


class TestSync:
    def test_sync_inserts_then_updates_and_flags_removed(self, db_session: Session) -> None:
        records = demo_studies(TODAY)
        run = asyncio.run(
            sync_studies(db_session, ListConnector(records), tenant_id="avion", triggered_by="t")
        )
        assert run.ok and run.counts["created"] == len(records)

        changed = [r.model_copy(update={"title": "Renamed"}) for r in records[1:]]
        run = asyncio.run(
            sync_studies(db_session, ListConnector(changed), tenant_id="avion", triggered_by="t")
        )
        assert run.counts == {
            "studies": len(changed),
            "created": 0,
            "updated": len(changed),
            "no_longer_in_source": 1,
        }
        studies = {s.external_id: s for s in db_session.scalars(select(Study))}
        assert studies[records[0].external_id].in_source is False
        assert studies[records[1].external_id].title == "Renamed"
        assert len(studies[records[1].external_id].sites) == len(records[1].sites)

    def test_failed_sync_keeps_previous_copy(self, db_session: Session) -> None:
        asyncio.run(
            sync_studies(db_session, ListConnector(demo_studies(TODAY)), tenant_id="avion", triggered_by="t")
        )
        run = asyncio.run(sync_studies(db_session, FailingConnector([]), tenant_id="avion", triggered_by="t"))
        assert not run.ok and "unavailable" in (run.error or "")
        assert len(db_session.scalars(select(Study)).all()) == 4


def _first_study(client: TestClient) -> dict:  # type: ignore[type-arg]
    return client.get("/api/v1/studies").json()["studies"][0]  # type: ignore[no-any-return]


class TestStudyApi:
    def test_portfolio_auto_syncs_and_labels_demo(self, client: TestClient) -> None:
        body = client.get("/api/v1/studies").json()
        assert len(body["studies"]) == 4
        assert body["source"]["connector"]["mode"] == "mock"
        assert body["source"]["last_successful_sync_at"] is not None
        assert "milestone_overdue" in body["rules"]
        no_target = next(s for s in body["studies"] if s["protocol_number"] == "DEMO-RES-202")
        assert no_target["enrolment_percent"] is None and no_target["enrolled"] == 9

    def test_filters(self, client: TestClient) -> None:
        assert len(client.get("/api/v1/studies", params={"phase": "Phase II"}).json()["studies"]) == 2
        assert len(client.get("/api/v1/studies", params={"q": "asthma"}).json()["studies"]) == 1

    def test_detail(self, client: TestClient) -> None:
        study = _first_study(client)
        body = client.get(f"/api/v1/studies/{study['id']}").json()
        assert body["study"]["protocol_number"] == study["protocol_number"]
        assert body["milestones"] and all("state" in m for m in body["milestones"])
        assert client.get("/api/v1/studies/00000000-0000-0000-0000-000000000000").status_code == 404

    def test_viewer_can_read_but_not_sync(self, make_client) -> None:  # type: ignore[no-untyped-def]
        viewer = make_client(Role.VIEWER)
        assert viewer.get("/api/v1/studies").status_code == 200
        assert viewer.post("/api/v1/connectors/simpletrials/sync").status_code == 403

    def test_admin_sync_is_audited(self, client: TestClient) -> None:
        body = client.post("/api/v1/connectors/simpletrials/sync").json()
        assert body["last_sync"]["ok"] is True
        events = client.get("/api/v1/audit-events").json()["items"]
        assert any(e["action"] == "connector.synced" for e in events)


@pytest.fixture
def admin(make_client) -> TestClient:  # type: ignore[no-untyped-def]
    return make_client(Role.ADMIN)  # type: ignore[no-any-return]


def _create_task(admin: TestClient, assignee: str = "demo-cra-1") -> dict:  # type: ignore[type-arg]
    study = _first_study(admin)
    res = admin.post(
        "/api/v1/tasks",
        json={
            "study_id": study["id"],
            "title": "Chase site 102 ethics renewal",
            "assignee_id": assignee,
            "due_date": "2026-01-01",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()  # type: ignore[no-any-return]


class TestTaskPermissions:
    def test_admin_creates_task_with_reference_and_audit(self, admin: TestClient) -> None:
        task = _create_task(admin)
        assert task["reference"] == "TSK-0001"
        assert task["assignee_name"] == "Demo CRA One"
        assert task["status"] == "Not started"
        assert task["overdue"] is True
        events = admin.get("/api/v1/audit-events").json()["items"]
        assert any(e["action"] == "task.created" for e in events)

    @pytest.mark.parametrize(
        "role", [Role.PROJECT_MANAGER, Role.CRA, Role.DATA_MANAGER, Role.SAFETY, Role.VIEWER]
    )
    def test_non_admins_cannot_create_or_edit(self, admin: TestClient, make_client, role: Role) -> None:  # type: ignore[no-untyped-def]
        task = _create_task(admin)
        other = make_client(role)
        study = _first_study(other)
        assert (
            other.post(
                "/api/v1/tasks", json={"study_id": study["id"], "title": "Nope", "assignee_id": "demo-cra-1"}
            ).status_code
            == 403
        )
        assert other.patch(f"/api/v1/tasks/{task['id']}", json={"title": "Changed"}).status_code == 403
        # Read-only access still works.
        listed = other.get("/api/v1/tasks").json()
        assert listed["can_manage"] is False
        assert listed["tasks"][0]["can_update_status"] is False

    def test_only_assignee_updates_status(self, admin: TestClient, make_client) -> None:  # type: ignore[no-untyped-def]
        task = _create_task(admin, assignee="demo-cra-1")
        url = f"/api/v1/tasks/{task['id']}/status"

        someone_else = make_client(Role.PROJECT_MANAGER, user_id="demo-pm-1")
        assert someone_else.post(url, json={"status": "In progress"}).status_code == 403

        assignee = make_client(Role.CRA, user_id="demo-cra-1")
        mine = assignee.get("/api/v1/tasks", params={"assignee": "me"}).json()["tasks"]
        assert [t["id"] for t in mine] == [task["id"]]
        assert mine[0]["can_update_status"] is True

        res = assignee.post(url, json={"status": "Completed"})
        assert res.status_code == 200 and res.json()["status"] == "Completed"
        assert res.json()["completed_at"] is not None
        assert assignee.post(url, json={"status": "Cancelled"}).status_code == 403
        assert assignee.post(url, json={"status": "Done-ish"}).status_code == 422

        # Completed tasks drop out of the default (open) list but remain retrievable.
        assert assignee.get("/api/v1/tasks", params={"assignee": "me"}).json()["tasks"] == []
        assert len(assignee.get("/api/v1/tasks", params={"include_closed": "true"}).json()["tasks"]) == 1

        events = admin.get("/api/v1/audit-events").json()["items"]
        change = next(e for e in events if e["action"] == "task.status_changed")
        assert change["details"] == {"from": "Not started", "to": "Completed"}

    def test_admin_edit_records_changes(self, admin: TestClient) -> None:
        task = _create_task(admin)
        res = admin.patch(f"/api/v1/tasks/{task['id']}", json={"assignee_id": "demo-cra-2", "due_date": None})
        assert res.status_code == 200
        assert res.json()["assignee_name"] == "Demo CRA Two" and res.json()["due_date"] is None
        event = next(
            e for e in admin.get("/api/v1/audit-events").json()["items"] if e["action"] == "task.updated"
        )
        assert event["details"]["changes"]["assignee"] == {"from": "Demo CRA One", "to": "Demo CRA Two"}

    def test_validation(self, admin: TestClient) -> None:
        study = _first_study(admin)
        bad_person = {"study_id": study["id"], "title": "Valid title", "assignee_id": "nobody"}
        assert admin.post("/api/v1/tasks", json=bad_person).status_code == 422
        bad_study = {"study_id": "x", "title": "Valid title", "assignee_id": "demo-cra-1"}
        assert admin.post("/api/v1/tasks", json=bad_study).status_code == 422
        blank = {"study_id": study["id"], "title": "   ", "assignee_id": "demo-cra-1"}
        assert admin.post("/api/v1/tasks", json=blank).status_code == 422

    def test_open_task_counts_on_portfolio(self, admin: TestClient) -> None:
        task = _create_task(admin)
        study = next(
            s for s in admin.get("/api/v1/studies").json()["studies"] if s["id"] == task["study"]["id"]
        )
        assert study["open_tasks"] == 1


class TestRiskPermissions:
    def _create(self, admin: TestClient, owner: str = "demo-pm-1") -> dict:  # type: ignore[type-arg]
        study = _first_study(admin)
        res = admin.post(
            "/api/v1/risks",
            json={
                "study_id": study["id"],
                "kind": "risk",
                "title": "Slow enrolment at site 102",
                "likelihood": 3,
                "impact": 2,
                "owner_id": owner,
                "mitigation": "Add a referral site",
            },
        )
        assert res.status_code == 201, res.text
        return res.json()  # type: ignore[no-any-return]

    def test_score_and_rating(self, admin: TestClient) -> None:
        risk = self._create(admin)
        assert risk["reference"] == "RSK-0001"
        assert (risk["score"], risk["rating"]) == (6, "High")

    def test_owner_only_status_and_admin_only_edit(self, admin: TestClient, make_client) -> None:  # type: ignore[no-untyped-def]
        risk = self._create(admin, owner="demo-pm-1")
        url = f"/api/v1/risks/{risk['id']}/status"
        assert (
            make_client(Role.CRA, user_id="demo-cra-1").post(url, json={"status": "Closed"}).status_code
            == 403
        )
        owner = make_client(Role.PROJECT_MANAGER, user_id="demo-pm-1")
        assert owner.patch(f"/api/v1/risks/{risk['id']}", json={"impact": 1}).status_code == 403
        res = owner.post(url, json={"status": "Mitigating"})
        assert res.status_code == 200 and res.json()["status"] == "Mitigating"

    def test_issue_reference_and_invalid_scores(self, admin: TestClient) -> None:
        study = _first_study(admin)
        base = {"study_id": study["id"], "title": "Protocol deviation trend", "owner_id": "demo-pm-1"}
        res = admin.post("/api/v1/risks", json={**base, "kind": "issue", "likelihood": 1, "impact": 1})
        assert res.json()["reference"] == "ISS-0001"
        assert admin.post("/api/v1/risks", json={**base, "likelihood": 4, "impact": 1}).status_code == 422


def test_people_directory(client: TestClient) -> None:
    people = client.get("/api/v1/people").json()
    assert {"dev-user", "demo-cra-1"} <= {p["id"] for p in people}


def test_mock_connector_info() -> None:
    assert MockStudyConnector("x").info().mode == "mock"
