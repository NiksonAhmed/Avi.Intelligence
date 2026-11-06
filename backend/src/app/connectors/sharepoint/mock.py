"""Demo SOP connector used when SharePoint is not configured.

All records are clearly labelled demo data in the UI. Owners are role titles, not real people.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

from .demo_content import demo_text_for
from .mapping import DEFAULT_FIELD_MAP, sort_sops
from .models import (
    CheckStep,
    ConnectionCheck,
    ConnectorInfo,
    DocumentKind,
    EditableCopy,
    SopDocument,
    SopDownload,
    SopListResult,
    SopStatus,
    SopVersion,
    StatusSource,
)

_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

# (number, title, version, status, department, effective, review, owner)
_SAMPLES: list[tuple[str, str, str, SopStatus, str, str | None, str | None, str]] = [
    (
        "SOP-001",
        "Document Control and SOP Management",
        "4.0",
        SopStatus.EFFECTIVE,
        "Quality Assurance",
        "2024-02-01",
        "2026-02-01",
        "Head of Quality",
    ),
    (
        "SOP-002",
        "Training and Training Records",
        "3.0",
        SopStatus.EFFECTIVE,
        "Quality Assurance",
        "2024-05-15",
        "2026-05-15",
        "Head of Quality",
    ),
    (
        "SOP-010",
        "Feasibility and Site Selection",
        "2.0",
        SopStatus.EFFECTIVE,
        "Clinical Operations",
        "2024-08-01",
        "2026-08-01",
        "Director, Clinical Operations",
    ),
    (
        "SOP-011",
        "Site Activation",
        "3.0",
        SopStatus.EFFECTIVE,
        "Clinical Operations",
        "2025-01-20",
        "2027-01-20",
        "Director, Clinical Operations",
    ),
    (
        "SOP-012",
        "Site Monitoring Visits and Visit Reports",
        "5.0",
        SopStatus.EFFECTIVE,
        "Clinical Operations",
        "2025-03-10",
        "2027-03-10",
        "Clinical Operations Manager",
    ),
    (
        "SOP-013",
        "Informed Consent Process Oversight",
        "2.1",
        SopStatus.IN_REVIEW,
        "Clinical Operations",
        None,
        None,
        "Clinical Operations Manager",
    ),
    (
        "SOP-014",
        "Protocol Deviation Management",
        "2.0",
        SopStatus.EFFECTIVE,
        "Clinical Operations",
        "2024-11-04",
        "2026-11-04",
        "Clinical Operations Manager",
    ),
    (
        "SOP-015",
        "Trial Master File Management",
        "3.0",
        SopStatus.EFFECTIVE,
        "Clinical Operations",
        "2025-06-02",
        "2027-06-02",
        "TMF Lead",
    ),
    (
        "SOP-020",
        "Data Management Plan and Database Lock",
        "2.0",
        SopStatus.EFFECTIVE,
        "Data Management",
        "2024-09-16",
        "2026-09-16",
        "Head of Data Management",
    ),
    (
        "SOP-021",
        "Data Query Management",
        "0.3",
        SopStatus.DRAFT,
        "Data Management",
        None,
        None,
        "Head of Data Management",
    ),
    (
        "SOP-030",
        "Safety Reporting (SAE and SUSAR)",
        "4.0",
        SopStatus.EFFECTIVE,
        "Pharmacovigilance",
        "2025-04-07",
        "2027-04-07",
        "Head of Pharmacovigilance",
    ),
    (
        "SOP-031",
        "Reference Safety Information Management",
        "1.0",
        SopStatus.SUPERSEDED,
        "Pharmacovigilance",
        "2022-03-01",
        None,
        "Head of Pharmacovigilance",
    ),
    (
        "SOP-040",
        "Vendor Qualification and Oversight",
        "2.0",
        SopStatus.EFFECTIVE,
        "Quality Assurance",
        "2024-07-22",
        "2026-07-22",
        "Head of Quality",
    ),
    (
        "SOP-041",
        "Corrective and Preventive Action (CAPA) Management",
        "3.0",
        SopStatus.EFFECTIVE,
        "Quality Assurance",
        "2025-02-17",
        "2027-02-17",
        "Head of Quality",
    ),
    (
        "SOP-050",
        "Risk-Based Quality Management",
        "1.1",
        SopStatus.IN_REVIEW,
        "Clinical Operations",
        None,
        None,
        "Director, Clinical Operations",
    ),
]


# Demo forms/templates: (number, title, version, parent SOP number)
_FORMS: list[tuple[str, str, str, str]] = [
    ("SOP-011-A", "Site Initiation Visit Report Template", "3.0", "SOP-011"),
    ("SOP-011-B", "Delegation of Duties Log", "2.0", "SOP-011"),
    ("SOP-012-A", "Monitoring Visit Report Template", "5.0", "SOP-012"),
]


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value).replace(tzinfo=UTC) if value else None


def _build_documents() -> list[SopDocument]:
    docs: list[SopDocument] = []
    for number, title, version, status, dept, effective, review, owner in _SAMPLES:
        file_name = f"{number} {title} v{version}.docx"
        modified = _dt(effective) or datetime(2025, 9, 1, tzinfo=UTC)
        docs.append(
            SopDocument(
                id=f"demo-{number.lower()}",
                title=title,
                file_name=file_name,
                sop_number=number,
                version=version,
                status=status,
                status_source=StatusSource.COLUMN,
                effective_date=_dt(effective),
                review_date=_dt(review),
                owner=owner,
                department=dept,
                folder_path=f"SOPs/{dept}",
                modified_at=modified,
                modified_by="Demo data",
                web_url=None,
                size_bytes=48_000 + len(title) * 512,
                mime_type=_DOCX,
            )
        )
    parents = {d.sop_number: d for d in docs}
    for number, title, version, parent_number in _FORMS:
        parent = parents[parent_number]
        docs.append(
            parent.model_copy(
                update={
                    "id": f"demo-{number.lower()}",
                    "title": title,
                    # Like Avion's library: a signed PDF with an editable Word copy next to it.
                    "file_name": f"{number} {title} v{version}.pdf",
                    "mime_type": "application/pdf",
                    "sop_number": number,
                    "kind": DocumentKind.FORM,
                    "parent_sop_number": parent_number,
                    "version": version,
                    "review_date": None,
                    "size_bytes": 24_000 + len(title) * 256,
                    "editable_copy": EditableCopy(
                        id=f"demo-{number.lower()}-word",
                        file_name=f"{number} {title} v{version}.docx",
                        size_bytes=18_000 + len(title) * 256,
                        mime_type=_DOCX,
                    ),
                }
            )
        )
    return sort_sops(docs)


class MockSopConnector:
    def __init__(self, reason: str) -> None:
        self._reason = reason
        self._docs = _build_documents()

    def info(self) -> ConnectorInfo:
        return ConnectorInfo(
            mode="mock", mock_reason=self._reason, library="Demo SOP library", field_map=DEFAULT_FIELD_MAP
        )

    def clear_cache(self) -> None:
        return None

    async def list_sops(self, force_refresh: bool = False) -> SopListResult:
        return SopListResult(documents=list(self._docs), fetched_at=datetime.now(UTC), from_cache=False)

    async def get_sop(self, sop_id: str) -> SopDocument | None:
        return next((d for d in self._docs if d.id == sop_id), None)

    async def list_versions(self, sop_id: str) -> list[SopVersion]:
        doc = await self.get_sop(sop_id)
        if not doc or not doc.version:
            return []
        major = int(doc.version.split(".")[0])
        return [
            SopVersion(
                id=f"{v}.0", modified_at=doc.modified_at, modified_by="Demo data", size_bytes=doc.size_bytes
            )
            for v in range(max(major, 1), 0, -1)
        ]

    async def download(self, sop_id: str, editable: bool = False) -> SopDownload | None:
        doc = await self.get_sop(sop_id)
        if not doc or (editable and doc.editable_copy is None):
            return None
        text = demo_text_for(doc.sop_number, doc.title, doc.version).encode()

        async def body() -> AsyncIterator[bytes]:
            yield text

        name = doc.editable_copy.file_name if editable and doc.editable_copy else doc.file_name
        stem = name.rsplit(".", 1)[0]
        return SopDownload(
            content=body(),
            content_type="text/plain; charset=utf-8",
            file_name=f"{stem} (DEMO).txt",
            size_bytes=len(text),
        )

    async def test_connection(self) -> ConnectionCheck:
        return ConnectionCheck(
            ok=False,
            steps=[CheckStep(label="SharePoint configured", ok=False, detail=self._reason)],
            document_count=len(self._docs),
        )
