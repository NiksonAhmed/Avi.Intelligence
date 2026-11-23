"""One site as Avi.Intelligence shows it, whichever source it came from.

The fields follow the Site Feasibility Tracker's sections: Site Details, Equipment, PET/CT, SPECT/CT,
Dose Calibrator (PET and SPECT), Gamma Counter System, Phantoms and QA/QC, Image Data Storage and
Transfer, plus the isotope licences (IP) and the physics phantom scans.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Literal, Protocol

from pydantic import BaseModel, Field


class EquipmentKind(StrEnum):
    PET_CT = "PET/CT"
    SPECT_CT = "SPECT/CT"
    DOSE_CALIBRATOR = "Dose calibrator"
    GAMMA_COUNTER = "Gamma counter"


EQUIPMENT: list[EquipmentKind] = list(EquipmentKind)
SHORT = {
    EquipmentKind.PET_CT: "PET",
    EquipmentKind.SPECT_CT: "SPECT",
    EquipmentKind.DOSE_CALIBRATOR: "DC",
    EquipmentKind.GAMMA_COUNTER: "GC",
}
# The isotopes the tracker asks about (its "117Lu" is 177Lu).
ISOTOPES = ["64Cu", "68Ga", "90Y", "177Lu", "225Ac"]


class ScanStatus(StrEnum):
    BOOKED = "Booked"
    SCANNED = "Scanned"
    SUBMITTED = "Submitted to core lab"
    PASSED = "Passed"
    FAILED = "Failed"


class Equipment(BaseModel):
    kind: EquipmentKind
    manufacturer: str | None = None
    model: str | None = None
    installed: date | None = None
    last_calibration: date | None = None
    maintenance: str | None = None
    """Maintenance or QC schedule, as written (e.g. "Quarterly")."""
    replacement: str | None = None
    """Plans to replace it, as written; a replacement means validating again."""


class Validation(BaseModel):
    """One piece of equipment validated (calibrated) for one isotope."""

    equipment: EquipmentKind
    isotope: str
    validated_by: str
    """e.g. "ARTnet" or "Core lab"."""
    validated_on: date | None = None
    """None only for a site's own survey answer without a date."""
    files_available: bool | None = None
    """None: not recorded."""
    next_review: date | None = None
    """Set only when the physicist or core lab gives a date; otherwise 12 months after validation."""
    reported_by_site: bool = False
    """From the site's feasibility survey, not Avion physics' record: never due or overdue."""


class PhantomScan(BaseModel):
    study: str
    equipment: EquipmentKind
    isotope: str
    status: ScanStatus
    on: date
    """When it is booked for, or when it last changed status."""


class QaQc(BaseModel):
    phantoms: list[str] = Field(default_factory=list)
    used_for_study_scans: str | None = None
    records_access: str | None = None
    monthly_submission: str | None = None
    daily_qc_storage: str | None = None
    routines: dict[str, str] = Field(default_factory=dict)
    """QA/QC routine per scanner, e.g. {"PET/CT": "Daily QC · monthly SUV check"}."""


class ImageTransfer(BaseModel):
    pacs: str | None = None
    dicom_export: str | None = None
    methods: list[str] = Field(default_factory=list)
    """How images reach the core lab, e.g. ["sFTP", "Web (https)"]."""


class SiteRecord(BaseModel):
    id: str
    name: str
    department: str | None = None
    city: str
    state: str
    lat: float
    lon: float
    last_survey: date | None = None
    artnet_accreditation: str | None = None
    physicist: str | None = None
    """The site physicist as recorded in the tracker's contacts."""
    radiopharmacy: bool | None = None
    licensed: list[str] = Field(default_factory=list)
    """Isotopes the site is licensed for."""
    equipment: list[Equipment] = Field(default_factory=list)
    """Only the equipment the site has."""
    validations: list[Validation] = Field(default_factory=list)
    scans: list[PhantomScan] = Field(default_factory=list)
    qa: QaQc = Field(default_factory=QaQc)
    transfer: ImageTransfer = Field(default_factory=ImageTransfer)
    source_url: str | None = None
    """The item in SharePoint ("Open in SharePoint"); None for demo data."""


class SiteSourceInfo(BaseModel):
    mode: Literal["demo", "sharepoint", "survey"]
    """survey: the sites' own answers in the feasibility tracker (see survey.py)."""
    reason: str | None = None
    fetched_at: datetime | None = None


class SiteValidationSource(Protocol):
    def info(self) -> SiteSourceInfo: ...

    async def list_sites(self, *, force_refresh: bool = False) -> list[SiteRecord]: ...
