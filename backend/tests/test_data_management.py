"""Data Management (Viedoc) Step 1: export reading, rules, sync, API, permissions and the module boundary."""

from __future__ import annotations

import asyncio
import csv
import io
import re
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.rbac import Role
from app.connectors.viedoc.client import ViedocClient
from app.core.config import Settings, ViedocConnectionSettings, get_settings
from app.data_management import rules
from app.data_management.demo import demo_export
from app.data_management.export_reader import QUERY_COLUMNS, read_export
from app.data_management.models import DmMissingItem, DmPendingForm, DmQuery
from app.data_management.sync import sync_connection

API = "/api/v1/data-management"
TODAY = date(2026, 11, 11)  # a Wednesday


def _settings(**changes: Any) -> Settings:
    # Never the developer's real Viedoc connections from .env: tests use the demo study or a fake Viedoc.
    base = {"data_management_enabled": True, "viedoc_connections": {}, "viedoc_allow_live": False}
    return get_settings().model_copy(update={**base, **changes})


@pytest.fixture
def dm(make_client):  # type: ignore[no-untyped-def]
    def _make(role: Role = Role.ADMIN, **settings: Any) -> TestClient:
        client = make_client(role)
        client.app.dependency_overrides[get_settings] = lambda: _settings(**settings)
        return client  # type: ignore[no-any-return]

    return _make


# ---- export reader ----------------------------------------------------------------------------


def test_demo_export_is_read_like_a_real_one() -> None:
    data = read_export(demo_export(TODAY))
    assert data.study_code == "DEMO_DM"
    assert len(data.queries) == 14 and len(data.missing) == 9 and len(data.pending) == 5
    by_number = {q.number: q for q in data.queries}
    assert by_number["1"].state == "open_at_site" and by_number["3"].state == "awaiting_approval"
    assert by_number["4"].state == "closed" and by_number["4"].closed_at is not None
    sent_back = by_number["8"]  # raised -> answered -> sent back -> answered again
    assert (
        sent_back.reopen_count == 1
        and sent_back.answered_count == 2
        and sent_back.state == "awaiting_approval"
    )
    assert [e.viedoc_state for e in sent_back.events][:2] == ["Query Raised", "Query Resolved"]
    # Viedoc's second header row (column IDs) is not read as data.
    assert all(q.subject_id != "SubjectId" for q in data.queries) and all(
        p.subject_id != "SubjectId" for p in data.pending
    )


def test_only_needed_columns_are_kept() -> None:
    """Demographics and form values in the same export are never read."""
    columns = list(QUERY_COLUMNS.values())
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=[*columns, "Year of birth"])
    writer.writeheader()
    c = QUERY_COLUMNS
    writer.writerow(
        {
            c["number"]: "1",
            c["site_code"]: "101",
            c["subject_id"]: "101-001",
            c["query_type"]: "Validation",
            c["state"]: "Query Raised",
            c["at"]: "2026-11-01 10:00",
            "Year of birth": "1961",
        }
    )
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("ST_20261111_010101_Queries.csv", buf.getvalue())
        z.writestr("ST_20261111_010101_DM.csv", "Subject Id,Year of birth,Race 1\n101-001,1961,Asian\n")
    data = read_export(archive.getvalue())
    record = data.queries[0]
    assert "1961" not in repr(record) and "Asian" not in repr(data)
    assert record.raised_at == datetime(2026, 11, 1, 10, 0, tzinfo=UTC)


def test_export_without_queries_is_refused() -> None:
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("X_20261111_010101_DM.csv", "a,b\n1,2\n")
    with pytest.raises(Exception, match="no Queries file"):
        read_export(archive.getvalue())


# ---- rules ------------------------------------------------------------------------------------


def test_clocks_flags_and_buckets() -> None:
    raised = datetime(2026, 11, 4, 9, 0, tzinfo=UTC)  # the previous Wednesday
    assert rules.clock_days("open_at_site", raised, TODAY) == 5
    assert rules.flag("open_at_site", 5, 5, 3) == "amber" and rules.flag("open_at_site", 6, 5, 3) == "red"
    assert (
        rules.flag("awaiting_approval", 3, 5, 3) == "amber"
        and rules.flag("awaiting_approval", 1, 5, 3) == "green"
    )
    assert rules.flag("closed", 99, 5, 3) == "none" and rules.clock_days("closed", raised, TODAY) is None
    assert [rules.bucket(d) for d in (0, 7, 8, 30, 31)] == ["0-7", "0-7", "8-14", "15-30", "30+"]


# ---- sync ---------------------------------------------------------------------------------------


def test_demo_sync_replaces_rows(db_session: Session) -> None:
    settings = _settings()
    for _ in range(2):  # a second sync replaces, never duplicates
        run = asyncio.run(
            sync_connection(db_session, settings, tenant_id="avion", name="demo", triggered_by="t")
        )
    assert run.ok and run.counts["queries"] == 14 and run.environment == "demo"
    assert len(db_session.scalars(select(DmQuery)).all()) == 14
    assert len(db_session.scalars(select(DmMissingItem)).all()) == 9
    assert len(db_session.scalars(select(DmPendingForm)).all()) == 5


def test_viedoc_sync_uses_the_export_and_keeps_the_copy_on_failure(db_session: Session) -> None:
    conn = ViedocConnectionSettings(
        api_url="https://v4apitraining.viedoc.net/", client_id="c", client_secret="s"
    )  # type: ignore[arg-type]
    settings = _settings(viedoc_connections={"sandbox": conn}, viedoc_mode="auto")  # a fake Viedoc
    calls: list[str] = []
    fail = {"now": False}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}")
        if request.url.path.endswith("openid-configuration"):
            return httpx.Response(
                200, json={"token_endpoint": "https://v4ststraining.viedoc.net/connect/token"}
            )
        if request.url.path == "/connect/token":
            return httpx.Response(200, json={"access_token": "t", "expires_in": 60})
        if request.url.path.endswith("/start"):
            return httpx.Response(500 if fail["now"] else 200, json={"exportId": "e1"})
        if request.url.path.endswith("/status"):
            return httpx.Response(200, json={"exportStatus": "Ready"})
        if request.url.path.endswith("/download"):
            return httpx.Response(200, content=demo_export(TODAY))
        return httpx.Response(200)

    def factory(c: ViedocConnectionSettings, allow_live: bool) -> ViedocClient:
        return ViedocClient(c, allow_live=allow_live, transport=httpx.MockTransport(handler))

    run = asyncio.run(
        sync_connection(
            db_session, settings, tenant_id="avion", name="SANDBOX", triggered_by="t", client_factory=factory
        )
    )
    assert run.ok and run.environment == "sandbox"
    assert "DELETE /clinic/dataexport/delete" in calls  # the export file never stays on Viedoc's server
    assert {q.environment for q in db_session.scalars(select(DmQuery))} == {"sandbox"}
    fail["now"] = True
    run = asyncio.run(
        sync_connection(
            db_session, settings, tenant_id="avion", name="sandbox", triggered_by="t", client_factory=factory
        )
    )
    assert not run.ok and run.error
    assert len(db_session.scalars(select(DmQuery)).all()) == 14  # previous copy kept


# ---- API ----------------------------------------------------------------------------------------


def test_hidden_unless_enabled(make_client) -> None:  # type: ignore[no-untyped-def]
    client = make_client(Role.ADMIN)
    client.app.dependency_overrides[get_settings] = lambda: get_settings().model_copy(
        update={"data_management_enabled": False}
    )
    assert client.get(f"{API}/status").status_code == 404


@pytest.mark.parametrize(
    ("role", "view", "sync"),
    [
        (Role.ADMIN, 200, 200),
        (Role.DATA_MANAGER, 200, 200),
        (Role.PROJECT_MANAGER, 200, 403),
        (Role.CRA, 200, 403),
        (Role.QA, 200, 403),
        (Role.CTA, 403, 403),
        (Role.SAFETY, 403, 403),
        (Role.VIEWER, 403, 403),
    ],
)
def test_access_by_role(dm, role: Role, view: int, sync: int) -> None:  # type: ignore[no-untyped-def]
    client = dm(role)
    assert client.get(f"{API}/overview").status_code == view
    assert client.post(f"{API}/sync", json={"connection": "demo"}).status_code == sync


def test_overview_tiles_sites_and_ageing(dm) -> None:  # type: ignore[no-untyped-def]
    body = dm().get(f"{API}/overview").json()
    assert body["connection"] == "demo" and body["environment"] == "demo" and body["study_code"] == "DEMO_DM"
    tiles = {t["key"]: t["value"] for t in body["tiles"]}
    assert tiles["open_at_site"] == 6 and tiles["awaiting_approval"] == 5
    assert tiles["missing_items"] == 9 and tiles["pending_forms"] == 5
    sites = {s["site_code"]: s for s in body["sites"]}
    assert sites["102"]["open_at_site"] == 3 and sites["102"]["oldest_days"] == 40
    assert body["sites"][0]["over_target"] >= body["sites"][-1]["over_target"]  # most overdue first
    assert sum(b["open_at_site"] + b["awaiting_approval"] for b in body["ageing"]) == 11


def test_query_list_filters_and_detail(dm) -> None:  # type: ignore[no-untyped-def]
    client = dm()
    everything = client.get(f"{API}/queries").json()
    assert everything["total"] == 14 and everything["counts"] == {
        "open_at_site": 6,
        "awaiting_approval": 5,
        "closed": 3,
    }
    assert everything["queries"][0]["flag"] == "red"  # worst first
    assert client.get(f"{API}/queries", params={"state": "not_closed"}).json()["total"] == 11
    assert client.get(f"{API}/queries", params={"site": "102"}).json()["total"] == 6
    assert client.get(f"{API}/queries", params={"reopened": "true"}).json()["total"] == 1
    assert client.get(f"{API}/queries", params={"search": "101-002"}).json()["total"] == 1
    reds = client.get(f"{API}/queries", params={"flag": "red"}).json()["queries"]
    assert reds and all(q["flag"] == "red" for q in reds)
    one = next(q for q in everything["queries"] if q["reopen_count"] == 1)
    detail = client.get(f"{API}/queries/{one['id']}").json()
    assert [e["viedoc_state"] for e in detail["events"]] == [
        "Query Raised",
        "Query Resolved",
        "Query Raised",
        "Query Resolved",
    ]
    assert detail["state_label"] == "Answered, awaiting approval"
    assert client.get(f"{API}/queries/nope").status_code == 404


def test_sync_is_audited(dm) -> None:  # type: ignore[no-untyped-def]
    client = dm(Role.DATA_MANAGER)
    run = client.post(f"{API}/sync", json={"connection": "demo"}).json()
    assert run["ok"] and run["counts"]["queries"] == 14
    status = client.get(f"{API}/status").json()
    assert (
        status["demo"] is True and status["can_sync"] is True and status["connections"][0]["last_run"]["ok"]
    )
    events = dm().get("/api/v1/audit-events").json()["items"]
    assert any(e["action"] == "dm.synced" for e in events)
    assert client.post(f"{API}/sync", json={"connection": "nope"}).status_code == 404


# ---- module boundary ------------------------------------------------------------------------------


def test_nothing_outside_the_module_imports_it() -> None:
    """Only the app's wiring (main.py) may import Data Management, so it could be split out later."""
    src = Path(__file__).resolve().parents[1] / "src" / "app"
    offenders = [
        str(p.relative_to(src))
        for p in src.rglob("*.py")
        if "data_management" not in p.parts
        and p.name != "main.py"
        and re.search(r"(from|import)\s+app\.data_management", p.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_mock_mode_ignores_real_connections() -> None:
    conn = ViedocConnectionSettings(
        api_url="https://v4apitraining.viedoc.net/", client_id="c", client_secret="s"
    )  # type: ignore[arg-type]
    from app.data_management.sync import connections

    assert connections(_settings(viedoc_connections={"sandbox": conn}, viedoc_mode="mock")) == {
        "demo": "demo"
    }
    assert connections(_settings(viedoc_connections={"sandbox": conn}, viedoc_mode="auto")) == {
        "sandbox": "sandbox"
    }
