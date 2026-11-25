"""The BD team's SharePoint conference list, read-only through Microsoft Graph.

Ready for when the list is connected: set CONFERENCES_SHAREPOINT_LIST (the list's name), and
CONFERENCES_SHAREPOINT_SITE_URL if the list is not on the SOP site; the Entra app needs read access to that
site (Sites.Selected grant). Each field accepts several likely column names, including the BD schedules'
(Conference, Date, Location, Website, Registration Dates, Attendee, Priority, Gov Support, Comment / Reason),
and CONFERENCES_FIELD_MAP (JSON, like SHAREPOINT_SOP_FIELD_MAP) can name the real ones.

There is deliberately no budget field: budgets and costs are never read (user decision 2026-11-24).
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from app.connectors.sharepoint.graph_client import GraphClient, site_lookup_path

from .geo import locate
from .models import ConferenceRecord, ConferenceSourceInfo
from .parsing import attendees_in, date_range, gov_support_in, priority_of, registration_date, tags_in

# Our field -> SharePoint column internal names to try, in order (first non-empty wins).
DEFAULT_FIELDS: dict[str, list[str]] = {
    "name": ["Title", "Conference", "ConferenceName", "EventName", "Event"],
    "city": ["City", "Location", "Venue_x0020_City"],
    "country": ["Country", "Country_x002f_Region", "CountryOrRegion"],
    "starts_on": ["StartDate", "Start_x0020_Date", "EventDate", "Start", "From", "Date", "Dates"],
    "ends_on": ["EndDate", "End_x0020_Date", "End", "To"],
    "priority": ["Priority", "Priority_x0020_Level"],
    "team": ["Attendee", "Attendees", "WhoIsGoing", "Who_x0020_is_x0020_going", "Team"],
    "tags": ["Tags", "Tag"],
    "gov_support": [
        "GovSupport",
        "Gov_x0020_Support",
        "GovernmentSupport",
        "Government_x0020_Support",
        "TradeMission",
        "Trade_x0020_Mission",
    ],
    "registration": [
        "RegistrationDates",
        "Registration_x0020_Dates",
        "Registration",
        "RegistrationDeadline",
        "Registration_x0020_Deadline",
        "RegisterBy",
        "EarlyBird",
        "Deadline",
    ],
    "booth": ["Booth", "BoothNumber", "Booth_x0020_Number"],
    "website": ["Website", "URL", "Link"],
    "notes": ["Comment", "Comments", "Reason", "Notes", "Description"],
}


def parse_field_map(raw_json: str | None) -> dict[str, list[str]]:
    fields = {k: list(v) for k, v in DEFAULT_FIELDS.items()}
    if not raw_json:
        return fields
    raw = json.loads(raw_json)
    if not isinstance(raw, dict):
        raise ValueError("CONFERENCES_FIELD_MAP must be a JSON object.")
    for key, value in raw.items():
        if key not in DEFAULT_FIELDS:
            raise ValueError(f'CONFERENCES_FIELD_MAP has unknown field "{key}".')
        names = value if isinstance(value, list) else [value]
        fields[key] = [str(n) for n in names] + fields[key]
    return fields


def _text(value: Any, limit: int = 500) -> str | None:
    if isinstance(value, dict):  # hyperlink / lookup columns
        value = value.get("Url") or value.get("Description") or value.get("LookupValue")
    if isinstance(value, list):  # multi-person or multi-choice columns
        value = ", ".join(str(v.get("LookupValue", v)) if isinstance(v, dict) else str(v) for v in value)
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text[:limit] or None


def _place(value: str | None) -> tuple[str | None, str | None]:
    """ "San Diego, USA" -> ("San Diego", "USA"); a city alone stays a city."""
    if not value:
        return None, None
    parts = [p.strip() for p in value.split(",") if p.strip()]
    if len(parts) >= 2 and locate(", ".join(parts[:-1])) is not None:
        return ", ".join(parts[:-1]), parts[-1]
    if len(parts) >= 2:
        return parts[0], parts[-1]
    return value, None


def map_item(
    item: dict[str, Any], fields: dict[str, list[str]], year: int | None = None
) -> ConferenceRecord | None:
    """One list row. `year` completes text dates like "7-10 Jan" (the schedule's year)."""
    values: dict[str, Any] = item.get("fields") or {}

    def pick(key: str) -> Any:
        for name in fields[key]:
            if values.get(name) not in (None, "", []):
                return values[name]
        return None

    name = _text(pick("name"), 300)
    start, end = date_range(pick("starts_on"), year)
    if not name or start is None:
        return None  # not a usable conference row
    if pick("ends_on") is not None:
        end = date_range(pick("ends_on"), year)[0] or end
    city, country = _text(pick("city"), 120), _text(pick("country"), 120)
    if country is None:
        city, country = _place(city)
    place = locate(city)
    team, notes = _text(pick("team"), 300), _text(pick("notes"), 1000)
    registration = _text(pick("registration"), 120)
    return ConferenceRecord(
        id=str(item.get("id")),
        name=name,
        city=city,
        country=country,
        lat=place[0] if place else None,
        lon=place[1] if place else None,
        starts_on=start,
        ends_on=end,
        priority=priority_of(pick("priority")),
        team=team,
        attendees=attendees_in(team),
        tags=tags_in(pick("tags"), notes),
        gov_support=_text(pick("gov_support"), 200) or gov_support_in(notes),
        registration=registration,
        register_by=registration_date(pick("registration"), start),
        booth=_text(pick("booth"), 60),
        website=_text(pick("website"), 500),
        notes=notes,
        source_url=_text(item.get("webUrl"), 1000),
    )


class SharePointConferenceSource:
    def __init__(
        self,
        client: GraphClient,
        *,
        site_url: str,
        list_name: str,
        fields: dict[str, list[str]],
        cache_seconds: int,
    ) -> None:
        self._client, self._site_url, self._list = client, site_url, list_name
        self._fields, self._cache_seconds = fields, cache_seconds
        self._cache: list[ConferenceRecord] | None = None
        self._expires = 0.0
        self._fetched_at: datetime | None = None

    def info(self) -> ConferenceSourceInfo:
        return ConferenceSourceInfo(mode="sharepoint", fetched_at=self._fetched_at)

    async def list_conferences(self, *, force_refresh: bool = False) -> list[ConferenceRecord]:
        if self._cache is not None and not force_refresh and time.monotonic() < self._expires:
            return self._cache
        site = await self._client.get(site_lookup_path(self._site_url))
        items = await self._client.get_all(
            f"/sites/{site['id']}/lists/{quote(self._list)}/items?$expand=fields&$top=200"
        )
        rows = [r for r in (map_item(i, self._fields) for i in items) if r is not None]
        self._cache, self._expires = rows, time.monotonic() + self._cache_seconds
        self._fetched_at = datetime.now(UTC)
        return rows
