"""Risks and issues report: open and overdue issues, priority, category, sites, ageing, monthly opened
vs closed, and the full list.

All risks and issues come from SimpleTrials, the CTMS (user decision 2026-11-13); nothing is raised in
Avi.Intelligence. SimpleTrials' API has no risk register, so its action items are the issues. Pure
calculations over the read-only copy; every figure follows a rule in `RISK_ISSUE_RULES`.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from statistics import median

from pydantic import BaseModel

from app.studies.models import Study, StudyActionItem, StudySite

from .deviations import AGEING, CountRow, _months
from .study_delivery import Option, Tile

TREND_MONTHS = 12
DUE_SOON_DAYS = 14
CLOSED_WINDOW_DAYS = 30
PRIORITY_ORDER = ["Critical", "High", "Medium", "Normal", "Low"]
NOT_SET = "Not set"

RISK_ISSUE_RULES = {
    "source": (
        "Risks and issues as recorded in SimpleTrials, the CTMS (read-only copy, refreshed with the hourly "
        "SimpleTrials sync or Sync now). SimpleTrials' API has no risk register, so its action items are "
        "shown as issues. Nothing is raised or edited in Avi.Intelligence."
    ),
    "open": "Open: not closed in SimpleTrials.",
    "overdue": "Overdue: open and past its due date in SimpleTrials.",
    "priority": "Priority as set in SimpleTrials; 'Not set' when none is recorded.",
    "ageing": "Open issues by days open: from the day the issue was opened in SimpleTrials to today.",
    "trend": f"Issues opened and closed per month (last {TREND_MONTHS} months).",
    "closed": (
        f"Closed in the last {CLOSED_WINDOW_DAYS} days, by the closed date in SimpleTrials. Days to close: "
        "from opened to closed."
    ),
}


class PriorityRow(BaseModel):
    key: str
    label: str
    count: int
    open: int
    overdue: int


class SiteIssues(BaseModel):
    key: str
    label: str
    protocol_number: str
    open: int
    overdue: int
    total: int


class IssueMonth(BaseModel):
    month: str
    """YYYY-MM"""
    opened: int = 0
    closed: int = 0


class IssueRow(BaseModel):
    id: str
    number: str | None
    protocol_number: str
    where: str
    category: str
    subcategory: str | None
    priority: str
    status: str
    closed: bool
    description: str | None
    response: str | None
    assignee: str | None
    opened_on: date | None
    due_on: date | None
    closed_on: date | None
    days_open: int | None
    days_overdue: int | None


class RisksIssues(BaseModel):
    tiles: list[Tile]
    by_priority: list[PriorityRow]
    by_category: list[CountRow]
    by_site: list[SiteIssues]
    ageing: list[CountRow]
    trend: list[IssueMonth]
    issues: list[IssueRow]
    has_issues: bool
    study_options: list[Option]
    site_options: list[Option]
    rules: dict[str, str]


def _site_label(site: StudySite) -> str:
    return f"{site.site_number} · {site.name}"


def _where(a: StudyActionItem, site: StudySite | None) -> str:
    if site is not None:
        return _site_label(site)
    if a.site_number:
        return f"{a.site_number}{f' · {a.site_name}' if a.site_name else ''}"
    return "Study level"


def build_risks_issues(
    studies: list[Study], today: date, *, study_id: str | None = None, site_id: str | None = None
) -> RisksIssues:
    study_options = [Option(id=s.id, label=f"{s.protocol_number} · {s.title}") for s in studies]
    scoped = [s for s in studies if not study_id or s.id == study_id]
    site_options = [
        Option(id=site.id, label=f"{_site_label(site)} ({s.protocol_number})")
        for s in scoped
        for site in s.sites
    ]

    rows: list[tuple[Study, StudySite | None, StudyActionItem]] = []
    for s in scoped:
        by_number = {site.site_number: site for site in s.sites}
        for a in s.action_items:
            site = by_number.get(a.site_number or "")
            if site_id and (site is None or site.id != site_id):
                continue
            rows.append((s, site, a))

    listed = [
        IssueRow(
            id=a.id,
            number=a.number,
            protocol_number=s.protocol_number,
            where=_where(a, site),
            category=a.category or "Not categorised",
            subcategory=a.subcategory,
            priority=a.priority or NOT_SET,
            status=a.status or ("Closed" if a.closed else "Open"),
            closed=a.closed,
            description=a.description,
            response=a.response,
            assignee=a.assignee,
            opened_on=a.opened_on,
            due_on=a.due_on,
            closed_on=a.closed_on,
            days_open=(today - a.opened_on).days if a.opened_on and not a.closed else None,
            days_overdue=(today - a.due_on).days if a.due_on and not a.closed and a.due_on < today else None,
        )
        for s, site, a in rows
    ]
    rank = {name: i for i, name in enumerate(PRIORITY_ORDER)}
    listed.sort(
        key=lambda r: (r.closed, -(r.days_overdue or 0), rank.get(r.priority, 9), r.due_on or date.max)
    )
    open_rows = [r for r in listed if not r.closed]
    overdue = [r for r in open_rows if r.days_overdue is not None]

    # ---- by priority and category ----
    priorities: dict[str, PriorityRow] = {}
    for r in listed:
        row = priorities.setdefault(
            r.priority, PriorityRow(key=r.priority, label=r.priority, count=0, open=0, overdue=0)
        )
        row.count += 1
        row.open += not r.closed
        row.overdue += r.days_overdue is not None
    by_priority = sorted(priorities.values(), key=lambda p: (rank.get(p.label, 9), p.label))

    def counts(key_of: Callable[[IssueRow], str]) -> list[CountRow]:
        out: dict[str, CountRow] = {}
        for r in listed:
            k = key_of(r)
            row = out.setdefault(k, CountRow(key=k, label=k, count=0, open=0))
            row.count += 1
            row.open += not r.closed
        return sorted(out.values(), key=lambda c: (-c.count, c.label))

    by_category = counts(lambda r: r.category)

    # ---- sites ----
    sites: dict[str, SiteIssues] = {}
    for s, site, _a in rows:
        key = site.id if site is not None else f"{s.id}-study"
        label = _site_label(site) if site is not None else "Study level"
        sites.setdefault(
            key,
            SiteIssues(key=key, label=label, protocol_number=s.protocol_number, open=0, overdue=0, total=0),
        )
    by_id = {r.id: r for r in listed}
    for s, site, a in rows:
        key = site.id if site is not None else f"{s.id}-study"
        r = by_id[a.id]
        bucket = sites[key]
        bucket.total += 1
        bucket.open += not r.closed
        bucket.overdue += r.days_overdue is not None
    by_site = sorted(
        (b for b in sites.values() if b.total),
        key=lambda b: (-b.overdue, -b.open, b.protocol_number, b.label),
    )

    # ---- ageing of open issues ----
    ageing = [CountRow(key=label, label=f"{label} days", count=0, open=0) for label, _lo, _hi in AGEING]
    for r in open_rows:
        if r.days_open is None:
            continue
        for bucket_row, (_label, lo, hi) in zip(ageing, AGEING, strict=True):
            if r.days_open >= lo and (hi is None or r.days_open <= hi):
                bucket_row.count += 1
                bucket_row.open += 1
                break

    # ---- opened vs closed per month ----
    trend = {m: IssueMonth(month=m) for m in _months(today, TREND_MONTHS)}
    for r in listed:
        for day, field in ((r.opened_on, "opened"), (r.closed_on, "closed")):
            if day is not None and (m := f"{day.year:04d}-{day.month:02d}") in trend:
                setattr(trend[m], field, getattr(trend[m], field) + 1)

    # ---- headline tiles ----
    high = [r for r in open_rows if r.priority in ("Critical", "High")]
    due_soon = sum(
        1 for r in open_rows if r.due_on and today <= r.due_on <= today + timedelta(days=DUE_SOON_DAYS)
    )
    since = today - timedelta(days=CLOSED_WINDOW_DAYS)
    closed_recent = [r for r in listed if r.closed and r.closed_on and r.closed_on >= since]
    to_close = [(r.closed_on - r.opened_on).days for r in listed if r.closed and r.closed_on and r.opened_on]
    oldest_overdue = max((r.days_overdue or 0 for r in overdue), default=0)
    tiles = [
        Tile(key="open", label="Open issues", value=str(len(open_rows)),
             note=f"{len(listed)} recorded in all", tone="warn" if open_rows else "good"),
        Tile(key="overdue", label="Overdue", value=str(len(overdue)),
             note=f"Oldest {oldest_overdue} days past due" if overdue else "None overdue",
             tone="bad" if overdue else "good"),
        Tile(key="high", label="Open high priority", value=str(len(high)),
             note="Critical or High in SimpleTrials", tone="bad" if high else "neutral"),
        Tile(key="due_soon", label=f"Due in the next {DUE_SOON_DAYS} days", value=str(due_soon),
             note="Still open", tone="warn" if due_soon else "neutral"),
        Tile(key="closed", label=f"Closed in the last {CLOSED_WINDOW_DAYS} days",
             value=str(len(closed_recent)),
             note=f"Median {median(to_close):g} days to close" if to_close else "No closed issues with dates",
             tone="info"),
    ]  # fmt: skip

    return RisksIssues(
        tiles=tiles,
        by_priority=by_priority,
        by_category=by_category,
        by_site=by_site,
        ageing=ageing,
        trend=list(trend.values()),
        issues=listed,
        has_issues=any(s.action_items for s in studies),
        study_options=study_options,
        site_options=site_options,
        rules=RISK_ISSUE_RULES,
    )
