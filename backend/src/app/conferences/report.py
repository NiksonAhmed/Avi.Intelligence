"""The Conferences page's figures: pure calculations over the conference list (no estimates)."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from app.reports.study_delivery import Tile

from .models import AvionRole, ConferenceRecord

DEADLINE_WINDOW_DAYS = 30

CONFERENCE_RULES = {
    "source": "Conferences as recorded by the BD team in their SharePoint list (read-only copy).",
    "role": "Avion's role as recorded in the list: Exhibiting, Speaking, Attending or Considering.",
    "next": "Next conference: the first that has not ended yet, by start date.",
    "deadline": f"Registration due: the deadline is within the next {DEADLINE_WINDOW_DAYS} days.",
    "map": "Pins are placed by city; a city the map does not know yet is listed as 'not on the map'.",
}


class ConferenceRow(BaseModel):
    id: str
    name: str
    city: str | None
    country: str | None
    lat: float | None
    lon: float | None
    starts_on: date
    ends_on: date
    role: AvionRole
    team: str | None
    booth: str | None
    register_by: date | None
    website: str | None
    notes: str | None
    source_url: str | None
    cost: float | None
    """Only for people who may see costs; None otherwise."""
    currency: str | None
    past: bool
    days_until: int
    """Days until it starts (negative once started)."""
    register_soon: bool


class Conferences(BaseModel):
    year: int
    years: list[int]
    tiles: list[Tile]
    conferences: list[ConferenceRow]
    next_id: str | None
    not_on_map: int
    can_see_cost: bool
    rules: dict[str, str]


def build_conferences(
    records: list[ConferenceRecord],
    today: date,
    *,
    year: int | None,
    role: AvionRole | None,
    can_see_cost: bool,
) -> Conferences:
    years = sorted({r.starts_on.year for r in records} | {today.year, today.year + 1})
    chosen = year or (today.year if any(r.starts_on.year == today.year and (r.ends_on or r.starts_on) >= today
                                        for r in records) else today.year + 1)  # fmt: skip
    rows: list[ConferenceRow] = []
    for r in sorted(records, key=lambda r: (r.starts_on, r.name)):
        if r.starts_on.year != chosen or (role and r.role != role):
            continue
        end = r.ends_on or r.starts_on
        rows.append(
            ConferenceRow(
                id=r.id, name=r.name, city=r.city, country=r.country, lat=r.lat, lon=r.lon,
                starts_on=r.starts_on, ends_on=end, role=r.role, team=r.team, booth=r.booth,
                register_by=r.register_by, website=r.website, notes=r.notes, source_url=r.source_url,
                cost=r.cost if can_see_cost else None, currency=r.currency if can_see_cost else None,
                past=end < today, days_until=(r.starts_on - today).days,
                register_soon=bool(r.register_by and end >= today and 0 <= (r.register_by - today).days
                                   <= DEADLINE_WINDOW_DAYS),
            )
        )  # fmt: skip
    upcoming = [r for r in rows if not r.past]
    nxt = upcoming[0] if upcoming else None
    countries = sorted({r.country for r in rows if r.country})
    stage = [r for r in rows if r.role in (AvionRole.EXHIBITING, AvionRole.SPEAKING)]
    due = [r for r in rows if r.register_soon]
    tiles = [
        Tile(key="total", label=f"Conferences in {chosen}", value=str(len(rows)),
             note=f"{len(upcoming)} still to come", tone="info"),
        Tile(key="countries", label="Countries", value=str(len(countries)),
             note=", ".join(countries[:3]) + ("…" if len(countries) > 3 else "") or "None", tone="neutral"),
        Tile(key="next", label="Next conference",
             value=(f"In {nxt.days_until} days" if nxt.days_until > 0 else "On now") if nxt else "—",
             note=f"{nxt.name}, {nxt.city}" if nxt else "None planned", tone="info" if nxt else "neutral"),
        Tile(key="stage", label="Exhibiting or speaking", value=str(len(stage)),
             note="Booths and talks to prepare", tone="neutral"),
        Tile(key="register", label="Registration due", value=str(len(due)),
             note=f"Deadline within {DEADLINE_WINDOW_DAYS} days" if due else "Nothing due soon",
             tone="warn" if due else "good"),
    ]  # fmt: skip
    return Conferences(
        year=chosen,
        years=years,
        tiles=tiles,
        conferences=rows,
        next_id=nxt.id if nxt else None,
        not_on_map=sum(1 for r in rows if r.lat is None),
        can_see_cost=can_see_cost,
        rules=CONFERENCE_RULES,
    )
