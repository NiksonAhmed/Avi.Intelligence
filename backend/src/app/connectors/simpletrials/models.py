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


class EtmfDocumentRecord(BaseModel):
    """One expected or filed eTMF document: metadata only (no file, no file name, no people)."""

    external_id: str
    level: Literal["study", "country", "site"] = "study"
    site_external_id: str | None = None
    section: str
    """Top-level TMF folder, e.g. "01. General Study Documents"."""
    folder: str | None = None
    """The folder the document sits in, when below the section."""
    name: str
    """The expected document's name (SimpleTrials common_name), else its title."""
    filed: bool
    """False for a placeholder: an expected document not yet filed."""
    doc_status: str | None = None
    qc_status: str | None = None
    qc_started_on: date | None = None
    qc_ended_on: date | None = None
    created_on: date | None = None
    uploaded_on: date | None = None
    document_date: date | None = None
    """The document's own date (signature date, else version date), for filing timeliness."""
    expires_on: date | None = None
    expired: bool = False
    version: str | None = None


class ActionItemRecord(BaseModel):
    """One SimpleTrials action item (e.g. a site visit follow-up), shown as a read-only issue.

    Kept: number, category, priority, status, site, dates, description, response and the assignee's
    display name. Not kept: user ids. Unblinded and inactive items are never read."""

    external_id: str
    number: str | None = None
    category: str | None = None
    subcategory: str | None = None
    priority: str | None = None
    status: str | None = None
    closed: bool = False
    site_number: str | None = None
    site_name: str | None = None
    description: str | None = None
    response: str | None = None
    assignee: str | None = None
    opened_on: date | None = None
    due_on: date | None = None
    closed_on: date | None = None


class SiteVisitRecord(BaseModel):
    """One SimpleTrials site visit (pre-study, initiation, monitoring, close-out), read-only.

    Site visits only: subject visits are never read (no patient-level data). No people, titles, notes,
    locations or contact details are kept: only the site, the kind of visit, its status and dates."""

    external_id: str
    site_external_id: str | None = None
    kind: str | None = None
    """e.g. "Routine Monitoring Visit", "Initiation", "Prestudy"."""
    status: str | None = None
    """e.g. "Scheduled", "Confirmed", "Completed"."""
    starts_on: date | None = None
    ends_on: date | None = None


class DeviationRecord(BaseModel):
    """One SimpleTrials protocol deviation (read-only), for the Protocol deviations report.

    No subject IDs or people are kept (no patient-level data from SimpleTrials): only whether the
    deviation concerns a subject. Unblinded and inactive deviations are never read."""

    external_id: str
    number: str | None = None
    site_external_id: str | None = None
    site_number: str | None = None
    site_name: str | None = None
    category: str | None = None
    severity: str | None = None
    """Normalised: Critical, Major, Minor, or SimpleTrials' own wording; None when not classified."""
    status: str | None = None
    closed: bool = False
    description: str | None = None
    subject_level: bool = False
    occurred_on: date | None = None
    identified_on: date | None = None
    reported_on: date | None = None
    closed_on: date | None = None
    reportable: bool | None = None
    """Reportable to the ethics committee / IRB, when SimpleTrials records it."""


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
    documents: list[EtmfDocumentRecord] | None = None
    """eTMF document metadata; None when it could not be read (the previous copy is kept)."""
    action_items: list[ActionItemRecord] | None = None
    """SimpleTrials action items; None when they could not be read (the previous copy is kept)."""
    deviations: list[DeviationRecord] | None = None
    """SimpleTrials protocol deviations; None when they could not be read (the previous copy is kept)."""
    site_visits: list[SiteVisitRecord] | None = None
    """SimpleTrials site visits (monitoring etc.); None when they could not be read (previous copy kept)."""


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
