"""Ask Avi.Intelligence about studies: question understanding, answers (no AI) and the /ask endpoint."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assistant.study_questions import answer, understand
from app.assistant.study_tools import (
    TOOLS,
    PlanInput,
    anthropic_tool_definitions,
    load_study_data,
    plan_items,
    run_tool,
)
from app.connectors.simpletrials.models import (
    MilestoneRecord,
    SiteRecord,
    StudyConnectorInfo,
    StudyRecord,
)
from app.knowledge.models import AssistantInteraction
from app.studies.models import StudyMilestone
from app.studies.sync import sync_studies

TODAY = date(2026, 11, 11)
ASK = "/api/v1/assistant/ask"


class ListConnector:
    def __init__(self, records: list[StudyRecord]) -> None:
        self.records = records

    def info(self) -> StudyConnectorInfo:
        return StudyConnectorInfo(mode="mock", mock_reason="test")

    async def fetch_studies(self) -> list[StudyRecord]:
        return self.records


def _d(days: int) -> date:
    return TODAY + timedelta(days=days)


def _m(name: str, end: int, *, original: int | None = None, phase: str | None = None, key: bool = False,
       done: bool = False) -> MilestoneRecord:  # fmt: skip
    return MilestoneRecord(
        external_id=name,
        name=name,
        planned_date=_d(end),
        baseline_date=_d(original) if original is not None else None,
        percent_complete=100 if done else 0,
        phase=phase,
        is_key=key,
    )


def _records() -> list[StudyRecord]:
    return [
        StudyRecord(
            external_id="A",
            protocol_number="AV-ONC-301",
            title="Oncology study",
            therapeutic_area="Oncology",
            enrolment_target=100,
            enrolled=40,
            sites=[
                SiteRecord(
                    external_id="A1",
                    site_number="101",
                    name="North Hospital",
                    enrolled=30,
                    enrolment_target=50,
                    activation_date=_d(-200),
                ),
                SiteRecord(
                    external_id="A2",
                    site_number="102",
                    name="South Clinic",
                    enrolled=0,
                    enrolment_target=50,
                    activation_target=_d(-10),
                ),
            ],  # fmt: skip
            milestones=[
                _m(
                    "04.05 First Patient In, First Visit (FPI, FPFV) Complete",
                    -100,
                    original=-110,
                    key=True,
                    done=True,
                ),
                _m("05.04 Last Patient In (LPI) Complete", 40, original=0, key=True),
                _m("05.05 Last Patient Out, Last Visit (LPO, LPLV) Complete", 200, original=150, key=True),
                _m("06.01 All Site Closeout Visits Complete", 60, phase="06. Site Closeout Activities"),
                _m("07.01 Database Soft Lock", -3, phase="07. Study Closeout Activities"),
                _m("07.03 Database Hard Lock", 300, phase="07. Study Closeout Activities", key=True),
            ],  # fmt: skip
        ),
        StudyRecord(
            external_id="B",
            protocol_number="AV-CV-201",
            title="Cardiology study",
            therapeutic_area="Cardiology",
            sites=[SiteRecord(external_id="B1", site_number="301", name="Heart Centre", enrolled=5)],
            milestones=[_m("04.05 First Patient In, First Visit (FPI, FPFV) Complete", 20, key=True)],
        ),
    ]


@pytest.fixture
def data(db_session: Session) -> Any:
    asyncio.run(sync_studies(db_session, ListConnector(_records()), tenant_id="avion", triggered_by="t"))
    source = "demo"
    return load_study_data(db_session, "avion", source, TODAY, None)


def _ids(data: Any, *numbers: str) -> list[str]:
    return [s.id for s in data.studies if s.protocol_number in numbers]


class TestUnderstanding:
    @pytest.mark.parametrize(
        "question",
        [
            "What are the key requirements for site activation?",
            "When are SAE reports due?",
            "How do I complete the delegation log?",
            "What is the SOP for monitoring visits?",
            "Which form do I use for a protocol deviation?",
            "Tell me about risk-based monitoring",
            "site initiation visit",
            "site activation checklist",
        ],
    )
    def test_procedure_questions_go_to_sop_search(self, data: Any, question: str) -> None:
        assert understand(question, data) is None

    @pytest.mark.parametrize(
        ("question", "intent"),
        [
            ("How are my studies going?", "status"),
            ("How is AV-ONC-301 going?", "status"),
            ("Is anything due for study closing?", "due"),
            ("Are we falling behind?", "behind"),
            ("Which sites are behind on enrolment?", "enrolment"),
            ("Which sites aren't activated?", "activation"),
            ("Any overdue tasks?", "tasks"),
            ("Open risks on the oncology study?", "risks"),
            ("When is database lock?", "milestone"),
        ],
    )
    def test_study_questions(self, data: Any, question: str, intent: str) -> None:
        parsed = understand(question, data)
        assert parsed is not None and parsed.intent == intent

    def test_study_site_phase_and_window(self, data: Any) -> None:
        q = understand("Is anything due for close-out on ONC-301 in the next 2 months?", data)
        assert q is not None
        assert (q.intent, q.phase, q.window_days) == ("due", "close-out", 60)
        assert q.study_ids == _ids(data, "AV-ONC-301")
        assert understand("Open risks on the cardiology study?", data).study_ids == _ids(data, "AV-CV-201")  # type: ignore[union-attr]
        site = understand("status of site 102", data)
        assert site is not None and site.site_numbers == ["102"]

    def test_milestone_names_abbreviations_and_typos(self, data: Any) -> None:
        def names(question: str) -> list[str]:
            q = understand(question, data)
            assert q is not None and q.intent == "milestone"
            return q.milestones

        assert names("When is LPI?") == ["05.04 Last Patient In (LPI) Complete"]
        assert names("when is last patient in") == ["05.04 Last Patient In (LPI) Complete"]
        assert names("When is databse lock?") == ["07.01 Database Soft Lock", "07.03 Database Hard Lock"]
        # "last" never matches "first": no entry matches, and the answer says so.
        q = understand("When is last patient in for AV-CV-201?", data)
        assert q is not None and q.intent == "milestone" and q.milestones == []
        assert q.asked_name == "last patient in"
        a = answer(data, q)
        assert a.headline == 'No plan entry matches "last patient in" in SimpleTrials.'


class TestAnswers:
    def test_status_one_study(self, data: Any) -> None:
        a = answer(data, understand("How is AV-ONC-301 going?", data))  # type: ignore[arg-type]
        assert a.headline == "AV-ONC-301 is not on plan."  # LPI slipped 40 days, LPO 50
        assert "Not on plan: 2 slipped more than 30 days." in a.lines
        assert any(line.startswith("Next key milestone: 05.04 Last Patient In") for line in a.lines)
        assert "Enrolment: 40 of 100 (40%)." in a.lines
        assert "Sites: 1 of 2 activated." in a.lines
        assert a.tables[0].title == "Key milestones" and len(a.tables[0].rows) == 4
        assert a.sources[0].url.startswith("/command-centre/")

    def test_status_all_studies(self, data: Any) -> None:
        a = answer(data, understand("How are my studies going?", data))  # type: ignore[arg-type]
        assert a.headline == "1 of 2 studies are not on plan."
        assert [r[0] for r in a.tables[0].rows] == ["AV-CV-201", "AV-ONC-301"]

    def test_close_out_due(self, data: Any) -> None:
        a = answer(data, understand("Is anything due for study close-out?", data))  # type: ignore[arg-type]
        names = [r[1] for r in a.tables[0].rows]
        # Soft lock is overdue; close-out visits are due in 60 days; LPO (200) and hard lock (300) are later.
        assert names == ["07.01 Database Soft Lock", "06.01 All Site Closeout Visits Complete"]
        assert a.lines == ["1 close-out plan entry due in the next 90 days.", "1 already overdue."]
        assert "close-out" in a.understood and "next 90 days" in a.understood

    def test_close_out_nothing_in_window_shows_the_next(self, data: Any) -> None:
        a = answer(data, understand("Anything due for close-out on AV-CV-201?", data))  # type: ignore[arg-type]
        assert a.headline == "Nothing close-out is due in the next 90 days."
        assert "No open close-out entries with an end date in SimpleTrials." in a.lines

    def test_behind(self, data: Any) -> None:
        a = answer(data, understand("Are we falling behind?", data))  # type: ignore[arg-type]
        assert a.headline == "Yes, some work is behind."
        titles = [t.title for t in a.tables]
        assert titles[:2] == ["Overdue", "Slipped more than 30 days"]
        assert "Sites not activated by their planned date" in titles
        assert "Sites past their planned activation date: 1." in a.lines

    def test_milestone_dates(self, data: Any) -> None:
        a = answer(data, understand("When is LPO for ONC-301?", data))  # type: ignore[arg-type]
        assert a.headline.startswith("05.05 Last Patient Out, Last Visit (LPO, LPLV) Complete: current end")
        assert "(+50 days)" in a.headline

    def test_enrolment_and_activation(self, data: Any) -> None:
        a = answer(data, understand("Which sites are behind on enrolment?", data))  # type: ignore[arg-type]
        assert [r[1] for r in a.tables[0].rows][:2] == ["102 · South Clinic", "101 · North Hospital"]
        assert a.headline == "1 site is below half of their enrolment target."
        b = answer(data, understand("Which sites aren't activated?", data))  # type: ignore[arg-type]
        # Site 102 is 10 days past its planned date (first); site 301 has no planned date.
        assert b.headline == "2 sites not yet activated." and b.tables[0].rows[0][4] == "10"

    def test_site_status(self, data: Any) -> None:
        a = answer(data, understand("status of site 102", data))  # type: ignore[arg-type]
        assert a.headline == (
            "Site 102 · South Clinic (AV-ONC-301): status not recorded; not activated "
            f"(planned {a.tables[0].rows[0][4]}, 10 days late); 0 of 50 enrolled (0%)."
        )


def test_tools_are_ready_for_claude(data: Any) -> None:
    defs = anthropic_tool_definitions()
    assert [d["name"] for d in defs] == [t.name for t in TOOLS]
    assert all(d["input_schema"]["type"] == "object" and d["description"] for d in defs)
    by_tool = run_tool(data, "plan_items", {"phase_words": ["close"], "include_completed": True})
    assert by_tool == plan_items(data, PlanInput(phase_words=["close"], include_completed=True))


class TestEndpoint:
    def test_study_question_is_answered_recorded_and_audited(
        self, client: TestClient, db_session: Session
    ) -> None:
        res = client.post(ASK, json={"question": "Is anything due for study close-out?"})
        assert res.status_code == 200
        body = res.json()
        assert body["kind"] == "study" and body["mode"] == "study-lookup" and body["model"] is None
        assert body["study"]["intent"] == "due" and body["study"]["sources"]
        row = db_session.scalars(select(AssistantInteraction)).one()
        assert row.mode == "study-lookup" and row.answer and row.citations
        events = client.get("/api/v1/audit-events").json()["items"]
        asked = next(e for e in events if e["action"] == "assistant.asked")
        assert asked["details"]["kind"] == "study" and asked["details"]["intent"] == "due"

    def test_sop_questions_still_search_sops(self, client: TestClient) -> None:
        body = client.post(
            ASK, json={"question": "What are the key requirements for site activation?"}
        ).json()
        assert body["kind"] == "sop" and body["study"] is None and body["excerpts"]

    def test_status_lists_study_examples(self, client: TestClient) -> None:
        body = client.get("/api/v1/assistant/status").json()
        assert "How are my studies going?" in body["study_questions"]


def _add_entry(data: Any, name: str, kind: str = "milestone", planned: date | None = None) -> None:
    study = data.studies[0]
    study.milestones.append(
        StudyMilestone(
            study_id=study.id, external_id=name, name=name, kind=kind, is_key=False, planned_date=planned
        )
    )


def test_sites_question_is_not_the_all_sites_activated_milestone(data: Any) -> None:
    # A plan entry called "All Sites Activated" must not take over a question about sites.
    _add_entry(data, "04.06 All Sites Activated")
    q = understand("Which sites aren't activated?", data)
    assert q is not None and q.intent == "activation"
    q = understand("When is all sites activated?", data)
    assert q is not None and q.intent == "milestone"


def test_abbreviations_and_close_out_words(data: Any) -> None:
    _add_entry(data, "07.09 Clinical Study Report Finalized")
    _add_entry(data, "03.01 CRF Database Developed", kind="task", planned=TODAY)
    q = understand("When is the CSR finalised?", data)
    assert q is not None and q.milestones == ["07.09 Clinical Study Report Finalized"]
    # "Database" alone is not close-out: the CRF database build is not listed.
    a = answer(data, understand("Is anything due for study close-out?", data))  # type: ignore[arg-type]
    assert all("CRF Database" not in r[1] for t in a.tables for r in t.rows)
