"""Reports and Insights: the Work management report (tasks by category, study and person; risk heat map)."""

from __future__ import annotations

import io
from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.auth.rbac import Role
from app.studies.clock import today

API = "/api/v1/reports/work-management"


def _day(offset: int) -> str:
    return (today() + timedelta(days=offset)).isoformat()


def _studies(client: TestClient) -> list[dict[str, Any]]:
    return client.get("/api/v1/studies").json()["studies"]  # type: ignore[no-any-return]


def _task(client: TestClient, **body: Any) -> dict[str, Any]:
    res = client.post("/api/v1/tasks", json={"category": "general", "title": "A task", **body})
    assert res.status_code == 201, res.text
    return res.json()  # type: ignore[no-any-return]


def _setup(client: TestClient) -> dict[str, Any]:
    s1, s2 = _studies(client)[:2]
    late = _task(
        client,
        category="study",
        study_id=s1["id"],
        title="Chase ethics approval",
        assignee_ids=["demo-cra-1", "demo-cra-2"],
        due_date=_day(-5),
    )
    _task(client, category="study", study_id=s1["id"], assignee_ids=["demo-cra-1"], due_date=_day(3))
    _task(client, category="study", study_id=s2["id"], assignee_ids=["demo-dm-1"], due_date=_day(40))
    _task(
        client,
        category="vendor",
        subject_name="Acme Central Lab",
        title="Check kit stock",
        assignee_ids=["demo-cra-2"],
        due_date=_day(-1),
    )
    done = _task(client, assignee_ids=["demo-cra-1"], due_date=_day(10))
    client.post(f"/api/v1/tasks/{done['id']}/status", json={"status": "Completed"})
    cancelled = _task(client, assignee_ids=["demo-cra-1"], due_date=_day(-20))
    client.post(f"/api/v1/tasks/{cancelled['id']}/status", json={"status": "Cancelled"})

    # CRA One finishes their part of the overdue task; CRA Two is still working on it.
    client.post(f"/api/v1/tasks/{late['id']}/status", json={"status": "Completed", "person_id": "demo-cra-1"})
    for likelihood, impact, kind, study in [(3, 3, "risk", s1), (3, 2, "issue", s1), (1, 1, "risk", s2)]:
        res = client.post(
            "/api/v1/risks",
            json={
                "study_id": study["id"],
                "kind": kind,
                "title": f"Risk {likelihood}x{impact}",
                "likelihood": likelihood,
                "impact": impact,
                "owner_id": "demo-pm-1",
            },
        )
        assert res.status_code == 201, res.text
    return {"s1": s1, "s2": s2, "late": late}


def _tile(report: dict[str, Any], key: str) -> dict[str, Any]:
    return next(t for t in report["tiles"] if t["key"] == key)


class TestFigures:
    def test_headline_tiles(self, client: TestClient) -> None:
        _setup(client)
        r = client.get(API).json()
        assert _tile(r, "open")["value"] == "4"
        assert _tile(r, "overdue")["value"] == "2"
        assert _tile(r, "due_soon")["value"] == "1"
        completed = _tile(r, "completed")
        assert completed["value"] == "1" and completed["note"] == "1 of 1 on time"
        assert _tile(r, "high_risks")["value"] == "2"  # 3x3 = 9 and 3x2 = 6 are High
        assert r["completed"] == {"total": 1, "with_due_date": 1, "on_time": 1}
        assert r["source"]["mode"] == "mock"

    def test_by_category_and_study(self, client: TestClient) -> None:
        ids = _setup(client)
        r = client.get(API).json()
        cats = {c["key"]: c for c in r["by_category"]}
        assert [c["key"] for c in r["by_category"]] == ["study", "sop", "vendor", "system", "general"]
        assert cats["study"]["total"] == 3 and cats["study"]["overdue"] == 1
        assert cats["study"]["in_progress"] == 1 and cats["study"]["not_started"] == 2
        assert cats["vendor"] == {**cats["vendor"], "total": 1, "overdue": 1}
        assert cats["general"]["total"] == 0  # completed and cancelled tasks are not open
        studies = {s["label"]: s for s in r["by_study"]}
        assert studies[ids["s1"]["protocol_number"]]["total"] == 2
        assert studies[ids["s2"]["protocol_number"]]["total"] == 1
        # Most overdue first; studies without open tasks are still listed.
        assert r["by_study"][0]["label"] == ids["s1"]["protocol_number"]
        assert len(r["by_study"]) == len(_studies(client))

    def test_by_person_counts_unfinished_parts_only(self, client: TestClient) -> None:
        _setup(client)
        people = {p["name"]: p for p in client.get(API).json()["by_person"]}
        # CRA One finished their part of the overdue task, so only the task due in 3 days is open.
        assert people["Demo CRA One"] == {**people["Demo CRA One"], "open": 1, "overdue": 0, "due_soon": 1}
        assert people["Demo CRA Two"] == {**people["Demo CRA Two"], "open": 2, "overdue": 2}
        assert list(people)[0] == "Demo CRA Two"  # most overdue first

    def test_overdue_list_names_who_it_waits_on(self, client: TestClient) -> None:
        ids = _setup(client)
        overdue = client.get(API).json()["overdue"]
        assert [o["reference"] for o in overdue] == [ids["late"]["reference"], overdue[1]["reference"]]
        first = overdue[0]
        assert first["days_overdue"] == 5 and first["waiting_on"] == ["Demo CRA Two"]
        assert first["about"] == ids["s1"]["protocol_number"]
        assert overdue[1]["about"] == "Acme Central Lab" and overdue[1]["category_label"] == "Vendor"

    def test_heat_map(self, client: TestClient) -> None:
        _setup(client)
        r = client.get(API).json()
        cells = {(c["likelihood"], c["impact"]): c for c in r["heat_map"]}
        assert len(cells) == 9
        assert cells[(3, 3)] == {**cells[(3, 3)], "risks": 1, "issues": 0, "rating": "High", "score": 9}
        assert cells[(3, 2)]["issues"] == 1
        assert cells[(1, 1)] == {**cells[(1, 1)], "risks": 1, "rating": "Low"}
        assert [x["score"] for x in r["top_risks"]] == [9, 6, 1]

    def test_closed_risks_are_left_out(self, client: TestClient) -> None:
        _setup(client)
        risk = client.get(API).json()["top_risks"][0]
        client.post(f"/api/v1/risks/{risk['risk_id']}/status", json={"status": "Closed"})
        r = client.get(API).json()
        assert [x["score"] for x in r["top_risks"]] == [6, 1]
        assert _tile(r, "high_risks")["value"] == "1"


class TestFilters:
    def test_study_filter_covers_tasks_and_risks(self, client: TestClient) -> None:
        ids = _setup(client)
        r = client.get(API, params={"study_id": ids["s2"]["id"]}).json()
        assert _tile(r, "open")["value"] == "1"
        assert [s["label"] for s in r["by_study"]] == [ids["s2"]["protocol_number"]]
        assert [x["score"] for x in r["top_risks"]] == [1]

    def test_category_filter(self, client: TestClient) -> None:
        _setup(client)
        r = client.get(API, params={"category": "vendor"}).json()
        assert [c["key"] for c in r["by_category"]] == ["vendor"]
        assert r["by_study"] == []
        assert _tile(r, "open")["value"] == "1"
        assert len(r["top_risks"]) == 3  # risks are not tasks: the category filter leaves them alone

    def test_rejects_bad_filters_and_is_readable_by_all_roles(self, make_client: Any) -> None:
        viewer = make_client(Role.VIEWER)
        assert viewer.get(API).status_code == 200
        assert viewer.get(API, params={"study_id": "not-an-id"}).status_code == 422
        assert viewer.get(API, params={"category": "nonsense"}).status_code == 422


def test_completed_late_is_not_on_time(client: TestClient) -> None:
    task = _task(client, assignee_ids=["demo-cra-1"], due_date=_day(-3))
    client.post(f"/api/v1/tasks/{task['id']}/status", json={"status": "Completed"})
    r = client.get(API).json()
    assert r["completed"] == {"total": 1, "with_due_date": 1, "on_time": 0}


def test_excel_export_has_sheets_rules_and_is_audited(client: TestClient) -> None:
    _setup(client)
    res = client.get(f"{API}/export.xlsx", params={"category": "study"})
    assert res.status_code == 200
    assert res.headers["content-disposition"].startswith('attachment; filename="Work management ')
    book = load_workbook(io.BytesIO(res.content))
    assert book.sheetnames[:4] == ["Open tasks", "By person", "By category", "Open risks and issues"]
    open_rows = list(book["Open tasks"].iter_rows(values_only=True))
    assert len(open_rows) == 1 + 3  # header + 3 open study tasks
    assert any("Demo CRA Two (Not started)" in str(c) for row in open_rows for c in row)
    about = " ".join(str(c) for row in book[book.sheetnames[-1]].iter_rows(values_only=True) for c in row)
    assert "Study tasks" in about and "Overdue" in about
    events = client.get("/api/v1/audit-events").json()["items"]
    assert any(e["action"] == "report.exported" and e["entity_id"] == "work-management" for e in events)
