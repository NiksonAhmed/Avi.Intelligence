"""The livelier top of every report (user decision 2026-11-16): a headline sentence and tile trends.

- **Headline:** one sentence that says what matters most, worked out by fixed rules from the same figures
  as the tiles (no AI), with a short second line.
- **Trends:** each tile's figure is saved once a day (the last value seen that day, all studies only), so
  the tiles can show a small trend line (one point per week, up to 12 weeks) and the change since about
  30 days ago. History starts the day this was switched on; nothing is back-filled or estimated. A
  filtered view (one study, site or department) shows no trend: the history is kept for all studies.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import ReportSnapshot
from .study_delivery import Tile, Tone

TREND_WEEKS = 12
COMPARE_DAYS = 30
MIN_COMPARE_DAYS = 7

# Which tiles are tracked, and which way is better: +1 higher is better, -1 lower is better, 0 neither.
TRACKED: dict[str, dict[str, int]] = {
    "study-delivery": {"on_plan": 1, "overdue": -1, "slipped_major": -1, "enrolment": 1},
    "deviations": {"total": 0, "open": -1, "major": -1, "rate": -1, "identify": -1},
    "risks-issues": {"open": -1, "overdue": -1, "high": -1, "due_soon": 0, "closed": 1},
    "etmf": {"completeness": 1, "missing": -1, "on_time": 1, "expiring": -1},
    "quality": {"approved": 0, "review_overdue": -1, "review_due_soon": 0, "changes": 0, "health": -1},
    "work-management": {"open": 0, "overdue": -1, "due_soon": 0, "completed": 1},
}


class TileTrend(BaseModel):
    points: list[float]
    """One value per week, oldest first, ending with today's (empty until there is history)."""
    change: float | None
    change_text: str | None
    """E.g. "+3 since 17 Oct" or "No change since 17 Oct"; None until a week of history exists."""
    tone: Literal["good", "bad", "neutral"]


class Insights(BaseModel):
    headline: str
    detail: str | None
    tone: Tone
    trends: dict[str, TileTrend]
    history_since: date | None
    """The first day figures were saved for this report (None when trends are not shown)."""


def number(value: str) -> float | None:
    """The first number in a tile's value: "71%" → 71, "142 of 200" → 142, "—" → None."""
    m = re.search(r"-?\d+(?:\.\d+)?", value.replace(",", ""))
    return float(m.group()) if m else None


def _day(d: date) -> str:
    return f"{d.day} {d:%b}"


def _fmt(v: float) -> str:
    return f"{v:g}" if abs(v) >= 1 or v == 0 else f"{v:.1f}"


def _trends(
    db: Session, tenant_id: str, source: str, report: str, tiles: list[Tile], today: date
) -> tuple[dict[str, TileTrend], date | None]:
    tracked = TRACKED.get(report, {})
    values = {t.key: v for t in tiles if t.key in tracked and (v := number(t.value)) is not None}
    kind = f"tiles:{report}"
    rows = list(
        db.scalars(
            select(ReportSnapshot)
            .where(
                ReportSnapshot.tenant_id == tenant_id,
                ReportSnapshot.kind == kind,
                ReportSnapshot.source == source,
            )
            .order_by(ReportSnapshot.day)
        )
    )
    todays = next((r for r in rows if r.day == today), None)
    if todays is None:
        todays = ReportSnapshot(tenant_id=tenant_id, kind=kind, source=source, day=today, data=values)
        db.add(todays)
        rows.append(todays)
    else:
        todays.data = values
    db.commit()

    since = rows[0].day
    start = today - timedelta(weeks=TREND_WEEKS)
    weekly: dict[tuple[int, int], dict[str, Any]] = {}
    for r in rows:
        if r.day >= start:
            weekly[r.day.isocalendar()[:2]] = r.data  # the last day of each week wins
    compare = next((r for r in reversed(rows) if r.day <= today - timedelta(days=COMPARE_DAYS)), None)
    if compare is None:
        compare = next((r for r in rows if r.day <= today - timedelta(days=MIN_COMPARE_DAYS)), None)

    out: dict[str, TileTrend] = {}
    for key, now in values.items():
        points = [float(d[key]) for d in weekly.values() if isinstance(d.get(key), int | float)]
        then = compare.data.get(key) if compare is not None else None
        change = now - then if isinstance(then, int | float) else None
        tone: Literal["good", "bad", "neutral"] = "neutral"
        text: str | None = None
        if change is not None and compare is not None:
            when = _day(compare.day)
            text = f"No change since {when}" if change == 0 else f"{change:+g} since {when}"
            better = tracked[key] * change
            tone = "good" if better > 0 else "bad" if better < 0 else "neutral"
        out[key] = TileTrend(
            points=points if len(points) > 1 else [], change=change, change_text=text, tone=tone
        )
    return out, since


# ---- headlines ---------------------------------------------------------------------------------------


def _n(tiles: dict[str, Tile], key: str) -> int:
    t = tiles.get(key)
    v = number(t.value) if t else None
    return int(v) if v is not None else 0


def _plural(n: int, word: str, many: str | None = None) -> str:
    return f"{n} {word if n == 1 else (many or word + 's')}"


def _phrase(n: int, tile: Tile | None) -> str:
    """ "6 due in the next 14 days" from a tile labelled "Due in the next 14 days"."""
    label = tile.label if tile else ""
    return f"{n} {label[:1].lower()}{label[1:]}".strip()


Headline = tuple[str, str | None, Tone]


def _study_delivery(r: Any, t: dict[str, Tile]) -> Headline:
    overdue, slipped = _n(t, "overdue"), _n(t, "slipped_major")
    plan = t["on_plan"].value if "on_plan" in t else None
    enrol = t.get("enrolment")
    detail = " ".join(
        x
        for x in (
            f"{plan} studies on plan." if plan else None,
            f"Enrolment: {enrol.value} ({enrol.note})." if enrol and enrol.note else None,
        )
        if x
    )
    if overdue or slipped:
        head = (
            _plural(overdue, "key milestone") + " overdue"
            if overdue
            else _plural(slipped, "key milestone") + " slipped"
        )
        if overdue and slipped:
            head += f", and {slipped} slipped {t['slipped_major'].label.split(' ', 1)[1].lower()}"
        elif slipped and not overdue:
            head += f" {t['slipped_major'].label.split(' ', 1)[1].lower()}"
        return head + ".", detail or None, "bad"
    return "Every key milestone is on plan.", detail or None, "good"


def _deviations(r: Any, t: dict[str, Tile]) -> Headline:
    open_n = _n(t, "open")
    serious = sum(1 for d in r.deviations if not d.closed and d.severity in ("Major", "Critical"))
    total = t.get("total")
    detail = f"{total.value} recorded, {total.note}." if total else None
    if serious:
        return (
            f"{_plural(serious, 'major or critical deviation')} still open, {open_n} open in all.",
            detail,
            "bad",
        )
    if open_n:
        return f"{_plural(open_n, 'protocol deviation')} open; none major or critical.", detail, "warn"
    return "No open protocol deviations.", detail, "good"


def _risks_issues(r: Any, t: dict[str, Tile]) -> Headline:
    open_n, overdue, high = _n(t, "open"), _n(t, "overdue"), _n(t, "high")
    closed = t.get("closed")
    detail = (
        f"{_phrase(_n(t, 'closed'), closed)}: {closed.note[:1].lower()}{closed.note[1:]}." if closed else None
    )
    if overdue:
        head = f"{overdue} of {_plural(open_n, 'open issue')} {'is' if overdue == 1 else 'are'} overdue"
        head += f"; {high} high priority." if high else "."
        return head, detail, "bad"
    if open_n:
        return f"{_plural(open_n, 'open issue')}, none overdue.", detail, "warn"
    return "No open risks or issues.", detail, "good"


def _etmf(r: Any, t: dict[str, Tile]) -> Headline:
    pct = t["completeness"].value if "completeness" in t else "—"
    missing = _n(t, "missing")
    expired = sum(1 for e in r.expiring if e.state == "expired")
    head = f"The eTMF is {pct} complete" if pct != "—" else "No eTMF documents expected yet"
    parts = []
    if missing:
        parts.append(f"{_plural(missing, 'document')} missing")
    if expired:
        parts.append(f"{expired} expired")
    head += (": " + " and ".join(parts) if parts else "") + "."
    on_time = t.get("on_time")
    detail = (
        f"{on_time.value} {on_time.label[:1].lower()}{on_time.label[1:]}."
        if on_time and on_time.value != "—"
        else None
    )
    return head, detail, "bad" if expired else "warn" if missing else "good"


def _quality(r: Any, t: dict[str, Tile]) -> Headline:
    overdue, soon = _n(t, "review_overdue"), _n(t, "review_due_soon")
    detail = (
        f"{_plural(_n(t, 'approved'), 'approved SOP')}; {_phrase(_n(t, 'changes'), t.get('changes'))};"
        f" {_phrase(_n(t, 'health'), t.get('health'))}."
    )
    if overdue:
        head = f"{_plural(overdue, 'SOP review')} overdue"
        head += f", and {_phrase(soon, t.get('review_due_soon'))}." if soon else "."
        return head, detail, "bad"
    if soon:
        return f"No SOP reviews overdue; {_phrase(soon, t.get('review_due_soon'))}.", detail, "warn"
    return "No SOP reviews overdue or due soon.", detail, "good"


def _work_management(r: Any, t: dict[str, Tile]) -> Headline:
    open_n, overdue, soon = _n(t, "open"), _n(t, "overdue"), _n(t, "due_soon")
    done = t.get("completed")
    detail = (
        f"{_phrase(_n(t, 'completed'), done)} ({done.note[:1].lower()}{done.note[1:]})." if done else None
    )
    if overdue:
        people = sum(1 for p in r.by_person if p.overdue)
        head = f"{overdue} of {_plural(open_n, 'open task')} {'is' if overdue == 1 else 'are'} overdue"
        head += f", across {_plural(people, 'person', 'people')}." if people else "."
        return head, detail, "bad"
    if open_n:
        return f"No overdue tasks; {_phrase(soon, t.get('due_soon'))}.", detail, "warn" if soon else "good"
    return "No open tasks.", detail, "good"


HEADLINES: dict[str, Callable[[Any, dict[str, Tile]], Headline]] = {
    "study-delivery": _study_delivery,
    "deviations": _deviations,
    "risks-issues": _risks_issues,
    "etmf": _etmf,
    "quality": _quality,
    "work-management": _work_management,
}


def build_insights(
    db: Session,
    *,
    tenant_id: str,
    source: str,
    report: str,
    built: Any,
    today: date,
    all_studies: bool,
) -> Insights:
    """The headline for `built` (a report), and tile trends when the view is unfiltered."""
    tiles = {t.key: t for t in built.tiles}
    head, detail, tone = HEADLINES[report](built, tiles)
    trends: dict[str, TileTrend] = {}
    since: date | None = None
    if all_studies:
        trends, since = _trends(db, tenant_id, source, report, built.tiles, today)
    return Insights(headline=head, detail=detail, tone=tone, trends=trends, history_since=since)
