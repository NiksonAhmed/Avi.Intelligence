"""Reading the BD schedules' text the way people write it (user decision 2026-11-24).

Dates like "7-10 Jan", "29 Apr - 01 May" or "30 May - 02 June" with the year from the schedule; registration
like "EBR to 30 Jan", "Feb-26" or "TBD"; attendees like "JB,MM" or "MM (JB)"; priority "1"; tags and trade
missions in the comment. Anything that cannot be read becomes None (shown as "not recorded"), never a guess.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any

from .models import PRIORITIES, TAGS

_MONTHS = {
    m: i
    for i, names in enumerate(
        [("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"), ("may",),
         ("jun", "june"), ("jul", "july"), ("aug", "august"), ("sep", "sept", "september"),
         ("oct", "october"), ("nov", "november"), ("dec", "december")],
        start=1,
    )
    for m in names
}  # fmt: skip
_MONTH = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"  # noqa: E501
_TAG_WORDS = {"BIO Partnering": ("bio partnering", "biopartnering"), "AUS Delegate": ("aus delegate",)}
_GOV = re.compile(r"((?:global vic|ausbio|mtp connect|austrade|[a-z]+)\s+trade mission|austrade)", re.I)


def _month(word: str) -> int:
    return _MONTHS[word.lower()[:3]]


def _safe(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def date_range(value: Any, year: int | None) -> tuple[date | None, date | None]:
    """(start, end) from a date cell. Real dates pass through; text needs the schedule's year."""
    if isinstance(value, datetime):
        return value.date(), None
    if isinstance(value, date):
        return value, None
    text = " ".join(str(value or "").split()).lower()
    iso = re.match(r"(\d{4}-\d{2}-\d{2})", text)
    if iso:
        try:
            return date.fromisoformat(iso.group(1)), None
        except ValueError:
            return None, None
    if year is None:
        return None, None
    # "29 Apr - 01 May", "30 May - 02 June"
    m = re.match(rf"(\d{{1,2}})\s*{_MONTH}\s*[-–to]+\s*(\d{{1,2}})\s*{_MONTH}", text)
    if m:
        start = _safe(year, _month(m.group(2)), int(m.group(1)))
        end_month = _month(m.group(4))
        end = _safe(year + (end_month < _month(m.group(2))), end_month, int(m.group(3)))
        return start, end
    # "7-10 Jan", "23 - 25 March"
    m = re.match(rf"(\d{{1,2}})\s*[-–]\s*(\d{{1,2}})\s*{_MONTH}", text)
    if m:
        month = _month(m.group(3))
        return _safe(year, month, int(m.group(1))), _safe(year, month, int(m.group(2)))
    # "12 July"
    m = re.match(rf"(\d{{1,2}})\s*{_MONTH}", text)
    if m:
        return _safe(year, _month(m.group(2)), int(m.group(1))), None
    return None, None


def registration_date(value: Any, conference_start: date | None) -> date | None:
    """The deadline in "EBR to 30 Jan", "EBR 10 Apr", "2-Mar-26", "Feb-26" or a real date. A day and month
    without a year fall in the conference's year, or the year before when that would be after the
    conference."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = " ".join(str(value or "").split()).lower()
    if not text or text in ("tbd", "tba", "n/a", "-"):
        return None
    iso = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if iso:
        try:
            return date.fromisoformat(iso.group(1))
        except ValueError:
            return None
    # "2-Mar-26" (day, month, 2-digit year)
    m = re.search(rf"(\d{{1,2}})[-\s]{_MONTH}[-\s](\d{{2}})\b", text)
    if m:
        return _safe(2000 + int(m.group(3)), _month(m.group(2)), int(m.group(1)))
    # "Feb-26": a month only, so the end of that month
    m = re.fullmatch(rf"{_MONTH}[-\s](\d{{2}})", text)
    if m:
        y, mo = 2000 + int(m.group(2)), _month(m.group(1))
        first_next = date(y + (mo == 12), mo % 12 + 1, 1)
        return first_next - timedelta(days=1)
    # "EBR to 30 Jan", "10 Apr"
    m = re.search(rf"(\d{{1,2}})\s*{_MONTH}", text)
    if m and conference_start is not None:
        found = _safe(conference_start.year, _month(m.group(2)), int(m.group(1)))
        if found and found > conference_start:
            found = _safe(conference_start.year - 1, _month(m.group(2)), int(m.group(1)))
        return found
    return None


def priority_of(value: Any) -> int | None:
    m = re.search(r"\b([123])\b", str(value if value is not None else ""))
    if m:
        return int(m.group(1))
    if isinstance(value, float) and value in PRIORITIES:
        return int(value)
    return None


def attendees_in(value: Any) -> list[str]:
    """Initials in "JB,MM", "MM (JB)" or "JB & MM", in order, once each."""
    out: list[str] = []
    for token in re.findall(r"\b[A-Z]{2,3}\b", str(value or "")):
        if token not in out and token not in ("TBD", "TBA", "BD", "PM", "AUS", "USA", "UK"):
            out.append(token)
    return out


def tags_in(*values: Any) -> list[str]:
    text = " ".join(str(v or "") for v in values).lower()
    return [tag for tag in TAGS if any(w in text for w in _TAG_WORDS[tag])]


def gov_support_in(value: Any) -> str | None:
    """A trade mission named in a comment, e.g. "Global Vic Trade Mission"."""
    m = _GOV.search(str(value or ""))
    return " ".join(m.group(1).split()) if m else None  # as written, e.g. "AusBio Trade Mission"
