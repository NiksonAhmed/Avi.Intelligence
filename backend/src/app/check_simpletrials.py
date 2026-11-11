"""Check the SimpleTrials API connection from the command line (read-only).

    uv run python -m app.check_simpletrials

Prints what would be synced (studies, sites, milestones). Never prints keys or request URLs.
"""

from __future__ import annotations

import asyncio
import sys

import truststore

from app.connectors.simpletrials import build_study_connector
from app.connectors.simpletrials.api_client import SimpleTrialsError
from app.core.config import get_settings


async def main() -> int:
    settings = get_settings()
    if settings.use_system_trust_store:
        truststore.inject_into_ssl()
    connector = build_study_connector(settings)
    info = connector.info()
    print(f"Mode: {info.mode}  Scope: {info.scope or '-'}  Base URL: {info.base_url or '-'}")
    if info.mode != "api":
        print(f"Not using the API: {info.mock_reason}")
        return 1
    try:
        studies = await connector.fetch_studies()
    except SimpleTrialsError as exc:
        print(f"FAILED: {exc}")
        return 2
    print(f"OK: {len(studies)} study(ies)")
    for s in studies:
        done = sum(1 for m in s.milestones if m.percent_complete == 100 or m.actual_date)
        print(
            f"- {s.protocol_number}{' [SANDBOX]' if s.sandbox else ''} | "
            f"{s.phase or '-'} | {s.status or '-'} | "
            f"sponsor {s.sponsor or '-'} | enrolled {s.enrolled if s.enrolled is not None else '-'}"
            f" of {s.enrolment_target or 'no target'} | {len(s.sites)} sites | "
            f"{len(s.milestones)} milestones ({done} complete)"
        )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
