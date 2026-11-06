"""Public data shapes for the SharePoint SOP connector (also used as API response models)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Literal, Protocol

from pydantic import BaseModel


class SopStatus(StrEnum):
    EFFECTIVE = "Effective"
    IN_REVIEW = "In Review"
    DRAFT = "Draft"
    SUPERSEDED = "Superseded"
    RETIRED = "Retired"
    UNKNOWN = "Unknown"


class StatusSource(StrEnum):
    """Where a status came from, so users can judge how much to trust it."""

    COLUMN = "column"
    FOLDER = "folder"
    CONTENT_APPROVAL = "content-approval"
    VERSION_NUMBER = "version-number"
    NONE = "none"


class DocumentKind(StrEnum):
    """An SOP itself, or a form/template that belongs to an SOP (e.g. CO-005-A under CO-SOP-005)."""

    SOP = "sop"
    FORM = "form"
    OTHER = "other"


class RevisionEntry(BaseModel):
    """One row of the document's own change history table."""

    issued: date | None
    version: str
    changes: str


class DocumentDetails(BaseModel):
    """Document control details read from the document itself (cover page and change history)."""

    version: str | None = None
    effective_date: date | None = None
    review_date: date | None = None
    prepared_by: str | None = None
    prepared_date: date | None = None
    reviewed_by: str | None = None
    reviewed_date: date | None = None
    approved_by: str | None = None
    approved_date: date | None = None
    revisions: list[RevisionEntry] = []

    def is_empty(self) -> bool:
        return not any(v for v in self.model_dump().values())


class EditableCopy(BaseModel):
    """The Word copy filed next to a signed PDF (e.g. in "Word_Documents_DoNotEdit")."""

    id: str
    file_name: str
    size_bytes: int | None
    mime_type: str | None


class SopDocument(BaseModel):
    id: str
    title: str
    file_name: str
    sop_number: str | None
    kind: DocumentKind = DocumentKind.SOP
    parent_sop_number: str | None = None
    """For forms/templates: the SOP they belong to, when the numbering says so."""
    version: str | None
    status: SopStatus
    status_source: StatusSource
    effective_date: datetime | None
    review_date: datetime | None
    owner: str | None
    department: str | None
    folder_path: str
    modified_at: datetime | None
    modified_by: str | None
    web_url: str | None
    size_bytes: int | None
    mime_type: str | None
    details: DocumentDetails | None = None
    """Read from inside the document when it was indexed (approved SOPs only)."""
    version_source: Literal["column", "document", "file-name"] | None = None
    file_name_version: str | None = None
    """Set when the file name states a different version than the document itself."""
    editable_copy: EditableCopy | None = None
    """Word copy of the same document and status, offered as a download for forms/templates."""


class SopVersion(BaseModel):
    id: str
    modified_at: datetime | None
    modified_by: str | None
    size_bytes: int | None


class ConnectorColumn(BaseModel):
    name: str
    display_name: str
    type: str


class CheckStep(BaseModel):
    label: str
    ok: bool
    detail: str | None = None


class ConnectionCheck(BaseModel):
    ok: bool
    steps: list[CheckStep]
    columns: list[ConnectorColumn] | None = None
    document_count: int | None = None


class ConnectorInfo(BaseModel):
    mode: Literal["live", "mock"]
    mock_reason: str | None = None
    site_url: str | None = None
    library: str
    folder: str | None = None
    approved_only: bool = False
    field_map: dict[str, list[str]]


class SopListResult(BaseModel):
    documents: list[SopDocument]
    fetched_at: datetime
    from_cache: bool


@dataclass
class SopDownload:
    content: AsyncIterator[bytes]
    content_type: str
    file_name: str
    size_bytes: int | None


class SopConnector(Protocol):
    def info(self) -> ConnectorInfo: ...

    async def list_sops(self, force_refresh: bool = False) -> SopListResult: ...

    async def get_sop(self, sop_id: str) -> SopDocument | None:
        """Returns None if the id is not an SOP within the configured library/folder."""
        ...

    async def list_versions(self, sop_id: str) -> list[SopVersion]: ...

    async def download(self, sop_id: str, editable: bool = False) -> SopDownload | None:
        """The listed document's file, or with editable=True its Word copy (None if it has none)."""
        ...

    async def test_connection(self) -> ConnectionCheck: ...

    def clear_cache(self) -> None: ...
