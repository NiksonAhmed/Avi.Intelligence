"""The BD team's SharePoint conference list, read-only through Microsoft Graph.

Ready for when the list is connected: set CONFERENCES_SHAREPOINT_LIST (the list's name), and
CONFERENCES_SHAREPOINT_SITE_URL if the list is not on the SOP site; the Entra app needs read access to that
site (Sites.Selected grant). Column names are not known yet, so each field accepts several likely names and
CONFERENCES_FIELD_MAP (JSON, like SHAREPOINT_SOP_FIELD_MAP) can name the real ones once BD confirms them.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import quote

from app.connectors.sharepoint.graph_client import GraphClient, site_lookup_path

from .geo import locate
from .models import AvionRole, ConferenceRecord, ConferenceSourceInfo

# Our field -> SharePoint column internal names to try, in order (first non-empty wins).
DEFAULT_FIELDS: dict[str, list[str]] = {
    "name": ["Title", "ConferenceName", "Conference", "EventName", "Event"],
    "city": ["City", "Location", "Venue_x0020_City"],
    "country": ["Country", "Country_x002f_Region", "CountryOrRegion"],
    "starts_on": ["StartDate", "Start_x0020_Date", "EventDate", "Start", "From"],
    "ends_on": ["EndDate", "End_x0020_Date", "End", "To"],
    "role": ["AvionRole", "Avion_x0020_Role", "Role", "ParticipationType", "Participation", "Status"],
    "team": ["WhoIsGoing", "Who_x0020_is_x0020_going", "Attendees", "Team"],
    "booth": ["Booth", "BoothNumber", "Booth_x0020_Number"],
    "register_by": ["RegistrationDeadline", "Registration_x0020_Deadline", "RegisterBy", "Deadline"],
    "website": ["Website", "URL", "Link"],
    "notes": ["Notes", "Comments", "Description"],
    "cost": ["Cost", "Budget", "TotalCost", "Total_x0020_Cost"],
    "currency": ["Currency"],
}

_ROLE_WORDS = {
    "exhibit": AvionRole.EXHIBITING,
    "booth": AvionRole.EXHIBITING,
    "sponsor": AvionRole.EXHIBITING,
    "speak": AvionRole.SPEAKING,
    "present": AvionRole.SPEAKING,
    "talk": AvionRole.SPEAKING,
    "attend": AvionRole.ATTENDING,
    "going": AvionRole.ATTENDING,
    "confirmed": AvionRole.ATTENDING,
    "registered": AvionRole.ATTENDING,
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


def role_of(value: Any) -> AvionRole:
    text = str(value or "").lower()
    for word, role in _ROLE_WORDS.items():
        if word in text:
            return role
    return AvionRole.CONSIDERING


def _date(value: Any) -> date | None:
    if isinstance(value, str) and len(value) >= 10:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _text(value: Any, limit: int = 500) -> str | None:
    if isinstance(value, dict):  # hyperlink / lookup columns
        value = value.get("Url") or value.get("Description") or value.get("LookupValue")
    if isinstance(value, list):  # multi-person or multi-choice columns
        value = ", ".join(str(v.get("LookupValue", v)) if isinstance(v, dict) else str(v) for v in value)
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text[:limit] or None


def _number(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def map_item(item: dict[str, Any], fields: dict[str, list[str]]) -> ConferenceRecord | None:
    values: dict[str, Any] = item.get("fields") or {}

    def pick(key: str) -> Any:
        for name in fields[key]:
            if values.get(name) not in (None, "", []):
                return values[name]
        return None

    name, start = _text(pick("name"), 300), _date(pick("starts_on"))
    if not name or start is None:
        return None  # not a usable conference row
    city = _text(pick("city"), 120)
    place = locate(city)
    return ConferenceRecord(
        id=str(item.get("id")),
        name=name,
        city=city,
        country=_text(pick("country"), 120),
        lat=place[0] if place else None,
        lon=place[1] if place else None,
        starts_on=start,
        ends_on=_date(pick("ends_on")),
        role=role_of(pick("role")),
        team=_text(pick("team"), 300),
        booth=_text(pick("booth"), 60),
        register_by=_date(pick("register_by")),
        website=_text(pick("website"), 500),
        notes=_text(pick("notes"), 1000),
        cost=_number(pick("cost")),
        currency=_text(pick("currency"), 8),
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
