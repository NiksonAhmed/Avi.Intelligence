"""Tests the Graph client and live connector against a simulated Microsoft Graph (httpx.MockTransport)."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from app.connectors.sharepoint.graph_client import GraphClient, GraphError, site_lookup_path
from app.connectors.sharepoint.live import GraphSopConnector
from app.connectors.sharepoint.mapping import DEFAULT_FIELD_MAP
from app.connectors.sharepoint.models import SopStatus

SITE = "https://avion.sharepoint.com/sites/Quality"


def file_item(item_id: str, name: str, folder: str, **fields: Any) -> dict[str, Any]:
    return {
        "id": item_id,
        "fields": fields,
        "driveItem": {
            "id": f"DI{item_id}",
            "name": name,
            "size": 100,
            "file": {"mimeType": "application/pdf"},
            "parentReference": {"path": f"/drives/D1/root:/{folder}"},
        },
    }


class FakeGraph:
    """Routes requests like Microsoft Graph would. Records calls for assertions."""

    def __init__(self) -> None:
        self.calls: list[httpx.Request] = []
        self.token_calls = 0
        self.throttle_next = 0
        self.fail_token = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        url = request.url
        if url.host == "login.microsoftonline.com":
            self.token_calls += 1
            if self.fail_token:
                return httpx.Response(
                    401,
                    json={
                        "error": "invalid_client",
                        "error_description": "AADSTS7000215: Invalid client secret.",
                    },
                )
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        if url.host == "files.sharepoint.com":
            assert "authorization" not in request.headers  # token must not leak to download host
            return httpx.Response(200, content=b"%PDF-1.7 fake")
        assert request.headers["authorization"] == "Bearer tok"
        if self.throttle_next:
            self.throttle_next -= 1
            return httpx.Response(429, headers={"Retry-After": "1"})
        path = url.path
        if path == "/v1.0/sites/avion.sharepoint.com:/sites/Quality":
            return httpx.Response(200, json={"id": "SITE1"})
        if path == "/v1.0/sites/SITE1/drives":
            return httpx.Response(
                200,
                json={
                    "value": [
                        {"id": "D0", "name": "Documents", "webUrl": f"{SITE}/Shared%20Documents"},
                        {
                            "id": "D1",
                            "name": "Controlled Documents",
                            "webUrl": f"{SITE}/Controlled%20Documents",
                        },
                    ]
                },
            )
        if path == "/v1.0/drives/D1/list":
            return httpx.Response(200, json={"id": "L1"})
        if path == "/v1.0/sites/SITE1/lists/L1/items":
            if url.params.get("page") == "2":
                return httpx.Response(
                    200,
                    json={
                        "value": [
                            file_item("3", "SOP-003 Monitoring.pdf", "SOPs", DocumentStatus="Draft"),
                            file_item("4", "Template A.docx", "Templates"),
                        ]
                    },
                )
            return httpx.Response(
                200,
                json={
                    "value": [
                        {"id": "0", "driveItem": {"id": "F0", "name": "SOPs", "folder": {}}},
                        file_item(
                            "1",
                            "SOP-010 Site Activation.pdf",
                            "SOPs/Clinical",
                            DocumentStatus="Approved",
                            DocumentOwnerLookupId="7",
                        ),
                        file_item("2", "SOP-002 Training.pdf", "SOPs", _ModerationStatus=2),
                    ],
                    "@odata.nextLink": "https://graph.microsoft.com/v1.0/sites/SITE1/lists/L1/items?page=2",
                },
            )
        if path == "/v1.0/sites/SITE1/lists/User Information List/items/7":
            return httpx.Response(200, json={"fields": {"Title": "Head of Quality"}})
        if path == "/v1.0/sites/SITE1/lists/L1/columns":
            return httpx.Response(
                200,
                json={
                    "value": [
                        {"name": "DocumentStatus", "displayName": "Document Status", "choice": {}},
                        {"name": "_Hidden", "displayName": "Hidden", "hidden": True, "text": {}},
                    ]
                },
            )
        if path == "/v1.0/drives/D1/items/DI1/versions":
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "id": "2.0",
                            "lastModifiedDateTime": "2025-01-01T00:00:00Z",
                            "lastModifiedBy": {"user": {"displayName": "QA"}},
                            "size": 100,
                        },
                    ]
                },
            )
        if path == "/v1.0/drives/D1/items/DI1/content":
            return httpx.Response(302, headers={"Location": "https://files.sharepoint.com/dl?token=abc"})
        return httpx.Response(404, json={"error": {"code": "itemNotFound", "message": f"No route {path}"}})


async def _no_sleep(_s: float) -> None:
    return None


def make_connector(fake: FakeGraph, folder: str | None = "SOPs") -> GraphSopConnector:
    client = GraphClient("tenant", "client", "secret", transport=httpx.MockTransport(fake), sleep=_no_sleep)
    return GraphSopConnector(
        client,
        site_url=SITE,
        library="Controlled Documents",
        folder=folder,
        field_map=DEFAULT_FIELD_MAP,
        cache_seconds=300,
    )


def test_site_lookup_path() -> None:
    assert site_lookup_path(SITE) == "/sites/avion.sharepoint.com:/sites/Quality"
    assert site_lookup_path("https://avion.sharepoint.com/") == "/sites/avion.sharepoint.com"
    assert site_lookup_path("https://avion.sharepoint.com/sites/My Site") == (
        "/sites/avion.sharepoint.com:/sites/My%20Site"
    )
    with pytest.raises(ValueError):
        site_lookup_path("https://evil.example.com/sites/x")
    with pytest.raises(ValueError):
        site_lookup_path("http://avion.sharepoint.com/sites/x")


def test_lists_sops_with_pagination_folder_scope_and_people() -> None:
    fake = FakeGraph()
    connector = make_connector(fake)
    result = asyncio.run(connector.list_sops())
    numbers = [d.sop_number for d in result.documents]
    assert numbers == ["SOP-002", "SOP-003", "SOP-010"]  # folder + template excluded, natural sort
    by_number = {d.sop_number: d for d in result.documents}
    assert by_number["SOP-010"].status == SopStatus.EFFECTIVE
    assert by_number["SOP-010"].owner == "Head of Quality"
    assert by_number["SOP-002"].status == SopStatus.IN_REVIEW
    assert by_number["SOP-003"].status == SopStatus.DRAFT


def test_list_is_cached_until_refresh() -> None:
    fake = FakeGraph()
    connector = make_connector(fake)
    asyncio.run(connector.list_sops())
    calls = len(fake.calls)
    second = asyncio.run(connector.list_sops())
    assert second.from_cache and len(fake.calls) == calls
    asyncio.run(connector.list_sops(force_refresh=True))
    assert len(fake.calls) > calls
    assert fake.token_calls == 1  # token reused


def test_no_folder_scope_includes_everything() -> None:
    result = asyncio.run(make_connector(FakeGraph(), folder=None).list_sops())
    assert len(result.documents) == 4


def test_retries_throttled_requests() -> None:
    fake = FakeGraph()
    fake.throttle_next = 2
    result = asyncio.run(make_connector(fake).list_sops())
    assert len(result.documents) == 3


def test_token_failure_is_reported_without_secret() -> None:
    fake = FakeGraph()
    fake.fail_token = True
    with pytest.raises(GraphError) as exc:
        asyncio.run(make_connector(fake).list_sops())
    assert "AADSTS7000215" in str(exc.value)
    assert "secret" not in str(exc.value).replace("client secret", "")


def test_get_sop_rejects_ids_outside_scope() -> None:
    connector = make_connector(FakeGraph())
    assert asyncio.run(connector.get_sop("DI4")) is None  # template, outside SOPs folder
    assert asyncio.run(connector.get_sop("DI1")) is not None


def test_versions_and_download_stream_without_token_leak() -> None:
    connector = make_connector(FakeGraph())
    versions = asyncio.run(connector.list_versions("DI1"))
    assert [v.id for v in versions] == ["2.0"]

    async def read() -> bytes:
        dl = await connector.download("DI1")
        assert dl is not None
        assert dl.file_name == "SOP-010 Site Activation.pdf"
        return b"".join([c async for c in dl.content])

    assert asyncio.run(read()) == b"%PDF-1.7 fake"


def test_refuses_non_graph_next_link() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "login.microsoftonline.com":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        return httpx.Response(200, json={"value": [], "@odata.nextLink": "https://evil.example.com/steal"})

    client = GraphClient("t", "c", "s", transport=httpx.MockTransport(handler), sleep=_no_sleep)
    with pytest.raises(GraphError, match="non-Graph"):
        asyncio.run(client.get_all("/sites/x/lists"))


def test_rejects_unexpected_download_host() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "login.microsoftonline.com":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        return httpx.Response(302, headers={"Location": "https://evil.example.com/file"})

    client = GraphClient("t", "c", "s", transport=httpx.MockTransport(handler), sleep=_no_sleep)
    with pytest.raises(GraphError, match="Unexpected download host"):
        asyncio.run(client.download_url("/drives/D/items/I/content"))


def test_connection_check_reports_steps_and_columns() -> None:
    check = asyncio.run(make_connector(FakeGraph()).test_connection())
    assert check.ok
    assert [c.name for c in check.columns or []] == ["DocumentStatus"]
    assert check.document_count == 3


def test_connection_check_reports_missing_library() -> None:
    fake = FakeGraph()
    client = GraphClient("t", "c", "s", transport=httpx.MockTransport(fake), sleep=_no_sleep)
    connector = GraphSopConnector(
        client, site_url=SITE, library="Nope", folder=None, field_map=DEFAULT_FIELD_MAP, cache_seconds=0
    )
    check = asyncio.run(connector.test_connection())
    assert not check.ok
    assert "Available libraries: Controlled Documents, Documents" in (check.steps[-1].detail or "")


def test_approved_only_and_numbered_only_avion_layout() -> None:
    """Avion's layout: status from Approved / Draft Unapproved / Superseded folders, forms under SOPs."""
    root = "1. Avion SoPs/01. Clinical Operations"
    items = [
        file_item("1", "CO-SOP-005 Site Selection.pdf", f"{root}/Approved"),
        file_item("2", "CO-SOP-005 Site Selection_2.0.docx", f"{root}/Approved/Word_Documents_DoNotEdit"),
        file_item("3", "CO-SOP-005 Site Selection.pdf", f"{root}/Approved/Superseded"),
        file_item("4", "CO-SOP-006 Site Initiation_3.0.docx", f"{root}/DraftUnapproved"),
        file_item("5", "CO-005-A Site Qualification Visit Report_2.0.pdf", f"{root}/Approved"),
        file_item("6", "Complete_with_Docusign_CO-SOP-005_Site.pdf", f"{root}/Approved"),
        file_item("7", "CO-SOP-007 Essential Documents.pdf", f"{root}/Approved", DocumentStatus="Superseded"),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1.0/sites/SITE1/lists/L1/items":
            return httpx.Response(200, json={"value": items})
        return FakeGraph()(request)

    connector = GraphSopConnector(
        GraphClient("t", "c", "s", transport=httpx.MockTransport(handler), sleep=_no_sleep),
        site_url=SITE,
        library="Controlled Documents",
        folder="1. Avion SoPs",
        field_map=DEFAULT_FIELD_MAP,
        cache_seconds=0,
        approved_only=True,
        numbered_only=True,
    )
    docs = asyncio.run(connector.list_sops()).documents
    assert [(d.sop_number, d.kind.value, d.file_name) for d in docs] == [
        ("CO-005-A", "form", "CO-005-A Site Qualification Visit Report_2.0.pdf"),
        ("CO-SOP-005", "sop", "CO-SOP-005 Site Selection.pdf"),  # signed PDF, not the Word copy
    ]
    assert docs[0].parent_sop_number == "CO-SOP-005"
    assert docs[1].version == "2.0" and docs[1].department == "Clinical Operations"
    # The Word copy is attached to the signed PDF and can be downloaded through it.
    assert docs[1].editable_copy is not None and docs[1].editable_copy.id == "DI2"
    assert asyncio.run(connector.get_sop("DI2")) is None  # but it is not a listed document itself
    # Drafts and superseded versions cannot be opened or downloaded by id either.
    assert asyncio.run(connector.get_sop("DI4")) is None
    assert asyncio.run(connector.get_sop("DI3")) is None
    assert asyncio.run(connector.download("DI7")) is None


def test_exclusions_file_types_and_department_from_folder() -> None:
    fake = FakeGraph()
    client = GraphClient("t", "c", "s", transport=httpx.MockTransport(fake), sleep=_no_sleep)
    connector = GraphSopConnector(
        client,
        site_url=SITE,
        library="Controlled Documents",
        folder=None,
        field_map=DEFAULT_FIELD_MAP,
        cache_seconds=0,
        exclude_folders=["Templates"],
        file_types=["pdf"],
    )
    docs = asyncio.run(connector.list_sops()).documents
    assert [d.sop_number for d in docs] == ["SOP-002", "SOP-003", "SOP-010"]  # template excluded

    scoped = make_connector(FakeGraph())  # folder "SOPs"
    by_number = {d.sop_number: d for d in asyncio.run(scoped.list_sops()).documents}
    assert by_number["SOP-010"].department == "Clinical"  # from "SOPs/Clinical"
    assert by_number["SOP-002"].department is None  # directly in the SOP folder

    only_docx = GraphSopConnector(
        GraphClient("t", "c", "s", transport=httpx.MockTransport(FakeGraph()), sleep=_no_sleep),
        site_url=SITE,
        library="Controlled Documents",
        folder=None,
        field_map=DEFAULT_FIELD_MAP,
        cache_seconds=0,
        file_types=["docx"],
    )
    assert [d.file_name for d in asyncio.run(only_docx.list_sops()).documents] == ["Template A.docx"]
