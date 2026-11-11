"""Data Management rules: whose clock is running, query age, ageing buckets and red/amber flags.

Two clocks (agreed in the plan): while a query is open at the site, the site's clock runs from the moment
it was raised (or sent back); once the site has answered, our clock runs until it is approved or closed.
Targets are in working days (Mon-Fri): DM_SITE_ANSWER_DAYS (default 5) and DM_APPROVAL_DAYS (default 3).
Red = over target; amber = on the last day of the target. Ageing buckets use calendar days since raised.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Literal

Flag = Literal["red", "amber", "green", "none"]
STATE_LABELS = {
    "open_at_site": "Open at site",
    "awaiting_approval": "Answered, awaiting approval",
    "closed": "Closed",
}
BUCKETS = [("0-7", 0, 7), ("8-14", 8, 14), ("15-30", 15, 30), ("30+", 31, None)]

RULES = {
    "clocks": (
        "Open at site: waiting for the site to answer (the site's clock, from when the query was raised or "
        "sent back). Answered, awaiting approval: the site has answered and the query waits for DM/CRA "
        "approval (our clock, from the answer)."
    ),
    "targets": (
        "Targets in working days (Monday to Friday): red when over target, amber on the last day of the "
        "target."
    ),
    "ageing": "Ageing: calendar days since the query was first raised, for queries not yet closed.",
    "missing": (
        "Unconfirmed missing data: fields left blank that the site has not yet confirmed as missing. "
        "Pending forms: forms expected at a visit but not completed."
    ),
    "source": "Read-only copy of the Viedoc export; subject IDs only, no other patient details are stored.",
}


def working_days(start: date, end: date) -> int:
    """Weekdays after `start` up to and including `end` (0 when end is on or before start)."""
    if end <= start:
        return 0
    days = (end - start).days
    weeks, extra = divmod(days, 7)
    count = weeks * 5
    for i in range(1, extra + 1):
        if (start + timedelta(days=weeks * 7 + i)).weekday() < 5:
            count += 1
    return count


def clock_days(state: str, state_since: datetime | None, today: date) -> int | None:
    """Working days on the running clock (None for closed queries or unknown dates)."""
    if state == "closed" or state_since is None:
        return None
    return working_days(state_since.date(), today)


def flag(state: str, days: int | None, site_target: int, approval_target: int) -> Flag:
    if state == "closed" or days is None:
        return "none"
    target = site_target if state == "open_at_site" else approval_target
    if days > target:
        return "red"
    if days == target:
        return "amber"
    return "green"


def age_days(raised_at: datetime | None, today: date) -> int | None:
    return (today - raised_at.date()).days if raised_at else None


def bucket(days: int | None) -> str | None:
    if days is None:
        return None
    for label, low, high in BUCKETS:
        if days >= low and (high is None or days <= high):
            return label
    return None
