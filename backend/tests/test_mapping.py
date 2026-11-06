from __future__ import annotations

from typing import Any

import pytest

from app.connectors.sharepoint.mapping import (
    DEFAULT_FIELD_MAP,
    classify_file_name,
    collapse_duplicates,
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
    status_from_folder,
    title_from_file_name,
    version_from_file_name,
)
from app.connectors.sharepoint.models import DocumentKind, SopDocument, SopStatus, StatusSource


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


class TestAvionNaming:
    """Numbering, titles and versions as used in Avion's SOP library (verified against SharePoint)."""

    @pytest.mark.parametrize(
        ("name", "kind", "number", "parent"),
        [
            ("CO-SOP-001 Trial Master File Documentation.pdf", DocumentKind.SOP, "CO-SOP-001", None),
            ("DM-SOP-002_Data Management_v1.1_08Oct2025.docx", DocumentKind.SOP, "DM-SOP-002", None),
            ("CO-SOP-07 Essential Document Collection.pdf", DocumentKind.SOP, "CO-SOP-007", None),
            (
                "CO-005-A Site Qualification Visit Report_2.0.docx",
                DocumentKind.FORM,
                "CO-005-A",
                "CO-SOP-005",
            ),
            ("DM-004-A_Data Transfer Agreement_v1.0.docx", DocumentKind.FORM, "DM-004-A", "DM-SOP-004"),
            ("SM-TEM-001_Safety Database Tracker.xlsx", DocumentKind.FORM, "SM-TEM-001", None),
            # Mentions an SOP but is not one: signature pages and change controls.
            # DocuSign's completed-envelope download is the signed document itself.
            ("Complete_with_Docusign_CO-SOP-004_Filing_of_.pdf", DocumentKind.SOP, "CO-SOP-004", None),
            ("Complete_with_Docusign_DM-007-A_Prior_Lockin.pdf", DocumentKind.FORM, "DM-007-A", "DM-SOP-007"),
            ("CC-012_GA-001-D_PM-SOP-009.pdf", DocumentKind.OTHER, None, None),
            ("SOP-XXX Computer System Validation.docx", DocumentKind.OTHER, None, None),
            ("Avi.Data_health_uat_v1_0_090420.docx", DocumentKind.OTHER, None, None),
        ],
    )
    def test_classify_file_name(
        self, name: str, kind: DocumentKind, number: str | None, parent: str | None
    ) -> None:
        assert classify_file_name(name) == (kind, number, parent)

    @pytest.mark.parametrize(
        ("name", "title", "version"),
        [
            ("CO-SOP-014 Monitoring Visit Activities_2.0.docx", "Monitoring Visit Activities", "2.0"),
            ("DM-SOP-002_Data Management_v1.1_08Oct2025.docx", "Data Management", "1.1"),
            ("MP-SOP-001_Site_Qualification_v_1.0_FINAL.docx", "Site Qualification", "1.0"),
            ("CO-SOP-001 Trial Master File Documentation.pdf", "Trial Master File Documentation", None),
            # DocuSign exports drop the dot from the version.
            ("QA-001-B_Deviation_Log_20.pdf", "Deviation Log", "2.0"),
            ("DM-001-H_Study_Deletion_Approval_v10_17Feb2026docx.pdf", "Study Deletion Approval", "1.0"),
            ("ST-SOP-001_Statistical_Principles_10_-_Copy.pdf", "Statistical Principles", "1.0"),
        ],
    )
    def test_title_and_version_from_file_name(self, name: str, title: str, version: str | None) -> None:
        number = classify_file_name(name)[1]
        assert title_from_file_name(name, number) == title
        assert version_from_file_name(name, number) == version

    def test_template_title_column_is_ignored(self) -> None:
        item = make_item(name="SM-SOP-005 SAE Reconciliation_2.0.docx", Title="SOP Template")
        doc = map_list_item_to_sop(item, DEFAULT_FIELD_MAP)
        assert doc is not None and doc.title == "SAE Reconciliation"
        assert doc.version == "2.0"  # from the file name, not SharePoint's save count

    def test_sharepoint_save_count_is_not_the_document_version(self) -> None:
        doc = map_list_item_to_sop(
            make_item(name="CO-SOP-001 TMF.pdf", _UIVersionString="18.0"), DEFAULT_FIELD_MAP
        )
        assert doc is not None and doc.version is None


class TestFolderStatus:
    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            ("01. Clinical Operations/Approved", SopStatus.EFFECTIVE),
            ("01. Clinical Operations/Approved/Word_Documents_DoNotEdit", SopStatus.EFFECTIVE),
            ("02. General Administration/Approved/3. Document Archiving", SopStatus.EFFECTIVE),
            ("01. Clinical Operations/Approved/General CRA acitvities/Superseded", SopStatus.SUPERSEDED),
            ("07. Data Management/Templates/Superceded", SopStatus.SUPERSEDED),  # spelling as found
            ("01. Clinical Operations/DraftUnapproved", SopStatus.DRAFT),
            ("04. Quality Assurance/Draft Unapproved", SopStatus.DRAFT),
            ("07. Data Management/SOPs/SOP under Revision", SopStatus.IN_REVIEW),
            ("10. Medical Physics", None),
        ],
    )
    def test_status_from_folder(self, path: str, expected: SopStatus | None) -> None:
        assert status_from_folder(path) == expected

    def test_approved_folder_never_overrides_a_column_that_says_otherwise(self) -> None:
        fields = {"DocumentStatus": "Superseded"}
        assert derive_status(fields, DEFAULT_FIELD_MAP, SopStatus.EFFECTIVE) == (
            SopStatus.SUPERSEDED,
            StatusSource.COLUMN,
        )
        assert derive_status({}, DEFAULT_FIELD_MAP, SopStatus.EFFECTIVE) == (
            SopStatus.EFFECTIVE,
            StatusSource.FOLDER,
        )

    def test_superseded_or_draft_folder_wins_over_an_approved_column(self) -> None:
        fields = {"DocumentStatus": "Approved"}
        assert derive_status(fields, DEFAULT_FIELD_MAP, SopStatus.SUPERSEDED)[0] == SopStatus.SUPERSEDED
        assert derive_status(fields, DEFAULT_FIELD_MAP, SopStatus.DRAFT)[0] == SopStatus.DRAFT

    def test_status_uses_folder_below_the_sop_folder(self) -> None:
        item = make_item(name="CO-SOP-001 TMF.pdf")
        item["driveItem"]["parentReference"]["path"] = (
            "/drives/b!x/root:/1. Avion SoPs/01. CO/Approved/Superseded"
        )
        doc = map_list_item_to_sop(item, DEFAULT_FIELD_MAP, scope="1. Avion SoPs")
        assert doc is not None
        assert (doc.status, doc.status_source) == (SopStatus.SUPERSEDED, StatusSource.FOLDER)

    def test_executed_records_are_not_forms(self) -> None:
        item = make_item(name="IT-001-A_GxP Impact Assessment_SimpleTrials.pdf")
        item["driveItem"]["parentReference"]["path"] = (
            "/drives/b!x/root:/SOPs/08. IT/Executed Forms & Registers"
        )
        doc = map_list_item_to_sop(item, DEFAULT_FIELD_MAP, scope="SOPs")
        assert doc is not None and doc.kind == DocumentKind.OTHER


def _doc(name: str, folder: str = "SOPs/Approved", modified: str = "2025-01-01T00:00:00Z") -> SopDocument:
    item = make_item(name=name)
    item["driveItem"]["parentReference"]["path"] = f"/drives/b!x/root:/{folder}"
    item["driveItem"]["lastModifiedDateTime"] = modified
    doc = map_list_item_to_sop(item, DEFAULT_FIELD_MAP, scope="SOPs")
    assert doc is not None
    return doc


def test_collapse_duplicates_prefers_signed_pdf_and_borrows_version() -> None:
    word = _doc("CO-SOP-014 Monitoring Visit Activities_3.0.docx", "SOPs/Approved/Word_Documents_DoNotEdit")
    pdf = _doc("CO-SOP-014 Monitoring Visit Activities.pdf")
    superseded = _doc("CO-SOP-014 Monitoring Visit Activities.pdf", "SOPs/Approved/Superseded")
    other = _doc("CO-SOP-001 TMF.pdf")
    result = {(d.sop_number, d.status): d for d in collapse_duplicates([word, pdf, superseded, other])}
    assert len(result) == 3
    kept = result[("CO-SOP-014", SopStatus.EFFECTIVE)]
    assert kept.file_name.endswith(".pdf")
    assert kept.version == "3.0"  # the Word copy's version, as the PDF name has none


def test_collapse_duplicates_restores_title_shortened_by_docusign() -> None:
    pdf = _doc("CO-SOP-004_Filing_of_Electronic_Study_Documen.pdf")
    word = _doc(
        "CO-SOP-004 Filing of Electronic Study Documents_1.0.docx", "SOPs/Approved/Word_Documents_DoNotEdit"
    )
    [kept] = collapse_duplicates([pdf, word])
    assert kept.file_name.endswith(".pdf")
    assert kept.title == "Filing of Electronic Study Documents"


def test_docusign_copy_is_used_when_it_is_the_only_signed_pdf() -> None:
    signed = _doc("Complete_with_Docusign_PM-SOP-002_Quality_Ri.pdf")
    word = _doc(
        "PM-SOP-002_Quality Risk Management in Clinical Trials_3.0.docx",
        "SOPs/Approved/Word_Documents_DoNotEdit",
    )
    [kept] = collapse_duplicates([word, signed])
    assert kept.file_name == "Complete_with_Docusign_PM-SOP-002_Quality_Ri.pdf"
    assert kept.title == "Quality Risk Management in Clinical Trials"  # full title from the Word copy
    assert kept.version == "3.0"


def test_word_copy_is_kept_alongside_the_signed_pdf() -> None:
    pdf = _doc("CO-008-A_Master_Accountability_Log_2.0.pdf")
    word = _doc("CO-008-A Master Accountability Log_2.0.docx", "SOPs/Approved/Word_Documents_DoNotEdit")
    superseded_word = _doc("CO-008-A Master Accountability Log_1.0.docx", "SOPs/Approved/Superseded")
    kept = {d.status: d for d in collapse_duplicates([pdf, word, superseded_word])}[SopStatus.EFFECTIVE]
    assert kept.file_name == pdf.file_name
    assert kept.editable_copy is not None and kept.editable_copy.file_name == word.file_name
    # Only a Word copy filed: it is the document itself, nothing extra to attach.
    [only_word] = collapse_duplicates([word])
    assert only_word.editable_copy is None


def test_plainly_named_signed_pdf_is_preferred_over_the_docusign_download() -> None:
    plain = _doc("CO-SOP-004_Filing_of_Electronic_Study_Documents_2.0.pdf")
    docusign = _doc("Complete_with_Docusign_CO-SOP-004_Filing_of_.pdf")
    [kept] = collapse_duplicates([docusign, plain])
    assert kept.file_name == plain.file_name


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
