"""Data Management API (/api/v1/data-management). Hidden (404) unless DATA_MANAGEMENT_ENABLED=true."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.audit.service import record_event
from app.auth.rbac import CurrentUser, Permission, require
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.studies.clock import today

from . import rules
from .models import DmMissingItem, DmPendingForm, DmQuery
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
    last_run: SyncRunOut | None
    last_success_at: datetime | None


class StatusOut(BaseModel):
    connections: list[ConnectionOut]
    can_sync: bool
    demo: bool
    site_answer_days: int
    approval_days: int
    sync_minutes: int
    rules: dict[str, str]


def _run_out(run: object | None) -> SyncRunOut | None:
    return SyncRunOut.model_validate(run, from_attributes=True) if run is not None else None


@router.get("/status", response_model=StatusOut)
def status(db: Db, user: Viewer, settings: Config) -> StatusOut:
    runs = last_runs(db, user.tenant_id)
    conns = connections(settings)
    return StatusOut(
        connections=[
            ConnectionOut(
                name=name,
                environment=env,
                last_run=_run_out(runs.get(name)),
                last_success_at=(ok.finished_at if (ok := last_success(db, user.tenant_id, name)) else None),
            )
            for name, env in conns.items()
        ],
        can_sync=user.can(Permission.DM_SYNC),
        demo=is_demo(settings),
        site_answer_days=settings.dm_site_answer_days,
        approval_days=settings.dm_approval_days,
        sync_minutes=settings.data_management_sync_minutes,
        rules=rules.RULES,
    )


class SyncRequest(BaseModel):
    connection: str


@router.post("/sync", response_model=SyncRunOut)
async def sync_now(body: SyncRequest, request: Request, db: Db, user: Syncer, settings: Config) -> SyncRunOut:
    if body.connection.lower() not in connections(settings):
        raise HTTPException(404, "No such Viedoc connection.")
    run = await sync_connection(
        db, settings, tenant_id=user.tenant_id, name=body.connection, triggered_by=user.name
    )
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


async def _connection(db: Session, user: CurrentUser, settings: Settings, name: str | None) -> str:
    conns = connections(settings)
    chosen = (name or next(iter(conns))).lower()
    if chosen not in conns:
        raise HTTPException(404, "No such Viedoc connection.")
    # The demo study syncs itself on first use; real Viedoc studies wait for "Sync now" or the schedule.
    if chosen == DEMO_CONNECTION and last_success(db, user.tenant_id, chosen) is None:
        await sync_connection(
            db, settings, tenant_id=user.tenant_id, name=chosen, triggered_by="system (first use)"
        )
    return chosen


class Tile(BaseModel):
    key: str
    label: str
    value: int
    note: str
    tone: Literal["good", "info", "warn", "bad", "neutral"]


class SiteRow(BaseModel):
    site_code: str
    site_name: str
    open_at_site: int
    awaiting_approval: int
    over_target: int
    oldest_days: int | None
    missing_items: int
    pending_forms: int


class BucketRow(BaseModel):
    label: str
    open_at_site: int
    awaiting_approval: int


class FormRow(BaseModel):
    form: str
    open: int


class OverviewOut(BaseModel):
    connection: str
    environment: str
    study_code: str | None
    as_of: datetime | None
    tiles: list[Tile]
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
    connection: Annotated[str | None, Query(max_length=64)] = None,
) -> OverviewOut:
    name = await _connection(db, user, settings, connection)
    now = today()
    queries = db.scalars(
        select(DmQuery).where(DmQuery.tenant_id == user.tenant_id, DmQuery.connection == name)
    ).all()
    missing = db.scalars(
        select(DmMissingItem).where(
            DmMissingItem.tenant_id == user.tenant_id, DmMissingItem.connection == name
        )
    ).all()
    pending = db.scalars(
        select(DmPendingForm).where(
            DmPendingForm.tenant_id == user.tenant_id, DmPendingForm.connection == name
        )
    ).all()
    sa, ap = settings.dm_site_answer_days, settings.dm_approval_days

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
             note=f"{red_open} over {sa} working days" if red_open else f"None over {sa} working days",
             tone="bad" if red_open else "neutral"),
        Tile(key="awaiting_approval", label="Answered, awaiting approval", value=len(awaiting),
             note=f"{red_wait} over {ap} working days" if red_wait else f"None over {ap} working days",
             tone="bad" if red_wait else ("warn" if awaiting else "good")),
        Tile(key="closed_30", label="Closed in the last 30 days", value=len(closed_recent),
             note=f"{reopened} queries were sent back at least once", tone="info"),
        Tile(key="missing_items", label="Unconfirmed missing data", value=len(unconfirmed),
             note="Blank fields not yet confirmed by the site", tone="warn" if unconfirmed else "good"),
        Tile(key="pending_forms", label="Pending forms", value=len(pending),
             note="Expected but not completed", tone="warn" if pending else "good"),
    ]  # fmt: skip

    site_names: dict[str, str] = {}
    for q in queries:
        site_names.setdefault(q.site_code, q.site_name)
    for p in pending:
        site_names.setdefault(p.site_code, p.site_name)
    for m in missing:
        site_names.setdefault(m.site_code, m.site_code)
    by_site: dict[str, SiteRow] = {
        code: SiteRow(site_code=code, site_name=nm, open_at_site=0, awaiting_approval=0, over_target=0,
                      oldest_days=None, missing_items=0, pending_forms=0)
        for code, nm in site_names.items()
    }  # fmt: skip
    for q in open_q + awaiting:
        row = by_site[q.site_code]
        if q.state == "open_at_site":
            row.open_at_site += 1
        else:
            row.awaiting_approval += 1
        row.over_target += flag_of(q) == "red"
        age = rules.age_days(q.raised_at, now)
        if age is not None and (row.oldest_days is None or age > row.oldest_days):
            row.oldest_days = age
    for m in unconfirmed:
        by_site[m.site_code].missing_items += 1
    for p in pending:
        by_site[p.site_code].pending_forms += 1
    sites = sorted(
        by_site.values(), key=lambda r: (-r.over_target, -(r.open_at_site + r.awaiting_approval), r.site_code)
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
    form_counts = Counter(q.form_name or q.form_id or "—" for q in open_q + awaiting)
    success = last_success(db, user.tenant_id, name)
    env = connections(settings)[name]
    forms_seen = sorted({(q.form_id or "", q.form_name or q.form_id or "") for q in queries if q.form_id})
    return OverviewOut(
        connection=name,
        environment=env,
        study_code=queries[0].study_code
        if queries
        else (str(success.counts.get("study")) if success else None),
        as_of=success.finished_at if success else None,
        tiles=tiles,
        sites=sites,
        ageing=list(ageing.values()),
        forms=[FormRow(form=f, open=n) for f, n in form_counts.most_common()],
        site_options=[{"id": code, "label": f"{code} · {nm}"} for code, nm in sorted(site_names.items())],
        form_options=[
            {"id": fid, "label": f"{fid} · {fname}" if fname != fid else fid} for fid, fname in forms_seen
        ],
    )


class QueryOut(BaseModel):
    id: str
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
    user_name: str | None
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
        id=q.id,
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
    connection: Annotated[str | None, Query(max_length=64)] = None,
    state: State | None = None,
    site: Annotated[str | None, Query(max_length=64)] = None,
    form: Annotated[str | None, Query(max_length=64)] = None,
    flag: Literal["red", "amber", "green"] | None = None,
    reopened: bool = False,
    search: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> QueryListOut:
    name = await _connection(db, user, settings, connection)
    now = today()
    stmt = select(DmQuery).where(DmQuery.tenant_id == user.tenant_id, DmQuery.connection == name)
    if site:
        stmt = stmt.where(DmQuery.site_code == site)
    if form:
        stmt = stmt.where(DmQuery.form_id == form)
    if reopened:
        stmt = stmt.where(DmQuery.reopen_count > 0)
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
    if state == "not_closed":
        rows = [r for r in rows if r.state != "closed"]
    elif state:
        rows = [r for r in rows if r.state == state]
    if flag:
        rows = [r for r in rows if r.flag == flag]
    order = {"red": 0, "amber": 1, "green": 2, "none": 3}
    rows.sort(key=lambda r: (order.get(r.flag, 9), -(r.clock_days or 0), -(r.age_days or 0), r.query_number))
    return QueryListOut(queries=rows[offset : offset + limit], total=len(rows), counts=dict(counts))


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
