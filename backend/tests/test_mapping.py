from __future__ import annotations

from typing import Any

import pytest

from app.connectors.sharepoint.mapping import (
    DEFAULT_FIELD_MAP,
    collect_person_lookup_ids,
    derive_status,
    extract_sop_number,
    field_to_text,
    folder_from_parent_path,
    is_within_folder,
    map_list_item_to_sop,
    normalise_status,
    parse_field_map,
    sort_sops,
    title_from_file_name,
)
from app.connectors.sharepoint.models import SopStatus, StatusSource


def make_item(name: str = "SOP-0042 Site Activation v3.2.docx", **fields: Any) -> dict[str, Any]:
    return {
        "id": "1",
        "fields": fields,
        "driveItem": {
            "id": "01ABC",
            "name": name,
            "webUrl": "https://avion.sharepoint.com/sites/QA/Docs/x.docx",
            "size": 1234,
            "file": {"mimeType": "application/pdf"},
            "parentReference": {"path": "/drives/b!xyz/root:/SOPs/Clinical%20Operations"},
            "lastModifiedDateTime": "2025-03-01T02:00:00Z",
            "lastModifiedBy": {"user": {"displayName": "Quality Team"}},
        },
    }


class TestExtraction:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("SOP-0042 Site Activation.docx", "SOP-0042"),
            ("sop_013 Informed consent.pdf", "SOP-013"),
            ("SOP CO 012 Monitoring.docx", "SOP-CO-012"),
            ("WI-101 Filing.docx", "WI-101"),
            ("Site Activation.docx", None),
        ],
    )
    def test_extract_sop_number(self, text: str, expected: str | None) -> None:
        assert extract_sop_number(text) == expected

    def test_title_from_file_name_strips_number_and_version(self) -> None:
        assert title_from_file_name("SOP-0042 Site Activation v3.2.docx", "SOP-0042") == "Site Activation"
        assert title_from_file_name("SOP_013_Informed_Consent.pdf", "SOP-013") == "Informed Consent"

    def test_title_falls_back_to_file_stem(self) -> None:
        assert title_from_file_name("SOP-0042.docx", "SOP-0042") == "SOP-0042"

    def test_field_to_text_handles_sharepoint_shapes(self) -> None:
        assert field_to_text("  Clinical ") == "Clinical"
        assert field_to_text(["QA", "Clinical"]) == "QA, Clinical"
        assert field_to_text({"LookupValue": "Quality"}) == "Quality"
        assert field_to_text(3) == "3"
        assert field_to_text(True) == "Yes"
        assert field_to_text("") is None


class TestStatus:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("Approved", SopStatus.EFFECTIVE),
            ("Effective", SopStatus.EFFECTIVE),
            ("Pending approval", SopStatus.IN_REVIEW),
            ("Draft", SopStatus.DRAFT),
            ("Superseded", SopStatus.SUPERSEDED),
            ("Retired", SopStatus.RETIRED),
            ("Banana", SopStatus.UNKNOWN),
        ],
    )
    def test_normalise_status(self, text: str, expected: SopStatus) -> None:
        assert normalise_status(text) == expected

    def test_status_column_wins(self) -> None:
        fields = {"DocumentStatus": "Draft", "_ModerationStatus": 0, "_UIVersionString": "3.0"}
        assert derive_status(fields, DEFAULT_FIELD_MAP) == (SopStatus.DRAFT, StatusSource.COLUMN)

    def test_content_approval_used_when_no_column(self) -> None:
        assert derive_status({"_ModerationStatus": 2}, DEFAULT_FIELD_MAP) == (
            SopStatus.IN_REVIEW,
            StatusSource.CONTENT_APPROVAL,
        )

    def test_version_number_fallback(self) -> None:
        assert derive_status({"_UIVersionString": "3.0"}, DEFAULT_FIELD_MAP)[0] == SopStatus.EFFECTIVE
        assert derive_status({"_UIVersionString": "3.1"}, DEFAULT_FIELD_MAP)[0] == SopStatus.DRAFT

    def test_unknown_when_nothing_available(self) -> None:
        assert derive_status({}, DEFAULT_FIELD_MAP) == (SopStatus.UNKNOWN, StatusSource.NONE)


class TestFieldMap:
    def test_default_when_empty(self) -> None:
        assert parse_field_map(None) == DEFAULT_FIELD_MAP

    def test_override_single_and_list(self) -> None:
        fm = parse_field_map('{"sop_number": "DocNo", "status": ["State", "Status"]}')
        assert fm["sop_number"] == ["DocNo"]
        assert fm["status"] == ["State", "Status"]
        assert fm["title"] == DEFAULT_FIELD_MAP["title"]

    @pytest.mark.parametrize("raw", ["not json", "[1]", '{"nope": "x"}', '{"status": ""}'])
    def test_rejects_invalid(self, raw: str) -> None:
        with pytest.raises(ValueError):
            parse_field_map(raw)


class TestFolders:
    def test_folder_from_parent_path_decodes(self) -> None:
        assert (
            folder_from_parent_path("/drives/b!x/root:/SOPs/Clinical%20Operations")
            == "SOPs/Clinical Operations"
        )
        assert folder_from_parent_path("/drives/b!x/root:") == ""
        assert folder_from_parent_path(None) == ""

    def test_is_within_folder(self) -> None:
        assert is_within_folder("SOPs/Clinical", "SOPs")
        assert is_within_folder("sops", "/SOPs/")
        assert not is_within_folder("SOPs-Archive", "SOPs")
        assert not is_within_folder("Templates", "SOPs")
        assert is_within_folder("anything", None)


class TestMapListItem:
    def test_maps_file_with_columns(self) -> None:
        item = make_item(
            DocumentStatus="Approved",
            DocumentVersion="3.2",
            EffectiveDate="2025-01-19T13:00:00Z",
            Department="Clinical Operations",
            Title="SOP-0042 Site Activation v3.2",
        )
        doc = map_list_item_to_sop(item, DEFAULT_FIELD_MAP)
        assert doc is not None
        assert doc.id == "01ABC"
        assert doc.sop_number == "SOP-0042"
        assert doc.title == "Site Activation"
        assert doc.version == "3.2"
        assert doc.status == SopStatus.EFFECTIVE
        assert doc.folder_path == "SOPs/Clinical Operations"
        assert doc.modified_by == "Quality Team"
        assert doc.effective_date is not None and doc.effective_date.year == 2025

    def test_explicit_title_column_used(self) -> None:
        doc = map_list_item_to_sop(make_item(DocumentTitle="Site Activation Procedure"), DEFAULT_FIELD_MAP)
        assert doc is not None and doc.title == "Site Activation Procedure"

    def test_skips_folders(self) -> None:
        item = make_item()
        item["driveItem"] = {"id": "f", "name": "SOPs", "folder": {"childCount": 3}}
        assert map_list_item_to_sop(item, DEFAULT_FIELD_MAP) is None

    def test_resolves_person_lookup(self) -> None:
        item = make_item(DocumentOwnerLookupId="12")
        assert collect_person_lookup_ids([item], DEFAULT_FIELD_MAP) == {"12"}
        doc = map_list_item_to_sop(item, DEFAULT_FIELD_MAP, {"12": "Head of Quality"}.get)
        assert doc is not None and doc.owner == "Head of Quality"


def test_sort_is_natural_and_unnumbered_last() -> None:
    docs = [
        map_list_item_to_sop(make_item(name=n), DEFAULT_FIELD_MAP)
        for n in ["SOP-10 B.docx", "Readme.docx", "SOP-2 A.docx"]
    ]
    ordered = sort_sops([d for d in docs if d])
    assert [d.sop_number for d in ordered] == ["SOP-2", "SOP-10", None]


class TestFolderRules:
    def test_relative_folder_and_department(self) -> None:
        from app.connectors.sharepoint.mapping import department_from_folder, relative_folder

        scope = "1. Avion SoPs"
        assert relative_folder("1. Avion SoPs/01. Clinical Operations/Monitoring", scope) == (
            "01. Clinical Operations/Monitoring"
        )
        assert department_from_folder("1. Avion SoPs/01. Clinical Operations", scope) == "Clinical Operations"
        assert department_from_folder("1. Avion SoPs/10. Medical Physics/Sub", scope) == "Medical Physics"
        assert department_from_folder("1. Avion SoPs/08. IT", scope) == "IT"
        assert department_from_folder("1. Avion SoPs", scope) is None

    def test_excluded_folders_and_file_types(self) -> None:
        from app.connectors.sharepoint.mapping import (
            has_allowed_extension,
            is_excluded_folder,
            parse_list_setting,
        )

        scope = "1. Avion SoPs"
        excluded = parse_list_setting("Avion Document Register; R3 Guideline Implementation ;", ";")
        assert excluded == ["Avion Document Register", "R3 Guideline Implementation"]
        assert is_excluded_folder("1. Avion SoPs/Avion Document Register", scope, excluded)
        assert is_excluded_folder("1. Avion SoPs/r3 guideline implementation/x", scope, excluded)
        assert not is_excluded_folder("1. Avion SoPs/01. Clinical Operations", scope, excluded)

        types = parse_list_setting("docx,doc,pdf", ",")
        assert has_allowed_extension("SOP-001 Thing.DOCX", types)
        assert not has_allowed_extension("Q&A_Sponsor Driven Audit.xlsx", types)
        assert has_allowed_extension("anything.xlsx", [])
