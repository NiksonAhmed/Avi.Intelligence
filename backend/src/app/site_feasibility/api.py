"""Site feasibility API (read-only) and its Excel export. Everyone may view (user decision 2026-11-18)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.audit.service import record_event
from app.auth.rbac import CurrentUser, Permission, require
from app.db.session import get_db
from app.reports.excel import Sheet, build_workbook
from app.site_validation.models import SiteValidationSource
from app.site_validation.source import get_site_source
from app.studies.clock import today

from .models import INDICATIONS, SCORE_MAX, FeasibilitySource, FeasibilitySourceInfo
from .report import (
    ISOTOPES,
    LABEL,
    Recommendation,
    SiteFeasibility,
    SiteFeasibilityDetail,
    build_site_detail,
    build_site_feasibility,
    score_of,
)
from .source import get_feasibility_source

router = APIRouter(prefix="/site-feasibility", tags=["Site feasibility"])

Source = Annotated[FeasibilitySource, Depends(get_feasibility_source)]
Validation = Annotated[SiteValidationSource, Depends(get_site_source)]
Viewer = Annotated[CurrentUser, Depends(require(Permission.SITE_FEASIBILITY_VIEW))]
Db = Annotated[Session, Depends(get_db)]


class SiteFeasibilityResponse(SiteFeasibility):
    source: FeasibilitySourceInfo


class SiteFeasibilityDetailResponse(SiteFeasibilityDetail):
    source: FeasibilitySourceInfo


def _check(isotope: str | None, indication: str | None) -> None:
    if isotope is not None and isotope not in ISOTOPES:
        raise HTTPException(422, f"Unknown isotope: {isotope}")
    if indication is not None and indication not in INDICATIONS:
        raise HTTPException(422, f"Unknown indication: {indication}")


async def _report(
    source: FeasibilitySource,
    isotope: str | None,
    indication: str | None,
    recommendation: Recommendation | None,
) -> SiteFeasibilityResponse:
    _check(isotope, indication)
    sites = await source.list_sites()
    r = build_site_feasibility(
        sites, today(), isotope=isotope, indication=indication, recommendation=recommendation
    )
    return SiteFeasibilityResponse(**r.model_dump(), source=source.info())


@router.get("", response_model=SiteFeasibilityResponse)
async def site_feasibility(
    source: Source,
    user: Viewer,
    isotope: str | None = None,
    indication: str | None = None,
    recommendation: Recommendation | None = None,
) -> SiteFeasibilityResponse:
    return await _report(source, isotope, indication, recommendation)


@router.get("/sites/{site_id}", response_model=SiteFeasibilityDetailResponse)
async def site_detail(
    site_id: str, source: Source, validation: Validation, user: Viewer
) -> SiteFeasibilityDetailResponse:
    site = next((s for s in await source.list_sites() if s.id == site_id), None)
    if site is None:
        raise HTTPException(404, "Site not found.")
    # The same site on Site validation (matched by name, as the SharePoint lists are).
    try:
        match = next(
            (v.id for v in await validation.list_sites() if v.name.casefold() == site.name.casefold()), None
        )
    except Exception:  # noqa: BLE001 (a link only: never fail the feasibility page because validation is down)
        match = None
    detail = build_site_detail(site, today(), match)
    return SiteFeasibilityDetailResponse(**detail.model_dump(), source=source.info())


@router.post("/refresh", status_code=204)
async def refresh(source: Source, user: Viewer) -> None:
    """Sync now: read the source again (read-only)."""
    await source.list_sites(force_refresh=True)


def _yes(v: object) -> object:
    return "—" if v is None else v


@router.get("/export.xlsx")
async def export(
    request: Request,
    db: Db,
    source: Source,
    user: Viewer,
    isotope: str | None = None,
    indication: str | None = None,
    recommendation: Recommendation | None = None,
) -> Response:
    r = await _report(source, isotope, indication, recommendation)
    chosen = {x.site_id for x in r.rows}
    sites = [s for s in await source.list_sites() if s.id in chosen]
    header = [
        "Site",
        "City",
        "State",
        "Sector",
        "Accepting new trials",
        "Recommendation",
        "Licensed for",
        "HREC (weeks)",
        "Contract (weeks)",
        "Start-up (weeks)",
        "Last survey",
        "Survey due",
        "Answered (%)",
        f"Performance score (of {SCORE_MAX})",
    ]
    rows = [
        [
            x.site,
            x.city,
            x.state,
            _yes(x.sector),
            _yes(x.accepting),
            LABEL[x.recommendation],
            ", ".join(x.licensed),
            _yes(x.hrec_weeks),
            _yes(x.contract_weeks),
            _yes(x.startup_weeks),
            x.last_survey,
            "Yes" if x.survey_due else "No",
            x.answered,
            _yes(x.score),
        ]
        for x in r.rows
    ]
    experience = [
        [s.name, c.indication, _yes(c.experience), _yes(c.imaging), _yes(c.therapeutic)]
        for s in sites
        for c in s.experience.by_indication
    ]
    performance = [
        [
            s.name,
            p.protocol,
            _yes(p.indication),
            _yes(p.expected_min),
            _yes(p.expected_max),
            _yes(p.actual),
            _yes(score_of(s.performance)),
        ]
        for s in sites
        if s.performance
        for p in s.performance.projects
    ]
    filters = " · ".join(
        x for x in (isotope, indication, LABEL[recommendation] if recommendation else None) if x
    )
    filters = filters or "All"
    about = [
        ("Report", "Site feasibility"),
        ("Filters", filters),
        ("Source", "SharePoint (read-only)" if r.source.mode == "sharepoint" else "Demo data"),
        ("Exported by", f"{user.name} on {datetime.now().strftime('%d %b %Y %H:%M')}"),
        *[(k.capitalize(), v) for k, v in r.rules.items()],
    ]
    content = build_workbook(
        [
            Sheet("Sites", header, rows),
            Sheet(
                "Experience",
                ["Site", "Indication", "Experience", "Imaging trials", "Therapeutic trials"],
                experience,
            ),
            Sheet(
                "Performance",
                [
                    "Site",
                    "Protocol",
                    "Indication",
                    "Expected min",
                    "Expected max",
                    "Actual enrolment",
                    "Score",
                ],
                performance,
            ),
        ],
        about,
    )
    record_event(
        db,
        user,
        action="report.exported",
        entity_type="report",
        entity_id="site-feasibility",
        summary=f"Exported Site feasibility to Excel ({filters})",
        details={
            "format": "xlsx",
            "isotope": isotope,
            "indication": indication,
            "recommendation": recommendation.value if recommendation else None,
        },
        request=request,
    )
    name = f"Site feasibility {datetime.now(UTC).strftime('%Y-%m-%d')}.xlsx"
    return Response(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"},
    )
