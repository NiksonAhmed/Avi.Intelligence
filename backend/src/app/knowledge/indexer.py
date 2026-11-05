"""Builds the knowledge index from Effective SOPs and serves a cached BM25 index per tenant."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.connectors.sharepoint.models import SopConnector, SopDocument, SopStatus

from .extraction import MAX_FILE_BYTES, UnsupportedDocument, chunk_sections, extract_sections
from .models import KnowledgeChunk, KnowledgeDocument
from .search import Bm25Index, Passage

log = logging.getLogger(__name__)


@dataclass
class IndexResult:
    indexed: int = 0
    unchanged: int = 0
    removed: int = 0
    failed: list[dict[str, str]] = field(default_factory=list)


def _naive_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo else value


async def _read_file(connector: SopConnector, sop: SopDocument) -> tuple[bytes, str, str]:
    download = await connector.download(sop.id)
    if download is None:
        raise UnsupportedDocument("Document is no longer available.")
    data = bytearray()
    async for chunk in download.content:
        data.extend(chunk)
        if len(data) > MAX_FILE_BYTES:
            raise UnsupportedDocument("File is larger than 25 MB.")
    return bytes(data), download.file_name, download.content_type


async def index_sops(db: Session, connector: SopConnector, tenant_id: str) -> IndexResult:
    """Indexes Effective SOPs only. Drafts, in-review and superseded SOPs are never given to the AI."""
    result = IndexResult()
    source = "demo" if connector.info().mode == "mock" else "sharepoint"
    listing = await connector.list_sops()
    effective = {d.id: d for d in listing.documents if d.status == SopStatus.EFFECTIVE}

    existing = {
        d.external_id: d
        for d in db.scalars(select(KnowledgeDocument).where(KnowledgeDocument.tenant_id == tenant_id))
    }

    for external_id, kd in existing.items():
        if external_id not in effective or kd.source != source:
            db.delete(kd)
            result.removed += 1
    db.flush()

    for sop in effective.values():
        current = existing.get(sop.id)
        if (
            current is not None
            and current.source == source
            and current.error is None
            and current.version == sop.version
            and _naive_utc(current.source_modified_at) == _naive_utc(sop.modified_at)
        ):
            result.unchanged += 1
            continue
        if current is not None and current in db:
            db.delete(current)
            db.flush()

        doc = KnowledgeDocument(
            tenant_id=tenant_id,
            source=source,
            external_id=sop.id,
            sop_number=sop.sop_number,
            title=sop.title,
            version=sop.version,
            status=sop.status.value,
            web_url=sop.web_url,
            source_modified_at=sop.modified_at,
        )
        try:
            data, file_name, content_type = await _read_file(connector, sop)
            chunks = chunk_sections(extract_sections(data, file_name, content_type))
            doc.chunks = [
                KnowledgeChunk(position=i, section=c.section, text=c.text) for i, c in enumerate(chunks)
            ]
            doc.chunk_count = len(chunks)
            result.indexed += 1
        except UnsupportedDocument as exc:
            doc.error = str(exc)[:500]
            result.failed.append({"sop": sop.sop_number or sop.title, "reason": str(exc)})
        db.add(doc)
        db.flush()

    db.commit()
    log.info(
        "knowledge.indexed",
        extra={
            "indexed": result.indexed,
            "unchanged": result.unchanged,
            "removed": result.removed,
            "failed": len(result.failed),
            "tenant": tenant_id,
        },
    )
    return result


@dataclass
class IndexStats:
    documents: int
    passages: int
    failed: int
    last_indexed_at: datetime | None


def index_stats(db: Session, tenant_id: str) -> IndexStats:
    docs = db.execute(
        select(
            func.count(KnowledgeDocument.id),
            func.coalesce(func.sum(KnowledgeDocument.chunk_count), 0),
            func.max(KnowledgeDocument.indexed_at),
        ).where(KnowledgeDocument.tenant_id == tenant_id)
    ).one()
    failed = db.scalar(
        select(func.count(KnowledgeDocument.id)).where(
            KnowledgeDocument.tenant_id == tenant_id, KnowledgeDocument.error.is_not(None)
        )
    )
    return IndexStats(documents=docs[0], passages=int(docs[1]), failed=failed or 0, last_indexed_at=docs[2])


_cache: dict[str, tuple[tuple[int, int, str], Bm25Index]] = {}
_cache_lock = Lock()


def get_search_index(db: Session, tenant_id: str) -> Bm25Index:
    """Returns a cached BM25 index, rebuilt whenever the tenant's indexed content changes."""
    stats = index_stats(db, tenant_id)
    signature = (stats.documents, stats.passages, str(stats.last_indexed_at))
    with _cache_lock:
        cached = _cache.get(tenant_id)
        if cached and cached[0] == signature:
            return cached[1]
    rows = db.execute(
        select(KnowledgeChunk, KnowledgeDocument)
        .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
        .where(KnowledgeDocument.tenant_id == tenant_id)
    ).all()
    passages = [
        Passage(
            chunk_id=chunk.id,
            document_id=doc.id,
            position=chunk.position,
            section=chunk.section,
            text=chunk.text,
            title=doc.title,
            sop_number=doc.sop_number,
        )
        for chunk, doc in rows
    ]
    index = Bm25Index(passages)
    with _cache_lock:
        _cache[tenant_id] = (signature, index)
    return index
