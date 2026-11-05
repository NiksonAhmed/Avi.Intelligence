"""SOP endpoints (Documents and Knowledge > SOPs)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.audit.service import record_event
from app.auth.rbac import CurrentUser, Permission, require
from app.connectors.sharepoint import get_sop_connector
from app.connectors.sharepoint.models import (
    ConnectorInfo,
    SopConnector,
    SopDocument,
    SopStatus,
    SopVersion,
)
from app.db.session import get_db

router = APIRouter(prefix="/sops", tags=["SOPs"])

REVIEW_WINDOW_DAYS = 30

# driveItem ids are alphanumeric (SharePoint) or contain "!" (OneDrive); demo ids use "-".
SopId = Annotated[str, Path(pattern=r"^[A-Za-z0-9!_\-]{1,200}$")]
Connector = Annotated[SopConnector, Depends(get_sop_connector)]


class SopSummary(BaseModel):
    total: int
    effective: int
    in_review_or_draft: int
    review_due: int
    """Effective SOPs whose review date is past or within the next 30 days."""


class SopSource(BaseModel):
    mode: str
    mock_reason: str | None
    site_url: str | None
    library: str
    folder: str | None


class SopListResponse(BaseModel):
    documents: list[SopDocument]
    total_unfiltered: int
    summary: SopSummary
    departments: list[str]
    fetched_at: datetime
    from_cache: bool
    source: SopSource


class SopDetailResponse(BaseModel):
    document: SopDocument
    versions: list[SopVersion]
    review_due: bool
    source: SopSource


def _source(info: ConnectorInfo) -> SopSource:
    return SopSource(
        mode=info.mode,
        mock_reason=info.mock_reason,
        site_url=info.site_url,
        library=info.library,
        folder=info.folder,
    )


def is_review_due(doc: SopDocument, now: datetime | None = None) -> bool:
    if doc.status != SopStatus.EFFECTIVE or doc.review_date is None:
        return False
    now = now or datetime.now(UTC)
    review = doc.review_date if doc.review_date.tzinfo else doc.review_date.replace(tzinfo=UTC)
    return review <= now + timedelta(days=REVIEW_WINDOW_DAYS)


def filter_sops(
    docs: list[SopDocument],
    q: str | None,
    status: SopStatus | None,
    department: str | None,
) -> list[SopDocument]:
    terms = [t for t in (q or "").lower().split() if t]
    result = []
    for doc in docs:
        if status and doc.status != status:
            continue
        if department and (doc.department or "").lower() != department.lower():
            continue
        haystack = " ".join(
            filter(None, [doc.sop_number, doc.title, doc.file_name, doc.department, doc.owner])
        ).lower()
        if all(t in haystack for t in terms):
            result.append(doc)
    return result


@router.get("", response_model=SopListResponse)
async def list_sops(
    connector: Connector,
    _user: Annotated[CurrentUser, Depends(require(Permission.SOP_READ))],
    q: Annotated[str | None, Query(max_length=200)] = None,
    status: SopStatus | None = None,
    department: Annotated[str | None, Query(max_length=200)] = None,
) -> SopListResponse:
    result = await connector.list_sops()
    docs = result.documents
    now = datetime.now(UTC)
    summary = SopSummary(
        total=len(docs),
        effective=sum(d.status == SopStatus.EFFECTIVE for d in docs),
        in_review_or_draft=sum(d.status in (SopStatus.IN_REVIEW, SopStatus.DRAFT) for d in docs),
        review_due=sum(is_review_due(d, now) for d in docs),
    )
    return SopListResponse(
        documents=filter_sops(docs, q, status, department),
        total_unfiltered=len(docs),
        summary=summary,
        departments=sorted({d.department for d in docs if d.department}),
        fetched_at=result.fetched_at,
        from_cache=result.from_cache,
        source=_source(connector.info()),
    )


@router.post("/refresh", status_code=204)
async def refresh_sops(
    connector: Connector,
    _user: Annotated[CurrentUser, Depends(require(Permission.SOP_READ))],
) -> None:
    connector.clear_cache()
    await connector.list_sops(force_refresh=True)


@router.get("/{sop_id}", response_model=SopDetailResponse)
async def get_sop(
    sop_id: SopId,
    connector: Connector,
    _user: Annotated[CurrentUser, Depends(require(Permission.SOP_READ))],
) -> SopDetailResponse:
    doc = await connector.get_sop(sop_id)
    if not doc:
        raise HTTPException(404, "SOP not found.")
    versions = await connector.list_versions(sop_id)
    return SopDetailResponse(
        document=doc, versions=versions, review_due=is_review_due(doc), source=_source(connector.info())
    )


def content_disposition(file_name: str) -> str:
    """RFC 6266 attachment header with an ASCII fallback and UTF-8 filename*."""
    ascii_name = "".join(c if 32 <= ord(c) < 127 and c not in '"\\' else "_" for c in file_name)
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(file_name, safe='')}"


@router.get("/{sop_id}/download")
async def download_sop(
    sop_id: SopId,
    request: Request,
    connector: Connector,
    user: Annotated[CurrentUser, Depends(require(Permission.SOP_DOWNLOAD))],
    db: Annotated[Session, Depends(get_db)],
) -> StreamingResponse:
    doc = await connector.get_sop(sop_id)
    download = await connector.download(sop_id) if doc else None
    if not doc or not download:
        raise HTTPException(404, "SOP not found.")
    record_event(
        db,
        user,
        action="sop.downloaded",
        entity_type="sop",
        entity_id=sop_id,
        summary=f"Downloaded {doc.sop_number or ''} {doc.title} (version {doc.version or 'unknown'})".strip(),
        details={
            "file_name": doc.file_name,
            "version": doc.version,
            "status": doc.status.value,
            "source": connector.info().mode,
        },
        request=request,
    )
    headers = {
        "Content-Disposition": content_disposition(download.file_name),
        "Cache-Control": "no-store",
    }
    if download.size_bytes is not None:
        headers["Content-Length"] = str(download.size_bytes)
    return StreamingResponse(download.content, media_type=download.content_type, headers=headers)
