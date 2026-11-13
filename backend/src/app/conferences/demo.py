"""Demo conferences, shown (and labelled as demo data) until the BD team's SharePoint list is connected.

Fictional entries: names describe the kind of event, not real conferences. Dates move with today so the
page always has past and upcoming conferences.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.studies.clock import today as app_today

from .geo import locate
from .models import AvionRole, ConferenceRecord, ConferenceSourceInfo

# (name, city, country, starts in days, length in days, role, team, booth, register days before, cost, notes)
_DEMO: list[tuple[str, str, str, int, int, AvionRole, str, str | None, int, float | None, str]] = [
    ("Demo Clinical Operations Summit", "Orlando", "USA", 80, 3, AvionRole.ATTENDING,
     "2 people · BD, Clinical Operations", None, 55, 4200, "Clinical operations and outsourcing"),
    ("Demo Rare Disease Congress", "Boston", "USA", 158, 2, AvionRole.SPEAKING,
     "2 people · BD, Medical", None, 70, 5100, "Talk on rare disease site selection"),
    ("Demo Clinical Outsourcing Europe", "Barcelona", "Spain", 179, 1, AvionRole.EXHIBITING,
     "2 people · BD", "B12", 80, 9800, "European sponsors and biotechs"),
    ("Demo Drug Development Meeting China", "Suzhou", "China", 188, 3, AvionRole.CONSIDERING,
     "To decide", None, 80, None, "APAC expansion"),
    ("Demo Biotech Partnering Convention", "San Diego", "USA", 206, 3, AvionRole.ATTENDING,
     "2 people · BD", None, 84, 6300, "Partnering meetings"),
    ("Demo Global Drug Development Meeting", "Philadelphia", "USA", 219, 4, AvionRole.EXHIBITING,
     "3 people · BD, Project Management", "1407", 80, 18500, "Main US event for sponsor meetings"),
    ("Demo Asia Biotech Forum", "Taipei", "Taiwan", 251, 3, AvionRole.CONSIDERING,
     "To decide", None, 82, None, ""),
    ("Demo Early-Phase Trials Australia", "Sydney", "Australia", 284, 2, AvionRole.SPEAKING,
     "1 person · Medical", None, 84, 7200, "Early-phase trials in Australia"),
    ("Demo Oncology Congress", "Berlin", "Germany", 336, 4, AvionRole.CONSIDERING,
     "To decide", None, 107, None, "Oncology sponsors"),
    ("Demo European Partnering Forum", "Stockholm", "Sweden", 353, 2, AvionRole.ATTENDING,
     "1 person · BD", None, 78, 3900, "Partnering"),
    ("Demo Clinical Outsourcing Europe", "Barcelona", "Spain", -186, 1, AvionRole.EXHIBITING,
     "2 people · BD", "B07", 80, 9400, "Attended"),
    ("Demo Global Drug Development Meeting", "Washington, DC", "USA", -152, 4, AvionRole.EXHIBITING,
     "3 people · BD", "1311", 80, 17900, "Attended"),
    ("Demo European Partnering Forum", "Vienna", "Austria", -11, 2, AvionRole.ATTENDING,
     "1 person · BD", None, 78, 3700, "Attended"),
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
        for n, (name, city, country, starts, days, role, team, booth, before, cost, notes) in enumerate(
            _DEMO, 1
        ):
            start = t + timedelta(days=starts)
            place = locate(city)
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
                    role=role,
                    team=team,
                    booth=booth,
                    register_by=start - timedelta(days=before),
                    notes=notes or None,
                    cost=cost,
                    currency="USD",
                )
            )
        return out
