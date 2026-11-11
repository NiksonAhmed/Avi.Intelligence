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
        (Role.PROJECT_MANAGER, 200, 200),  # everyone may view and sync (user decision)
        (Role.CRA, 200, 200),
        (Role.QA, 200, 200),
        (Role.CTA, 200, 200),
        (Role.SAFETY, 200, 200),
        (Role.VIEWER, 200, 200),
    ],
)
def test_access_by_role(dm, role: Role, view: int, sync: int) -> None:  # type: ignore[no-untyped-def]
    client = dm(role)
    assert client.get(f"{API}/overview").status_code == view
    assert client.post(f"{API}/sync", json={"connection": "demo"}).status_code == sync


def test_overview_tiles_sites_and_ageing(dm) -> None:  # type: ignore[no-untyped-def]
    body = dm().get(f"{API}/overview").json()
    assert (
        body["scope"] == "demo"
        and body["multi"] is False
        and body["environment"] == "demo"
        and body["study_code"] == "DEMO_DM"
    )
    tiles = {t["key"]: t["value"] for t in body["tiles"]}
    assert tiles["open_at_site"] == 6 and tiles["awaiting_approval"] == 5
    assert tiles["missing_items"] == 9 and tiles["pending_forms"] == 5
    sites = {s["site_code"]: s for s in body["sites"]}
    assert sites["102"]["open_at_site"] == 3 and sites["102"]["oldest_days"] == 40
    assert body["sites"][0]["overdue"] >= body["sites"][-1]["overdue"]  # most overdue first
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
    views = everything["views"]
    assert (views["attention"], views["open"], views["awaiting"], views["sent_back"], views["closed"]) == (
        11,
        6,
        5,
        1,
        3,
    )
    assert everything["views"]["overdue"] == len(
        client.get(f"{API}/queries", params={"state": "not_closed", "flag": "red"}).json()["queries"]
    )
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


# ---- several studies ------------------------------------------------------------------------------


def _many_studies(db_session: Session) -> Settings:
    """Two sandbox studies and one live study (live allowed here, against a fake Viedoc only)."""

    def conn(env: str) -> ViedocConnectionSettings:
        return ViedocConnectionSettings(
            api_url="https://v4apitraining.viedoc.net/",
            client_id="c",
            client_secret="s",
            environment=env,  # type: ignore[arg-type]
        )

    settings = _settings(
        viedoc_mode="auto",
        viedoc_allow_live=True,
        viedoc_connections={"onc": conn("sandbox"), "cv": conn("sandbox"), "neu": conn("live")},
    )

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("openid-configuration"):
            return httpx.Response(
                200, json={"token_endpoint": "https://v4ststraining.viedoc.net/connect/token"}
            )
        if path == "/connect/token":
            return httpx.Response(200, json={"access_token": "t", "expires_in": 60})
        if path.endswith("/start"):
            return httpx.Response(200, json={"exportId": "e1"})
        if path.endswith("/status"):
            return httpx.Response(200, json={"exportStatus": "Ready"})
        if path.endswith("/download"):
            return httpx.Response(200, content=demo_export(TODAY))
        return httpx.Response(200)

    def factory(c: ViedocConnectionSettings, allow_live: bool) -> ViedocClient:
        return ViedocClient(c, allow_live=allow_live, transport=httpx.MockTransport(handler))

    for name in ("onc", "cv", "neu"):
        run = asyncio.run(
            sync_connection(
                db_session, settings, tenant_id="avion", name=name, triggered_by="t", client_factory=factory
            )
        )
        assert run.ok
    return settings


def test_scopes_combine_studies_but_never_sandbox_with_live(make_client, db_session: Session) -> None:  # type: ignore[no-untyped-def]
    settings = _many_studies(db_session)
    client = make_client(Role.ADMIN)
    client.app.dependency_overrides[get_settings] = lambda: settings
    status = client.get(f"{API}/status").json()
    scopes = [(s["id"], s["label"], s["multi"]) for s in status["scopes"]]
    # Only one live study, so no "All live studies"; two sandbox studies can be combined.
    assert scopes[0] == ("all-sandbox", "All sandbox studies", True)
    assert ("neu", "DEMO_DM · Live", False) in scopes and ("onc", "DEMO_DM · Sandbox", False) in scopes
    assert status["default_scope"] == "all-sandbox"

    combined = client.get(f"{API}/overview", params={"scope": "all-sandbox"}).json()
    assert combined["multi"] is True and combined["study_code"] is None
    assert {s["connection"] for s in combined["studies"]} == {"onc", "cv"}
    assert {t["key"]: t["value"] for t in combined["tiles"]}["open_at_site"] == 12  # 6 + 6, live left out
    # The same site code in two studies stays two rows.
    assert sorted(
        (s["connection"], s["site_code"]) for s in combined["sites"] if s["site_code"] == "102"
    ) == [
        ("cv", "102"),
        ("onc", "102"),
    ]
    assert any(o["id"] == "onc:102" for o in combined["site_options"])

    everything = client.get(f"{API}/queries", params={"scope": "all-sandbox"}).json()
    assert everything["total"] == 28 and {q["connection"] for q in everything["queries"]} == {"onc", "cv"}
    one_study = client.get(f"{API}/queries", params={"scope": "all-sandbox", "study": "cv"}).json()
    assert one_study["total"] == 14
    one_site = client.get(f"{API}/queries", params={"scope": "all-sandbox", "site": "onc:102"}).json()
    assert one_site["total"] == 6 and {q["connection"] for q in one_site["queries"]} == {"onc"}

    live = client.get(f"{API}/overview", params={"scope": "neu"}).json()
    assert live["environment"] == "live" and live["multi"] is False
    assert client.get(f"{API}/overview", params={"scope": "all-live"}).status_code == 200  # one live study
    assert client.get(f"{API}/overview", params={"scope": "all-other"}).status_code == 404


def test_queries_on_the_visit_date_are_labelled(dm, db_session: Session) -> None:  # type: ignore[no-untyped-def]
    """Viedoc raises some queries on the visit (event) date itself: they have a visit but no form."""
    assert rules.form_label(None, None, "Event date") == "Visit date (no form)"
    assert rules.form_label("EG", "ECG", "Item") == "ECG"
    client = dm()
    client.get(f"{API}/overview")  # demo study synced on first use
    db_session.add(
        DmQuery(
            tenant_id="avion", connection="demo", environment="demo", study_code="DEMO_DM", query_number="99",
            site_code="101", site_name="Demo Hospital North", subject_id="101-009", event_id="E03_D1",
            event_name="Day 1", form_id=None, query_type="Validation", raised_on="Event date",
            state="open_at_site", viedoc_state="Query Raised", raised_at=datetime(2026, 11, 1, tzinfo=UTC),
            state_since=datetime(2026, 11, 1, tzinfo=UTC),
        )
    )  # fmt: skip
    db_session.commit()
    body = client.get(f"{API}/overview").json()
    assert {"form": "Visit date (no form)", "open": 1} in body["forms"]
    assert {"id": "visit-date", "label": "Visit date (no form)"} in body["form_options"]
    only = client.get(f"{API}/queries", params={"form": "visit-date"}).json()
    assert only["total"] == 1 and only["queries"][0]["form_label"] == "Visit date (no form)"


def test_query_date_range(dm) -> None:  # type: ignore[no-untyped-def]
    from datetime import timedelta as td

    from app.studies.clock import today as app_today

    client = dm()
    t = app_today()
    # Demo queries were first raised 2, 3, 5, 6, 7, 9, 11, 12, 14, 18, 20, 25, 35 and 40 days ago.
    recent = client.get(f"{API}/queries", params={"raised_from": str(t - td(days=10))}).json()
    assert recent["total"] == 6
    window = client.get(
        f"{API}/queries", params={"raised_from": str(t - td(days=20)), "raised_to": str(t - td(days=11))}
    ).json()
    assert window["total"] == 5  # 11, 12, 14, 18 and 20 days ago
    assert all(q["raised_at"] for q in window["queries"])
    bad = client.get(f"{API}/queries", params={"raised_from": str(t), "raised_to": str(t - td(days=1))})
    assert bad.status_code == 422
    assert client.get(f"{API}/queries", params={"raised_from": "not-a-date"}).status_code == 422


# ---- SDV ----------------------------------------------------------------------------------------


def test_sdv_read_from_the_export() -> None:
    data = read_export(demo_export(TODAY))
    forms = [f for f in data.forms if f.kind == "form"]
    assert len(data.forms) == 72 and len(forms) == 54  # 18 subject-visits x (3 forms + the visit date)
    assert sum(f.sdv_required for f in data.forms) == 360 and sum(f.sdv_done for f in data.forms) == 127
    done = next(
        f for f in forms if f.subject_id == "101-001" and f.event_id == "E01_SCR" and f.form_id == "VS"
    )
    assert (done.sdv_required, done.sdv_done, done.last_sdv_by) == (6, 6, None)  # names are never kept
    assert done.data_review_at and done.signed_at and done.locked_at


def test_sdv_tab(dm) -> None:  # type: ignore[no-untyped-def]
    client = dm()
    body = client.get(f"{API}/sdv", params={"view": "all"}).json()
    assert body["summary"] == {
        "required": 360,
        "done": 127,
        "percent": 35.3,
        "forms_total": 54,
        "forms_complete": 15,
    }
    tiles = {t["key"]: t["value"] for t in body["tiles"]}
    assert tiles["fields"] == 35 and tiles["forms_complete"] == 15 and tiles["waiting"] == 52
    assert (tiles["data_review"], tiles["signed"], tiles["locked"]) == (28, 17, 6)  # 15, 9 and 3 of 54 forms
    assert [(s["site_code"], s["percent"]) for s in body["sites"]] == [
        ("201", 0.0),
        ("102", 25.0),
        ("101", 72.5),
    ]
    assert [(v["event_id"], v["percent"]) for v in body["visits"]] == [("E01_SCR", 55.6), ("E03_D1", 15.0)]
    assert body["views"] == {"waiting": 52, "complete": 20, "all": 72}

    waiting = client.get(f"{API}/sdv").json()  # default view: waiting for SDV, oldest visit first
    assert waiting["total"] == 52 and all(f["status"] == "waiting" for f in waiting["forms"])
    assert waiting["forms"][0]["days_since_visit"] >= waiting["forms"][-1]["days_since_visit"]
    complete = client.get(f"{API}/sdv", params={"view": "complete"}).json()
    assert complete["total"] == 20 and all(f["done"] == f["required"] for f in complete["forms"])

    assert client.get(f"{API}/sdv", params={"site": "201"}).json()["total"] == 16  # 2 subjects x 2 visits x 4
    dates = client.get(f"{API}/sdv", params={"form": "visit-date", "view": "all"}).json()
    assert dates["total"] == 18 and {f["form_label"] for f in dates["forms"]} == {"Visit date (no form)"}
    assert client.get(f"{API}/sdv", params={"visit": "E03_D1", "view": "all"}).json()["total"] == 36
    assert client.get(f"{API}/sdv", params={"search": "101-001", "view": "all"}).json()["total"] == 8
    assert (
        client.get(f"{API}/sdv", params={"visit_from": "2026-12-01", "visit_to": "2026-11-01"}).status_code
        == 422
    )


def test_overview_reports_sdv_completed_vs_required(dm) -> None:  # type: ignore[no-untyped-def]
    body = dm().get(f"{API}/overview").json()
    assert body["sdv"]["required"] == 360 and body["sdv"]["done"] == 127
    tile = next(t for t in body["tiles"] if t["key"] == "sdv")
    assert tile["value"] == 35 and tile["note"] == "127 of 360 fields verified"
    sites = {s["site_code"]: (s["sdv_done"], s["sdv_required"]) for s in body["sites"]}
    assert sites == {"101": (87, 120), "102": (40, 160), "201": (0, 80)}


@pytest.mark.parametrize(("role", "code"), [(Role.CRA, 200), (Role.CTA, 200), (Role.VIEWER, 200)])
def test_sdv_access(dm, role: Role, code: int) -> None:  # type: ignore[no-untyped-def]
    assert dm(role).get(f"{API}/sdv").status_code == code


def test_visit_dates_match_across_sdv_and_review_files() -> None:
    """Visit-date rows: the review file uses a "$EVENT" form code where SDV.csv has none, and every visit
    has the same event sequence number; each visit date must still be one row with its SDV field."""
    from app.data_management.export_reader import REVIEW_COLUMNS, SDV_COLUMNS

    def table(columns: list[str], rows: list[dict[str, str]]) -> str:
        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
        return out.getvalue()

    sc, rc = SDV_COLUMNS, REVIEW_COLUMNS
    visits = [("E01", "2026-01-10", "1"), ("E02", "2026-02-10", "1")]  # same sequence number, as in Viedoc
    sdv = [{sc["site_code"]: "01", sc["subject_id"]: "01-001", sc["event_id"]: e, sc["event_date"]: d,
            sc["event_seq"]: "", sc["reviewed_item"]: "Event date"} for e, d, _ in visits]  # fmt: skip
    review = [{rc["site_code"]: "01", rc["subject_id"]: "01-001", rc["event_id"]: e, rc["event_date"]: d,
               rc["event_seq"]: seq, rc["form_id"]: "$EVENT", rc["reviewed_item"]: "Event date"}
              for e, d, seq in visits]  # fmt: skip
    queries = table(list(QUERY_COLUMNS.values()), [])
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("ST_20261111_010101_Queries.csv", queries)
        z.writestr("ST_20261111_010101_SDV.csv", table(list(sc.values()), sdv))
        z.writestr("ST_20261111_010101_Review_status.csv", table(list(rc.values()), review))
    forms = read_export(archive.getvalue()).forms
    assert sorted((f.event_id, f.sdv_required, f.kind) for f in forms) == [
        ("E01", 1, "event_date"),
        ("E02", 1, "event_date"),
    ]


def test_download_only_for_admin_and_data_manager() -> None:
    from app.auth.rbac import ROLE_PERMISSIONS, Permission

    can_download = {role for role, perms in ROLE_PERMISSIONS.items() if Permission.DM_EXPORT in perms}
    assert can_download == {Role.ADMIN, Role.DATA_MANAGER}  # never CRAs (user decision)
    assert all(Permission.DM_VIEW in perms for perms in ROLE_PERMISSIONS.values())


def test_staff_names_are_never_stored(db_session: Session) -> None:
    """Roles only: Viedoc's user names (query history, SDV/review/sign/lock "by") are not kept."""
    from app.data_management.models import DmFormStatus, DmQueryEvent

    asyncio.run(sync_connection(db_session, _settings(), tenant_id="avion", name="demo", triggered_by="t"))
    events = db_session.scalars(select(DmQueryEvent)).all()
    assert events and all(e.user_name is None for e in events)
    assert any(e.user_role == "Study Coordinator" for e in events)
    forms = db_session.scalars(select(DmFormStatus)).all()
    assert forms and all(
        f.last_sdv_by is None and f.data_review_by is None and f.signed_by is None and f.locked_by is None
        for f in forms
    )
    assert any(f.signed_at for f in forms)  # the dates are kept


def test_sync_guard_reuses_a_fresh_sync_and_refuses_a_second_running_one(dm) -> None:  # type: ignore[no-untyped-def]
    from app.data_management import api as dm_api

    client = dm(Role.CRA)
    first = client.post(f"{API}/sync", json={"connection": "demo"}).json()
    again = client.post(f"{API}/sync", json={"connection": "demo"}).json()
    assert (
        first["ok"] and again["started_at"][:26] == first["started_at"][:26]
    )  # reused: Viedoc not asked again
    events = dm().get("/api/v1/audit-events").json()["items"]
    assert sum(e["action"] == "dm.synced" for e in events) == 1
    dm_api._SYNCING.add(("avion", "demo"))
    try:
        refused = client.post(f"{API}/sync", json={"connection": "demo"})
        assert refused.status_code == 409 and "already running" in refused.json()["detail"]
    finally:
        dm_api._SYNCING.discard(("avion", "demo"))


def _sheet(content: bytes, name: str) -> list[tuple[object, ...]]:
    import io

    from openpyxl import load_workbook

    return list(load_workbook(io.BytesIO(content), read_only=True)[name].iter_rows(values_only=True))


@pytest.mark.parametrize(
    ("role", "code"),
    [
        (Role.ADMIN, 200),
        (Role.DATA_MANAGER, 200),
        (Role.CRA, 403),  # never CRAs (user decision)
        (Role.PROJECT_MANAGER, 403),
        (Role.QA, 403),
        (Role.VIEWER, 403),
    ],
)
def test_excel_download_only_for_admin_and_data_manager(dm, role: Role, code: int) -> None:  # type: ignore[no-untyped-def]
    client = dm(role)
    assert client.get(f"{API}/queries/export.xlsx").status_code == code
    assert client.get(f"{API}/sdv/export.xlsx").status_code == code
    assert client.get(f"{API}/status").json()["can_export"] is (code == 200)


def test_queries_excel_matches_the_screen(dm) -> None:  # type: ignore[no-untyped-def]
    client = dm(Role.DATA_MANAGER)
    params = {"site": "102", "state": "not_closed"}
    on_screen = client.get(f"{API}/queries", params=params).json()
    res = client.get(f"{API}/queries/export.xlsx", params=params)
    assert res.status_code == 200 and res.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert 'filename="DEMO_DM queries site 102' in res.headers["content-disposition"]
    rows = _sheet(res.content, "Queries")
    assert rows[0][:4] == ("Study", "Site", "Site name", "Subject") and "Query text" in rows[0]
    assert len(rows) - 1 == on_screen["total"] and all(r[1] == "102" for r in rows[1:])
    assert [r[7] for r in rows[1:]] == [q["query_number"] for q in on_screen["queries"]]  # same order
    about = dict((r[0], r[1]) for r in _sheet(res.content, "About"))
    assert "site: 102" in str(about["Filters"]) and "role" in str(about["Data protection"])
    events = dm().get("/api/v1/audit-events").json()["items"]
    assert any(e["action"] == "dm.exported" and e["entity_id"] == "queries" for e in events)


def test_sdv_excel_matches_the_screen(dm) -> None:  # type: ignore[no-untyped-def]
    client = dm()
    on_screen = client.get(f"{API}/sdv", params={"view": "all"}).json()
    res = client.get(f"{API}/sdv/export.xlsx", params={"view": "all"})
    assert res.status_code == 200
    forms = _sheet(res.content, "SDV forms")
    assert len(forms) - 1 == on_screen["total"]
    assert sum(r[8] for r in forms[1:]) == on_screen["summary"]["required"]  # type: ignore[misc]
    assert len(_sheet(res.content, "By site")) - 1 == len(on_screen["sites"])
    assert len(_sheet(res.content, "By visit")) - 1 == len(on_screen["visits"])
