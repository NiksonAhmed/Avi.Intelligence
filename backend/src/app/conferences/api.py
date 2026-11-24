"""Conferences API (read-only), its Excel export and its card on the Overview.

Answers 404 unless CONFERENCES_ENABLED is on (the module can be switched off per company).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.audit.service import record_event
from app.auth.rbac import CurrentUser, Permission, require
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.overview import providers
from app.overview.schemas import Kpi, Row, Section, SourceInfo
from app.reports.excel import Sheet, build_workbook
from app.studies.clock import today

from .models import TAGS, ConferenceSource, ConferenceSourceInfo
from .report import Conferences, build_conferences
from .source import get_conference_source


def enabled(settings: Annotated[Settings, Depends(get_settings)]) -> Settings:
    if not settings.conferences_enabled:
        raise HTTPException(404, "Conferences are not enabled.")
    return settings


router = APIRouter(prefix="/conferences", tags=["Conferences"], dependencies=[Depends(enabled)])

Source = Annotated[ConferenceSource, Depends(get_conference_source)]
Viewer = Annotated[CurrentUser, Depends(require(Permission.CONFERENCE_VIEW))]
Db = Annotated[Session, Depends(get_db)]


class ConferencesResponse(Conferences):
    source: ConferenceSourceInfo


Priority = Annotated[int | None, Query(ge=1, le=3, description="1, 2 or 3")]


def _tag(tag: str | None) -> str | None:
    if tag is not None and tag not in TAGS:
        raise HTTPException(422, f"Unknown tag: {tag}")
    return tag


async def _conferences(
    source: ConferenceSource,
    user: CurrentUser,
    year: int | None,
    priority: int | None = None,
    who: str | None = None,
    tag: str | None = None,
) -> ConferencesResponse:
    records = await source.list_conferences()
    report = build_conferences(records, today(), year=year, priority=priority, who=who, tag=_tag(tag))
    return ConferencesResponse(**report.model_dump(), source=source.info())


@router.get("", response_model=ConferencesResponse)
async def conferences(
    source: Source,
    user: Viewer,
    year: int | None = None,
    priority: Priority = None,
    who: str | None = None,
    tag: str | None = None,
) -> ConferencesResponse:
    return await _conferences(source, user, year, priority, who, tag)


@router.post("/refresh", status_code=204)
async def refresh(source: Source, user: Viewer) -> None:
    """Sync now: read the SharePoint list again (read-only)."""
    await source.list_conferences(force_refresh=True)


@router.get("/export.xlsx")
async def export(
    request: Request,
    db: Db,
    source: Source,
    user: Viewer,
    year: int | None = None,
    priority: Priority = None,
    who: str | None = None,
    tag: str | None = None,
) -> Response:
    r = await _conferences(source, user, year, priority, who, tag)
    header = ["Starts", "Ends", "Conference", "City", "Country", "Priority", "Who is going", "Tags",
              "Gov support", "Register by", "Registration (as written)", "Website", "Date clash with",
              "Reason"]  # fmt: skip
    rows = [
        [c.starts_on, c.ends_on, c.name, c.city, c.country, c.priority, c.team, ", ".join(c.tags),
         c.gov_support, c.register_by, c.registration, c.website,
         "; ".join(k.name + (f" ({', '.join(k.shared)} booked twice)" if k.shared else "")
                   for k in c.clashes),
         c.notes]
        for c in r.conferences
    ]  # fmt: skip
    filters = " · ".join(x for x in (f"Priority {priority}" if priority else None, who, tag) if x)
    about = [
        ("Report", "Conferences"),
        ("Year", str(r.year) + (f" · {filters}" if filters else "")),
        ("Source", "BD team's SharePoint list (read-only)" if r.source.mode == "sharepoint" else "Demo data"),
        ("Exported by", f"{user.name} on {datetime.now().strftime('%d %b %Y %H:%M')}"),
        *[(k.capitalize(), v) for k, v in r.rules.items()],
    ]
    content = build_workbook([Sheet("Conferences", header, rows)], about)
    record_event(
        db,
        user,
        action="report.exported",
        entity_type="report",
        entity_id="conferences",
        summary=f"Exported Conferences to Excel ({r.year})",
        details={
            "format": "xlsx",
            "year": r.year,
            "priority": priority,
            "who": who,
            "tag": tag,
        },
        request=request,
    )
    name = f"Conferences {r.year} {datetime.now(UTC).strftime('%Y-%m-%d')}.xlsx"
    return Response(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"},
    )


# ---- the "Next conferences" card on the Overview ------------------------------------------------------


async def contribute(_db: Session, user: CurrentUser) -> providers.Contribution:
    if not get_settings().conferences_enabled or not user.can(Permission.CONFERENCE_VIEW):
        return providers.Contribution()
    source = get_conference_source()
    r = await _conferences(source, user, None)
    upcoming = [c for c in r.conferences if not c.past]
    tiles = {t.key: t for t in r.tiles}
    section = Section(
        key="conferences",
        title="Next conferences",
        source="from SharePoint" if r.source.mode == "sharepoint" else "demo data",
        link="/conferences",
        link_label="Conferences",
        kpis=[
            Kpi(label=t.label, value=t.value, note=t.note, tone=t.tone, link="/conferences")
            for k in ("next", "register")
            if (t := tiles.get(k)) is not None
        ],
        rows=[
            Row(
                label=c.name,
                detail=" · ".join(
                    x for x in (c.city, c.country, f"Priority {c.priority}" if c.priority else None) if x
                ),
                chip=f"{c.starts_on.day} {c.starts_on:%b}" + (" · register soon" if c.register_soon else ""),
                tone="warn" if c.register_soon else "info",
                link="/conferences",
            )
            for c in upcoming[:3]
        ],
        notice=None
        if r.source.mode == "sharepoint"
        else "Demo conferences until the BD team's list is connected.",
        empty="No conferences planned.",
    )
    sources = (
        [SourceInfo(name="Conferences", as_of=r.source.fetched_at)] if r.source.mode == "sharepoint" else []
    )
    register = tiles.get("register")
    highlights = (
        {
            "conf_register": Kpi(
                label="Conference registrations due",
                value=register.value,
                note=register.note,
                tone=register.tone,
                link="/conferences",
            )
        }
        if register is not None
        else {}
    )
    return providers.Contribution(sections={"conferences": section}, sources=sources, highlights=highlights)


providers.register(contribute)

# Its answers in Ask Avi.Intelligence register themselves with the assistant here.
from . import assistant_topic  # noqa: E402, F401
