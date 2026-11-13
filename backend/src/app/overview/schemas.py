"""The shapes of the Overview page: generic sections of figures and rows, each linking to its detail."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

Tone = Literal["good", "info", "warn", "bad", "neutral"]


class Kpi(BaseModel):
    """One figure; `link` opens the page with the detail."""

    label: str
    value: str
    note: str | None = None
    tone: Tone = "neutral"
    link: str | None = None


class Row(BaseModel):
    """One line in a section (a task, a site, a document...)."""

    label: str
    detail: str | None = None
    chip: str | None = None
    tone: Tone = "neutral"
    link: str | None = None


class Section(BaseModel):
    key: str
    title: str
    source: str
    """Where the figures come from, e.g. "from SimpleTrials"."""
    link: str | None = None
    link_label: str | None = None
    kpis: list[Kpi] = []
    rows: list[Row] = []
    notice: str | None = None
    """Shown instead of, or above, the figures (e.g. "not connected yet", "could not load")."""
    empty: str | None = None
    """Shown when there are no rows."""


class SourceInfo(BaseModel):
    name: str
    as_of: datetime | None
    ok: bool = True


class Attention(BaseModel):
    counts: list[Kpi]
    items: list[Row]


class ViewOption(BaseModel):
    id: str
    label: str


class Overview(BaseModel):
    view: str
    view_label: str
    views: list[ViewOption]
    """Views this person may switch to: their own role; administrators may preview every role."""
    purpose: str
    sources: list[SourceInfo]
    attention: Attention
    sections: list[Section]
