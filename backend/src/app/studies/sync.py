"""Copy SimpleTrials records into the local database.

SimpleTrials stays the system of record: this only inserts/updates our read-only copy. Studies that
disappear from the source are flagged (`in_source = False`) rather than deleted, so tasks and risks
linked to them are never lost. Sites and milestones are replaced to mirror the source exactly.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.simpletrials.models import StudyConnector
from app.core.logging import redact

from .models import ConnectorSync, Study, StudyMilestone, StudySite

log = logging.getLogger("studies.sync")

CONNECTOR_NAME = "simpletrials"


def _source_label(mode: str) -> str:
    return "demo" if mode == "mock" else CONNECTOR_NAME


async def sync_studies(
    db: Session, connector: StudyConnector, *, tenant_id: str, triggered_by: str
) -> ConnectorSync:
    mode = connector.info().mode
    run = ConnectorSync(tenant_id=tenant_id, connector=CONNECTOR_NAME, mode=mode, triggered_by=triggered_by)
    db.add(run)
    db.commit()
    try:
        records = await connector.fetch_studies()
    except Exception as exc:  # report the failure on screen; keep the previous copy untouched
        run.finished_at = datetime.now(UTC)
        run.error = redact(str(exc))[:1000]
        db.commit()
        log.warning("simpletrials.sync_failed", extra={"error": run.error})
        return run

    source = _source_label(mode)
    now = datetime.now(UTC)
    existing = {
        s.external_id: s
        for s in db.scalars(select(Study).where(Study.tenant_id == tenant_id, Study.source == source))
    }
    created = updated = 0
    seen: set[str] = set()
    for rec in records:
        seen.add(rec.external_id)
        study = existing.get(rec.external_id)
        if study is None:
            study = Study(tenant_id=tenant_id, source=source, external_id=rec.external_id)
            db.add(study)
            created += 1
        else:
            updated += 1
        study.protocol_number = rec.protocol_number
        study.title = rec.title
        study.sponsor = rec.sponsor
        study.phase = rec.phase
        study.therapeutic_area = rec.therapeutic_area
        study.status = rec.status
        study.countries = list(rec.countries)
        study.project_manager = rec.project_manager
        study.enrolment_target = rec.enrolment_target
        study.enrolled = rec.enrolled
        study.sandbox = rec.sandbox
        study.in_source = True
        study.synced_at = now
        study.sites = [StudySite(**s.model_dump()) for s in rec.sites]
        study.milestones = [
            StudyMilestone(position=i, **m.model_dump()) for i, m in enumerate(rec.milestones)
        ]

    flagged = 0
    for ext_id, study in existing.items():
        if ext_id not in seen and study.in_source:
            study.in_source = False
            flagged += 1

    run.ok = True
    run.finished_at = datetime.now(UTC)
    run.counts = {
        "studies": len(records),
        "created": created,
        "updated": updated,
        "no_longer_in_source": flagged,
    }
    db.commit()
    log.info("simpletrials.synced", extra={"counts": run.counts})
    return run


def last_sync(
    db: Session, tenant_id: str, *, successful_only: bool = False, mode: str | None = None
) -> ConnectorSync | None:
    query = select(ConnectorSync).where(
        ConnectorSync.tenant_id == tenant_id, ConnectorSync.connector == CONNECTOR_NAME
    )
    if successful_only:
        query = query.where(ConnectorSync.ok.is_(True))
    if mode:
        query = query.where(ConnectorSync.mode == mode)
    return db.scalars(query.order_by(ConnectorSync.started_at.desc()).limit(1)).first()


async def ensure_synced(db: Session, connector: StudyConnector, tenant_id: str) -> None:
    """Run a first sync automatically (per mode, so switching demo → API also syncs once)."""
    mode = connector.info().mode
    if last_sync(db, tenant_id, successful_only=True, mode=mode) is None:
        await sync_studies(db, connector, tenant_id=tenant_id, triggered_by="system (first use)")
