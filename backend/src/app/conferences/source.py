"""Chooses where conferences come from: the BD team's SharePoint list when configured, else demo data."""

from __future__ import annotations

from functools import lru_cache

from app.connectors.sharepoint.graph_client import GraphClient
from app.core.config import Settings, get_settings

from .demo import DemoConferenceSource
from .models import ConferenceSource
from .sharepoint import SharePointConferenceSource, parse_field_map


def build_conference_source(settings: Settings) -> ConferenceSource:
    if settings.conferences_mode == "mock":
        return DemoConferenceSource("CONFERENCES_MODE is set to mock.")
    if not settings.conferences_sharepoint_list:
        return DemoConferenceSource(
            "The BD team's SharePoint conference list is not connected yet (CONFERENCES_SHAREPOINT_LIST)."
        )
    site = settings.conferences_sharepoint_site_url or settings.sharepoint_site_url
    if not (settings.sharepoint_has_credentials and site and settings.sharepoint_client_secret):
        return DemoConferenceSource("SharePoint access is not configured yet.")
    client = GraphClient(
        tenant_id=settings.sharepoint_tenant_id or "",
        client_id=settings.sharepoint_client_id or "",
        client_secret=settings.sharepoint_client_secret.get_secret_value(),
    )
    return SharePointConferenceSource(
        client,
        site_url=site,
        list_name=settings.conferences_sharepoint_list,
        fields=parse_field_map(settings.conferences_field_map),
        cache_seconds=settings.sharepoint_cache_minutes * 60,
    )


@lru_cache
def _cached() -> ConferenceSource:
    return build_conference_source(get_settings())


def get_conference_source() -> ConferenceSource:
    return _cached()
