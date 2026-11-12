"""Study Portfolio and Study Command Centre endpoints (read-only copy of SimpleTrials data)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.audit.service import record_event
from app.auth.rbac import CurrentUser, Permission, require
from app.connectors.simpletrials import get_study_connector
from app.connectors.simpletrials.models import StudyConnector, StudyConnectorInfo
from app.db.session import get_db
from app.studies.clock import today
from app.studies.models import ConnectorSync, Risk, Study, Task
from app.studies.rules import (
    RULES,
    TASK_CLOSED,
    MilestoneState,
    RiskStatus,
    ScheduleState,
    enrolment_percent,
    milestone_state,
    schedule_state,
    total_enrolled,
    variance_days,
)
from app.studies.sync import CONNECTOR_NAME, ensure_synced, last_sync, sync_studies

router = APIRouter(tags=["Studies"])

StudyId = Annotated[str, Path(pattern=r"^[0-9a-f\-]{36}$")]
Connector = Annotated[StudyConnector, Depends(get_study_connector)]
Db = Annotated[Session, Depends(get_db)]


class SyncInfo(BaseModel):
    started_at: datetime
    finished_at: datetime | None
    ok: bool
    mode: str
    counts: dict[str, int]
    error: str | None
    triggered_by: str


class StudySource(BaseModel):
    connector: StudyConnectorInfo
    last_sync: SyncInfo | None
    last_successful_sync_at: datetime | None


class MilestoneOut(BaseModel):
    """One entry of the study plan (phase, task or milestone), in SimpleTrials order."""

    id: str
    external_id: str
    parent_external_id: str | None
    kind: str
    is_key: bool
    name: str
    phase: str | None
    start_date: date | None
    """Current start date."""
    baseline_start_date: date | None
    """Original start date."""
    start_variance_days: int | None
    """Current start minus original start, in days (positive = later)."""
    planned_date: date | None
    """Current end date."""
    actual_date: date | None
    baseline_date: date | None
    """Original end date."""
    percent_complete: int | None
    variance_days: int | None
    state: MilestoneState
    """Progress status (against the current end date)."""
    schedule: ScheduleState
    """Schedule status (current vs original end date)."""


class SiteOut(BaseModel):
    id: str
    site_number: str
    name: str
    country: str | None
    principal_investigator: str | None
    status: str | None
    activation_date: date | None
    activation_target: date | None = None
    enrolled: int | None
    enrolment_target: int | None
    enrolment_percent: float | None


class StudySummary(BaseModel):
    id: str
    protocol_number: str
    title: str
    sponsor: str | None
    phase: str | None
    therapeutic_area: str | None
    status: str | None
    countries: list[str]
    project_manager: str | None
    in_source: bool
    sandbox: bool
    synced_at: datetime
    site_count: int
    enrolled: int | None
    enrolment_target: int | None
    enrolment_percent: float | None
    overdue_milestones: int
    next_milestone: MilestoneOut | None
    open_tasks: int
    open_risks: int


class StudyListResponse(BaseModel):
    studies: list[StudySummary]
    total_unfiltered: int
    statuses: list[str]
    phases: list[str]
    source: StudySource
    rules: dict[str, str]


class StudyDetailResponse(BaseModel):
    study: StudySummary
    sites: list[SiteOut]
    milestones: list[MilestoneOut]
    source: StudySource
    rules: dict[str, str]


def _sync_info(run: ConnectorSync | None) -> SyncInfo | None:
    if run is None:
        return None
    return SyncInfo(
        started_at=run.started_at,
        finished_at=run.finished_at,
        ok=run.ok,
        mode=run.mode,
        counts=run.counts or {},
        error=run.error,
        triggered_by=run.triggered_by,
    )


def study_source(db: Session, connector: StudyConnector, tenant_id: str) -> StudySource:
    mode = connector.info().mode
    ok_run = last_sync(db, tenant_id, successful_only=True, mode=mode)
    return StudySource(
        connector=connector.info(),
        last_sync=_sync_info(last_sync(db, tenant_id, mode=mode)),
        last_successful_sync_at=ok_run.finished_at if ok_run else None,
    )


def current_source_label(connector: StudyConnector) -> str:
    return "demo" if connector.info().mode == "mock" else CONNECTOR_NAME


def _milestones(study: Study, now: date) -> list[MilestoneOut]:
    return [
        MilestoneOut(
            id=m.id,
            external_id=m.external_id,
            parent_external_id=m.parent_external_id,
            kind=m.kind,
            is_key=m.is_key,
            name=m.name,
            phase=m.phase,
            start_date=m.start_date,
            baseline_start_date=m.baseline_start_date,
            start_variance_days=variance_days(m.start_date, m.baseline_start_date),
            planned_date=m.planned_date,
            actual_date=m.actual_date,
            baseline_date=m.baseline_date,
            percent_complete=m.percent_complete,
            variance_days=variance_days(m.planned_date, m.baseline_date),
            state=milestone_state(m.planned_date, m.actual_date, now, m.percent_complete, m.start_date),
            schedule=schedule_state(m.planned_date, m.baseline_date),
        )
        for m in study.milestones
    ]


def _open_counts(db: Session, tenant_id: str) -> tuple[dict[str, int], dict[str, int]]:
    # Only study tasks count towards a study (SOP, vendor, system and general tasks have none).
    tasks = {
        study_id: count
        for study_id, count in db.execute(
            select(Task.study_id, func.count())
            .where(
                Task.tenant_id == tenant_id,
                Task.study_id.is_not(None),
                Task.status.not_in([s.value for s in TASK_CLOSED]),
            )
            .group_by(Task.study_id)
        ).all()
        if study_id
    }
    risks = dict(
        db.execute(
            select(Risk.study_id, func.count())
            .where(Risk.tenant_id == tenant_id, Risk.status != RiskStatus.CLOSED.value)
            .group_by(Risk.study_id)
        ).all()
    )
    return tasks, risks


def summarise(study: Study, now: date, open_tasks: int, open_risks: int) -> StudySummary:
    # Headline figures use key milestones only, so a late minor task does not flag the whole study.
    milestones = [m for m in _milestones(study, now) if m.is_key and m.kind == "milestone"]
    pending = [m for m in milestones if m.state != MilestoneState.COMPLETED and m.planned_date]
    # Prefer the study-level count reported by SimpleTrials; otherwise sum what the sites report.
    enrolled = (
        study.enrolled if study.enrolled is not None else total_enrolled([s.enrolled for s in study.sites])
    )
    return StudySummary(
        id=study.id,
        protocol_number=study.protocol_number,
        title=study.title,
        sponsor=study.sponsor,
        phase=study.phase,
        therapeutic_area=study.therapeutic_area,
        status=study.status,
        countries=study.countries or [],
        project_manager=study.project_manager,
        in_source=study.in_source,
        sandbox=study.sandbox,
        synced_at=study.synced_at,
        site_count=len(study.sites),
        enrolled=enrolled,
        enrolment_target=study.enrolment_target,
        enrolment_percent=enrolment_percent(enrolled, study.enrolment_target),
        overdue_milestones=sum(m.state == MilestoneState.OVERDUE for m in milestones),
        next_milestone=min(pending, key=lambda m: m.planned_date or date.max, default=None),
        open_tasks=open_tasks,
        open_risks=open_risks,
    )


def _load_studies(db: Session, tenant_id: str, source: str) -> list[Study]:
    return list(
        db.scalars(
            select(Study)
            .where(Study.tenant_id == tenant_id, Study.source == source)
            .options(selectinload(Study.sites), selectinload(Study.milestones))
            .order_by(Study.protocol_number)
        )
    )


@router.get("/studies", response_model=StudyListResponse)
async def list_studies(
    db: Db,
    connector: Connector,
    user: Annotated[CurrentUser, Depends(require(Permission.STUDY_READ))],
    q: Annotated[str | None, Query(max_length=200)] = None,
    status: Annotated[str | None, Query(max_length=64)] = None,
    phase: Annotated[str | None, Query(max_length=32)] = None,
) -> StudyListResponse:
    await ensure_synced(db, connector, user.tenant_id)
    studies = _load_studies(db, user.tenant_id, current_source_label(connector))
    tasks, risks = _open_counts(db, user.tenant_id)
    now = today()
    terms = [t for t in (q or "").lower().split() if t]
    result = []
    for s in studies:
        if status and (s.status or "").lower() != status.lower():
            continue
        if phase and (s.phase or "").lower() != phase.lower():
            continue
        haystack = " ".join(
            filter(None, [s.protocol_number, s.title, s.sponsor, s.therapeutic_area, s.project_manager])
        ).lower()
        if all(t in haystack for t in terms):
            result.append(summarise(s, now, tasks.get(s.id, 0), risks.get(s.id, 0)))
    return StudyListResponse(
        studies=result,
        total_unfiltered=len(studies),
        statuses=sorted({s.status for s in studies if s.status}),
        phases=sorted({s.phase for s in studies if s.phase}),
        source=study_source(db, connector, user.tenant_id),
        rules=RULES,
    )


def get_study_or_404(db: Session, tenant_id: str, study_id: str) -> Study:
    study = db.scalars(
        select(Study)
        .where(Study.tenant_id == tenant_id, Study.id == study_id)
        .options(selectinload(Study.sites), selectinload(Study.milestones))
    ).first()
    if study is None:
        raise HTTPException(404, "Study not found.")
    return study


@router.get("/studies/{study_id}", response_model=StudyDetailResponse)
async def get_study(
    study_id: StudyId,
    db: Db,
    connector: Connector,
    user: Annotated[CurrentUser, Depends(require(Permission.STUDY_READ))],
) -> StudyDetailResponse:
    study = get_study_or_404(db, user.tenant_id, study_id)
    tasks, risks = _open_counts(db, user.tenant_id)
    now = today()
    return StudyDetailResponse(
        study=summarise(study, now, tasks.get(study.id, 0), risks.get(study.id, 0)),
        sites=[
            SiteOut(
                id=s.id,
                site_number=s.site_number,
                name=s.name,
                country=s.country,
                principal_investigator=s.principal_investigator,
                status=s.status,
                activation_date=s.activation_date,
                activation_target=s.activation_target,
                enrolled=s.enrolled,
                enrolment_target=s.enrolment_target,
                enrolment_percent=enrolment_percent(s.enrolled, s.enrolment_target),
            )
            for s in study.sites
        ],
        milestones=_milestones(study, now),
        source=study_source(db, connector, user.tenant_id),
        rules=RULES,
    )


@router.get("/connectors/simpletrials", response_model=StudySource, tags=["Administration"])
def simpletrials_status(
    db: Db,
    connector: Connector,
    user: Annotated[CurrentUser, Depends(require(Permission.CONNECTOR_MANAGE))],
) -> StudySource:
    return study_source(db, connector, user.tenant_id)


@router.post("/connectors/simpletrials/sync", response_model=StudySource, tags=["Administration"])
async def simpletrials_sync(
    request: Request,
    db: Db,
    connector: Connector,
    user: Annotated[CurrentUser, Depends(require(Permission.CONNECTOR_MANAGE))],
) -> StudySource:
    run = await sync_studies(db, connector, tenant_id=user.tenant_id, triggered_by=user.name)
    record_event(
        db,
        user,
        action="connector.synced",
        entity_type="connector",
        entity_id=CONNECTOR_NAME,
        summary=f"Synced studies from SimpleTrials ({'succeeded' if run.ok else 'failed'})",
        details={"mode": run.mode, "ok": run.ok, "counts": run.counts, "error": run.error},
        request=request,
    )
    return study_source(db, connector, user.tenant_id)


SYNC_REUSE = timedelta(minutes=2)
"""A press of Sync now this soon after a successful sync reuses it instead of asking SimpleTrials again."""
_SYNCING: set[str] = set()
"""Tenants with a SimpleTrials sync running now."""


def _aware(at: datetime) -> datetime:
    return at if at.tzinfo else at.replace(tzinfo=UTC)


@router.post("/studies/sync", response_model=StudySource)
async def studies_sync(
    request: Request,
    db: Db,
    connector: Connector,
    user: Annotated[CurrentUser, Depends(require(Permission.STUDY_SYNC))],
) -> StudySource:
    """Sync now for everyone (read-only towards SimpleTrials); one at a time, recent syncs reused."""
    if user.tenant_id in _SYNCING:
        raise HTTPException(409, "A SimpleTrials sync is already running. Try again in a minute.")
    mode = connector.info().mode
    recent = last_sync(db, user.tenant_id, successful_only=True, mode=mode)
    if recent and recent.finished_at and datetime.now(UTC) - _aware(recent.finished_at) < SYNC_REUSE:
        return study_source(db, connector, user.tenant_id)
    _SYNCING.add(user.tenant_id)
    try:
        run = await sync_studies(db, connector, tenant_id=user.tenant_id, triggered_by=user.name)
    finally:
        _SYNCING.discard(user.tenant_id)
    record_event(
        db,
        user,
        action="connector.synced",
        entity_type="connector",
        entity_id=CONNECTOR_NAME,
        summary=f"Synced studies from SimpleTrials ({'succeeded' if run.ok else 'failed'})",
        details={"mode": run.mode, "ok": run.ok, "counts": run.counts, "error": run.error},
        request=request,
    )
    return study_source(db, connector, user.tenant_id)
