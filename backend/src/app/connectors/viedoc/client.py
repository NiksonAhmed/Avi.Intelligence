"""Minimal read-only client for the Viedoc API (Step 0: discovery).

Facts from Viedoc's public API page (Nov 2026): OAuth 2.0 client credentials; each API client is linked
to one study and has scopes (e.g. data export); one API instance per region (EU, US, Japan, China), each
with a training environment; endpoints are documented in Swagger UI. The token address, base address and
endpoint names are not public, so this client finds them: the token address from the API's OpenID
configuration (unless given), and the endpoint list from the API's Swagger/OpenAPI description.

Clinical data and queries come out of Viedoc only as an export (start -> status -> download -> delete).

Rules: secrets and tokens are only sent to Viedoc hosts and are never logged or put in errors. Study data
is never changed: apart from sign-in, only GET is used, plus exactly two calls that handle our own export
copy (`EXPORT_CALLS`): starting an export and deleting that export file afterwards. Every other write
endpoint (creating sites, inviting users, ePRO accounts...) is refused in code.
"""

from __future__ import annotations

import asyncio
import base64
import csv
import io
import re
import time
import zipfile
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from app.core.config import ViedocConnectionSettings

USER_AGENT = "Avi.Intelligence/0.1 (read-only integration)"
API_VERSION = "2022-01-01"
ALLOWED_HOST_SUFFIXES = (".viedoc.net", ".viedoc.com", ".viedoc.cn")
# The only non-GET calls ever made: they create and remove our own export copy, never study data.
EXPORT_CALLS = {("POST", "clinic/dataexport/start"), ("DELETE", "clinic/dataexport/delete")}
_REFUSED_HELP = {
    403: "Viedoc refused the request (IP address not allowed, or the client is not linked to a study).",
    401: "Viedoc did not accept the access token.",
    400: "Viedoc rejected the request (invalid data or unsupported API version).",
}
SPEC_PATHS = (
    "swagger/v1/swagger.json",
    "swagger/v2/swagger.json",
    "swagger/v3/swagger.json",
    "swagger/docs/v1",
    "openapi.json",
    "openapi/v1.json",
    "v1/openapi.json",
    "api-docs",
    "v2/api-docs",
    "v3/api-docs",
)


class ViedocError(Exception):
    """A Viedoc API failure, described without secrets or tokens."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class LiveNotAllowed(ViedocError):
    pass


def check_viedoc_url(url: str, what: str) -> str:
    """Only https Viedoc addresses may receive the client secret or a token."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not any(host.endswith(s) for s in ALLOWED_HOST_SUFFIXES):
        raise ViedocError(f"{what} must be an https Viedoc address (got host {host or '-'!r}).")
    return url


def _oauth_error_code(res: httpx.Response) -> str:
    """The OAuth error code (e.g. "invalid_scope") from a failed sign-in, only when it is a plain code
    of letters and underscores, so nothing else from the reply (which might echo input) is ever shown."""
    try:
        code = res.json().get("error")
    except (ValueError, AttributeError):
        return ""
    return code if isinstance(code, str) and re.fullmatch(r"[a-z_]{3,40}", code) else ""


def _sts_candidates(api_url: str) -> list[str]:
    """Viedoc's sign-in (STS) host for an API host: the first "api" in the host name becomes "sts"."""
    host = urlparse(api_url).hostname or ""
    first = host.split(".", 1)[0]
    if "api" not in first:
        return []
    return [f"https://{first.replace('api', 'sts', 1)}.{host.split('.', 1)[1]}/"]


def _origin(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}/"


class ViedocClient:
    def __init__(
        self,
        connection: ViedocConnectionSettings,
        *,
        allow_live: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if connection.environment == "live" and not allow_live:
            raise LiveNotAllowed(
                "This is a live Viedoc connection. Live studies are not read until VIEDOC_ALLOW_LIVE=true "
                "(after Avion's data-protection and Quality sign-off)."
            )
        self.connection = connection
        self.api_url = check_viedoc_url(connection.api_url.rstrip("/") + "/", "VIEDOC api_url")
        self._transport = transport
        self._token: str | None = None
        self._token_expires = 0.0
        self.granted_scopes: list[str] = []
        self.token_expires_in: int | None = None

    def _http(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=self._transport,
            timeout=httpx.Timeout(30.0, connect=10.0),
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            follow_redirects=False,
        )

    async def token_url(self) -> str:
        if self.connection.token_url:
            return check_viedoc_url(self.connection.token_url, "VIEDOC token_url")
        # OpenID discovery: the API address, its host root, then Viedoc's sign-in server, which sits
        # next to the API on its own host (v4apitraining.viedoc.net -> v4ststraining.viedoc.net).
        for base in dict.fromkeys([self.api_url, _origin(self.api_url), *_sts_candidates(self.api_url)]):
            url = urljoin(base, ".well-known/openid-configuration")
            async with self._http() as http:
                try:
                    res = await http.get(url)
                except httpx.HTTPError:
                    continue
            if res.status_code == 200:
                try:
                    endpoint = res.json().get("token_endpoint")
                except ValueError:
                    continue
                if isinstance(endpoint, str):
                    return check_viedoc_url(endpoint, "Discovered token endpoint")
        raise ViedocError(
            "Could not find the token address. Set VIEDOC_CONNECTIONS__<NAME>__TOKEN_URL from Viedoc's "
            "API documentation (Swagger)."
        )

    async def sign_in(self) -> None:
        """Gets an access token (client credentials). Tries the secret as Basic auth, then in the body."""
        url = await self.token_url()
        secret = self.connection.client_secret.get_secret_value()
        form: dict[str, str] = {"grant_type": "client_credentials"}
        if self.connection.scope:
            form["scope"] = self.connection.scope
        basic = base64.b64encode(f"{self.connection.client_id}:{secret}".encode()).decode()
        attempts = [
            ({"Authorization": f"Basic {basic}"}, form),
            ({}, {**form, "client_id": self.connection.client_id, "client_secret": secret}),
        ]
        last_status: int | None = None
        codes: list[str] = []
        async with self._http() as http:
            for headers, data in attempts:
                try:
                    res = await http.post(url, data=data, headers=headers)
                except httpx.HTTPError as exc:
                    raise ViedocError(f"Could not reach Viedoc's sign-in ({type(exc).__name__}).") from None
                last_status = res.status_code
                codes.append(_oauth_error_code(res))
                if res.status_code == 200:
                    body = res.json()
                    token = body.get("access_token")
                    if not isinstance(token, str):
                        raise ViedocError("Viedoc's sign-in response had no access token.", 200)
                    self._token = token
                    self.token_expires_in = int(body.get("expires_in") or 0) or None
                    self._token_expires = time.monotonic() + (self.token_expires_in or 300) - 30
                    self.granted_scopes = str(body.get("scope") or "").split()
                    return
                if res.status_code not in (400, 401):
                    break
        help_text = {
            400: "Viedoc rejected the sign-in request (check the client ID, secret and scope).",
            401: "Viedoc rejected the client ID or secret.",
        }
        detail = help_text.get(last_status or 0, f"Sign-in failed (HTTP {last_status}).")
        shown = [c for c in codes if c]
        if shown:
            detail += f" Viedoc's error code: {', '.join(dict.fromkeys(shown))}."
        raise ViedocError(f"{detail} Token address host: {urlparse(url).hostname}.", last_status)

    async def _auth_headers(self) -> dict[str, str]:
        if self._token is None or time.monotonic() >= self._token_expires:
            await self.sign_in()
        return {"Authorization": f"Bearer {self._token}"}

    async def _request(
        self, method: str, path: str, *, params: dict[str, Any] | None = None, json: Any = None
    ) -> httpx.Response:
        clean = path.lstrip("/").split("?", 1)[0]
        if method != "GET" and (method, clean) not in EXPORT_CALLS:
            raise ViedocError(f"{method} {clean} is not allowed: Avi.Intelligence never changes Viedoc data.")
        url = check_viedoc_url(urljoin(self.api_url, path.lstrip("/")), "Request address")
        headers = {**await self._auth_headers(), "Accept-Version": API_VERSION}
        async with self._http() as http:
            try:
                return await http.request(method, url, params=params, json=json, headers=headers)
            except httpx.HTTPError as exc:
                raise ViedocError(f"Could not reach Viedoc ({type(exc).__name__}).") from None

    async def get(self, path: str, params: dict[str, Any] | None = None) -> tuple[int, Any]:
        """GET a path under the API address. Returns (status, JSON body or None)."""
        res = await self._request("GET", path, params=params)
        try:
            body = res.json()
        except ValueError:
            body = None
        return res.status_code, body

    # ---- export: the only way clinical data and queries come out of Viedoc ----

    async def start_export(self, options: dict[str, Any]) -> str:
        res = await self._request("POST", "clinic/dataexport/start", json=options)
        if res.status_code != 200:
            raise ViedocError(
                _REFUSED_HELP.get(res.status_code, f"Export not started (HTTP {res.status_code})."),
                res.status_code,
            )
        export_id = res.json().get("exportId")
        if not isinstance(export_id, str):
            raise ViedocError("Viedoc did not return an export id.", 200)
        return export_id

    async def export_status(self, export_id: str) -> tuple[str, int | None]:
        res = await self._request("GET", "clinic/dataexport/status", params={"exportId": export_id})
        if res.status_code != 200:
            raise ViedocError(
                _REFUSED_HELP.get(res.status_code, f"Export status failed (HTTP {res.status_code})."),
                res.status_code,
            )
        body = res.json()
        return str(body.get("exportStatus")), body.get("progressPercent")

    async def download_export(self, export_id: str) -> bytes:
        res = await self._request("GET", "clinic/dataexport/download", params={"exportId": export_id})
        if res.status_code != 200:
            raise ViedocError(
                _REFUSED_HELP.get(res.status_code, f"Download failed (HTTP {res.status_code})."),
                res.status_code,
            )
        return res.content

    async def delete_export(self, export_id: str) -> bool:
        res = await self._request("DELETE", "clinic/dataexport/delete", params={"exportId": export_id})
        return res.status_code == 200

    async def run_export(
        self, options: dict[str, Any], *, poll_seconds: float = 3.0, timeout_seconds: float = 600.0
    ) -> bytes:
        """Start an export, wait until it is ready, download it into memory and always delete it from
        Viedoc's server afterwards. Nothing is written to disk."""
        export_id = await self.start_export(options)
        try:
            waited = 0.0
            while True:
                status, _progress = await self.export_status(export_id)
                if status == "Ready":
                    return await self.download_export(export_id)
                if status == "Error":
                    raise ViedocError("Viedoc reported an error while preparing the export.")
                if waited >= timeout_seconds:
                    raise ViedocError(f"The export was not ready after {int(timeout_seconds)} seconds.")
                await asyncio.sleep(poll_seconds)
                waited += poll_seconds
        finally:
            await self.delete_export(export_id)

    async def _spec_paths_from_swagger_ui(self) -> list[str]:
        """Viedoc versions its API by date (e.g. /swagger/2022-01-01/swagger.json); the Swagger page's
        script names the current description(s), newest first."""
        found: list[str] = []
        for script in ("swagger/index.js", "swagger/swagger-initializer.js"):
            async with self._http() as http:
                try:
                    res = await http.get(urljoin(self.api_url, script))
                except httpx.HTTPError:
                    continue
            if res.status_code == 200:
                found += re.findall(r"[\"'](/?swagger/[\w.-]+/swagger\.json)[\"']", res.text)
        return sorted(dict.fromkeys(p.lstrip("/") for p in found), reverse=True)

    async def find_spec(self) -> tuple[str, dict[str, Any]] | None:
        """The API's Swagger/OpenAPI description: the one the Swagger page names, else a usual address."""
        named = await self._spec_paths_from_swagger_ui()
        for base in dict.fromkeys([self.api_url, _origin(self.api_url)]):
            for path in [*named, *SPEC_PATHS]:
                url = urljoin(base, path)
                async with self._http() as http:
                    try:
                        res = await http.get(url, headers=await self._auth_headers())
                    except httpx.HTTPError:
                        continue
                if res.status_code != 200:
                    continue
                try:
                    body = res.json()
                except ValueError:
                    continue
                if isinstance(body, dict) and isinstance(body.get("paths"), dict):
                    return url, body
        return None


# ---- describing what comes back, without values ---------------------------------------------------

_INTEREST = {
    "queries": ("query", "queries"),
    "clinical data / forms": ("form", "item", "clinical", "export", "data"),
    "visits / events": ("visit", "event"),
    "subjects": ("subject", "patient"),
    "sites": ("site",),
    "deviations": ("deviation",),
    "lab ranges": ("lab", "range", "reference"),
    "study design / metadata": ("metadata", "design", "study"),
}


def list_endpoints(spec: dict[str, Any]) -> list[dict[str, str]]:
    rows = []
    for path, ops in sorted(spec.get("paths", {}).items()):
        if not isinstance(ops, dict):
            continue
        for method, op in ops.items():
            if method.lower() not in ("get", "post", "put", "patch", "delete") or not isinstance(op, dict):
                continue
            text = f"{path} {op.get('summary', '')} {' '.join(op.get('tags', []))}".lower()
            areas = [area for area, words in _INTEREST.items() if any(w in text for w in words)]
            rows.append(
                {
                    "method": method.upper(),
                    "path": path,
                    "summary": str(op.get("summary") or op.get("operationId") or "")[:100],
                    "areas": ", ".join(areas),
                }
            )
    return rows


def describe_shape(value: Any, *, depth: int = 0, max_depth: int = 4) -> list[str]:
    """The structure of a JSON response: field names, types and list lengths, never the values."""
    pad = "  " * depth
    if isinstance(value, dict):
        if len(value) > 40:  # likely keyed by record ids (e.g. subjects): don't list the names
            return [f"{pad}(object with {len(value)} keys; names not shown)"]
        lines = []
        for key, inner in value.items():
            if isinstance(inner, (dict, list)) and depth < max_depth:
                kind = f"list[{len(inner)}]" if isinstance(inner, list) else "object"
                lines.append(f"{pad}{key}: {kind}")
                lines.extend(describe_shape(inner, depth=depth + 1, max_depth=max_depth))
            else:
                lines.append(f"{pad}{key}: {type(inner).__name__}")
        return lines
    if isinstance(value, list):
        if not value:
            return [f"{pad}(empty list)"]
        first = value[0]
        if isinstance(first, (dict, list)):
            return [f"{pad}first item:", *describe_shape(first, depth=depth + 1, max_depth=max_depth)]
        return [f"{pad}items: {type(first).__name__}"]
    return [f"{pad}{type(value).__name__}"]


def _describe_csv(name: str, data: bytes) -> list[str]:
    text = data.decode("utf-8-sig", errors="replace")
    sample = text[:4096]
    try:
        dialect: type[csv.Dialect] | csv.Dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = csv.reader(io.StringIO(text), dialect)
    header = next(rows, [])
    count = sum(1 for _ in rows)
    cols = [h.strip()[:40] for h in header]
    # Files that matter for Data Management get every column; ordinary form files a short preview.
    key = any(w in name.lower() for w in _DM_FILE_WORDS)
    shown = cols if key else cols[:8]
    more = "" if key or len(cols) <= 8 else f" ... (+{len(cols) - 8} more)"
    return [f"{name}: {count} rows, {len(cols)} columns", f"  columns: {', '.join(shown)}{more}"]


_DM_FILE_WORDS = ("quer", "history", "review", "sdv", "pending", "status", "edit", "event", "sign", "deviat")


def _describe_xlsx(name: str, data: bytes) -> list[str]:
    from openpyxl import load_workbook

    book = load_workbook(io.BytesIO(data), read_only=True)
    lines = [f"{name}: Excel, sheets: {', '.join(book.sheetnames)}"]
    for sheet in book.worksheets:
        rows = sheet.iter_rows(values_only=True)
        header = next(rows, ())
        count = sum(1 for _ in rows)
        cols = [str(c).strip()[:40] for c in header if c is not None]
        lines += [f"  {sheet.title}: {count} rows", f"    columns: {', '.join(cols)}"]
    return lines


def _describe_xml(name: str, data: bytes) -> list[str]:
    from collections import Counter

    # Tag names only, counted with a pattern rather than an XML parser (no entity expansion risk).
    tags = re.findall(rb"<([A-Za-z_][\w.:-]*)", data)
    counts: Counter[str] = Counter(t.decode(errors="replace").split(":")[-1] for t in tags)
    top = ", ".join(f"{tag} x{n}" for tag, n in counts.most_common(25))
    return [f"{name}: XML, element counts: {top}"]


def describe_export_file(content: bytes, name: str = "export") -> list[str]:
    """What an export contains: file names, sheets, column names and row counts, never the values."""
    if content[:2] == b"PK" and zipfile.is_zipfile(io.BytesIO(content)):
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            inner = [i for i in archive.infolist() if not i.is_dir()]
            if [i.filename for i in inner if i.filename.startswith("xl/")]:  # an .xlsx is itself a zip
                return _describe_xlsx(name, content)
            lines = [f"{name}: zip with {len(inner)} file(s)"]
            for info in inner:
                lines += ["  " + line for line in describe_export_file(archive.read(info), info.filename)]
            return lines
    lower = name.lower()
    if lower.endswith(".xml") or content.lstrip()[:5] == b"<?xml":
        return _describe_xml(name, content)
    if lower.endswith((".csv", ".txt")) or b"," in content[:2048] or b";" in content[:2048]:
        return _describe_csv(name, content)
    return [f"{name}: {len(content)} bytes (format not recognised)"]


def _shape_of(value: str) -> str:
    """A value's format, not the value: letters become a, digits d ("2026-11-03" -> dddd-dd-dd)."""
    return re.sub(r"\d", "d", re.sub(r"[A-Za-z]", "a", value))


def describe_columns(
    content: bytes, file_suffix: str, columns: list[str], max_distinct: int = 25
) -> list[str]:
    """For named columns of one CSV in an export: the distinct values only when there are few of them
    (system vocabulary such as states and roles), otherwise just how many; plus the value formats.
    Free text, names and IDs have many distinct values and are therefore never shown."""
    from collections import Counter

    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        name = next((n for n in archive.namelist() if n.endswith(file_suffix)), None)
        if name is None:
            return [f"No file ending with {file_suffix!r} in the export."]
        text = archive.read(name).decode("utf-8-sig", errors="replace")
    rows = list(csv.DictReader(io.StringIO(text)))
    lines = [f"{name}: {len(rows)} rows"]
    for col in columns:
        values = [r.get(col, "") or "" for r in rows]
        if not any(col in r for r in rows[:1]):
            lines.append(f"  {col}: (no such column)")
            continue
        distinct = Counter(values)
        shapes = Counter(_shape_of(v) for v in values if v)
        shape_text = ", ".join(f"{s!r} x{n}" for s, n in shapes.most_common(3))
        if len(distinct) <= max_distinct:
            vals = ", ".join(f"{v or '(blank)'!r} x{n}" for v, n in distinct.most_common())
            lines.append(f"  {col}: {vals}")
        else:
            lines.append(f"  {col}: {len(distinct)} distinct values (not shown); formats: {shape_text}")
    return lines
