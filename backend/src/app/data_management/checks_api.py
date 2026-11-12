"""Data Management Step 3: missing data and labs (/missing, /labs and their Excel downloads).

Registered on the module's router by api.py. Same pattern as SDV: tiles, breakdowns, a filtered list
with quick views, and an Excel copy of the list on screen for System Admin and Data Manager.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import HTTPException, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.rbac import CurrentUser
from app.core.config import Settings
from app.reports.excel import Sheet
from app.studies.clock import today

from . import rules
from .api import Config, Db, Exporter, Scope, Tile, Viewer, _day, _scope, _study_codes, _xlsx, router
from .models import DmLabResult, DmMissingItem, DmPendingForm

UNCONFIRMED = "unconfirmed missing data"
UPGRADE = "pending form upgrade"

MISSING_RULES = {
    "missing": (
        "Missing fields: fields saved blank that the site has not yet confirmed as missing (Viedoc: "
        "unconfirmed missing data). Pending forms: forms expected at a visit but not completed. Forms "
        "awaiting upgrade: forms waiting to be moved to a new study design version."
    ),
    "target": (
        "The site's clock runs from when the form was saved with the field blank (missing fields) or from "
        "when the form became pending. Target in working days; overdue (red) when over target, amber on "
        "the last day."
    ),
}

LAB_RULES = {
    "labs": (
        "Lab results are read from the lab forms during the sync and kept as flags only: no result "
        "values and no normal-range numbers are stored. Open Viedoc to see a value."
    ),
    "range": (
        "Out of range: the result is below the lower or above the upper limit of the normal range entered "
        "on the form (a result entered as '<' or '>' counts only when it lies wholly outside the range). "
        "Results without a number (e.g. urine dipstick) are not range-checked."
    ),
    "evaluation": (
        "Evaluation is the investigator's assessment on the form: normal, abnormal not clinically "
        "significant (NCS) or abnormal clinically significant (CS); a CS result should carry an AE/MH "
        "reference. 'Out of range but evaluated normal' is worth checking with the site."
    ),
}


def _options(sc: Scope, codes: dict[str, str], sites: set[tuple[str, str, str]]) -> list[dict[str, str]]:
    return [
        {
            "id": f"{conn}:{code}" if sc.multi else code,
            "label": f"{codes.get(conn, conn)} · {code} · {name}" if sc.multi else f"{code} · {name}",
        }
        for conn, code, name in sorted(sites)
    ]


def _site_match(site: str | None, connection: str, site_code: str) -> bool:
    if not site:
        return True
    conn, _, code = site.rpartition(":")
    return site_code == code and (not conn or connection == conn)


def _between(day: datetime | None, start: date | None, end: date | None) -> bool:
    if not (start or end):
        return True
    if day is None:
        return False
    d = day.date()
    return (not start or d >= start) and (not end or d <= end)


# --- Missing data -----------------------------------------------------------------------------------

MissingView = Literal["fields", "pending", "upgrade", "overdue"]
MissingKind = Literal["field", "pending", "upgrade"]


class MissingRow(BaseModel):
    id: str
    kind: MissingKind
    connection: str
    study_code: str
    site_code: str
    site_name: str
    subject_id: str
    event_id: str | None
    event_name: str | None
    event_date: datetime | None
    form_id: str | None
    form_label: str
    item_label: str | None
    since: datetime | None
    days: int | None
    working_days: int | None
    flag: str


class MissingSiteRow(BaseModel):
    connection: str
    study_code: str
    site_code: str
    site_name: str
    fields: int
    overdue: int
    pending_forms: int
    upgrades: int
    oldest_days: int | None


class MissingCountRow(BaseModel):
    id: str
    label: str
    fields: int
    pending_forms: int


class MissingFieldRow(BaseModel):
    form_label: str
    item_label: str
    subjects: int


class MissingSubjectRow(BaseModel):
    connection: str
    study_code: str
    site_code: str
    subject_id: str
    fields: int
    pending_forms: int
    oldest_days: int | None


class MissingOut(BaseModel):
    scope: str
    multi: bool
    environment: str
    tiles: list[Tile]
    sites: list[MissingSiteRow]
    visits: list[MissingCountRow]
    forms: list[MissingCountRow]
    top_fields: list[MissingFieldRow]
    """The fields left blank for the most subjects."""
    subjects: list[MissingSubjectRow]
    """Subjects with the most gaps (missing fields plus pending forms)."""
    items: list[MissingRow]
    total: int
    views: dict[str, int]
    studies: list[dict[str, str]]
    site_options: list[dict[str, str]]
    form_options: list[dict[str, str]]
    visit_options: list[dict[str, str]]
    target_days: int
    rules: dict[str, str]


def _missing_rows(db: Session, user: CurrentUser, settings: Settings, sc: Scope) -> list[MissingRow]:
    now = today()
    codes = _study_codes(db, user.tenant_id, sc.names)
    target = settings.dm_site_answer_days
    rows: list[MissingRow] = []

    def row(kind: MissingKind, **kw: object) -> MissingRow:
        since = kw.pop("since")
        assert since is None or isinstance(since, datetime)
        wd = rules.working_days(since.date(), now) if since else None
        conn = str(kw["connection"])
        return MissingRow(
            kind=kind,
            study_code=codes.get(conn, conn),
            since=since,
            days=rules.age_days(since, now),
            working_days=wd,
            flag=rules.flag("open_at_site", wd, target, target),
            **kw,  # type: ignore[arg-type]
        )

    for m in db.scalars(
        select(DmMissingItem).where(
            DmMissingItem.tenant_id == user.tenant_id, DmMissingItem.connection.in_(sc.names)
        )
    ):
        kind_text = m.query_type.lower()
        if kind_text not in (UNCONFIRMED, UPGRADE):
            continue
        rows.append(
            row(
                "field" if kind_text == UNCONFIRMED else "upgrade",
                id=m.id,
                connection=m.connection,
                site_code=m.site_code,
                site_name=m.site_name or "",
                subject_id=m.subject_id,
                event_id=m.event_id,
                event_name=m.event_name,
                event_date=m.event_date,
                form_id=m.form_id,
                form_label=m.form_name or m.form_id or "—",
                item_label=(m.item_label or m.item_id) if kind_text == UNCONFIRMED else None,
                since=m.saved_at,
            )
        )
    for p in db.scalars(
        select(DmPendingForm).where(
            DmPendingForm.tenant_id == user.tenant_id, DmPendingForm.connection.in_(sc.names)
        )
    ):
        rows.append(
            row(
                "pending",
                id=p.id,
                connection=p.connection,
                site_code=p.site_code,
                site_name=p.site_name,
                subject_id=p.subject_id,
                event_id=p.event_id,
                event_name=p.event_name,
                event_date=None,
                form_id=p.form_id,
                form_label=p.form_name or p.form_id or "—",
                item_label=None,
                since=p.pending_since,
            )
        )
    return rows


@router.get("/missing", response_model=MissingOut)
async def missing_view(
    db: Db,
    user: Viewer,
    settings: Config,
    scope: Annotated[str | None, Query(max_length=64)] = None,
    study: Annotated[str | None, Query(max_length=64)] = None,
    view: MissingView = "fields",
    site: Annotated[str | None, Query(max_length=130)] = None,
    form: Annotated[str | None, Query(max_length=64)] = None,
    visit: Annotated[str | None, Query(max_length=64)] = None,
    since_from: Annotated[date | None, Query(description="Missing or pending since, on or after")] = None,
    since_to: Annotated[date | None, Query(description="Missing or pending since, on or before")] = None,
    search: Annotated[str | None, Query(max_length=100, description="Subject ID")] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 500,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> MissingOut:
    if since_from and since_to and since_from > since_to:
        raise HTTPException(422, "The start of the date range is after its end.")
    sc = await _scope(db, user, settings, scope)
    codes = _study_codes(db, user.tenant_id, sc.names)
    every = _missing_rows(db, user, settings, sc)
    site_names = {(r.connection, r.site_code, r.site_name) for r in every}
    form_names = {(r.form_id or "", r.form_label) for r in every if r.form_id}
    visit_names = {(r.event_id or "", r.event_name or r.event_id or "") for r in every if r.event_id}

    rows = [
        r
        for r in every
        if (not study or r.connection == study.lower())
        and _site_match(site, r.connection, r.site_code)
        and (not form or r.form_id == form)
        and (not visit or r.event_id == visit)
        and _between(r.since, since_from, since_to)
        and (not search or search.lower() in r.subject_id.lower())
    ]
    fields = [r for r in rows if r.kind == "field"]
    pending = [r for r in rows if r.kind == "pending"]
    upgrades = [r for r in rows if r.kind == "upgrade"]
    overdue = [r for r in rows if r.kind != "upgrade" and r.flag == "red"]
    oldest_pending = max((r.days or 0 for r in pending), default=None)
    subjects_affected = {(r.connection, r.subject_id) for r in fields + pending}
    target = settings.dm_site_answer_days
    tiles = [
        Tile(key="fields", label="Missing fields", value=len(fields),
             note=f"Unconfirmed by the site · {len({(r.connection, r.subject_id) for r in fields})} subjects",
             tone="warn" if fields else "good"),
        Tile(key="overdue", label="Overdue", value=len(overdue),
             note=f"Over {target} working days (fields and forms)", tone="bad" if overdue else "good"),
        Tile(key="pending", label="Pending forms", value=len(pending),
             note=f"Oldest {oldest_pending} days" if oldest_pending is not None else "Not completed yet",
             tone="warn" if pending else "good"),
        Tile(key="subjects", label="Subjects with gaps", value=len(subjects_affected),
             note="Missing fields or pending forms", tone="neutral"),
        Tile(key="upgrades", label="Forms awaiting upgrade", value=len(upgrades),
             note="Waiting for a new design version", tone="info" if upgrades else "neutral"),
    ]  # fmt: skip

    by_site: dict[tuple[str, str], MissingSiteRow] = {}
    for r in rows:
        srow = by_site.setdefault(
            (r.connection, r.site_code),
            MissingSiteRow(connection=r.connection, study_code=r.study_code, site_code=r.site_code,
                           site_name=r.site_name, fields=0, overdue=0, pending_forms=0, upgrades=0,
                           oldest_days=None),
        )  # fmt: skip
        if r.kind == "field":
            srow.fields += 1
        elif r.kind == "pending":
            srow.pending_forms += 1
        else:
            srow.upgrades += 1
        if r.kind != "upgrade":
            srow.overdue += r.flag == "red"
            if r.days is not None and (srow.oldest_days is None or r.days > srow.oldest_days):
                srow.oldest_days = r.days
    sites = sorted(by_site.values(), key=lambda x: (-x.overdue, -(x.fields + x.pending_forms), x.site_code))

    def counts(key: str) -> list[MissingCountRow]:
        out: dict[str, MissingCountRow] = {}
        for r in fields + pending:
            ident = (r.event_id if key == "visit" else r.form_id) or ""
            label = (r.event_name if key == "visit" else r.form_label) or ident or "—"
            c = out.setdefault(ident, MissingCountRow(id=ident, label=label, fields=0, pending_forms=0))
            if r.kind == "field":
                c.fields += 1
            else:
                c.pending_forms += 1
        return sorted(out.values(), key=lambda c: (-(c.fields + c.pending_forms), c.label))

    blank: dict[tuple[str, str], set[tuple[str, str]]] = defaultdict(set)
    for r in fields:
        blank[(r.form_label, r.item_label or "—")].add((r.connection, r.subject_id))
    top_fields = sorted(
        (MissingFieldRow(form_label=f, item_label=i, subjects=len(s)) for (f, i), s in blank.items()),
        key=lambda x: (-x.subjects, x.form_label, x.item_label),
    )[:10]

    by_subject: dict[tuple[str, str], MissingSubjectRow] = {}
    for r in fields + pending:
        subj = by_subject.setdefault(
            (r.connection, r.subject_id),
            MissingSubjectRow(connection=r.connection, study_code=r.study_code, site_code=r.site_code,
                              subject_id=r.subject_id, fields=0, pending_forms=0, oldest_days=None),
        )  # fmt: skip
        if r.kind == "field":
            subj.fields += 1
        else:
            subj.pending_forms += 1
        if r.days is not None and (subj.oldest_days is None or r.days > subj.oldest_days):
            subj.oldest_days = r.days
    subjects = sorted(by_subject.values(), key=lambda x: (-(x.fields + x.pending_forms), x.subject_id))[:10]

    listed = {"fields": fields, "pending": pending, "upgrade": upgrades, "overdue": overdue}[view]
    order = {"red": 0, "amber": 1, "green": 2, "none": 3}
    listed = sorted(listed, key=lambda r: (order.get(r.flag, 9), -(r.days or 0), r.subject_id, r.form_label))
    return MissingOut(
        scope=sc.id,
        multi=sc.multi,
        environment=sc.environment,
        tiles=tiles,
        sites=sites,
        visits=counts("visit"),
        forms=counts("form"),
        top_fields=top_fields,
        subjects=subjects,
        items=listed[offset : offset + limit],
        total=len(listed),
        views={
            "fields": len(fields),
            "pending": len(pending),
            "upgrade": len(upgrades),
            "overdue": len(overdue),
        },  # fmt: skip
        studies=[{"connection": n, "study_code": codes.get(n, n)} for n in sc.names],
        site_options=_options(sc, codes, site_names),
        form_options=[
            {"id": fid, "label": f"{fid} · {fn}" if fn != fid else fid} for fid, fn in sorted(form_names)
        ],
        visit_options=[{"id": eid, "label": name} for eid, name in sorted(visit_names)],
        target_days=target,
        rules=MISSING_RULES,
    )


KIND_LABELS = {"field": "Missing field", "pending": "Pending form", "upgrade": "Awaiting upgrade"}
FLAG_LABELS = {"red": "Overdue", "amber": "Last day of target", "green": "Within target", "none": ""}


@router.get("/missing/export.xlsx")
async def export_missing(
    request: Request,
    db: Db,
    user: Exporter,
    settings: Config,
    scope: Annotated[str | None, Query(max_length=64)] = None,
    study: Annotated[str | None, Query(max_length=64)] = None,
    view: MissingView = "fields",
    site: Annotated[str | None, Query(max_length=130)] = None,
    form: Annotated[str | None, Query(max_length=64)] = None,
    visit: Annotated[str | None, Query(max_length=64)] = None,
    since_from: date | None = None,
    since_to: date | None = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> Response:
    """The missing data list as on screen (same view and filters), with site and subject summaries."""
    sc = await _scope(db, user, settings, scope)
    data = await missing_view(
        db, user, settings, scope=sc.id, study=study, view=view, site=site, form=form, visit=visit,
        since_from=since_from, since_to=since_to, search=search, limit=10**7, offset=0,
    )  # fmt: skip
    items = Sheet(
        "Missing data",
        ["Study", "Site", "Site name", "Subject", "Visit", "Visit date", "Form", "Field", "Type", "Since",
         "Days", "Working days", "Target"],
        [[r.study_code, r.site_code, r.site_name, r.subject_id, r.event_name, _day(r.event_date),
          r.form_label, r.item_label, KIND_LABELS[r.kind], _day(r.since), r.days, r.working_days,
          FLAG_LABELS.get(r.flag, "")] for r in data.items],
    )  # fmt: skip
    sites = Sheet(
        "By site",
        ["Study", "Site", "Site name", "Missing fields", "Overdue", "Pending forms", "Awaiting upgrade",
         "Oldest (days)"],
        [[r.study_code, r.site_code, r.site_name, r.fields, r.overdue, r.pending_forms, r.upgrades,
          r.oldest_days] for r in data.sites],
    )  # fmt: skip
    subjects = Sheet(
        "Most gaps",
        ["Study", "Site", "Subject", "Missing fields", "Pending forms", "Oldest (days)"],
        [[r.study_code, r.site_code, r.subject_id, r.fields, r.pending_forms, r.oldest_days]
         for r in data.subjects],
    )  # fmt: skip
    filters: dict[str, object] = {
        "view": view, "study": study, "site": site, "form": form, "visit": visit, "since from": since_from,
        "since to": since_to, "subject": search,
    }  # fmt: skip
    about = [("Missing data", MISSING_RULES["missing"]), ("Target", MISSING_RULES["target"])]
    return _xlsx(
        request, db, user, report="missing data", sc=sc, filters=filters, sheets=[items, sites, subjects],
        about=about, rows=len(data.items),
    )  # fmt: skip


# --- Labs ---------------------------------------------------------------------------------------------

LabView = Literal[
    "flagged", "out_of_range", "clin_sig", "missing", "no_evaluation", "no_unit", "no_range", "all"
]
EVALUATION_LABELS = {
    "normal": "Normal",
    "abnormal_ncs": "Abnormal, not clinically significant",
    "abnormal_cs": "Abnormal, clinically significant",
    "other": "Other",
    "missing": "Not evaluated",
}


def lab_issues(r: DmLabResult) -> list[str]:
    """What Data Management should look at for one result (empty when nothing)."""
    issues: list[str] = []
    if r.status == "missing":
        issues.append("Result missing")
    if r.out_of_range:
        issues.append(f"Out of range ({r.out_of_range})")
        if r.evaluation == "normal":
            issues.append("Out of range but evaluated normal")
    if r.evaluation == "abnormal_cs":
        issues.append("Clinically significant")
    if r.cs_reference_missing:
        issues.append("No AE/MH reference")
    if r.evaluation == "missing":
        issues.append("Not evaluated")
    if r.unit_missing:
        issues.append("No unit")
    if r.range_missing:
        issues.append("No normal range")
    return issues


_LAB_VIEWS: dict[str, Callable[[DmLabResult], bool]] = {
    "flagged": lambda r: bool(lab_issues(r)),
    "out_of_range": lambda r: bool(r.out_of_range),
    "clin_sig": lambda r: r.evaluation == "abnormal_cs",
    "missing": lambda r: r.status == "missing",
    "no_evaluation": lambda r: r.evaluation == "missing",
    "no_unit": lambda r: r.unit_missing,
    "no_range": lambda r: r.range_missing,
    "all": lambda r: True,
}


class LabRow(BaseModel):
    id: str
    connection: str
    study_code: str
    site_code: str
    site_name: str
    subject_id: str
    event_id: str | None
    event_name: str | None
    event_date: datetime | None
    form_id: str
    form_label: str
    analyte: str
    status: str
    out_of_range: str | None
    evaluation: str | None
    evaluation_label: str | None
    issues: list[str]


class LabAnalyteRow(BaseModel):
    form_label: str
    analyte: str
    expected: int
    reported: int
    missing: int
    not_done: int
    out_of_range: int
    clin_sig: int
    no_range: int
    no_unit: int
    missing_percent: float | None


class LabSiteRow(BaseModel):
    connection: str
    study_code: str
    site_code: str
    site_name: str
    reported: int
    missing: int
    out_of_range: int
    clin_sig: int
    flagged: int


class LabsOut(BaseModel):
    scope: str
    multi: bool
    environment: str
    tiles: list[Tile]
    analytes: list[LabAnalyteRow]
    sites: list[LabSiteRow]
    results: list[LabRow]
    total: int
    views: dict[str, int]
    studies: list[dict[str, str]]
    site_options: list[dict[str, str]]
    form_options: list[dict[str, str]]
    visit_options: list[dict[str, str]]
    analyte_options: list[dict[str, str]]
    rules: dict[str, str]


def _pct(part: int, whole: int) -> float | None:
    return round(part / whole * 100, 1) if whole else None


@router.get("/labs", response_model=LabsOut)
async def labs_view(
    db: Db,
    user: Viewer,
    settings: Config,
    scope: Annotated[str | None, Query(max_length=64)] = None,
    study: Annotated[str | None, Query(max_length=64)] = None,
    view: LabView = "flagged",
    site: Annotated[str | None, Query(max_length=130)] = None,
    form: Annotated[str | None, Query(max_length=64)] = None,
    visit: Annotated[str | None, Query(max_length=64)] = None,
    analyte: Annotated[str | None, Query(max_length=200)] = None,
    visit_from: date | None = None,
    visit_to: date | None = None,
    search: Annotated[str | None, Query(max_length=100, description="Subject ID")] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 500,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> LabsOut:
    if visit_from and visit_to and visit_from > visit_to:
        raise HTTPException(422, "The start of the date range is after its end.")
    sc = await _scope(db, user, settings, scope)
    codes = _study_codes(db, user.tenant_id, sc.names)
    every = list(
        db.scalars(
            select(DmLabResult).where(
                DmLabResult.tenant_id == user.tenant_id, DmLabResult.connection.in_(sc.names)
            )
        )
    )
    for r in every:
        codes.setdefault(r.connection, r.study_code)

    def form_label(r: DmLabResult) -> str:
        return r.form_name or r.form_id

    rows = [
        r
        for r in every
        if (not study or r.connection == study.lower())
        and _site_match(site, r.connection, r.site_code)
        and (not form or r.form_id == form)
        and (not visit or r.event_id == visit)
        and (not analyte or r.analyte == analyte)
        and _between(r.event_date, visit_from, visit_to)
        and (not search or search.lower() in r.subject_id.lower())
    ]
    reported = [r for r in rows if r.status == "reported"]
    missing = [r for r in rows if r.status == "missing"]
    not_done = [r for r in rows if r.status == "not_done"]
    high = sum(r.out_of_range == "high" for r in rows)
    low = sum(r.out_of_range == "low" for r in rows)
    cs = [r for r in rows if r.evaluation == "abnormal_cs"]
    cs_no_ref = sum(r.cs_reference_missing for r in rows)
    no_eval = sum(r.evaluation == "missing" for r in rows)
    normal_but_out = sum(bool(r.out_of_range) and r.evaluation == "normal" for r in rows)
    no_range = sum(r.range_missing for r in rows)
    no_unit = sum(r.unit_missing for r in rows)
    expected = len(reported) + len(missing)
    tiles = [
        Tile(key="reported", label="Results reported (%)", value=round(_pct(len(reported), expected) or 0),
             note=f"{len(reported)} of {expected} expected · {len(not_done)} not done", tone="info"),
        Tile(key="missing", label="Results missing", value=len(missing), note="Expected but blank",
             tone="warn" if missing else "good"),
        Tile(key="out_of_range", label="Out of range", value=high + low, note=f"{high} high · {low} low",
             tone="warn" if high + low else "good"),
        Tile(key="clin_sig", label="Clinically significant", value=len(cs),
             note=f"{cs_no_ref} without AE/MH reference" if cs_no_ref else "All have an AE/MH reference",
             tone="bad" if cs_no_ref else ("warn" if cs else "good")),
        Tile(key="checks", label="To check with the site", value=no_eval + normal_but_out,
             note=f"{no_eval} not evaluated · {normal_but_out} out of range but 'Normal'",
             tone="warn" if no_eval + normal_but_out else "good"),
        Tile(key="set_up", label="Missing unit or range", value=no_unit + no_range,
             note=f"{no_unit} no unit · {no_range} no normal range", tone="neutral"),
    ]  # fmt: skip

    by_analyte: dict[tuple[str, str], LabAnalyteRow] = {}
    for r in rows:
        a = by_analyte.setdefault(
            (form_label(r), r.analyte),
            LabAnalyteRow(form_label=form_label(r), analyte=r.analyte, expected=0, reported=0, missing=0,
                          not_done=0, out_of_range=0, clin_sig=0, no_range=0, no_unit=0,
                          missing_percent=None),
        )  # fmt: skip
        a.expected += r.status != "not_done"
        a.reported += r.status == "reported"
        a.missing += r.status == "missing"
        a.not_done += r.status == "not_done"
        a.out_of_range += bool(r.out_of_range)
        a.clin_sig += r.evaluation == "abnormal_cs"
        a.no_range += r.range_missing
        a.no_unit += r.unit_missing
    for a in by_analyte.values():
        a.missing_percent = _pct(a.missing, a.expected)
    analytes = sorted(
        by_analyte.values(),
        key=lambda a: (-(a.missing_percent or 0), -a.out_of_range, a.form_label, a.analyte),
    )

    by_site: dict[tuple[str, str], LabSiteRow] = {}
    for r in rows:
        srow = by_site.setdefault(
            (r.connection, r.site_code),
            LabSiteRow(connection=r.connection, study_code=codes.get(r.connection, r.connection),
                       site_code=r.site_code, site_name=r.site_name, reported=0, missing=0, out_of_range=0,
                       clin_sig=0, flagged=0),
        )  # fmt: skip
        srow.reported += r.status == "reported"
        srow.missing += r.status == "missing"
        srow.out_of_range += bool(r.out_of_range)
        srow.clin_sig += r.evaluation == "abnormal_cs"
        srow.flagged += bool(lab_issues(r))
    sites = sorted(by_site.values(), key=lambda x: (-x.flagged, x.site_code))

    views = {key: sum(1 for r in rows if test(r)) for key, test in _LAB_VIEWS.items()}
    listed = [r for r in rows if _LAB_VIEWS[view](r)]
    listed.sort(
        key=lambda r: (
            r.evaluation != "abnormal_cs",
            not r.out_of_range,
            r.event_date.date() if r.event_date else date.min,
            r.subject_id,
            r.form_id,
            r.analyte,
        )
    )
    return LabsOut(
        scope=sc.id,
        multi=sc.multi,
        environment=sc.environment,
        tiles=tiles,
        analytes=analytes,
        sites=sites,
        results=[
            LabRow(
                id=r.id,
                connection=r.connection,
                study_code=codes.get(r.connection, r.connection),
                site_code=r.site_code,
                site_name=r.site_name,
                subject_id=r.subject_id,
                event_id=r.event_id,
                event_name=r.event_name,
                event_date=r.event_date,
                form_id=r.form_id,
                form_label=form_label(r),
                analyte=r.analyte,
                status=r.status,
                out_of_range=r.out_of_range,
                evaluation=r.evaluation,
                evaluation_label=EVALUATION_LABELS.get(r.evaluation) if r.evaluation else None,
                issues=lab_issues(r),
            )
            for r in listed[offset : offset + limit]
        ],
        total=len(listed),
        views=views,
        studies=[{"connection": n, "study_code": codes.get(n, n)} for n in sc.names],
        site_options=_options(sc, codes, {(r.connection, r.site_code, r.site_name) for r in every}),
        form_options=[
            {"id": fid, "label": f"{fid} · {fn}" if fn != fid else fid}
            for fid, fn in sorted({(r.form_id, form_label(r)) for r in every})
        ],
        visit_options=[
            {"id": eid, "label": name}
            for eid, name in sorted({(r.event_id, r.event_name or r.event_id) for r in every if r.event_id})
        ],
        analyte_options=[{"id": a, "label": a} for a in sorted({r.analyte for r in every})],
        rules=LAB_RULES,
    )


STATUS_LABELS = {"reported": "Reported", "missing": "Missing", "not_done": "Not done"}


@router.get("/labs/export.xlsx")
async def export_labs(
    request: Request,
    db: Db,
    user: Exporter,
    settings: Config,
    scope: Annotated[str | None, Query(max_length=64)] = None,
    study: Annotated[str | None, Query(max_length=64)] = None,
    view: LabView = "flagged",
    site: Annotated[str | None, Query(max_length=130)] = None,
    form: Annotated[str | None, Query(max_length=64)] = None,
    visit: Annotated[str | None, Query(max_length=64)] = None,
    analyte: Annotated[str | None, Query(max_length=200)] = None,
    visit_from: date | None = None,
    visit_to: date | None = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> Response:
    """The lab list as on screen (same view and filters), flags only, with analyte and site summaries."""
    sc = await _scope(db, user, settings, scope)
    data = await labs_view(
        db, user, settings, scope=sc.id, study=study, view=view, site=site, form=form, visit=visit,
        analyte=analyte, visit_from=visit_from, visit_to=visit_to, search=search, limit=10**7, offset=0,
    )  # fmt: skip
    results = Sheet(
        "Lab results",
        ["Study", "Site", "Site name", "Subject", "Visit", "Visit date", "Form", "Analyte", "Result",
         "Out of range", "Evaluation", "To check"],
        [[r.study_code, r.site_code, r.site_name, r.subject_id, r.event_name, _day(r.event_date),
          r.form_label, r.analyte, STATUS_LABELS.get(r.status, r.status), r.out_of_range or "",
          r.evaluation_label or "", "; ".join(r.issues)] for r in data.results],
    )  # fmt: skip
    analytes = Sheet(
        "By analyte",
        ["Form", "Analyte", "Expected", "Reported", "Missing", "Missing %", "Not done", "Out of range",
         "Clinically significant", "No normal range", "No unit"],
        [[a.form_label, a.analyte, a.expected, a.reported, a.missing, a.missing_percent, a.not_done,
          a.out_of_range, a.clin_sig, a.no_range, a.no_unit] for a in data.analytes],
    )  # fmt: skip
    sites = Sheet(
        "By site",
        ["Study", "Site", "Site name", "Reported", "Missing", "Out of range", "Clinically significant",
         "To check"],
        [[s.study_code, s.site_code, s.site_name, s.reported, s.missing, s.out_of_range, s.clin_sig,
          s.flagged] for s in data.sites],
    )  # fmt: skip
    filters: dict[str, object] = {
        "view": view, "study": study, "site": site, "form": form, "visit": visit, "analyte": analyte,
        "visit from": visit_from, "visit to": visit_to, "subject": search,
    }  # fmt: skip
    about = [
        ("Labs", LAB_RULES["labs"]),
        ("Range", LAB_RULES["range"]),
        ("Evaluation", LAB_RULES["evaluation"]),
    ]
    return _xlsx(
        request, db, user, report="labs", sc=sc, filters=filters, sheets=[results, analytes, sites],
        about=about, rows=len(data.results),
    )  # fmt: skip
