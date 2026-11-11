"""Minimal read-only client for the SimpleTrials REST API (v1).

Facts from the SimpleTrials API Guide (Dec 2025) and a test against the Sandbox study:
  * Credentials are query parameters: customer_key + customer_id (workspace) or study_key + study_id.
    Keys therefore appear in request URLs, so this client never logs URLs or puts them in errors.
  * A User-Agent header is required (403 otherwise).
  * Lists are paged with limit (max 1000) and offset; responses carry count/limit/offset/total and a
    root attribute named after the resource (e.g. "sites").
  * Requests are rate limited: requests are made one at a time, with back-off on HTTP 429.
Only GET is used; Avi.Intelligence never writes to SimpleTrials.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Literal
from urllib.parse import urlparse

import httpx

log = logging.getLogger("simpletrials")

USER_AGENT = "Avi.Intelligence/0.1 (read-only integration)"
PAGE_SIZE = 1000
MAX_RETRIES = 4
ALLOWED_HOSTS = {"app.simpletrials.com", "eu.simpletrials.com", "apac.simpletrials.com"}


class SimpleTrialsError(Exception):
    """An API failure, described without the request URL (which contains the key)."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


_STATUS_HELP = {
    401: "SimpleTrials rejected the credentials (check the ID and key, and that API access is enabled).",
    403: "SimpleTrials refused the request (forbidden).",
    412: "SimpleTrials needs a valid study ID for this request.",
}


def validate_base_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError(
            "SIMPLETRIALS_BASE_URL must be https://app|eu|apac.simpletrials.com/api/v1/ "
            f"(got host {parsed.hostname!r})."
        )
    return base_url.rstrip("/") + "/"


class SimpleTrialsClient:
    def __init__(
        self,
        *,
        base_url: str,
        scope: Literal["workspace", "study"],
        account_id: str,
        key: str,
        transport: httpx.AsyncBaseTransport | None = None,
        retry_base_seconds: float = 1.0,
    ) -> None:
        self.base_url = validate_base_url(base_url)
        self.scope = scope
        self.account_id = account_id
        self._auth = (
            {"customer_id": account_id, "customer_key": key}
            if scope == "workspace"
            else {"study_id": account_id, "study_key": key}
        )
        self._transport = transport
        self._retry_base = retry_base_seconds

    async def get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        query = {**(params or {}), **self._auth}
        if self.scope == "study":
            query["study_id"] = self.account_id  # a study key only grants its own study
        async with httpx.AsyncClient(
            base_url=self.base_url,
            transport=self._transport,
            timeout=httpx.Timeout(30.0, connect=10.0),
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            follow_redirects=False,
        ) as client:
            for attempt in range(MAX_RETRIES + 1):
                try:
                    res = await client.get(endpoint, params=query)
                except httpx.HTTPError as exc:  # network failure: report the type, not the URL
                    raise SimpleTrialsError(f"Could not reach SimpleTrials ({type(exc).__name__}).") from None
                if res.status_code == 429 and attempt < MAX_RETRIES:
                    delay = self._retry_base * (2**attempt)
                    log.info("simpletrials.rate_limited", extra={"endpoint": endpoint, "retry_in_s": delay})
                    await asyncio.sleep(delay)
                    continue
                if res.status_code != 200:
                    detail = _STATUS_HELP.get(res.status_code)
                    if detail is None:
                        try:
                            detail = str(res.json().get("error", ""))[:200] or f"HTTP {res.status_code}"
                        except ValueError:
                            detail = f"HTTP {res.status_code}"
                    raise SimpleTrialsError(f"{endpoint}: {detail}", res.status_code)
                try:
                    body = res.json()
                except ValueError:
                    raise SimpleTrialsError(f"{endpoint}: response was not JSON.", 200) from None
                if not isinstance(body, dict):
                    raise SimpleTrialsError(f"{endpoint}: unexpected response shape.", 200)
                return body
        raise SimpleTrialsError(f"{endpoint}: still rate limited after {MAX_RETRIES} retries.", 429)

    async def list_all(
        self, endpoint: str, root: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Fetch every page of a list endpoint, sequentially."""
        items: list[dict[str, Any]] = []
        offset = 0
        while True:
            body = await self.get(endpoint, {**(params or {}), "limit": PAGE_SIZE, "offset": offset})
            page = body.get(root) or []
            if not isinstance(page, list):
                raise SimpleTrialsError(f"{endpoint}: unexpected response shape.", 200)
            items.extend(p for p in page if isinstance(p, dict))
            total = body.get("total")
            offset += len(page)
            if not page or not isinstance(total, int) or offset >= total:
                return items
