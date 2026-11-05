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
    enrolled: int | None = Field(default=None, ge=0)
    enrolment_target: int | None = Field(default=None, ge=0)


class MilestoneRecord(BaseModel):
    external_id: str
    name: str
    planned_date: date | None = None
    actual_date: date | None = None


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
    sites: list[SiteRecord] = Field(default_factory=list)
    milestones: list[MilestoneRecord] = Field(default_factory=list)


class StudyConnectorInfo(BaseModel):
    name: str = "SimpleTrials"
    mode: Literal["mock", "import", "api"]
    mock_reason: str | None = None


class StudyConnector(Protocol):
    def info(self) -> StudyConnectorInfo: ...

    async def fetch_studies(self) -> list[StudyRecord]: ...
