"""Data Management API (/api/v1/data-management). Hidden (404) unless DATA_MANAGEMENT_ENABLED=true."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.audit.service import record_event
from app.auth.rbac import CurrentUser, Permission, require
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.reports.excel import Sheet, build_workbook
from app.studies.clock import today

from . import rules
from .models import DmFormStatus, DmMissingItem, DmPendingForm, DmQuery
from .sync import DEMO_CONNECTION, connections, is_demo, last_runs, last_success, sync_connection


def enabled(settings: Annotated[Settings, Depends(get_settings)]) -> Settings:
    if not settings.data_management_enabled:
        raise HTTPException(404, "Data Management is not enabled.")
    return settings


router = APIRouter(prefix="/data-management", tags=["Data Management"], dependencies=[Depends(enabled)])

Db = Annotated[Session, Depends(get_db)]
Config = Annotated[Settings, Depends(enabled)]
Viewer = Annotated[CurrentUser, Depends(require(Permission.DM_VIEW))]
Syncer = Annotated[CurrentUser, Depends(require(Permission.DM_SYNC))]
Exporter = Annotated[CurrentUser, Depends(require(Permission.DM_EXPORT))]
State = Literal["open_at_site", "awaiting_approval", "closed", "not_closed"]


class SyncRunOut(BaseModel):
    started_at: datetime
    finished_at: datetime | None
    ok: bool
    counts: dict[str, object]
    error: str | None
    triggered_by: str


class ConnectionOut(BaseModel):
    name: str
    environment: str
    study_code: str | None
    last_run: SyncRunOut | None
    last_success_at: datetime | None


class ScopeOut(BaseModel):
    id: str
    """A connection name, or "all-live" / "all-sandbox" (all studies of one environment)."""
    label: str
    environment: str
    multi: bool


class StatusOut(BaseModel):
    connections: list[ConnectionOut]
    scopes: list[ScopeOut]
    default_scope: str
    can_sync: bool
    can_export: bool
    demo: bool
    site_answer_days: int
    approval_days: int
    sync_minutes: int
    rules: dict[str, str]


def _run_out(run: object | None) -> SyncRunOut | None:
    return SyncRunOut.model_validate(run, from_attributes=True) if run is not None else None


ENV_LABELS = {"live": "Live", "sandbox": "Sandbox", "demo": "Demo"}


def _study_codes(db: Session, tenant_id: str, names: list[str]) -> dict[str, str]:
    codes: dict[str, str] = {}
    for name in names:
        ok = last_success(db, tenant_id, name)
        if ok and ok.counts.get("study"):
            codes[name] = str(ok.counts["study"])
    return codes


def _scopes(settings: Settings, codes: dict[str, str]) -> list[ScopeOut]:
    """All live studies, all sandbox studies (only when there are two or more), then each study.
    Live and sandbox studies are never combined."""
    conns = connections(settings)
    out: list[ScopeOut] = []
    for env in ("live", "sandbox"):
        if sum(e == env for e in conns.values()) >= 2:
            out.append(ScopeOut(id=f"all-{env}", label=f"All {env} studies", environment=env, multi=True))
    for name, env in conns.items():
        label = f"{codes.get(name, name)} · {ENV_LABELS.get(env, env)}"
        out.append(ScopeOut(id=name, label=label, environment=env, multi=False))
    return out


@router.get("/status", response_model=StatusOut)
def status(db: Db, user: Viewer, settings: Config) -> StatusOut:
    runs = last_runs(db, user.tenant_id)
    conns = connections(settings)
    codes = _study_codes(db, user.tenant_id, list(conns))
    scopes = _scopes(settings, codes)
    return StatusOut(
        scopes=scopes,
        default_scope=scopes[0].id,
        connections=[
            ConnectionOut(
                name=name,
                environment=env,
                study_code=codes.get(name),
                last_run=_run_out(runs.get(name)),
                last_success_at=(ok.finished_at if (ok := last_success(db, user.tenant_id, name)) else None),
            )
            for name, env in conns.items()
        ],
        can_sync=user.can(Permission.DM_SYNC),
        can_export=user.can(Permission.DM_EXPORT),
        demo=is_demo(settings),
        site_answer_days=settings.dm_site_answer_days,
        approval_days=settings.dm_approval_days,
        sync_minutes=settings.data_management_sync_minutes,
        rules=rules.RULES,
    )


class SyncRequest(BaseModel):
    connection: str


SYNC_REUSE = timedelta(minutes=2)
"""A press of Sync now this soon after a successful sync reuses it instead of asking Viedoc again."""
_SYNCING: set[tuple[str, str]] = set()
"""(tenant, connection) syncs running now: Viedoc builds one export at a time per study."""


def _aware(at: datetime) -> datetime:
    return at if at.tzinfo else at.replace(tzinfo=UTC)


@router.post("/sync", response_model=SyncRunOut)
async def sync_now(body: SyncRequest, request: Request, db: Db, user: Syncer, settings: Config) -> SyncRunOut:
    name = body.connection.lower()
    if name not in connections(settings):
        raise HTTPException(404, "No such Viedoc connection.")
    key = (user.tenant_id, name)
    if key in _SYNCING:
        raise HTTPException(409, "A sync of this study is already running. Try again in a minute.")
    recent = last_success(db, user.tenant_id, name)
    if recent and recent.finished_at and datetime.now(UTC) - _aware(recent.finished_at) < SYNC_REUSE:
        reused = _run_out(recent)
        assert reused is not None
        return reused
    _SYNCING.add(key)
    try:
        run = await sync_connection(db, settings, tenant_id=user.tenant_id, name=name, triggered_by=user.name)
    finally:
        _SYNCING.discard(key)
    record_event(
        db,
        user,
        action="dm.synced",
        entity_type="viedoc_connection",
        entity_id=run.connection,
        summary=f"Data Management sync from Viedoc ({run.connection}): {'ok' if run.ok else 'failed'}",
        details={"counts": run.counts, "error": run.error},
        request=request,
    )
    out = _run_out(run)
    assert out is not None
    return out


class Scope(BaseModel):
    id: str
    names: list[str]
    environment: str
    multi: bool


async def _scope(db: Session, user: CurrentUser, settings: Settings, scope: str | None) -> Scope:
    """One study, or all studies of one environment ("all-live", "all-sandbox"); never a mix."""
    conns = connections(settings)
    chosen = (scope or _scopes(settings, {})[0].id).lower()
    if chosen.startswith("all-"):
        env = chosen[4:]
        names = [n for n, e in conns.items() if e == env]
        if not names:
            raise HTTPException(404, "No studies in that environment.")
        result = Scope(id=chosen, names=names, environment=env, multi=True)
    elif chosen in conns:
        result = Scope(id=chosen, names=[chosen], environment=conns[chosen], multi=False)
    else:
        raise HTTPException(404, "No such Viedoc connection.")
    # The demo study syncs itself on first use; real Viedoc studies wait for "Sync now" or the schedule.
    if DEMO_CONNECTION in result.names and last_success(db, user.tenant_id, DEMO_CONNECTION) is None:
        await sync_connection(
            db, settings, tenant_id=user.tenant_id, name=DEMO_CONNECTION, triggered_by="system (first use)"
        )
    return result


class Tile(BaseModel):
    key: str
    label: str
    value: int
    note: str
    tone: Literal["good", "info", "warn", "bad", "neutral"]


class SiteRow(BaseModel):
    connection: str
    study_code: str
    site_code: str
    site_name: str
    open_at_site: int
    awaiting_approval: int
    overdue: int
    oldest_days: int | None
    missing_items: int
    pending_forms: int
    sdv_required: int = 0
    sdv_done: int = 0


class SdvSummary(BaseModel):
    """SDV completed vs required, counted per field (only fields set up for SDV in Viedoc)."""

    required: int
    done: int
    percent: float | None
    forms_total: int
    forms_complete: int


def sdv_summary(rows: list[DmFormStatus]) -> SdvSummary:
    required = sum(r.sdv_required for r in rows)
    done = sum(r.sdv_done for r in rows)
    forms = [r for r in rows if r.kind == "form" and r.sdv_required]
    return SdvSummary(
        required=required,
        done=done,
        percent=round(done / required * 100, 1) if required else None,
        forms_total=len(forms),
        forms_complete=sum(r.sdv_done >= r.sdv_required for r in forms),
    )


class BucketRow(BaseModel):
    label: str
    open_at_site: int
    awaiting_approval: int


class FormRow(BaseModel):
    form: str
    open: int


class OverviewOut(BaseModel):
    scope: str
    multi: bool
    environment: str
    study_code: str | None
    """The study's code for a single study; None for all studies."""
    studies: list[dict[str, str]]
    as_of: datetime | None
    tiles: list[Tile]
    sdv: SdvSummary
    sites: list[SiteRow]
    ageing: list[BucketRow]
    forms: list[FormRow]
    site_options: list[dict[str, str]]
    form_options: list[dict[str, str]]


@router.get("/overview", response_model=OverviewOut)
async def overview(
    db: Db,
    user: Viewer,
    settings: Config,
    scope: Annotated[str | None, Query(max_length=64)] = None,
) -> OverviewOut:
    sc = await _scope(db, user, settings, scope)
    now = today()
    queries = db.scalars(
        select(DmQuery).where(DmQuery.tenant_id == user.tenant_id, DmQuery.connection.in_(sc.names))
    ).all()
    missing = db.scalars(
        select(DmMissingItem).where(
            DmMissingItem.tenant_id == user.tenant_id, DmMissingItem.connection.in_(sc.names)
        )
    ).all()
    pending = db.scalars(
        select(DmPendingForm).where(
            DmPendingForm.tenant_id == user.tenant_id, DmPendingForm.connection.in_(sc.names)
        )
    ).all()
    statuses = list(
        db.scalars(
            select(DmFormStatus).where(
                DmFormStatus.tenant_id == user.tenant_id, DmFormStatus.connection.in_(sc.names)
            )
        )
    )
    codes = _study_codes(db, user.tenant_id, sc.names)
    for q in queries:
        codes.setdefault(q.connection, q.study_code)
    sa, ap = settings.dm_site_answer_days, settings.dm_approval_days
    sdv = sdv_summary(statuses)

    def flag_of(q: DmQuery) -> str:
        return rules.flag(q.state, rules.clock_days(q.state, q.state_since, now), sa, ap)

    open_q = [q for q in queries if q.state == "open_at_site"]
    awaiting = [q for q in queries if q.state == "awaiting_approval"]
    since = now - timedelta(days=30)
    reopened = sum(q.reopen_count > 0 for q in queries)
    closed_recent = [
        q for q in queries if q.state == "closed" and q.closed_at and q.closed_at.date() >= since
    ]
    red_open = sum(flag_of(q) == "red" for q in open_q)
    red_wait = sum(flag_of(q) == "red" for q in awaiting)
    unconfirmed = [m for m in missing if m.query_type.lower() == "unconfirmed missing data"]
    tiles = [
        Tile(key="open_at_site", label="Open at site", value=len(open_q),
             note=f"{red_open} overdue (over {sa} working days)" if red_open else "None overdue",
             tone="bad" if red_open else "neutral"),
        Tile(key="awaiting_approval", label="Answered, awaiting approval", value=len(awaiting),
             note=f"{red_wait} overdue (over {ap} working days)" if red_wait else "None overdue",
             tone="bad" if red_wait else ("warn" if awaiting else "good")),
        Tile(key="closed_30", label="Closed in the last 30 days", value=len(closed_recent),
             note=f"{reopened} queries were sent back at least once", tone="info"),
        Tile(key="missing_items", label="Unconfirmed missing data", value=len(unconfirmed),
             note="Blank fields not yet confirmed by the site", tone="warn" if unconfirmed else "good"),
        Tile(key="pending_forms", label="Pending forms", value=len(pending),
             note="Expected but not completed", tone="warn" if pending else "good"),
        Tile(key="sdv", label="SDV completed (%)", value=round(sdv.percent or 0),
             note=f"{sdv.done} of {sdv.required} fields verified" if sdv.required else "No SDV fields",
             tone="good" if sdv.required and sdv.done == sdv.required else "info"),
    ]  # fmt: skip

    # Sites are kept apart per study: the same site code can exist in two studies.
    site_names: dict[tuple[str, str], str] = {}
    for q in queries:
        site_names.setdefault((q.connection, q.site_code), q.site_name)
    for p in pending:
        site_names.setdefault((p.connection, p.site_code), p.site_name)
    for m in missing:
        site_names.setdefault((m.connection, m.site_code), m.site_code)
    for st in statuses:
        site_names.setdefault((st.connection, st.site_code), st.site_name)
    by_site: dict[tuple[str, str], SiteRow] = {
        key: SiteRow(connection=key[0], study_code=codes.get(key[0], key[0]), site_code=key[1], site_name=nm,
                     open_at_site=0, awaiting_approval=0, overdue=0, oldest_days=None, missing_items=0,
                     pending_forms=0)
        for key, nm in site_names.items()
    }  # fmt: skip
    for q in open_q + awaiting:
        row = by_site[(q.connection, q.site_code)]
        if q.state == "open_at_site":
            row.open_at_site += 1
        else:
            row.awaiting_approval += 1
        row.overdue += flag_of(q) == "red"
        age = rules.age_days(q.raised_at, now)
        if age is not None and (row.oldest_days is None or age > row.oldest_days):
            row.oldest_days = age
    for m in unconfirmed:
        by_site[(m.connection, m.site_code)].missing_items += 1
    for p in pending:
        by_site[(p.connection, p.site_code)].pending_forms += 1
    for st in statuses:
        row = by_site[(st.connection, st.site_code)]
        row.sdv_required += st.sdv_required
        row.sdv_done += st.sdv_done
    sites = sorted(
        by_site.values(), key=lambda r: (-r.overdue, -(r.open_at_site + r.awaiting_approval), r.site_code)
    )

    ageing = {
        label: BucketRow(label=label, open_at_site=0, awaiting_approval=0) for label, _l, _h in rules.BUCKETS
    }
    for q in open_q + awaiting:
        b = rules.bucket(rules.age_days(q.raised_at, now))
        if b:
            if q.state == "open_at_site":
                ageing[b].open_at_site += 1
            else:
                ageing[b].awaiting_approval += 1
    form_counts = Counter(rules.form_label(q.form_id, q.form_name, q.raised_on) for q in open_q + awaiting)
    successes = [ok for n in sc.names if (ok := last_success(db, user.tenant_id, n))]
    forms_seen = sorted({(q.form_id or "", q.form_name or q.form_id or "") for q in queries if q.form_id})
    return OverviewOut(
        scope=sc.id,
        multi=sc.multi,
        environment=sc.environment,
        study_code=None if sc.multi else codes.get(sc.names[0]),
        studies=[{"connection": n, "study_code": codes.get(n, n)} for n in sc.names],
        # The oldest of the studies' last syncs, so "as of" is never more recent than any part.
        as_of=min((ok.finished_at for ok in successes if ok.finished_at), default=None),
        tiles=tiles,
        sdv=sdv,
        sites=sites,
        ageing=list(ageing.values()),
        forms=[FormRow(form=f, open=n) for f, n in form_counts.most_common()],
        site_options=[
            {
                "id": f"{conn}:{code}" if sc.multi else code,
                "label": f"{codes.get(conn, conn)} · {code} · {nm}" if sc.multi else f"{code} · {nm}",
            }
            for (conn, code), nm in sorted(site_names.items())
        ],
        form_options=[
            *({"id": fid, "label": f"{fid} · {fname}" if fname != fid else fid} for fid, fname in forms_seen),
            *(
                [{"id": rules.VISIT_DATE, "label": rules.VISIT_DATE_LABEL}]
                if any(not q.form_id and (q.raised_on or "").lower() == "event date" for q in queries)
                else []
            ),
        ],
    )


class QueryOut(BaseModel):
    form_label: str
    """The form, or "Visit date (no form)" for queries raised on the visit date."""
    id: str
    connection: str
    study_code: str
    query_number: str
    site_code: str
    site_name: str
    subject_id: str
    event_name: str | None
    form_id: str | None
    form_name: str | None
    item_label: str | None
    query_type: str
    edit_check: str | None
    query_text: str | None
    state: str
    state_label: str
    viedoc_state: str
    raised_at: datetime | None
    state_since: datetime | None
    age_days: int | None
    clock_days: int | None
    flag: str
    reopen_count: int
    resolution: str | None


class QueryEventOut(BaseModel):
    viedoc_state: str
    at: datetime | None
    user_role: str | None
    resolution: str | None


class QueryDetailOut(QueryOut):
    event_id: str | None
    item_id: str | None
    raised_on: str | None
    events: list[QueryEventOut]


class QueryListOut(BaseModel):
    queries: list[QueryOut]
    total: int
    counts: dict[str, int]
    """By state, over the filtered set before paging."""
    views: dict[str, int]
    """How many each quick view would show (attention, open, awaiting, overdue, sent_back, closed)."""


def _query_out(q: DmQuery, now: date, settings: Settings, cls: type[QueryOut] = QueryOut) -> QueryOut:
    clock = rules.clock_days(q.state, q.state_since, now)
    extra: dict[str, object] = {}
    if cls is QueryDetailOut:
        extra = {
            "event_id": q.event_id,
            "item_id": q.item_id,
            "raised_on": q.raised_on,
            "events": [QueryEventOut.model_validate(e, from_attributes=True) for e in q.events],
        }
    return cls(
        form_label=rules.form_label(q.form_id, q.form_name, q.raised_on),
        id=q.id,
        connection=q.connection,
        study_code=q.study_code,
        query_number=q.query_number,
        site_code=q.site_code,
        site_name=q.site_name,
        subject_id=q.subject_id,
        event_name=q.event_name,
        form_id=q.form_id,
        form_name=q.form_name,
        item_label=q.item_label,
        query_type=q.query_type,
        edit_check=q.edit_check,
        query_text=q.query_text,
        state=q.state,
        state_label=rules.STATE_LABELS.get(q.state, q.state),
        viedoc_state=q.viedoc_state,
        raised_at=q.raised_at,
        state_since=q.state_since,
        age_days=rules.age_days(q.raised_at, now) if q.state != "closed" else None,
        clock_days=clock,
        flag=rules.flag(q.state, clock, settings.dm_site_answer_days, settings.dm_approval_days),
        reopen_count=q.reopen_count,
        resolution=q.resolution,
        **extra,
    )


@router.get("/queries", response_model=QueryListOut)
async def list_queries(
    db: Db,
    user: Viewer,
    settings: Config,
    scope: Annotated[str | None, Query(max_length=64)] = None,
    study: Annotated[
        str | None, Query(max_length=64, description="One study within an all-studies scope")
    ] = None,
    state: State | None = None,
    site: Annotated[str | None, Query(max_length=64)] = None,
    form: Annotated[str | None, Query(max_length=64)] = None,
    flag: Literal["red", "amber", "green"] | None = None,
    reopened: bool = False,
    raised_from: Annotated[date | None, Query(description="Raised on or after this day (UTC)")] = None,
    raised_to: Annotated[date | None, Query(description="Raised on or before this day (UTC)")] = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> QueryListOut:
    if raised_from and raised_to and raised_from > raised_to:
        raise HTTPException(422, "The start of the date range is after its end.")
    sc = await _scope(db, user, settings, scope)
    now = today()
    names = [n for n in sc.names if not study or n == study.lower()]
    stmt = select(DmQuery).where(DmQuery.tenant_id == user.tenant_id, DmQuery.connection.in_(names))
    if site:
        # "connection:site" in an all-studies scope (the same site code can exist in two studies)
        conn, _, code = site.rpartition(":")
        stmt = stmt.where(DmQuery.site_code == code)
        if conn:
            stmt = stmt.where(DmQuery.connection == conn)
    if form == rules.VISIT_DATE:
        stmt = stmt.where(DmQuery.form_id.is_(None), DmQuery.raised_on == "Event date")
    elif form:
        stmt = stmt.where(DmQuery.form_id == form)
    # Viedoc's query dates are UTC: a day runs from 00:00 to the next 00:00 UTC.
    if raised_from:
        stmt = stmt.where(DmQuery.raised_at >= datetime.combine(raised_from, time.min, tzinfo=UTC))
    if raised_to:
        stmt = stmt.where(
            DmQuery.raised_at < datetime.combine(raised_to + timedelta(days=1), time.min, tzinfo=UTC)
        )
    if search:
        like = f"%{search}%"
        stmt = stmt.where(
            or_(
                DmQuery.subject_id.ilike(like),
                DmQuery.query_number.ilike(like),
                DmQuery.item_label.ilike(like),
                DmQuery.edit_check.ilike(like),
                DmQuery.query_text.ilike(like),
            )
        )
    rows = [_query_out(q, now, settings) for q in db.scalars(stmt)]
    counts: dict[str, int] = defaultdict(int)
    for r in rows:
        counts[r.state] += 1
    # How many each quick view would show, given the other filters (search, site, form, dates).
    views = {
        "attention": sum(r.state != "closed" for r in rows),
        "open": counts["open_at_site"],
        "awaiting": counts["awaiting_approval"],
        "overdue": sum(r.state != "closed" and r.flag == "red" for r in rows),
        "sent_back": sum(r.reopen_count > 0 for r in rows),
        "closed": counts["closed"],
    }
    if reopened:
        rows = [r for r in rows if r.reopen_count > 0]
    if state == "not_closed":
        rows = [r for r in rows if r.state != "closed"]
    elif state:
        rows = [r for r in rows if r.state == state]
    if flag:
        rows = [r for r in rows if r.flag == flag]
    order = {"red": 0, "amber": 1, "green": 2, "none": 3}
    rows.sort(key=lambda r: (order.get(r.flag, 9), -(r.clock_days or 0), -(r.age_days or 0), r.query_number))
    return QueryListOut(
        queries=rows[offset : offset + limit], total=len(rows), counts=dict(counts), views=views
    )


# --- Excel downloads (System Admin and Data Manager only) ---

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
FLAG_LABELS = {"red": "Overdue", "amber": "Last day of target", "green": "Within target", "none": ""}


def _day(at: datetime | None) -> date | None:
    return at.date() if at else None


def _filters_text(filters: dict[str, object]) -> str:
    shown = [f"{k}: {v}" for k, v in filters.items() if v not in (None, "", False)]
    return "; ".join(shown) or "None (everything in scope)"


def _xlsx(
    request: Request,
    db: Session,
    user: CurrentUser,
    *,
    report: str,
    sc: Scope,
    filters: dict[str, object],
    sheets: list[Sheet],
    about: list[tuple[str, str]],
    rows: int,
) -> Response:
    codes = _study_codes(db, user.tenant_id, sc.names)
    as_of = [
        ok.finished_at for n in sc.names if (ok := last_success(db, user.tenant_id, n)) and ok.finished_at
    ]
    study = codes.get(sc.names[0], sc.names[0]) if len(sc.names) == 1 else sc.id
    about = [
        ("Report", f"Data Management: {report}"),
        ("Study", study if len(sc.names) == 1 else ", ".join(codes.get(n, n) for n in sc.names)),
        ("Environment", sc.environment),
        ("Filters", _filters_text(filters)),
        ("Rows", str(rows)),
        (
            "Source",
            "Viedoc export (read-only copy)"
            + (f", as of {min(_aware(a) for a in as_of):%d %b %Y %H:%M} UTC" if as_of else ""),
        ),
        *about,
        ("Data protection", "Subject IDs only. Staff are shown by role, never by name."),
        ("Changes", "Make any change in Viedoc; this file is a read-only copy."),
        ("Exported", f"{datetime.now(UTC):%d %b %Y %H:%M} UTC"),
    ]
    content = build_workbook(sheets, about)
    record_event(
        db,
        user,
        action="dm.exported",
        entity_type="dm_report",
        entity_id=report,
        summary=f"Downloaded Data Management {report} to Excel ({study})",
        details={
            "format": "xlsx",
            "scope": sc.id,
            "rows": rows,
            "filters": {k: str(v) for k, v in filters.items() if v},
        },
        request=request,
    )
    site = str(filters.get("site") or "").rpartition(":")[2]
    name = re.sub(r"[^\w.\- ]+", " ", f"{study} {report}{f' site {site}' if site else ''} {today():%Y-%m-%d}")
    return Response(
        content,
        media_type=XLSX,
        headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"', "Cache-Control": "no-store"},
    )


@router.get("/queries/export.xlsx")
async def export_queries(
    request: Request,
    db: Db,
    user: Exporter,
    settings: Config,
    scope: Annotated[str | None, Query(max_length=64)] = None,
    study: Annotated[str | None, Query(max_length=64)] = None,
    state: State | None = None,
    site: Annotated[str | None, Query(max_length=130)] = None,
    form: Annotated[str | None, Query(max_length=64)] = None,
    flag: Literal["red", "amber", "green"] | None = None,
    reopened: bool = False,
    raised_from: date | None = None,
    raised_to: date | None = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> Response:
    """The query list as on screen (same filters), for sending to a site or filing."""
    sc = await _scope(db, user, settings, scope)
    data = await list_queries(
        db, user, settings, scope=sc.id, study=study, state=state, site=site, form=form, flag=flag,
        reopened=reopened, raised_from=raised_from, raised_to=raised_to, search=search,
        limit=10**7, offset=0,
    )  # fmt: skip
    headers = [
        "Study", "Site", "Site name", "Subject", "Visit", "Form", "Field", "Query no.", "Query type",
        "Edit check", "Query text", "State", "Raised", "Days open", "Working days on the clock",
        "Target", "Times sent back", "Site answer",
    ]  # fmt: skip
    rows = [
        [
            q.study_code, q.site_code, q.site_name, q.subject_id, q.event_name, q.form_label, q.item_label,
            q.query_number, q.query_type, q.edit_check, q.query_text, q.state_label, _day(q.raised_at),
            q.age_days, q.clock_days, FLAG_LABELS.get(q.flag, ""), q.reopen_count, q.resolution,
        ]
        for q in data.queries
    ]  # fmt: skip
    filters: dict[str, object] = {
        "study": study, "state": state, "site": site, "form": form, "target": flag and FLAG_LABELS[flag],
        "sent back": reopened, "raised from": raised_from, "raised to": raised_to, "search": search,
    }  # fmt: skip
    about = [
        (
            "Targets",
            f"Sites answer within {settings.dm_site_answer_days} working days; "
            f"answers are approved within {settings.dm_approval_days}.",
        ),
        ("Clock", rules.RULES["clocks"]),
        ("Order", "Overdue first, then longest waiting."),
    ]
    return _xlsx(
        request, db, user, report="queries", sc=sc, filters=filters,
        sheets=[Sheet("Queries", headers, rows)], about=about, rows=len(rows),
    )  # fmt: skip


@router.get("/queries/{query_id}", response_model=QueryDetailOut)
def get_query(query_id: str, db: Db, user: Viewer, settings: Config) -> QueryOut:
    q = db.scalars(
        select(DmQuery)
        .where(DmQuery.tenant_id == user.tenant_id, DmQuery.id == query_id)
        .options(selectinload(DmQuery.events))
    ).first()
    if q is None:
        raise HTTPException(404, "Query not found.")
    return _query_out(q, today(), settings, QueryDetailOut)


# --- SDV (source data verification) ---

SdvView = Literal["waiting", "complete", "all"]


class SdvSiteRow(BaseModel):
    connection: str
    study_code: str
    site_code: str
    site_name: str
    required: int
    done: int
    percent: float | None
    forms_waiting: int
    oldest_waiting_days: int | None


class SdvVisitRow(BaseModel):
    event_id: str
    event_name: str
    required: int
    done: int
    percent: float | None


class SdvFormRow(BaseModel):
    id: str
    connection: str
    study_code: str
    site_code: str
    site_name: str
    subject_id: str
    event_name: str | None
    event_date: datetime | None
    form_label: str
    kind: str
    required: int
    done: int
    percent: float | None
    status: Literal["waiting", "complete"]
    days_since_visit: int | None
    last_sdv_at: datetime | None
    data_review_at: datetime | None
    signed_at: datetime | None
    locked_at: datetime | None


class SdvOut(BaseModel):
    scope: str
    multi: bool
    environment: str
    tiles: list[Tile]
    summary: SdvSummary
    sites: list[SdvSiteRow]
    visits: list[SdvVisitRow]
    forms: list[SdvFormRow]
    total: int
    views: dict[str, int]
    studies: list[dict[str, str]]
    site_options: list[dict[str, str]]
    form_options: list[dict[str, str]]
    visit_options: list[dict[str, str]]
    rules: dict[str, str]


SDV_RULES = {
    "sdv": (
        "SDV is counted per field: only fields set up for SDV in Viedoc are counted (so a risk-based SDV "
        "plan is respected), and a form or visit date is fully verified when all of its fields are."
    ),
    "review": (
        "Data review, signed and locked: the share of forms with that step recorded in Viedoc. "
        "Age: days since the visit date."
    ),
}


def _pct(part: int, whole: int) -> float | None:
    return round(part / whole * 100, 1) if whole else None


@router.get("/sdv", response_model=SdvOut)
async def sdv_view(
    db: Db,
    user: Viewer,
    settings: Config,
    scope: Annotated[str | None, Query(max_length=64)] = None,
    study: Annotated[str | None, Query(max_length=64)] = None,
    view: SdvView = "waiting",
    site: Annotated[str | None, Query(max_length=130)] = None,
    form: Annotated[str | None, Query(max_length=64)] = None,
    visit: Annotated[str | None, Query(max_length=64)] = None,
    visit_from: Annotated[date | None, Query(description="Visit on or after this day")] = None,
    visit_to: Annotated[date | None, Query(description="Visit on or before this day")] = None,
    search: Annotated[str | None, Query(max_length=100, description="Subject ID")] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 500,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SdvOut:
    if visit_from and visit_to and visit_from > visit_to:
        raise HTTPException(422, "The start of the date range is after its end.")
    sc = await _scope(db, user, settings, scope)
    now = today()
    rows_all = list(
        db.scalars(
            select(DmFormStatus).where(
                DmFormStatus.tenant_id == user.tenant_id, DmFormStatus.connection.in_(sc.names)
            )
        )
    )
    codes = _study_codes(db, user.tenant_id, sc.names)
    for r in rows_all:
        codes.setdefault(r.connection, r.study_code)

    # Options come from everything in scope, so they do not shrink as filters are applied.
    site_names = sorted({(r.connection, r.site_code, r.site_name) for r in rows_all})
    form_names = sorted({(r.form_id or "", r.form_name or r.form_id or "") for r in rows_all if r.form_id})
    visit_names = sorted(
        {(r.event_id or "", r.event_name or r.event_id or "") for r in rows_all if r.event_id}
    )

    rows = [r for r in rows_all if r.sdv_required > 0]
    if study:
        rows = [r for r in rows if r.connection == study.lower()]
    if site:
        conn, _, code = site.rpartition(":")
        rows = [r for r in rows if r.site_code == code and (not conn or r.connection == conn)]
    if form == rules.VISIT_DATE:
        rows = [r for r in rows if r.kind == "event_date"]
    elif form:
        rows = [r for r in rows if r.form_id == form]
    if visit:
        rows = [r for r in rows if r.event_id == visit]
    if visit_from:
        rows = [r for r in rows if r.event_date and r.event_date.date() >= visit_from]
    if visit_to:
        rows = [r for r in rows if r.event_date and r.event_date.date() <= visit_to]
    if search:
        rows = [r for r in rows if search.lower() in r.subject_id.lower()]

    summary = sdv_summary(rows)
    forms_only = [r for r in rows_all if r.kind == "form"]
    if study:
        forms_only = [r for r in forms_only if r.connection == study.lower()]
    waiting_rows = [r for r in rows if r.sdv_done < r.sdv_required]
    oldest = max((rules.age_days(r.event_date, now) or 0 for r in waiting_rows if r.event_date), default=None)
    reviewed = sum(bool(r.data_review_at) for r in forms_only)
    signed = sum(bool(r.signed_at) for r in forms_only)
    locked = sum(bool(r.locked_at) for r in forms_only)
    n_forms = len(forms_only)
    tiles = [
        Tile(key="fields", label="Fields verified", value=round(summary.percent or 0),
             note=f"{summary.done} of {summary.required} fields (%)", tone="info"),
        Tile(key="forms_complete", label="Forms fully verified", value=summary.forms_complete,
             note=f"of {summary.forms_total} forms needing SDV", tone="good" if summary.forms_total and
             summary.forms_complete == summary.forms_total else "neutral"),
        Tile(key="waiting", label="Waiting for SDV", value=len(waiting_rows),
             note=f"Oldest visit {oldest} days ago" if oldest is not None else "Nothing waiting",
             tone="warn" if waiting_rows else "good"),
        Tile(key="data_review", label="Data reviewed", value=round(_pct(reviewed, n_forms) or 0),
             note=f"{reviewed} of {n_forms} forms (%)", tone="neutral"),
        Tile(key="signed", label="Signed", value=round(_pct(signed, n_forms) or 0),
             note=f"{signed} of {n_forms} forms (%)", tone="neutral"),
        Tile(key="locked", label="Locked", value=round(_pct(locked, n_forms) or 0),
             note=f"{locked} of {n_forms} forms (%)", tone="neutral"),
    ]  # fmt: skip

    by_site: dict[tuple[str, str], SdvSiteRow] = {}
    for r in rows:
        key = (r.connection, r.site_code)
        row = by_site.setdefault(
            key,
            SdvSiteRow(
                connection=r.connection,
                study_code=codes.get(r.connection, r.connection),
                site_code=r.site_code,
                site_name=r.site_name,
                required=0,
                done=0,
                percent=None,
                forms_waiting=0,
                oldest_waiting_days=None,
            ),
        )
        row.required += r.sdv_required
        row.done += r.sdv_done
        if r.sdv_done < r.sdv_required:
            row.forms_waiting += 1
            age = rules.age_days(r.event_date, now)
            if age is not None and (row.oldest_waiting_days is None or age > row.oldest_waiting_days):
                row.oldest_waiting_days = age
    for row in by_site.values():
        row.percent = _pct(row.done, row.required)
    sites = sorted(by_site.values(), key=lambda x: (x.percent if x.percent is not None else 101, x.site_code))

    by_visit: dict[str, SdvVisitRow] = {}
    for r in rows:
        visit_key = r.event_id or ""
        v = by_visit.setdefault(
            visit_key,
            SdvVisitRow(
                event_id=visit_key,
                event_name=r.event_name or visit_key or "—",
                required=0,
                done=0,
                percent=None,
            ),
        )
        v.required += r.sdv_required
        v.done += r.sdv_done
    for v in by_visit.values():
        v.percent = _pct(v.done, v.required)

    views = {"waiting": len(waiting_rows), "complete": len(rows) - len(waiting_rows), "all": len(rows)}
    if view == "waiting":
        listed = list(waiting_rows)
    elif view == "complete":
        listed = [r for r in rows if r.sdv_done >= r.sdv_required]
    else:
        listed = list(rows)
    listed.sort(
        key=lambda r: (r.event_date or datetime.max.replace(tzinfo=UTC), r.subject_id, r.form_id or "")
    )
    out_rows = [
        SdvFormRow(
            id=r.id,
            connection=r.connection,
            study_code=codes.get(r.connection, r.connection),
            site_code=r.site_code,
            site_name=r.site_name,
            subject_id=r.subject_id,
            event_name=r.event_name,
            event_date=r.event_date,
            form_label=r.form_name or r.form_id or rules.VISIT_DATE_LABEL,
            kind=r.kind,
            required=r.sdv_required,
            done=r.sdv_done,
            percent=_pct(r.sdv_done, r.sdv_required),
            status="complete" if r.sdv_done >= r.sdv_required else "waiting",
            days_since_visit=rules.age_days(r.event_date, now),
            last_sdv_at=r.last_sdv_at,
            data_review_at=r.data_review_at,
            signed_at=r.signed_at,
            locked_at=r.locked_at,
        )
        for r in listed[offset : offset + limit]
    ]
    return SdvOut(
        scope=sc.id,
        multi=sc.multi,
        environment=sc.environment,
        tiles=tiles,
        summary=summary,
        sites=sites,
        visits=sorted(by_visit.values(), key=lambda v: v.event_id),
        forms=out_rows,
        total=len(listed),
        views=views,
        studies=[{"connection": n, "study_code": codes.get(n, n)} for n in sc.names],
        site_options=[
            {
                "id": f"{conn}:{code}" if sc.multi else code,
                "label": f"{codes.get(conn, conn)} · {code} · {nm}" if sc.multi else f"{code} · {nm}",
            }
            for conn, code, nm in site_names
        ],
        form_options=[
            *({"id": fid, "label": f"{fid} · {fname}" if fname != fid else fid} for fid, fname in form_names),
            *(
                [{"id": rules.VISIT_DATE, "label": "Visit date"}]
                if any(r.kind == "event_date" for r in rows_all)
                else []
            ),
        ],
        visit_options=[{"id": eid, "label": name} for eid, name in visit_names],
        rules=SDV_RULES,
    )


@router.get("/sdv/export.xlsx")
async def export_sdv(
    request: Request,
    db: Db,
    user: Exporter,
    settings: Config,
    scope: Annotated[str | None, Query(max_length=64)] = None,
    study: Annotated[str | None, Query(max_length=64)] = None,
    view: SdvView = "waiting",
    site: Annotated[str | None, Query(max_length=130)] = None,
    form: Annotated[str | None, Query(max_length=64)] = None,
    visit: Annotated[str | None, Query(max_length=64)] = None,
    visit_from: date | None = None,
    visit_to: date | None = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> Response:
    """The SDV list as on screen (same view and filters), with site and visit progress."""
    sc = await _scope(db, user, settings, scope)
    data = await sdv_view(
        db, user, settings, scope=sc.id, study=study, view=view, site=site, form=form, visit=visit,
        visit_from=visit_from, visit_to=visit_to, search=search, limit=10**7, offset=0,
    )  # fmt: skip
    forms = Sheet(
        "SDV forms",
        [
            "Study", "Site", "Site name", "Subject", "Visit", "Visit date", "Form", "Fields verified",
            "Fields needing SDV", "% verified", "Status", "Days since visit", "Last verified",
            "Data reviewed", "Signed", "Locked",
        ],
        [
            [
                f.study_code, f.site_code, f.site_name, f.subject_id, f.event_name, _day(f.event_date),
                f.form_label, f.done, f.required, f.percent,
                "Complete" if f.status == "complete" else "Waiting",
                f.days_since_visit, _day(f.last_sdv_at), _day(f.data_review_at), _day(f.signed_at),
                _day(f.locked_at),
            ]
            for f in data.forms
        ],
    )  # fmt: skip
    sites = Sheet(
        "By site",
        ["Study", "Site", "Site name", "Fields verified", "Fields needing SDV", "% verified", "Forms waiting",
         "Oldest waiting (days)"],
        [[r.study_code, r.site_code, r.site_name, r.done, r.required, r.percent, r.forms_waiting,
          r.oldest_waiting_days] for r in data.sites],
    )  # fmt: skip
    visits = Sheet(
        "By visit",
        ["Visit", "Fields verified", "Fields needing SDV", "% verified"],
        [[v.event_name, v.done, v.required, v.percent] for v in data.visits],
    )
    filters: dict[str, object] = {
        "view": view, "study": study, "site": site, "form": form, "visit": visit, "visit from": visit_from,
        "visit to": visit_to, "subject": search,
    }  # fmt: skip
    about = [("SDV", SDV_RULES["sdv"]), ("Review", SDV_RULES["review"])]
    return _xlsx(
        request, db, user, report="SDV", sc=sc, filters=filters, sheets=[forms, sites, visits],
        about=about, rows=len(data.forms),
    )  # fmt: skip
