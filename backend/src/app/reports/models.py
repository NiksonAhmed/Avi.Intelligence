"""History kept for reports: milestone completion dates and daily snapshots."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _now() -> datetime:
    return datetime.now(UTC)


def _uuid() -> str:
    return str(uuid.uuid4())


class MilestoneCompletion(Base):
    """When a milestone was completed.

    SimpleTrials' API gives no actual completion date, so the date a sync first sees the milestone at
    100% is recorded ("first-seen") — but only when an earlier snapshot saw it incomplete. A milestone
    already complete when tracking began has no known date ("before-tracking", completed_on None). A
    date the source does provide is used instead ("actual").
    """

    __tablename__ = "milestone_completions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    study_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("studies.id", ondelete="CASCADE"), index=True
    )
    milestone_external_id: Mapped[str] = mapped_column(String(255))
    completed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    basis: Mapped[str] = mapped_column(String(16))  # "actual" | "first-seen" | "before-tracking"
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (Index("ux_milestone_completions", "study_id", "milestone_external_id", unique=True),)


class ReportSnapshot(Base):
    """A small daily record of key figures, so trends can be shown (history starts when it is enabled)."""

    __tablename__ = "report_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(32))  # "study-delivery" (more kinds per report)
    source: Mapped[str] = mapped_column(String(32))  # "simpletrials" | "demo"
    day: Mapped[date] = mapped_column(Date)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (Index("ux_report_snapshots_day", "tenant_id", "kind", "source", "day", unique=True),)
