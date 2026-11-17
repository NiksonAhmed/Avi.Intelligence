"""Where the sites come from. Demo data for now: the tracker is not in SharePoint lists yet (user decision
2026-11-17: build with demo data first; connect SharePoint later, the same way as Conferences)."""

from __future__ import annotations

from functools import lru_cache

from .demo import DemoSiteSource
from .models import SiteValidationSource


@lru_cache
def _cached() -> SiteValidationSource:
    return DemoSiteSource("The site validation tracker is not connected to SharePoint yet.")


def get_site_source() -> SiteValidationSource:
    return _cached()
