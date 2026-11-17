"""Demo sites, shown (and labelled as demo data) until the site validation lists are connected.

Fictional sites placed in real Australian cities; no real site, person or result. Dates move with today
so the page always shows something in date, due soon and overdue. Manufacturers and phantoms come from
the tracker's pick lists.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.studies.clock import today as app_today

from .models import (
    Equipment,
    EquipmentKind,
    ImageTransfer,
    PhantomScan,
    QaQc,
    ScanStatus,
    SiteRecord,
    SiteSourceInfo,
    Validation,
)

PET, SPECT, DC, GC = (
    EquipmentKind.PET_CT,
    EquipmentKind.SPECT_CT,
    EquipmentKind.DOSE_CALIBRATOR,
    EquipmentKind.GAMMA_COUNTER,
)
NEMA, INSERT = "NEMA IEC Body Phantom", "ARTnet long half-life radionuclide insert"
UNIFORMITY, WATER = "Uniformity phantom", "Water phantom"

# (id, city, state, lat, lon, ARTnet, physicist, licensed, equipment {kind: manufacturer}, phantoms)
_SITES = [
    ("101", "Sydney", "NSW", -33.87, 151.21, "Yes (64Cu, 68Ga)", "A", ["64Cu", "68Ga", "177Lu"],
     {PET: "Siemens", SPECT: "GE", DC: "Capintec", GC: "Hidex"}, [NEMA, INSERT]),
    ("102", "Newcastle", "NSW", -32.93, 151.78, "Yes (225Ac)", "B", ["225Ac", "177Lu"],
     {SPECT: "Siemens", DC: "Comecer"}, [UNIFORMITY]),
    ("103", "Melbourne", "VIC", -37.81, 144.96, "Yes (90Y, 225Ac)", "C", ["64Cu", "90Y", "177Lu", "225Ac"],
     {PET: "GE", SPECT: "GE", DC: "Capintec", GC: "PerkinElmer"}, [NEMA, INSERT]),
    ("104", "Geelong", "VIC", -38.15, 144.36, "Yes (64Cu)", "C", ["64Cu"],
     {PET: "Philips", DC: "Biodex"}, []),
    ("105", "Brisbane", "QLD", -27.47, 153.03, "Yes (64Cu, 225Ac)", "D", ["64Cu", "225Ac"],
     {PET: "Siemens", SPECT: "Siemens", DC: "Capintec", GC: "Berthold"}, [NEMA, INSERT]),
    ("106", "Townsville", "QLD", -19.26, 146.82, "Yes (225Ac)", "E", ["177Lu", "225Ac"],
     {SPECT: "GE", DC: "Capintec"}, [WATER]),
    ("107", "Adelaide", "SA", -34.93, 138.60, "Yes (64Cu, 90Y)", "F", ["64Cu", "90Y"],
     {PET: "Siemens", SPECT: "Siemens", DC: "Comecer", GC: "Hidex"}, [NEMA]),
    ("108", "Perth", "WA", -31.95, 115.86, "Yes (64Cu, 90Y)", "G", ["64Cu", "90Y"],
     {PET: "GE", SPECT: "GE", DC: "Capintec", GC: "Mirion"}, [NEMA, INSERT]),
    ("109", "Hobart", "TAS", -42.88, 147.33, "Intending", "H", ["225Ac"],
     {SPECT: "Siemens", DC: "Capintec"}, []),
    ("110", "Canberra", "ACT", -35.28, 149.13, "Intending", "A", ["64Cu"],
     {PET: "Siemens", DC: "Biodex"}, [UNIFORMITY]),
    ("111", "Darwin", "NT", -12.46, 130.84, "No", None, [],
     {SPECT: "GE", DC: "Capintec"}, []),
    ("112", "Gold Coast", "QLD", -28.02, 153.40, "Yes (64Cu)", "D", ["64Cu"],
     {PET: "Philips", DC: "Capintec"}, [NEMA]),
]  # fmt: skip

# (site, equipment, isotope, by, validated days ago, files available)
_VALIDATIONS = [
    ("101", PET, "64Cu", "ARTnet", 250, True), ("101", PET, "68Ga", "ARTnet", 250, True),
    ("101", DC, "64Cu", "ARTnet", 249, True), ("101", GC, "64Cu", "Core lab", 332, True),
    ("101", SPECT, "177Lu", "ARTnet", 165, True),
    ("102", SPECT, "225Ac", "ARTnet", 288, True), ("102", DC, "225Ac", "ARTnet", 287, False),
    ("103", PET, "90Y", "ARTnet", 377, True), ("103", PET, "64Cu", "ARTnet", 189, True),
    ("103", SPECT, "225Ac", "ARTnet", 169, True), ("103", SPECT, "177Lu", "ARTnet", 169, True),
    ("103", DC, "225Ac", "ARTnet", 168, True), ("103", GC, "225Ac", "Core lab", 313, True),
    ("104", PET, "64Cu", "Core lab", 307, True),
    ("105", PET, "64Cu", "ARTnet", 181, True), ("105", GC, "64Cu", "ARTnet", 180, True),
    ("105", GC, "225Ac", "ARTnet", 180, True), ("105", SPECT, "225Ac", "ARTnet", 179, True),
    ("106", SPECT, "225Ac", "ARTnet", 98, True), ("106", SPECT, "177Lu", "ARTnet", 98, True),
    ("107", PET, "64Cu", "ARTnet", 229, True), ("107", GC, "90Y", "ARTnet", 228, True),
    ("108", PET, "64Cu", "ARTnet", 63, True), ("108", SPECT, "90Y", "ARTnet", 62, True),
    ("108", DC, "64Cu", "ARTnet", 63, True),
    ("112", PET, "64Cu", "ARTnet", 133, True), ("112", DC, "64Cu", "ARTnet", 133, True),
]  # fmt: skip

# (site, study, equipment, isotope, status, days from today)
_SCANS = [
    ("109", "DEMO-RD-110", SPECT, "225Ac", ScanStatus.BOOKED, 21),
    ("110", "DEMO-ONC-301", PET, "64Cu", ScanStatus.BOOKED, 16),
    ("104", "DEMO-ONC-301", PET, "64Cu", ScanStatus.SUBMITTED, -15),
    ("103", "DEMO-ONC-301", PET, "90Y", ScanStatus.SCANNED, -7),
    ("102", "DEMO-RD-110", SPECT, "177Lu", ScanStatus.FAILED, -20),
    ("101", "DEMO-ONC-301", PET, "64Cu", ScanStatus.PASSED, -256),
    ("105", "DEMO-RD-110", SPECT, "225Ac", ScanStatus.PASSED, -186),
]

_MODEL = {PET: "PET/CT (demo model)", SPECT: "SPECT/CT (demo model)", DC: "Dose calibrator (demo model)",
          GC: "Gamma counter (demo model)"}  # fmt: skip
_ROUTINE = {PET: "Daily QC · monthly SUV check", SPECT: "Daily uniformity · monthly centre of rotation"}
# CT and MRI routines (the tracker asks for both, whatever the site's nuclear medicine equipment).
_ROUTINE_OTHER = {"CT": "Daily warm-up and air calibration", "MRI": "Under vendor service contract"}


class DemoSiteSource:
    def __init__(self, reason: str, today: date | None = None) -> None:
        self._reason = reason
        self._today = today

    def info(self) -> SiteSourceInfo:
        return SiteSourceInfo(mode="demo", reason=self._reason, fetched_at=None)

    async def list_sites(self, *, force_refresh: bool = False) -> list[SiteRecord]:
        t = self._today or app_today()
        out: list[SiteRecord] = []
        for sid, city, state, lat, lon, artnet, phys, licensed, kit, phantoms in _SITES:
            has_phantom = bool(phantoms)
            out.append(
                SiteRecord(
                    id=f"demo-{sid}",
                    name=f"Demo Site {sid}",
                    department="Nuclear medicine",
                    city=city,
                    state=state,
                    lat=lat,
                    lon=lon,
                    last_survey=t - timedelta(days=97),
                    artnet_accreditation=artnet,
                    physicist=f"Physicist (demo {phys})" if phys else None,
                    radiopharmacy=has_phantom,
                    licensed=licensed,
                    equipment=[
                        Equipment(
                            kind=k,
                            manufacturer=m,
                            model=_MODEL[k],
                            installed=date(t.year - 6, 3, 1),
                            last_calibration=t - timedelta(days=40),
                            maintenance="Quarterly",
                            replacement="Planned next year" if sid == "103" and k == PET else None,
                        )
                        for k, m in kit.items()
                    ],
                    validations=[
                        Validation(
                            equipment=e,
                            isotope=i,
                            validated_by=by,
                            validated_on=t - timedelta(days=ago),
                            files_available=files,
                        )
                        for s, e, i, by, ago, files in _VALIDATIONS
                        if s == sid
                    ],
                    scans=[
                        PhantomScan(study=st, equipment=e, isotope=i, status=status, on=t + timedelta(days=d))
                        for s, st, e, i, status, d in _SCANS
                        if s == sid
                    ],
                    qa=QaQc(
                        phantoms=phantoms,
                        used_for_study_scans="Yes" if has_phantom else "No",
                        records_access="Yes" if has_phantom else "Not known",
                        monthly_submission="Yes" if has_phantom else "Not known",
                        daily_qc_storage="Internal server" if has_phantom else "Paper log",
                        routines={**{k.value: r for k, r in _ROUTINE.items() if k in kit}, **_ROUTINE_OTHER},
                    ),
                    transfer=ImageTransfer(
                        pacs="Demo PACS",
                        dicom_export="Yes",
                        methods=["sFTP", "Web (https)"] if has_phantom else ["Web (https)"],
                    ),
                )
            )
        return out
