"""Study delivery report: key milestones, enrolment by site and site activation.

Pure calculations over the local copy of SimpleTrials data. Every figure follows a rule listed in
`STUDY_DELIVERY_RULES` (shown under each chart); nothing is estimated.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel

from app.studies.models import Study
from app.studies.rules import (
    MAJOR_SLIP_DAYS,
    RULES,
    MilestoneState,
    ScheduleState,
    enrolment_percent,
    milestone_state,
    schedule_state,
    total_enrolled,
    variance_days,
)

from .models import MilestoneCompletion

Tone = Literal["good", "info", "warn", "bad", "neutral"]
DUE_SOON_DAYS = 14

STUDY_DELIVERY_RULES = {
    **RULES,
    "study_on_plan": (
        "A study is on plan when none of its key milestones is overdue and none still to be completed "
        f"has slipped more than {MAJOR_SLIP_DAYS} days against its original end date."
    ),
    "on_time": (
        "On time: completed on or before the original (baseline) end date. SimpleTrials does not provide an "
        "actual completion date, so Avi.Intelligence records the day a sync first sees the milestone at "
        "100%. Milestones already complete when tracking began have no known date and are not counted."
    ),
    "enrolment": (
        "Enrolled against target as reported by SimpleTrials for each site. Sites with no target are listed "
        "as such; no target is estimated."
    ),
    "activation": (
        "Activated: SimpleTrials has an actual activation date. On time: activated on or before the planned "
        f"(target) activation date. Due soon: planned within {DUE_SOON_DAYS} days."
    ),
}


class Tile(BaseModel):
    key: str
    label: str
    value: str
    note: str
    tone: Tone


class MilestoneRow(BaseModel):
    study_id: str
    protocol_number: str
    name: str
    original_date: date | None
    current_date: date | None
    variance_days: int | None
    state: MilestoneState
    schedule: ScheduleState
    completed_on: date | None
    completion_basis: str | None
    on_time: bool | None


class SiteRow(BaseModel):
    study_id: str
    protocol_number: str
    site_id: str
    site_number: str
    name: str
    country: str | None
    enrolled: int | None
    target: int | None
    percent: float | None
    flag: Literal["none", "zero", "no_target", "over_target"]


class PendingSite(BaseModel):
    study_id: str
    protocol_number: str
    site_id: str
    site_number: str
    name: str
    status: str | None
    planned_date: date | None
    days_late: int | None
    state: Literal["late", "due_soon", "upcoming", "no_date"]


class Activation(BaseModel):
    total: int
    activated: int
    percent: float | None
    with_target: int
    on_time: int


class OnTime(BaseModel):
    completed: int
    on_time: int
    with_original_date: int


class Option(BaseModel):
    id: str
    label: str


class StudyDelivery(BaseModel):
    tiles: list[Tile]
    milestones: list[MilestoneRow]
    on_time: OnTime
    sites: list[SiteRow]
    activation: Activation
    pending_sites: list[PendingSite]
    study_options: list[Option]
    site_options: list[Option]
    rules: dict[str, str]


def _pct(part: int, whole: int) -> float | None:
    return round(part / whole * 100, 1) if whole else None


def build_study_delivery(
    studies: list[Study],
    completions: list[MilestoneCompletion],
    today: date,
    *,
    study_id: str | None = None,
    site_id: str | None = None,
) -> StudyDelivery:
    study_options = [Option(id=s.id, label=f"{s.protocol_number} · {s.title}") for s in studies]
    scoped = [s for s in studies if not study_id or s.id == study_id]
    site_options = [
        Option(id=site.id, label=f"{site.site_number} · {site.name} ({s.protocol_number})")
        for s in scoped
        for site in s.sites
    ]
    done = {(c.study_id, c.milestone_external_id): c for c in completions}

    # ---- key milestones ----
    rows: list[MilestoneRow] = []
    on_plan_studies = 0
    for s in scoped:
        study_ok = True
        for m in s.milestones:
            if not (m.is_key and m.kind == "milestone"):
                continue
            state = milestone_state(m.planned_date, m.actual_date, today, m.percent_complete, m.start_date)
            schedule = schedule_state(m.planned_date, m.baseline_date)
            slip = variance_days(m.planned_date, m.baseline_date)
            completion = done.get((s.id, m.external_id))
            completed = state == MilestoneState.COMPLETED
            completed_on = completion.completed_on if completion else m.actual_date
            done_on_time = (
                completed_on <= m.baseline_date if completed and completed_on and m.baseline_date else None
            )
            if not completed and (state == MilestoneState.OVERDUE or schedule == ScheduleState.SLIPPED_MAJOR):
                study_ok = False
            rows.append(
                MilestoneRow(
                    study_id=s.id,
                    protocol_number=s.protocol_number,
                    name=m.name,
                    original_date=m.baseline_date,
                    current_date=m.planned_date,
                    variance_days=slip,
                    state=state,
                    schedule=schedule,
                    completed_on=completed_on if completed else None,
                    completion_basis=(
                        completion.basis if completion else ("actual" if m.actual_date else None)
                    )
                    if completed
                    else None,
                    on_time=done_on_time,
                )
            )
        on_plan_studies += study_ok
    rows.sort(key=lambda r: (r.protocol_number, r.current_date or date.max))
    pending = [r for r in rows if r.state != MilestoneState.COMPLETED]
    overdue = sum(r.state == MilestoneState.OVERDUE for r in rows)
    slipped_major = sum(r.schedule == ScheduleState.SLIPPED_MAJOR for r in pending)
    completed_rows = [r for r in rows if r.state == MilestoneState.COMPLETED]
    on_time = OnTime(
        completed=len(completed_rows),
        on_time=sum(r.on_time is True for r in completed_rows),
        with_original_date=sum(r.on_time is not None for r in completed_rows),
    )

    # ---- enrolment by site ----
    site_rows: list[SiteRow] = []
    for s in scoped:
        for site in s.sites:
            if site_id and site.id != site_id:
                continue
            percent = enrolment_percent(site.enrolled, site.enrolment_target)
            flag: Literal["none", "zero", "no_target", "over_target"] = "none"
            if not site.enrolment_target:
                flag = "no_target"
            elif not site.enrolled:
                flag = "zero"
            elif site.enrolled > site.enrolment_target:
                flag = "over_target"
            site_rows.append(
                SiteRow(
                    study_id=s.id,
                    protocol_number=s.protocol_number,
                    site_id=site.id,
                    site_number=site.site_number,
                    name=site.name,
                    country=site.country,
                    enrolled=site.enrolled,
                    target=site.enrolment_target,
                    percent=percent,
                    flag=flag,
                )
            )
    # Furthest behind first; sites without a target last.
    site_rows.sort(
        key=lambda r: (r.percent is None, r.percent if r.percent is not None else 0, r.site_number)
    )

    # Study-level enrolment (SimpleTrials' study figure when given, else the sum of its sites).
    enrolled_total = 0
    target_total = 0
    without_target = 0
    for s in scoped:
        enrolled = s.enrolled if s.enrolled is not None else total_enrolled([x.enrolled for x in s.sites])
        enrolled_total += enrolled or 0
        if s.enrolment_target:
            target_total += s.enrolment_target
        else:
            without_target += 1

    # ---- site activation ----
    sites_in_scope = [(s, site) for s in scoped for site in s.sites if not site_id or site.id == site_id]
    activated = [(s, site) for s, site in sites_in_scope if site.activation_date]
    with_target = [(s, site) for s, site in activated if site.activation_target]
    activation = Activation(
        total=len(sites_in_scope),
        activated=len(activated),
        percent=_pct(len(activated), len(sites_in_scope)),
        with_target=len(with_target),
        on_time=sum(
            1
            for _s, site in with_target
            if site.activation_date
            and site.activation_target
            and site.activation_date <= site.activation_target
        ),
    )
    pending_sites: list[PendingSite] = []
    for s, site in sites_in_scope:
        if site.activation_date:
            continue
        target = site.activation_target
        days_late = (today - target).days if target and target < today else None
        pending_state: Literal["late", "due_soon", "upcoming", "no_date"]
        if target is None:
            pending_state = "no_date"
        elif target < today:
            pending_state = "late"
        elif (target - today).days <= DUE_SOON_DAYS:
            pending_state = "due_soon"
        else:
            pending_state = "upcoming"
        pending_sites.append(
            PendingSite(
                study_id=s.id,
                protocol_number=s.protocol_number,
                site_id=site.id,
                site_number=site.site_number,
                name=site.name,
                status=site.status,
                planned_date=target,
                days_late=days_late,
                state=pending_state,
            )
        )
    order = {"late": 0, "due_soon": 1, "upcoming": 2, "no_date": 3}
    pending_sites.sort(key=lambda p: (order[p.state], p.planned_date or date.max))

    # ---- headline tiles ----
    if target_total:
        pct = _pct(enrolled_total, target_total)
        enrol_value = f"{enrolled_total} of {target_total}"
        enrol_note = f"{pct:g}%" + (
            f" · {without_target} study with no target" if without_target == 1 else ""
        )
        if without_target > 1:
            enrol_note += f" · {without_target} studies with no target"
    else:
        enrol_value = f"{enrolled_total} enrolled"
        enrol_note = "No enrolment target recorded"
    tiles = [
        Tile(
            key="on_plan",
            label="Studies on plan",
            value=f"{on_plan_studies} of {len(scoped)}",
            note=f"No key milestone overdue or slipped over {MAJOR_SLIP_DAYS} days",
            tone="neutral",
        ),
        Tile(
            key="overdue",
            label="Key milestones overdue",
            value=str(overdue),
            note="Past the current end date, not completed",
            tone="bad" if overdue else "good",
        ),
        Tile(
            key="slipped_major",
            label=f"Slipped more than {MAJOR_SLIP_DAYS} days",
            value=str(slipped_major),
            note="Still to complete; current vs original end date",
            tone="bad" if slipped_major else "good",
        ),
        Tile(key="enrolment", label="Enrolled vs target", value=enrol_value, note=enrol_note, tone="info"),
    ]

    return StudyDelivery(
        tiles=tiles,
        milestones=rows,
        on_time=on_time,
        sites=site_rows,
        activation=activation,
        pending_sites=pending_sites,
        study_options=study_options,
        site_options=site_options,
        rules=STUDY_DELIVERY_RULES,
    )
