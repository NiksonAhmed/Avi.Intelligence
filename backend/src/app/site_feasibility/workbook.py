"""Reads the Site Feasibility Tracker workbook in SharePoint (user decision 2026-11-23).

The tracker stays an Excel file that the team keeps editing; the app downloads it read-only and reads two
sheets: **Feasibility** (one row per site survey) and **Post-Activation _ DRAFT** (one row per project at a
site). Columns are found by their header wording, not their position, so inserting a column does not break
anything. The **Validation** sheet only holds the dropdown options, and the hidden **Contacts** sheet is
never read.
"""

from __future__ import annotations

import io
import re
import time
import warnings
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

import openpyxl

from app.connectors.sharepoint.graph_client import GraphClient
from app.site_validation.geo import CITIES, locate, short_state

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

FEASIBILITY_SHEET = "Feasibility"
POST_ACTIVATION_SHEET = "Post-Activation _ DRAFT"
ISOTOPES = ["64Cu", "68Ga", "90Y", "177Lu", "225Ac"]
AUSTRALIA_MIDDLE = (-25.27, 133.78)

# Words that identify each indication in the tracker's headers (the template spells some of them its own way).
_INDICATION_WORDS: dict[str, str] = {
    "Breast cancer": "breast",
    "Prostate cancer": "prostate",
    "Non-small-cell lung cancer (NSCLC)": "nsclc",
    "Small-cell lung cancer (SCLC)": "(sclc)",
    "Colorectal cancer": "colorectal",
    "Pancreatic cancer": "pancreatic",
    "Gastric cancer": "gastric",
    "Essential thrombocytopenia": "thrombocytopenia",
    "Myelofibrosis": "myelof",  # the template has "myelofribrosis"
    "Melanoma": "melanoma",
    "Oral squamous cell carcinoma (OSCC)": "oscc",
    "Head and neck squamous cell carcinoma (HNSCC)": "hnscc",
    "Infection": "infection",
}

# Equipment checklist item -> header wording (and the section it is in).
_EQUIPMENT: dict[str, tuple[str, ...]] = {
    "ECG": ("do you have an ecg",),
    "Room temperature centrifuge": ("room temperature centrifuge",),
    "Refrigerated centrifuge": ("refrigerated centrifuge",),
    "Temperature-monitored secure storage (room temperature)": ("room temperature storage for ip storage",),
    "Temperature-monitored secure storage (2–8 °C)": ("secure fridge for sample storage",),
    "Temperature-monitored secure storage (−20 °C / −80 °C)": (
        "secure -20 freezer for sample storage",
        "secure -80 freezer for sample storage",
    ),
    "Liquid nitrogen for sample storage": ("liquid nitrogen",),
    "Biosafety cabinet": ("biosafety cabinet",),
    "CT or MRI scanner": ("ct or mri scanner",),
    "SPECT/CT or PET/CT scanner": ("spect/ct or pet/ct scanner",),
    "Gamma counter": ("do you have a gamma counter",),
    "Dose calibrator": ("dose calibrator to measure",),
    "Laboratory": ("do you have a laboratory",),
    "Radiopharmacy / hot lab": ("radiopharmacy / hot lab",),
    "Pharmacokinetic (PK) sampling": ("pharmacokinetic (pk)",),
}
assert set(_EQUIPMENT) == set(EQUIPMENT_CHECKLIST)
assert set(_INDICATION_WORDS) == set(INDICATIONS)

# Overall Site Assessment criterion -> header wording, in SCORES order.
_SCORE_WORDS: dict[str, str] = {
    "Time to RGO approval": "time to rgo approval",
    "Time to activation": "time to activation",
    "Time to FPI": "time to fpi",
    "Recruitment success": "recruitment success",
    "CRA meeting with PI": "cra meeting with pi",
    "Data entry": "data entry",
    "Query resolution": "query resolution",
    "Site issues": "site issues",
    "Protocol deviations": "protocol deviations",
}
assert list(_SCORE_WORDS) == list(SCORES)


# ---- reading cells -------------------------------------------------------------------------------


def norm(value: Any) -> str:
    """Header wording for matching: lower case, single spaces, no non-breaking spaces or '#'."""
    text = str(value or "").replace(" ", " ").replace("\xa0", " ").replace("#", " ").replace("’", "'")
    return " ".join(text.lower().split())


def text(value: Any, limit: int = 1000) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.strftime("%d %b %Y")
    out = " ".join(str(value).split())
    return out[:limit] or None


def yes_no(value: Any) -> str | None:
    """ "Yes"/"No" when the answer starts with one (the page's rules compare these); otherwise as written."""
    t = text(value)
    if t is None:
        return None
    first = re.split(r"[\s,.;:()/-]+", t.lower(), maxsplit=1)[0]
    if first in ("yes", "y"):
        return "Yes"
    if first in ("no", "n"):
        return "No"
    return t


def number(value: Any) -> float | None:
    """A number of weeks or a count. "12-14" gives 13 (the middle); words without digits give None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    found = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", str(value or ""))]
    if not found:
        return None
    return sum(found[:2]) / len(found[:2])


def count(value: Any) -> int | None:
    n = number(value)
    return None if n is None else int(round(n))


_DATE_FORMATS = ("%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%Y-%m-%d", "%d %b %Y", "%d %B %Y", "%b %Y", "%B %Y")


def a_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    t = text(value)
    if not t:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            continue
    return None


def isotopes_in(value: Any) -> list[str]:
    """Isotopes mentioned in free text ("Lu-177, 68Ga and Y90" -> 177Lu, 68Ga, 90Y)."""
    t = norm(value).replace("-", "").replace(" ", "")
    found = []
    for iso in ISOTOPES:
        digits, element = re.match(r"(\d+)(\w+)", iso).groups()  # type: ignore[union-attr]
        if digits + element.lower() in t or element.lower() + digits in t:
            found.append(iso)
    return found


# ---- headers -------------------------------------------------------------------------------------


@dataclass
class Headers:
    """Header wording and section for each column of a sheet."""

    names: list[str]
    sections: list[str]

    def find(self, *words: str, section: str | None = None, exclude: str | None = None) -> int | None:
        """First column whose header contains all the words (and is in the section when given)."""
        for i, name in enumerate(self.names):
            if section and not self.sections[i].startswith(section):
                continue
            if exclude and exclude in name:
                continue
            if all(w in name for w in words):
                return i
        return None

    def find_all(self, *words: str, section: str | None = None) -> list[int]:
        return [
            i
            for i, name in enumerate(self.names)
            if all(w in name for w in words) and (not section or self.sections[i].startswith(section))
        ]


def read_headers(rows: list[tuple[Any, ...]]) -> tuple[Headers, int]:
    """Finds the header row (the one with "Name of Site") in the first rows; returns it and its index."""
    for i, row in enumerate(rows[:10]):
        if any(norm(v) == "name of site" for v in row):
            above = rows[i - 1] if i > 0 else ()
            sections, current = [], ""
            for j in range(len(row)):
                cell = above[j] if j < len(above) else None
                if cell not in (None, ""):
                    current = norm(cell)
                sections.append(current)
            return Headers([norm(v) for v in row], sections), i
    raise ValueError("The header row (with 'Name of Site') was not found.")


# ---- one row -------------------------------------------------------------------------------------


class Row:
    def __init__(self, values: tuple[Any, ...], headers: Headers) -> None:
        self.values, self.headers = values, headers

    def at(self, index: int | None) -> Any:
        if index is None or index >= len(self.values):
            return None
        value = self.values[index]
        return None if isinstance(value, str) and not value.strip() else value

    def get(self, *words: str, section: str | None = None, exclude: str | None = None) -> Any:
        return self.at(self.headers.find(*words, section=section, exclude=exclude))

    def filled(self) -> bool:
        return self.answers() > 0

    def answers(self) -> int:
        return sum(1 for v in self.values if v is not None and str(v).strip())


def site_key(name: Any, department: Any = None) -> str:
    return f"{norm(name)}|{norm(department)}"


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:60]


def city_of(address: Any) -> str | None:
    """The best-known city named in the address (longest match wins), from the built-in city table."""
    a = norm(address)
    if not a:
        return None
    best = None
    for city in CITIES:
        if re.search(rf"(?<![a-z]){re.escape(city)}(?![a-z])", a) and (best is None or len(city) > len(best)):
            best = city
    return best.title() if best else None


def map_feasibility(row: Row) -> FeasibilitySite | None:
    name = text(row.get("name of site"))
    if not name:
        return None
    department = text(row.get("department", section="site details"))
    state_raw = text(row.get("state", section="site details"))
    city = city_of(row.get("site address"))
    lat, lon = locate(city, state_raw) or AUSTRALIA_MIDDLE
    withdrawal = text(row.get("known pi or site withdrawal"))
    withdrawal_note = text(row.get("comments on withdrawal"))
    if withdrawal_note:
        withdrawal = f"{withdrawal}: {withdrawal_note}" if withdrawal else withdrawal_note

    by_indication = []
    for indication, word in _INDICATION_WORDS.items():
        flag = next(
            (
                i
                for i in row.headers.find_all(word, section="experience")
                if "trials" not in row.headers.names[i]
            ),
            None,
        )
        flag = flag if flag is not None and "how many" not in row.headers.names[flag] else None
        imaging = row.headers.find("trials", word, "(imaging)", section="experience")
        therapeutic = row.headers.find("trials", word, "(therapeutic)", section="experience")
        by_indication.append(
            TrialCounts(
                indication=indication,
                experience=yes_no(row.at(flag)),
                imaging=count(row.at(imaging)),
                therapeutic=count(row.at(therapeutic)),
            )
        )

    def isotopes_where(*words: str) -> list[str]:
        out = []
        for iso in ISOTOPES:
            spellings = [iso.lower()] + (["117lu"] if iso == "177Lu" else [])  # the template's typo
            if any(yes_no(row.get(*words, s, section="ip")) == "Yes" for s in spellings):
                out.append(iso)
        return out

    equipment: dict[str, str | None] = {}
    for item, wordings in _EQUIPMENT.items():
        answers = [yes_no(row.get(w)) for w in wordings]
        if "Yes" in answers:
            equipment[item] = "Yes"
        elif any(a is not None for a in answers):
            equipment[item] = next(a for a in answers if a is not None)
        else:
            equipment[item] = None

    artnet = yes_no(row.get("artnet (or equivalent) accreditation"))
    artnet_detail = text(row.get("if yes, please provide details of radioisotopes"))
    if artnet == "Yes" and artnet_detail:
        artnet = f"Yes ({artnet_detail})"

    return FeasibilitySite(
        id="",  # given once all rows are read (see read_tracker)
        name=name,
        department=department,
        city=city or (short_state(state_raw) or "Location not given"),
        state=short_state(state_raw),
        lat=lat,
        lon=lon,
        sector=text(row.get("private/public")),
        last_survey=a_date(row.get("last survey return date")),
        last_survey_study=text(row.get("last study survey completed for")),
        survey_type=text(row.get("survey type")),
        accepting=yes_no(row.get("currently accepting new trials")),
        withdrawal=withdrawal,
        recommend_diagnostics=yes_no(row.get("recommend for diagnostics")),
        recommend_therapeutics=yes_no(row.get("recommend for therapeutics")),
        timelines=Timelines(
            startup_weeks=number(row.get("start-up (weeks)")),
            siv_weeks=number(row.get("siv (weeks)")),
            fpi_weeks=number(row.get("fpi (weeks)")),
        ),
        experience=Experience(
            imaging_trials=yes_no(row.get("experience in conducting imaging clinical trials")),
            therapeutic_trials=yes_no(row.get("experience in conducting therapeutic clinical trials")),
            isotopes=isotopes_in(row.get("radioisotope", section="experience")),
            patient_identification=text(row.get("primary method for identifying eligible patients")),
            by_indication=by_indication,
            active_imaging_trials=count(row.get("clinical trials (imaging) with active enrolment")),
        ),
        ip=IpReadiness(
            licensed=isotopes_where("is your site licensed for"),
            trained=isotopes_where("trained to use"),
            handled=isotopes_where("previously calibrated"),
            treatment_days=text(row.get("days/time are available for treatment")),
            fridges=count(row.get("fridge", section="ip", exclude="?")),
            freezers_20=count(row.get("-20c", section="ip", exclude="?")),
            freezers_80=count(row.get("-80c", section="ip", exclude="?")),
        ),
        equipment=equipment,
        admin=Administrative(
            audited=yes_no(row.get("undergone any clinical trial audits")),
            auditor=text(row.get("auditor")),
            major_findings=text(row.get("major findings")),
            sops=yes_no(row.get("sop's for clinical trials")),
            radiation_licence=text(row.get("radiation safety licen")),
            central_hrec=yes_no(row.get("central/private hrec")),
            hrec_weeks=number(row.get("hrec tat (weeks)")),
            additional_approvals=text(row.get("additional approvals (e.g", exclude="requirements")),
            contract_during_hrec=yes_no(row.get("contract and budget negotiation during hrec")),
            contract_weeks=number(row.get("tat draft contract/budget")),
            artnet=artnet,
            remote_monitoring=yes_no(row.get("remote monitoring")),
            remote_records=text(row.get("which records can be acc")),
        ),
    )


@dataclass
class _ProjectRow:
    key: str
    name_key: str
    project: Project | None
    scores: dict[str, int]
    competing: str | None
    comments: str | None


def map_post_activation(row: Row) -> _ProjectRow | None:
    name = row.get("name of site")
    if not text(name):
        return None
    department = row.get("department", section="site details")
    protocol = text(row.get("protocol", section="projects"))
    actual = [count(row.at(i)) for i in row.headers.find_all("what was the actual enrolment")]
    actual_known = [a for a in actual if a is not None]
    project = (
        Project(
            protocol=protocol,
            indication=text(row.get("indication", section="projects")),
            expected_min=count(row.get("expected minimum enrolment")),
            expected_max=count(row.get("expected maximum enrolment")),
            actual=sum(actual_known) if actual_known else None,
        )
        if protocol
        else None
    )
    scores: dict[str, int] = {}
    for criterion, words in _SCORE_WORDS.items():
        score = count(row.get(words, section="overall site assessment"))
        if score is not None:
            scores[criterion] = max(0, min(score, SCORES[criterion]))
    return _ProjectRow(
        key=site_key(name, department),
        name_key=norm(name),
        project=project,
        scores=scores,
        competing=yes_no(row.get("directly competing trials")),
        comments=text(row.get("comments", section="overall site assessment")),
    )


# ---- the whole workbook --------------------------------------------------------------------------


@dataclass
class TrackerResult:
    sites: list[FeasibilitySite]
    skipped: dict[str, int] = field(default_factory=dict)


def _rows(ws: Any) -> list[tuple[Any, ...]]:
    return [tuple(r) for r in ws.iter_rows(values_only=True)]


def read_tracker(content: bytes, *, source_url: str | None = None) -> TrackerResult:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # openpyxl warns about Excel features it does not read
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        try:
            raw = _rows(wb[FEASIBILITY_SHEET])
            post = _rows(wb[POST_ACTIVATION_SHEET]) if POST_ACTIVATION_SHEET in wb.sheetnames else []
        finally:
            wb.close()

    headers, at = read_headers(raw)
    rows = [Row(v, headers) for v in raw[at + 1 :]]
    rows = [r for r in rows if r.filled()]
    mapped = [map_feasibility(r) for r in rows]
    nameless = sum(1 for r, m in zip(rows, mapped, strict=True) if m is None and r.answers() >= 5)

    # One site (name + department) can have several surveys: keep the latest.
    latest: dict[str, FeasibilitySite] = {}
    for site in (s for s in mapped if s is not None):
        key = site_key(site.name, site.department)
        held = latest.get(key)
        if held is None or (site.last_survey or date.min) >= (held.last_survey or date.min):
            latest[key] = site

    used: set[str] = set()
    sites: list[FeasibilitySite] = []
    for site in latest.values():
        base = "tr-" + (_slug(f"{site.name} {site.department or ''}") or "site")
        sid, n = base, 2
        while sid in used:
            sid, n = f"{base}-{n}", n + 1
        used.add(sid)
        sites.append(site.model_copy(update={"id": sid, "source_url": source_url}))

    unmatched = 0
    if post:
        p_headers, p_at = read_headers(post)
        by_key = {site_key(s.name, s.department): s for s in sites}
        by_name: dict[str, list[FeasibilitySite]] = {}
        for s in sites:
            by_name.setdefault(norm(s.name), []).append(s)
        for values in post[p_at + 1 :]:
            prow = Row(values, p_headers)
            if not prow.filled():
                continue
            pr = map_post_activation(prow)
            if pr is None:
                continue
            same_name = by_name.get(pr.name_key, [])
            match = by_key.get(pr.key) or (same_name[0] if len(same_name) == 1 else None)
            if match is None:
                unmatched += 1
                continue
            perf = match.performance or Performance()
            if pr.project:
                perf.projects.append(pr.project)
            if pr.scores:
                perf.scores = pr.scores  # the latest assessed project (lower rows are newer)
            perf.competing_trials = pr.competing or perf.competing_trials
            perf.comments = pr.comments or perf.comments
            match.performance = perf

    return TrackerResult(
        sites=sites,
        skipped={
            "rows_without_a_site_name": nameless,
            "older_surveys_of_the_same_site": sum(1 for s in mapped if s is not None) - len(sites),
            "post_activation_rows_not_matched": unmatched,
        },
    )


# ---- the source ----------------------------------------------------------------------------------


class WorkbookFeasibilitySource:
    """Downloads the tracker from SharePoint (read-only) and keeps the result for a few minutes."""

    def __init__(
        self,
        client: GraphClient,
        *,
        drive_id: str,
        item_id: str,
        cache_seconds: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client, self._drive_id, self._item_id = client, drive_id, item_id
        self._cache_seconds, self._clock = cache_seconds, clock
        self._cache: list[FeasibilitySite] | None = None
        self._expires = 0.0
        self._fetched_at: datetime | None = None
        self.skipped: dict[str, int] = {}

    def info(self) -> FeasibilitySourceInfo:
        return FeasibilitySourceInfo(mode="sharepoint", fetched_at=self._fetched_at)

    async def list_sites(self, *, force_refresh: bool = False) -> list[FeasibilitySite]:
        if self._cache is not None and not force_refresh and self._clock() < self._expires:
            return self._cache
        item_path = f"/drives/{self._drive_id}/items/{self._item_id}"
        item = await self._client.get(f"{item_path}?$select=name,webUrl,lastModifiedDateTime")
        url = await self._client.download_url(f"{item_path}/content")
        content = b"".join([chunk async for chunk in self._client.stream_url(url)])
        result = read_tracker(content, source_url=item.get("webUrl"))
        self.skipped = result.skipped
        self._cache, self._expires = result.sites, self._clock() + self._cache_seconds
        self._fetched_at = datetime.now(UTC)
        return result.sites
