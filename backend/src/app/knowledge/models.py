"""Knowledge index (SOP text split into sections) and assistant interaction log."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def _now() -> datetime:
    return datetime.now(UTC)


def _uuid() -> str:
    return str(uuid.uuid4())


class KnowledgeDocument(Base):
    """One indexed source document (currently: an Effective SOP)."""

    __tablename__ = "knowledge_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[str] = mapped_column(String(32))  # "sharepoint" | "demo"
    external_id: Mapped[str] = mapped_column(String(255))  # SharePoint driveItem id
    sop_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(500))
    version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32))
    web_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    source_modified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    # Document control details read from the document itself (cover page, change history);
    # see app.knowledge.document_details. None = not read yet.
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    indexed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    chunks: Mapped[list[KnowledgeChunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="KnowledgeChunk.position"
    )

    __table_args__ = (Index("ux_knowledge_documents_external", "tenant_id", "external_id", unique=True),)


class KnowledgeChunk(Base):
    """A passage of a document, the unit of retrieval and citation."""

    __tablename__ = "knowledge_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    section: Mapped[str] = mapped_column(String(300))
    text: Mapped[str] = mapped_column(Text)

    document: Mapped[KnowledgeDocument] = relationship(back_populates="chunks")


class AssistantInteraction(Base):
    """Every question and answer, kept for traceability (append-only)."""

    __tablename__ = "assistant_interactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    user_id: Mapped[str] = mapped_column(String(255))
    user_name: Mapped[str] = mapped_column(String(255))
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    mode: Mapped[str] = mapped_column(String(32))  # "ai" | "search-only"
    outcome: Mapped[str] = mapped_column(String(32))  # "answered" | "refused" | "no-sources" | "error"
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
