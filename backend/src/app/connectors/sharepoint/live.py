"""SOP connector backed by a SharePoint document library via Microsoft Graph."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote, unquote

from .graph_client import GraphClient, GraphError, site_lookup_path
from .mapping import (
    FieldMap,
    collect_person_lookup_ids,
    department_from_folder,
    has_allowed_extension,
    is_excluded_folder,
    is_within_folder,
    map_list_item_to_sop,
    sort_sops,
)
from .models import (
    CheckStep,
    ConnectionCheck,
    ConnectorColumn,
    ConnectorInfo,
    SopDocument,
    SopDownload,
    SopListResult,
    SopVersion,
)

log = logging.getLogger(__name__)

MAX_PERSON_LOOKUPS = 200


class GraphSopConnector:
    def __init__(
        self,
        client: GraphClient,
        *,
        site_url: str,
        library: str,
        folder: str | None,
        field_map: FieldMap,
        cache_seconds: float,
        exclude_folders: list[str] | None = None,
        file_types: list[str] | None = None,
    ) -> None:
        self._client = client
        self._site_url = site_url
        self._library = library
        self._folder = folder.strip("/") if folder else None
        self._field_map = field_map
        self._exclude_folders = exclude_folders or []
        self._file_types = file_types or []
        self._cache_seconds = cache_seconds
        self._targets: tuple[str, str, str] | None = None  # site_id, drive_id, list_id
        self._cache: SopListResult | None = None
        self._cache_expires = 0.0
        self._lock = asyncio.Lock()

    def info(self) -> ConnectorInfo:
        return ConnectorInfo(
            mode="live",
            site_url=self._site_url,
            library=self._library,
            folder=self._folder,
            field_map=self._field_map,
        )

    def clear_cache(self) -> None:
        self._cache = None
        self._cache_expires = 0.0

    # ---- target resolution -----------------------------------------------------------------
    async def _resolve_site(self) -> str:
        site = await self._client.get(site_lookup_path(self._site_url))
        return str(site["id"])

    async def _resolve_drive(self, site_id: str) -> str:
        drives = await self._client.get_all(f"/sites/{site_id}/drives?$select=id,name,webUrl")
        wanted = self._library.lower()
        for drive in drives:
            url_name = unquote(str(drive.get("webUrl", "")).rstrip("/").rsplit("/", 1)[-1]).lower()
            if str(drive.get("name", "")).lower() == wanted or url_name == wanted:
                return str(drive["id"])
        available = ", ".join(sorted(str(d.get("name")) for d in drives)) or "none"
        raise GraphError(
            f'Document library "{self._library}" was not found on the site. '
            f"Available libraries: {available}.",
            404,
        )

    async def _resolve_targets(self) -> tuple[str, str, str]:
        if self._targets is None:
            site_id = await self._resolve_site()
            drive_id = await self._resolve_drive(site_id)
            lst = await self._client.get(f"/drives/{drive_id}/list?$select=id,displayName")
            self._targets = (site_id, drive_id, str(lst["id"]))
        return self._targets

    # ---- reads ------------------------------------------------------------------------------
    async def _resolve_people(self, site_id: str, ids: set[str]) -> dict[str, str]:
        """Resolves person-column lookup ids via the site's hidden User Information List."""
        names: dict[str, str] = {}
        sem = asyncio.Semaphore(5)
        list_path = quote("User Information List")

        async def one(lookup_id: str) -> None:
            async with sem:
                try:
                    item = await self._client.get(
                        f"/sites/{site_id}/lists/{list_path}/items/{quote(lookup_id)}?$expand=fields"
                    )
                except GraphError:
                    return  # access to the hidden list may be denied; owner then shows as unknown
                title = (item.get("fields") or {}).get("Title")
                if isinstance(title, str) and title:
                    names[lookup_id] = title

        await asyncio.gather(*(one(i) for i in sorted(ids)[:MAX_PERSON_LOOKUPS]))
        return names

    async def _fetch_all(self) -> list[SopDocument]:
        site_id, _drive_id, list_id = await self._resolve_targets()
        items: list[dict[str, Any]] = await self._client.get_all(
            f"/sites/{site_id}/lists/{list_id}/items?$expand=fields,driveItem&$top=200"
        )
        people = await self._resolve_people(site_id, collect_person_lookup_ids(items, self._field_map))
        docs: list[SopDocument] = []
        for item in items:
            doc = map_list_item_to_sop(item, self._field_map, people.get)
            if (
                doc is None
                or not is_within_folder(doc.folder_path, self._folder)
                or is_excluded_folder(doc.folder_path, self._folder, self._exclude_folders)
                or not has_allowed_extension(doc.file_name, self._file_types)
            ):
                continue
            if not doc.department:
                doc.department = department_from_folder(doc.folder_path, self._folder)
            docs.append(doc)
        log.info("sharepoint.sops.fetched", extra={"count": len(docs), "items": len(items)})
        return sort_sops(docs)

    async def list_sops(self, force_refresh: bool = False) -> SopListResult:
        async with self._lock:
            now = time.monotonic()
            if self._cache and not force_refresh and now < self._cache_expires:
                return self._cache.model_copy(update={"from_cache": True})
            docs = await self._fetch_all()
            self._cache = SopListResult(documents=docs, fetched_at=datetime.now(UTC), from_cache=False)
            self._cache_expires = now + self._cache_seconds
            return self._cache

    async def get_sop(self, sop_id: str) -> SopDocument | None:
        # Looking the id up in the scoped list guarantees we never serve files outside the SOP folder.
        result = await self.list_sops()
        return next((d for d in result.documents if d.id == sop_id), None)

    async def list_versions(self, sop_id: str) -> list[SopVersion]:
        if not await self.get_sop(sop_id):
            return []
        _site_id, drive_id, _list_id = await self._resolve_targets()
        raw = await self._client.get_all(f"/drives/{drive_id}/items/{quote(sop_id)}/versions")
        versions: list[SopVersion] = []
        for v in raw:
            modified = v.get("lastModifiedDateTime")
            user = ((v.get("lastModifiedBy") or {}).get("user") or {}).get("displayName")
            versions.append(
                SopVersion(
                    id=str(v.get("id")),
                    modified_at=datetime.fromisoformat(modified.replace("Z", "+00:00")) if modified else None,
                    modified_by=user,
                    size_bytes=v.get("size") if isinstance(v.get("size"), int) else None,
                )
            )
        return versions

    async def download(self, sop_id: str) -> SopDownload | None:
        doc = await self.get_sop(sop_id)
        if not doc:
            return None
        _site_id, drive_id, _list_id = await self._resolve_targets()
        url = await self._client.download_url(f"/drives/{drive_id}/items/{quote(sop_id)}/content")
        return SopDownload(
            content=self._client.stream_url(url),
            content_type=doc.mime_type or "application/octet-stream",
            file_name=doc.file_name,
            size_bytes=doc.size_bytes,
        )

    # ---- diagnostics ------------------------------------------------------------------------
    async def test_connection(self) -> ConnectionCheck:
        steps: list[CheckStep] = []
        columns: list[ConnectorColumn] | None = None
        count: int | None = None
        try:
            site_id = await self._resolve_site()
            steps.append(
                CheckStep(label="Authenticate and open SharePoint site", ok=True, detail=self._site_url)
            )
        except (GraphError, ValueError) as exc:
            steps.append(CheckStep(label="Authenticate and open SharePoint site", ok=False, detail=str(exc)))
            return ConnectionCheck(ok=False, steps=steps)
        try:
            drive_id = await self._resolve_drive(site_id)
            lst = await self._client.get(f"/drives/{drive_id}/list?$select=id,displayName")
            self._targets = (site_id, drive_id, str(lst["id"]))
            steps.append(CheckStep(label=f'Find library "{self._library}"', ok=True))
        except GraphError as exc:
            steps.append(CheckStep(label=f'Find library "{self._library}"', ok=False, detail=str(exc)))
            return ConnectionCheck(ok=False, steps=steps)
        try:
            raw_cols = await self._client.get_all(
                f"/sites/{site_id}/lists/{lst['id']}/columns?$select=name,displayName,hidden,"
                "text,choice,dateTime,personOrGroup,number,lookup,calculated"
            )
            columns = [
                ConnectorColumn(
                    name=c["name"], display_name=c.get("displayName", c["name"]), type=_column_type(c)
                )
                for c in raw_cols
                if not c.get("hidden")
            ]
            steps.append(CheckStep(label="Read library columns", ok=True, detail=f"{len(columns)} columns"))
        except GraphError as exc:
            steps.append(CheckStep(label="Read library columns", ok=False, detail=str(exc)))
        try:
            result = await self.list_sops(force_refresh=True)
            count = len(result.documents)
            scope = f' in folder "{self._folder}"' if self._folder else ""
            steps.append(CheckStep(label="List SOP documents", ok=True, detail=f"{count} documents{scope}"))
        except GraphError as exc:
            steps.append(CheckStep(label="List SOP documents", ok=False, detail=str(exc)))
        return ConnectionCheck(
            ok=all(s.ok for s in steps), steps=steps, columns=columns, document_count=count
        )


def _column_type(col: dict[str, Any]) -> str:
    for key in ("text", "choice", "dateTime", "personOrGroup", "number", "lookup", "calculated"):
        if key in col:
            return key
    return "other"
