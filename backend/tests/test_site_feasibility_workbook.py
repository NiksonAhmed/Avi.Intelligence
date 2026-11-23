"""Site feasibility from the tracker workbook (user decision 2026-11-23). The workbook here is made up: the
tracker's header wording with invented sites. Tests never read the real tracker or call SharePoint."""

from __future__ import annotations

import asyncio
import io
import random
from collections.abc import AsyncIterator
from datetime import date, datetime
from typing import Any

import openpyxl
import pytest

from app.core.config import Settings
from app.site_feasibility.demo import DemoFeasibilitySource
from app.site_feasibility.models import FeasibilitySite
from app.site_feasibility.report import Recommendation, build_site_feasibility, recommendation_of
from app.site_feasibility.source import build_feasibility_source
from app.site_feasibility.workbook import (
    WorkbookFeasibilitySource,
    a_date,
    city_of,
    isotopes_in,
    number,
    read_tracker,
    yes_no,
)

TODAY = date(2026, 11, 23)

# (section, header) as the tracker words them, including its spelling.
FEAS_HEADERS: list[tuple[str, str]] = [
    ("Site Details", "Country"),
    ("Site Details", "State"),
    ("Site Details", "Name of Site"),
    ("Site Details", "Department"),
    ("Site Details", "Site Address"),
    ("Site Details", "Last Survey Return Date"),
    ("Site Details", "Last Study Survey Completed for"),
    ("Site Details", "Private/Public"),
    ("Site Details", "Survey Type"),
    (
        "Site Details",
        "Is site/department currently accepting new trials? If no, when are site expected to reopen",
    ),
    ("Site Details", "Known PI or Site withdrawal from trial?"),
    ("Site Details", "Comments on Withdrawal"),
    ("Site Details", "Recommend for Diagnostics?"),
    ("Site Details", "Recommend for Therapeutics?"),
    ("Predicted Timelines", "Start-up (weeks)"),
    ("Predicted Timelines", "SIV (weeks)"),
    ("Predicted Timelines", "FPI (weeks)"),
    ("Experience", "Radioisotope"),
    ("Experience", "Experience in conducting imaging clinical trials?"),
    ("Experience", "Experience in conducting therapeutic clinical trials?"),
    ("Experience", "Primary method for identifying eligible patients?"),
    ("Experience", "Breast Cancer"),
    ("Experience", "# Trials Breast Cancer (imaging)"),
    ("Experience", "# Trials Breast Cancer (therapeutic)"),
    ("Experience", "Myelofibrosis"),
    ("Experience", "# trials myelofribrosis (therapeutic)"),
    ("Experience", "# clinical trials (imaging) with active enrolment (PI)"),
    ("Experience", "How many Breast Cancer patients are currently actively receiving care at your facility?"),
    ("IP", "Is your site licensed for 64Cu?"),
    ("IP", "Is your site licensed for 177Lu?"),
    ("IP", "Are your site personnel trained to use 117Lu based drug products? 4"),
    ("IP", "Have your site previously calibrated, drawn up a specific dose, and administered an 90Y based"),
    ("IP", "What days/time are available for treatment administrations?"),
    ("IP", "Radioactive refrigerator (4 degrees)?"),
    ("IP", "#fridge"),
    ("IP", "#-20C"),
    ("IP", "Do you have a secure temperature monitored room temperature storage for IP storage?"),
    ("Equipment", "Do you have an ECG?"),
    ("Equipment", "Do you have an temperature monitored, secure -20 freezer for sample storage?"),
    ("Equipment", "Do you have an temperature monitored, secure -80 freezer for sample storage?"),
    ("Equipment", "Do you have a Gamma Counter?"),
    ("Administrative", "Has your site undergone any clinical trial audits and/or regulatory inspections?"),
    ("Administrative", "Auditor (E.g. TGA, sponsor etc)"),
    ("Administrative", "HREC TAT (weeks)"),
    ("Administrative", "Additional Approvals (E.g. RGO)"),
    ("Administrative", "Requirements and Timelines for additional approvals (e.g RGO)"),
    ("Administrative", "TAT Draft Contract/Budget to Finalisation (weeks)"),
    ("Administrative", "Does your site have ARTNet (or equivalent) accreditation?"),
    ("Administrative", "If yes, please provide details of radioisotopes."),
    ("Administrative", "Remote Monitoring?"),
    ("PET/CT", "Manufacturer of PET/CT"),
]

POST_HEADERS: list[tuple[str, str]] = [
    ("Site Details", "Country"),
    ("Site Details", "Name of Site"),
    ("Site Details", "Department"),
    ("Projects", "Protocol"),
    ("Projects", "Indication"),
    ("Projects", "Expected Minimum Enrolment Per CTRA (#)"),
    ("Projects", "Expected Maximum Enrolment per CTRA (#)"),
    ("Actual Timelines", "Time to FPI from SIV (actual) (weeks)"),
    ("Breast Cancer", "What was the actual enrolment for metastatic or locally advanced breast cancer?"),
    ("Melanoma", "What was the actual enrolment for locally advanced or metastatic melanoma?"),
    ("Overall Site Assessment", "Directly Competing Trials?"),
    ("Overall Site Assessment", "Time to RGO Approval (Score 1-3)"),
    ("Overall Site Assessment", "Time to FPI (Score 1-5)"),
    ("Overall Site Assessment", "Recruitment Success (Score 1-5)"),
    ("Overall Site Assessment", "Comments"),
]

ALPHA = {
    "Country": "Australia",
    "State": "New South Wales",
    "Name of Site": "Test Hospital Alpha",
    "Department": "Nuclear Medicine",
    "Site Address": "1 Test Street, Sydney NSW 2000",
    "Last Survey Return Date": datetime(2026, 3, 1),
    "Last Study Survey Completed for": "TEST-101",
    "Private/Public": "Public",
    "Survey Type": "Site feasibility survey",
    "Is site/department currently accepting": "Yes",
    "Recommend for Diagnostics?": "Not applicable",
    "Recommend for Therapeutics?": "Yes - strong team",
    "Start-up (weeks)": "12-14",
    "SIV (weeks)": 16,
    "Radioisotope": "Lu-177, 68Ga and Y90",
    "Experience in conducting imaging clinical trials?": "Yes",
    "Breast Cancer": "Yes",
    "# Trials Breast Cancer (imaging)": 3,
    "# Trials Breast Cancer (therapeutic)": "2",
    "Myelofibrosis": "No",
    "How many Breast Cancer patients": 400,
    "Is your site licensed for 64Cu?": "Yes",
    "Is your site licensed for 177Lu?": "yes",
    "Are your site personnel trained to use 117Lu": "Yes",
    "Have your site previously calibrated": "Yes",
    "What days/time": "Mon to Thu",
    "#fridge": 2,
    "#-20C": "1",
    "Radioactive refrigerator (4 degrees)?": "Yes",
    "room temperature storage for IP storage": "No",
    "Do you have an ECG?": "Yes",
    "secure -20 freezer": "No",
    "secure -80 freezer": "Yes",
    "Has your site undergone": "Yes",
    "Auditor": "Sponsor",
    "HREC TAT (weeks)": 6,
    "Additional Approvals (E.g. RGO)": "RGO",
    "Requirements and Timelines": "Four weeks after HREC",
    "TAT Draft Contract": "8 weeks",
    "ARTNet": "Yes",
    "If yes, please provide details": "90Y, 177Lu",
    "Remote Monitoring?": "No",
    "Manufacturer of PET/CT": "Imaging Co",
}


def _value(row: dict[str, Any], header: str) -> Any:
    h = header.lower()
    for key, value in row.items():  # a header that starts with the key wins ...
        if h.startswith(key.lower()):
            return value
    for key, value in row.items():  # ... then one that contains it
        if key.lower() in h and not h.startswith(("is site/", "how many")):
            return value
    return None


def _sheet(ws: Any, headers: list[tuple[str, str]], rows: list[dict[str, Any]], order: list[int]) -> None:
    ws.append(["SENSITIVE: NOT FOR SHARING EXTERNAL TO AVION"])
    sections, last = [], None
    for i in order:
        section = headers[i][0]
        sections.append(section if section != last else None)
        last = section
    ws.append([None, *sections])
    ws.append([None, *[headers[i][1] for i in order]])
    for row in rows:
        ws.append([None, *[_value(row, headers[i][1]) for i in order]])


def workbook(
    feas: list[dict[str, Any]], post: list[dict[str, Any]] | None = None, *, shuffle: bool = False
) -> bytes:
    wb = openpyxl.Workbook()
    wb.active.title = "Instructions"
    for name in (
        "Site Assessment Metrics",
        "Feasibility",
        "Contacts",
        "Post-Activation _ DRAFT",
        "Validation",
    ):
        wb.create_sheet(name)
    order = list(range(len(FEAS_HEADERS)))
    if shuffle:  # same sections together, columns moved around within them
        random.Random(4).shuffle(order)  # noqa: S311 (test column order)
        order.sort(key=lambda i: [s for s, _ in FEAS_HEADERS].index(FEAS_HEADERS[i][0]))
    _sheet(wb["Feasibility"], FEAS_HEADERS, feas, order)
    _sheet(wb["Post-Activation _ DRAFT"], POST_HEADERS, post or [], list(range(len(POST_HEADERS))))
    wb["Contacts"].append(["Name", "Phone"])
    wb["Contacts"].append(["SECRET-CONTACT", "0400 000 000"])
    wb["Validation"].append([None, "Country", "State"])
    wb["Validation"].append([None, "Australia", "VALIDATION-OPTION"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


BETA = {
    "Name of Site": "Test Hospital Beta",
    "State": "TAS",
    "Site Address": "Somewhere remote",
    "Last Survey Return Date": "15/07/2025",
    "Is site/department currently accepting": "Unknown",
    "Recommend for Diagnostics?": "Not known",
    "Recommend for Therapeutics?": "Not known",
}


def test_cell_reading() -> None:
    assert (
        yes_no("Yes - strong team") == "Yes"
        and yes_no("no.") == "No"
        and yes_no("Not applicable") == "Not applicable"
    )
    assert yes_no("  ") is None and yes_no(None) is None
    assert number("12-14") == 13 and number("8 weeks") == 8 and number("TBC") is None and number(6) == 6
    assert a_date("15/07/2025") == date(2025, 7, 15) and a_date(datetime(2026, 3, 1)) == date(2026, 3, 1)
    assert a_date("Jun 2025") == date(2025, 6, 1) and a_date("soon") is None
    assert isotopes_in("Lu-177, 68Ga and Y90") == ["68Ga", "90Y", "177Lu"]
    assert city_of("1 Test Street, Sydney NSW 2000") == "Sydney" and city_of("Somewhere remote") is None


def test_a_site_from_the_feasibility_sheet() -> None:
    result = read_tracker(workbook([ALPHA, BETA]), source_url="https://example.sharepoint.com/tracker.xlsm")
    alpha = next(s for s in result.sites if s.name == "Test Hospital Alpha")
    assert alpha.id == "tr-test-hospital-alpha-nuclear-medicine" and alpha.department == "Nuclear Medicine"
    assert (alpha.city, alpha.state) == ("Sydney", "NSW") and alpha.lat == pytest.approx(-33.87)
    assert alpha.last_survey == date(2026, 3, 1) and alpha.last_survey_study == "TEST-101"
    assert alpha.accepting == "Yes" and alpha.recommend_therapeutics == "Yes"
    assert alpha.recommend_diagnostics == "Not applicable"
    assert recommendation_of(alpha) == Recommendation.THERAPEUTICS
    assert alpha.timelines.startup_weeks == 13 and alpha.timelines.siv_weeks == 16
    assert alpha.experience.isotopes == ["68Ga", "90Y", "177Lu"] and alpha.experience.imaging_trials == "Yes"
    breast = next(c for c in alpha.experience.by_indication if c.indication == "Breast cancer")
    assert (breast.experience, breast.imaging, breast.therapeutic) == ("Yes", 3, 2)
    myelo = next(c for c in alpha.experience.by_indication if c.indication == "Myelofibrosis")
    assert myelo.experience == "No"  # "How many ... patients" is not mistaken for the experience answer
    assert alpha.ip.licensed == ["64Cu", "177Lu"] and alpha.ip.trained == ["177Lu"]  # "117Lu" in the template
    assert alpha.ip.handled == ["90Y"] and alpha.ip.treatment_days == "Mon to Thu"
    assert (alpha.ip.fridges, alpha.ip.freezers_20) == (
        2,
        1,
    )  # counts, not the "Radioactive refrigerator?" answer
    assert alpha.equipment["ECG"] == "Yes" and alpha.equipment["Gamma counter"] is None
    assert (
        alpha.equipment["Temperature-monitored secure storage (−20 °C / −80 °C)"] == "Yes"
    )  # either freezer
    assert alpha.equipment["Temperature-monitored secure storage (room temperature)"] == "No"
    assert (
        alpha.admin.auditor == "Sponsor" and alpha.admin.hrec_weeks == 6 and alpha.admin.contract_weeks == 8
    )
    assert alpha.admin.additional_approvals == "RGO"  # not the "Requirements and Timelines" column
    assert alpha.admin.artnet == "Yes (90Y, 177Lu)" and alpha.admin.remote_monitoring == "No"
    assert alpha.source_url == "https://example.sharepoint.com/tracker.xlsm"


def test_unknowns_and_places_without_a_city() -> None:
    beta = next(s for s in read_tracker(workbook([ALPHA, BETA])).sites if s.name == "Test Hospital Beta")
    assert recommendation_of(beta) == Recommendation.NOT_ASSESSED  # "Not known" is not "not recommended"
    assert (beta.city, beta.state) == ("TAS", "TAS")  # pinned to the middle of the state
    assert beta.accepting == "Unknown" and beta.last_survey == date(2025, 7, 15)


def test_columns_found_by_header_not_position() -> None:
    plain = read_tracker(workbook([ALPHA])).sites[0]
    moved = read_tracker(workbook([ALPHA], shuffle=True)).sites[0]
    assert moved.model_dump() == plain.model_dump()


def test_latest_survey_of_a_site_wins() -> None:
    older = {**ALPHA, "Last Survey Return Date": datetime(2024, 1, 1), "HREC TAT (weeks)": 20}
    result = read_tracker(workbook([older, ALPHA]))
    assert len(result.sites) == 1 and result.sites[0].admin.hrec_weeks == 6
    assert result.skipped["older_surveys_of_the_same_site"] == 1


def test_post_activation_joins_projects_and_scores() -> None:
    post = [
        {"Name of Site": "test hospital alpha", "Department": "Nuclear Medicine", "Protocol": "TEST-201",
         "Indication": "Breast cancer", "Expected Minimum": 4, "Expected Maximum": 8,
         "actual enrolment for metastatic or locally advanced breast": 5, "Directly Competing Trials?": "No"},
        {"Name of Site": "Test Hospital Alpha", "Department": "Nuclear Medicine", "Protocol": "TEST-202",
         "actual enrolment for locally advanced or metastatic melanoma": "3",
         "Time to RGO Approval": 9, "Time to FPI (Score": 4, "Recruitment Success": 5,
         "Comments": "Good site"},
        {"Name of Site": "Not In Feasibility", "Protocol": "TEST-203"},
    ]  # fmt: skip
    result = read_tracker(workbook([ALPHA], post))
    perf = result.sites[0].performance
    assert perf is not None and [p.protocol for p in perf.projects] == ["TEST-201", "TEST-202"]
    assert (perf.projects[0].expected_min, perf.projects[0].expected_max, perf.projects[0].actual) == (
        4,
        8,
        5,
    )
    assert perf.projects[1].actual == 3
    assert perf.scores == {
        "Time to RGO approval": 3,
        "Time to FPI": 4,
        "Recruitment success": 5,
    }  # 9 capped at 3
    assert perf.competing_trials == "No" and perf.comments == "Good site"
    assert result.skipped["post_activation_rows_not_matched"] == 1


def test_contacts_and_dropdown_options_are_never_read() -> None:
    dumped = str([s.model_dump() for s in read_tracker(workbook([ALPHA, BETA])).sites])
    assert "SECRET-CONTACT" not in dumped and "VALIDATION-OPTION" not in dumped


def test_the_page_works_on_tracker_sites() -> None:
    sites = read_tracker(workbook([ALPHA, BETA])).sites
    page = build_site_feasibility(sites, TODAY)
    tiles = {t.key: t.value for t in page.tiles}
    assert tiles["sites"] == "2" and tiles["therapeutics"] == "1" and tiles["surveys_due"] == "1"


class FakeGraph:
    def __init__(self, content: bytes) -> None:
        self.content, self.downloads, self.paths = content, 0, []

    async def get(self, path: str) -> dict[str, Any]:
        self.paths.append(path)
        return {"name": "tracker.xlsm", "webUrl": "https://example.sharepoint.com/tracker.xlsm"}

    async def download_url(self, path: str) -> str:
        self.paths.append(path)
        return "https://example.sharepoint.com/download"

    async def stream_url(self, url: str) -> AsyncIterator[bytes]:
        self.downloads += 1
        yield self.content[:100]
        yield self.content[100:]


def test_source_downloads_once_then_caches() -> None:
    graph = FakeGraph(workbook([ALPHA]))
    now = [0.0]
    source = WorkbookFeasibilitySource(
        graph,  # type: ignore[arg-type]
        drive_id="b!drive",
        item_id="ITEM",
        cache_seconds=300,
        clock=lambda: now[0],
    )

    async def go() -> list[FeasibilitySite]:
        await source.list_sites()
        await source.list_sites()
        assert graph.downloads == 1  # cached
        now[0] = 301
        await source.list_sites()
        assert graph.downloads == 2  # expired
        return await source.list_sites(force_refresh=True)

    sites = asyncio.run(go())
    assert graph.downloads == 3 and sites[0].source_url == "https://example.sharepoint.com/tracker.xlsm"
    assert graph.paths[1] == "/drives/b!drive/items/ITEM/content"  # read-only download
    assert source.info().mode == "sharepoint" and source.info().fetched_at is not None


def test_source_choice() -> None:
    base = {"sharepoint_tenant_id": "t", "sharepoint_client_id": "c", "sharepoint_client_secret": "s"}
    assert isinstance(build_feasibility_source(Settings(**base)), DemoFeasibilitySource)  # type: ignore[arg-type]
    ids = {"site_feasibility_drive_id": "b!d", "site_feasibility_item_id": "i"}
    mock = Settings(**base, **ids, site_feasibility_mode="mock")  # type: ignore[arg-type]
    assert isinstance(build_feasibility_source(mock), DemoFeasibilitySource)
    live = build_feasibility_source(Settings(**base, **ids, site_feasibility_mode="auto"))  # type: ignore[arg-type]
    assert isinstance(live, WorkbookFeasibilitySource)
    no_secret = Settings(**ids, site_feasibility_mode="auto", sharepoint_client_secret="")  # type: ignore[arg-type]
    assert isinstance(build_feasibility_source(no_secret), DemoFeasibilitySource)
