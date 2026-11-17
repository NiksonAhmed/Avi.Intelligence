"""Chooses where feasibility answers come from. Demo data for now: the tracker's SharePoint lists are
connected together with the other Microsoft connections, once Microsoft sign-in is in place (user decision
2026-11-17)."""

from __future__ import annotations

from functools import lru_cache

from .demo import DemoFeasibilitySource
from .models import FeasibilitySource


@lru_cache
def _cached() -> FeasibilitySource:
    return DemoFeasibilitySource(
        "The site feasibility tracker is not connected to SharePoint yet; it will be connected with the "
        "other Microsoft lists once Microsoft sign-in is in place."
    )


def get_feasibility_source() -> FeasibilitySource:
    return _cached()
