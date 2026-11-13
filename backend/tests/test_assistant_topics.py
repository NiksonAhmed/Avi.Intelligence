"""Ask Avi.Intelligence answers across the app: studies, tasks, risks and issues, deviations, eTMF, site
visits, conferences, Data Management, and SOPs (demo data; no AI)."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.auth.rbac import Role
from app.core.config import get_settings
from app.data_management import assistant_topic as dm_topic

ASK = "/api/v1/assistant/ask"


@pytest.fixture(autouse=True)
def dm_off(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Data Management off unless a test switches it on (never the developer's .env setting)."""
    off = get_settings().model_copy(update={"data_management_enabled": False})
    monkeypatch.setattr(dm_topic, "get_settings", lambda: off)


def ask(client: TestClient, question: str) -> dict[str, Any]:
    res = client.post(ASK, json={"question": question})
    assert res.status_code == 200, res.text
    return res.json()  # type: ignore[no-any-return]


def study(body: dict[str, Any]) -> dict[str, Any]:
    assert body["kind"] == "study", body
    return body["study"]  # type: ignore[no-any-return]


def test_my_overdue_tasks_any_category(make_client) -> None:  # type: ignore[no-untyped-def]
    admin = make_client(Role.ADMIN)
    for title, person in [("Renew insurance", "demo-cra-1"), ("Someone else's", "demo-cra-2")]:
        task = {"category": "general", "title": title, "assignee_ids": [person], "due_date": "2020-01-01"}
        assert admin.post("/api/v1/tasks", json=task).status_code == 201
    answer = study(ask(make_client(Role.CRA, user_id="demo-cra-1"), "What are my overdue tasks?"))
    assert answer["intent"] == "tasks" and answer["understood"].startswith("Your open tasks")
    assert answer["headline"] == "You have 1 open task, 1 overdue."
    assert answer["tables"][0]["rows"][0][1] == "General"


def test_risks_and_issues_come_from_simpletrials(client: TestClient) -> None:
    answer = study(ask(client, "Any open risks or issues?"))
    assert answer["intent"] == "risks" and answer["headline"] == "2 open risks and issues, 1 overdue."
    assert "SimpleTrials" in answer["lines"][0] and answer["tables"][0]["links"][0] == "/risks"


def test_protocol_deviations(client: TestClient) -> None:
    answer = study(ask(client, "Any open protocol deviations?"))
    assert answer["intent"] == "deviations" and answer["headline"].startswith("8 protocol deviations, 5 open")
    assert answer["tables"][0]["links"][0] == "/reports?tab=deviations"


def test_etmf_and_site_visits(client: TestClient) -> None:
    etmf = study(ask(client, "Which eTMF documents are expiring?"))
    assert etmf["intent"] == "etmf" and etmf["headline"].startswith("eTMF completeness")
    visits = study(ask(client, "Upcoming monitoring visits?"))
    assert visits["intent"] == "visits" and visits["headline"].startswith("3 upcoming site visits")
    assert visits["tables"][0]["rows"][0][1] == "Routine Monitoring Visit"


def test_visit_or_documents_alone_still_go_to_sop_search(client: TestClient) -> None:
    assert ask(client, "site initiation visit")["kind"] != "study"
    assert ask(client, "What does the SOP say about filing documents?")["kind"] != "study"


def test_conferences(make_client) -> None:  # type: ignore[no-untyped-def]
    viewer = make_client(Role.VIEWER)
    nxt = study(ask(viewer, "When is the next conference?"))
    assert (
        nxt["intent"] == "conferences"
        and "Next: Demo Clinical Operations Summit in Orlando" in nxt["headline"]
    )
    assert "demo conferences" in nxt["lines"][0] and nxt["sources"][0]["url"] == "/conferences"
    due = study(ask(viewer, "Which conference registrations are due?"))
    assert (
        due["understood"].startswith("Registration deadlines")
        and due["tables"][0]["title"] == "Registration deadlines"
    )
    exhibiting = study(ask(viewer, "Where are we exhibiting at conferences?"))
    assert all(row[3] == "Exhibiting" for row in exhibiting["tables"][0]["rows"])
    cost = study(ask(viewer, "What is the budget for conferences?"))
    assert "Cost" not in cost["tables"][0]["columns"] and any("allowed" in line for line in cost["lines"])
    admin_cost = study(ask(make_client(Role.ADMIN), "What is the budget for conferences?"))
    assert "Cost" in admin_cost["tables"][0]["columns"]


def test_data_management_when_switched_on(make_client, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    on = get_settings().model_copy(
        update={"data_management_enabled": True, "viedoc_connections": {}, "viedoc_allow_live": False}
    )
    monkeypatch.setattr(dm_topic, "get_settings", lambda: on)
    dm = make_client(Role.DATA_MANAGER)
    queries = study(ask(dm, "How many queries are open?"))
    assert queries["intent"] == "dm_queries" and "queries open at sites" in queries["headline"]
    assert queries["tables"][0]["links"][0] == "/data-management?tab=queries"
    assert study(ask(dm, "What is our SDV progress?"))["intent"] == "dm_sdv"
    labs = study(ask(dm, "Any clinically significant labs?"))
    assert labs["intent"] == "dm_labs" and "Flags only" in labs["lines"][0]
    assert study(ask(dm, "How much missing data is there?"))["intent"] == "dm_missing"
    # No subject IDs in answers (the demo study's subjects look like "DM-1-001").
    assert "DM-1-0" not in str(queries)
    # A procedure question about queries is still an SOP question.
    assert ask(dm, "What does the SOP say about raising queries?")["kind"] != "study"


def test_data_management_off_never_answers(client: TestClient) -> None:
    body = ask(client, "How many queries are open?")
    assert body["kind"] != "study" or not body["study"]["intent"].startswith("dm_")
