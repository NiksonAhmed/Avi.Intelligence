"""Sections contributed by optional modules (e.g. Data Management), registered by the module itself.

The Overview never imports an optional module; the module calls `register()` when it is loaded, and its
provider decides for itself whether it applies (module switched on, user allowed to see it).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.auth.rbac import CurrentUser

from .schemas import Kpi, Section, SourceInfo


@dataclass
class Contribution:
    sections: dict[str, Section] = field(default_factory=dict)
    """Keyed by section key; each role's layout picks the keys it wants."""
    sources: list[SourceInfo] = field(default_factory=list)
    highlights: dict[str, Kpi] = field(default_factory=dict)
    """Figures a role may put in "Needs your attention" (e.g. "dm_awaiting", "dm_clin_sig")."""


Provider = Callable[[Session, CurrentUser], Awaitable[Contribution]]

_PROVIDERS: list[Provider] = []


def register(provider: Provider) -> None:
    if provider not in _PROVIDERS:
        _PROVIDERS.append(provider)


def registered() -> list[Provider]:
    return list(_PROVIDERS)
