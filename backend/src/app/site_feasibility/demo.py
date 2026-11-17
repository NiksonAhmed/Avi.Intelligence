"""Demo feasibility answers, shown (and labelled as demo data) until the tracker is connected.

The same fictional "Demo Site" names and cities as Site validation, so the two pages link up; no real site,
person or answer. Survey dates move with today so some surveys are always over 12 months old.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.site_validation.demo import _SITES as VALIDATION_SITES
from app.studies.clock import today as app_today

from .models import (
    EQUIPMENT_CHECKLIST,
    INDICATIONS,
    SCORES,
    Administrative,
    Experience,
    FeasibilitySite,
    FeasibilitySourceInfo,
    IpReadiness,
    Performance,
    Project,
    Timelines,
    TrialCounts,
)

Y, N, NK = "Yes", "No", "Not known"

# id: (sector, accepting, recommend diagnostics, recommend therapeutics, survey days ago,
#      start-up, SIV and FPI weeks, HREC weeks, contract weeks, audited, remote monitoring,
#      indications with trial experience)
_PROFILE: dict[str, tuple[Any, ...]] = {
    "101": ("Public", Y, Y, Y, 120, 12, 14, 18, 8, 10, Y, Y,
            ["Breast cancer", "Prostate cancer", "Melanoma"]),
    "102": ("Public", Y, Y, Y, 210, 14, 16, 22, 10, 12, Y, Y, ["Prostate cancer", "Pancreatic cancer"]),
    "103": ("Public", Y, Y, Y, 90, 10, 12, 16, 6, 8, Y, Y, ["Breast cancer", "Prostate cancer",
            "Non-small-cell lung cancer (NSCLC)", "Colorectal cancer", "Myelofibrosis"]),
    "104": ("Private", Y, Y, N, 300, 8, 10, 14, 4, 6, N, Y, ["Prostate cancer"]),
    "105": ("Public", Y, Y, Y, 150, 12, 13, 20, 8, 9, Y, Y, ["Breast cancer", "Gastric cancer",
            "Head and neck squamous cell carcinoma (HNSCC)"]),
    "106": ("Public", Y, N, Y, 420, 18, 20, 28, 12, 16, Y, N, ["Prostate cancer"]),
    "107": ("Public", Y, Y, Y, 60, 11, 12, 17, 7, 9, Y, Y, ["Colorectal cancer", "Pancreatic cancer"]),
    "108": ("Private", Y, Y, Y, 45, 9, 10, 15, 5, 7, Y, Y, ["Breast cancer", "Melanoma",
            "Small-cell lung cancer (SCLC)"]),
    "109": ("Public", N, None, None, 500, None, None, None, 14, None, None, NK, []),
    "110": ("Public", Y, Y, None, 380, 16, 18, 26, 9, 14, N, N, ["Essential thrombocytopenia"]),
    "111": ("Public", Y, N, N, 200, 20, 24, 32, 16, 20, N, N, []),
    "112": ("Private", Y, Y, N, 30, 8, 9, 13, 4, 5, Y, Y,
            ["Prostate cancer", "Oral squamous cell carcinoma (OSCC)"]),
}  # fmt: skip

# Sites that have run a study for us:
# (protocol, indication, expected min, expected max, actual enrolment, scores in SCORES order)
_PERFORMANCE: dict[str, tuple[Any, ...]] = {
    "101": ("DEMO-ONC-301", "Breast cancer", 6, 10, 9, [3, 2, 4, 4, 5, 4, 4, 5, 4]),
    "103": ("DEMO-ONC-301", "Prostate cancer", 8, 12, 12, [3, 2, 5, 5, 5, 5, 4, 5, 5]),
    "105": ("DEMO-RD-110", "Gastric cancer", 4, 8, 3, [2, 1, 3, 2, 4, 3, 3, 4, 3]),
    "107": ("DEMO-CV-201", "Colorectal cancer", 5, 8, 6, [3, 2, 4, 4, 4, 4, 5, 4, 4]),
    "102": ("DEMO-RD-110", "Pancreatic cancer", 3, 6, 1, [1, 1, 2, 1, 3, 2, 2, 2, 3]),
}

# Equipment items a site does not have (everything else on the checklist is "Yes").
_NO_EQUIPMENT: dict[str, set[str]] = {
    "102": {"Liquid nitrogen for sample storage", "Gamma counter"},
    "104": {"SPECT/CT or PET/CT scanner", "Biosafety cabinet", "Gamma counter"},
    "106": {"Gamma counter", "Pharmacokinetic (PK) sampling", "Liquid nitrogen for sample storage"},
    "109": {"Gamma counter", "Laboratory", "Pharmacokinetic (PK) sampling"},
    "110": {"Radiopharmacy / hot lab", "Gamma counter"},
    "111": {"Radiopharmacy / hot lab", "Gamma counter", "Biosafety cabinet",
            "Liquid nitrogen for sample storage", "Pharmacokinetic (PK) sampling"},
    "112": {"Gamma counter", "Liquid nitrogen for sample storage"},
}  # fmt: skip


def _performance(perf: tuple[Any, ...] | None) -> Performance | None:
    if perf is None:
        return None
    protocol, indication, low, high, actual, scores = perf
    return Performance(
        projects=[
            Project(
                protocol=protocol, indication=indication, expected_min=low, expected_max=high, actual=actual
            )
        ],
        scores=dict(zip(SCORES, scores, strict=True)),
        competing_trials="No" if actual >= low else "Yes: a competing sponsor study opened at the site",
    )


class DemoFeasibilitySource:
    def __init__(self, reason: str, today: date | None = None) -> None:
        self._reason = reason
        self._today = today

    def info(self) -> FeasibilitySourceInfo:
        return FeasibilitySourceInfo(mode="demo", reason=self._reason, fetched_at=None)

    async def list_sites(self, *, force_refresh: bool = False) -> list[FeasibilitySite]:
        t = self._today or app_today()
        out: list[FeasibilitySite] = []
        for sid, city, state, lat, lon, artnet, _phys, licensed, _kit, _phantoms in VALIDATION_SITES:
            (sector, accepting, diag, ther, ago, start, siv, fpi, hrec, contract, audited, remote, inds) = (
                _PROFILE[sid]
            )
            sparse = sid in ("109", "111")  # surveys only partly answered
            perf = _PERFORMANCE.get(sid)
            out.append(
                FeasibilitySite(
                    id=f"demo-{sid}",
                    name=f"Demo Site {sid}",
                    department="Nuclear medicine",
                    city=city,
                    state=state,
                    lat=lat,
                    lon=lon,
                    sector=sector,
                    last_survey=t - timedelta(days=ago),
                    last_survey_study="DEMO-ONC-301" if int(sid) % 2 else "DEMO-RD-110",
                    survey_type="Site feasibility survey",
                    accepting=accepting,
                    withdrawal="PI on extended leave; department not taking new trials this year"
                    if sid == "109"
                    else None,
                    recommend_diagnostics=diag,
                    recommend_therapeutics=ther,
                    timelines=Timelines(startup_weeks=start, siv_weeks=siv, fpi_weeks=fpi),
                    experience=Experience(
                        imaging_trials=None if sparse else (Y if inds else N),
                        therapeutic_trials=None if sparse else (Y if ther == Y else N),
                        isotopes=[] if sparse else licensed,
                        patient_identification=None
                        if sparse
                        else "Multidisciplinary team meetings and clinic lists",
                        by_indication=[
                            TrialCounts(
                                indication=i,
                                experience=Y if i in inds else (None if sparse else N),
                                imaging=(2 + len(i) % 4) if i in inds else (None if sparse else 0),
                                therapeutic=(1 + len(i) % 3)
                                if i in inds and ther == Y
                                else (None if sparse else 0),
                            )
                            for i in INDICATIONS
                        ],
                        active_imaging_trials=None if sparse else len(inds),
                    ),
                    ip=IpReadiness(
                        licensed=licensed,
                        trained=licensed if not sparse else [],
                        handled=licensed[:2],
                        treatment_days=None if sparse else "Monday to Thursday, 8 am to 3 pm",
                        fridges=None if sparse else 1,
                        freezers_20=None if sparse else 1,
                        freezers_80=None if sparse else (1 if sector == "Public" else 0),
                    ),
                    equipment={
                        item: (
                            None
                            if sparse and k % 3 == 0
                            else (N if item in _NO_EQUIPMENT.get(sid, ()) else Y)
                        )
                        for k, item in enumerate(EQUIPMENT_CHECKLIST)
                    },
                    admin=Administrative(
                        audited=audited,
                        auditor="Sponsor" if audited == Y else None,
                        major_findings=N if audited == Y else None,
                        sops=None if sparse else Y,
                        radiation_licence=None if sparse else "Current; copy on file",
                        central_hrec=None if sparse else (Y if sector == "Public" else N),
                        hrec_weeks=hrec,
                        additional_approvals=None if sparse else "Research governance (RGO)",
                        contract_during_hrec=None if sparse else Y,
                        contract_weeks=contract,
                        artnet=artnet,
                        remote_monitoring=remote,
                        remote_records="Source documents and EMR read-only" if remote == Y else None,
                    ),
                    performance=_performance(perf),
                )
            )
        return out
