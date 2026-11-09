"""Derived indicators. Each one is a simple, documented rule over recorded data: nothing is estimated.

The same rule texts are returned to the UI so screens can explain every indicator.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

DUE_SOON_DAYS = 14
MAJOR_SLIP_DAYS = 30


class MilestoneState(StrEnum):
    """Progress status: against the current end date and today."""

    COMPLETED = "completed"
    OVERDUE = "overdue"
    DUE_SOON = "due_soon"
    IN_PROGRESS = "in_progress"
    NOT_STARTED = "not_started"
    UPCOMING = "upcoming"
    """Not due yet, and no start date to tell whether it has started."""
    NOT_PLANNED = "not_planned"


class ScheduleState(StrEnum):
    """Schedule status: current end date compared with the original (baseline) end date."""

    ON_PLAN = "on_plan"
    SLIPPED = "slipped"
    SLIPPED_MAJOR = "slipped_major"
    AHEAD = "ahead"
    NO_BASELINE = "no_baseline"


RULES: dict[str, str] = {
    "milestone_overdue": "Overdue: the current end date has passed and SimpleTrials does not show it "
    "as complete (no actual date, or less than 100% complete).",
    "milestone_completed": "Completed: SimpleTrials has an actual date or shows 100% complete.",
    "milestone_due_soon": f"Due soon: current end date within the next {DUE_SOON_DAYS} days, not completed.",
    "milestone_in_progress": "In progress: the start date has passed, it is not complete and not yet due.",
    "milestone_not_started": "Not started: the start date is still in the future.",
    "schedule_on_plan": "On plan: the current end date is the same as the original (baseline) end date.",
    "schedule_slipped": "Slipped: the current end date is later than the original (baseline) end date. "
    f"More than {MAJOR_SLIP_DAYS} days is shown in red.",
    "schedule_ahead": "Ahead: the current end date is earlier than the original (baseline) end date.",
    "start_moved": "Start moved: the current start date differs from the original (baseline) start date "
    "(+ later, − earlier). The Schedule status is based on end dates.",
    "schedule_no_baseline": "No original (baseline) end date in SimpleTrials to compare with.",
    "key_milestone": "Key milestone: SimpleTrials' standard study milestones (e.g. First Patient In) "
    "and Avion's chosen list. Portfolio headline figures count key milestones only.",
    "enrolment": "Enrolment: participants enrolled at all sites, as reported by SimpleTrials, against "
    "the study target. Not shown when SimpleTrials has no target.",
    "risk_score": "Score: likelihood × impact as entered by the risk owner (1 = low, 3 = high). "
    "6 or more is High, 3–4 Medium, 1–2 Low.",
    "task_overdue": "Overdue: the due date has passed and the task is not completed or cancelled.",
}


def milestone_state(
    planned: date | None,
    actual: date | None,
    today: date,
    percent_complete: int | None = None,
    start: date | None = None,
) -> MilestoneState:
    """Progress status from the current end date (`planned`), start date and % complete."""
    if actual is not None or percent_complete == 100:
        return MilestoneState.COMPLETED
    if planned is None:
        return MilestoneState.NOT_PLANNED
    if planned < today:
        return MilestoneState.OVERDUE
    if (planned - today).days <= DUE_SOON_DAYS:
        return MilestoneState.DUE_SOON
    if start is not None:
        return MilestoneState.IN_PROGRESS if start <= today else MilestoneState.NOT_STARTED
    return MilestoneState.UPCOMING


def variance_days(planned: date | None, baseline: date | None) -> int | None:
    """Current end minus original end, in days (positive = later). None if either is unknown."""
    if planned is None or baseline is None:
        return None
    return (planned - baseline).days


def schedule_state(planned: date | None, baseline: date | None) -> ScheduleState:
    days = variance_days(planned, baseline)
    if days is None:
        return ScheduleState.NO_BASELINE
    if days == 0:
        return ScheduleState.ON_PLAN
    if days < 0:
        return ScheduleState.AHEAD
    return ScheduleState.SLIPPED_MAJOR if days > MAJOR_SLIP_DAYS else ScheduleState.SLIPPED


def enrolment_percent(enrolled: int | None, target: int | None) -> float | None:
    """Percentage of target, or None when either figure is missing (never guessed)."""
    if enrolled is None or not target:
        return None
    return round(enrolled * 100 / target, 1)


def total_enrolled(site_counts: list[int | None]) -> int | None:
    known = [c for c in site_counts if c is not None]
    return sum(known) if known else None


def risk_score(likelihood: int, impact: int) -> int:
    return likelihood * impact


def risk_rating(score: int) -> str:
    if score >= 6:
        return "High"
    if score >= 3:
        return "Medium"
    return "Low"


class TaskStatus(StrEnum):
    NOT_STARTED = "Not started"
    IN_PROGRESS = "In progress"
    BLOCKED = "Blocked"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"


TASK_CLOSED = {TaskStatus.COMPLETED, TaskStatus.CANCELLED}
PERSON_STATUSES = [s for s in TaskStatus if s != TaskStatus.CANCELLED]
"""Statuses each assigned person can set for their own part (only a manager cancels a task)."""


def overall_task_status(statuses: list[str]) -> TaskStatus:
    """A task with several people: Completed when everyone is done, Blocked if anyone is blocked,
    In progress once anyone has started or finished, otherwise Not started."""
    values = [TaskStatus(s) for s in statuses]
    if values and all(v == TaskStatus.COMPLETED for v in values):
        return TaskStatus.COMPLETED
    if TaskStatus.BLOCKED in values:
        return TaskStatus.BLOCKED
    if any(v in (TaskStatus.IN_PROGRESS, TaskStatus.COMPLETED) for v in values):
        return TaskStatus.IN_PROGRESS
    return TaskStatus.NOT_STARTED


class TaskCategory(StrEnum):
    """What a task is about. Study tasks link to a study; SOP tasks to approved SOPs/forms."""

    STUDY = "study"
    SOP = "sop"
    VENDOR = "vendor"
    SYSTEM = "system"
    GENERAL = "general"


TASK_CATEGORY_LABELS: dict[TaskCategory, str] = {
    TaskCategory.STUDY: "Study",
    TaskCategory.SOP: "Procedures and SOPs",
    TaskCategory.VENDOR: "Vendor",
    TaskCategory.SYSTEM: "Computer system",
    TaskCategory.GENERAL: "General",
}


class RiskStatus(StrEnum):
    OPEN = "Open"
    MITIGATING = "Mitigating"
    CLOSED = "Closed"


class RiskKind(StrEnum):
    RISK = "risk"
    ISSUE = "issue"


def task_overdue(due: date | None, status: str, today: date) -> bool:
    return due is not None and due < today and status not in TASK_CLOSED
