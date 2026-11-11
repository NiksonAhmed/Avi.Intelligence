"""Keeps report history up to date after each SimpleTrials sync.

- Milestone completions: the first time a milestone is seen complete, its completion date is recorded
  (the source's actual date when it has one, otherwise the day it was first seen at 100%).
- Daily snapshot: one small record of key figures per day, so trends can be drawn later.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.studies.models import Study

from .models import MilestoneCompletion, ReportSnapshot

STUDY_DELIVERY = "study-delivery"


def _is_complete(actual: date | None, percent: int | None) -> bool:
    return actual is not None or (percent is not None and percent >= 100)


def _seen_incomplete(db: Session, tenant_id: str, source: str) -> set[tuple[str, str]]:
    """(study id, milestone id) pairs that the latest snapshot recorded as not yet complete."""
    latest = db.scalars(
        select(ReportSnapshot)
        .where(
            ReportSnapshot.tenant_id == tenant_id,
            ReportSnapshot.kind == STUDY_DELIVERY,
            ReportSnapshot.source == source,
        )
        .order_by(ReportSnapshot.day.desc())
        .limit(1)
    ).first()
    if latest is None:
        return set()
    return {
        (s["id"], m["id"])
        for s in latest.data.get("studies", [])
        for m in s.get("milestones", [])
        if not (m.get("percent") is not None and m["percent"] >= 100)
    }


def record_completions(db: Session, tenant_id: str, source: str, today: date) -> int:
    """Records newly completed milestones. Returns how many were recorded.

    A completion date is only recorded when it is known: the source's actual date, or today when an
    earlier snapshot saw the milestone incomplete. A milestone already complete when tracking began is
    recorded without a date ("before-tracking") and is left out of on-time figures.
    """
    studies = db.scalars(
        select(Study)
        .where(Study.tenant_id == tenant_id, Study.source == source)
        .options(selectinload(Study.milestones))
    ).all()
    known = {
        (c.study_id, c.milestone_external_id)
        for c in db.scalars(select(MilestoneCompletion).where(MilestoneCompletion.tenant_id == tenant_id))
    }
    was_open = _seen_incomplete(db, tenant_id, source)
    added = 0
    for study in studies:
        for m in study.milestones:
            if m.kind == "phase" or not _is_complete(m.actual_date, m.percent_complete):
                continue
            if (study.id, m.external_id) in known:
                continue
            if m.actual_date:
                completed_on, basis = m.actual_date, "actual"
            elif (study.id, m.external_id) in was_open:
                completed_on, basis = today, "first-seen"
            else:
                completed_on, basis = None, "before-tracking"
            db.add(
                MilestoneCompletion(
                    tenant_id=tenant_id,
                    study_id=study.id,
                    milestone_external_id=m.external_id,
                    completed_on=completed_on,
                    basis=basis,
                )
            )
            added += 1
    db.commit()
    return added


def _study_delivery_data(studies: list[Study]) -> dict[str, Any]:
    def iso(d: date | None) -> str | None:
        return d.isoformat() if d else None

    return {
        "studies": [
            {
                "id": s.id,
                "protocol": s.protocol_number,
                "enrolled": s.enrolled,
                "target": s.enrolment_target,
                "milestones": [
                    {
                        "id": m.external_id,
                        "name": m.name,
                        "current": iso(m.planned_date),
                        "original": iso(m.baseline_date),
                        "percent": m.percent_complete,
                    }
                    for m in s.milestones
                    if m.is_key and m.kind == "milestone"
                ],
                "sites": [
                    {
                        "number": site.site_number,
                        "enrolled": site.enrolled,
                        "target": site.enrolment_target,
                        "activated": iso(site.activation_date),
                        "activation_target": iso(site.activation_target),
                    }
                    for site in s.sites
                ],
            }
            for s in studies
        ]
    }


def take_daily_snapshot(db: Session, tenant_id: str, source: str, today: date) -> bool:
    """Saves today's study-delivery figures once per day. Returns True when a snapshot was taken."""
    exists = db.scalars(
        select(ReportSnapshot.id).where(
            ReportSnapshot.tenant_id == tenant_id,
            ReportSnapshot.kind == STUDY_DELIVERY,
            ReportSnapshot.source == source,
            ReportSnapshot.day == today,
        )
    ).first()
    if exists:
        return False
    studies = list(
        db.scalars(
            select(Study)
            .where(Study.tenant_id == tenant_id, Study.source == source, Study.in_source.is_(True))
            .options(selectinload(Study.milestones), selectinload(Study.sites))
            .order_by(Study.protocol_number)
        )
    )
    db.add(
        ReportSnapshot(
            tenant_id=tenant_id,
            kind=STUDY_DELIVERY,
            source=source,
            day=today,
            data=_study_delivery_data(studies),
        )
    )
    db.commit()
    return True


def snapshot_days(db: Session, tenant_id: str, source: str, kind: str = STUDY_DELIVERY) -> int:
    return len(
        db.scalars(
            select(ReportSnapshot.day).where(
                ReportSnapshot.tenant_id == tenant_id,
                ReportSnapshot.kind == kind,
                ReportSnapshot.source == source,
            )
        ).all()
    )
