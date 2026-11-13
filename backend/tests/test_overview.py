"""Overview: the role-based home page and the CRA site assignments it relies on (demo data)."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.auth.rbac import Role
from app.core.config import get_settings
from app.data_management import overview_section

API = "/api/v1/overview"


@pytest.fixture(autouse=True)
def dm_off(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Data Management off unless a test switches it on (never the developer's .env setting)."""
    off = get_settings().model_copy(update={"data_management_enabled": False})
    monkeypatch.setattr(overview_section, "get_settings", lambda: off)


def _keys(body: dict[str, Any]) -> list[str]:
    return [s["key"] for s in body["sections"]]


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        (
            Role.ADMIN,
            ["connectors", "studies", "risks", "deviations", "etmf", "sops", "team_tasks", "conferences"],
        ),
        (
            Role.PROJECT_MANAGER,
            ["studies", "risks", "deviations", "etmf", "team_tasks", "sops", "conferences"],
        ),
        (Role.CRA, ["my_sites", "visits", "risks", "conferences"]),
        (Role.CTA, ["etmf", "studies", "sops", "conferences"]),
        (
            Role.DATA_MANAGER,
            ["deviations", "conferences"],
        ),  # its Data Management sections need the module switched on
        (Role.SAFETY, ["safety_db", "deviations", "sops", "conferences"]),
        (Role.QA, ["sops", "deviations", "team_tasks", "risks", "conferences"]),
        (Role.VIEWER, ["studies", "conferences"]),
    ],
)
def test_each_role_has_its_own_page(make_client, role: Role, expected: list[str]) -> None:  # type: ignore[no-untyped-def]
    body = make_client(role).get(API).json()
    assert body["view"] == role.value and _keys(body) == expected
    assert len(body["attention"]["counts"]) == 3
    assert [s["name"] for s in body["sources"]][:2] == ["SimpleTrials", "SharePoint"]
    allowed = ("my_sites", "safety_db", "conferences")  # conferences: "demo data until the list is connected"
    assert all(not s["notice"] or s["key"] in allowed for s in body["sections"])


def test_only_administrators_may_preview_other_roles(make_client) -> None:  # type: ignore[no-untyped-def]
    admin = make_client(Role.ADMIN)
    body = admin.get(API, params={"view": "cra"}).json()
    assert body["view"] == "cra" and len(body["views"]) == len(Role)
    cra = make_client(Role.CRA).get(API, params={"view": "admin"}).json()
    assert cra["view"] == "cra" and [v["id"] for v in cra["views"]] == ["cra"]


def test_figures_match_the_reports(client: TestClient) -> None:
    body = client.get(API).json()
    risks = next(s for s in body["sections"] if s["key"] == "risks")
    report = client.get("/api/v1/reports/risks-issues").json()
    tile = {t["key"]: t["value"] for t in report["tiles"]}
    assert [k["value"] for k in risks["kpis"]] == [tile["open"], tile["overdue"], tile["high"]]
    assert all(k["link"] == "/reports?tab=risks" for k in risks["kpis"])
    assert risks["rows"][0]["chip"].endswith("overdue")


def test_my_tasks_come_first(make_client) -> None:  # type: ignore[no-untyped-def]
    admin = make_client(Role.ADMIN)
    study = admin.get("/api/v1/studies").json()["studies"][0]
    task = {"category": "study", "study_id": study["id"], "assignee_ids": ["demo-cra-1"]}
    for title, due in [("Chase ethics renewal", "2020-01-01"), ("Someone else's task", "2020-01-01")]:
        people = ["demo-cra-1"] if title.startswith("Chase") else ["demo-cra-2"]
        res = admin.post(
            "/api/v1/tasks", json={**task, "title": title, "due_date": due, "assignee_ids": people}
        )
        assert res.status_code == 201, res.text
    body = make_client(Role.CRA, user_id="demo-cra-1").get(API).json()
    counts, items = body["attention"]["counts"], body["attention"]["items"]
    assert (counts[0]["label"], counts[0]["value"], counts[0]["link"]) == (
        "Your overdue tasks",
        "1",
        "/tasks",
    )
    assert (
        len(items) == 1 and "Chase ethics renewal" in items[0]["label"] and items[0]["chip"].endswith("late")
    )


class TestCraSites:
    def test_all_sites_until_assigned_then_only_theirs(self, make_client) -> None:  # type: ignore[no-untyped-def]
        cra = make_client(Role.CRA, user_id="demo-cra-1")
        before = next(s for s in cra.get(API).json()["sections"] if s["key"] == "my_sites")
        assert before["title"] == "Sites" and "No sites are assigned to you yet" in before["notice"]

        admin = make_client(Role.ADMIN)
        options = admin.get("/api/v1/site-assignments").json()
        first = next(
            s for s in options["sites"] if s["label"].startswith("DEMO-ONC-301 · ")
        )  # has demo visits
        assert {"demo-cra-1", "demo-cra-2"} <= {p["id"] for p in options["people"]}
        res = admin.put("/api/v1/site-assignments/demo-cra-1", json={"sites": [first["key"]]})
        assert res.status_code == 200 and res.json()["assignments"]["demo-cra-1"] == [first["key"]]

        body = cra.get(API).json()
        mine = next(s for s in body["sections"] if s["key"] == "my_sites")
        assert mine["title"] == "Your sites" and mine["notice"] is None and len(mine["rows"]) == 1
        assert mine["rows"][0]["chip"].startswith("Next visit")  # a demo monitoring visit in 4 days
        visits = next(s for s in body["sections"] if s["key"] == "visits")
        assert [r["label"] for r in visits["rows"]] == ["Routine Monitoring Visit"]
        assert body["attention"]["counts"][2]["label"] == "Site visits in the next 14 days"
        assert body["attention"]["counts"][2]["value"] == "1"

        events = admin.get("/api/v1/audit-events").json()["items"]
        assert any(e["action"] == "site_assignment.updated" for e in events)
        # Unassigning everything goes back to all sites.
        admin.put("/api/v1/site-assignments/demo-cra-1", json={"sites": []})
        again = next(s for s in cra.get(API).json()["sections"] if s["key"] == "my_sites")
        assert again["title"] == "Sites"

    def test_only_administrators_assign_and_only_real_sites(self, make_client) -> None:  # type: ignore[no-untyped-def]
        assert make_client(Role.PROJECT_MANAGER).get("/api/v1/site-assignments").status_code == 403
        admin = make_client(Role.ADMIN)
        admin.get("/api/v1/studies")
        assert admin.put("/api/v1/site-assignments/demo-cra-1", json={"sites": ["x:y"]}).status_code == 422
        assert admin.put("/api/v1/site-assignments/nobody", json={"sites": []}).status_code == 404


def test_data_management_sections_when_the_module_is_on(make_client, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    on = get_settings().model_copy(
        update={"data_management_enabled": True, "viedoc_connections": {}, "viedoc_allow_live": False}
    )
    monkeypatch.setattr(overview_section, "get_settings", lambda: on)
    dm = make_client(Role.DATA_MANAGER)
    dm.app.dependency_overrides[get_settings] = lambda: on
    body = dm.get(API).json()
    assert _keys(body) == ["dm_queries", "dm_missing", "dm_labs", "dm_sdv", "deviations", "conferences"]
    assert body["attention"]["counts"][2]["label"].startswith("Answered")
    assert "Viedoc" in [s["name"] for s in body["sources"]]
    viewer = make_client(Role.VIEWER).get(API).json()  # viewers see no Data Management on the Overview
    assert _keys(viewer) == ["studies", "conferences"]
