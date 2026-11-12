"""Protocol deviations report: volume, severity, category, sites (with a rate per enrolled subject), monthly
trend, ageing of open deviations and the full list.

Pure calculations over the read-only copy of SimpleTrials protocol deviations (no subject IDs, no
people). Every figure follows a rule in `DEVIATION_RULES`.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from statistics import median

from pydantic import BaseModel

from app.studies.models import Study, StudyDeviation, StudySite

from .study_delivery import Option, Tile

TREND_MONTHS = 12
SEVERITY_ORDER = ["Critical", "Major", "Minor"]
NOT_CLASSIFIED = "Not classified"
AGEING = [("0-30", 0, 30), ("31-60", 31, 60), ("61-90", 61, 90), ("Over 90", 91, None)]

DEVIATION_RULES = {
    "source": (
        "Protocol deviations as recorded in SimpleTrials (read-only copy, refreshed with the hourly "
        "SimpleTrials sync). No subject IDs or people are copied."
    ),
    "severity": (
        "Severity as classified in SimpleTrials: Critical, Major (including 'important') or Minor "
        "(including 'non-important'); 'Not classified' when no classification is recorded."
    ),
    "rate": (
        "Rate: deviations per 10 enrolled subjects, using the enrolled counts from SimpleTrials. Sites "
        "with no enrolled subjects show no rate."
    ),
    "trend": f"Deviations by the month they occurred (last {TREND_MONTHS} months), split by severity.",
    "ageing": (
        "Open deviations by days open: from the day the deviation was identified (else the day it "
        "occurred) to today."
    ),
    "identify": "Days to identify: from the day a deviation occurred to the day it was identified.",
}


class CountRow(BaseModel):
    key: str
    label: str
    count: int
    open: int


class SiteRow(BaseModel):
    key: str
    label: str
    protocol_number: str
    total: int
    open: int
    major: int
    """Major or critical."""
    enrolled: int | None
    per_10: float | None


class MonthRow(BaseModel):
    month: str
    """YYYY-MM"""
    critical: int = 0
    major: int = 0
    minor: int = 0
    other: int = 0


class DeviationRow(BaseModel):
    id: str
    number: str | None
    protocol_number: str
    where: str
    category: str
    severity: str
    status: str
    closed: bool
    description: str | None
    subject_level: bool
    occurred_on: date | None
    identified_on: date | None
    reported_on: date | None
    closed_on: date | None
    reportable: bool | None
    days_open: int | None
    days_to_identify: int | None


class Deviations(BaseModel):
    tiles: list[Tile]
    by_severity: list[CountRow]
    by_category: list[CountRow]
    by_site: list[SiteRow]
    trend: list[MonthRow]
    ageing: list[CountRow]
    deviations: list[DeviationRow]
    has_deviations: bool
    study_options: list[Option]
    site_options: list[Option]
    rules: dict[str, str]


def _site_label(site: StudySite) -> str:
    return f"{site.site_number} · {site.name}"


def _where(d: StudyDeviation, site: StudySite | None) -> str:
    if site is not None:
        return _site_label(site)
    if d.site_number:
        return f"{d.site_number}{f' · {d.site_name}' if d.site_name else ''}"
    return "Study level"


def _months(today: date, n: int) -> list[str]:
    y, m = today.year, today.month
    out = []
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    return list(reversed(out))


def build_deviations(
    studies: list[Study], today: date, *, study_id: str | None = None, site_id: str | None = None
) -> Deviations:
    study_options = [Option(id=s.id, label=f"{s.protocol_number} · {s.title}") for s in studies]
    scoped = [s for s in studies if not study_id or s.id == study_id]
    site_options = [
        Option(id=site.id, label=f"{_site_label(site)} ({s.protocol_number})")
        for s in scoped
        for site in s.sites
    ]

    rows: list[tuple[Study, StudySite | None, StudyDeviation]] = []
    for s in scoped:
        by_ext = {site.external_id: site for site in s.sites}
        by_number = {site.site_number: site for site in s.sites}
        for d in s.deviations:
            site = by_ext.get(d.site_external_id or "") or by_number.get(d.site_number or "")
            if site_id and (site is None or site.id != site_id):
                continue
            rows.append((s, site, d))

    def severity(d: StudyDeviation) -> str:
        return d.severity or NOT_CLASSIFIED

    def days_open(d: StudyDeviation) -> int | None:
        start = d.identified_on or d.occurred_on
        return (today - start).days if start and not d.closed else None

    listed = [
        DeviationRow(
            id=d.id,
            number=d.number,
            protocol_number=s.protocol_number,
            where=_where(d, site),
            category=d.category or "Not categorised",
            severity=severity(d),
            status=d.status or ("Closed" if d.closed else "Open"),
            closed=d.closed,
            description=d.description,
            subject_level=d.subject_level,
            occurred_on=d.occurred_on,
            identified_on=d.identified_on,
            reported_on=d.reported_on,
            closed_on=d.closed_on,
            reportable=d.reportable,
            days_open=days_open(d),
            days_to_identify=(
                (d.identified_on - d.occurred_on).days
                if d.identified_on and d.occurred_on and d.identified_on >= d.occurred_on
                else None
            ),
        )
        for s, site, d in rows
    ]
    rank = {name: i for i, name in enumerate(SEVERITY_ORDER)}
    listed.sort(
        key=lambda r: (r.closed, rank.get(r.severity, 9), -(r.days_open or 0), r.occurred_on or date.min)
    )

    def counts(key_of: Callable[[DeviationRow], str]) -> list[CountRow]:
        out: dict[str, CountRow] = {}
        for r in listed:
            k = key_of(r)
            row = out.setdefault(k, CountRow(key=k, label=k, count=0, open=0))
            row.count += 1
            row.open += not r.closed
        return list(out.values())

    by_severity = sorted(counts(lambda r: r.severity), key=lambda c: (rank.get(c.label, 9), c.label))
    by_category = sorted(counts(lambda r: r.category), key=lambda c: (-c.count, c.label))

    # ---- sites, with a rate per 10 enrolled subjects ----
    site_rows: dict[str, SiteRow] = {}
    for s in scoped:
        for site in s.sites:
            if site_id and site.id != site_id:
                continue
            site_rows[site.id] = SiteRow(
                key=site.id, label=_site_label(site), protocol_number=s.protocol_number, total=0, open=0,
                major=0, enrolled=site.enrolled, per_10=None,
            )  # fmt: skip
    for _s, site, d in rows:
        if site is None:
            continue
        row = site_rows[site.id]
        row.total += 1
        row.open += not d.closed
        row.major += severity(d) in ("Major", "Critical")
    for row in site_rows.values():
        row.per_10 = round(row.total / row.enrolled * 10, 1) if row.enrolled else None
    by_site = sorted(
        (r for r in site_rows.values() if r.total),
        key=lambda r: (-(r.per_10 or 0), -r.total, r.protocol_number, r.label),
    )

    # ---- monthly trend by severity ----
    months = _months(today, TREND_MONTHS)
    trend = {m: MonthRow(month=m) for m in months}
    for r in listed:
        if r.occurred_on is None:
            continue
        m = f"{r.occurred_on.year:04d}-{r.occurred_on.month:02d}"
        if m in trend:
            field = r.severity.lower() if r.severity in SEVERITY_ORDER else "other"
            setattr(trend[m], field, getattr(trend[m], field) + 1)

    # ---- ageing of open deviations ----
    ageing = [CountRow(key=label, label=f"{label} days", count=0, open=0) for label, _lo, _hi in AGEING]
    for r in listed:
        if r.days_open is None:
            continue
        for bucket, (_label, lo, hi) in zip(ageing, AGEING, strict=True):
            if r.days_open >= lo and (hi is None or r.days_open <= hi):
                bucket.count += 1
                bucket.open += 1
                break

    # ---- headline tiles ----
    total = len(listed)
    open_rows = [r for r in listed if not r.closed]
    serious = [r for r in listed if r.severity in ("Major", "Critical")]
    recent = sum(1 for r in listed if r.occurred_on and (today - r.occurred_on).days <= 30)
    oldest = max((r.days_open or 0 for r in open_rows), default=None)
    enrolled = sum(
        site.enrolled or 0 for s in scoped for site in s.sites if not site_id or site.id == site_id
    )
    identify = [r.days_to_identify for r in listed if r.days_to_identify is not None]
    tiles = [
        Tile(key="total", label="Protocol deviations", value=str(total),
             note=f"{recent} in the last 30 days", tone="info"),
        Tile(key="open", label="Open", value=str(len(open_rows)),
             note=f"Oldest open {oldest} days" if open_rows else "None open",
             tone="warn" if open_rows else "good"),
        Tile(key="major", label="Major or critical", value=str(len(serious)),
             note=f"{sum(not r.closed for r in serious)} still open" if serious else "None recorded",
             tone="bad" if any(not r.closed for r in serious) else "neutral"),
        Tile(key="rate", label="Per 10 enrolled subjects",
             value=f"{total / enrolled * 10:.1f}" if enrolled else "—",
             note=f"{total} deviations, {enrolled} subjects enrolled" if enrolled else "No enrolled subjects",
             tone="neutral"),
        Tile(key="identify", label="Median days to identify",
             value=f"{median(identify):g}" if identify else "—",
             note=f"From occurrence to identification ({len(identify)} with both dates)" if identify
             else "Needs occurrence and identification dates", tone="neutral"),
    ]  # fmt: skip
    return Deviations(
        tiles=tiles,
        by_severity=by_severity,
        by_category=by_category,
        by_site=by_site,
        trend=list(trend.values()),
        ageing=ageing,
        deviations=listed,
        has_deviations=any(s.deviations for s in studies),
        study_options=study_options,
        site_options=site_options,
        rules=DEVIATION_RULES,
    )
