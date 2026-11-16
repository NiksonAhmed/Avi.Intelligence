"""The Reports summary (user decision 2026-11-16): what everyone sees first, detail only when asked.

Every figure is taken from the full reports (Study delivery, Risks and issues, Protocol deviations, eTMF,
Work management), so the summary and the full reports always agree. Each card, ring and study carries a
short "detail" (a one-line summary and the few items behind the number) and the full report it opens.
Fixed rules, no AI, nothing estimated.

Study status (shown red, amber or green):
- **Off track:** a key milestone is overdue (past its current end date, not completed).
- **At risk:** otherwise, a key milestone still to complete has slipped more than 30 days, an open issue
  is overdue, a major or critical deviation is open, or a site is late to activate.
- **On track:** none of these.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel

from app.studies.models import Study
from app.studies.rules import MAJOR_SLIP_DAYS, MilestoneState, ScheduleState, total_enrolled

from .study_delivery import Tone

Report = Literal["study", "risks", "deviations", "etmf", "quality", "work"]

SUMMARY_RULES = {
    "status": (
        "Off track: a key milestone is overdue. At risk: a key milestone still to complete has slipped more "
        f"than {MAJOR_SLIP_DAYS} days, an open issue is overdue, a major or critical deviation is open, or a "
        "site is late to activate. On track: none of these."
    ),
    "source": "Figures from the full reports (SimpleTrials read-only copy and Avi.Intelligence tasks).",
    "enrolment": (
        "Total enrolled at the end of each month, from the figures Avi.Intelligence saves daily, and the "
        "new patients that month. The first month has no 'new' figure. Nothing is back-filled."
    ),
}


class SummaryCard(BaseModel):
    key: str
    label: str
    value: str
    foot: str
    tone: Tone
    change: str | None
    change_tone: Literal["good", "bad", "neutral"]


class StudyStatus(BaseModel):
    id: str
    protocol_number: str
    what: str
    status: Literal["on_track", "at_risk", "off_track"]
    reason: str
    enrolled: int
    target: int | None
    percent: float | None


class EnrolmentMonth(BaseModel):
    month: str
    """"YYYY-MM"."""
    total: int
    new: int | None


class Spark(BaseModel):
    key: str
    label: str
    value: str
    points: list[float]


class Slice(BaseModel):
    key: str
    label: str
    count: int


class Ring(BaseModel):
    key: str
    label: str
    percent: float | None
    left: str
    right: str


class DetailRow(BaseModel):
    label: str
    chip: str
    tone: Tone


class Detail(BaseModel):
    title: str
    summary: str
    rows: list[DetailRow]
    report: Report
    study_id: str | None = None


class Summary(BaseModel):
    cards: list[SummaryCard]
    studies: list[StudyStatus]
    enrolment: list[EnrolmentMonth]
    enrolment_target: int | None
    sparks: list[Spark]
    sites: list[Slice]
    rings: list[Ring]
    details: dict[str, Detail]
    history_since: date | None
    rules: dict[str, str]


def _days(n: int, word: str = "day") -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _day(d: date | None) -> str:
    return f"{d.day} {d:%b %Y}" if d else "no date"


def _change(trends: dict[str, Any], key: str) -> tuple[str | None, Literal["good", "bad", "neutral"]]:
    t = trends.get(key)
    return (t.change_text, t.tone) if t is not None else (None, "neutral")


def _study_enrolled(study: Study) -> int:
    if study.enrolled is not None:
        return study.enrolled
    return total_enrolled([x.enrolled for x in study.sites]) or 0


def _months(history: Sequence[Any]) -> list[EnrolmentMonth]:
    last: dict[str, int] = {}
    for p in history:  # ordered by day: the last value of each month wins
        last[p.day.strftime("%Y-%m")] = p.enrolled
    out: list[EnrolmentMonth] = []
    for month, total in last.items():
        out.append(EnrolmentMonth(month=month, total=total, new=total - out[-1].total if out else None))
    return out[-12:]


def build_summary(
    *,
    delivery: Any,
    risks: Any,
    deviations: Any,
    etmf: Any,
    work: Any,
    studies: list[Study],
    history: Sequence[Any],
    today: date,
) -> Summary:
    milestones = delivery.milestones
    overdue = [m for m in milestones if m.state == MilestoneState.OVERDUE]
    open_issues = [i for i in risks.issues if not i.closed]
    overdue_issues = [i for i in open_issues if i.days_overdue is not None]
    open_devs = [d for d in deviations.deviations if not d.closed]
    serious = [d for d in open_devs if d.severity in ("Major", "Critical")]
    # The same rule as Study delivery: the study's own figure when given, else the sum of its sites.
    enrolled = sum(_study_enrolled(s) for s in studies)
    target = sum(s.enrolment_target for s in studies if s.enrolment_target) or None
    late_sites = [p for p in delivery.pending_sites if p.state == "late"]
    slipped_open = sum(
        m.schedule == ScheduleState.SLIPPED_MAJOR and m.state != MilestoneState.COMPLETED for m in milestones
    )

    trends = {
        "enrolment": _change(delivery.insights.trends, "enrolment"),
        "milestones": _change(delivery.insights.trends, "overdue"),
        "issues": _change(risks.insights.trends, "open"),
        "deviations": _change(deviations.insights.trends, "open"),
    }
    cards = [
        SummaryCard(
            key="enrolment",
            label="Patients enrolled",
            value=str(enrolled),
            foot=f"Target {target}" if target else "No target recorded",
            tone="info",
            change=trends["enrolment"][0],
            change_tone=trends["enrolment"][1],
        ),
        SummaryCard(
            key="milestones",
            label="Key milestones overdue",
            value=str(len(overdue)),
            foot=f"{slipped_open} slipped over {MAJOR_SLIP_DAYS} days",
            tone="bad" if overdue else "good",
            change=trends["milestones"][0],
            change_tone=trends["milestones"][1],
        ),
        SummaryCard(
            key="issues",
            label="Open risks and issues",
            value=str(len(open_issues)),
            foot=f"{len(overdue_issues)} overdue",
            tone="warn" if open_issues else "good",
            change=trends["issues"][0],
            change_tone=trends["issues"][1],
        ),
        SummaryCard(
            key="deviations",
            label="Open deviations",
            value=str(len(open_devs)),
            foot=f"{len(serious)} major or critical",
            tone="bad" if serious else "info",
            change=trends["deviations"][0],
            change_tone=trends["deviations"][1],
        ),
    ]

    # ---- one status per study ----
    by_id = {s.id: s for s in studies}
    statuses: list[StudyStatus] = []
    details: dict[str, Detail] = {}
    for opt in delivery.study_options:
        study = by_id.get(opt.id)
        if study is None:
            continue
        p = study.protocol_number
        s_overdue = sorted(
            (m for m in overdue if m.study_id == study.id), key=lambda m: m.current_date or today
        )
        s_slipped = [
            m
            for m in milestones
            if m.study_id == study.id
            and m.state != MilestoneState.COMPLETED
            and m.schedule == ScheduleState.SLIPPED_MAJOR
        ]
        s_issues = [i for i in overdue_issues if i.protocol_number == p]
        s_serious = [d for d in serious if d.protocol_number == p]
        s_late = [x for x in late_sites if x.study_id == study.id]
        s_enrolled = _study_enrolled(study)
        s_target = study.enrolment_target or None
        status: Literal["on_track", "at_risk", "off_track"]
        if s_overdue:
            m = s_overdue[0]
            late = (today - m.current_date).days if m.current_date else 0
            status, reason = "off_track", f"{m.name} {_days(late)} late"
        elif s_slipped:
            status, reason = (
                "at_risk",
                f"{s_slipped[0].name} slipped {_days(s_slipped[0].variance_days or 0)}",
            )
        elif s_issues:
            status, reason = "at_risk", f"{_days(len(s_issues), 'issue')} overdue"
        elif s_serious:
            status, reason = (
                "at_risk",
                f"{len(s_serious)} major deviation{'s' if len(s_serious) != 1 else ''} open",
            )
        elif s_late:
            status, reason = "at_risk", f"{_days(len(s_late), 'site')} late to activate"
        else:
            nxt = min(
                (
                    m
                    for m in milestones
                    if m.study_id == study.id and m.state != MilestoneState.COMPLETED and m.current_date
                ),
                key=lambda m: m.current_date,
                default=None,
            )
            status, reason = "on_track", f"Next: {nxt.name}, {_day(nxt.current_date)}" if nxt else "On plan"
        what = " · ".join(
            x
            for x in (
                study.therapeutic_area,
                (study.phase if study.phase.lower().startswith("phase") else f"Phase {study.phase}")
                if study.phase
                else None,
                _days(len(study.sites), "site"),
            )
            if x
        )
        statuses.append(
            StudyStatus(
                id=study.id,
                protocol_number=p,
                what=what,
                status=status,
                reason=reason,
                enrolled=s_enrolled,
                target=s_target,
                percent=round(s_enrolled * 100 / s_target, 1) if s_target else None,
            )
        )
        label = {"on_track": "On track", "at_risk": "At risk", "off_track": "Off track"}[status]
        details[f"study:{study.id}"] = Detail(
            title=f"{p} · {label}",
            summary=reason + ".",
            report="study",
            study_id=study.id,
            rows=[
                DetailRow(
                    label="Enrolled",
                    chip=f"{s_enrolled} of {s_target}" if s_target else f"{s_enrolled}",
                    tone="info",
                ),
                DetailRow(
                    label="Key milestones overdue",
                    chip=str(len(s_overdue)),
                    tone="bad" if s_overdue else "good",
                ),
                DetailRow(
                    label="Open issues overdue", chip=str(len(s_issues)), tone="bad" if s_issues else "good"
                ),
                DetailRow(
                    label="Major or critical deviations open",
                    chip=str(len(s_serious)),
                    tone="bad" if s_serious else "good",
                ),
                DetailRow(
                    label="Sites late to activate", chip=str(len(s_late)), tone="bad" if s_late else "good"
                ),
            ],
        )
    order = {"off_track": 0, "at_risk": 1, "on_track": 2}
    statuses.sort(key=lambda s: (order[s.status], s.protocol_number))

    # ---- details behind the cards and rings ----
    details["enrolment"] = Detail(
        title="Patients enrolled",
        summary=f"{enrolled} enrolled"
        + (f" of a target of {target} ({round(enrolled * 100 / target)}%)." if target else "."),
        report="study",
        rows=[
            DetailRow(
                label=f"{s.site_number} · {s.name} ({s.protocol_number})",
                chip=f"{s.enrolled or 0} of {s.target}" if s.target else f"{s.enrolled or 0}, no target",
                tone="warn" if not s.enrolled else "info",
            )
            for s in sorted(delivery.sites, key=lambda s: s.percent if s.percent is not None else 1e9)[:6]
        ],
    )
    details["milestones"] = Detail(
        title="Key milestones overdue",
        summary=f"{_days(len(overdue), 'key milestone')} past the current end date and not completed."
        if overdue
        else "No key milestone is overdue.",
        report="study",
        rows=[
            DetailRow(
                label=f"{m.protocol_number} · {m.name}",
                chip=f"{_days((today - m.current_date).days)} late" if m.current_date else "Overdue",
                tone="bad",
            )
            for m in sorted(overdue, key=lambda m: m.current_date or today)[:6]
        ],
    )
    details["issues"] = Detail(
        title="Open risks and issues",
        summary=f"{len(open_issues)} open in SimpleTrials, {len(overdue_issues)} overdue.",
        report="risks",
        rows=[
            DetailRow(
                label=f"{i.description or i.category} · {i.where}",
                chip=f"{_days(i.days_overdue)} overdue"
                if i.days_overdue is not None
                else (f"Due {_day(i.due_on)}" if i.due_on else i.status),
                tone="bad" if i.days_overdue is not None else "info",
            )
            for i in open_issues[:6]
        ],
    )
    details["deviations"] = Detail(
        title="Open deviations",
        summary=f"{len(open_devs)} open, {len(serious)} major or critical. No subject numbers are shown.",
        report="deviations",
        rows=[
            DetailRow(
                label=f"{d.severity} · {d.category} · {d.where}",
                chip=f"{_days(d.days_open)} open" if d.days_open is not None else d.status,
                tone="bad" if d.severity in ("Major", "Critical") else "info",
            )
            for d in open_devs[:6]
        ],
    )
    o = etmf.overall
    details["etmf"] = Detail(
        title="eTMF complete",
        summary=f"{o.filed} of {o.expected} expected documents filed"
        + (f" ({o.percent:g}%)." if o.percent is not None else "."),
        report="etmf",
        rows=[
            DetailRow(label=s.label, chip=f"{s.missing} missing", tone="warn") for s in etmf.sites_missing[:6]
        ],
    )
    a = delivery.activation
    details["sites"] = Detail(
        title="Sites activated",
        summary=f"{a.activated} of {a.total} sites activated; {_days(len(late_sites), 'site')} late.",
        report="study",
        rows=[
            DetailRow(
                label=f"{x.protocol_number} · {x.site_number} · {x.name}",
                chip=f"{_days(x.days_late or 0)} late"
                if x.state == "late"
                else (f"Planned {_day(x.planned_date)}" if x.planned_date else "No planned date"),
                tone="bad" if x.state == "late" else "neutral",
            )
            for x in delivery.pending_sites[:6]
        ],
    )
    ot = delivery.on_time
    late_done = [m for m in milestones if m.on_time is False]
    details["ontime"] = Detail(
        title="Key milestones on time",
        summary=f"{ot.on_time} of {ot.with_original_date} completed key milestones were on time."
        if ot.with_original_date
        else "No completed key milestones with an original date yet.",
        report="study",
        rows=[
            DetailRow(
                label=f"{m.protocol_number} · {m.name}",
                chip=f"{_days(m.variance_days or 0)} late",
                tone="bad",
            )
            for m in late_done[:6]
        ],
    )

    # ---- small weekly trends (from the saved daily figures) ----
    def spark(key: str, label: str, report: Any, tile: str) -> Spark:
        t = report.insights.trends.get(tile)
        value = next((x.value for x in report.tiles if x.key == tile), "—")
        return Spark(key=key, label=label, value=value, points=t.points if t is not None else [])

    sparks = [
        spark("work", "Overdue tasks", work, "overdue"),
        spark("issues", "Open issues", risks, "open"),
        spark("etmf", "eTMF documents missing", etmf, "missing"),
    ]
    sites = [
        Slice(key="activated", label="Activated", count=a.activated),
        Slice(key="pending", label="Not yet", count=len(delivery.pending_sites) - len(late_sites)),
        Slice(key="late", label="Late", count=len(late_sites)),
    ]
    rings = [
        Ring(
            key="etmf",
            label="eTMF complete",
            percent=o.percent,
            left=f"{o.filed} filed",
            right=f"{o.missing} missing",
        ),
        Ring(
            key="enrolment",
            label="Enrolment",
            percent=round(enrolled * 100 / target, 1) if target else None,
            left=f"{enrolled} enrolled",
            right=f"of {target}" if target else "no target",
        ),
        Ring(
            key="sites",
            label="Sites activated",
            percent=a.percent,
            left=f"{a.activated} activated",
            right=f"{a.total - a.activated} not yet",
        ),
        Ring(
            key="ontime",
            label="Key milestones on time",
            percent=round(ot.on_time * 100 / ot.with_original_date, 1) if ot.with_original_date else None,
            left=f"{ot.on_time} on time",
            right=f"{ot.with_original_date - ot.on_time} late",
        ),
    ]
    return Summary(
        cards=cards,
        studies=statuses,
        enrolment=_months(history),
        enrolment_target=target,
        sparks=sparks,
        sites=sites,
        rings=rings,
        details=details,
        history_since=delivery.insights.history_since,
        rules=SUMMARY_RULES,
    )
