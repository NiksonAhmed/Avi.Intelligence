"""Quality (SOPs) report: review schedule, reviews due by month, library health and the change log.

Pure calculations over the SharePoint SOP library (approved documents) and the details read from
inside each file (cover page, change history). Every figure follows a rule in `QUALITY_RULES`.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Literal

from pydantic import BaseModel

from app.connectors.sharepoint.models import DocumentKind, SopDocument, SopStatus

from .study_delivery import Option, Tile

REVIEW_WINDOW_DAYS = 30
MONTHS_AHEAD = 12
PERIODS = (3, 6, 12, 24)
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

QUALITY_RULES = {
    "review": (
        "Next review: the review date in SharePoint, or the one on the SOP's cover page. Overdue: the "
        f"review date has passed. Due soon: within the next {REVIEW_WINDOW_DAYS} days. Only approved "
        "(effective) SOPs are counted; forms and templates are reviewed with their SOP."
    ),
    "health": (
        "Library health: details that are missing or disagree, so the library can be kept audit-ready. "
        "A document can have more than one finding."
    ),
    "change_log": (
        "Changes: entries in each document's change history issued in the period. For documents "
        "without a readable change history, the date the current version took effect is used."
    ),
    "tasks": "Open review tasks: open Procedures and SOPs tasks linked to the SOP.",
}

ReviewState = Literal["overdue", "due_soon", "scheduled", "no_date"]


class ScheduleRow(BaseModel):
    id: str
    sop_number: str | None
    title: str
    version: str | None
    department: str | None
    owner: str | None
    effective_date: date | None
    review_date: date | None
    days_to_review: int | None
    state: ReviewState
    forms: int
    open_tasks: int


class MonthBucket(BaseModel):
    key: str
    """"overdue", or the month as YYYY-MM."""
    label: str
    count: int
    items: list[str]


class HealthItem(BaseModel):
    id: str
    label: str


class HealthCheck(BaseModel):
    key: str
    label: str
    description: str
    count: int
    items: list[HealthItem]


class ChangeEntry(BaseModel):
    id: str
    sop_number: str | None
    title: str
    kind: DocumentKind
    version: str
    issued: date
    changes: str | None
    basis: Literal["history", "effective"]


class Quality(BaseModel):
    tiles: list[Tile]
    schedule: list[ScheduleRow]
    by_month: list[MonthBucket]
    later: int
    """Reviews due after the months shown."""
    health: list[HealthCheck]
    changes: list[ChangeEntry]
    months: int
    department_options: list[Option]
    rules: dict[str, str]


def _day(value: datetime | None) -> date | None:
    return value.date() if value else None


def _label(doc: SopDocument) -> str:
    return f"{doc.sop_number} · {doc.title}" if doc.sop_number else doc.title


def _month_add(day: date, months: int) -> date:
    total = day.year * 12 + day.month - 1 + months
    return date(total // 12, total % 12 + 1, 1)


def review_state(review: date | None, today: date) -> ReviewState:
    if review is None:
        return "no_date"
    if review < today:
        return "overdue"
    if review <= today + timedelta(days=REVIEW_WINDOW_DAYS):
        return "due_soon"
    return "scheduled"


def build_quality(
    docs: list[SopDocument],
    open_tasks_by_sop: dict[str, int],
    today: date,
    *,
    department: str | None = None,
    months: int = 12,
) -> Quality:
    departments = sorted({d.department for d in docs if d.department})
    scoped = [d for d in docs if not department or (d.department or "").lower() == department.lower()]
    sops = [d for d in scoped if d.kind == DocumentKind.SOP]
    forms = [d for d in scoped if d.kind == DocumentKind.FORM]
    approved = [d for d in sops if d.status == SopStatus.EFFECTIVE]

    # ---- review schedule ----
    form_count: dict[str, int] = {}
    for f in docs:
        if f.kind == DocumentKind.FORM and f.parent_sop_number:
            form_count[f.parent_sop_number] = form_count.get(f.parent_sop_number, 0) + 1
    schedule: list[ScheduleRow] = []
    for d in approved:
        review = _day(d.review_date)
        schedule.append(
            ScheduleRow(
                id=d.id,
                sop_number=d.sop_number,
                title=d.title,
                version=d.version,
                department=d.department,
                owner=d.owner,
                effective_date=_day(d.effective_date),
                review_date=review,
                days_to_review=(review - today).days if review else None,
                state=review_state(review, today),
                forms=form_count.get(d.sop_number or "", 0),
                open_tasks=open_tasks_by_sop.get(d.id, 0),
            )
        )
    schedule.sort(key=lambda r: (r.review_date is None, r.review_date or date.max, r.sop_number or ""))

    # ---- reviews by month (overdue first, then the next 12 months) ----
    first = date(today.year, today.month, 1)
    buckets = [MonthBucket(key="overdue", label="Overdue", count=0, items=[])]
    for i in range(MONTHS_AHEAD):
        m = _month_add(first, i)
        buckets.append(
            MonthBucket(key=f"{m:%Y-%m}", label=f"{_MONTHS[m.month - 1]} {m:%y}", count=0, items=[])
        )
    index = {b.key: b for b in buckets}
    later = 0
    for r in schedule:
        if r.review_date is None:
            continue
        bucket = index["overdue"] if r.state == "overdue" else index.get(f"{r.review_date:%Y-%m}")
        if bucket is None:
            later += 1
            continue
        bucket.count += 1
        bucket.items.append(r.sop_number or r.title)

    # ---- library health ----
    sop_numbers = {d.sop_number for d in docs if d.kind == DocumentKind.SOP and d.sop_number}

    def check(key: str, label: str, description: str, found: list[SopDocument]) -> HealthCheck:
        return HealthCheck(
            key=key,
            label=label,
            description=description,
            count=len(found),
            items=[HealthItem(id=d.id, label=_label(d)) for d in found],
        )

    listed = sops + forms
    health = [
        check(
            "no_review_date",
            "No review date",
            "Approved SOPs with no review date in SharePoint or on the cover page.",
            [d for d in approved if d.review_date is None],
        ),
        check(
            "no_effective_date",
            "No effective date",
            "Approved SOPs and forms with no effective date in SharePoint or on the cover page.",
            [d for d in listed if d.status == SopStatus.EFFECTIVE and d.effective_date is None],
        ),
        check(
            "no_owner",
            "No owner",
            "SOPs with no owner recorded in SharePoint.",
            [d for d in sops if not d.owner],
        ),
        check(
            "version_mismatch",
            "File name and document disagree on the version",
            "The file name states a different version from the document's cover page.",
            [d for d in listed if d.file_name_version and d.file_name_version != d.version],
        ),
        check(
            "no_word_copy",
            "Form without an editable Word copy",
            "Forms and templates with no Word version next to the signed PDF.",
            [d for d in forms if d.editable_copy is None and (d.mime_type or "").endswith("pdf")],
        ),
        check(
            "orphan_form",
            "Form whose SOP is not in the library",
            "The form's number points to an SOP that is not listed as approved.",
            [d for d in forms if d.parent_sop_number and d.parent_sop_number not in sop_numbers],
        ),
        check(
            "no_number",
            "No document number",
            "No SOP or form number could be read from the file name or SharePoint.",
            [d for d in scoped if not d.sop_number],
        ),
    ]
    with_issue = {i.id for c in health for i in c.items}

    # ---- change log ----
    months = months if months in PERIODS else 12
    since = today - timedelta(days=round(months * 30.44))
    changes: list[ChangeEntry] = []
    for d in listed:
        history = [e for e in (d.details.revisions if d.details else []) if e.issued]
        if history:
            for entry in history:
                if entry.issued and since <= entry.issued <= today:
                    changes.append(
                        ChangeEntry(
                            id=d.id,
                            sop_number=d.sop_number,
                            title=d.title,
                            kind=d.kind,
                            version=entry.version,
                            issued=entry.issued,
                            changes=entry.changes or None,
                            basis="history",
                        )
                    )
            continue
        effective = _day(d.effective_date)
        if effective and since <= effective <= today and d.version:
            changes.append(
                ChangeEntry(
                    id=d.id,
                    sop_number=d.sop_number,
                    title=d.title,
                    kind=d.kind,
                    version=d.version,
                    issued=effective,
                    changes=None,
                    basis="effective",
                )
            )
    changes.sort(key=lambda c: (c.issued, c.sop_number or ""), reverse=True)

    # ---- headline tiles ----
    overdue = sum(r.state == "overdue" for r in schedule)
    due_soon = sum(r.state == "due_soon" for r in schedule)
    period = f"{months} months"
    tiles = [
        Tile(
            key="approved",
            label="Approved SOPs",
            value=str(len(approved)),
            note=f"{len(forms)} form{'s' if len(forms) != 1 else ''} and templates",
            tone="neutral",
        ),
        Tile(
            key="review_overdue",
            label="Reviews overdue",
            value=str(overdue),
            note="Review date has passed",
            tone="bad" if overdue else "good",
        ),
        Tile(
            key="review_due_soon",
            label=f"Reviews due in {REVIEW_WINDOW_DAYS} days",
            value=str(due_soon),
            note="Plan the review now",
            tone="warn" if due_soon else "neutral",
        ),
        Tile(
            key="changes",
            label=f"Changes in the last {period}",
            value=str(len(changes)),
            note=f"{len({c.id for c in changes})} documents",
            tone="info",
        ),
        Tile(
            key="health",
            label="Documents with findings",
            value=str(len(with_issue)),
            note=f"of {len(listed)} listed" if listed else "Nothing listed",
            tone="warn" if with_issue else "good",
        ),
    ]
    return Quality(
        tiles=tiles,
        schedule=schedule,
        by_month=buckets,
        later=later,
        health=health,
        changes=changes,
        months=months,
        department_options=[Option(id=d, label=d) for d in departments],
        rules=QUALITY_RULES,
    )
