"""Site validation API (read-only) and its Excel export. Everyone may view (user decision 2026-11-17)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.audit.service import record_event
from app.auth.rbac import CurrentUser, Permission, require
from app.connectors.sharepoint.graph_client import GraphError
from app.core.config import get_settings
from app.db.session import get_db
from app.reports.excel import Sheet, build_workbook
from app.studies.clock import today

from .models import ISOTOPES, EquipmentKind, SiteRecord, SiteSourceInfo, SiteValidationSource
from .report import LABEL, SiteDetail, SiteValidation, build_site_detail, build_site_validation
from .sharepoint import SharePointSiteSource
from .source import get_site_source

SCAN_HEADER = ["Site", "City", "Study", "Equipment", "Isotope", "Status", "Date"]

router = APIRouter(prefix="/site-validation", tags=["Site validation"])
# Administration: the connector's status (connector managers only).
admin_router = APIRouter(prefix="/connectors/site-validation", tags=["Administration"])

Source = Annotated[SiteValidationSource, Depends(get_site_source)]
Viewer = Annotated[CurrentUser, Depends(require(Permission.SITE_VALIDATION_VIEW))]
Manager = Annotated[CurrentUser, Depends(require(Permission.CONNECTOR_MANAGE))]
Db = Annotated[Session, Depends(get_db)]


class SiteValidationResponse(SiteValidation):
    source: SiteSourceInfo


class SiteDetailResponse(SiteDetail):
    source: SiteSourceInfo


def _isotope(isotope: str | None) -> str | None:
    if isotope is not None and isotope not in ISOTOPES:
        raise HTTPException(422, f"Unknown isotope: {isotope}")
    return isotope


async def _report(
    source: SiteValidationSource, equipment: EquipmentKind | None, isotope: str | None
) -> SiteValidationResponse:
    sites = await source.list_sites()
    r = build_site_validation(sites, today(), equipment=equipment, isotope=_isotope(isotope))
    return SiteValidationResponse(**r.model_dump(), source=source.info())


@router.get("", response_model=SiteValidationResponse)
async def site_validation(
    source: Source, user: Viewer, equipment: EquipmentKind | None = None, isotope: str | None = None
) -> SiteValidationResponse:
    return await _report(source, equipment, isotope)


@router.get("/sites/{site_id}", response_model=SiteDetailResponse)
async def site_detail(site_id: str, source: Source, user: Viewer) -> SiteDetailResponse:
    site = next((s for s in await source.list_sites() if s.id == site_id), None)
    if site is None:
        raise HTTPException(404, "Site not found.")
    return SiteDetailResponse(**build_site_detail(site, today()).model_dump(), source=source.info())


@router.post("/refresh", status_code=204)
async def refresh(source: Source, user: Viewer) -> None:
    """Sync now: read the source again (read-only)."""
    await source.list_sites(force_refresh=True)


@router.get("/export.xlsx")
async def export(
    request: Request,
    db: Db,
    source: Source,
    user: Viewer,
    equipment: EquipmentKind | None = None,
    isotope: str | None = None,
) -> Response:
    r = await _report(source, equipment, isotope)
    header = ["Site", "City", "State", "Equipment", "Isotope", "Validated by", "Validated on",
              "Files on file", "Next review", "Phantom scan booked", "Status"]  # fmt: skip
    rows = [
        [x.site, x.city, x.state, x.equipment.value, x.isotope, x.validated_by, x.validated_on,
         x.files_available, x.next_review, x.scan_on, LABEL[x.status]]
        for x in r.rows
    ]  # fmt: skip
    scans = [[s.site, s.city, s.study, s.equipment.value, s.isotope, s.status.value, s.on] for s in r.scans]
    filters = " · ".join(x for x in (equipment.value if equipment else None, isotope) if x) or "All"
    about = [
        ("Report", "Site validation status"),
        ("Filters", filters),
        ("Source", "SharePoint (read-only)" if r.source.mode == "sharepoint" else "Demo data"),
        ("Exported by", f"{user.name} on {datetime.now().strftime('%d %b %Y %H:%M')}"),
        *[(k.capitalize(), v) for k, v in r.rules.items()],
    ]
    content = build_workbook(
        [
            Sheet("Validations", header, rows),
            Sheet(
                "Phantom scans", ["Site", "City", "Study", "Equipment", "Isotope", "Status", "Date"], scans
            ),
        ],
        about,
    )
    record_event(
        db,
        user,
        action="report.exported",
        entity_type="report",
        entity_id="site-validation",
        summary=f"Exported Site validation status to Excel ({filters})",
        details={"format": "xlsx", "equipment": equipment.value if equipment else None, "isotope": isotope},
        request=request,
    )
    name = f"Site validation {datetime.now(UTC).strftime('%Y-%m-%d')}.xlsx"
    return Response(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"},
    )


# ---- Administration: is the SharePoint connection working? ---------------------------------------------


class SiteValidationConnector(BaseModel):
    mode: Literal["demo", "sharepoint"]
    reason: str | None
    """Why demo data is shown."""
    site_url: str | None
    sites_list: str | None
    validations_list: str | None
    scans_list: str | None
    ok: bool | None
    """None in demo mode; else whether the last read worked."""
    error: str | None
    fetched_at: datetime | None
    counts: dict[str, int]
    skipped: dict[str, int]
    """Rows that could not be used (missing name, place, equipment, isotope or date; or no matching site)."""


async def _status(source: SiteValidationSource, refresh: bool) -> SiteValidationConnector:
    info = source.info()
    settings = get_settings()
    if not isinstance(source, SharePointSiteSource):
        return SiteValidationConnector(
            mode="demo", reason=info.reason, site_url=None, sites_list=None, validations_list=None,
            scans_list=None, ok=None, error=None, fetched_at=None, counts={}, skipped={},
        )  # fmt: skip
    sites_list, validations_list, scans_list = source.lists()
    error = None
    sites: list[SiteRecord] = []
    try:
        sites = await source.list_sites(force_refresh=refresh)
    except GraphError as e:
        error = f"SharePoint answered {e.status}: {e}"
    except Exception as e:  # noqa: BLE001 (shown to the administrator, never raised)
        error = f"Could not read the lists: {type(e).__name__}"
    return SiteValidationConnector(
        mode="sharepoint",
        reason=None,
        site_url=settings.site_validation_sharepoint_site_url or settings.sharepoint_site_url,
        sites_list=sites_list,
        validations_list=validations_list,
        scans_list=scans_list,
        ok=error is None,
        error=error,
        fetched_at=source.info().fetched_at,
        counts={
            "sites": len(sites),
            "validations": sum(len(s.validations) for s in sites),
            "scans": sum(len(s.scans) for s in sites),
        },
        skipped=source.skipped,
    )


@admin_router.get("", response_model=SiteValidationConnector)
async def connector_status(source: Source, user: Manager) -> SiteValidationConnector:
    return await _status(source, refresh=False)


@admin_router.post("/test", response_model=SiteValidationConnector)
async def connector_test(source: Source, user: Manager) -> SiteValidationConnector:
    """Read the lists again now and report what came back (read-only)."""
    return await _status(source, refresh=True)
