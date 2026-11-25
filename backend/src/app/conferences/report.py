"""The Conferences page's figures: pure calculations over the conference list (no estimates, no costs)."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from app.reports.study_delivery import Tile

from .models import PRIORITIES, TAGS, ConferenceRecord

DEADLINE_WINDOW_DAYS = 30

CONFERENCE_RULES = {
    "source": "Conferences as recorded by the BD team in their SharePoint list (read-only copy). Budgets are "
    "never read.",
    "priority": "Priority as recorded by BD: 1 (must go), 2 or 3.",
    "next": "Next conference: the first that has not ended yet, by start date.",
    "clash": "Date clash: two conferences in the same year whose dates overlap; 'booked twice' when the same "
    "person is going to both.",
    "deadline": f"Registration due: the early-bird or registration deadline is within the next "
    f"{DEADLINE_WINDOW_DAYS} days.",
    "map": "Pins are placed by city and coloured by priority; a city the map does not know yet is listed as "
    "'not on the map'.",
}


class ClashRef(BaseModel):
    id: str
    name: str
    starts_on: date
    ends_on: date
    shared: list[str]
    """People going to both (initials); empty when different people go."""


class ConferenceRow(BaseModel):
    id: str
    name: str
    city: str | None
    country: str | None
    lat: float | None
    lon: float | None
    starts_on: date
    ends_on: date
    priority: int | None
    team: str | None
    attendees: list[str]
    tags: list[str]
    gov_support: str | None
    registration: str | None
    register_by: date | None
    booth: str | None
    website: str | None
    notes: str | None
    source_url: str | None
    past: bool
    days_until: int
    """Days until it starts (negative once started)."""
    register_soon: bool
    clashes: list[ClashRef]


class ClashGroup(BaseModel):
    starts_on: date
    ends_on: date
    names: list[str]
    shared: list[str]
    """People booked at two of them at once."""


class Conferences(BaseModel):
    year: int
    years: list[int]
    tiles: list[Tile]
    conferences: list[ConferenceRow]
    clash_groups: list[ClashGroup]
    next_id: str | None
    not_on_map: int
    attendees: list[str]
    """Everyone going in the chosen year (for the filter)."""
    tags: list[str]
    rules: dict[str, str]


def _overlaps(a: ConferenceRecord, b: ConferenceRecord) -> bool:
    return a.starts_on <= (b.ends_on or b.starts_on) and b.starts_on <= (a.ends_on or a.starts_on)


def _groups(records: list[ConferenceRecord]) -> list[list[ConferenceRecord]]:
    """Conferences joined by overlapping dates (A overlaps B, B overlaps C: one group)."""
    groups: list[list[ConferenceRecord]] = []
    for r in sorted(records, key=lambda r: r.starts_on):
        touching = [g for g in groups if any(_overlaps(r, x) for x in g)]
        merged = [r] + [x for g in touching for x in g]
        groups = [g for g in groups if g not in touching] + [merged]
    return [sorted(g, key=lambda r: (r.starts_on, r.name)) for g in groups if len(g) > 1]


def build_conferences(
    records: list[ConferenceRecord],
    today: date,
    *,
    year: int | None,
    priority: int | None = None,
    who: str | None = None,
    tag: str | None = None,
) -> Conferences:
    years = sorted({r.starts_on.year for r in records} | {today.year, today.year + 1})
    chosen = year or (today.year if any(r.starts_on.year == today.year and (r.ends_on or r.starts_on) >= today
                                        for r in records) else today.year + 1)  # fmt: skip
    in_year = sorted((r for r in records if r.starts_on.year == chosen), key=lambda r: (r.starts_on, r.name))

    # Clashes over the whole year, whatever the filters.
    clash_of: dict[str, list[ClashRef]] = {r.id: [] for r in in_year}
    for a in in_year:
        for b in in_year:
            if a.id != b.id and _overlaps(a, b):
                shared = [p for p in a.attendees if p in b.attendees]
                clash_of[a.id].append(ClashRef(id=b.id, name=b.name, starts_on=b.starts_on,
                                               ends_on=b.ends_on or b.starts_on, shared=shared))  # fmt: skip
    groups = []
    for g in _groups(in_year):
        shared = sorted({p for a in g for b in g if a.id != b.id and _overlaps(a, b) for p in a.attendees
                         if p in b.attendees})  # fmt: skip
        groups.append(ClashGroup(starts_on=min(r.starts_on for r in g),
                                 ends_on=max(r.ends_on or r.starts_on for r in g),
                                 names=[r.name for r in g], shared=shared))  # fmt: skip

    rows: list[ConferenceRow] = []
    for r in in_year:
        if priority is not None and r.priority != priority:
            continue
        if who and who not in r.attendees:
            continue
        if tag and tag not in r.tags:
            continue
        end = r.ends_on or r.starts_on
        rows.append(
            ConferenceRow(
                id=r.id, name=r.name, city=r.city, country=r.country, lat=r.lat, lon=r.lon,
                starts_on=r.starts_on, ends_on=end, priority=r.priority, team=r.team, attendees=r.attendees,
                tags=r.tags, gov_support=r.gov_support, registration=r.registration,
                register_by=r.register_by,
                booth=r.booth, website=r.website, notes=r.notes, source_url=r.source_url,
                past=end < today, days_until=(r.starts_on - today).days,
                register_soon=bool(r.register_by and end >= today and 0 <= (r.register_by - today).days
                                   <= DEADLINE_WINDOW_DAYS),
                clashes=clash_of[r.id],
            )
        )  # fmt: skip
    upcoming = [r for r in rows if not r.past]
    nxt = upcoming[0] if upcoming else None
    countries = sorted({r.country for r in rows if r.country})
    by_priority = {p: sum(1 for r in rows if r.priority == p) for p in PRIORITIES}
    due = [r for r in rows if r.register_soon]
    twice = sum(1 for g in groups if g.shared)
    priority_note = " · ".join(f"Priority {p}: {by_priority[p]}" for p in (2, 3))
    tiles = [
        Tile(key="total", label=f"Conferences in {chosen}", value=str(len(rows)),
             note=f"{len(countries)} {'country' if len(countries) == 1 else 'countries'} · "
                  f"{len(upcoming)} still to come", tone="info"),
        Tile(key="priority", label="Priority 1", value=str(by_priority[1]), note=priority_note, tone="good"),
        Tile(key="next", label="Next conference",
             value=(f"In {nxt.days_until} days" if nxt.days_until > 0 else "On now") if nxt else "—",
             note=f"{nxt.name}, {nxt.city}" if nxt else "None planned", tone="info" if nxt else "neutral"),
        Tile(key="clashes", label="Date clashes", value=str(len(groups)),
             note=(f"{twice} with someone booked twice" if twice else "Different people at each")
             if groups else "No overlapping dates", tone="warn" if twice else "neutral"),
        Tile(key="register", label="Registration due", value=str(len(due)),
             note=f"Deadline within {DEADLINE_WINDOW_DAYS} days" if due else "Nothing due soon",
             tone="warn" if due else "good"),
    ]  # fmt: skip
    attendees = sorted({p for r in in_year for p in r.attendees})
    return Conferences(
        year=chosen,
        years=years,
        tiles=tiles,
        conferences=rows,
        clash_groups=groups,
        next_id=nxt.id if nxt else None,
        not_on_map=sum(1 for r in rows if r.lat is None),
        attendees=attendees,
        tags=[t for t in TAGS if any(t in r.tags for r in in_year)],
        rules=CONFERENCE_RULES,
    )
