"""Public data shapes for the SharePoint SOP connector (also used as API response models)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
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
    CONTENT_APPROVAL = "content-approval"
    VERSION_NUMBER = "version-number"
    NONE = "none"


class SopDocument(BaseModel):
    id: str
    title: str
    file_name: str
    sop_number: str | None
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

    async def download(self, sop_id: str) -> SopDownload | None: ...

    async def test_connection(self) -> ConnectionCheck: ...

    def clear_cache(self) -> None: ...
