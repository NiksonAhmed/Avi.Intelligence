"""Site validation figures: pure calculations over the site list (no estimates, no AI).

Rules (shown on the page behind the ⓘ):
- Next review: the date the physicist or core lab gave, otherwise 12 months after validation.
- Overdue: the next review date has passed. Due soon: within 60 days.
- Files missing: validated, but the certificate files are not on file.
- Booked: a phantom scan is booked and nothing is validated yet for that equipment and isotope.
- A site's colour on the map is its worst status for the filters chosen.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel

from app.reports.study_delivery import Tile, Tone

from .models import (
    EQUIPMENT,
    ISOTOPES,
    SHORT,
    Equipment,
    EquipmentKind,
    ImageTransfer,
    PhantomScan,
    QaQc,
    ScanStatus,
    SiteRecord,
    Validation,
)

REVIEW_MONTHS = 12
DUE_WINDOW_DAYS = 60

RULES = {
    "source": "Site validation tracker and physics phantom status (read-only copy).",
    "review": f"Next review: the date the physicist or core lab gave, otherwise {REVIEW_MONTHS} months after "
    "validation.",
    "status": f"Overdue: the review date has passed. Due soon: within {DUE_WINDOW_DAYS} days. Files missing: "
    "validated but the certificate is not on file. Booked: a phantom scan is booked and nothing is "
    "validated yet.",
    "map": "A site's colour is its worst status for the filters chosen; under each city is the equipment on "
    "site.",
}


class Status(StrEnum):
    """Worst first."""

    OVERDUE = "overdue"
    FILES_MISSING = "files_missing"
    DUE_SOON = "due_soon"
    BOOKED = "booked"
    IN_DATE = "in_date"
    NONE = "none"


ORDER = list(Status)
LABEL = {
    Status.OVERDUE: "Overdue",
    Status.FILES_MISSING: "Files missing",
    Status.DUE_SOON: "Due soon",
    Status.BOOKED: "Booked",
    Status.IN_DATE: "In date",
    Status.NONE: "Nothing validated",
}
VALIDATED = {Status.IN_DATE, Status.DUE_SOON, Status.FILES_MISSING}


def next_review(v: Validation) -> date:
    if v.next_review:
        return v.next_review
    d = v.validated_on
    try:
        return d.replace(year=d.year + REVIEW_MONTHS // 12)
    except ValueError:  # 29 February
        return d.replace(year=d.year + REVIEW_MONTHS // 12, day=28)


def status_of(v: Validation, today: date) -> Status:
    days = (next_review(v) - today).days
    if days < 0:
        return Status.OVERDUE
    if not v.files_available:
        return Status.FILES_MISSING
    return Status.DUE_SOON if days <= DUE_WINDOW_DAYS else Status.IN_DATE


class ValidationRow(BaseModel):
    site_id: str
    site: str
    city: str
    state: str
    equipment: EquipmentKind
    isotope: str
    validated_by: str | None
    validated_on: date | None
    files_available: bool | None
    next_review: date | None
    days_to_review: int | None
    scan_on: date | None
    """For a booked scan: when it is booked for."""
    status: Status


def _rows(site: SiteRecord, today: date) -> list[ValidationRow]:
    rows = [
        ValidationRow(
            site_id=site.id,
            site=site.name,
            city=site.city,
            state=site.state,
            equipment=v.equipment,
            isotope=v.isotope,
            validated_by=v.validated_by,
            validated_on=v.validated_on,
            files_available=v.files_available,
            next_review=next_review(v),
            days_to_review=(next_review(v) - today).days,
            scan_on=None,
            status=status_of(v, today),
        )
        for v in site.validations
    ]
    done = {(v.equipment, v.isotope) for v in site.validations}
    rows += [
        ValidationRow(
            site_id=site.id,
            site=site.name,
            city=site.city,
            state=site.state,
            equipment=s.equipment,
            isotope=s.isotope,
            validated_by=None,
            validated_on=None,
            files_available=None,
            next_review=None,
            days_to_review=None,
            scan_on=s.on,
            status=Status.BOOKED,
        )
        for s in site.scans
        if s.status == ScanStatus.BOOKED and (s.equipment, s.isotope) not in done
    ]
    return rows


def _worst(rows: list[ValidationRow]) -> Status:
    return min((r.status for r in rows), key=ORDER.index, default=Status.NONE)


class SitePin(BaseModel):
    id: str
    name: str
    city: str
    state: str
    lat: float
    lon: float
    status: Status
    equipment: list[str]
    """Short names of the equipment on site (PET, SPECT, DC, GC)."""
    attention: bool
    """Overdue, files missing or due soon: the pin pulses."""
    phantoms: int
    """How many phantoms the site has (Phantoms and QA/QC section)."""


class ReviewDue(BaseModel):
    site_id: str
    site: str
    city: str
    equipment: EquipmentKind
    isotope: str
    physicist: str | None
    next_review: date
    days: int


class ScanRow(BaseModel):
    site_id: str
    site: str
    city: str
    study: str
    equipment: EquipmentKind
    isotope: str
    status: ScanStatus
    on: date


class SiteValidation(BaseModel):
    headline: str
    tiles: list[Tile]
    sites: list[SitePin]
    reviews: list[ReviewDue]
    scans: list[ScanRow]
    rows: list[ValidationRow]
    equipment_options: list[EquipmentKind]
    isotope_options: list[str]
    rules: dict[str, str]


def _keep(row: ValidationRow, equipment: EquipmentKind | None, isotope: str | None) -> bool:
    return (equipment is None or row.equipment == equipment) and (isotope is None or row.isotope == isotope)


def build_site_validation(
    sites: list[SiteRecord],
    today: date,
    *,
    equipment: EquipmentKind | None = None,
    isotope: str | None = None,
) -> SiteValidation:
    by_site = {s.id: [r for r in _rows(s, today) if _keep(r, equipment, isotope)] for s in sites}
    rows = sorted(
        (r for rs in by_site.values() for r in rs),
        key=lambda r: (ORDER.index(r.status), r.next_review or r.scan_on or today, r.site),
    )
    pins = []
    for s in sites:
        worst = _worst(by_site[s.id])
        pins.append(
            SitePin(
                id=s.id,
                name=s.name,
                city=s.city,
                state=s.state,
                lat=s.lat,
                lon=s.lon,
                status=worst,
                equipment=[SHORT[e.kind] for e in sorted(s.equipment, key=lambda e: EQUIPMENT.index(e.kind))],
                attention=worst in (Status.OVERDUE, Status.FILES_MISSING, Status.DUE_SOON),
                phantoms=len(s.qa.phantoms),
            )
        )
    names = {s.id: s for s in sites}
    reviews = sorted(
        (
            ReviewDue(
                site_id=r.site_id,
                site=r.site,
                city=r.city,
                equipment=r.equipment,
                isotope=r.isotope,
                physicist=names[r.site_id].physicist,
                next_review=r.next_review,
                days=r.days_to_review,
            )
            for r in rows
            if r.next_review is not None and r.days_to_review is not None and r.days_to_review <= 120
        ),
        key=lambda x: x.next_review,
    )
    scans = sorted(
        (
            ScanRow(
                site_id=s.id,
                site=s.name,
                city=s.city,
                study=p.study,
                equipment=p.equipment,
                isotope=p.isotope,
                status=p.status,
                on=p.on,
            )  # fmt: skip
            for s in sites
            for p in s.scans
            if p.status != ScanStatus.PASSED
            and (equipment is None or p.equipment == equipment)
            and (isotope is None or p.isotope == isotope)
        ),
        key=lambda x: x.on,
    )

    def count(status: Status) -> int:
        return sum(1 for r in rows if r.status == status)

    validated = sum(1 for rs in by_site.values() if any(r.status in VALIDATED for r in rs))
    overdue, due, missing = count(Status.OVERDUE), count(Status.DUE_SOON), count(Status.FILES_MISSING)
    total = len(sites)

    tone_over: Tone = "bad" if overdue else "good"
    tone_due: Tone = "warn" if due else "good"
    tone_miss: Tone = "bad" if missing else "good"
    tiles = [
        Tile(key="validated", label="Sites validated", value=f"{validated} of {total}",
             note="At least one in-date validation", tone="info"),
        Tile(key="due", label=f"Reviews due in {DUE_WINDOW_DAYS} days", value=str(due),
             note="Physicist review coming up", tone=tone_due),
        Tile(key="overdue", label="Overdue", value=str(overdue),
             note="Review date has passed", tone=tone_over),
        Tile(key="missing", label="Files missing", value=str(missing),
             note="Validated, certificate not on file", tone=tone_miss),
        Tile(key="scans", label="Phantom scans in progress", value=str(len(scans)),
             note="Booked, scanned, submitted or failed", tone="info"),
    ]  # fmt: skip

    parts = [f"{validated} of {total} sites hold an in-date validation."]
    first = next((r for r in rows if r.status == Status.OVERDUE), None)
    if first:
        more = f" and {overdue - 1} more" if overdue > 1 else ""
        parts.append(f"{first.site} · {first.equipment.value} {first.isotope} is overdue{more}.")
    parts.append(
        f"{due} {'review is' if due == 1 else 'reviews are'} due in the next {DUE_WINDOW_DAYS} days"
        f" and {len(scans)} phantom {'scan is' if len(scans) == 1 else 'scans are'} in progress."
    )
    return SiteValidation(
        headline=" ".join(parts),
        tiles=tiles,
        sites=pins,
        reviews=reviews,
        scans=scans,
        rows=rows,
        equipment_options=EQUIPMENT,
        isotope_options=ISOTOPES,
        rules=RULES,
    )


# ---- one site: what pops up when it is clicked -----------------------------------------------------------


class GridCell(BaseModel):
    equipment: EquipmentKind
    isotope: str
    state: Status | None
    """None: the site does not have this equipment."""
    validated: bool
    """False with an equipment present and state NONE: not validated for this isotope."""
    tip: str


class SiteDetail(BaseModel):
    id: str
    name: str
    department: str | None
    city: str
    state: str
    status: Status
    last_survey: date | None
    artnet_accreditation: str | None
    physicist: str | None
    radiopharmacy: bool | None
    licensed: list[str]
    equipment: list[Equipment]
    """In the tracker's order; only what the site has."""
    missing_equipment: list[EquipmentKind]
    isotopes: list[str]
    grid: list[GridCell]
    qa: QaQc
    transfer: ImageTransfer
    scans: list[PhantomScan]
    rows: list[ValidationRow]
    source_url: str | None


def build_site_detail(site: SiteRecord, today: date) -> SiteDetail:
    rows = _rows(site, today)
    has = {e.kind for e in site.equipment}
    grid: list[GridCell] = []
    for kind in EQUIPMENT:
        for iso in ISOTOPES:
            row = next((r for r in rows if r.equipment == kind and r.isotope == iso), None)
            what = f"{kind.value} · {iso}"
            state: Status | None
            if kind not in has:
                state, tip = None, f"{kind.value}: not on site"
            elif row is None:
                state, tip = Status.NONE, f"{what}: not validated"
            elif row.status == Status.BOOKED:
                state, tip = row.status, f"{what}: scan booked {row.scan_on:%d %b %Y}"
            else:
                assert row.validated_on and row.next_review
                state = row.status
                tip = (
                    f"{what}: {LABEL[row.status]} · validated {row.validated_on:%d %b %Y}"
                    f" by {row.validated_by} · next review {row.next_review:%d %b %Y}"
                )
            validated = row is not None and row.status != Status.BOOKED and kind in has
            grid.append(GridCell(equipment=kind, isotope=iso, state=state, validated=validated, tip=tip))
    return SiteDetail(
        id=site.id,
        name=site.name,
        department=site.department,
        city=site.city,
        state=site.state,
        status=_worst(rows),
        last_survey=site.last_survey,
        artnet_accreditation=site.artnet_accreditation,
        physicist=site.physicist,
        radiopharmacy=site.radiopharmacy,
        licensed=site.licensed,
        equipment=sorted(site.equipment, key=lambda e: EQUIPMENT.index(e.kind)),
        missing_equipment=[k for k in EQUIPMENT if k not in has],
        isotopes=ISOTOPES,
        grid=grid,
        qa=site.qa,
        transfer=site.transfer,
        scans=sorted(site.scans, key=lambda s: s.on, reverse=True),
        rows=sorted(rows, key=lambda r: (ORDER.index(r.status), r.next_review or r.scan_on or today)),
        source_url=site.source_url,
    )
