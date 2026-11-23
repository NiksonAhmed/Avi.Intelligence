"""Site validation from the sites' feasibility survey answers (user decision 2026-11-23). The workbook is made
up (the tracker's header wording, invented sites); tests never read the real tracker or call SharePoint."""

from __future__ import annotations

import asyncio
import io
from collections.abc import AsyncIterator
from datetime import date, datetime
from typing import Any

import openpyxl
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.site_feasibility.workbook import TrackerDownload, WorkbookFeasibilitySource, read_tracker
from app.site_validation.demo import DemoSiteSource
from app.site_validation.models import EquipmentKind
from app.site_validation.report import Status, build_site_detail, build_site_validation
from app.site_validation.source import build_site_source, get_site_source
from app.site_validation.survey import SurveySiteSource, read_survey_sites

TODAY = date(2026, 11, 23)

# (section, header) as the tracker words them.
HEADERS: list[tuple[str, str]] = [
    ("Site Details", "State"),
    ("Site Details", "Name of Site"),
    ("Site Details", "Department"),
    ("Site Details", "Site Address"),
    ("Site Details", "Last Survey Return Date"),
    ("IP", "Have your site previously calibrated, drawn up a specific dose, and administered an 90Y based"),
    ("Equipment", "Do you have a Gamma Counter?"),
    ("Equipment", "Do you have a Dose Calibrator to measure radioactivity of IP admin?"),
    ("Equipment", "Do you have a Radiopharmacy / Hot Lab?"),
    ("Administrative", "Does your site have ARTNet (or equivalent) accreditation?"),
    ("PET/CT", "Manufacturer of PET/CT"),
    ("PET/CT", "PET/CT System ModelVersion/Serial No."),
    ("PET/CT", "PET/CT Approximate Installation Date"),
    ("PET/CT", "PET/CT Last Calibration/Normalization"),
    ("PET/CT", "PET/CT Scanner Maintenance Schedule"),
    ("PET/CT", "Calibrated by ARTnet for 90Y?"),
    ("PET/CT", "Date of certification for 90Y?"),
    ("PET/CT", "Files availabile 90Y?"),
    ("PET/CT", "Calibrated by ARTnet for 64Cu?"),
    ("SPECT/CT", "Manufacturer of SPECT/CT"),
    ("SPECT/CT", "ARTnet Calibration 225Ac?"),
    ("SPECT/CT", "Certificate Available 225Ac?"),
    ("Phantoms and QA/QC Procedures", "Phantom Availability (Select one)"),
    ("Phantoms and QA/QC Procedures", "QA/QC routines PET/CT"),
    ("Dose Calibrator (DC) - SPECT Radionuclides", "Manufacturer - DC SPECT"),
    ("Dose Calibrator (DC) - SPECT Radionuclides", "DC calibrated for 225Ac?"),
    ("Dose Calibrator (DC) - SPECT Radionuclides", "ARTnet certification for 225Ac?"),
    ("Gamma Counter System (GC)", "Has this GC been calibrated for 90Y?"),
    ("Gamma Counter System (GC)", "manufacturer's preset calibration factors for 90Y?"),
    ("Image Data Storage and Transfer", "PACS System"),
    ("Image Data Storage and Transfer", "Export reconstructed images in a DICOM format?"),
    ("Image Data Storage and Transfer", "Alternative Data Transfer: sFTP"),
    ("Image Data Storage and Transfer", "Alternative Data Transfer: Web (https)"),
]

ALPHA: dict[str, Any] = {
    "State": "VIC",
    "Name of Site": "Test Hospital Alpha",
    "Department": "Nuclear Medicine",
    "Site Address": "1 Test Street, Melbourne VIC 3000",
    "Last Survey Return Date": datetime(2026, 3, 1),
    "Have your site previously calibrated, drawn up a specific dose, and administered an 90Y based": "Yes",
    "Do you have a Gamma Counter?": "Yes",
    "Do you have a Radiopharmacy / Hot Lab?": "Yes",
    "Does your site have ARTNet (or equivalent) accreditation?": "Yes",
    "Manufacturer of PET/CT": "Imaging Co",
    "PET/CT System ModelVersion/Serial No.": "Model X",
    "PET/CT Approximate Installation Date": datetime(2020, 3, 1),
    "PET/CT Last Calibration/Normalization": "10/10/2026",
    "PET/CT Scanner Maintenance Schedule": "Quarterly",
    "Calibrated by ARTnet for 90Y?": "Yes",
    "Date of certification for 90Y?": datetime(2024, 1, 15),  # old: still never "overdue" (site's answer)
    "Files availabile 90Y?": "Yes",
    "Calibrated by ARTnet for 64Cu?": "No",
    "Manufacturer of SPECT/CT": "N/A",
    "ARTnet Calibration 225Ac?": "Yes",
    "Certificate Available 225Ac?": "No",
    "Phantom Availability (Select one)": "NEMA IEC Body Phantom",
    "QA/QC routines PET/CT": "Daily QC",
    "Manufacturer - DC SPECT": "Calibrator Co",
    "DC calibrated for 225Ac?": "Yes",
    "ARTnet certification for 225Ac?": "Yes",
    "Has this GC been calibrated for 90Y?": "Not known",
    "manufacturer's preset calibration factors for 90Y?": "Yes",
    "PACS System": "Demo PACS",
    "Export reconstructed images in a DICOM format?": "Yes",
    "Alternative Data Transfer: sFTP": "Yes",
    "Alternative Data Transfer: Web (https)": "No",
}
BETA: dict[str, Any] = {"State": "TAS", "Name of Site": "Test Hospital Beta", "Site Address": "Hobart"}


def workbook(*sites: dict[str, Any]) -> bytes:
    wb = openpyxl.Workbook()
    wb.active.title = "Instructions"
    ws = wb.create_sheet("Feasibility")
    wb.create_sheet("Contacts").append(["SECRET-CONTACT"])
    ws.append(["SENSITIVE: NOT FOR SHARING EXTERNAL TO AVION"])
    sections, last = [], None
    for section, _ in HEADERS:
        sections.append(section if section != last else None)
        last = section
    ws.append([None, *sections])
    ws.append([None, *[h for _, h in HEADERS]])
    for site in sites:
        ws.append([None, *[site.get(h) for _, h in HEADERS]])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _alpha() -> Any:
    return next(s for s in read_survey_sites(workbook(ALPHA, BETA)) if s.name == "Test Hospital Alpha")


def test_equipment_and_calibrations_from_the_survey() -> None:
    alpha = _alpha()
    kinds = {e.kind: e for e in alpha.equipment}
    # SPECT/CT has no manufacturer ("N/A") but reports a calibration, so it is on site; the gamma counter
    # comes from the general Equipment question.
    assert set(kinds) == set(EquipmentKind)
    pet = kinds[EquipmentKind.PET_CT]
    assert (pet.manufacturer, pet.model, pet.installed, pet.maintenance) == (
        "Imaging Co",
        "Model X",
        date(2020, 3, 1),
        "Quarterly",
    )
    assert pet.last_calibration == date(2026, 10, 10) and kinds[EquipmentKind.SPECT_CT].manufacturer is None
    found = {(v.equipment, v.isotope): v for v in alpha.validations}
    assert set(found) == {
        (EquipmentKind.PET_CT, "90Y"),
        (EquipmentKind.SPECT_CT, "225Ac"),
        (EquipmentKind.DOSE_CALIBRATOR, "225Ac"),
    }  # "No", "Not known", "preset" and the IP question are not calibrations
    pet90 = found[(EquipmentKind.PET_CT, "90Y")]
    assert (
        pet90.validated_by == "ARTnet" and pet90.validated_on == date(2024, 1, 15) and pet90.files_available
    )
    assert found[(EquipmentKind.SPECT_CT, "225Ac")].files_available is False
    assert (
        found[(EquipmentKind.DOSE_CALIBRATOR, "225Ac")].validated_by == "ARTnet"
    )  # from "ARTnet certification"
    assert all(v.reported_by_site for v in alpha.validations)
    assert alpha.qa.phantoms == ["NEMA IEC Body Phantom"] and alpha.qa.routines == {"PET/CT": "Daily QC"}
    assert alpha.transfer.pacs == "Demo PACS" and alpha.transfer.dicom_export == "Yes"
    assert alpha.transfer.methods == ["sFTP"]
    assert alpha.radiopharmacy is True and alpha.physicist is None and alpha.scans == []


def test_sites_answers_are_never_due_or_overdue() -> None:
    sites = read_survey_sites(workbook(ALPHA, BETA))
    page = build_site_validation(sites, TODAY, survey=True)
    tiles = {t.key: t.value for t in page.tiles}
    # Tiles from what the survey holds (user decision 2026-11-23): nothing that is always empty.
    assert tiles == {
        "validated": "1 of 2",
        "artnet": "1 of 2",
        "imaging": "1 of 2",
        "phantoms": "1 of 2",
        "stale": "1",
    }
    notes = {t.key: t.note for t in page.tiles}
    assert notes["imaging"] == "PET/CT 1 · SPECT/CT 1"  # Beta (no survey date) is the out-of-date one
    assert {r.status for r in page.rows} == {Status.REPORTED}
    assert page.reviews == [] and page.scans == [] and not any(p.attention for p in page.sites)
    assert page.headline.startswith(
        "1 of 2 sites report a calibration; 1 have PET/CT or SPECT/CT; 1 survey is over 12 months old."
    )
    assert (
        "not verified by Avion physics" in page.headline
        and "Calibrated (site's answer)" in page.rules["status"]
    )
    pins = {p.name: p for p in page.sites}
    assert (
        pins["Test Hospital Alpha"].status == Status.REPORTED
        and pins["Test Hospital Beta"].status == Status.NONE
    )
    # Filters still work.
    only = build_site_validation(sites, TODAY, equipment=EquipmentKind.SPECT_CT, isotope="225Ac", survey=True)
    assert [r.isotope for r in only.rows] == ["225Ac"]
    imaging = next(t for t in only.tiles if t.key == "imaging")
    assert (imaging.label, imaging.value) == ("SPECT/CT on site", "1 of 2")


def test_a_site_panel_says_whose_answer_it_is() -> None:
    d = build_site_detail(_alpha(), TODAY)
    cell = next(c for c in d.grid if c.equipment == EquipmentKind.PET_CT and c.isotope == "90Y")
    assert cell.state == Status.REPORTED and cell.validated
    assert cell.tip == (
        "PET/CT · 90Y: calibrated, as the site reported by ARTnet · certified 15 Jan 2024"
        " · certificate on file"
    )
    spect = next(c for c in d.grid if c.equipment == EquipmentKind.SPECT_CT and c.isotope == "225Ac")
    assert spect.tip.endswith("no date given · certificate not on file")
    gc = next(c for c in d.grid if c.equipment == EquipmentKind.GAMMA_COUNTER and c.isotope == "90Y")
    assert gc.state == Status.NONE  # "Not known"


def test_same_site_ids_as_site_feasibility() -> None:
    content = workbook(ALPHA, BETA)
    assert [s.id for s in read_survey_sites(content)] == [s.id for s in read_tracker(content).sites]


class FakeGraph:
    def __init__(self, content: bytes) -> None:
        self.content, self.downloads = content, 0

    async def get(self, path: str) -> dict[str, Any]:
        return {"webUrl": "https://example.sharepoint.com/tracker.xlsm"}

    async def download_url(self, path: str) -> str:
        return "https://example.sharepoint.com/download"

    async def stream_url(self, url: str) -> AsyncIterator[bytes]:
        self.downloads += 1
        yield self.content


def _download(graph: FakeGraph) -> TrackerDownload:
    return TrackerDownload(graph, drive_id="b!d", item_id="i", cache_seconds=300)  # type: ignore[arg-type]


def test_both_pages_share_one_download() -> None:
    graph = FakeGraph(workbook(ALPHA, BETA))
    download = _download(graph)

    async def go() -> None:
        await WorkbookFeasibilitySource(download).list_sites()
        sites = await SurveySiteSource(download).list_sites()
        assert len(sites) == 2 and sites[0].source_url == "https://example.sharepoint.com/tracker.xlsm"

    asyncio.run(go())
    assert graph.downloads == 1


def test_source_choice() -> None:
    download = _download(FakeGraph(b""))
    assert isinstance(build_site_source(Settings(site_validation_mode="auto"), download), SurveySiteSource)  # type: ignore[call-arg]
    assert isinstance(build_site_source(Settings(site_validation_mode="mock"), download), DemoSiteSource)  # type: ignore[call-arg]
    assert isinstance(build_site_source(Settings(site_validation_mode="auto"), None), DemoSiteSource)  # type: ignore[call-arg]


def test_page_and_admin_card_in_survey_mode(client: TestClient) -> None:
    source = SurveySiteSource(_download(FakeGraph(workbook(ALPHA, BETA))))
    client.app.dependency_overrides[get_site_source] = lambda: source  # type: ignore[attr-defined]
    body = client.get("/api/v1/site-validation").json()
    assert body["source"]["mode"] == "survey" and "not verified by Avion physics" in body["source"]["reason"]
    assert {t["key"]: t["value"] for t in body["tiles"]}["phantoms"] == "1 of 2"
    assert body["rows"][0]["status"] == "reported"
    card = client.get("/api/v1/connectors/site-validation").json()
    assert (
        card["mode"] == "survey"
        and card["ok"]
        and card["counts"] == {"sites": 2, "validations": 3, "scans": 0}
    )
    xlsx = client.get("/api/v1/site-validation/export.xlsx")
    assert xlsx.status_code == 200 and xlsx.content[:2] == b"PK"
