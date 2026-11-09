"""Who may assign which tasks, people's own tasks, and tasks with several people."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.auth.rbac import ROLE_LABELS, Role
from app.studies.rules import overall_task_status


@pytest.fixture
def admin(make_client) -> TestClient:  # type: ignore[no-untyped-def]
    return make_client(Role.ADMIN)  # type: ignore[no-any-return]


def _study_id(client: TestClient) -> str:
    return client.get("/api/v1/studies").json()["studies"][0]["id"]  # type: ignore[no-any-return]


def test_overall_status_rule() -> None:
    assert overall_task_status(["Completed", "Completed"]) == "Completed"
    assert overall_task_status(["Completed", "Not started"]) == "In progress"
    assert overall_task_status(["In progress", "Blocked"]) == "Blocked"
    assert overall_task_status(["Not started", "Not started"]) == "Not started"


def test_role_labels() -> None:
    assert ROLE_LABELS[Role.CTA] == "Clinical Trials Associate"
    assert ROLE_LABELS[Role.SAFETY] == "Pharmacovigilance"


class TestProjectManager:
    def test_assigns_study_and_general_tasks(self, make_client) -> None:  # type: ignore[no-untyped-def]
        pm = make_client(Role.PROJECT_MANAGER, user_id="demo-pm-1")
        listed = pm.get("/api/v1/tasks").json()
        assert listed["can_assign"] == ["study", "general"]
        res = pm.post(
            "/api/v1/tasks",
            json={
                "study_id": _study_id(pm),
                "title": "Chase ethics",
                "assignee_ids": ["demo-cra-1", "demo-cra-2"],
            },
        )
        assert res.status_code == 201
        assert (
            pm.patch(f"/api/v1/tasks/{res.json()['id']}", json={"title": "Chase ethics renewal"}).status_code
            == 200
        )
        general = pm.post(
            "/api/v1/tasks",
            json={"category": "general", "title": "Team meeting notes", "assignee_id": "demo-cra-1"},
        )
        assert general.status_code == 201

    def test_vendor_and_system_tasks_for_themselves_only(self, make_client) -> None:  # type: ignore[no-untyped-def]
        pm = make_client(Role.PROJECT_MANAGER, user_id="demo-pm-1")
        body = {"category": "vendor", "subject_name": "Acme Lab", "title": "Check lab kits"}
        assert pm.post("/api/v1/tasks", json={**body, "assignee_id": "demo-cra-1"}).status_code == 403
        assert pm.post("/api/v1/tasks", json={**body, "assignee_id": "demo-pm-1"}).status_code == 201


class TestOwnTasks:
    @pytest.mark.parametrize("role", [Role.CRA, Role.CTA, Role.DATA_MANAGER, Role.SAFETY])
    def test_staff_create_tasks_for_themselves(self, make_client, admin: TestClient, role: Role) -> None:  # type: ignore[no-untyped-def]
        me = make_client(role, user_id="demo-cra-1")
        listed = me.get("/api/v1/tasks").json()
        assert listed["can_assign"] == []
        assert listed["can_create"] == ["study", "vendor", "system", "general"]

        res = me.post(
            "/api/v1/tasks",
            json={
                "study_id": _study_id(me),
                "title": "Prepare for SIV at site 102",
                "assignee_id": "demo-cra-1",
            },
        )
        assert res.status_code == 201
        task = res.json()
        assert task["own_task"] is True and task["can_edit"] is True

        # They can edit and cancel their own task, but not hand it to someone else.
        url = f"/api/v1/tasks/{task['id']}"
        assert me.patch(url, json={"title": "Prepare SIV slides"}).status_code == 200
        assert me.patch(url, json={"assignee_ids": ["demo-cra-1", "demo-cra-2"]}).status_code == 403
        assert me.post(f"{url}/status", json={"status": "Cancelled"}).status_code == 200

        # Visible to everyone (read-only to others).
        others = admin.get("/api/v1/tasks", params={"include_closed": "true"}).json()["tasks"]
        assert any(t["id"] == task["id"] for t in others)
        colleague = make_client(Role.CRA, user_id="demo-cra-2")
        seen = next(
            t
            for t in colleague.get("/api/v1/tasks", params={"include_closed": "true"}).json()["tasks"]
            if t["id"] == task["id"]
        )
        assert seen["can_edit"] is False and seen["can_update_status"] is False

    def test_cannot_assign_to_others(self, make_client) -> None:  # type: ignore[no-untyped-def]
        me = make_client(Role.CRA, user_id="demo-cra-1")
        body = {"category": "general", "title": "Something"}
        assert me.post("/api/v1/tasks", json={**body, "assignee_id": "demo-cra-2"}).status_code == 403
        res = me.post("/api/v1/tasks", json={**body, "assignee_ids": ["demo-cra-1", "demo-cra-2"]})
        assert res.status_code == 403

    def test_viewer_creates_nothing(self, make_client) -> None:  # type: ignore[no-untyped-def]
        viewer = make_client(Role.VIEWER, user_id="demo-cra-1")
        assert viewer.get("/api/v1/tasks").json()["can_create"] == []
        res = viewer.post(
            "/api/v1/tasks", json={"category": "general", "title": "Note", "assignee_id": "demo-cra-1"}
        )
        assert res.status_code == 403

    def test_admin_edits_own_tasks_of_others(self, make_client, admin: TestClient) -> None:  # type: ignore[no-untyped-def]
        me = make_client(Role.CRA, user_id="demo-cra-1")
        task = me.post(
            "/api/v1/tasks", json={"category": "general", "title": "Personal", "assignee_id": "demo-cra-1"}
        )
        assert (
            admin.patch(
                f"/api/v1/tasks/{task.json()['id']}", json={"title": "Personal (checked)"}
            ).status_code
            == 200
        )


class TestSeveralPeople:
    def _task(self, admin: TestClient) -> dict:  # type: ignore[type-arg]
        res = admin.post(
            "/api/v1/tasks",
            json={
                "category": "general",
                "title": "Complete GCP refresher",
                "assignee_ids": ["demo-cra-1", "demo-cra-2", "demo-dm-1", "demo-cra-1"],
                "due_date": "2027-01-31",
            },
        )
        assert res.status_code == 201, res.text
        return res.json()  # type: ignore[no-any-return]

    def test_each_person_has_own_status(self, admin: TestClient, make_client) -> None:  # type: ignore[no-untyped-def]
        task = self._task(admin)
        assert [a["name"] for a in task["assignees"]] == ["Demo CRA One", "Demo CRA Two", "Demo Data Manager"]
        assert task["progress"] == {"completed": 0, "total": 3}
        url = f"/api/v1/tasks/{task['id']}/status"

        one = make_client(Role.CRA, user_id="demo-cra-1")
        res = one.post(url, json={"status": "Completed"}).json()
        assert res["my_status"] == "Completed" and res["status"] == "In progress"
        assert res["progress"] == {"completed": 1, "total": 3}
        # Someone else's part is not theirs to change.
        assert one.post(url, json={"status": "Completed", "person_id": "demo-cra-2"}).status_code == 403

        # The task stays open (and in my list) until everyone has finished.
        assert [t["id"] for t in one.get("/api/v1/tasks", params={"assignee": "me"}).json()["tasks"]] == [
            task["id"]
        ]

        make_client(Role.CRA, user_id="demo-cra-2").post(url, json={"status": "Completed"})
        # A manager can update a person's part for them.
        res = admin.post(url, json={"status": "Completed", "person_id": "demo-dm-1"}).json()
        assert res["status"] == "Completed" and res["completed_at"] is not None
        assert res["progress"] == {"completed": 3, "total": 3}

    def test_blocked_and_reassignment_keep_statuses(self, admin: TestClient, make_client) -> None:  # type: ignore[no-untyped-def]
        task = self._task(admin)
        url = f"/api/v1/tasks/{task['id']}"
        make_client(Role.CRA, user_id="demo-cra-1").post(f"{url}/status", json={"status": "Completed"})
        assert (
            make_client(Role.CRA, user_id="demo-cra-2")
            .post(f"{url}/status", json={"status": "Blocked"})
            .json()["status"]
            == "Blocked"
        )
        # Remove the blocked person and add someone new: CRA One keeps "Completed".
        res = admin.patch(url, json={"assignee_ids": ["demo-cra-1", "demo-dm-1", "demo-safety-1"]}).json()
        assert {a["name"]: a["status"] for a in res["assignees"]} == {
            "Demo CRA One": "Completed",
            "Demo Data Manager": "Not started",
            "Demo Safety Lead": "Not started",
        }
        assert res["status"] == "In progress"

    def test_cancel_and_reopen(self, admin: TestClient, make_client) -> None:  # type: ignore[no-untyped-def]
        task = self._task(admin)
        url = f"/api/v1/tasks/{task['id']}/status"
        assert admin.post(url, json={"status": "Cancelled"}).json()["status"] == "Cancelled"
        person = make_client(Role.CRA, user_id="demo-cra-1")
        assert person.post(url, json={"status": "In progress"}).status_code == 409
        # Admin reopens by setting a status for everyone.
        assert (
            admin.patch(f"/api/v1/tasks/{task['id']}", json={"status": "Not started"}).json()["status"]
            == "Not started"
        )

    def test_needs_someone(self, admin: TestClient) -> None:
        res = admin.post("/api/v1/tasks", json={"category": "general", "title": "Nobody", "assignee_ids": []})
        assert res.status_code == 422
        res = admin.post(
            "/api/v1/tasks", json={"category": "general", "title": "Ghost", "assignee_ids": ["nobody"]}
        )
        assert res.status_code == 422
