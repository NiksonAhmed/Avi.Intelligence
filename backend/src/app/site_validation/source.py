"""Chooses where sites come from: the site validation lists in SharePoint when configured, else demo data
(the same pattern as Conferences)."""

from __future__ import annotations

from functools import lru_cache

from app.connectors.sharepoint.graph_client import GraphClient
from app.core.config import Settings, get_settings
from app.site_feasibility.source import get_tracker_download
from app.site_feasibility.workbook import TrackerDownload

from .demo import DemoSiteSource
from .models import SiteValidationSource
from .sharepoint import SharePointSiteSource, parse_field_map
from .survey import SurveySiteSource


def build_site_source(settings: Settings, tracker: TrackerDownload | None = None) -> SiteValidationSource:
    if settings.site_validation_mode == "mock":
        return DemoSiteSource("SITE_VALIDATION_MODE is set to mock.")
    if not settings.site_validation_sites_list and tracker is not None:
        # Until physics' own record is connected: the sites' answers in the feasibility tracker.
        return SurveySiteSource(tracker)
    if not settings.site_validation_sites_list:
        return DemoSiteSource(
            "The site validation lists are not connected to SharePoint yet (SITE_VALIDATION_SITES_LIST)."
        )
    site = settings.site_validation_sharepoint_site_url or settings.sharepoint_site_url
    if not (settings.sharepoint_has_credentials and site and settings.sharepoint_client_secret):
        return DemoSiteSource("SharePoint access is not configured yet.")
    client = GraphClient(
        tenant_id=settings.sharepoint_tenant_id or "",
        client_id=settings.sharepoint_client_id or "",
        client_secret=settings.sharepoint_client_secret.get_secret_value(),
    )
    return SharePointSiteSource(
        client,
        site_url=site,
        sites_list=settings.site_validation_sites_list,
        validations_list=settings.site_validation_validations_list,
        scans_list=settings.site_validation_scans_list,
        fields=parse_field_map(settings.site_validation_field_map),
        cache_seconds=settings.sharepoint_cache_minutes * 60,
    )


@lru_cache
def _cached() -> SiteValidationSource:
    return build_site_source(get_settings(), get_tracker_download())


def get_site_source() -> SiteValidationSource:
    return _cached()
