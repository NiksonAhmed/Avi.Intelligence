"""The Business Development role (user decisions 2026-11-16): conferences, SOPs, their own tasks and the
study portfolio at portfolio level only; no study detail, reports, risks, deviations, Data Management or
audit trail; conferences are read-only (edited in SharePoint); no costs."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.auth.rbac import ROLE_PERMISSIONS, Permission, Role
from app.core.config import get_settings
from app.data_management import overview_section as dm_overview

API = "/api/v1"


@pytest.fixture(autouse=True)
def dm_off(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    off = get_settings().model_copy(update={"data_management_enabled": False})
    monkeypatch.setattr(dm_overview, "get_settings", lambda: off)


@pytest.fixture
def bd(make_client) -> TestClient:  # type: ignore[no-untyped-def]
    return make_client(Role.BUSINESS_DEVELOPMENT, user_id="demo-bd-1")  # type: ignore[no-any-return]


def test_permissions() -> None:
    perms = ROLE_PERMISSIONS[Role.BUSINESS_DEVELOPMENT]
    assert {Permission.PORTFOLIO_READ, Permission.CONFERENCE_VIEW, Permission.TASK_VIEW} <= perms
    assert not perms & {
        Permission.STUDY_READ,
        Permission.DM_VIEW,
        Permission.AUDIT_READ,
        Permission.WORK_MANAGE,
    }
    # Everyone else keeps the portfolio and their tasks.
    assert all({Permission.PORTFOLIO_READ, Permission.TASK_VIEW} <= p for p in ROLE_PERMISSIONS.values())


def test_sees_the_portfolio_tasks_conferences_and_sops(bd: TestClient) -> None:
    studies = bd.get(f"{API}/studies")
    assert studies.status_code == 200 and studies.json()["studies"]
    assert bd.get(f"{API}/tasks", params={"assignee": "me"}).status_code == 200
    assert bd.get(f"{API}/conferences").status_code == 200
    assert bd.get(f"{API}/sops").status_code == 200


def test_no_study_detail_reports_risks_or_audit(bd: TestClient) -> None:
    study_id = bd.get(f"{API}/studies").json()["studies"][0]["id"]
    for path in (
        f"/studies/{study_id}",
        "/reports/study-delivery",
        "/reports/deviations",
        "/reports/risks-issues",
        "/risks",
        "/audit-events",
    ):
        assert bd.get(f"{API}{path}").status_code == 403, path


def test_overview_is_conferences_then_portfolio(bd: TestClient) -> None:
    body = bd.get(f"{API}/overview").json()
    assert body["view"] == "business_development" and body["view_label"] == "Business Development"
    assert [s["key"] for s in body["sections"]] == ["conferences", "portfolio"]
    portfolio = body["sections"][1]
    assert [k["label"] for k in portfolio["kpis"]] == ["Studies", "Sites", "Patients enrolled"]
    assert all(r["link"] == "/portfolio" for r in portfolio["rows"])
    labels = [k["label"] for k in body["attention"]["counts"]]
    assert labels[-1] == "Conference registrations due"


def test_assistant_answers_conferences_not_study_detail(bd: TestClient) -> None:
    conf = bd.post(f"{API}/assistant/ask", json={"question": "When is the next conference?"}).json()
    assert conf["kind"] == "study" and conf["study"]["intent"] == "conferences"
    dev = bd.post(f"{API}/assistant/ask", json={"question": "Any open protocol deviations?"}).json()
    assert dev["kind"] != "study"
