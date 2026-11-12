"""SimpleTrials API client, mapping and connector, against a fake API (no network)."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import date
from typing import Any

import httpx
import pytest

from app.connectors.simpletrials import build_study_connector
from app.connectors.simpletrials.api_client import SimpleTrialsClient, SimpleTrialsError, validate_base_url
from app.connectors.simpletrials.live import ApiStudyConnector
from app.connectors.simpletrials.mapping import (
    as_int,
    map_action_items,
    map_documents,
    map_plan,
    map_site,
    map_study,
    normalise_name,
    parse_key_names,
)
from app.core.config import Settings as RealSettings
from app.core.logging import JsonFormatter, redact
from app.studies.rules import MilestoneState, ScheduleState, milestone_state, schedule_state, variance_days

KEY = "00000000-test-key-0000-000000000000"

STUDY = {
    "id": 42,
    "number": "Sandbox Study",
    "name": None,
    "description": "A fictitious single-blind Phase IIB study to evaluate a demo product",
    "program_name": "Influenza",
    "study_indication": "Influenza",
    "phase_display": "IIB",
    "status_display": "Planned",
    "sponsor": {"display_name": "SandboxPharma"},
    "original_targets": {"sites": "15", "enrolled": "40"},
    "revised_targets": {"sites": "0", "enrolled": "0"},
    "actual_enrolled": 5,
    "sandbox": True,
    "study_countries": [{"country_name": "USA"}, {"country_name": "Australia"}],
}

SITES = [
    {
        "id": 1,
        "number": "1001",
        "active": True,
        "organization_display_name": "General Hospital",
        "descriptor": "1001 : General Hospital : USA : Feyton, Kathy",
        "principal_investigator_full_name": "Kathy Feyton",
        "status": "selected",
        "status_display": "Selected",
        "substatus": "active",
        "substatus_display": "Active",
        "detail": {
            "site_activation_actual": "2026-04-14",
            "subjects_enrolled_actual": 3,
            "subjects_enrolled_target": 8,
        },
    },
    {
        "id": 2,
        "number": "2014",
        "active": True,
        "organization_display_name": "Calvary City",
        "descriptor": "2014 : Calvary City : Australia : ",
        "status_display": "Pending",
        "substatus": "not_applicable",
        "substatus_display": "N/A",
        "detail": {},
    },
    {"id": 3, "number": "9999", "active": False, "organization_display_name": "Inactive site"},
]

TASKS = [
    {
        "id": 10,
        "name": "04. Site Startup Activities",
        "parent_task_id": None,
        "duration_value": 62,
        "active": True,
        "end_date": "2026-08-24",
        "baseline_end_date": "2026-08-24",
        "percent_complete": 0,
    },
    {
        # As in the Sandbox: First Patient In has a 2-day duration but carries the "fpi" code.
        "id": 11,
        "name": "04.05 First Patient In",
        "parent_task_id": 10,
        "duration_value": 2,
        "system_name": "fpi",
        "active": True,
        "start_date": "2026-06-09",
        "baseline_start_date": "2026-06-08",
        "end_date": "2026-06-11",
        "baseline_end_date": "2026-06-09",
        "percent_complete": 100,
    },
    {
        "id": 12,
        "name": "04.06 All Sites Activated",
        "parent_task_id": 10,
        "duration_value": 0,
        "system_name": "all_sites_activated",
        "active": True,
        "end_date": "2026-08-24",
        "baseline_end_date": "2026-08-24",
        "percent_complete": 0,
    },
    {
        "id": 14,
        "name": "04.01 First Ethics Approval",
        "parent_task_id": 10,
        "duration_value": 0,
        "system_name": None,
        "active": True,
        "end_date": "2026-05-28",
        "baseline_end_date": "2026-05-28",
    },
    {
        "id": 15,
        "name": "04.02 Regulatory Binder Prepared",
        "parent_task_id": 10,
        "duration_value": 0,
        "active": True,
        "end_date": "2026-05-30",
    },
    {
        "id": 16,
        "name": "04.03 Contract Negotiation",
        "parent_task_id": 10,
        "duration_value": 30,
        "active": True,
        "start_date": "2026-04-01",
        "end_date": "2026-07-01",
        "baseline_end_date": "2026-05-01",
    },
    {
        "id": 13,
        "name": "Removed milestone",
        "parent_task_id": 10,
        "duration_value": 0,
        "active": False,
        "end_date": "2026-01-01",
    },
]


DOCUMENTS: list[dict[str, Any]] = [
    {  # expected at a site, not yet filed
        "id": 1,
        "active": True,
        "placeholder": True,
        "tmf_level": "site",
        "site_id": 5001,
        "common_name": "Original Protocol",
        "title": "Original Protocol",
        "document_path": "Sandbox Study/BY SITE/1001 : General Hospital : USA : smith, john/"
        "01. General Study Documents/01.01 Protocol",
        "created_at": "2026-02-19T16:54:57.401+00:00",
    },
    {  # filed at study level; an older version (precursor 3) is left out
        "id": 2,
        "active": True,
        "placeholder": False,
        "tmf_level": "study",
        "precursor_id": 3,
        "title": "Insurance certificate v2.pdf",
        "file_name": "Insurance certificate v2.pdf",
        "original_file_name": "secret-name.pdf",
        "url": "https://example.invalid/file",
        "document_path": "Sandbox Study/01. General Study Documents",
        "uploaded_at": "2026-04-14T05:13:14.975+00:00",
        "doc_version_on": "2026-04-10",
        "expires_on": "2026-04-15",
        "expiration_status": "expired",
        "doc_status_display": "Draft",
        "qc_status": "approved",
        "qc_ended_at": "2026-04-16T00:00:00+00:00",
        "doc_version": "2.0",
    },
    {
        "id": 3,
        "active": True,
        "placeholder": False,
        "document_path": "Sandbox Study/01. General Study Documents",
    },
    {"id": 4, "active": True, "placeholder": False, "parent_type": "PaymentHistory", "document_path": "x"},
    {"id": 5, "active": False, "placeholder": True, "document_path": "Sandbox Study/02. Other"},
    {"id": 6, "active": True, "placeholder": True, "document_path": "", "title": "Loose document"},
]


ACTIONS = [
    {
        "id": 11, "number": 1, "active": True, "unblinded": False, "category": "site",
        "category_display": "Site", "subcategory": "site_visit", "subcategory_display": "Site Visit",
        "priority": "high", "priority_display": "High", "status": "new", "site_number": "1001",
        "site_display_name": "Sandbox Clinic", "description": "Collect   the missing\nlog", "response": None,
        "assigned_to_display_name": "Smith, Alex", "assigned_to_id": 991, "opened_by_id": 992,
        "opened_on": "2026-10-01", "due_on": "2026-10-15", "closed_on": None,
        "created_at": "2026-10-01T09:00:00.000+00:00",
    },
    {
        "id": 12, "number": 2, "active": True, "unblinded": False, "category": "study", "status": "closed",
        "priority": "normal", "closed_on": "2026-10-20", "opened_on": "2026-10-02", "description": "Done",
    },
    {"id": 13, "number": 3, "active": True, "unblinded": True, "status": "new", "description": "Unblinded"},
    {"id": 14, "number": 4, "active": False, "status": "new", "description": "Deleted"},
]  # fmt: skip


class FakeApi:
    """Records requests and serves canned JSON; pages lists by limit/offset like SimpleTrials."""

    def __init__(self, routes: dict[str, Any], page_size: int | None = None) -> None:
        self.routes = routes
        self.page_size = page_size
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        name = request.url.path.rsplit("/", 1)[-1]
        route = self.routes.get(name)
        if callable(route):
            return route(request)  # type: ignore[no-any-return]
        if route is None:
            return httpx.Response(404, json={"error": "Not found"})
        if isinstance(route, list):
            offset = int(request.url.params.get("offset", 0))
            limit = self.page_size or int(request.url.params.get("limit", 1000))
            page = route[offset : offset + limit]
            return httpx.Response(200, json={name: page, "count": len(page), "total": len(route)})
        return httpx.Response(200, json=route)

    def client(self, scope: str = "study", **kw: Any) -> SimpleTrialsClient:
        return SimpleTrialsClient(
            base_url="https://app.simpletrials.com/api/v1/",
            scope=scope,  # type: ignore[arg-type]
            account_id="42",
            key=KEY,
            transport=httpx.MockTransport(self.handler),
            retry_base_seconds=0,
            **kw,
        )


class TestMapping:
    def test_study(self) -> None:
        rec = map_study(STUDY, SITES, TASKS)
        assert rec.external_id == "42"
        assert rec.protocol_number == "Sandbox Study"
        assert rec.title.startswith("A fictitious single-blind")
        assert (rec.sponsor, rec.phase, rec.status) == ("SandboxPharma", "Phase IIB", "Planned")
        assert rec.enrolment_target == 40  # revised "0" means not set, so the original target is used
        assert rec.enrolled == 5 and rec.sandbox is True
        assert rec.countries == ["USA", "Australia"]
        assert [s.site_number for s in rec.sites] == ["1001", "2014"]  # inactive site skipped

    def test_site(self) -> None:
        site = map_site(SITES[0])
        assert site is not None
        assert site.status == "Selected · Active"
        assert site.country == "USA"
        assert site.activation_date == date(2026, 4, 14)
        assert (site.enrolled, site.enrolment_target) == (3, 8)
        pending = map_site(SITES[1])
        assert pending is not None and pending.status == "Pending" and pending.enrolled is None

    def test_full_plan_in_simpletrials_order(self) -> None:
        plan = map_plan(TASKS, parse_key_names("First Ethics Approval;Database Hard Lock"))
        # Everything active is kept, in SimpleTrials order; the inactive entry is dropped.
        assert [p.external_id for p in plan] == ["10", "11", "12", "14", "15", "16"]
        kinds = {p.name: p.kind for p in plan}
        assert kinds["04. Site Startup Activities"] == "phase"
        assert kinds["04.05 First Patient In"] == "milestone"  # has a duration but carries the "fpi" code
        assert kinds["04.02 Regulatory Binder Prepared"] == "milestone"
        assert kinds["04.03 Contract Negotiation"] == "task"

    def test_key_milestones(self) -> None:
        plan = {p.name: p for p in map_plan(TASKS, parse_key_names("first ethics approval"))}
        assert plan["04.05 First Patient In"].is_key  # SimpleTrials code
        assert plan["04.06 All Sites Activated"].is_key  # SimpleTrials code
        assert plan["04.01 First Ethics Approval"].is_key  # Avion's list, numbering and case ignored
        assert not plan["04.02 Regulatory Binder Prepared"].is_key
        assert not plan["04.03 Contract Negotiation"].is_key  # tasks are never key milestones
        assert not plan["04. Site Startup Activities"].is_key

    def test_plan_fields(self) -> None:
        fpi = next(p for p in map_plan(TASKS) if p.external_id == "11")
        assert fpi.phase == "04. Site Startup Activities" and fpi.parent_external_id == "10"
        assert (fpi.start_date, fpi.planned_date, fpi.baseline_date, fpi.percent_complete) == (
            date(2026, 6, 9),
            date(2026, 6, 11),
            date(2026, 6, 9),
            100,
        )
        assert fpi.baseline_start_date == date(2026, 6, 8)
        assert fpi.system_code == "fpi"
        assert fpi.actual_date is None  # the API has no actual completion date
        assert normalise_name("07.03  Database HARD lock") == "database hard lock"

    def test_targets_and_numbers(self) -> None:
        assert as_int("40") == 40 and as_int("x") is None and as_int(None) is None and as_int(True) is None
        assert map_study({**STUDY, "revised_targets": {"enrolled": "50"}}, [], []).enrolment_target == 50
        assert map_study({**STUDY, "original_targets": {"enrolled": "0"}}, [], []).enrolment_target is None


class TestPlanRules:
    today = date(2026, 11, 6)

    def test_progress_status(self) -> None:
        t = self.today
        assert milestone_state(date(2026, 6, 11), None, t, 100) == MilestoneState.COMPLETED
        assert milestone_state(date(2026, 6, 11), None, t, 50) == MilestoneState.OVERDUE
        assert milestone_state(date(2026, 11, 20), None, t, 0) == MilestoneState.DUE_SOON
        assert (
            milestone_state(date(2027, 3, 1), None, t, 10, start=date(2026, 10, 1))
            == MilestoneState.IN_PROGRESS
        )
        assert (
            milestone_state(date(2027, 3, 1), None, t, 0, start=date(2027, 1, 1))
            == MilestoneState.NOT_STARTED
        )
        assert milestone_state(date(2027, 3, 1), None, t, 0) == MilestoneState.UPCOMING  # no start date

    def test_schedule_status(self) -> None:
        d = date(2026, 6, 9)
        assert schedule_state(d, d) == ScheduleState.ON_PLAN
        assert schedule_state(date(2026, 6, 11), d) == ScheduleState.SLIPPED
        assert schedule_state(date(2026, 7, 10), d) == ScheduleState.SLIPPED_MAJOR  # more than 30 days
        assert schedule_state(date(2026, 7, 9), d) == ScheduleState.SLIPPED  # exactly 30 days
        assert schedule_state(date(2026, 6, 1), d) == ScheduleState.AHEAD
        assert schedule_state(d, None) == ScheduleState.NO_BASELINE
        assert variance_days(date(2026, 6, 11), d) == 2 and variance_days(date(2026, 6, 1), d) == -8


class TestClient:
    def test_study_scope_sends_study_credentials_and_user_agent(self) -> None:
        api = FakeApi({"study": STUDY})
        asyncio.run(api.client().get("study"))
        req = api.requests[0]
        assert req.method == "GET"
        assert req.url.params["study_id"] == "42" and req.url.params["study_key"] == KEY
        assert "customer_key" not in req.url.params
        assert req.headers["user-agent"].startswith("Avi.Intelligence")

    def test_pagination(self) -> None:
        tasks = [{"id": i} for i in range(5)]
        api = FakeApi({"tasks": tasks}, page_size=2)
        items = asyncio.run(api.client().list_all("tasks", "tasks"))
        assert [t["id"] for t in items] == [0, 1, 2, 3, 4]
        assert [r.url.params["offset"] for r in api.requests] == ["0", "2", "4"]

    def test_retries_on_rate_limit(self) -> None:
        calls = {"n": 0}

        def flaky(_req: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(429) if calls["n"] < 3 else httpx.Response(200, json=STUDY)

        assert asyncio.run(FakeApi({"study": flaky}).client().get("study"))["id"] == 42
        assert calls["n"] == 3

    @pytest.mark.parametrize("status", [401, 403, 412, 500])
    def test_errors_never_contain_the_key(self, status: int) -> None:
        api = FakeApi({"study": lambda _r: httpx.Response(status, json={"error": "nope"})})
        with pytest.raises(SimpleTrialsError) as err:
            asyncio.run(api.client().get("study"))
        assert KEY not in str(err.value) and "simpletrials.com" not in str(err.value)
        assert err.value.status == status

    def test_network_error_never_contains_the_key(self) -> None:
        def boom(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError(f"failed {request.url}")

        with pytest.raises(SimpleTrialsError) as err:
            asyncio.run(FakeApi({"study": boom}).client().get("study"))
        assert KEY not in str(err.value)

    def test_only_simpletrials_hosts(self) -> None:
        with pytest.raises(ValueError):
            validate_base_url("https://evil.example.com/api/v1/")
        with pytest.raises(ValueError):
            validate_base_url("http://app.simpletrials.com/api/v1/")
        assert (
            validate_base_url("https://eu.simpletrials.com/api/v1") == "https://eu.simpletrials.com/api/v1/"
        )


class TestConnector:
    def test_study_scope(self) -> None:
        api = FakeApi({"study": STUDY, "sites": SITES, "tasks": TASKS})
        connector = ApiStudyConnector(api.client())
        records = asyncio.run(connector.fetch_studies())
        assert len(records) == 1 and records[0].protocol_number == "Sandbox Study"
        assert [r.url.path.rsplit("/", 1)[-1] for r in api.requests] == [
            "study",
            "sites",
            "tasks",
            "documents",
            "action_items",
        ]
        assert connector.info().mode == "api" and connector.info().scope == "study"
        # No eTMF or action item access (404 here): the study still syncs; previous copies are kept.
        assert records[0].documents is None and records[0].action_items is None

    def test_reads_etmf_metadata_and_never_patient_data(self) -> None:
        api = FakeApi(
            {"study": STUDY, "sites": SITES, "tasks": TASKS, "documents": DOCUMENTS, "action_items": ACTIONS}
        )
        records = asyncio.run(ApiStudyConnector(api.client()).fetch_studies())
        assert records[0].documents is not None and len(records[0].documents) == 3
        assert records[0].action_items is not None and len(records[0].action_items) == 2
        paths = {r.url.path.rsplit("/", 1)[-1] for r in api.requests}
        assert "subjects" not in paths and paths <= {"study", "sites", "tasks", "documents", "action_items"}

    def test_workspace_scope_lists_studies(self) -> None:
        api = FakeApi(
            {"studies": [{"id": 42}, {"id": 43, "active": False}], "study": STUDY, "sites": [], "tasks": []}
        )
        records = asyncio.run(ApiStudyConnector(api.client(scope="workspace")).fetch_studies())
        assert len(records) == 1
        assert api.requests[0].url.params["customer_key"] == KEY
        assert api.requests[1].url.params["study_id"] == "42"

    def test_only_get_requests(self) -> None:
        api = FakeApi({"study": STUDY, "sites": SITES, "tasks": TASKS})
        asyncio.run(ApiStudyConnector(api.client()).fetch_studies())
        assert {r.method for r in api.requests} == {"GET"}


def Settings(**kw: Any) -> RealSettings:  # noqa: N802 - isolate from the developer's .env file
    # conftest forces SIMPLETRIALS_MODE=mock for the app; these tests exercise mode selection itself.
    return RealSettings(_env_file=None, **{"simpletrials_mode": "auto", **kw})  # type: ignore[call-arg]


class TestSettings:
    def test_mode_selection(self) -> None:
        assert build_study_connector(Settings(simpletrials_mode="auto")).info().mode == "mock"
        study = Settings(simpletrials_study_id="42", simpletrials_study_key=KEY)
        assert build_study_connector(study).info().scope == "study"
        both = Settings(
            simpletrials_study_id="42",
            simpletrials_study_key=KEY,
            simpletrials_customer_id="7",
            simpletrials_customer_key=KEY,
        )
        assert both.simpletrials_scope == "workspace"
        assert (
            build_study_connector(
                Settings(simpletrials_mode="mock", simpletrials_study_id="1", simpletrials_study_key=KEY)
            )
            .info()
            .mode
            == "mock"
        )
        with pytest.raises(RuntimeError):
            build_study_connector(
                Settings(simpletrials_mode="api", simpletrials_study_key=None, simpletrials_study_id=None)
            )

    def test_key_hidden_in_settings_repr(self) -> None:
        assert KEY not in repr(Settings(simpletrials_study_id="42", simpletrials_study_key=KEY))


def test_logs_redact_keys() -> None:
    assert (
        redact(f"GET /api/v1/study?study_id=42&study_key={KEY}")
        == "GET /api/v1/study?study_id=42&study_key=***"
    )
    record = logging.makeLogRecord({"msg": f"url customer_key={KEY}&x=1", "levelname": "INFO", "name": "t"})
    out = json.loads(JsonFormatter().format(record))
    assert KEY not in out["msg"]


def test_map_documents() -> None:
    docs = {d.external_id: d for d in map_documents(DOCUMENTS)}
    assert set(docs) == {"1", "2", "6"}  # superseded (3), payment attachment (4) and inactive (5) left out
    site = docs["1"]
    assert (site.level, site.site_external_id, site.filed) == ("site", "5001", False)
    assert (site.section, site.folder, site.name) == (
        "01. General Study Documents",
        "01.01 Protocol",
        "Original Protocol",
    )
    filed = docs["2"]
    assert (filed.level, filed.section, filed.folder, filed.filed) == (
        "study",
        "01. General Study Documents",
        None,
        True,
    )
    assert filed.uploaded_on == date(2026, 4, 14) and filed.document_date == date(2026, 4, 10)
    assert filed.expired is True and filed.expires_on == date(2026, 4, 15)
    assert (filed.doc_status, filed.qc_status, filed.version) == ("Draft", "approved", "2.0")
    assert filed.qc_ended_on == date(2026, 4, 16)
    # File names, URLs and people are never kept.
    dumped = str(filed.model_dump())
    assert (
        "secret-name" not in dumped
        and "example.invalid" not in dumped
        and "smith" not in str(site.model_dump())
    )
    assert docs["6"].section == "Unfiled" and docs["6"].name == "Loose document"


def test_map_action_items() -> None:
    items = {a.external_id: a for a in map_action_items(ACTIONS)}
    assert set(items) == {"11", "12"}  # unblinded and inactive items are never read
    first = items["11"]
    assert (first.number, first.category, first.subcategory, first.priority, first.status) == (
        "1",
        "Site",
        "Site Visit",
        "High",
        "New",
    )
    assert (first.site_number, first.site_name, first.assignee) == ("1001", "Sandbox Clinic", "Smith, Alex")
    assert first.description == "Collect the missing log" and first.closed is False
    assert (first.opened_on, first.due_on) == (date(2026, 10, 1), date(2026, 10, 15))
    assert "991" not in str(first.model_dump())  # user ids are not kept
    done = items["12"]
    assert done.closed is True and done.closed_on == date(2026, 10, 20) and done.category == "Study"
