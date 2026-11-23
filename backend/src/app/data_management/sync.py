"""Copies what Data Management needs from Viedoc, one connection (study) at a time. Read-only.

Each run: start an export (queries with history and pending forms) -> wait -> download into memory ->
Viedoc's export file is deleted -> keep only the needed columns -> replace this connection's rows. The
file is never written to disk. If anything fails, the previous copy is kept and the error is recorded.
Without any Viedoc connection configured, a clearly labelled demo study is used instead.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.connectors.viedoc.client import ViedocClient
from app.core.config import Settings, ViedocConnectionSettings
from app.core.logging import redact
from app.db.session import new_session

from .demo import demo_export
from .export_reader import ExportData, read_export
from .models import (
    DmFormStatus,
    DmLabResult,
    DmMissingItem,
    DmPendingForm,
    DmQuery,
    DmQueryEvent,
    DmSyncRun,
)

log = logging.getLogger("data_management.sync")

DEMO_CONNECTION = "demo"
DEFAULT_TENANT = "avion"
EXPORT_OPTIONS: dict[str, Any] = {
    "outputFormat": "CSV",
    "includeQueries": True,
    "includeQueryHistory": True,
    "includePendingForms": True,
    # SDV (fields set up for SDV, done or pending) and review/sign/lock status per form.
    "includeSdv": True,
    "includeSDVPending": True,
    "includeSDVPerformedOrNA": True,
    "includeReviewStatus": True,
}

ClientFactory = Callable[[ViedocConnectionSettings, bool], ViedocClient]


def _default_client(connection: ViedocConnectionSettings, allow_live: bool) -> ViedocClient:
    return ViedocClient(connection, allow_live=allow_live)


def connections(settings: Settings) -> dict[str, str]:
    """Connection name -> environment. The demo study stands in when none is configured, or always
    when VIEDOC_MODE=mock (tests never reach a real Viedoc study)."""
    if settings.viedoc_mode == "mock":
        return {DEMO_CONNECTION: "demo"}
    configured: dict[str, str] = {name: c.environment for name, c in settings.viedoc_connections.items()}
    return configured or {DEMO_CONNECTION: "demo"}


def is_demo(settings: Settings) -> bool:
    return connections(settings) == {DEMO_CONNECTION: "demo"}


def _store(db: Session, tenant_id: str, name: str, environment: str, data: ExportData) -> None:
    old = db.scalars(select(DmQuery).where(DmQuery.tenant_id == tenant_id, DmQuery.connection == name)).all()
    for q in old:
        db.delete(q)  # cascades to its history rows
    db.execute(
        delete(DmMissingItem).where(DmMissingItem.tenant_id == tenant_id, DmMissingItem.connection == name)
    )
    db.execute(
        delete(DmPendingForm).where(DmPendingForm.tenant_id == tenant_id, DmPendingForm.connection == name)
    )
    db.execute(
        delete(DmFormStatus).where(DmFormStatus.tenant_id == tenant_id, DmFormStatus.connection == name)
    )
    db.execute(delete(DmLabResult).where(DmLabResult.tenant_id == tenant_id, DmLabResult.connection == name))
    db.flush()
    for r in data.queries:
        db.add(
            DmQuery(
                tenant_id=tenant_id,
                connection=name,
                environment=environment,
                study_code=data.study_code,
                query_number=r.number,
                site_code=r.site_code,
                site_name=r.site_name,
                subject_id=r.subject_id,
                event_id=r.event_id,
                event_name=r.event_name,
                form_id=r.form_id,
                form_name=r.form_name,
                item_id=r.item_id,
                item_label=r.item_label,
                query_type=r.query_type,
                raised_on=r.raised_on,
                edit_check=r.edit_check,
                query_text=r.query_text,
                state=r.state,
                viedoc_state=r.viedoc_state,
                resolution=r.resolution,
                raised_at=r.raised_at,
                state_since=r.state_since,
                closed_at=r.closed_at,
                reopen_count=r.reopen_count,
                answered_count=r.answered_count,
                events=[
                    DmQueryEvent(
                        position=i,
                        viedoc_state=e.viedoc_state,
                        at=e.at,
                        user_role=e.user_role,
                        user_name=e.user_name,
                        resolution=e.resolution,
                    )
                    for i, e in enumerate(r.events)
                ],
            )
        )
    for m in data.missing:
        db.add(
            DmMissingItem(
                tenant_id=tenant_id,
                connection=name,
                site_code=m.site_code,
                subject_id=m.subject_id,
                event_id=m.event_id,
                form_id=m.form_id,
                item_id=m.item_id,
                query_type=m.query_type,
                site_name=m.site_name,
                event_name=m.event_name,
                event_date=m.event_date,
                form_name=m.form_name,
                item_label=m.item_label,
                saved_at=m.saved_at,
            )
        )
    for lab in data.labs:
        db.add(
            DmLabResult(
                tenant_id=tenant_id,
                connection=name,
                environment=environment,
                study_code=data.study_code,
                site_code=lab.site_code,
                site_name=lab.site_name,
                subject_id=lab.subject_id,
                event_id=lab.event_id,
                event_name=lab.event_name,
                event_date=lab.event_date,
                form_id=lab.form_id,
                form_name=data.form_names.get(lab.form_id),
                analyte=lab.analyte,
                status=lab.status,
                out_of_range=lab.out_of_range,
                unit_missing=lab.unit_missing,
                range_missing=lab.range_missing,
                evaluation=lab.evaluation,
                cs_reference_missing=lab.cs_reference_missing,
            )
        )
    for f in data.forms:
        db.add(
            DmFormStatus(
                tenant_id=tenant_id,
                connection=name,
                environment=environment,
                study_code=data.study_code,
                site_code=f.site_code,
                site_name=f.site_name,
                subject_id=f.subject_id,
                event_id=f.event_id,
                event_name=f.event_name,
                event_date=f.event_date,
                form_id=f.form_id,
                form_name=f.form_name,
                form_seq=f.form_seq,
                kind=f.kind,
                sdv_required=f.sdv_required,
                sdv_done=f.sdv_done,
                last_sdv_at=f.last_sdv_at,
                last_sdv_by=f.last_sdv_by,
                data_review_at=f.data_review_at,
                data_review_by=f.data_review_by,
                clinical_review_at=f.clinical_review_at,
                clinical_review_by=f.clinical_review_by,
                signed_at=f.signed_at,
                signed_by=f.signed_by,
                locked_at=f.locked_at,
                locked_by=f.locked_by,
            )
        )
    for p in data.pending:
        db.add(
            DmPendingForm(
                tenant_id=tenant_id,
                connection=name,
                site_code=p.site_code,
                site_name=p.site_name,
                subject_id=p.subject_id,
                event_id=p.event_id,
                event_name=p.event_name,
                form_id=p.form_id,
                form_name=p.form_name,
                pending_since=p.pending_since,
            )
        )


async def sync_connection(
    db: Session,
    settings: Settings,
    *,
    tenant_id: str,
    name: str,
    triggered_by: str,
    client_factory: ClientFactory = _default_client,
) -> DmSyncRun:
    name = name.lower()
    environment = connections(settings).get(name)
    if environment is None:
        raise KeyError(name)
    run = DmSyncRun(tenant_id=tenant_id, connection=name, environment=environment, triggered_by=triggered_by)
    db.add(run)
    db.commit()
    try:
        if name == DEMO_CONNECTION and is_demo(settings):
            content = demo_export()
        else:
            client = client_factory(settings.viedoc_connections[name], settings.viedoc_allow_live)
            content = await client.run_export(EXPORT_OPTIONS)
        data = read_export(content)
        _store(db, tenant_id, name, environment, data)
        run.ok = True
        run.counts = {
            "study": data.study_code,
            "queries": len(data.queries),
            "open_at_site": sum(q.state == "open_at_site" for q in data.queries),
            "awaiting_approval": sum(q.state == "awaiting_approval" for q in data.queries),
            "closed": sum(q.state == "closed" for q in data.queries),
            "missing_items": len(data.missing),
            "pending_forms": len(data.pending),
            "sdv_required": sum(f.sdv_required for f in data.forms),
            "sdv_done": sum(f.sdv_done for f in data.forms),
            "forms_with_status": len(data.forms),
            "lab_results": len(data.labs),
            "lab_out_of_range": sum(bool(r.out_of_range) for r in data.labs),
        }
    except Exception as exc:  # shown on screen; the previous copy is kept
        db.rollback()
        run = db.merge(run)
        run.error = redact(str(exc))[:1000]
        log.warning("dm.sync_failed", extra={"connection": name, "error": run.error})
    run.finished_at = datetime.now(UTC)
    db.commit()
    return run


def last_runs(db: Session, tenant_id: str) -> dict[str, DmSyncRun]:
    runs = db.scalars(
        select(DmSyncRun).where(DmSyncRun.tenant_id == tenant_id).order_by(DmSyncRun.started_at.desc())
    ).all()
    latest: dict[str, DmSyncRun] = {}
    for r in runs:
        latest.setdefault(r.connection, r)
    return latest


def last_success(db: Session, tenant_id: str, name: str) -> DmSyncRun | None:
    return db.scalars(
        select(DmSyncRun)
        .where(DmSyncRun.tenant_id == tenant_id, DmSyncRun.connection == name, DmSyncRun.ok.is_(True))
        .order_by(DmSyncRun.started_at.desc())
        .limit(1)
    ).first()


async def run_scheduled_sync(settings: Settings) -> None:
    for name in connections(settings):
        db = new_session()
        try:
            await sync_connection(
                db, settings, tenant_id=DEFAULT_TENANT, name=name, triggered_by="system (scheduled)"
            )
        except Exception:
            log.exception("dm.scheduled_sync_failed", extra={"connection": name})
        finally:
            db.close()


async def scheduler_loop(settings: Settings) -> None:
    while True:
        await asyncio.sleep(settings.data_management_sync_minutes * 60)
        await run_scheduled_sync(settings)
