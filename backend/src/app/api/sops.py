"""SOP endpoints (Documents and Knowledge > SOPs)."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal
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
    DocumentDetails,
    DocumentKind,
    SopConnector,
    SopDocument,
    SopStatus,
)
from app.db.session import get_db, new_session
from app.knowledge.indexer import document_details_by_id, is_current, refresh_index

log = logging.getLogger(__name__)
router = APIRouter(prefix="/sops", tags=["SOPs"])

REVIEW_WINDOW_DAYS = 30

# driveItem ids are alphanumeric (SharePoint) or contain "!" (OneDrive); demo ids use "-".
SopId = Annotated[str, Path(pattern=r"^[A-Za-z0-9!_\-]{1,200}$")]
Connector = Annotated[SopConnector, Depends(get_sop_connector)]


class SopSummary(BaseModel):
    total: int
    """SOPs only (forms and templates are counted separately)."""
    forms: int
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
    approved_only: bool
    """Only approved documents are listed; drafts and superseded versions are never shown."""


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
    forms: list[SopDocument]
    """For an SOP: its forms and templates (by numbering, e.g. CO-005-A under CO-SOP-005)."""
    parent: SopDocument | None
    """For a form or template: the SOP it belongs to, when that SOP is in the library."""
    review_due: bool
    source: SopSource


def _source(info: ConnectorInfo) -> SopSource:
    return SopSource(
        mode=info.mode,
        mock_reason=info.mock_reason,
        site_url=info.site_url,
        library=info.library,
        folder=info.folder,
        approved_only=info.approved_only,
    )


def is_review_due(doc: SopDocument, now: datetime | None = None) -> bool:
    if doc.status != SopStatus.EFFECTIVE or doc.review_date is None:
        return False
    now = now or datetime.now(UTC)
    review = doc.review_date if doc.review_date.tzinfo else doc.review_date.replace(tzinfo=UTC)
    return review <= now + timedelta(days=REVIEW_WINDOW_DAYS)


def _as_datetime(value: date | None) -> datetime | None:
    return datetime(value.year, value.month, value.day, tzinfo=UTC) if value else None


def with_document_details(doc: SopDocument, details: DocumentDetails | None) -> SopDocument:
    """Adds what the document itself states (cover page, change history).

    Precedence: SharePoint column > the document's cover page > the file name. When the file name
    states a different version than the document, the file name's version is kept for display.
    """
    if details is None or details.is_empty():
        return doc
    update: dict[str, object] = {"details": details}
    if details.version and doc.version_source != "column":
        if doc.version and doc.version != details.version:
            update["file_name_version"] = doc.version
        update["version"] = details.version
        update["version_source"] = "document"
    if doc.effective_date is None and details.effective_date:
        update["effective_date"] = _as_datetime(details.effective_date)
    if doc.review_date is None and details.review_date:
        update["review_date"] = _as_datetime(details.review_date)
    return doc.model_copy(update=update)


def _with_details(
    docs: list[SopDocument], db: Session, user: CurrentUser, info: ConnectorInfo
) -> list[SopDocument]:
    source = "demo" if info.mode == "mock" else "sharepoint"
    found = document_details_by_id(db, user.tenant_id, source)

    def current_details(doc: SopDocument) -> DocumentDetails | None:
        # Only what was read from the file as it is now: after a change in SharePoint the old
        # reading is not shown (the file is re-read in the background).
        stored = found.get(doc.id)
        return stored[0] if stored and is_current(stored[1], doc) else None

    return [with_document_details(d, current_details(d)) for d in docs]


_background: set[asyncio.Task[None]] = set()


async def _reread_changed_files(connector: SopConnector, tenant_id: str) -> None:
    db = new_session()
    try:
        result = await refresh_index(db, connector, tenant_id)
        if result.indexed or result.removed:
            log.info("sops.reread", extra={"indexed": result.indexed, "removed": result.removed})
    except Exception:  # background work must never break the page; the next refresh retries
        log.exception("sops.reread_failed")
    finally:
        db.close()


def reread_in_background(connector: SopConnector, tenant_id: str) -> None:
    """After a fresh SharePoint listing, re-read new or changed SOP files (live SharePoint only)."""
    if connector.info().mode != "live":
        return
    task = asyncio.get_running_loop().create_task(_reread_changed_files(connector, tenant_id))
    _background.add(task)
    task.add_done_callback(_background.discard)


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
    user: Annotated[CurrentUser, Depends(require(Permission.SOP_READ))],
    db: Annotated[Session, Depends(get_db)],
    q: Annotated[str | None, Query(max_length=200)] = None,
    status: SopStatus | None = None,
    department: Annotated[str | None, Query(max_length=200)] = None,
) -> SopListResponse:
    result = await connector.list_sops()
    if not result.from_cache:
        reread_in_background(connector, user.tenant_id)
    docs = _with_details(result.documents, db, user, connector.info())
    sops = [d for d in docs if d.kind == DocumentKind.SOP]
    now = datetime.now(UTC)
    summary = SopSummary(
        total=len(sops),
        forms=len(docs) - len(sops),
        effective=sum(d.status == SopStatus.EFFECTIVE for d in sops),
        in_review_or_draft=sum(d.status in (SopStatus.IN_REVIEW, SopStatus.DRAFT) for d in sops),
        review_due=sum(is_review_due(d, now) for d in sops),
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
    user: Annotated[CurrentUser, Depends(require(Permission.SOP_READ))],
) -> None:
    connector.clear_cache()
    await connector.list_sops(force_refresh=True)
    reread_in_background(connector, user.tenant_id)


@router.get("/{sop_id}", response_model=SopDetailResponse)
async def get_sop(
    sop_id: SopId,
    connector: Connector,
    user: Annotated[CurrentUser, Depends(require(Permission.SOP_READ))],
    db: Annotated[Session, Depends(get_db)],
) -> SopDetailResponse:
    found = await connector.get_sop(sop_id)
    if not found:
        raise HTTPException(404, "SOP not found.")
    docs = _with_details((await connector.list_sops()).documents, db, user, connector.info())
    doc = next((d for d in docs if d.id == sop_id), found)
    forms = (
        [d for d in docs if d.kind == DocumentKind.FORM and d.parent_sop_number == doc.sop_number]
        if doc.kind == DocumentKind.SOP and doc.sop_number
        else []
    )
    parent = (
        next(
            (d for d in docs if d.kind == DocumentKind.SOP and d.sop_number == doc.parent_sop_number),
            None,
        )
        if doc.parent_sop_number
        else None
    )
    return SopDetailResponse(
        document=doc,
        forms=forms,
        parent=parent,
        review_due=is_review_due(doc),
        source=_source(connector.info()),
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
    file_format: Annotated[Literal["original", "word"], Query(alias="format")] = "original",
) -> StreamingResponse:
    """Downloads the document. format=word gives the Word copy of a form/template for filling in;
    SOPs themselves are only issued as filed (normally the signed PDF)."""
    doc = await connector.get_sop(sop_id)
    if not doc:
        raise HTTPException(404, "SOP not found.")
    word = file_format == "word"
    if word and doc.kind != DocumentKind.FORM:
        raise HTTPException(400, "Word copies are offered for forms and templates only.")
    if word and doc.editable_copy is None and doc.file_name.lower().endswith((".docx", ".doc")):
        word = False  # the filed form is already a Word document
    download = await connector.download(sop_id, editable=word)
    if not download:
        raise HTTPException(
            404, "No Word copy of this form is filed in SharePoint." if word else "SOP not found."
        )
    record_event(
        db,
        user,
        action="sop.downloaded",
        entity_type="sop",
        entity_id=sop_id,
        summary=(
            f"Downloaded {doc.sop_number or ''} {doc.title} (version {doc.version or 'unknown'})"
            f"{' as Word' if word else ''}"
        ).strip(),
        details={
            "file_name": download.file_name,
            "format": "word" if word else "original",
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
