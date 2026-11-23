"""Chooses where feasibility answers come from: the Site Feasibility Tracker workbook in SharePoint when its
drive and item IDs are set (user decision 2026-11-23), else demo sites."""

from __future__ import annotations

from functools import lru_cache

from app.connectors.sharepoint.graph_client import GraphClient
from app.core.config import Settings, get_settings

from .demo import DemoFeasibilitySource
from .models import FeasibilitySource
from .workbook import TrackerDownload, WorkbookFeasibilitySource


def build_tracker_download(settings: Settings) -> TrackerDownload | None:
    """The tracker in SharePoint, when its IDs and the SharePoint app credentials are set."""
    secret = settings.sharepoint_client_secret
    if not (settings.site_feasibility_drive_id and settings.site_feasibility_item_id):
        return None
    if not (settings.sharepoint_tenant_id and settings.sharepoint_client_id and secret):
        return None
    client = GraphClient(
        tenant_id=settings.sharepoint_tenant_id,
        client_id=settings.sharepoint_client_id,
        client_secret=secret.get_secret_value(),
    )
    return TrackerDownload(
        client,
        drive_id=settings.site_feasibility_drive_id,
        item_id=settings.site_feasibility_item_id,
        cache_seconds=settings.sharepoint_cache_minutes * 60,
    )


@lru_cache
def get_tracker_download() -> TrackerDownload | None:
    """One download shared by Site feasibility and Site validation."""
    return build_tracker_download(get_settings())


def build_feasibility_source(
    settings: Settings, download: TrackerDownload | None = None
) -> FeasibilitySource:
    if settings.site_feasibility_mode == "mock":
        return DemoFeasibilitySource("SITE_FEASIBILITY_MODE is set to mock.")
    if not (settings.site_feasibility_drive_id and settings.site_feasibility_item_id):
        return DemoFeasibilitySource(
            "The site feasibility tracker is not connected yet "
            "(SITE_FEASIBILITY_DRIVE_ID and SITE_FEASIBILITY_ITEM_ID)."
        )
    download = download or build_tracker_download(settings)
    if download is None:
        return DemoFeasibilitySource("SharePoint access is not configured yet.")
    return WorkbookFeasibilitySource(download)


@lru_cache
def _cached() -> FeasibilitySource:
    return build_feasibility_source(get_settings(), get_tracker_download())


def get_feasibility_source() -> FeasibilitySource:
    return _cached()
