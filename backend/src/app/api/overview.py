"""Overview: the role-based home page, and the CRA site assignments it relies on.

Each role sees its own page (user decision 2026-11-13): what needs them today, then the sections that
matter for their job. Every figure is taken from an existing report or module (same rules, same
numbers) and links to the page with the detail. Administrators may preview any role's page. Nothing is
estimated and no AI is used.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.reports import _deviations, _etmf, _quality, _risks_issues, _study_delivery, _work_management
from app.api.studies import current_source_label, study_source
from app.audit.service import record_event
from app.auth.directory import list_people
from app.auth.rbac import ROLE_LABELS, CurrentUser, Permission, Role, require
from app.connectors.sharepoint import get_sop_connector
from app.connectors.sharepoint.models import SopConnector
from app.connectors.simpletrials import get_study_connector
from app.connectors.simpletrials.models import StudyConnector
from app.db.session import get_db
from app.overview import providers
from app.overview.schemas import Attention, Kpi, Overview, Row, Section, SourceInfo, ViewOption
from app.reports.etmf import build_etmf
from app.reports.study_delivery import Tile
from app.reports.work_management import task_about
from app.studies.clock import today
from app.studies.models import SiteAssignment, Study, StudySite, Task, TaskAssignee
from app.studies.rules import TASK_CATEGORY_LABELS, TASK_CLOSED, MilestoneState, TaskCategory, TaskStatus
from app.studies.sync import ensure_synced, last_sync

log = logging.getLogger(__name__)

router = APIRouter(tags=["Overview"])

Connector = Annotated[StudyConnector, Depends(get_study_connector)]
SopConnectorDep = Annotated[SopConnector, Depends(get_sop_connector)]
Db = Annotated[Session, Depends(get_db)]
Reader = Annotated[CurrentUser, Depends(require(Permission.STUDY_READ))]
Manager = Annotated[CurrentUser, Depends(require(Permission.WORK_MANAGE))]

VISIT_WINDOW_DAYS = 14
MILESTONE_WINDOW_DAYS = 30
TASK_SOON_DAYS = 7

PURPOSE: dict[Role, str] = {
    Role.ADMIN: "Everything at a glance, plus the health of the connectors.",
    Role.PROJECT_MANAGER: "How the studies are doing: milestones, risks and issues, deviations and the eTMF.",
    Role.CRA: "Your sites: visits coming up, what to chase, and what to check at the next visit.",
    Role.CTA: "The eTMF: what is missing, what is late to file and what is about to expire.",
    Role.DATA_MANAGER: "Data quality: queries to review, missing data, lab flags and SDV.",
    Role.SAFETY: "Safety signals across studies, and your safety SOPs and tasks.",
    Role.QA: "SOPs due for review, serious deviations, and the tasks you assign.",
    Role.VIEWER: "How the studies are doing (read-only).",
}

# Which sections each role sees, in order. Unknown keys (e.g. a module that is switched off) are skipped.
# "conferences" (Next conferences) comes from the Conferences module when it is on.
LAYOUT: dict[Role, list[str]] = {
    Role.ADMIN: [
        "connectors",
        "studies",
        "risks",
        "deviations",
        "etmf",
        "dm",
        "sops",
        "team_tasks",
        "conferences",
    ],
    Role.PROJECT_MANAGER: [
        "studies",
        "risks",
        "deviations",
        "etmf",
        "dm",
        "team_tasks",
        "sops",
        "conferences",
    ],
    Role.CRA: ["my_sites", "visits", "dm", "risks", "conferences"],
    Role.CTA: ["etmf", "studies", "sops", "conferences"],
    Role.DATA_MANAGER: ["dm_queries", "dm_missing", "dm_labs", "dm_sdv", "deviations", "conferences"],
    Role.SAFETY: ["safety_db", "dm_labs", "deviations", "sops", "conferences"],
    Role.QA: ["sops", "deviations", "team_tasks", "risks", "conferences"],
    Role.VIEWER: ["studies", "conferences"],
}

# The third "Needs your attention" figure for each role (the first two are the person's own tasks).
HIGHLIGHT: dict[Role, str] = {
    Role.ADMIN: "milestones_overdue",
    Role.PROJECT_MANAGER: "milestones_overdue",
    Role.CRA: "visits_soon",
    Role.CTA: "etmf_expiring",
    Role.DATA_MANAGER: "dm_awaiting",
    Role.SAFETY: "dm_clin_sig",
    Role.QA: "sop_reviews_overdue",
    Role.VIEWER: "milestones_overdue",
}


def _kpi(tile: Tile, link: str) -> Kpi:
    return Kpi(label=tile.label, value=tile.value, note=tile.note, tone=tile.tone, link=link)


def _pick(tiles: list[Tile], keys: list[str], link: str) -> list[Kpi]:
    by_key = {t.key: t for t in tiles}
    return [_kpi(by_key[k], link) for k in keys if k in by_key]


def _day(d: date) -> str:
    return f"{d:%a} {d.day} {d:%b}"


def _days(n: int, word: str = "day") -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


class _Ctx:
    """Everything one Overview request needs, computed once and only when a section asks for it."""

    def __init__(self, db: Session, connector: StudyConnector, sops: SopConnector, user: CurrentUser) -> None:
        self.db, self.connector, self.sops, self.user = db, connector, sops, user
        self.now = today()
        self.highlights: dict[str, Kpi] = {}
        self.sources: list[SourceInfo] = []
        self._studies: list[Study] | None = None

    def studies(self) -> list[Study]:
        if self._studies is None:
            self._studies = _source_studies(self)
        return self._studies


# ---- sections built from existing reports -------------------------------------------------------------


async def _studies(c: _Ctx) -> Section:
    r = await _study_delivery(c.db, c.connector, c.user, None, None)
    overdue = next((t for t in r.tiles if t.key == "overdue"), None)
    if overdue is not None:
        c.highlights["milestones_overdue"] = _kpi(overdue, "/reports?tab=study")
    soon = c.now + timedelta(days=MILESTONE_WINDOW_DAYS)
    upcoming = sorted(
        (
            m
            for m in r.milestones
            if m.state != MilestoneState.COMPLETED and m.current_date and c.now <= m.current_date <= soon
        ),
        key=lambda m: m.current_date or date.max,
    )
    return Section(
        key="studies",
        title="Studies at a glance",
        source="from SimpleTrials",
        link="/portfolio",
        link_label="Study Portfolio",
        kpis=_pick(r.tiles, ["on_plan", "overdue", "slipped_major", "enrolment"], "/reports?tab=study"),
        rows=[
            Row(
                label=f"{m.protocol_number} · {m.name}",
                detail="Next milestone",
                chip=f"Planned {_day(m.current_date)}" if m.current_date else None,
                tone="info",
                link=f"/command-centre/{m.study_id}",
            )
            for m in upcoming[:4]
        ],
        empty=f"No milestones in the next {MILESTONE_WINDOW_DAYS} days.",
    )


async def _risks(c: _Ctx) -> Section:
    r = await _risks_issues(c.db, c.connector, c.user, None, None)
    rows = [
        Row(
            label=i.description or "Issue",
            detail=f"{i.protocol_number} · {i.where}",
            chip=(
                f"{_days(i.days_overdue)} overdue"
                if i.days_overdue is not None
                else (f"Due {_day(i.due_on)}" if i.due_on else i.status)
            ),
            tone="bad" if i.days_overdue is not None else "warn",
            link="/risks",
        )
        for i in r.issues
        if not i.closed
    ]
    return Section(
        key="risks",
        title="Risks and issues",
        source="from SimpleTrials",
        link="/reports?tab=risks",
        link_label="Risks and issues report",
        kpis=_pick(r.tiles, ["open", "overdue", "high"], "/reports?tab=risks"),
        rows=rows[:3],
        empty="No open risks or issues.",
    )


async def _deviations_section(c: _Ctx) -> Section:
    r = await _deviations(c.db, c.connector, c.user, None, None)
    rows = [
        Row(
            label=f"{d.severity} · {d.category}",
            detail=f"{d.protocol_number} · {d.where}"
            + (f" · occurred {_day(d.occurred_on)}" if d.occurred_on else ""),
            chip=f"{_days(d.days_open)} open" if d.days_open is not None else d.status,
            tone="bad" if d.severity in ("Critical", "Major") else "warn",
            link="/reports?tab=deviations",
        )
        for d in r.deviations
        if not d.closed
    ]
    return Section(
        key="deviations",
        title="Protocol deviations",
        source="from SimpleTrials",
        link="/reports?tab=deviations",
        link_label="Deviations report",
        kpis=_pick(r.tiles, ["total", "open", "major"], "/reports?tab=deviations"),
        rows=rows[:3],
        empty="No open protocol deviations.",
    )


async def _etmf_section(c: _Ctx) -> Section:
    r = await _etmf(c.db, c.connector, c.user, None, None)
    expiring = next((t for t in r.tiles if t.key == "expiring"), None)
    if expiring is not None:
        c.highlights["etmf_expiring"] = _kpi(expiring, "/reports?tab=etmf")
    rows = [
        Row(
            label=e.name,
            detail=f"{e.protocol_number} · {e.where}",
            chip=f"Expired {_day(e.expires_on)}" if e.state == "expired" else f"Expires {_day(e.expires_on)}",
            tone="bad" if e.state == "expired" else "warn",
            link="/reports?tab=etmf",
        )
        for e in r.expiring[:3]
    ] + [
        Row(
            label=s.label,
            detail=f"{s.missing} of {s.expected} documents still expected",
            chip=f"{s.percent:g}% filed" if s.percent is not None else None,
            tone="warn" if s.missing else "good",
            link="/reports?tab=etmf",
        )
        for s in r.sites_missing[:3]
    ]
    return Section(
        key="etmf",
        title="eTMF",
        source="from SimpleTrials eTMF",
        link="/reports?tab=etmf",
        link_label="eTMF report",
        kpis=_pick(r.tiles, ["completeness", "missing", "on_time", "expiring"], "/reports?tab=etmf"),
        rows=rows,
        empty="Nothing missing or expiring.",
    )


async def _sops_section(c: _Ctx) -> Section:
    r = await _quality(c.db, c.sops, c.user, None, 12)
    overdue = next((t for t in r.tiles if t.key == "review_overdue"), None)
    if overdue is not None:
        c.highlights["sop_reviews_overdue"] = _kpi(overdue, "/reports?tab=quality")
    due = [s for s in r.schedule if s.state in ("overdue", "due_soon")]
    due.sort(key=lambda s: s.days_to_review if s.days_to_review is not None else 10**6)
    return Section(
        key="sops",
        title="SOPs",
        source="from SharePoint",
        link="/reports?tab=quality",
        link_label="Quality (SOPs) report",
        kpis=_pick(
            r.tiles, ["review_overdue", "review_due_soon", "approved", "changes"], "/reports?tab=quality"
        ),
        rows=[
            Row(
                label=f"{s.sop_number or ''} {s.title}".strip(),
                detail=s.department,
                chip=(
                    f"Review {_days(-(s.days_to_review or 0))} overdue"
                    if s.state == "overdue"
                    else f"Review due {_day(s.review_date)}"
                    if s.review_date
                    else "Review due"
                ),
                tone="bad" if s.state == "overdue" else "warn",
                link=f"/documents/sops/{s.id}",
            )
            for s in due[:4]
        ],
        empty="No SOP reviews overdue or due soon.",
    )


async def _team_tasks(c: _Ctx) -> Section:
    r = await _work_management(c.db, c.connector, c.user, None, None)
    return Section(
        key="team_tasks",
        title="Team tasks",
        source="Avi.Intelligence",
        link="/reports?tab=work",
        link_label="Work management report",
        kpis=_pick(r.tiles, ["open", "overdue", "due_soon"], "/reports?tab=work"),
        rows=[
            Row(
                label=f"{t.reference} · {t.title}",
                detail=" · ".join(
                    [
                        t.category_label,
                        *([t.about] if t.about else []),
                        f"waiting on {', '.join(t.waiting_on)}",
                    ]
                ),
                chip=f"{_days(t.days_overdue)} late",
                tone="bad",
                link="/reports?tab=work",
            )
            for t in r.overdue[:4]
        ],
        empty="No overdue tasks.",
    )


# ---- CRA: assigned sites and site visits ---------------------------------------------------------------


def _source_studies(c: _Ctx) -> list[Study]:
    source = current_source_label(c.connector)
    return list(
        c.db.scalars(
            select(Study)
            .where(Study.tenant_id == c.user.tenant_id, Study.source == source, Study.in_source.is_(True))
            .options(
                selectinload(Study.sites),
                selectinload(Study.action_items),
                selectinload(Study.deviations),
                selectinload(Study.site_visits),
                selectinload(Study.etmf_documents),
            )
            .order_by(Study.protocol_number)
        )
    )


def _assigned(c: _Ctx, studies: list[Study]) -> tuple[list[tuple[Study, StudySite]], bool]:
    """The person's assigned sites; all sites (and False) when none are assigned yet."""
    keys = {
        (a.study_id, a.site_external_id)
        for a in c.db.scalars(
            select(SiteAssignment).where(
                SiteAssignment.tenant_id == c.user.tenant_id, SiteAssignment.person_id == c.user.id
            )
        )
    }
    every = [(s, site) for s in studies for site in s.sites]
    mine = [(s, site) for s, site in every if (s.id, site.external_id) in keys]
    return (mine, True) if mine else (every, False)


async def _my_sites(c: _Ctx) -> Section:
    studies = c.studies()
    sites, assigned = _assigned(c, studies)
    rows: list[Row] = []
    for study, site in sites:
        overdue = sum(
            1
            for a in study.action_items
            if a.site_number == site.site_number and not a.closed and a.due_on and a.due_on < c.now
        )
        open_devs = sum(
            1
            for d in study.deviations
            if not d.closed and (d.site_external_id == site.external_id or d.site_number == site.site_number)
        )
        etmf = build_etmf([study], c.now, study_id=study.id, site_id=site.id)
        missing = next((t.value for t in etmf.tiles if t.key == "missing"), "0")
        visit = next(
            (
                v
                for v in study.site_visits
                if v.site_external_id == site.external_id
                and v.starts_on
                and v.starts_on >= c.now
                and (v.status or "").lower() != "completed"
            ),
            None,
        )
        parts = [f"{site.enrolled if site.enrolled is not None else 'No'} enrolled"]
        if overdue:
            parts.append(f"{overdue} overdue action item{'' if overdue == 1 else 's'}")
        if open_devs:
            parts.append(f"{open_devs} open deviation{'' if open_devs == 1 else 's'}")
        parts.append(f"{missing} site documents expected")
        rows.append(
            Row(
                label=f"{site.site_number} · {site.name}",
                detail=f"{study.protocol_number} · " + " · ".join(parts),
                chip=f"Next visit {_day(visit.starts_on)}"
                if visit and visit.starts_on
                else "No visit planned",
                tone="bad" if overdue or open_devs else ("info" if visit else "neutral"),
                link=f"/command-centre/{study.id}?tab=sites",
            )
        )
    return Section(
        key="my_sites",
        title="Your sites" if assigned else "Sites",
        source="from SimpleTrials",
        link="/command-centre",
        link_label="Study Command Centre",
        rows=rows,
        notice=None
        if assigned
        else "No sites are assigned to you yet, so all sites are shown. An administrator assigns sites in "
        "Administration.",
        empty="No sites.",
    )


async def _visits(c: _Ctx) -> Section:
    studies = c.studies()
    sites, assigned = _assigned(c, studies)
    site_keys = {(s.id, site.external_id): (s, site) for s, site in sites}
    upcoming = sorted(
        (
            (site_keys[(s.id, v.site_external_id or "")], v)
            for s in studies
            for v in s.site_visits
            if (s.id, v.site_external_id or "") in site_keys
            and v.starts_on
            and v.starts_on >= c.now
            and (v.status or "").lower() != "completed"
        ),
        key=lambda pair: pair[1].starts_on or date.max,
    )
    soon = [
        p for p in upcoming if p[1].starts_on and p[1].starts_on <= c.now + timedelta(days=VISIT_WINDOW_DAYS)
    ]
    c.highlights["visits_soon"] = Kpi(
        label=f"Site visits in the next {VISIT_WINDOW_DAYS} days",
        value=str(len(soon)),
        tone="warn" if soon else "neutral",
        link="/command-centre",
    )
    return Section(
        key="visits",
        title="Site visits",
        source="from SimpleTrials",
        link="/command-centre",
        link_label="Study Command Centre",
        rows=[
            Row(
                label=v.kind or "Site visit",
                detail=f"{study.protocol_number} · {site.site_number} · {site.name}"
                + (f" · {v.status}" if v.status else ""),
                chip=_day(v.starts_on) if v.starts_on else None,
                tone="warn"
                if v.starts_on and v.starts_on <= c.now + timedelta(days=VISIT_WINDOW_DAYS)
                else "info",
                link=f"/command-centre/{study.id}?tab=sites",
            )
            for (study, site), v in upcoming[:5]
        ],
        empty="No site visits planned" + ("" if assigned else " at any site") + ".",
    )


# ---- administrator and pharmacovigilance ---------------------------------------------------------------


async def _connectors(c: _Ctx) -> Section:
    info = study_source(c.db, c.connector, c.user.tenant_id)
    run = last_sync(c.db, c.user.tenant_id, mode=c.connector.info().mode)
    st_ok = run is None or run.ok
    sp = c.sops.info()
    rows = [
        Row(
            label="SimpleTrials",
            detail=f"{info.connector.mode} · {info.connector.scope or ''} · last sync "
            + (f"{info.last_successful_sync_at:%d %b %H:%M}" if info.last_successful_sync_at else "never"),
            chip="OK" if st_ok else "Last sync failed",
            tone="good" if st_ok else "bad",
            link="/admin",
        ),
        Row(label="SharePoint", detail=f"{sp.mode}", chip="OK", tone="good", link="/admin"),
    ]
    rows += [
        Row(
            label=s.name,
            detail="last sync " + (f"{s.as_of:%d %b %H:%M}" if s.as_of else "never"),
            chip="OK" if s.ok else "Last sync failed",
            tone="good" if s.ok else "bad",
            link="/data-management",
        )
        for s in c.sources
        if s.name not in ("SimpleTrials", "SharePoint")
    ]
    rows.append(Row(label="Avie Safety DB", detail="next on the connector roadmap", chip="Not connected"))
    return Section(
        key="connectors",
        title="Connectors",
        source="read-only",
        link="/admin",
        link_label="Administration",
        rows=rows,
    )


async def _safety_db(_c: _Ctx) -> Section:
    return Section(
        key="safety_db",
        title="Serious adverse events",
        source="from the safety database",
        notice="The safety database is not connected yet. Serious adverse events, SUSARs and reporting "
        "deadlines appear here once the Avie Safety DB connector is built (next on the connector roadmap).",
    )


BUILDERS: dict[str, Callable[[_Ctx], Awaitable[Section]]] = {
    "studies": _studies,
    "risks": _risks,
    "deviations": _deviations_section,
    "etmf": _etmf_section,
    "sops": _sops_section,
    "team_tasks": _team_tasks,
    "my_sites": _my_sites,
    "visits": _visits,
    "connectors": _connectors,
    "safety_db": _safety_db,
}
TITLES = {
    "studies": "Studies at a glance",
    "risks": "Risks and issues",
    "deviations": "Protocol deviations",
    "etmf": "eTMF",
    "sops": "SOPs",
    "team_tasks": "Team tasks",
    "my_sites": "Your sites",
    "visits": "Site visits",
    "connectors": "Connectors",
    "safety_db": "Serious adverse events",
}
NOT_LOADED = "Could not load this section just now. Try Sync all, or open the report."


# ---- the person's own tasks ----------------------------------------------------------------------------


def _attention(c: _Ctx, role: Role) -> Attention:
    tasks = list(
        c.db.scalars(
            select(Task)
            .where(
                Task.tenant_id == c.user.tenant_id,
                Task.status.not_in([s.value for s in TASK_CLOSED]),
                Task.assignees.any(
                    (TaskAssignee.person_id == c.user.id)
                    & (TaskAssignee.status != TaskStatus.COMPLETED.value)
                ),
            )
            .options(selectinload(Task.study), selectinload(Task.documents), selectinload(Task.assignees))
        )
    )
    overdue = [t for t in tasks if t.due_date and t.due_date < c.now]
    soon_end = c.now + timedelta(days=TASK_SOON_DAYS)
    soon = [t for t in tasks if t.due_date and c.now <= t.due_date <= soon_end]
    counts = [
        Kpi(
            label="Your overdue tasks",
            value=str(len(overdue)),
            tone="bad" if overdue else "good",
            link="/tasks",
        ),
        Kpi(
            label=f"Your tasks due in the next {TASK_SOON_DAYS} days",
            value=str(len(soon)),
            tone="warn" if soon else "neutral",
            link="/tasks",
        ),
    ]
    highlight = c.highlights.get(HIGHLIGHT[role])
    if highlight is not None:
        counts.append(highlight)
    else:
        sop = [t for t in tasks if t.category == TaskCategory.SOP.value]
        counts.append(
            Kpi(label="SOP reviews assigned to you", value=str(len(sop)), tone="info", link="/tasks")
        )

    def chip(t: Task) -> tuple[str, str]:
        if t.due_date is None:
            return "No due date", "neutral"
        if t.due_date < c.now:
            return f"{_days((c.now - t.due_date).days)} late", "bad"
        return f"Due {_day(t.due_date)}", "warn" if t.due_date <= soon_end else "info"

    ordered = sorted(tasks, key=lambda t: (t.due_date is None, t.due_date or date.max, t.reference))
    items = []
    for t in ordered[:5]:
        text, tone = chip(t)
        about = task_about(t)
        items.append(
            Row(
                label=f"{t.reference} · {t.title}",
                detail=f"{TASK_CATEGORY_LABELS[TaskCategory(t.category)]}{f' · {about}' if about else ''}",
                chip=text,
                tone=tone,  # type: ignore[arg-type]
                link="/tasks",
            )
        )
    return Attention(counts=counts, items=items)


@router.get("/overview", response_model=Overview)
async def overview(
    db: Db,
    connector: Connector,
    sops: SopConnectorDep,
    user: Reader,
    view: Annotated[Role | None, Query(description="Another role's page (administrators only)")] = None,
) -> Overview:
    allowed = list(Role) if user.role == Role.ADMIN else [user.role]
    role: Role = view if view is not None and view in allowed else user.role
    await ensure_synced(db, connector, user.tenant_id)
    c = _Ctx(db, connector, sops, user)

    info = study_source(db, connector, user.tenant_id)
    run = last_sync(db, user.tenant_id, mode=connector.info().mode)
    c.sources.append(
        SourceInfo(name="SimpleTrials", as_of=info.last_successful_sync_at, ok=run is None or run.ok)
    )
    try:
        listing = await sops.list_sops()
        c.sources.append(SourceInfo(name="SharePoint", as_of=listing.fetched_at))
    except Exception:  # a SharePoint outage must not take the Overview down
        log.warning("overview.sharepoint_unavailable")
        c.sources.append(SourceInfo(name="SharePoint", as_of=None, ok=False))

    contributed: dict[str, Section] = {}
    for provider in providers.registered():
        try:
            got = await provider(db, user)
        except Exception:
            log.exception("overview.provider_failed")
            continue
        contributed.update(got.sections)
        c.sources += got.sources
        c.highlights.update(got.highlights)

    sections: list[Section] = []
    for key in LAYOUT[role]:
        if key in contributed:
            sections.append(contributed[key])
            continue
        build = BUILDERS.get(key)
        if build is None:
            continue  # e.g. Data Management switched off
        try:
            sections.append(await build(c))
        except Exception:
            log.exception("overview.section_failed", extra={"section": key})
            sections.append(Section(key=key, title=TITLES.get(key, key), source="", notice=NOT_LOADED))
    # The administrator's connector list needs every source, including module ones: build it last.
    if role == Role.ADMIN:
        sections = [await _connectors(c) if s.key == "connectors" else s for s in sections]

    return Overview(
        view=role.value,
        view_label=ROLE_LABELS[role],
        views=[ViewOption(id=r.value, label=ROLE_LABELS[r]) for r in allowed],
        purpose=PURPOSE[role],
        sources=c.sources,
        attention=_attention(c, role),
        sections=sections,
    )


# ---- CRA site assignments (administrators) -------------------------------------------------------------


class AssignablePerson(BaseModel):
    id: str
    name: str
    job_title: str


class AssignableSite(BaseModel):
    key: str
    """"<study id>:<SimpleTrials site id>"."""
    label: str


class SiteAssignments(BaseModel):
    people: list[AssignablePerson]
    sites: list[AssignableSite]
    assignments: dict[str, list[str]]


class SiteAssignmentUpdate(BaseModel):
    sites: list[str] = Field(default_factory=list, max_length=500)


def _assignable_sites(db: Session, connector: StudyConnector, tenant_id: str) -> list[AssignableSite]:
    source = current_source_label(connector)
    studies = db.scalars(
        select(Study)
        .where(Study.tenant_id == tenant_id, Study.source == source, Study.in_source.is_(True))
        .options(selectinload(Study.sites))
        .order_by(Study.protocol_number)
    )
    return [
        AssignableSite(
            key=f"{s.id}:{site.external_id}", label=f"{s.protocol_number} · {site.site_number} · {site.name}"
        )
        for s in studies
        for site in s.sites
    ]


def _current(db: Session, tenant_id: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for a in db.scalars(select(SiteAssignment).where(SiteAssignment.tenant_id == tenant_id)):
        out.setdefault(a.person_id, []).append(f"{a.study_id}:{a.site_external_id}")
    return out


@router.get("/site-assignments", response_model=SiteAssignments, tags=["Administration"])
async def get_site_assignments(db: Db, connector: Connector, user: Manager) -> SiteAssignments:
    await ensure_synced(db, connector, user.tenant_id)
    return SiteAssignments(
        people=[AssignablePerson(id=p.id, name=p.name, job_title=p.job_title) for p in list_people()],
        sites=_assignable_sites(db, connector, user.tenant_id),
        assignments=_current(db, user.tenant_id),
    )


@router.put("/site-assignments/{person_id}", response_model=SiteAssignments, tags=["Administration"])
async def put_site_assignments(
    person_id: Annotated[str, Path(max_length=255)],
    body: SiteAssignmentUpdate,
    request: Request,
    db: Db,
    connector: Connector,
    user: Manager,
) -> SiteAssignments:
    person = next((p for p in list_people() if p.id == person_id), None)
    if person is None:
        raise HTTPException(404, "Person not found.")
    valid = {s.key: s.label for s in _assignable_sites(db, connector, user.tenant_id)}
    unknown = [k for k in body.sites if k not in valid]
    if unknown:
        raise HTTPException(422, "Unknown site.")
    before = set(_current(db, user.tenant_id).get(person_id, []))
    after = set(body.sites)
    for a in db.scalars(
        select(SiteAssignment).where(
            SiteAssignment.tenant_id == user.tenant_id, SiteAssignment.person_id == person_id
        )
    ):
        if f"{a.study_id}:{a.site_external_id}" not in after:
            db.delete(a)
    for key in after - before:
        study_id, site_ext = key.split(":", 1)
        db.add(
            SiteAssignment(
                tenant_id=user.tenant_id,
                person_id=person_id,
                study_id=study_id,
                site_external_id=site_ext,
                assigned_by_name=user.name,
            )
        )
    db.commit()
    if before != after:
        record_event(
            db,
            user,
            action="site_assignment.updated",
            entity_type="person",
            entity_id=person_id,
            summary=f"Sites for {person.name}: {len(after)} assigned",
            details={
                "added": sorted(valid[k] for k in after - before),
                "removed": sorted(valid.get(k, k) for k in before - after),
            },
            request=request,
        )
    return await get_site_assignments(db, connector, user)
