"""One site's feasibility answers as Avi.Intelligence shows them, whichever source they came from.

The fields follow the tracker's Feasibility sheet (Site Details, Predicted Timelines, Experience, IP,
Equipment, Administrative) and its Post-Activation sheet (projects, enrolment and the Overall Site
Assessment scores). Imaging equipment, isotope validations and phantoms live on Site validation instead.
Answers stay as the site gave them ("Yes", "No", "Not known"); None means not answered.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Protocol

from pydantic import BaseModel, Field

# The indications the tracker asks about, in its order.
INDICATIONS = [
    "Breast cancer",
    "Prostate cancer",
    "Non-small-cell lung cancer (NSCLC)",
    "Small-cell lung cancer (SCLC)",
    "Colorectal cancer",
    "Pancreatic cancer",
    "Gastric cancer",
    "Essential thrombocytopenia",
    "Myelofibrosis",
    "Melanoma",
    "Oral squamous cell carcinoma (OSCC)",
    "Head and neck squamous cell carcinoma (HNSCC)",
    "Infection",
]

# The tracker's general equipment checklist (imaging equipment is detailed on Site validation).
EQUIPMENT_CHECKLIST = [
    "ECG",
    "Room temperature centrifuge",
    "Refrigerated centrifuge",
    "Temperature-monitored secure storage (room temperature)",
    "Temperature-monitored secure storage (2–8 °C)",
    "Temperature-monitored secure storage (−20 °C / −80 °C)",
    "Liquid nitrogen for sample storage",
    "Biosafety cabinet",
    "CT or MRI scanner",
    "SPECT/CT or PET/CT scanner",
    "Gamma counter",
    "Dose calibrator",
    "Laboratory",
    "Radiopharmacy / hot lab",
    "Pharmacokinetic (PK) sampling",
]

# Overall Site Assessment (Post-Activation): each criterion and its maximum score.
SCORES: dict[str, int] = {
    "Time to RGO approval": 3,
    "Time to activation": 2,
    "Time to FPI": 5,
    "Recruitment success": 5,
    "CRA meeting with PI": 5,
    "Data entry": 5,
    "Query resolution": 5,
    "Site issues": 5,
    "Protocol deviations": 5,
}
SCORE_MAX = sum(SCORES.values())


class Timelines(BaseModel):
    """Predicted by the site, in weeks."""

    startup_weeks: float | None = None
    siv_weeks: float | None = None
    fpi_weeks: float | None = None


class TrialCounts(BaseModel):
    indication: str
    experience: str | None = None
    """Has the site treated or imaged this indication in trials ("Yes" / "No")."""
    imaging: int | None = None
    therapeutic: int | None = None


class Experience(BaseModel):
    imaging_trials: str | None = None
    therapeutic_trials: str | None = None
    isotopes: list[str] = Field(default_factory=list)
    """Radioisotopes the site has trial experience with."""
    patient_identification: str | None = None
    by_indication: list[TrialCounts] = Field(default_factory=list)
    active_imaging_trials: int | None = None


class IpReadiness(BaseModel):
    licensed: list[str] = Field(default_factory=list)
    trained: list[str] = Field(default_factory=list)
    """Isotopes the site's staff are trained to use."""
    handled: list[str] = Field(default_factory=list)
    """Isotopes the site has calibrated, drawn up and administered before."""
    treatment_days: str | None = None
    fridges: int | None = None
    freezers_20: int | None = None
    freezers_80: int | None = None


class Administrative(BaseModel):
    audited: str | None = None
    auditor: str | None = None
    major_findings: str | None = None
    sops: str | None = None
    radiation_licence: str | None = None
    central_hrec: str | None = None
    hrec_weeks: float | None = None
    additional_approvals: str | None = None
    contract_during_hrec: str | None = None
    contract_weeks: float | None = None
    artnet: str | None = None
    remote_monitoring: str | None = None
    remote_records: str | None = None


class Project(BaseModel):
    protocol: str
    indication: str | None = None
    expected_min: int | None = None
    expected_max: int | None = None
    actual: int | None = None


class Performance(BaseModel):
    """How the site did once activated (Post-Activation sheet)."""

    projects: list[Project] = Field(default_factory=list)
    scores: dict[str, int] = Field(default_factory=dict)
    """Overall Site Assessment, criterion → score (see SCORES for each maximum)."""
    competing_trials: str | None = None
    comments: str | None = None


class FeasibilitySite(BaseModel):
    id: str
    name: str
    department: str | None = None
    city: str
    state: str
    lat: float
    lon: float
    sector: str | None = None
    """Public or Private."""
    last_survey: date | None = None
    last_survey_study: str | None = None
    survey_type: str | None = None
    accepting: str | None = None
    """Is the site or department accepting new trials."""
    withdrawal: str | None = None
    """Known PI or site withdrawal, as written."""
    recommend_diagnostics: str | None = None
    recommend_therapeutics: str | None = None
    timelines: Timelines = Field(default_factory=Timelines)
    experience: Experience = Field(default_factory=Experience)
    ip: IpReadiness = Field(default_factory=IpReadiness)
    equipment: dict[str, str | None] = Field(default_factory=dict)
    """Checklist item → "Yes" / "No" / None (not answered)."""
    admin: Administrative = Field(default_factory=Administrative)
    performance: Performance | None = None
    source_url: str | None = None


class FeasibilitySourceInfo(BaseModel):
    mode: Literal["demo", "sharepoint"]
    reason: str | None = None
    fetched_at: datetime | None = None


class FeasibilitySource(Protocol):
    def info(self) -> FeasibilitySourceInfo: ...

    async def list_sites(self, *, force_refresh: bool = False) -> list[FeasibilitySite]: ...
