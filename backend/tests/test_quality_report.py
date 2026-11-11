"""Reports and Insights: the Quality (SOPs) report (review schedule, library health, change log)."""

from __future__ import annotations

import asyncio
import io
from datetime import UTC, date, datetime
from typing import Any

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.auth.rbac import Role
from app.connectors.sharepoint.mock import MockSopConnector
from app.connectors.sharepoint.models import (
    DocumentDetails,
    DocumentKind,
    EditableCopy,
    RevisionEntry,
    SopDocument,
    SopStatus,
)
from app.reports.quality import build_quality, review_state

API = "/api/v1/reports/quality"
TODAY = date(2026, 11, 9)


def _demo() -> list[SopDocument]:
    return asyncio.run(MockSopConnector("t").list_sops()).documents


def _doc(number: str, **changes: Any) -> SopDocument:
    base = next(d for d in _demo() if d.sop_number == "SOP-011")
    return base.model_copy(
        update={"id": f"x-{number}", "sop_number": number, "title": f"Doc {number}", **changes}
    )


def _at(day: str) -> datetime:
    return datetime.fromisoformat(day).replace(tzinfo=UTC)


def _tile(report: dict[str, Any], key: str) -> dict[str, Any]:
    return next(t for t in report["tiles"] if t["key"] == key)


def test_review_state() -> None:
    assert review_state(None, TODAY) == "no_date"
    assert review_state(date(2026, 11, 8), TODAY) == "overdue"
    assert review_state(TODAY, TODAY) == "due_soon"
    assert review_state(date(2026, 12, 9), TODAY) == "due_soon"
    assert review_state(date(2026, 12, 10), TODAY) == "scheduled"


class TestBuild:
    def test_schedule_and_months_count_approved_sops_only(self) -> None:
        docs = [
            _doc("A-1", review_date=_at("2026-10-01")),
            _doc("A-2", review_date=_at("2026-11-20")),
            _doc("A-3", review_date=_at("2027-02-03")),
            _doc("A-4", review_date=_at("2028-06-01")),
            _doc("A-5", status=SopStatus.IN_REVIEW, review_date=_at("2026-01-01")),
        ]
        q = build_quality(docs, {"x-A-2": 2}, TODAY)
        assert [r.sop_number for r in q.schedule] == ["A-1", "A-2", "A-3", "A-4"]
        assert [r.state for r in q.schedule] == ["overdue", "due_soon", "scheduled", "scheduled"]
        assert q.schedule[1].open_tasks == 2 and q.schedule[1].days_to_review == 11
        months = {b.key: b.count for b in q.by_month}
        assert months["overdue"] == 1 and months["2026-11"] == 1 and months["2027-02"] == 1
        assert len(q.by_month) == 13 and q.later == 1  # June 2028 is beyond the next 12 months
        tiles = {t.key: t.value for t in q.tiles}
        assert tiles["approved"] == "4" and tiles["review_overdue"] == "1" and tiles["review_due_soon"] == "1"

    def test_library_health(self) -> None:
        form = _doc(
            "B-1-A",
            kind=DocumentKind.FORM,
            parent_sop_number="B-9",
            mime_type="application/pdf",
            editable_copy=None,
        )
        docs = [
            _doc("B-1", review_date=None, owner=None),
            _doc("B-2", effective_date=None, file_name_version="1.0", version="2.0"),
            _doc("B-3", status=SopStatus.DRAFT, effective_date=None),  # drafts have no dates yet
            form,
        ]
        q = build_quality(docs, {}, TODAY)
        found = {c.key: [i.label.split(" · ")[0] for i in c.items] for c in q.health}
        assert found["no_review_date"] == ["B-1"]
        assert found["no_owner"] == ["B-1"]
        assert found["no_effective_date"] == ["B-2"]
        assert found["version_mismatch"] == ["B-2"]
        assert found["no_word_copy"] == ["B-1-A"]
        assert found["orphan_form"] == ["B-1-A"]
        assert {t.key: t.value for t in q.tiles}["health"] == "3"

    def test_change_log_uses_history_then_effective_date(self) -> None:
        history = DocumentDetails(
            revisions=[
                RevisionEntry(issued=date(2026, 9, 1), version="4.0", changes="Added remote monitoring"),
                RevisionEntry(issued=date(2025, 1, 1), version="3.0", changes="Old change"),
            ]
        )
        docs = [
            _doc("C-1", details=history),
            _doc("C-2", effective_date=_at("2026-07-01"), version="2.0"),
            _doc("C-3", effective_date=_at("2024-01-01")),
        ]
        q = build_quality(docs, {}, TODAY, months=6)
        assert [(c.sop_number, c.version, c.basis) for c in q.changes] == [
            ("C-1", "4.0", "history"),
            ("C-2", "2.0", "effective"),
        ]
        assert q.changes[0].changes == "Added remote monitoring"
        assert len(build_quality(docs, {}, TODAY, months=24).changes) == 3
        assert build_quality(docs, {}, TODAY, months=5).months == 12  # unsupported period: default

    def test_department_filter(self) -> None:
        q = build_quality(_demo(), {}, TODAY, department="pharmacovigilance")
        assert q.schedule and {r.department for r in q.schedule} == {"Pharmacovigilance"}
        assert "Quality Assurance" in [o.id for o in q.department_options]


class TestApi:
    def test_demo_library(self, client: TestClient) -> None:
        r = client.get(API).json()
        assert _tile(r, "approved")["value"] == "11"
        assert r["source"]["mode"] == "mock" and r["months"] == 12
        # In Review and Draft SOPs are not flagged for missing dates.
        assert next(c for c in r["health"] if c["key"] == "no_effective_date")["count"] == 0
        sop011 = next(s for s in r["schedule"] if s["sop_number"] == "SOP-011")
        assert sop011["forms"] == 2

    def test_counts_open_sop_tasks(self, client: TestClient) -> None:
        res = client.post(
            "/api/v1/tasks",
            json={
                "category": "sop",
                "document_ids": ["demo-sop-011"],
                "title": "Annual review",
                "assignee_ids": ["demo-cra-1"],
            },
        )
        assert res.status_code == 201, res.text
        row = next(s for s in client.get(API).json()["schedule"] if s["id"] == "demo-sop-011")
        assert row["open_tasks"] == 1
        client.post(f"/api/v1/tasks/{res.json()['id']}/status", json={"status": "Cancelled"})
        row = next(s for s in client.get(API).json()["schedule"] if s["id"] == "demo-sop-011")
        assert row["open_tasks"] == 0

    def test_filters_and_access(self, make_client: Any) -> None:
        viewer = make_client(Role.VIEWER)
        r = viewer.get(API, params={"department": "Data Management", "months": 24}).json()
        assert {s["department"] for s in r["schedule"]} == {"Data Management"}
        assert viewer.get(API, params={"months": 0}).status_code == 422
        assert viewer.get(API, params={"department": "x" * 201}).status_code == 422

    def test_excel_export_is_audited(self, client: TestClient) -> None:
        res = client.get(f"{API}/export.xlsx", params={"months": 24})
        assert res.status_code == 200
        assert res.headers["content-disposition"].startswith('attachment; filename="Quality SOPs ')
        book = load_workbook(io.BytesIO(res.content))
        assert book.sheetnames[:3] == ["Review schedule", "Change log", "Library health"]
        rows = list(book["Review schedule"].iter_rows(values_only=True))
        assert rows[0][0] == "SOP" and len(rows) == 1 + 11
        assert any(r[8] == "Overdue" for r in rows[1:])
        events = client.get("/api/v1/audit-events").json()["items"]
        assert any(e["action"] == "report.exported" and e["entity_id"] == "quality" for e in events)


def test_form_with_word_copy_is_healthy() -> None:
    form = _doc(
        "D-1-A",
        kind=DocumentKind.FORM,
        parent_sop_number="D-1",
        mime_type="application/pdf",
        editable_copy=EditableCopy(id="w", file_name="D-1-A.docx", size_bytes=1, mime_type="x"),
    )
    q = build_quality([_doc("D-1"), form], {}, TODAY)
    assert all(c.count == 0 for c in q.health)
