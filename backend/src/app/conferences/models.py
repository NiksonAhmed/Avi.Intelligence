"""One conference as Avi.Intelligence shows it, whichever source it came from."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Literal, Protocol

from pydantic import BaseModel


class AvionRole(StrEnum):
    EXHIBITING = "Exhibiting"
    SPEAKING = "Speaking"
    ATTENDING = "Attending"
    CONSIDERING = "Considering"


class ConferenceRecord(BaseModel):
    id: str
    name: str
    city: str | None = None
    country: str | None = None
    lat: float | None = None
    lon: float | None = None
    """Placed from the city and country (see `geo.py`); None when the city is not known."""
    starts_on: date
    ends_on: date | None = None
    role: AvionRole = AvionRole.CONSIDERING
    team: str | None = None
    """Who is going, as written in the list."""
    booth: str | None = None
    register_by: date | None = None
    website: str | None = None
    notes: str | None = None
    cost: float | None = None
    """Shown only to people with `conference.cost`."""
    currency: str | None = None
    source_url: str | None = None
    """The item in SharePoint ("Open in SharePoint"); None for demo data."""


class ConferenceSourceInfo(BaseModel):
    mode: Literal["demo", "sharepoint"]
    reason: str | None = None
    """Why demo data is shown (e.g. the list is not connected yet)."""
    fetched_at: datetime | None = None


class ConferenceSource(Protocol):
    def info(self) -> ConferenceSourceInfo: ...

    async def list_conferences(self, *, force_refresh: bool = False) -> list[ConferenceRecord]: ...
