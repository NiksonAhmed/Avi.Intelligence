"""'Today' in the organisation's time zone, so overdue rules match what staff see on their calendar."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import get_settings


def today() -> date:
    try:
        return datetime.now(ZoneInfo(get_settings().app_time_zone)).date()
    except ZoneInfoNotFoundError:
        return date.today()
