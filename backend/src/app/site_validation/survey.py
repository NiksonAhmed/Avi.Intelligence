"""Site validation from the sites' own feasibility survey answers (user decision 2026-11-23).

Until Avion physics' own validation record is connected, Site validation reads the same Site Feasibility
Tracker as Site feasibility (one shared download) and shows what each site said in its latest survey: the
imaging equipment it has, whether each piece is calibrated (usually by ARTnet) for each isotope, its phantoms,
QA/QC and image transfer. These are the sites' answers, mostly without dates, and not checked by Avion
physics, so they get their own status ("Calibrated (site's answer)") and are never due or overdue. The
tracker has no phantom-scan stages, so there are no scans.
"""

from __future__ import annotations

from datetime import datetime

from app.site_feasibility.models import FeasibilitySite
from app.site_feasibility.workbook import (
    Row,
    TrackerDownload,
    a_date,
    latest_surveys,
    load_sheets,
    text,
    yes_no,
)

from .models import (
    ISOTOPES,
    Equipment,
    EquipmentKind,
    ImageTransfer,
    QaQc,
    SiteRecord,
    SiteSourceInfo,
    Validation,
)

REASON = (
    "From the sites' own feasibility survey answers: what each site said it has and is calibrated for, "
    "mostly without dates and not verified by Avion physics. Review dates, certificates on file and phantom "
    "scans are not in the survey; they come with the physics validation record."
)

# The tracker's section(s) for each piece of equipment (section names as read, lower case).
_SECTIONS: dict[EquipmentKind, tuple[str, ...]] = {
    EquipmentKind.PET_CT: ("pet/ct",),
    EquipmentKind.SPECT_CT: ("spect/ct",),
    EquipmentKind.DOSE_CALIBRATOR: ("dose calibrator (dc) - pet", "dose calibrator (dc) - spect"),
    EquipmentKind.GAMMA_COUNTER: ("gamma counter",),
}
# The general Equipment question that also says the site has it.
_HAS: dict[EquipmentKind, str] = {
    EquipmentKind.DOSE_CALIBRATOR: "dose calibrator to measure",
    EquipmentKind.GAMMA_COUNTER: "do you have a gamma counter",
}
_NONE_WORDS = {"n/a", "na", "no", "none", "nil", "-", "not applicable", "not known", "unknown"}
_ROUTINES = {
    "SPECT/CT": "qa/qc routines spect/ct",
    "PET/CT": "qa/qc routines pet/ct",
    "CT": "qa/qc routines for ct",
    "MRI": "qa/qc routines for mri",
}
_TRANSFER_LABELS = {"ftp": "FTP", "sftp": "sFTP", "web (https)": "Web (https)"}


def _tokens(isotope: str) -> list[str]:
    return [isotope.lower()] + (["117lu"] if isotope == "177Lu" else [])  # the template's typo


def _real(value: object) -> str | None:
    t = text(value)
    return None if t is None or t.strip().lower() in _NONE_WORDS else t


def _columns(row: Row, prefixes: tuple[str, ...]) -> list[int]:
    return [i for i, s in enumerate(row.headers.sections) if s.startswith(prefixes)]


def _first(row: Row, cols: list[int], *words: str, exclude: tuple[str, ...] = ()) -> object:
    for i in cols:
        name = row.headers.names[i]
        if all(w in name for w in words) and not any(x in name for x in exclude):
            value = row.at(i)
            if value is not None:
                return value
    return None


def _validations(row: Row, kind: EquipmentKind, cols: list[int]) -> list[Validation]:
    out: dict[str, Validation] = {}
    names = row.headers.names
    for iso in ISOTOPES:
        for i in cols:
            name = names[i]
            if not any(t in name for t in _tokens(iso)) or "calibrat" not in name:
                continue
            if any(x in name for x in ("date", "if no", "preset", "files")):
                continue
            if yes_no(row.at(i)) != "Yes":
                continue

            def near(*words: str, iso: str = iso) -> object:
                for j in cols:
                    n = names[j]
                    if any(t in n for t in _tokens(iso)) and all(w in n for w in words):
                        value = row.at(j)
                        if value is not None:
                            return value
                return None

            files = yes_no(near("availab"))
            artnet = "artnet" in name or yes_no(near("artnet certification")) == "Yes"
            out.setdefault(
                iso,
                Validation(
                    equipment=kind,
                    isotope=iso,
                    validated_by="ARTnet" if artnet else "Not stated",
                    validated_on=a_date(near("date of")),
                    files_available=True if files == "Yes" else False if files == "No" else None,
                    reported_by_site=True,
                ),
            )
    return list(out.values())


def map_survey_site(site: FeasibilitySite, row: Row) -> SiteRecord:
    equipment: list[Equipment] = []
    validations: list[Validation] = []
    for kind, prefixes in _SECTIONS.items():
        cols = _columns(row, prefixes)
        found = _validations(row, kind, cols)
        manufacturer = _real(_first(row, cols, "manufacturer", exclude=("preset",)))
        model = _real(_first(row, cols, "model"))
        has = kind in _HAS and yes_no(row.get(_HAS[kind])) == "Yes"
        if not (found or manufacturer or model or has):
            continue
        validations += found
        equipment.append(
            Equipment(
                kind=kind,
                manufacturer=manufacturer,
                model=model,
                installed=a_date(_first(row, cols, "installation")),
                last_calibration=a_date(_first(row, cols, "last calibration")),
                maintenance=_real(_first(row, cols, "maintenance")),
            )
        )

    phantom = _real(row.get("phantom availability"))
    qa = QaQc(
        phantoms=[phantom] if phantom else [],
        used_for_study_scans=yes_no(row.get("used for study specific scans")),
        records_access=yes_no(row.get("access to qa/qc records")),
        monthly_submission=yes_no(row.get("monthly basis")),
        daily_qc_storage=text(row.get("record/store your daily qc")),
        routines={k: v for k, w in _ROUTINES.items() if (v := _real(row.get(w)))},
    )
    methods = []
    for i, name in enumerate(row.headers.names):
        if name.startswith("alternative data transfer:") and yes_no(row.at(i)) == "Yes":
            label = name.split(":", 1)[1].strip()
            methods.append(_TRANSFER_LABELS.get(label, label))
    transfer = ImageTransfer(
        pacs=_real(row.get("pacs system")),
        dicom_export=yes_no(row.get("export reconstructed images in a dicom")),
        methods=methods,
    )
    radiopharmacy = site.equipment.get("Radiopharmacy / hot lab")
    return SiteRecord(
        id=site.id,
        name=site.name,
        department=site.department,
        city=site.city,
        state=site.state,
        lat=site.lat,
        lon=site.lon,
        last_survey=site.last_survey,
        artnet_accreditation=site.admin.artnet,
        physicist=None,  # the Contacts sheet is never read
        radiopharmacy=True if radiopharmacy == "Yes" else False if radiopharmacy == "No" else None,
        licensed=site.ip.licensed,
        equipment=equipment,
        validations=validations,
        scans=[],
        qa=qa,
        transfer=transfer,
        source_url=site.source_url,
    )


def read_survey_sites(content: bytes, source_url: str | None = None) -> list[SiteRecord]:
    raw, _ = load_sheets(content)
    return [map_survey_site(site, row) for site, row in latest_surveys(raw, source_url).latest]


class SurveySiteSource:
    """Site validation from the tracker's survey answers; re-read only when a new copy is downloaded."""

    def __init__(self, download: TrackerDownload) -> None:
        self._download = download
        self._read_for: datetime | None = None
        self._sites: list[SiteRecord] = []

    def info(self) -> SiteSourceInfo:
        return SiteSourceInfo(mode="survey", reason=REASON, fetched_at=self._download.fetched_at)

    async def list_sites(self, *, force_refresh: bool = False) -> list[SiteRecord]:
        file = await self._download.get(force_refresh=force_refresh)
        if file.fetched_at != self._read_for:
            self._sites, self._read_for = read_survey_sites(file.content, file.web_url), file.fetched_at
        return self._sites
