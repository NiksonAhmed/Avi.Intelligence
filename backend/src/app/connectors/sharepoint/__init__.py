"""SharePoint SOP connector: chooses the live Graph connector or the demo connector from settings."""

from __future__ import annotations

from functools import lru_cache

from app.core.config import Settings, get_settings

from .graph_client import GraphClient
from .live import GraphSopConnector
from .mapping import parse_field_map
from .mock import MockSopConnector
from .models import SopConnector


def build_sop_connector(settings: Settings) -> SopConnector:
    if settings.sharepoint_mode == "mock":
        return MockSopConnector("SHAREPOINT_MODE is set to mock.")
    if not settings.sharepoint_has_credentials:
        if settings.sharepoint_mode == "live":
            raise RuntimeError(
                "SHAREPOINT_MODE=live but SHAREPOINT_TENANT_ID, SHAREPOINT_CLIENT_ID, "
                "SHAREPOINT_CLIENT_SECRET or SHAREPOINT_SITE_URL is missing."
            )
        return MockSopConnector("SharePoint credentials are not configured (see .env.example).")

    assert settings.sharepoint_client_secret is not None  # guaranteed by sharepoint_has_credentials
    client = GraphClient(
        tenant_id=settings.sharepoint_tenant_id or "",
        client_id=settings.sharepoint_client_id or "",
        client_secret=settings.sharepoint_client_secret.get_secret_value(),
    )
    return GraphSopConnector(
        client,
        site_url=settings.sharepoint_site_url or "",
        library=settings.sharepoint_sop_library,
        folder=settings.sharepoint_sop_folder,
        field_map=parse_field_map(settings.sharepoint_sop_field_map),
        cache_seconds=settings.sharepoint_cache_minutes * 60,
    )


@lru_cache
def get_sop_connector() -> SopConnector:
    return build_sop_connector(get_settings())
