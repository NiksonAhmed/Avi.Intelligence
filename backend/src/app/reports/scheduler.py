"""Scheduled SimpleTrials sync (default hourly), run inside the API process.

Each run is an ordinary read-only sync (the same as "Sync now"), recorded in the sync history with
`triggered_by = "system (scheduled)"`; the daily report snapshot is taken by the first sync of each day.
Failures are logged and retried at the next interval; they never stop the app.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from app.connectors.simpletrials import get_study_connector
from app.db.session import new_session
from app.studies.models import Study
from app.studies.sync import sync_studies

log = logging.getLogger("reports.scheduler")

DEFAULT_TENANT = "avion"


def _tenants() -> list[str]:
    db = new_session()
    try:
        found = sorted(set(db.scalars(select(Study.tenant_id)).all()))
    finally:
        db.close()
    return found or [DEFAULT_TENANT]


async def run_scheduled_sync() -> None:
    connector = get_study_connector()
    for tenant_id in _tenants():
        db = new_session()
        try:
            run = await sync_studies(db, connector, tenant_id=tenant_id, triggered_by="system (scheduled)")
            log.info("scheduled_sync.done", extra={"tenant": tenant_id, "ok": run.ok})
        except Exception:
            log.exception("scheduled_sync.failed", extra={"tenant": tenant_id})
        finally:
            db.close()


async def scheduler_loop(interval_minutes: int) -> None:
    while True:
        await asyncio.sleep(interval_minutes * 60)
        await run_scheduled_sync()
