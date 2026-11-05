"""Study data.

Two kinds of table live here:
  * Synced from SimpleTrials (studies, study_sites, study_milestones, connector_syncs): read-only in
    Avi.Intelligence. Rows carry `source`, `external_id` and `synced_at` so every value can be traced.
  * Managed in Avi.Intelligence (tasks, risks): created by an administrator, status updated by the
    assigned person. Every change is written to the audit trail.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def _now() -> datetime:
    return datetime.now(UTC)


def _uuid() -> str:
    return str(uuid.uuid4())


class Study(Base):
    __tablename__ = "studies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[str] = mapped_column(String(32))  # "simpletrials" | "demo"
    external_id: Mapped[str] = mapped_column(String(255))
    protocol_number: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(500))
    sponsor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phase: Mapped[str | None] = mapped_column(String(32), nullable=True)
    therapeutic_area: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    countries: Mapped[list[str]] = mapped_column(JSON, default=list)
    project_manager: Mapped[str | None] = mapped_column(String(255), nullable=True)
    enrolment_target: Mapped[int | None] = mapped_column(Integer, nullable=True)
    in_source: Mapped[bool] = mapped_column(Boolean, default=True)
    """False when the study no longer appears in SimpleTrials (kept so linked tasks/risks survive)."""
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    sites: Mapped[list[StudySite]] = relationship(
        back_populates="study", cascade="all, delete-orphan", order_by="StudySite.site_number"
    )
    milestones: Mapped[list[StudyMilestone]] = relationship(
        back_populates="study", cascade="all, delete-orphan", order_by="StudyMilestone.position"
    )

    __table_args__ = (Index("ux_studies_external", "tenant_id", "source", "external_id", unique=True),)


class StudySite(Base):
    __tablename__ = "study_sites"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    study_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("studies.id", ondelete="CASCADE"), index=True
    )
    external_id: Mapped[str] = mapped_column(String(255))
    site_number: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(500))
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    principal_investigator: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    activation_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    enrolled: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enrolment_target: Mapped[int | None] = mapped_column(Integer, nullable=True)

    study: Mapped[Study] = relationship(back_populates="sites")


class StudyMilestone(Base):
    __tablename__ = "study_milestones"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    study_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("studies.id", ondelete="CASCADE"), index=True
    )
    external_id: Mapped[str] = mapped_column(String(255))
    position: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str] = mapped_column(String(255))
    planned_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    study: Mapped[Study] = relationship(back_populates="milestones")


class ConnectorSync(Base):
    """One run of a connector sync (append-only), shown as "last synced" on screens."""

    __tablename__ = "connector_syncs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    connector: Mapped[str] = mapped_column(String(64))
    mode: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ok: Mapped[bool] = mapped_column(Boolean, default=False)
    counts: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    triggered_by: Mapped[str] = mapped_column(String(255))


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    reference: Mapped[str] = mapped_column(String(32))  # human-readable, e.g. TSK-0007
    study_id: Mapped[str] = mapped_column(String(36), ForeignKey("studies.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    assignee_id: Mapped[str] = mapped_column(String(255), index=True)
    assignee_name: Mapped[str] = mapped_column(String(255))
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(32))
    created_by_id: Mapped[str] = mapped_column(String(255))
    created_by_name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    study: Mapped[Study] = relationship()


class Risk(Base):
    __tablename__ = "risks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    reference: Mapped[str] = mapped_column(String(32))  # e.g. RSK-0003 / ISS-0002
    study_id: Mapped[str] = mapped_column(String(36), ForeignKey("studies.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # "risk" | "issue"
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    likelihood: Mapped[int] = mapped_column(Integer)  # 1 low, 2 medium, 3 high (as entered)
    impact: Mapped[int] = mapped_column(Integer)
    mitigation: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[str] = mapped_column(String(255), index=True)
    owner_name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32))
    created_by_id: Mapped[str] = mapped_column(String(255))
    created_by_name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    study: Mapped[Study] = relationship()
