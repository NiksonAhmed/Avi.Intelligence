"""Task categories: Study, Procedures and SOPs, Vendor, Computer system and General.

Administrators manage every category; Quality Assurance may also create, assign and edit
Procedures and SOPs tasks. SOP tasks can only name SOPs/forms from the live approved list.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.auth.rbac import Role

SOP = "demo-sop-011"  # Effective demo SOP
FORM = "demo-sop-011-a"  # its form
IN_REVIEW = "demo-sop-050"  # not approved


@pytest.fixture
def admin(make_client) -> TestClient:  # type: ignore[no-untyped-def]
    return make_client(Role.ADMIN)  # type: ignore[no-any-return]


@pytest.fixture
def qa(make_client) -> TestClient:  # type: ignore[no-untyped-def]
    return make_client(Role.QA, user_id="demo-pm-2")  # type: ignore[no-any-return]


def _sop_task(client: TestClient, ids: list[str] | None = None, **extra: object) -> dict:  # type: ignore[type-arg]
    res = client.post(
        "/api/v1/tasks",
        json={
            "category": "sop",
            "document_ids": ids or [SOP, FORM],
            "title": "Periodic review of SOP-011",
            "description": "Check section 6 against ICH E6(R3).",
            "assignee_id": "demo-cra-1",
            "due_date": "2027-01-31",
            **extra,
        },
    )
    assert res.status_code == 201, res.text
    return res.json()  # type: ignore[no-any-return]


class TestSopTasks:
    def test_qa_creates_sop_task_with_snapshot_and_audit(self, qa: TestClient, admin: TestClient) -> None:
        task = _sop_task(qa)
        assert task["category"] == "sop" and task["category_label"] == "Procedures and SOPs"
        assert task["study"] is None
        assert [(d["sop_number"], d["kind"], d["version"]) for d in task["documents"]] == [
            ("SOP-011", "sop", "3.0"),
            ("SOP-011-A", "form", "3.0"),
        ]
        assert task["can_edit"] is True

        event = next(
            e for e in admin.get("/api/v1/audit-events").json()["items"] if e["action"] == "task.created"
        )
        assert "SOP-011, SOP-011-A" in event["summary"]
        assert event["details"]["documents"] == ["SOP-011 v3.0", "SOP-011-A v3.0"]

    def test_only_approved_documents(self, qa: TestClient) -> None:
        for ids in ([IN_REVIEW], ["no-such-item"], []):
            res = qa.post(
                "/api/v1/tasks",
                json={"category": "sop", "document_ids": ids, "title": "Review", "assignee_id": "demo-cra-1"},
            )
            assert res.status_code == 422, ids

    def test_qa_assigns_its_categories_only(self, qa: TestClient, admin: TestClient) -> None:
        listed = qa.get("/api/v1/tasks").json()
        assert listed["can_assign"] == ["sop", "vendor", "system", "general"]
        assert listed["can_create"] == ["study", "sop", "vendor", "system", "general"]  # study: own only
        assert listed["can_manage"] is False
        study_id = qa.get("/api/v1/studies").json()["studies"][0]["id"]
        res = qa.post(
            "/api/v1/tasks",
            json={"study_id": study_id, "title": "Chase ethics", "assignee_id": "demo-cra-1"},
        )
        assert res.status_code == 403

        study_task = admin.post(
            "/api/v1/tasks",
            json={"study_id": study_id, "title": "Chase ethics", "assignee_id": "demo-cra-1"},
        ).json()
        assert qa.patch(f"/api/v1/tasks/{study_task['id']}", json={"title": "Changed"}).status_code == 403
        assert (
            next(t for t in qa.get("/api/v1/tasks").json()["tasks"] if t["id"] == study_task["id"])[
                "can_edit"
            ]
            is False
        )

        # QA may edit and cancel SOP tasks it did not create.
        sop = _sop_task(admin)
        assert qa.patch(f"/api/v1/tasks/{sop['id']}", json={"assignee_id": "demo-cra-2"}).status_code == 200
        res = qa.post(f"/api/v1/tasks/{sop['id']}/status", json={"status": "Cancelled"})
        assert res.status_code == 200 and res.json()["status"] == "Cancelled"

    @pytest.mark.parametrize("role", [Role.PROJECT_MANAGER, Role.CRA, Role.CTA, Role.SAFETY, Role.VIEWER])
    def test_no_one_else_creates_sop_tasks_even_for_themselves(self, make_client, role: Role) -> None:  # type: ignore[no-untyped-def]
        client = make_client(role, user_id="demo-cra-1")
        assert "sop" not in client.get("/api/v1/tasks").json()["can_create"]
        res = client.post(
            "/api/v1/tasks",
            json={"category": "sop", "document_ids": [SOP], "title": "Review", "assignee_id": "demo-cra-1"},
        )
        assert res.status_code == 403

    def test_assignee_updates_status(self, qa: TestClient, make_client) -> None:  # type: ignore[no-untyped-def]
        task = _sop_task(qa)
        assignee = make_client(Role.CRA, user_id="demo-cra-1")
        url = f"/api/v1/tasks/{task['id']}/status"
        assert assignee.post(url, json={"status": "Completed"}).status_code == 200
        assert assignee.post(url, json={"status": "Cancelled"}).status_code == 403

    def test_filter_by_sop_and_category(self, qa: TestClient, admin: TestClient) -> None:
        sop_task = _sop_task(qa, ids=[FORM])
        admin.post(
            "/api/v1/tasks",
            json={
                "category": "vendor",
                "subject_name": "Acme Labs",
                "title": "Requalify",
                "assignee_id": "demo-pm-1",
            },
        )
        about_form = admin.get("/api/v1/tasks", params={"sop_id": FORM}).json()["tasks"]
        assert [t["id"] for t in about_form] == [sop_task["id"]]
        assert admin.get("/api/v1/tasks", params={"sop_id": SOP}).json()["tasks"] == []
        vendors = admin.get("/api/v1/tasks", params={"category": "vendor"}).json()["tasks"]
        assert [t["subject_name"] for t in vendors] == ["Acme Labs"]

    def test_edit_documents_keeps_original_snapshot(self, qa: TestClient, admin: TestClient) -> None:
        task = _sop_task(qa, ids=[SOP])
        res = qa.patch(f"/api/v1/tasks/{task['id']}", json={"document_ids": [SOP, "demo-sop-012"]})
        assert res.status_code == 200
        assert [d["sop_number"] for d in res.json()["documents"]] == ["SOP-011", "SOP-012"]
        assert qa.patch(f"/api/v1/tasks/{task['id']}", json={"document_ids": []}).status_code == 422
        assert qa.patch(f"/api/v1/tasks/{task['id']}", json={"document_ids": [IN_REVIEW]}).status_code == 422
        event = [
            e for e in admin.get("/api/v1/audit-events").json()["items"] if e["action"] == "task.updated"
        ][0]
        assert event["details"]["changes"]["documents"] == {"from": ["SOP-011"], "to": ["SOP-011", "SOP-012"]}


class TestOtherCategories:
    @pytest.mark.parametrize(("category", "label"), [("vendor", "Vendor"), ("system", "Computer system")])
    def test_named_categories_need_a_name(self, admin: TestClient, category: str, label: str) -> None:
        body = {"category": category, "title": "Annual review", "assignee_id": "demo-pm-1"}
        assert admin.post("/api/v1/tasks", json=body).status_code == 422
        res = admin.post("/api/v1/tasks", json={**body, "subject_name": "  Viedoc  "})
        assert res.status_code == 201
        assert res.json()["subject_name"] == "Viedoc" and res.json()["category_label"] == label
        renamed = admin.patch(f"/api/v1/tasks/{res.json()['id']}", json={"subject_name": "Viedoc EDC"})
        assert renamed.json()["subject_name"] == "Viedoc EDC"

    def test_general_task(self, admin: TestClient) -> None:
        res = admin.post(
            "/api/v1/tasks",
            json={"category": "general", "title": "Update training matrix", "assignee_id": "demo-pm-1"},
        )
        assert res.status_code == 201
        assert res.json()["study"] is None and res.json()["documents"] == []

    def test_links_must_match_category(self, admin: TestClient) -> None:
        study_id = admin.get("/api/v1/studies").json()["studies"][0]["id"]
        cases = [
            {"category": "general", "study_id": study_id},
            {"category": "vendor", "subject_name": "X", "document_ids": [SOP]},
            {"category": "general", "subject_name": "X"},
            {"category": "study"},  # no study
        ]
        for extra in cases:
            res = admin.post(
                "/api/v1/tasks", json={"title": "Something", "assignee_id": "demo-pm-1", **extra}
            )
            assert res.status_code == 422, extra

    def test_existing_study_tasks_default_and_portfolio_counts(self, admin: TestClient) -> None:
        studies = admin.get("/api/v1/studies").json()["studies"]
        res = admin.post(
            "/api/v1/tasks",
            json={"study_id": studies[0]["id"], "title": "Chase ethics", "assignee_id": "demo-pm-1"},
        )
        assert res.json()["category"] == "study" and res.json()["study"]["id"] == studies[0]["id"]
        admin.post(
            "/api/v1/tasks",
            json={"category": "general", "title": "Not a study task", "assignee_id": "demo-pm-1"},
        )
        counts = {s["id"]: s["open_tasks"] for s in admin.get("/api/v1/studies").json()["studies"]}
        assert sum(counts.values()) == 1
