"""One conference as Avi.Intelligence shows it, whichever source it came from.

The fields follow the BD team's conference schedules (user decision 2026-11-24): conference, dates, location,
website, registration (early-bird) deadline, who is going, priority 1-3, government support (trade missions)
and the reason or comment, with its tags (BIO Partnering, AUS Delegate). Budget and costs are never read
(user decision 2026-11-16, confirmed 2026-11-24).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Protocol

from pydantic import BaseModel, Field

PRIORITIES = (1, 2, 3)
TAGS = ("BIO Partnering", "AUS Delegate")


class ConferenceRecord(BaseModel):
    id: str
    name: str
    city: str | None = None
    country: str | None = None
    lat: float | None = None
    lon: float | None = None
    """Placed from the city (see `geo.py`); None when the city is not known."""
    starts_on: date
    ends_on: date | None = None
    priority: int | None = None
    """1 (must go) to 3, as in the BD schedule; None when not set."""
    team: str | None = None
    """Who is going, as written in the list (e.g. "MM (JB)")."""
    attendees: list[str] = Field(default_factory=list)
    """The people's initials found in `team` (e.g. ["MM", "JB"]), for the filter and clash check."""
    tags: list[str] = Field(default_factory=list)
    """BIO Partnering, AUS Delegate: from their own column or the comment."""
    gov_support: str | None = None
    """Government support or trade mission (e.g. "Global Vic Trade Mission")."""
    registration: str | None = None
    """The registration text as written (e.g. "EBR to 30 Jan", "TBD")."""
    register_by: date | None = None
    """The early-bird or registration deadline, when a date can be read from `registration`."""
    booth: str | None = None
    website: str | None = None
    notes: str | None = None
    """The reason or comment: why Avion is going."""
    source_url: str | None = None
    """The item in SharePoint ("Open in SharePoint"); None for demo data."""


class ConferenceSourceInfo(BaseModel):
    mode: Literal["demo", "sharepoint"]
    reason: str | None = None
    """Why demo data is shown (e.g. the list is not connected yet)."""
    fetched_at: datetime | None = None
    files: list[str] = Field(default_factory=list)
    """The workbooks read, when the source is the BD document library."""


class ConferenceSource(Protocol):
    def info(self) -> ConferenceSourceInfo: ...

    async def list_conferences(self, *, force_refresh: bool = False) -> list[ConferenceRecord]: ...
