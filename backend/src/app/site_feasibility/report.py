"""Site feasibility figures: pure calculations over the site list (no estimates, no AI).

Rules (shown on the page behind the ⓘ):
- Recommendation: as recorded in the tracker ("Recommend for Diagnostics?" / "Recommend for Therapeutics?").
- Survey due: the last survey was returned more than 12 months ago.
- Survey answered: the share of the tracked questions that have an answer.
- Performance score: the Overall Site Assessment, the sum of its criteria (maximum 40).
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from statistics import median

from pydantic import BaseModel

from app.reports.study_delivery import Tile

from .models import (
    INDICATIONS,
    SCORE_MAX,
    SCORES,
    Administrative,
    Experience,
    FeasibilitySite,
    IpReadiness,
    Performance,
    Timelines,
)

SURVEY_MONTHS = 12
ISOTOPES = ["64Cu", "68Ga", "90Y", "177Lu", "225Ac"]

RULES = {
    "source": "Site Feasibility Tracker: Feasibility and Post-Activation sheets (read-only copy).",
    "recommendation": "Recommendation as recorded in the tracker: recommended for diagnostics (imaging) "
    "and/or therapeutics studies. Not assessed: neither question answered.",
    "survey": f"Survey due: the last survey was returned more than {SURVEY_MONTHS} months ago.",
    "answered": "Survey answered: the share of the tracked questions (site details, timelines, experience, "
    "IP, equipment and administrative) that have an answer.",
    "score": "Performance score: the Overall Site Assessment after a study, the sum of its "
    f"{len(SCORES)} criteria (maximum {SCORE_MAX}).",
}


class Recommendation(StrEnum):
    BOTH = "both"
    THERAPEUTICS = "therapeutics"
    DIAGNOSTICS = "diagnostics"
    NOT_RECOMMENDED = "not_recommended"
    NOT_ASSESSED = "not_assessed"


LABEL = {
    Recommendation.BOTH: "Diagnostics and therapeutics",
    Recommendation.THERAPEUTICS: "Therapeutics only",
    Recommendation.DIAGNOSTICS: "Diagnostics only",
    Recommendation.NOT_RECOMMENDED: "Not recommended",
    Recommendation.NOT_ASSESSED: "Not assessed",
}


def _unanswered(answer: str | None) -> bool:
    """Blank, or "Not known" / "Unknown" / "TBC" in the tracker."""
    return answer is None or answer.strip().lower().startswith(
        ("not known", "unknown", "tbc", "to be confirmed")
    )


def recommendation_of(site: FeasibilitySite) -> Recommendation:
    d, t = site.recommend_diagnostics, site.recommend_therapeutics
    if _unanswered(d) and _unanswered(t):
        return Recommendation.NOT_ASSESSED
    if d == "Yes" and t == "Yes":
        return Recommendation.BOTH
    if t == "Yes":
        return Recommendation.THERAPEUTICS
    if d == "Yes":
        return Recommendation.DIAGNOSTICS
    return Recommendation.NOT_RECOMMENDED


def _months_ago(d: date, today: date) -> int:
    return (today.year - d.year) * 12 + today.month - d.month - (today.day < d.day)


def survey_due(site: FeasibilitySite, today: date) -> bool:
    return site.last_survey is None or _months_ago(site.last_survey, today) >= SURVEY_MONTHS


def _answers(site: FeasibilitySite) -> list[object]:
    """Every tracked answer (None when not answered)."""
    t: Timelines = site.timelines
    e: Experience = site.experience
    ip: IpReadiness = site.ip
    a: Administrative = site.admin
    details = [
        site.sector,
        site.last_survey,
        site.accepting,
        site.recommend_diagnostics,
        site.recommend_therapeutics,
    ]
    timeline = [t.startup_weeks, t.siv_weeks, t.fpi_weeks]
    experience = [
        e.imaging_trials,
        e.therapeutic_trials,
        e.patient_identification,
        e.active_imaging_trials,
        *[c.experience for c in e.by_indication],
    ]
    ip_answers = [ip.treatment_days, ip.fridges, ip.freezers_20, ip.freezers_80]
    admin = [
        a.audited,
        a.sops,
        a.radiation_licence,
        a.central_hrec,
        a.hrec_weeks,
        a.additional_approvals,
        a.contract_during_hrec,
        a.contract_weeks,
        a.artnet,
        a.remote_monitoring,
    ]
    return [*details, *timeline, *experience, *ip_answers, *site.equipment.values(), *admin]


def answered(site: FeasibilitySite) -> int:
    """Percentage of the tracked questions answered."""
    answers = _answers(site)
    return round(100 * sum(a is not None for a in answers) / len(answers)) if answers else 0


def score_of(perf: Performance | None) -> int | None:
    if perf is None or not perf.scores:
        return None
    return sum(perf.scores.values())


def _short(site: FeasibilitySite) -> str:
    return {
        Recommendation.BOTH: "Diag · Ther",
        Recommendation.THERAPEUTICS: "Ther",
        Recommendation.DIAGNOSTICS: "Diag",
        Recommendation.NOT_RECOMMENDED: "Not recommended",
        Recommendation.NOT_ASSESSED: "Not assessed",
    }[recommendation_of(site)]


class FeasibilityPin(BaseModel):
    id: str
    name: str
    city: str
    state: str
    lat: float
    lon: float
    recommendation: Recommendation
    short: str
    """Under the city on the map, e.g. "Diag · Ther"."""
    accepting: str | None
    survey_due: bool
    hrec_weeks: float | None


class FeasibilityRow(BaseModel):
    site_id: str
    site: str
    city: str
    state: str
    sector: str | None
    accepting: str | None
    recommendation: Recommendation
    licensed: list[str]
    hrec_weeks: float | None
    contract_weeks: float | None
    startup_weeks: float | None
    last_survey: date | None
    survey_due: bool
    answered: int
    score: int | None


class SurveyDue(BaseModel):
    site_id: str
    site: str
    city: str
    last_survey: date | None
    months: int | None


class Fastest(BaseModel):
    site_id: str
    site: str
    city: str
    hrec_weeks: float | None
    contract_weeks: float | None
    startup_weeks: float | None


class SiteFeasibility(BaseModel):
    headline: str
    tiles: list[Tile]
    sites: list[FeasibilityPin]
    rows: list[FeasibilityRow]
    surveys_due: list[SurveyDue]
    fastest: list[Fastest]
    """Recommended sites with the shortest predicted start-up, quickest first."""
    isotope_options: list[str]
    indication_options: list[str]
    recommendation_options: list[dict[str, str]]
    rules: dict[str, str]


def _matches(
    site: FeasibilitySite, isotope: str | None, indication: str | None, rec: Recommendation | None
) -> bool:
    if isotope and isotope not in site.ip.licensed:
        return False
    if indication and not any(
        c.indication == indication and (c.experience == "Yes" or (c.imaging or 0) + (c.therapeutic or 0) > 0)
        for c in site.experience.by_indication
    ):
        return False
    return not (rec and recommendation_of(site) != rec)


def _weeks(v: float | None) -> str:
    return "—" if v is None else f"{v:g} weeks"


def build_site_feasibility(
    sites: list[FeasibilitySite],
    today: date,
    *,
    isotope: str | None = None,
    indication: str | None = None,
    recommendation: Recommendation | None = None,
) -> SiteFeasibility:
    chosen = [s for s in sites if _matches(s, isotope, indication, recommendation)]
    recs = {s.id: recommendation_of(s) for s in chosen}
    therapeutics = [s for s in chosen if recs[s.id] in (Recommendation.BOTH, Recommendation.THERAPEUTICS)]
    diagnostics = [s for s in chosen if recs[s.id] in (Recommendation.BOTH, Recommendation.DIAGNOSTICS)]
    accepting = [s for s in chosen if s.accepting == "Yes"]
    due = [s for s in chosen if survey_due(s, today)]
    hrec = [s.admin.hrec_weeks for s in chosen if s.admin.hrec_weeks is not None]
    scores = [x for s in chosen if (x := score_of(s.performance)) is not None]

    tiles = [
        Tile(
            key="sites",
            label="Sites surveyed",
            value=str(len(chosen)),
            note=f"{len(accepting)} accepting new trials",
            tone="info",
        ),
        Tile(
            key="therapeutics",
            label="Recommended: therapeutics",
            value=str(len(therapeutics)),
            note=f"of {len(chosen)} sites",
            tone="good",
        ),
        Tile(
            key="diagnostics",
            label="Recommended: diagnostics",
            value=str(len(diagnostics)),
            note=f"of {len(chosen)} sites",
            tone="good",
        ),
        Tile(
            key="hrec",
            label="Median HREC turnaround",
            value=f"{median(hrec):g} wk" if hrec else "—",
            note=f"from {len(hrec)} sites" if hrec else "No answers yet",
            tone="neutral",
        ),
        Tile(
            key="surveys_due",
            label="Surveys due",
            value=str(len(due)),
            note=f"over {SURVEY_MONTHS} months old",
            tone="warn" if due else "good",
        ),
    ]

    filters = " · ".join(
        x for x in (isotope, indication, LABEL[recommendation] if recommendation else None) if x
    )
    if not chosen:
        headline = f"No sites match {filters}." if filters else "No sites surveyed yet."
    else:
        scope = f" for {filters}" if filters else ""
        parts = [
            f"{len(chosen)} sites surveyed{scope}: {len(therapeutics)} recommended for therapeutics and "
            f"{len(diagnostics)} for diagnostics."
        ]
        not_accepting = [s for s in chosen if s.accepting == "No"]
        if not_accepting:
            parts.append(f"{', '.join(s.name for s in not_accepting)} not accepting new trials.")
        if due:
            parts.append(
                f"{len(due)} survey{'s are' if len(due) > 1 else ' is'} over {SURVEY_MONTHS} months old."
            )
        if scores:
            parts.append(
                f"{len(scores)} sites have a performance score (average {sum(scores) / len(scores):.0f} "
                f"of {SCORE_MAX})."
            )
        headline = " ".join(parts)

    rows = sorted(
        (
            FeasibilityRow(
                site_id=s.id,
                site=s.name,
                city=s.city,
                state=s.state,
                sector=s.sector,
                accepting=s.accepting,
                recommendation=recs[s.id],
                licensed=s.ip.licensed,
                hrec_weeks=s.admin.hrec_weeks,
                contract_weeks=s.admin.contract_weeks,
                startup_weeks=s.timelines.startup_weeks,
                last_survey=s.last_survey,
                survey_due=survey_due(s, today),
                answered=answered(s),
                score=score_of(s.performance),
            )
            for s in chosen
        ),
        key=lambda r: (list(Recommendation).index(r.recommendation), r.site),
    )
    surveys_due = sorted(
        (
            SurveyDue(
                site_id=s.id,
                site=s.name,
                city=s.city,
                last_survey=s.last_survey,
                months=_months_ago(s.last_survey, today) if s.last_survey else None,
            )
            for s in due
        ),
        key=lambda d: -(d.months or 10_000),
    )
    fastest = sorted(
        (
            Fastest(
                site_id=s.id,
                site=s.name,
                city=s.city,
                hrec_weeks=s.admin.hrec_weeks,
                contract_weeks=s.admin.contract_weeks,
                startup_weeks=s.timelines.startup_weeks,
            )
            for s in chosen
            if recs[s.id] != Recommendation.NOT_RECOMMENDED
            and s.accepting != "No"
            and s.timelines.startup_weeks is not None
        ),
        key=lambda f: (f.startup_weeks, f.site),
    )
    return SiteFeasibility(
        headline=headline,
        tiles=tiles,
        sites=[
            FeasibilityPin(
                id=s.id,
                name=s.name,
                city=s.city,
                state=s.state,
                lat=s.lat,
                lon=s.lon,
                recommendation=recs[s.id],
                short=_short(s),
                accepting=s.accepting,
                survey_due=survey_due(s, today),
                hrec_weeks=s.admin.hrec_weeks,
            )
            for s in chosen
        ],
        rows=rows,
        surveys_due=surveys_due,
        fastest=fastest[:6],
        isotope_options=ISOTOPES,
        indication_options=INDICATIONS,
        recommendation_options=[{"value": r.value, "label": LABEL[r]} for r in Recommendation],
        rules={**RULES, "weeks": "Turnaround and timelines in weeks, as predicted by the site."},
    )


class ScoreRow(BaseModel):
    criterion: str
    score: int | None
    max: int


class SiteFeasibilityDetail(FeasibilitySite):
    recommendation: Recommendation
    recommendation_label: str
    survey_due: bool
    answered: int
    score: int | None
    score_max: int
    score_rows: list[ScoreRow]
    validation_site_id: str | None = None
    """The same site on Site validation, when it is there (matched by name)."""


def build_site_detail(
    site: FeasibilitySite, today: date, validation_site_id: str | None
) -> SiteFeasibilityDetail:
    rec = recommendation_of(site)
    perf = site.performance
    return SiteFeasibilityDetail(
        **site.model_dump(),
        recommendation=rec,
        recommendation_label=LABEL[rec],
        survey_due=survey_due(site, today),
        answered=answered(site),
        score=score_of(perf),
        score_max=SCORE_MAX,
        score_rows=[
            ScoreRow(criterion=c, score=(perf.scores.get(c) if perf else None), max=m)
            for c, m in SCORES.items()
        ],
        validation_site_id=validation_site_id,
    )
