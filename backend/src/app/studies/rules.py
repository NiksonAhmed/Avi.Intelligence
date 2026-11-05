"""Derived indicators. Each one is a simple, documented rule over recorded data: nothing is estimated.

The same rule texts are returned to the UI so screens can explain every indicator.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

DUE_SOON_DAYS = 14


class MilestoneState(StrEnum):
    COMPLETED = "completed"
    OVERDUE = "overdue"
    DUE_SOON = "due_soon"
    UPCOMING = "upcoming"
    NOT_PLANNED = "not_planned"


RULES: dict[str, str] = {
    "milestone_overdue": "Overdue: the planned date has passed and SimpleTrials has no actual date.",
    "milestone_due_soon": f"Due soon: planned within the next {DUE_SOON_DAYS} days, not yet completed.",
    "enrolment": "Enrolment: participants enrolled at all sites, as reported by SimpleTrials, against "
    "the study target. Not shown when SimpleTrials has no target.",
    "risk_score": "Score: likelihood × impact as entered by the risk owner (1 = low, 3 = high). "
    "6 or more is High, 3–4 Medium, 1–2 Low.",
    "task_overdue": "Overdue: the due date has passed and the task is not completed or cancelled.",
}


def milestone_state(planned: date | None, actual: date | None, today: date) -> MilestoneState:
    if actual is not None:
        return MilestoneState.COMPLETED
    if planned is None:
        return MilestoneState.NOT_PLANNED
    if planned < today:
        return MilestoneState.OVERDUE
    if (planned - today).days <= DUE_SOON_DAYS:
        return MilestoneState.DUE_SOON
    return MilestoneState.UPCOMING


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


class RiskStatus(StrEnum):
    OPEN = "Open"
    MITIGATING = "Mitigating"
    CLOSED = "Closed"


class RiskKind(StrEnum):
    RISK = "risk"
    ISSUE = "issue"


def task_overdue(due: date | None, status: str, today: date) -> bool:
    return due is not None and due < today and status not in TASK_CLOSED
