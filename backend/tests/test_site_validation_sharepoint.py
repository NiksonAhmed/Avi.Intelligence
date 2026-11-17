"""Site validation from SharePoint lists: column mapping, matching rows to sites, and the admin status.
A fake Graph client stands in for SharePoint (tests never call real APIs)."""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

from fastapi.testclient import TestClient

from app.site_validation.models import EquipmentKind, ScanStatus
from app.site_validation.sharepoint import (
    SharePointSiteSource,
    equipment_of,
    isotope_of,
    parse_field_map,
    scan_status_of,
)

SITES = [
    {
        "id": "1",
        "webUrl": "https://sp/sites/1",
        "fields": {
            "Title": "Demo Hospital",
            "City": "Hobart",
            "State": "Tasmania",
            "SitePhysicist": "Physicist (demo)",
            "LicensedFor": ["Cu-64", "117Lu"],
            "PETManufacturer": "Siemens",
            "PETModel": "Demo",
            "GammaCounterOnSite": "Yes",
            "Phantoms": "NEMA IEC Body Phantom; ARTnet long half-life radionuclide insert",
            "QAQCRoutineCT": "Daily warm-up",
            "TransferMethods": ["sFTP", "Web (https)"],
            "DICOMExport": "Yes",
        },
    },
    {"id": "2", "fields": {"Title": "Somewhere", "City": "Unknown town", "State": "QLD"}},  # placed by state
    {"id": "3", "fields": {"Title": "No place"}},  # skipped: nowhere to put it
]
VALIDATIONS = [
    {
        "id": "v1",
        "fields": {
            "Site": {"LookupValue": "Demo Hospital"},
            "Equipment": "PET/CT",
            "Isotope": "[64Cu]",
            "ValidatedBy": "ARTnet",
            "ValidatedOn": "2026-03-10T00:00:00Z",
            "FilesAvailable": True,
        },
    },
    {
        "id": "v2",
        "fields": {
            "Site": "Other site",
            "Equipment": "SPECT",
            "Isotope": "225Ac",
            "ValidatedOn": "2026-03-10",
        },
    },  # no matching site
    {
        "id": "v3",
        "fields": {
            "Site": "Demo Hospital",
            "Equipment": "Fridge",
            "Isotope": "64Cu",
            "ValidatedOn": "2026-03-10",
        },
    },  # skipped: unknown equipment
]
SCANS = [
    {"id": "s1", "fields": {"Site": "demo hospital", "Study": "DEMO-1", "Equipment": "Gamma counter",
                            "Isotope": "Ac-225", "Status": "Scheduled", "ScanDate": "2026-12-08"}},
]  # fmt: skip


class FakeGraph:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def get(self, path: str) -> dict[str, Any]:
        self.calls.append(path)
        return {"id": "site-id"}

    async def get_all(self, path: str) -> list[dict[str, Any]]:
        self.calls.append(path)
        if "/lists/Sites/" in path:
            return SITES
        if "/lists/Validations/" in path:
            return VALIDATIONS
        return SCANS


def _source() -> tuple[SharePointSiteSource, FakeGraph]:
    graph = FakeGraph()
    src = SharePointSiteSource(
        graph,  # type: ignore[arg-type]
        site_url="https://example.sharepoint.com/sites/physics",
        sites_list="Sites",
        validations_list="Validations",
        scans_list="Phantom scans",
        fields=parse_field_map(None),
        cache_seconds=60,
    )
    return src, graph


def test_value_parsing() -> None:
    assert [isotope_of(x) for x in ("Cu-64", "64Cu", "[64Cu]", "Cu64", "117Lu", "Ac-225", "nope")] == [
        "64Cu", "64Cu", "64Cu", "64Cu", "177Lu", "225Ac", None,
    ]  # fmt: skip
    assert equipment_of("SPECT/CT") == EquipmentKind.SPECT_CT and equipment_of("PET") == EquipmentKind.PET_CT
    assert equipment_of("Dose calibrator") == EquipmentKind.DOSE_CALIBRATOR and equipment_of("x") is None
    assert scan_status_of("Submitted to core lab") == ScanStatus.SUBMITTED
    assert scan_status_of("Scheduled") == ScanStatus.BOOKED


def test_reads_the_three_lists() -> None:
    src, graph = _source()
    sites = asyncio.run(src.list_sites())
    assert [s.name for s in sites] == ["Demo Hospital", "Somewhere"]
    hosp = sites[0]
    assert hosp.state == "TAS" and (hosp.lat, hosp.lon) == (-42.88, 147.33)
    assert hosp.licensed == ["64Cu", "177Lu"]
    assert [e.kind for e in hosp.equipment] == [EquipmentKind.PET_CT, EquipmentKind.GAMMA_COUNTER]
    assert hosp.qa.phantoms == ["NEMA IEC Body Phantom", "ARTnet long half-life radionuclide insert"]
    assert hosp.qa.routines == {"CT": "Daily warm-up"} and hosp.transfer.methods == ["sFTP", "Web (https)"]
    assert [(v.equipment, v.isotope, v.validated_on) for v in hosp.validations] == [
        (EquipmentKind.PET_CT, "64Cu", date(2026, 3, 10))
    ]
    assert hosp.scans[0].status == ScanStatus.BOOKED and hosp.scans[0].isotope == "225Ac"
    assert hosp.source_url == "https://sp/sites/1"
    assert src.skipped == {"sites": 1, "validations": 1, "scans": 0, "not_matched_to_a_site": 1}
    assert any("Phantom%20scans" in c for c in graph.calls)  # list names are URL-encoded
    n = len(graph.calls)
    asyncio.run(src.list_sites())
    assert len(graph.calls) == n  # cached


def test_field_map_names_real_columns() -> None:
    fields = parse_field_map('{"sites.city": "Suburb"}')
    assert fields["sites.city"][0] == "Suburb"
    try:
        parse_field_map('{"nope": "x"}')
    except ValueError as e:
        assert "unknown field" in str(e)
    else:
        raise AssertionError("expected an error")


def test_admin_status_in_demo_mode(client: TestClient, make_client) -> None:  # type: ignore[no-untyped-def]
    from app.auth.rbac import Role

    body = client.get("/api/v1/connectors/site-validation").json()
    assert body["mode"] == "demo" and body["ok"] is None and "mock" in body["reason"]
    assert client.post("/api/v1/connectors/site-validation/test").status_code == 200
    assert make_client(Role.CRA).get("/api/v1/connectors/site-validation").status_code == 403
