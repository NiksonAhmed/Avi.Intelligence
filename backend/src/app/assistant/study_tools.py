"""Read-only study look-ups for Ask Avi.Intelligence.

Each look-up reads Avi.Intelligence's copy of SimpleTrials (plus its own tasks and risks) and applies the
same rules as the Study Command Centre and Reports, so every answer agrees with those pages. Nothing is
written and SimpleTrials is not called while answering.

The look-ups are deliberately shaped as *tools*: each has a typed input model and a plain description,
and `anthropic_tool_definitions()` turns them into Claude tool definitions. Today the assistant chooses
the look-up itself from the question's key words (no AI, no cost); once an Anthropic key is configured,
the same look-ups can be handed to Claude unchanged.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.studies.models import Risk, Study, Task
from app.studies.rules import (
    DUE_SOON_DAYS,
    MAJOR_SLIP_DAYS,
    TASK_CLOSED,
    MilestoneState,
    RiskStatus,
    ScheduleState,
    enrolment_percent,
    milestone_state,
    risk_rating,
    risk_score,
    schedule_state,
    task_overdue,
    total_enrolled,
    variance_days,
)

PRIVACY_NOTE = "Study-level data only: no patient-level data is read."


@dataclass
class StudyData:
    """Everything the look-ups need, loaded once per question."""

    studies: list[Study]
    tasks: list[Task]
    risks: list[Risk]
    today: date
    as_of: datetime | None
    sandbox_only: bool
    by_id: dict[str, Study] = field(init=False)

    def __post_init__(self) -> None:
        self.by_id = {s.id: s for s in self.studies}

    def pick(self, study_ids: list[str] | None) -> list[Study]:
        if not study_ids:
            return self.studies
        return [self.by_id[i] for i in study_ids if i in self.by_id]


def load_study_data(
    db: Session, tenant_id: str, source: str, today: date, as_of: datetime | None
) -> StudyData:
    studies = list(
        db.scalars(
            select(Study)
            .where(Study.tenant_id == tenant_id, Study.source == source, Study.in_source.is_(True))
            .options(selectinload(Study.sites), selectinload(Study.milestones))
            .order_by(Study.protocol_number)
        )
    )
    ids = [s.id for s in studies]
    tasks = list(
        db.scalars(
            select(Task)
            .where(Task.tenant_id == tenant_id, Task.study_id.in_(ids))
            .options(selectinload(Task.assignees))
        )
    )
    risks = list(db.scalars(select(Risk).where(Risk.tenant_id == tenant_id, Risk.study_id.in_(ids))))
    return StudyData(
        studies=studies,
        tasks=tasks,
        risks=risks,
        today=today,
        as_of=as_of,
        sandbox_only=bool(studies) and all(s.sandbox for s in studies),
    )


# ---- outputs -----------------------------------------------------------------------------------


class PlanItem(BaseModel):
    study_id: str
    protocol_number: str
    phase: str | None
    name: str
    kind: str
    is_key: bool
    original_end: date | None
    current_end: date | None
    slip_days: int | None
    percent_complete: int | None
    state: MilestoneState
    schedule: ScheduleState
    days_from_today: int | None
    """Current end date minus today (negative: that many days ago)."""


class StudyStatus(BaseModel):
    study_id: str
    protocol_number: str
    title: str
    status: str | None
    phase: str | None
    sandbox: bool
    on_plan: bool
    key_overdue: int
    key_slipped_major: int
    next_key_milestone: PlanItem | None
    key_milestones: list[PlanItem]
    enrolled: int | None
    enrolment_target: int | None
    enrolment_percent: float | None
    sites_total: int
    sites_activated: int
    open_tasks: int
    overdue_tasks: int
    open_risks: int
    high_risks: int


class SiteRow(BaseModel):
    study_id: str
    protocol_number: str
    site_number: str
    name: str
    country: str | None
    status: str | None
    enrolled: int | None
    target: int | None
    percent: float | None
    activated_on: date | None
    planned_activation: date | None
    days_late: int | None


class TaskRow(BaseModel):
    reference: str
    protocol_number: str
    title: str
    status: str
    due_date: date | None
    overdue: bool
    people: list[str]


class RiskRow(BaseModel):
    reference: str
    protocol_number: str
    kind: str
    title: str
    score: int
    rating: str
    owner: str
    status: str


# ---- look-ups ----------------------------------------------------------------------------------


def _plan(study: Study, today: date) -> list[PlanItem]:
    rows = []
    for m in study.milestones:
        if m.kind == "phase":
            continue
        rows.append(
            PlanItem(
                study_id=study.id,
                protocol_number=study.protocol_number,
                phase=m.phase,
                name=m.name,
                kind=m.kind,
                is_key=m.is_key,
                original_end=m.baseline_date,
                current_end=m.planned_date,
                slip_days=variance_days(m.planned_date, m.baseline_date),
                percent_complete=m.percent_complete,
                state=milestone_state(m.planned_date, m.actual_date, today, m.percent_complete, m.start_date),
                schedule=schedule_state(m.planned_date, m.baseline_date),
                days_from_today=(m.planned_date - today).days if m.planned_date else None,
            )
        )
    return rows


def study_status(data: StudyData, study: Study) -> StudyStatus:
    plan = _plan(study, data.today)
    key = [p for p in plan if p.is_key and p.kind == "milestone"]
    pending = [p for p in key if p.state != MilestoneState.COMPLETED]
    overdue = sum(p.state == MilestoneState.OVERDUE for p in key)
    slipped = sum(p.schedule == ScheduleState.SLIPPED_MAJOR for p in pending)
    enrolled = (
        study.enrolled if study.enrolled is not None else total_enrolled([s.enrolled for s in study.sites])
    )
    tasks = [t for t in data.tasks if t.study_id == study.id and t.status not in TASK_CLOSED]
    risks = [r for r in data.risks if r.study_id == study.id and r.status != RiskStatus.CLOSED]
    return StudyStatus(
        study_id=study.id,
        protocol_number=study.protocol_number,
        title=study.title,
        status=study.status,
        phase=study.phase,
        sandbox=study.sandbox,
        on_plan=not overdue and not slipped,
        key_overdue=overdue,
        key_slipped_major=slipped,
        # The next one still ahead; overdue ones are counted in key_overdue.
        next_key_milestone=min(
            (p for p in pending if p.current_end and p.current_end >= data.today),
            key=lambda p: p.current_end or date.max,
            default=None,
        ),
        key_milestones=key,
        enrolled=enrolled,
        enrolment_target=study.enrolment_target,
        enrolment_percent=enrolment_percent(enrolled, study.enrolment_target),
        sites_total=len(study.sites),
        sites_activated=sum(1 for s in study.sites if s.activation_date),
        open_tasks=len(tasks),
        overdue_tasks=sum(task_overdue(t.due_date, t.status, data.today) for t in tasks),
        open_risks=len(risks),
        high_risks=sum(risk_rating(risk_score(r.likelihood, r.impact)) == "High" for r in risks),
    )


class StudiesInput(BaseModel):
    study_ids: list[str] | None = Field(
        default=None, description="Study ids to include; omit for every study the user can see."
    )


def studies_overview(data: StudyData, params: StudiesInput) -> list[StudyStatus]:
    return [study_status(data, s) for s in data.pick(params.study_ids)]


class PlanInput(BaseModel):
    study_ids: list[str] | None = Field(default=None, description="Studies to search; omit for all.")
    phase_words: list[str] | None = Field(
        default=None, description='Keep entries whose phase contains any of these words, e.g. ["close"].'
    )
    name_words: list[str] | None = Field(
        default=None,
        description='Keep entries whose name contains any of these words, e.g. ["database lock"].',
    )
    states: list[MilestoneState] | None = Field(default=None, description="Keep only these progress states.")
    due_within_days: int | None = Field(
        default=None, ge=0, le=3650, description="Keep entries due between today and this many days ahead."
    )
    include_overdue: bool = Field(
        default=True, description="With due_within_days, also keep overdue entries."
    )
    include_completed: bool = Field(default=False, description="Also return completed entries.")
    key_only: bool = Field(default=False, description="Only key milestones.")


def plan_items(data: StudyData, params: PlanInput) -> list[PlanItem]:
    phase_words = [w.lower() for w in params.phase_words or []]
    name_words = [w.lower() for w in params.name_words or []]
    rows: list[PlanItem] = []
    for study in data.pick(params.study_ids):
        for p in _plan(study, data.today):
            if params.key_only and not p.is_key:
                continue
            if not params.include_completed and p.state == MilestoneState.COMPLETED:
                continue
            if params.states and p.state not in params.states:
                continue
            phase_hit = any(w in (p.phase or "").lower() for w in phase_words)
            name_hit = any(w in p.name.lower() for w in name_words)
            if (phase_words or name_words) and not (phase_hit or name_hit):
                continue
            if params.due_within_days is not None:
                overdue = p.state == MilestoneState.OVERDUE
                in_window = p.days_from_today is not None and 0 <= p.days_from_today <= params.due_within_days
                if not (in_window or (params.include_overdue and overdue)):
                    continue
            rows.append(p)
    rows.sort(key=lambda p: (p.current_end or date.max, p.protocol_number, p.name))
    return rows


class SitesInput(BaseModel):
    study_ids: list[str] | None = Field(default=None, description="Studies to include; omit for all.")
    site_numbers: list[str] | None = Field(default=None, description='Only these sites, e.g. ["102"].')


def sites(data: StudyData, params: SitesInput) -> list[SiteRow]:
    rows = []
    wanted = {n.lower() for n in params.site_numbers or []}
    for study in data.pick(params.study_ids):
        for s in study.sites:
            if wanted and s.site_number.lower() not in wanted:
                continue
            target = s.activation_target
            late = (
                (data.today - target).days
                if not s.activation_date and target and target < data.today
                else None
            )
            rows.append(
                SiteRow(
                    study_id=study.id,
                    protocol_number=study.protocol_number,
                    site_number=s.site_number,
                    name=s.name,
                    country=s.country,
                    status=s.status,
                    enrolled=s.enrolled,
                    target=s.enrolment_target,
                    percent=enrolment_percent(s.enrolled, s.enrolment_target),
                    activated_on=s.activation_date,
                    planned_activation=target,
                    days_late=late,
                )
            )
    return rows


class WorkInput(BaseModel):
    study_ids: list[str] | None = Field(default=None, description="Studies to include; omit for all.")
    overdue_only: bool = Field(default=False, description="Tasks only: keep overdue tasks.")


def open_tasks(data: StudyData, params: WorkInput) -> list[TaskRow]:
    ids = {s.id for s in data.pick(params.study_ids)}
    rows = []
    for t in data.tasks:
        if t.study_id not in ids or t.status in TASK_CLOSED:
            continue
        overdue = task_overdue(t.due_date, t.status, data.today)
        if params.overdue_only and not overdue:
            continue
        rows.append(
            TaskRow(
                reference=t.reference,
                protocol_number=data.by_id[t.study_id].protocol_number if t.study_id else "",
                title=t.title,
                status=t.status,
                due_date=t.due_date,
                overdue=overdue,
                people=[a.person_name for a in t.assignees if a.status != "Completed"],
            )
        )
    rows.sort(key=lambda r: (not r.overdue, r.due_date or date.max, r.reference))
    return rows


def open_risks(data: StudyData, params: WorkInput) -> list[RiskRow]:
    ids = {s.id for s in data.pick(params.study_ids)}
    rows = [
        RiskRow(
            reference=r.reference,
            protocol_number=data.by_id[r.study_id].protocol_number,
            kind=r.kind,
            title=r.title,
            score=risk_score(r.likelihood, r.impact),
            rating=risk_rating(risk_score(r.likelihood, r.impact)),
            owner=r.owner_name,
            status=r.status,
        )
        for r in data.risks
        if r.study_id in ids and r.status != RiskStatus.CLOSED
    ]
    rows.sort(key=lambda r: (-r.score, r.reference))
    return rows


# ---- tool registry (for a future Claude integration) ------------------------------------------


@dataclass(frozen=True)
class StudyTool:
    name: str
    description: str
    input_model: type[BaseModel]
    run: Callable[[StudyData, Any], Any]


TOOLS: list[StudyTool] = [
    StudyTool(
        "studies_overview",
        "Status of each study: on plan or not, overdue and slipped key milestones, next key milestone, "
        "enrolment against target, site activation, open tasks and risks.",
        StudiesInput,
        studies_overview,
    ),
    StudyTool(
        "plan_items",
        "Entries of the SimpleTrials study plan (tasks and milestones) with original and current end dates, "
        f"slip and status. Due soon = within {DUE_SOON_DAYS} days; slipped more than {MAJOR_SLIP_DAYS} days "
        "is a major slip. Filter by phase or name words, status or a due window.",
        PlanInput,
        plan_items,
    ),
    StudyTool(
        "sites",
        "Each site's enrolment against target and its activation (actual or planned date, days late).",
        SitesInput,
        sites,
    ),
    StudyTool("open_tasks", "Open Avi.Intelligence tasks for studies, overdue first.", WorkInput, open_tasks),
    StudyTool("open_risks", "Open risks and issues for studies, highest score first.", WorkInput, open_risks),
]


def anthropic_tool_definitions() -> list[dict[str, Any]]:
    """The look-ups as Claude tool definitions (name, description, JSON input schema)."""
    return [
        {"name": t.name, "description": t.description, "input_schema": t.input_model.model_json_schema()}
        for t in TOOLS
    ]


def run_tool(data: StudyData, name: str, arguments: dict[str, Any]) -> Any:
    tool = next(t for t in TOOLS if t.name == name)
    return tool.run(data, tool.input_model.model_validate(arguments))
