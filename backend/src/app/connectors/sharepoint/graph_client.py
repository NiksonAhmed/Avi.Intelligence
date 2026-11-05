"""Minimal async Microsoft Graph client (OAuth 2.0 client-credentials flow).

No Graph SDK dependency: httpx + token cache + retry with Retry-After + pagination + SSRF guards.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any
from urllib.parse import quote, unquote, urlsplit

import httpx

GRAPH_ORIGIN = "https://graph.microsoft.com"
GRAPH_BASE = f"{GRAPH_ORIGIN}/v1.0"
LOGIN_ORIGIN = "https://login.microsoftonline.com"
RETRY_STATUSES = {429, 503, 504}
MAX_RETRIES = 3


class GraphError(Exception):
    def __init__(self, message: str, status: int, code: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code


class GraphClient:
    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        timeout: float = 30.0,
    ) -> None:
        self._tenant_id = tenant_id
        self._client_id = client_id
        self._client_secret = client_secret
        self._sleep = sleep
        self._http = httpx.AsyncClient(transport=transport, timeout=timeout)
        self._token: str | None = None
        self._token_expires_at = 0.0
        self._token_lock = asyncio.Lock()

    async def aclose(self) -> None:
        await self._http.aclose()

    # ---- auth -------------------------------------------------------------------------------
    async def _get_token(self) -> str:
        async with self._token_lock:  # de-duplicate concurrent token requests
            if self._token and self._token_expires_at > time.time() + 60:
                return self._token
            url = f"{LOGIN_ORIGIN}/{quote(self._tenant_id, safe='')}/oauth2/v2.0/token"
            resp = await self._http.post(
                url,
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "scope": f"{GRAPH_ORIGIN}/.default",
                    "grant_type": "client_credentials",
                },
            )
            body: dict[str, Any] = _safe_json(resp)
            token = body.get("access_token")
            if resp.status_code != 200 or not isinstance(token, str):
                # error_description explains AADSTS failures (bad secret, wrong tenant) and holds no secrets.
                detail = str(body.get("error_description") or f"HTTP {resp.status_code}").splitlines()[0]
                raise GraphError(
                    f"Could not obtain a Microsoft Graph token: {detail}",
                    resp.status_code,
                    body.get("error"),
                )
            self._token = token
            self._token_expires_at = time.time() + float(body.get("expires_in", 3600))
            return token

    # ---- requests ---------------------------------------------------------------------------
    @staticmethod
    def _resolve(path_or_url: str) -> str:
        """Accepts a Graph-relative path or absolute Graph URL; refuses other hosts (SSRF guard)."""
        if path_or_url.startswith("/"):
            return f"{GRAPH_BASE}{path_or_url}"
        parts = urlsplit(path_or_url)
        if f"{parts.scheme}://{parts.netloc}" != GRAPH_ORIGIN:
            raise GraphError(f"Refusing to call non-Graph URL host: {parts.netloc}", 0)
        return path_or_url

    async def request(
        self, method: str, path_or_url: str, *, follow_redirects: bool = True
    ) -> httpx.Response:
        url = self._resolve(path_or_url)
        attempt = 0
        refreshed = False
        while True:
            token = await self._get_token()
            resp = await self._http.request(
                method,
                url,
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                follow_redirects=follow_redirects,
            )
            if resp.status_code == 401 and not refreshed:
                refreshed = True
                self._token = None  # token revoked/expired early: retry once with a fresh one
                continue
            if resp.status_code in RETRY_STATUSES and attempt < MAX_RETRIES:
                await self._sleep(_retry_delay(resp, attempt))
                attempt += 1
                continue
            if resp.status_code >= 400:
                err = _safe_json(resp).get("error") or {}
                message = err.get("message") if isinstance(err, dict) else None
                code = err.get("code") if isinstance(err, dict) else None
                raise GraphError(
                    message or f"Microsoft Graph request failed (HTTP {resp.status_code}).",
                    resp.status_code,
                    code,
                )
            return resp

    async def get(self, path_or_url: str) -> dict[str, Any]:
        resp = await self.request("GET", path_or_url)
        return _safe_json(resp)

    async def get_all(self, path_or_url: str, max_pages: int = 100) -> list[dict[str, Any]]:
        """Follows @odata.nextLink until all pages are read (bounded to avoid runaway loops)."""
        items: list[dict[str, Any]] = []
        next_url: str | None = path_or_url
        for _ in range(max_pages):
            if not next_url:
                break
            page = await self.get(next_url)
            items.extend(page.get("value") or [])
            next_url = page.get("@odata.nextLink")
        return items

    async def download_url(self, path: str) -> str:
        """Gets the short-lived pre-authenticated download URL Graph redirects /content requests to."""
        resp = await self.request("GET", path, follow_redirects=False)
        location: str | None = resp.headers.get("Location")
        if resp.status_code not in (301, 302, 303, 307, 308) or not location:
            raise GraphError("Microsoft Graph did not return a download location.", resp.status_code)
        host = urlsplit(location).hostname or ""
        if urlsplit(location).scheme != "https" or not (
            host.endswith(".sharepoint.com") or host.endswith(".svc.ms")
        ):
            raise GraphError(f"Unexpected download host: {host}", 0)
        return location

    async def stream_url(self, url: str) -> AsyncIterator[bytes]:
        """Streams a pre-authenticated URL. The Graph bearer token is deliberately NOT sent."""
        async with self._http.stream("GET", url) as resp:
            if resp.status_code >= 400:
                raise GraphError(f"File download failed (HTTP {resp.status_code}).", resp.status_code)
            async for chunk in resp.aiter_bytes():
                yield chunk


def _safe_json(resp: httpx.Response) -> dict[str, Any]:
    try:
        data = resp.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _retry_delay(resp: httpx.Response, attempt: int) -> float:
    try:
        retry_after = float(resp.headers.get("Retry-After", ""))
    except ValueError:
        retry_after = 0.0
    delay = retry_after if retry_after > 0 else float(2**attempt)
    return min(delay, 30.0)


def site_lookup_path(site_url: str) -> str:
    """Converts "https://tenant.sharepoint.com/sites/QA" to the Graph site lookup path."""
    parts = urlsplit(site_url)
    host = parts.hostname or ""
    if parts.scheme != "https" or not host.endswith(".sharepoint.com"):
        raise ValueError("SHAREPOINT_SITE_URL must be an https://<tenant>.sharepoint.com/... URL.")
    path = unquote(parts.path).rstrip("/")
    return f"/sites/{host}:{quote(path)}" if path else f"/sites/{host}"
