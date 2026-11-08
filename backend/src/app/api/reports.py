"""Reports and Insights endpoints (read-only)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.studies import current_source_label, study_source
from app.audit.service import record_event
from app.auth.rbac import CurrentUser, Permission, require
from app.connectors.simpletrials import get_study_connector
from app.connectors.simpletrials.models import StudyConnector
from app.db.session import get_db
from app.reports.excel import Sheet, build_workbook
from app.reports.history import snapshot_days
from app.reports.models import MilestoneCompletion
from app.reports.study_delivery import StudyDelivery, build_study_delivery
from app.studies.clock import today
from app.studies.models import Study
from app.studies.rules import MilestoneState, ScheduleState
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
