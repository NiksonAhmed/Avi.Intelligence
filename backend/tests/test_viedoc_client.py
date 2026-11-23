"""Viedoc Step 0 discovery client: fake Viedoc only, never the real API."""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

import httpx
import pytest

from app.check_viedoc import run
from app.connectors.viedoc.client import (
    LiveNotAllowed,
    ViedocClient,
    ViedocError,
    describe_shape,
    list_endpoints,
)
from app.core.config import Settings, ViedocConnectionSettings

SECRET = "very-secret-value-123"
TOKEN = "token-abc-should-never-print"
API = "https://sandbox-api.viedoc.net/api/"
SPEC = {
    "info": {"title": "Viedoc API", "version": "4"},
    "paths": {
        "/v1/queries": {"get": {"summary": "List queries", "tags": ["Queries"]}},
        "/v1/sites": {"get": {"summary": "List sites"}},
        "/v1/subjects/{id}": {"put": {"summary": "Update subject"}},
    },
}


def conn(**kw: Any) -> ViedocConnectionSettings:
    return ViedocConnectionSettings(api_url=API, client_id="client-1", client_secret=SECRET, **kw)  # type: ignore[arg-type]


class FakeViedoc:
    def __init__(self, *, basic_ok: bool = True, spec: bool = True) -> None:
        self.basic_ok = basic_ok
        self.spec = spec
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path.endswith("/.well-known/openid-configuration"):
            return httpx.Response(200, json={"token_endpoint": "https://sandbox-id.viedoc.net/connect/token"})
        if path == "/connect/token":
            body = request.content.decode()
            if "Authorization" in request.headers and not self.basic_ok:
                return httpx.Response(401, json={"error": "invalid_client"})
            if "Authorization" not in request.headers and "client_secret" not in body:
                return httpx.Response(401)
            return httpx.Response(
                200, json={"access_token": TOKEN, "expires_in": 3600, "scope": "export read"}
            )
        if request.headers.get("Authorization") != f"Bearer {TOKEN}":
            return httpx.Response(401)
        if path == "/api/swagger/v1/swagger.json" and self.spec:
            return httpx.Response(200, json=SPEC)
        if path == "/api/v1/queries":
            return httpx.Response(
                200,
                json={"total": 2, "items": [{"queryId": 7, "subject": "1001-003", "text": SECRET}]},
            )
        return httpx.Response(404)

    def client(self, connection: ViedocConnectionSettings | None = None, **kw: Any) -> ViedocClient:
        return ViedocClient(connection or conn(), transport=httpx.MockTransport(self.handler), **kw)


def test_sign_in_discovers_the_token_address_and_reports_scopes() -> None:
    fake = FakeViedoc()
    client = fake.client()
    asyncio.run(client.sign_in())
    assert client.granted_scopes == ["export", "read"] and client.token_expires_in == 3600
    token_call = next(r for r in fake.requests if r.url.path == "/connect/token")
    assert token_call.method == "POST" and token_call.url.host == "sandbox-id.viedoc.net"


def test_falls_back_to_secret_in_the_body() -> None:
    fake = FakeViedoc(basic_ok=False)
    client = fake.client(conn(token_url="https://sandbox-id.viedoc.net/connect/token"))
    asyncio.run(client.sign_in())
    tries = [r for r in fake.requests if r.url.path == "/connect/token"]
    assert len(tries) == 2 and "Authorization" not in tries[1].headers


def test_only_viedoc_hosts_and_never_live_by_default() -> None:
    with pytest.raises(ViedocError):
        ViedocClient(
            ViedocConnectionSettings(api_url="https://evil.example.com/", client_id="a", client_secret="b")
        )  # type: ignore[arg-type]
    with pytest.raises(ViedocError):
        ViedocClient(
            ViedocConnectionSettings(api_url="http://x.viedoc.net/", client_id="a", client_secret="b")
        )  # type: ignore[arg-type]
    with pytest.raises(LiveNotAllowed):
        ViedocClient(conn(environment="live"))
    assert ViedocClient(conn(environment="live"), allow_live=True).connection.environment == "live"
    # A token address outside Viedoc is refused before the secret is sent.
    client = FakeViedoc().client(conn(token_url="https://evil.example.com/token"))
    with pytest.raises(ViedocError):
        asyncio.run(client.sign_in())


def test_errors_never_contain_the_secret() -> None:
    def always_401(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("openid-configuration"):
            return httpx.Response(200, json={"token_endpoint": "https://sandbox-id.viedoc.net/connect/token"})
        return httpx.Response(401, json={"error": SECRET})

    client = ViedocClient(conn(), transport=httpx.MockTransport(always_401))
    with pytest.raises(ViedocError) as err:
        asyncio.run(client.sign_in())
    assert SECRET not in str(err.value) and err.value.status == 401


def test_finds_and_lists_endpoints() -> None:
    found = asyncio.run(FakeViedoc().client().find_spec())
    assert found is not None and found[0].endswith("/api/swagger/v1/swagger.json")
    rows = list_endpoints(found[1])
    assert [(r["method"], r["path"]) for r in rows] == [
        ("GET", "/v1/queries"),
        ("GET", "/v1/sites"),
        ("PUT", "/v1/subjects/{id}"),
    ]
    assert rows[0]["areas"] == "queries" and "sites" in rows[1]["areas"]


def test_describe_shape_shows_names_never_values() -> None:
    text = "\n".join(
        describe_shape({"total": 2, "items": [{"queryId": 7, "subject": "1001-003", "text": SECRET}]})
    )
    assert "items: list[1]" in text and "queryId: int" in text and "text: str" in text
    assert SECRET not in text and "1001-003" not in text
    many = {f"S-{i}": {"x": 1} for i in range(50)}
    assert describe_shape(many) == ["(object with 50 keys; names not shown)"]


def _settings(**connections: ViedocConnectionSettings) -> Settings:
    return Settings(_env_file=None, viedoc_connections=connections)  # type: ignore[call-arg]


def _run(settings: Settings, fake: FakeViedoc, monkeypatch: pytest.MonkeyPatch, **kw: Any) -> int:
    import app.check_viedoc as cli

    real = cli.ViedocClient

    def with_fake(c: ViedocConnectionSettings, allow_live: bool = False) -> ViedocClient:
        return real(c, allow_live=allow_live, transport=httpx.MockTransport(fake.handler))

    monkeypatch.setattr(cli, "ViedocClient", with_fake)
    args = argparse.Namespace(**{"connection": None, "try_path": None, "save_spec": None, **kw})
    return asyncio.run(run(args, settings))


def test_command_lists_endpoints_and_never_prints_secrets(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Any
) -> None:
    target = tmp_path / "viedoc-api.json"
    code = _run(_settings(sandbox=conn()), FakeViedoc(), monkeypatch, save_spec=str(target))
    out = capsys.readouterr().out
    assert code == 0
    assert (
        "Connection: sandbox (SANDBOX)" in out and "Signed in: yes" in out and "scopes: export, read" in out
    )
    assert "3 endpoints (2 read-only GET)" in out
    assert "GET    /v1/queries" in out and "! PUT" in out
    assert json.loads(target.read_text(encoding="utf-8"))["info"]["title"] == "Viedoc API"
    assert SECRET not in out and TOKEN not in out


def test_command_try_shows_structure_only(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = FakeViedoc()
    code = _run(_settings(sandbox=conn()), fake, monkeypatch, connection="SANDBOX", try_path="/v1/queries")
    out = capsys.readouterr().out
    assert code == 0 and "GET /v1/queries -> HTTP 200" in out and "queryId: int" in out
    assert SECRET not in out and "1001-003" not in out and TOKEN not in out
    # Only GET, apart from the sign-in request.
    assert {r.method for r in fake.requests if r.url.path != "/connect/token"} == {"GET"}


def test_command_without_connections_or_live(capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        asyncio.run(run(argparse.Namespace(connection=None, try_path=None, save_spec=None), _settings())) == 1
    )
    assert "No Viedoc connection in .env" in capsys.readouterr().out
    live = _settings(prod=conn(environment="live"))
    assert asyncio.run(run(argparse.Namespace(connection=None, try_path=None, save_spec=None), live)) == 2
    assert "VIEDOC_ALLOW_LIVE" in capsys.readouterr().out


def test_settings_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VIEDOC_CONNECTIONS__SANDBOX__API_URL", API)
    monkeypatch.setenv("VIEDOC_CONNECTIONS__SANDBOX__CLIENT_ID", "c")
    monkeypatch.setenv("VIEDOC_CONNECTIONS__SANDBOX__CLIENT_SECRET", SECRET)
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.viedoc_connections["sandbox"].environment == "sandbox"
    assert s.viedoc_allow_live is False and s.data_management_enabled is False
    assert SECRET not in repr(s)
    json.dumps(list(s.viedoc_connections))


def test_sign_in_server_next_to_the_api_is_found() -> None:
    from app.connectors.viedoc.client import _sts_candidates

    assert _sts_candidates("https://v4apitraining.viedoc.net/") == ["https://v4ststraining.viedoc.net/"]
    assert _sts_candidates("https://v4api.viedoc.net/x") == ["https://v4sts.viedoc.net/"]
    assert _sts_candidates("https://other.viedoc.net/") == []

    def handler(request: httpx.Request) -> httpx.Response:
        # Only the sign-in host publishes the OpenID configuration.
        if request.url.host == "v4ststraining.viedoc.net" and request.url.path.endswith(
            "openid-configuration"
        ):
            return httpx.Response(
                200, json={"token_endpoint": "https://v4ststraining.viedoc.net/connect/token"}
            )
        return httpx.Response(404)

    client = ViedocClient(
        ViedocConnectionSettings(
            api_url="https://v4apitraining.viedoc.net", client_id="a", client_secret="b"
        ),  # type: ignore[arg-type]
        transport=httpx.MockTransport(handler),
    )
    assert asyncio.run(client.token_url()) == "https://v4ststraining.viedoc.net/connect/token"


def test_finds_the_dated_description_named_by_the_swagger_page() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("openid-configuration"):
            return httpx.Response(200, json={"token_endpoint": "https://sandbox-id.viedoc.net/connect/token"})
        if path == "/connect/token":
            return httpx.Response(200, json={"access_token": TOKEN, "expires_in": 60})
        if path == "/api/swagger/index.js":
            return httpx.Response(200, text='configObject.urls = [{url: "/swagger/2022-01-01/swagger.json"}]')
        if path == "/api/swagger/2022-01-01/swagger.json":
            return httpx.Response(200, json=SPEC)
        return httpx.Response(404)

    client = ViedocClient(conn(), transport=httpx.MockTransport(handler))
    found = asyncio.run(client.find_spec())
    assert found is not None and found[0].endswith("/swagger/2022-01-01/swagger.json")


def _zip_with_csv() -> bytes:
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(
            "Queries.csv", f"SiteCode,SubjectKey,QueryText,QueryState\n101,1001-003,{SECRET},Resolved\n"
        )
        z.writestr("AE.csv", "SiteCode,SubjectKey,AETERM\n101,1001-003,Headache\n101,1001-004,Nausea\n")
    return buf.getvalue()


class FakeExport:
    def __init__(self, finish: str = "Ready") -> None:
        self.finish = finish
        self.calls: list[tuple[str, str]] = []
        self.status_calls = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append((request.method, path))
        if path.endswith("openid-configuration"):
            return httpx.Response(200, json={"token_endpoint": "https://sandbox-id.viedoc.net/connect/token"})
        if path == "/connect/token":
            return httpx.Response(200, json={"access_token": TOKEN, "expires_in": 60})
        assert request.headers["Accept-Version"] == "2022-01-01"
        if path == "/api/clinic/dataexport/start":
            assert json.loads(request.content)["includeQueries"] is True
            return httpx.Response(200, json={"exportId": "e-1"})
        if path == "/api/clinic/dataexport/status":
            self.status_calls += 1
            done = self.status_calls > 1
            return httpx.Response(
                200, json={"exportStatus": self.finish if done else "InProgress", "progressPercent": 50}
            )
        if path == "/api/clinic/dataexport/download":
            return httpx.Response(200, content=_zip_with_csv())
        if path == "/api/clinic/dataexport/delete":
            return httpx.Response(200)
        return httpx.Response(404)


def test_export_runs_reads_in_memory_and_is_always_deleted() -> None:
    fake = FakeExport()
    client = ViedocClient(conn(), transport=httpx.MockTransport(fake.handler))
    content = asyncio.run(client.run_export({"outputFormat": "CSV", "includeQueries": True}, poll_seconds=0))
    assert ("DELETE", "/api/clinic/dataexport/delete") in fake.calls
    from app.connectors.viedoc.client import describe_export_file

    text = "\n".join(describe_export_file(content))
    assert (
        "zip with 2 file(s)" in text and "Queries.csv: 1 rows, 4 columns" in text and "AE.csv: 2 rows" in text
    )
    assert "QueryText" in text and SECRET not in text and "1001-003" not in text and "Headache" not in text


def test_export_error_still_deletes() -> None:
    fake = FakeExport(finish="Error")
    client = ViedocClient(conn(), transport=httpx.MockTransport(fake.handler))
    with pytest.raises(ViedocError):
        asyncio.run(client.run_export({"includeQueries": True}, poll_seconds=0))
    assert fake.calls[-1] == ("DELETE", "/api/clinic/dataexport/delete")


def test_writes_other_than_the_export_are_refused() -> None:
    fake = FakeExport()
    client = ViedocClient(conn(), transport=httpx.MockTransport(fake.handler))
    refused = [
        ("POST", "admin/studysites"),
        ("PUT", "admin/studysites/1"),
        ("POST", "epro/accounts"),
        ("DELETE", "admin/users/1"),
    ]
    for method, path in refused:
        with pytest.raises(ViedocError, match="never changes Viedoc data"):
            asyncio.run(client._request(method, path))
    assert not any(p.startswith("/api/admin") or p.startswith("/api/epro") for _m, p in fake.calls)


def test_trial_export_command_prints_structure_only(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import app.check_viedoc as cli

    fake = FakeExport()
    real = cli.ViedocClient

    class Fast(real):  # type: ignore[misc, valid-type]
        async def run_export(self, options: dict[str, Any], **_kw: Any) -> bytes:
            return await super().run_export(options, poll_seconds=0)

    monkeypatch.setattr(
        cli,
        "ViedocClient",
        lambda c, allow_live=False: Fast(
            c, allow_live=allow_live, transport=httpx.MockTransport(fake.handler)
        ),
    )
    code = asyncio.run(
        run(
            argparse.Namespace(connection=None, try_path=None, save_spec=None, trial_export=True),
            _settings(sandbox=conn()),
        )
    )
    out = capsys.readouterr().out
    assert code == 0 and "deleted from Viedoc's server" in out and "Queries.csv: 1 rows" in out
    assert SECRET not in out and "1001-003" not in out and TOKEN not in out
