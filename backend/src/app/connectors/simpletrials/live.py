"""SimpleTrials API connector (read-only)."""

from __future__ import annotations

import logging
from typing import Any

from .api_client import SimpleTrialsClient, SimpleTrialsError
from .mapping import map_action_items, map_documents, map_study
from .models import StudyConnectorInfo, StudyRecord

log = logging.getLogger("simpletrials")


class ApiStudyConnector:
    def __init__(self, client: SimpleTrialsClient, key_names: frozenset[str] = frozenset()) -> None:
        self._client = client
        self._key_names = key_names

    def info(self) -> StudyConnectorInfo:
        return StudyConnectorInfo(mode="api", scope=self._client.scope, base_url=self._client.base_url)

    async def _study_ids(self) -> list[str]:
        if self._client.scope == "study":
            return [self._client.account_id]
        studies = await self._client.list_all("studies", "studies")
        return [
            str(s["id"]) for s in studies if s.get("id") is not None and s.get("active", True) is not False
        ]

    async def fetch_studies(self) -> list[StudyRecord]:
        records = []
        for study_id in await self._study_ids():  # sequential: the API is rate limited
            params: dict[str, Any] = {"study_id": study_id}
            study = await self._client.get("study", params)
            sites = await self._client.list_all("sites", "sites", params)
            tasks = await self._client.list_all("tasks", "tasks", params)
            record = map_study(study, sites, tasks, self._key_names)
            try:  # eTMF metadata only; a key without eTMF access must not stop the study sync
                record.documents = map_documents(
                    await self._client.list_all("documents", "documents", params)
                )
            except SimpleTrialsError as exc:
                log.warning("simpletrials.documents_unavailable", extra={"status": exc.status})
            try:  # read-only issues for Risks and Issues; must not stop the study sync either
                record.action_items = map_action_items(
                    await self._client.list_all("action_items", "action_items", params)
                )
            except SimpleTrialsError as exc:
                log.warning("simpletrials.action_items_unavailable", extra={"status": exc.status})
            records.append(record)
        return records
