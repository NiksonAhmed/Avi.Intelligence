"""Study data.

Two kinds of table live here:
  * Synced from SimpleTrials (studies, study_sites, study_milestones, connector_syncs): read-only in
    Avi.Intelligence. Rows carry `source`, `external_id` and `synced_at` so every value can be traced.
  * Managed in Avi.Intelligence (tasks, risks). Tasks are assigned by Admin, Project Managers and QA
    (by category) or created by anyone for themselves; each assigned person updates their own status.
    A task belongs to a category: a study, approved SOPs/forms, a vendor, a computer system, or general.
    Every change is written to the audit trail.
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
    enrolled: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sandbox: Mapped[bool] = mapped_column(Boolean, default=False)
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
    activation_target: Mapped[date | None] = mapped_column(Date, nullable=True)
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
    baseline_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    percent_complete: Mapped[int | None] = mapped_column(Integer, nullable=True)
    phase: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Full CTMS plan: phases, tasks and milestones in SimpleTrials order (position).
    kind: Mapped[str] = mapped_column(String(16), default="milestone", server_default="milestone")
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    baseline_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    parent_external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    system_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_key: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")

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
    # study | sop | vendor | system | general (see TaskCategory). Existing tasks are study tasks.
    category: Mapped[str] = mapped_column(String(16), default="study", server_default="study", index=True)
    # Study tasks only.
    study_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("studies.id"), index=True, nullable=True
    )
    # Vendor / computer system tasks: the name as typed (no managed list yet).
    subject_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Optional link to an entry of the study plan (SimpleTrials task/milestone id, stable across syncs).
    # The name is a snapshot so the link stays readable even if the plan entry later disappears.
    plan_item_external_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    plan_item_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Overall status, derived from the assigned people's statuses (see overall_task_status), or
    # "Cancelled" when a manager cancels the whole task. Stored so lists can filter on it.
    status: Mapped[str] = mapped_column(String(32))
    created_by_id: Mapped[str] = mapped_column(String(255))
    created_by_name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    study: Mapped[Study | None] = relationship()
    documents: Mapped[list[TaskDocument]] = relationship(
        back_populates="task", cascade="all, delete-orphan", order_by="TaskDocument.position"
    )
    assignees: Mapped[list[TaskAssignee]] = relationship(
        back_populates="task", cascade="all, delete-orphan", order_by="TaskAssignee.position"
    )


class TaskAssignee(Base):
    """A person a task is assigned to, with their own status (e.g. 5 of 8 have read the SOP)."""

    __tablename__ = "task_assignees"
    __table_args__ = (Index("uq_task_assignee", "task_id", "person_id", unique=True),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("tasks.id"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    person_id: Mapped[str] = mapped_column(String(255), index=True)
    person_name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    task: Mapped[Task] = relationship(back_populates="assignees")


class TaskDocument(Base):
    """An approved SOP or form a Procedures and SOPs task is about.

    Number, title and version are a snapshot taken when the task is raised, so the task still reads
    "Review CO-SOP-005 v2.0" after v3.0 is approved or the file moves in SharePoint.
    """

    __tablename__ = "task_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("tasks.id"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    sop_id: Mapped[str] = mapped_column(String(200), index=True)  # SharePoint drive item id
    kind: Mapped[str] = mapped_column(String(16))  # sop | form
    sop_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(300))
    version: Mapped[str | None] = mapped_column(String(32), nullable=True)

    task: Mapped[Task] = relationship(back_populates="documents")


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
