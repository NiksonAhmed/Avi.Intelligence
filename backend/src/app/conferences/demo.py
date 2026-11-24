"""Demo conferences, shown (and labelled as demo data) until the BD team's SharePoint list is connected.

Fictional entries in the shape of the BD schedules (priority, initials, tags, trade missions): names describe
the kind of event, not real conferences, and the initials are no one's. Dates move with today so the page
always has past and upcoming conferences, a registration due soon and two date clashes.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.studies.clock import today as app_today

from .geo import locate
from .models import ConferenceRecord, ConferenceSourceInfo

# (name, city, country, starts in days, length in days, priority, who, tags, gov support, register days
#  before (None: TBD), notes)
_DEMO: list[tuple[str, str, str, int, int, int, str, list[str], str | None, int | None, str]] = [
    ("Demo Clinical Operations Summit", "Orlando", "USA", 80, 3, 2, "AB", [], None, 55,
     "Clinical operations and outsourcing."),
    ("Demo Biotech Partnering Week", "San Francisco", "USA", 95, 4, 1, "AB", ["BIO Partnering"], None, 60,
     "Scheduled partnering meetings with newly financed biotechs."),
    ("Demo Radiopharmaceutical Congress", "Suzhou", "China", 150, 3, 1, "CD", ["BIO Partnering"],
     "Global Vic Trade Mission", 80, "Biotech, clinical research and CRO services in APAC."),
    ("Demo Theranostics Conference", "Osaka", "Japan", 151, 4, 1, "CD", [], None, 75,
     "Radioligand therapies and theranostics."),
    ("Demo Clinical Outsourcing Europe", "Barcelona", "Spain", 179, 2, 2, "EF", [], None, 80,
     "European sponsors and biotechs."),
    ("Demo Clinical Trials Asia", "Singapore", "Singapore", 186, 2, 1, "CD", ["AUS Delegate"], "Austrade", 84,
     "Asia-Pacific trial design and sponsor–CRO partnerships."),
    ("Demo Nuclear Medicine Meeting", "Washington, DC", "USA", 230, 4, 1, "CD", [], None, 90,
     "Largest North American nuclear medicine meeting."),
    ("Demo Global Biotech Convention", "Philadelphia", "USA", 232, 4, 1, "CD, AB", ["BIO Partnering",
     "AUS Delegate"], "AusBio Trade Mission", 100, "Largest global biotech conference; partnering."),
    ("Demo Oncology Congress", "Chicago", "USA", 229, 5, 1, "AB", ["BIO Partnering"], None, 95,
     "Global oncology clinical meeting."),
    ("Demo Biologics Festival", "Melbourne", "Australia", 284, 2, 2, "EF", [], None, None,
     "Biologics, cell and gene therapy, RNA therapeutics."),
    ("Demo Health Expo", "Dubai", "UAE", 300, 4, 3, "CD", [], "MTP Connect Trade Mission", None,
     "Healthcare exhibition across the Middle East."),
    ("Demo Clinical Outsourcing Europe", "Barcelona", "Spain", -186, 2, 2, "EF", [], None, 80, "Attended."),
    ("Demo European Partnering Forum", "Vienna", "Austria", -11, 2, 2, "AB", ["BIO Partnering"], None, 78,
     "Attended."),
]  # fmt: skip


class DemoConferenceSource:
    def __init__(self, reason: str, today: date | None = None) -> None:
        self._reason = reason
        self._today = today

    def info(self) -> ConferenceSourceInfo:
        return ConferenceSourceInfo(mode="demo", reason=self._reason, fetched_at=None)

    async def list_conferences(self, *, force_refresh: bool = False) -> list[ConferenceRecord]:
        t = self._today or app_today()
        out: list[ConferenceRecord] = []
        for n, row in enumerate(_DEMO, 1):
            name, city, country, starts, days, priority, who, tags, gov, before, notes = row
            start = t + timedelta(days=starts)
            place = locate(city)
            deadline = start - timedelta(days=before) if before is not None else None
            out.append(
                ConferenceRecord(
                    id=f"demo-{n}",
                    name=name,
                    city=city,
                    country=country,
                    lat=place[0] if place else None,
                    lon=place[1] if place else None,
                    starts_on=start,
                    ends_on=start + timedelta(days=days - 1),
                    priority=priority,
                    team=who,
                    attendees=[p.strip() for p in who.split(",")],
                    tags=tags,
                    gov_support=gov,
                    registration=f"EBR to {deadline.day} {deadline:%b}" if deadline else "TBD",
                    register_by=deadline,
                    website=None,
                    notes=notes,
                )
            )
        return out
