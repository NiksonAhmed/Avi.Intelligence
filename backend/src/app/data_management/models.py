"""Data Management tables (prefix dm_): a read-only copy of what Data Management needs from Viedoc.

Each sync replaces a connection's rows, so the copy mirrors Viedoc. Subject IDs only: no names, initials,
dates of birth or other demographics are stored. Every row carries its connection and environment
(sandbox or live), so sandbox and live data are never mixed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class DmSyncRun(Base):
    __tablename__ = "dm_sync_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    connection: Mapped[str] = mapped_column(String(64))
    environment: Mapped[str] = mapped_column(String(16))  # sandbox | live | demo
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ok: Mapped[bool] = mapped_column(Boolean, default=False)
    counts: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    triggered_by: Mapped[str] = mapped_column(String(255))


class DmQuery(Base):
    """One Viedoc query (current state), rebuilt from its history rows in the export."""

    __tablename__ = "dm_queries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    connection: Mapped[str] = mapped_column(String(64), index=True)
    environment: Mapped[str] = mapped_column(String(16))
    study_code: Mapped[str] = mapped_column(String(100))
    query_number: Mapped[str] = mapped_column(String(32))
    """Viedoc's query study sequence number."""
    site_code: Mapped[str] = mapped_column(String(64))
    site_name: Mapped[str] = mapped_column(String(300))
    subject_id: Mapped[str] = mapped_column(String(64), index=True)
    event_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    form_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    form_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    item_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    item_label: Mapped[str | None] = mapped_column(String(300), nullable=True)
    query_type: Mapped[str] = mapped_column(String(64))
    raised_on: Mapped[str | None] = mapped_column(String(32), nullable=True)  # Item | Event date
    edit_check: Mapped[str | None] = mapped_column(String(200), nullable=True)
    query_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str] = mapped_column(String(32))  # open_at_site | awaiting_approval | closed
    viedoc_state: Mapped[str] = mapped_column(String(64))
    resolution: Mapped[str | None] = mapped_column(String(300), nullable=True)
    raised_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    state_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    """When the query entered its current state (the start of whoever's clock is running)."""
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reopen_count: Mapped[int] = mapped_column(Integer, default=0)
    answered_count: Mapped[int] = mapped_column(Integer, default=0)

    events: Mapped[list[DmQueryEvent]] = relationship(
        back_populates="query", cascade="all, delete-orphan", order_by="DmQueryEvent.position"
    )

    __table_args__ = (Index("ix_dm_queries_conn_state", "tenant_id", "connection", "state"),)


class DmQueryEvent(Base):
    """One history row of a query: a state change, when, and by which role (and user name)."""

    __tablename__ = "dm_query_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    query_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("dm_queries.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    viedoc_state: Mapped[str] = mapped_column(String(64))
    at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user_role: Mapped[str | None] = mapped_column(String(100), nullable=True)
    user_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resolution: Mapped[str | None] = mapped_column(String(300), nullable=True)

    query: Mapped[DmQuery] = relationship(back_populates="events")


class DmMissingItem(Base):
    """A field left blank and not yet confirmed as missing by the site (Viedoc: unconfirmed missing data),
    or a form waiting for a design upgrade (query type "Pending form upgrade")."""

    __tablename__ = "dm_missing_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    connection: Mapped[str] = mapped_column(String(64), index=True)
    site_code: Mapped[str] = mapped_column(String(64))
    site_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    subject_id: Mapped[str] = mapped_column(String(64))
    event_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    event_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    form_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    form_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    item_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    item_label: Mapped[str | None] = mapped_column(String(300), nullable=True)
    query_type: Mapped[str] = mapped_column(String(64))
    saved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    """When the form was saved with the field blank (the site's clock starts here)."""


class DmPendingForm(Base):
    """A form that is expected but not completed yet (Viedoc: pending forms)."""

    __tablename__ = "dm_pending_forms"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    connection: Mapped[str] = mapped_column(String(64), index=True)
    site_code: Mapped[str] = mapped_column(String(64))
    site_name: Mapped[str] = mapped_column(String(300))
    subject_id: Mapped[str] = mapped_column(String(64))
    event_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    form_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    form_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    pending_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DmFormStatus(Base):
    """One form at one visit (or the visit date itself): SDV progress (counted per field) and review,
    sign and lock status, from Viedoc's SDV and review status export files."""

    __tablename__ = "dm_form_status"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    connection: Mapped[str] = mapped_column(String(64), index=True)
    environment: Mapped[str] = mapped_column(String(16))
    study_code: Mapped[str] = mapped_column(String(100))
    site_code: Mapped[str] = mapped_column(String(64))
    site_name: Mapped[str] = mapped_column(String(300))
    subject_id: Mapped[str] = mapped_column(String(64), index=True)
    event_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    event_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    form_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    form_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    form_seq: Mapped[str | None] = mapped_column(String(32), nullable=True)
    kind: Mapped[str] = mapped_column(String(16))  # form | event_date
    sdv_required: Mapped[int] = mapped_column(Integer, default=0)
    sdv_done: Mapped[int] = mapped_column(Integer, default=0)
    last_sdv_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sdv_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    data_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    data_review_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    clinical_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    clinical_review_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    signed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


class DmLabResult(Base):
    """One expected lab result (analyte) on a lab form at one visit, kept as flags only (user decision):
    no result values and no normal-range numbers are stored, only what Data Management acts on."""

    __tablename__ = "dm_lab_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    connection: Mapped[str] = mapped_column(String(64), index=True)
    environment: Mapped[str] = mapped_column(String(16))
    study_code: Mapped[str] = mapped_column(String(100))
    site_code: Mapped[str] = mapped_column(String(64))
    site_name: Mapped[str] = mapped_column(String(300))
    subject_id: Mapped[str] = mapped_column(String(64), index=True)
    event_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    event_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    form_id: Mapped[str] = mapped_column(String(64))
    form_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    analyte: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16))  # reported | missing | not_done
    out_of_range: Mapped[str | None] = mapped_column(String(8), nullable=True)  # high | low
    unit_missing: Mapped[bool] = mapped_column(Boolean, default=False)
    range_missing: Mapped[bool] = mapped_column(Boolean, default=False)
    evaluation: Mapped[str | None] = mapped_column(String(16), nullable=True)
    """normal | abnormal_ncs | abnormal_cs | other | missing; None when the form has no evaluation."""
    cs_reference_missing: Mapped[bool] = mapped_column(Boolean, default=False)
