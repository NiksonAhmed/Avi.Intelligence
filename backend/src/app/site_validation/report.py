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
    REPORTED = "reported"
    """The site says it is calibrated (feasibility survey); not Avion physics' record, no review date."""
    NONE = "none"


ORDER = list(Status)
LABEL = {
    Status.OVERDUE: "Overdue",
    Status.FILES_MISSING: "Files missing",
    Status.DUE_SOON: "Due soon",
    Status.BOOKED: "Booked",
    Status.IN_DATE: "In date",
    Status.REPORTED: "Calibrated (site's answer)",
    Status.NONE: "Nothing validated",
}
VALIDATED = {Status.IN_DATE, Status.DUE_SOON, Status.FILES_MISSING}


def next_review(v: Validation) -> date | None:
    if v.next_review:
        return v.next_review
    d = v.validated_on
    if d is None or v.reported_by_site:
        return None
    try:
        return d.replace(year=d.year + REVIEW_MONTHS // 12)
    except ValueError:  # 29 February
        return d.replace(year=d.year + REVIEW_MONTHS // 12, day=28)


def status_of(v: Validation, today: date) -> Status:
    review = next_review(v)
    if v.reported_by_site or review is None:
        return Status.REPORTED
    days = (review - today).days
    if days < 0:
        return Status.OVERDUE
    if v.files_available is False:
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
            next_review=(review := next_review(v)),
            days_to_review=(review - today).days if review else None,
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
    survey: bool = False,
) -> SiteValidation:
    """survey: the sites' own feasibility answers, which have no review dates or phantom scans."""
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

    if survey:
        return _survey_page(sites, by_site, pins, rows, today, equipment)
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


SURVEY_RULES = {
    "source": "The sites' own answers in the Site Feasibility Tracker (read-only copy from SharePoint).",
    "survey": "Answers over 12 months old: the site's last survey was returned 12 or more months ago "
    "(the same rule as Site feasibility), so its answers may be out of date.",
    "status": "Calibrated (site's answer): the site said in its feasibility survey that this equipment is "
    "calibrated for the isotope (usually by ARTnet). Mostly no dates or certificates are recorded and Avion "
    "physics has not checked them, so nothing is shown as due or overdue.",
    "map": "A site's colour shows whether it reports any calibration for the filters chosen; under each "
    "city is the equipment on site.",
}


SURVEY_MONTHS = 12


def _months_ago(d: date, today: date) -> int:
    return (today.year - d.year) * 12 + today.month - d.month - (today.day < d.day)


def survey_out_of_date(site: SiteRecord, today: date) -> bool:
    """The same rule as Site feasibility's "survey due": no survey, or returned 12 or more months ago."""
    return site.last_survey is None or _months_ago(site.last_survey, today) >= SURVEY_MONTHS


def _survey_page(
    sites: list[SiteRecord],
    by_site: dict[str, list[ValidationRow]],
    pins: list[SitePin],
    rows: list[ValidationRow],
    today: date,
    equipment: EquipmentKind | None,
) -> SiteValidation:
    """Tiles from what the sites' survey answers hold; nothing that would always be empty."""
    total = len(sites)
    reporting = sum(1 for rs in by_site.values() if any(r.status == Status.REPORTED for r in rs))
    pairs: dict[tuple[str, str], int] = {}
    for r in rows:
        if r.status == Status.REPORTED:
            pairs[(r.equipment.value, r.isotope)] = pairs.get((r.equipment.value, r.isotope), 0) + 1
    artnet = sum(1 for s in sites if (s.artnet_accreditation or "").startswith("Yes"))
    kinds = [{e.kind for e in s.equipment} for s in sites]
    if equipment is None:
        imaging = sum(1 for k in kinds if k & {EquipmentKind.PET_CT, EquipmentKind.SPECT_CT})
        pet = sum(1 for k in kinds if EquipmentKind.PET_CT in k)
        spect = sum(1 for k in kinds if EquipmentKind.SPECT_CT in k)
        imaging_tile = Tile(
            key="imaging",
            label="PET/CT or SPECT/CT on site",
            value=f"{imaging} of {total}",
            note=f"PET/CT {pet} · SPECT/CT {spect}",
            tone="info",
        )
    else:
        having = sum(1 for k in kinds if equipment in k)
        imaging = having
        imaging_tile = Tile(
            key="imaging",
            label=f"{equipment.value} on site",
            value=f"{having} of {total}",
            note="As the site reported",
            tone="info",
        )
    phantoms = sum(1 for s in sites if s.qa.phantoms)
    stale = sum(1 for s in sites if survey_out_of_date(s, today))
    tiles = [
        Tile(key="validated", label="Sites reporting a calibration", value=f"{reporting} of {total}",
             note="Equipment calibrated for an isotope (mostly ARTnet)", tone="info"),
        Tile(key="artnet", label="ARTnet accredited", value=f"{artnet} of {total}",
             note="ARTnet or equivalent accreditation", tone="info"),
        imaging_tile,
        Tile(key="phantoms", label="Phantoms listed", value=f"{phantoms} of {total}",
             note="Sites that said which phantoms they have", tone="info"),
        Tile(key="stale", label=f"Answers over {SURVEY_MONTHS} months old", value=str(stale),
             note="Ask the site for a new survey", tone="warn" if stale else "good"),
    ]  # fmt: skip
    where = equipment.value if equipment else "PET/CT or SPECT/CT"
    parts = [f"{reporting} of {total} sites report a calibration; {imaging} have {where}"]
    parts[0] += f"; {stale} {'survey is' if stale == 1 else 'surveys are'} over {SURVEY_MONTHS} months old."
    if pairs:
        (kind, iso), n = max(pairs.items(), key=lambda kv: (kv[1], kv[0]))
        parts.append(f"Most often {kind} for {iso} ({n} {'site' if n == 1 else 'sites'}).")
    parts.append("These are the sites' own answers, not verified by Avion physics.")
    return SiteValidation(
        headline=" ".join(parts),
        tiles=tiles,
        sites=[p.model_copy(update={"attention": False}) for p in pins],
        reviews=[],
        scans=[],
        rows=rows,
        equipment_options=EQUIPMENT,
        isotope_options=ISOTOPES,
        rules=SURVEY_RULES,
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
            elif row.status == Status.REPORTED:
                state = row.status
                files = {True: " · certificate on file", False: " · certificate not on file"}
                tip = (
                    f"{what}: calibrated, as the site reported"
                    + (
                        f" by {row.validated_by}"
                        if row.validated_by and row.validated_by != "Not stated"
                        else ""
                    )
                    + (
                        f" · certified {row.validated_on:%d %b %Y}"
                        if row.validated_on
                        else " · no date given"
                    )
                    + files.get(row.files_available, "")  # type: ignore[arg-type]
                )
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
