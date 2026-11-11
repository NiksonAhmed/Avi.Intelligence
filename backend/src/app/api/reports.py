"""Reports and Insights endpoints (read-only)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.api.sops import SopSource, _with_details
from app.api.sops import _source as sop_source
from app.api.studies import current_source_label, study_source
from app.audit.service import record_event
from app.auth.rbac import CurrentUser, Permission, require
from app.connectors.sharepoint import get_sop_connector
from app.connectors.sharepoint.models import SopConnector
from app.connectors.simpletrials import get_study_connector
from app.connectors.simpletrials.models import StudyConnector
from app.db.session import get_db
from app.reports.etmf import Etmf, build_etmf
from app.reports.excel import Sheet, build_workbook
from app.reports.history import snapshot_days
from app.reports.models import MilestoneCompletion
from app.reports.quality import REVIEW_WINDOW_DAYS, Quality, build_quality
from app.reports.study_delivery import StudyDelivery, build_study_delivery
from app.reports.work_management import DUE_SOON_DAYS, WorkManagement, build_work_management, level
from app.studies.clock import today
from app.studies.models import Risk, Study, Task, TaskDocument
from app.studies.rules import TASK_CATEGORY_LABELS, TASK_CLOSED, MilestoneState, ScheduleState, TaskCategory
from app.studies.sync import ensure_synced

router = APIRouter(prefix="/reports", tags=["Reports"])

Connector = Annotated[StudyConnector, Depends(get_study_connector)]
Db = Annotated[Session, Depends(get_db)]
Reader = Annotated[CurrentUser, Depends(require(Permission.STUDY_READ))]
IdParam = Annotated[str | None, Query(pattern=r"^[0-9a-f\-]{36}$")]


class ReportSource(BaseModel):
    mode: str
    """"api" (SimpleTrials) or "mock" (demo data)."""
    as_of: datetime | None
    """When the data was last copied from SimpleTrials (last successful sync)."""
    sandbox_only: bool
    snapshot_days: int
    """Days of history kept so far (trend charts need a few weeks)."""


class StudyDeliveryResponse(StudyDelivery):
    source: ReportSource


def _studies(db: Session, tenant_id: str, source: str) -> list[Study]:
    return list(
        db.scalars(
            select(Study)
            .where(Study.tenant_id == tenant_id, Study.source == source, Study.in_source.is_(True))
            .options(selectinload(Study.sites), selectinload(Study.milestones))
            .order_by(Study.protocol_number)
        )
    )


async def _study_delivery(
    db: Session, connector: StudyConnector, user: CurrentUser, study_id: str | None, site_id: str | None
) -> StudyDeliveryResponse:
    await ensure_synced(db, connector, user.tenant_id)
    source = current_source_label(connector)
    studies = _studies(db, user.tenant_id, source)
    completions = list(
        db.scalars(select(MilestoneCompletion).where(MilestoneCompletion.tenant_id == user.tenant_id))
    )
    report = build_study_delivery(studies, completions, today(), study_id=study_id, site_id=site_id)
    info = study_source(db, connector, user.tenant_id)
    return StudyDeliveryResponse(
        **report.model_dump(),
        source=ReportSource(
            mode=info.connector.mode,
            as_of=info.last_successful_sync_at,
            sandbox_only=bool(studies) and all(s.sandbox for s in studies),
            snapshot_days=snapshot_days(db, user.tenant_id, source),
        ),
    )


@router.get("/study-delivery", response_model=StudyDeliveryResponse)
async def study_delivery(
    db: Db, connector: Connector, user: Reader, study_id: IdParam = None, site_id: IdParam = None
) -> StudyDeliveryResponse:
    return await _study_delivery(db, connector, user, study_id, site_id)


_STATE_LABEL = {
    MilestoneState.COMPLETED: "Completed",
    MilestoneState.OVERDUE: "Overdue",
    MilestoneState.DUE_SOON: "Due soon",
    MilestoneState.IN_PROGRESS: "In progress",
    MilestoneState.NOT_STARTED: "Not started",
    MilestoneState.UPCOMING: "Upcoming",
    MilestoneState.NOT_PLANNED: "No end date",
}
_SCHEDULE_LABEL = {
    ScheduleState.ON_PLAN: "On plan",
    ScheduleState.SLIPPED: "Slipped",
    ScheduleState.SLIPPED_MAJOR: "Slipped more than 30 days",
    ScheduleState.AHEAD: "Ahead",
    ScheduleState.NO_BASELINE: "No original date",
}


@router.get("/study-delivery/export.xlsx")
async def study_delivery_export(
    request: Request,
    db: Db,
    connector: Connector,
    user: Reader,
    study_id: IdParam = None,
    site_id: IdParam = None,
) -> Response:
    r = await _study_delivery(db, connector, user, study_id, site_id)
    sheets = [
        Sheet(
            "Key milestones",
            [
                "Study",
                "Milestone",
                "Original end",
                "Current end",
                "Slip (days)",
                "Progress",
                "Schedule",
                "Completed on",
                "Completion date basis",
                "On time",
            ],
            [
                [
                    m.protocol_number,
                    m.name,
                    m.original_date,
                    m.current_date,
                    m.variance_days,
                    _STATE_LABEL[m.state],
                    _SCHEDULE_LABEL[m.schedule],
                    m.completed_on,
                    {
                        "first-seen": "First seen complete by Avi.Intelligence",
                        "before-tracking": "Completed before tracking began (date unknown)",
                        "actual": "SimpleTrials actual date",
                    }.get(m.completion_basis or "", ""),
                    m.on_time,
                ]
                for m in r.milestones
            ],
        ),
        Sheet(
            "Enrolment by site",
            ["Study", "Site", "Name", "Country", "Enrolled", "Target", "% of target", "Note"],
            [
                [
                    s.protocol_number,
                    s.site_number,
                    s.name,
                    s.country,
                    s.enrolled,
                    s.target,
                    s.percent,
                    {
                        "zero": "None enrolled",
                        "no_target": "No target recorded",
                        "over_target": "Above target",
                    }.get(s.flag, ""),
                ]
                for s in r.sites
            ],
        ),
        Sheet(
            "Sites not yet activated",
            ["Study", "Site", "Name", "Status", "Planned activation", "Days late", "State"],
            [
                [
                    p.protocol_number,
                    p.site_number,
                    p.name,
                    p.status,
                    p.planned_date,
                    p.days_late,
                    {
                        "late": "Late",
                        "due_soon": "Due soon",
                        "upcoming": "Upcoming",
                        "no_date": "No planned date",
                    }[p.state],
                ]
                for p in r.pending_sites
            ],
        ),
    ]
    scope = next((o.label for o in r.study_options if o.id == study_id), "All studies")
    about = [
        ("Report", "Study delivery"),
        (
            "Scope",
            scope
            + (
                f" · site {next((o.label for o in r.site_options if o.id == site_id), '')}" if site_id else ""
            ),
        ),
        ("Data as of", r.source.as_of.strftime("%d %b %Y %H:%M UTC") if r.source.as_of else "Not yet synced"),
        (
            "Source",
            "SimpleTrials (read-only copy)"
            if r.source.mode == "api"
            else "Demo data (SimpleTrials not connected)",
        ),
        ("Exported by", f"{user.name} on {datetime.now().strftime('%d %b %Y %H:%M')}"),
        *[
            (key.replace("_", " ").capitalize(), text)
            for key, text in r.rules.items()
            if key in ("study_on_plan", "on_time", "enrolment", "activation", "schedule_slipped")
        ],
    ]
    content = build_workbook(sheets, about)
    record_event(
        db,
        user,
        action="report.exported",
        entity_type="report",
        entity_id="study-delivery",
        summary=f"Exported Study delivery report to Excel ({scope})",
        details={"format": "xlsx", "study_id": study_id, "site_id": site_id},
        request=request,
    )
    name = f"Study delivery {datetime.now().strftime('%Y-%m-%d')}.xlsx"
    return Response(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"},
    )


# --- Work management ---


class WorkManagementResponse(WorkManagement):
    source: ReportSource


async def _work_management(
    db: Session,
    connector: StudyConnector,
    user: CurrentUser,
    study_id: str | None,
    category: TaskCategory | None,
) -> WorkManagementResponse:
    await ensure_synced(db, connector, user.tenant_id)
    source = current_source_label(connector)
    studies = _studies(db, user.tenant_id, source)
    tasks = list(
        db.scalars(
            select(Task)
            .where(Task.tenant_id == user.tenant_id)
            .options(joinedload(Task.study), selectinload(Task.documents), selectinload(Task.assignees))
        ).unique()
    )
    risks = list(
        db.scalars(
            select(Risk).where(Risk.tenant_id == user.tenant_id).options(joinedload(Risk.study))
        ).unique()
    )
    report = build_work_management(tasks, risks, studies, today(), study_id=study_id, category=category)
    info = study_source(db, connector, user.tenant_id)
    return WorkManagementResponse(
        **report.model_dump(),
        source=ReportSource(
            mode=info.connector.mode,
            as_of=datetime.now(UTC),
            sandbox_only=bool(studies) and all(s.sandbox for s in studies),
            snapshot_days=0,
        ),
    )


@router.get("/work-management", response_model=WorkManagementResponse)
async def work_management(
    db: Db,
    connector: Connector,
    user: Reader,
    study_id: IdParam = None,
    category: TaskCategory | None = None,
) -> WorkManagementResponse:
    return await _work_management(db, connector, user, study_id, category)


@router.get("/work-management/export.xlsx")
async def work_management_export(
    request: Request,
    db: Db,
    connector: Connector,
    user: Reader,
    study_id: IdParam = None,
    category: TaskCategory | None = None,
) -> Response:
    r = await _work_management(db, connector, user, study_id, category)
    sheets = [
        Sheet(
            "Open tasks",
            ["Task", "Category", "About", "Title", "People (their status)", "Status", "Due", "Days overdue"],
            [
                [
                    t.reference,
                    t.category_label,
                    t.about,
                    t.title,
                    t.people,
                    t.status,
                    t.due_date,
                    t.days_overdue,
                ]
                for t in r.open_tasks
            ],
        ),
        Sheet(
            "By person",
            ["Person", "Open parts", "Overdue", f"Due in {DUE_SOON_DAYS} days", "Blocked"],
            [[p.name, p.open, p.overdue, p.due_soon, p.blocked] for p in r.by_person],
        ),
        Sheet(
            "By category",
            ["Category", "Open", "Not started", "In progress", "Blocked", "Overdue"],
            [[c.label, c.total, c.not_started, c.in_progress, c.blocked, c.overdue] for c in r.by_category],
        ),
        Sheet(
            "Open risks and issues",
            [
                "Reference",
                "Type",
                "Study",
                "Title",
                "Likelihood",
                "Impact",
                "Score",
                "Rating",
                "Owner",
                "Status",
            ],
            [
                [
                    x.reference,
                    "Issue" if x.kind == "issue" else "Risk",
                    x.protocol_number,
                    x.title,
                    level(x.likelihood),
                    level(x.impact),
                    x.score,
                    x.rating,
                    x.owner_name,
                    x.status,
                ]
                for x in r.top_risks
            ],
        ),
    ]
    scope = next((o.label for o in r.study_options if o.id == study_id), "All studies")
    if category:
        scope += f" · {TASK_CATEGORY_LABELS[category]} tasks"
    about = [
        ("Report", "Work management"),
        ("Scope", scope),
        ("Data as of", datetime.now(UTC).strftime("%d %b %Y %H:%M UTC")),
        ("Source", "Avi.Intelligence tasks, risks and issues"),
        ("Exported by", f"{user.name} on {datetime.now().strftime('%d %b %Y %H:%M')}"),
        *[(key.replace("_", " ").capitalize(), text) for key, text in r.rules.items()],
    ]
    content = build_workbook(sheets, about)
    record_event(
        db,
        user,
        action="report.exported",
        entity_type="report",
        entity_id="work-management",
        summary=f"Exported Work management report to Excel ({scope})",
        details={"format": "xlsx", "study_id": study_id, "category": category.value if category else None},
        request=request,
    )
    name = f"Work management {datetime.now().strftime('%Y-%m-%d')}.xlsx"
    return Response(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"},
    )


# --- Quality (SOPs) ---

SopConnectorDep = Annotated[SopConnector, Depends(get_sop_connector)]
SopReader = Annotated[CurrentUser, Depends(require(Permission.SOP_READ))]
Department = Annotated[str | None, Query(max_length=200)]
Months = Annotated[int, Query(ge=1, le=24, description="Change log period: 3, 6, 12 or 24 months")]


class QualityResponse(Quality):
    source: SopSource
    fetched_at: datetime


async def _quality(
    db: Session, connector: SopConnector, user: CurrentUser, department: str | None, months: int
) -> QualityResponse:
    result = await connector.list_sops()
    docs = _with_details(result.documents, db, user, connector.info())
    open_tasks: dict[str, int] = {}
    for doc in db.scalars(
        select(TaskDocument)
        .join(Task)
        .where(
            Task.tenant_id == user.tenant_id,
            Task.category == TaskCategory.SOP.value,
            Task.status.not_in([s.value for s in TASK_CLOSED]),
        )
    ):
        open_tasks[doc.sop_id] = open_tasks.get(doc.sop_id, 0) + 1
    report = build_quality(docs, open_tasks, today(), department=department, months=months)
    return QualityResponse(
        **report.model_dump(), source=sop_source(connector.info()), fetched_at=result.fetched_at
    )


@router.get("/quality", response_model=QualityResponse)
async def quality(
    db: Db, connector: SopConnectorDep, user: SopReader, department: Department = None, months: Months = 12
) -> QualityResponse:
    return await _quality(db, connector, user, department, months)


_REVIEW_LABEL = {
    "overdue": "Overdue",
    "due_soon": f"Due within {REVIEW_WINDOW_DAYS} days",
    "scheduled": "Scheduled",
    "no_date": "No review date",
}


@router.get("/quality/export.xlsx")
async def quality_export(
    request: Request,
    db: Db,
    connector: SopConnectorDep,
    user: SopReader,
    department: Department = None,
    months: Months = 12,
) -> Response:
    r = await _quality(db, connector, user, department, months)
    sheets = [
        Sheet(
            "Review schedule",
            [
                "SOP",
                "Title",
                "Version",
                "Department",
                "Owner",
                "Effective",
                "Next review",
                "Days to review",
                "Review status",
                "Forms",
                "Open review tasks",
            ],
            [
                [
                    s.sop_number,
                    s.title,
                    s.version,
                    s.department,
                    s.owner,
                    s.effective_date,
                    s.review_date,
                    s.days_to_review,
                    _REVIEW_LABEL[s.state],
                    s.forms,
                    s.open_tasks,
                ]
                for s in r.schedule
            ],
        ),
        Sheet(
            "Change log",
            ["Document", "Title", "Type", "Version", "Issued", "Changes", "Date from"],
            [
                [
                    c.sop_number,
                    c.title,
                    "Form" if c.kind == "form" else "SOP",
                    c.version,
                    c.issued,
                    c.changes,
                    "Change history" if c.basis == "history" else "Effective date of current version",
                ]
                for c in r.changes
            ],
        ),
        Sheet(
            "Library health",
            ["Finding", "Document"],
            [[c.label, i.label] for c in r.health for i in c.items],
        ),
    ]
    scope = (department or "All departments") + f" · changes in the last {r.months} months"
    about = [
        ("Report", "Quality (SOPs)"),
        ("Scope", scope),
        ("Data as of", r.fetched_at.strftime("%d %b %Y %H:%M UTC")),
        (
            "Source",
            "SharePoint SOP library (approved documents)" if r.source.mode == "live" else "Demo data",
        ),
        ("Exported by", f"{user.name} on {datetime.now().strftime('%d %b %Y %H:%M')}"),
        *[(key.replace("_", " ").capitalize(), text) for key, text in r.rules.items()],
    ]
    content = build_workbook(sheets, about)
    record_event(
        db,
        user,
        action="report.exported",
        entity_type="report",
        entity_id="quality",
        summary=f"Exported Quality (SOPs) report to Excel ({scope})",
        details={"format": "xlsx", "department": department, "months": r.months},
        request=request,
    )
    name = f"Quality SOPs {datetime.now().strftime('%Y-%m-%d')}.xlsx"
    return Response(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"},
    )


# --- eTMF ---


class EtmfResponse(Etmf):
    source: ReportSource


async def _etmf(
    db: Session, connector: StudyConnector, user: CurrentUser, study_id: str | None, site_id: str | None
) -> EtmfResponse:
    await ensure_synced(db, connector, user.tenant_id)
    source = current_source_label(connector)
    studies = list(
        db.scalars(
            select(Study)
            .where(Study.tenant_id == user.tenant_id, Study.source == source, Study.in_source.is_(True))
            .options(selectinload(Study.sites), selectinload(Study.etmf_documents))
            .order_by(Study.protocol_number)
        )
    )
    report = build_etmf(studies, today(), study_id=study_id, site_id=site_id)
    info = study_source(db, connector, user.tenant_id)
    return EtmfResponse(
        **report.model_dump(),
        source=ReportSource(
            mode=info.connector.mode,
            as_of=info.last_successful_sync_at,
            sandbox_only=bool(studies) and all(s.sandbox for s in studies),
            snapshot_days=0,
        ),
    )


@router.get("/etmf", response_model=EtmfResponse)
async def etmf(
    db: Db, connector: Connector, user: Reader, study_id: IdParam = None, site_id: IdParam = None
) -> EtmfResponse:
    return await _etmf(db, connector, user, study_id, site_id)


@router.get("/etmf/export.xlsx")
async def etmf_export(
    request: Request,
    db: Db,
    connector: Connector,
    user: Reader,
    study_id: IdParam = None,
    site_id: IdParam = None,
) -> Response:
    r = await _etmf(db, connector, user, study_id, site_id)
    sheets = [
        Sheet(
            "Missing documents",
            ["Study", "Site", "Section", "Folder", "Document"],
            [[m.protocol_number, m.where, m.section, m.folder, m.name] for m in r.missing_documents],
        ),
        Sheet(
            "Completeness by study",
            ["Study", "Expected", "Filed", "Missing", "% filed"],
            [[c.label, c.expected, c.filed, c.missing, c.percent] for c in r.by_study],
        ),
        Sheet(
            "By site and section",
            ["Study", "Site", *[f"{sec} (filed of expected)" for sec in r.sections]],
            [
                [
                    h.protocol_number,
                    h.label,
                    *[f"{c.filed} of {c.expected}" if c.expected else "" for c in h.cells],
                ]
                for h in r.heat_map
            ],
        ),
        Sheet(
            "Expiring documents",
            ["Study", "Where", "Document", "Expires", "Days", "State"],
            [
                [
                    e.protocol_number,
                    e.where,
                    e.name,
                    e.expires_on,
                    e.days,
                    "Expired" if e.state == "expired" else "Expiring",
                ]
                for e in r.expiring
            ],
        ),
        Sheet(
            "QC and timeliness",
            ["Measure", "Group", "Documents"],
            [["QC status", b.label, b.count] for b in r.qc]
            + [["Filing timeliness", b.label, b.count] for b in r.timeliness],
        ),
    ]
    scope = next((o.label for o in r.study_options if o.id == study_id), "All studies")
    if site_id:
        scope += f" · site {next((o.label for o in r.site_options if o.id == site_id), '')}"
    about = [
        ("Report", "eTMF"),
        ("Scope", scope),
        ("Data as of", r.source.as_of.strftime("%d %b %Y %H:%M UTC") if r.source.as_of else "Not yet synced"),
        (
            "Source",
            "SimpleTrials eTMF document metadata (read-only copy; files are never downloaded)"
            if r.source.mode == "api"
            else "Demo data (SimpleTrials not connected)",
        ),
        ("Exported by", f"{user.name} on {datetime.now().strftime('%d %b %Y %H:%M')}"),
        *[(key.replace("_", " ").capitalize(), text) for key, text in r.rules.items()],
    ]
    content = build_workbook(sheets, about)
    record_event(
        db,
        user,
        action="report.exported",
        entity_type="report",
        entity_id="etmf",
        summary=f"Exported eTMF report to Excel ({scope})",
        details={"format": "xlsx", "study_id": study_id, "site_id": site_id},
        request=request,
    )
    name = f"eTMF {datetime.now().strftime('%Y-%m-%d')}.xlsx"
    return Response(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"},
    )
