"""Records read from SimpleTrials (CTMS), independent of how they were obtained (API or export)."""

from __future__ import annotations

from datetime import date
from typing import Literal, Protocol

from pydantic import BaseModel, Field


class SiteRecord(BaseModel):
    external_id: str
    site_number: str
    name: str
    country: str | None = None
    principal_investigator: str | None = None
    status: str | None = None
    activation_date: date | None = None
    activation_target: date | None = None
    """Planned activation date (SimpleTrials: site_activation_target)."""
    enrolled: int | None = Field(default=None, ge=0)
    enrolment_target: int | None = Field(default=None, ge=0)


class MilestoneRecord(BaseModel):
    external_id: str
    name: str
    planned_date: date | None = None
    """Current planned date (SimpleTrials: end_date)."""
    actual_date: date | None = None
    """Actual completion date, when the source provides one (the SimpleTrials API does not)."""
    baseline_date: date | None = None
    """Original plan (SimpleTrials: baseline_end_date)."""
    percent_complete: int | None = Field(default=None, ge=0, le=100)
    phase: str | None = None
    """Grouping, e.g. the parent task "04. Site Startup Activities"."""
    kind: Literal["phase", "task", "milestone"] = "milestone"
    start_date: date | None = None
    """Current planned start (SimpleTrials: start_date)."""
    baseline_start_date: date | None = None
    """Original planned start (SimpleTrials: baseline_start_date)."""
    parent_external_id: str | None = None
    system_code: str | None = None
    """SimpleTrials' fixed code for standard milestones (e.g. "fpi"), stable across renames."""
    is_key: bool = False
    """Key milestone: drives the portfolio headline (overdue count, next milestone)."""


class StudyRecord(BaseModel):
    external_id: str
    protocol_number: str
    title: str
    sponsor: str | None = None
    phase: str | None = None
    therapeutic_area: str | None = None
    status: str | None = None
    countries: list[str] = Field(default_factory=list)
    project_manager: str | None = None
    enrolment_target: int | None = Field(default=None, ge=0)
    enrolled: int | None = Field(default=None, ge=0)
    """Study-level enrolled count reported by the source; if absent, the site counts are summed."""
    sandbox: bool = False
    """A SimpleTrials training/sandbox study holding fictitious data."""
    sites: list[SiteRecord] = Field(default_factory=list)
    milestones: list[MilestoneRecord] = Field(default_factory=list)


class StudyConnectorInfo(BaseModel):
    name: str = "SimpleTrials"
    mode: Literal["mock", "import", "api"]
    mock_reason: str | None = None
    scope: Literal["workspace", "study"] | None = None
    """API access level: all studies, or a single study."""
    base_url: str | None = None


class StudyConnector(Protocol):
    def info(self) -> StudyConnectorInfo: ...

    async def fetch_studies(self) -> list[StudyRecord]: ...
