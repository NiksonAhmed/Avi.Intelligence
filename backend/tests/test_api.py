from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.api.sops import content_disposition, is_review_due
from app.auth.rbac import Role
from app.connectors.sharepoint.mock import MockSopConnector
from app.connectors.sharepoint.models import SopStatus


def test_health(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok"}


def test_security_headers(client: TestClient) -> None:
    res = client.get("/api/health")
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["X-Frame-Options"] == "DENY"
    assert "X-Request-ID" in res.headers


def test_list_sops_returns_documents_summary_and_source(client: TestClient) -> None:
    body = client.get("/api/v1/sops").json()
    assert body["total_unfiltered"] == len(body["documents"]) == 18  # 15 SOPs + 3 forms
    assert body["source"]["mode"] == "mock"
    sops = [d for d in body["documents"] if d["kind"] == "sop"]
    assert body["summary"]["total"] == 15 and body["summary"]["forms"] == 3
    assert body["summary"]["effective"] == sum(d["status"] == "Effective" for d in sops)
    assert "Clinical Operations" in body["departments"]


def test_list_sops_filters(client: TestClient) -> None:
    body = client.get("/api/v1/sops", params={"q": "site activation"}).json()
    assert [d["sop_number"] for d in body["documents"]] == ["SOP-011"]
    body = client.get("/api/v1/sops", params={"status": "Draft"}).json()
    assert {d["status"] for d in body["documents"]} == {"Draft"}
    body = client.get("/api/v1/sops", params={"department": "pharmacovigilance"}).json()
    assert len(body["documents"]) == 2
    assert body["total_unfiltered"] == 18  # summary is unaffected by filters


def test_invalid_status_rejected(client: TestClient) -> None:
    assert client.get("/api/v1/sops", params={"status": "Bogus"}).status_code == 422


def test_get_sop_detail(client: TestClient) -> None:
    body = client.get("/api/v1/sops/demo-sop-011").json()
    assert body["document"]["title"] == "Site Activation"
    assert "versions" not in body  # SharePoint save history is not shown (saves are not versions)
    assert [f["sop_number"] for f in body["forms"]] == ["SOP-011-A", "SOP-011-B"]
    assert body["parent"] is None


def test_form_detail_links_to_its_sop(client: TestClient) -> None:
    body = client.get("/api/v1/sops/demo-sop-011-b").json()
    assert body["document"]["kind"] == "form"
    assert body["parent"]["sop_number"] == "SOP-011"
    assert body["forms"] == []


def test_get_sop_not_found_and_bad_id(client: TestClient) -> None:
    assert client.get("/api/v1/sops/does-not-exist").status_code == 404
    assert client.get("/api/v1/sops/bad%20id%3B").status_code == 422


def test_download_streams_file_and_writes_audit(client: TestClient) -> None:
    res = client.get("/api/v1/sops/demo-sop-011/download")
    assert res.status_code == 200
    assert b"DEMO DOCUMENT" in res.content
    assert res.headers["content-disposition"].startswith("attachment;")
    assert res.headers["cache-control"] == "no-store"

    audit = client.get("/api/v1/audit-events").json()
    assert audit["total"] == 1
    event = audit["items"][0]
    assert event["action"] == "sop.downloaded"
    assert event["entity_id"] == "demo-sop-011"
    assert "Site Activation" in event["summary"]


def test_forms_can_be_downloaded_as_word(client: TestClient) -> None:
    detail = client.get("/api/v1/sops/demo-sop-011-a").json()["document"]
    assert detail["file_name"].endswith(".pdf")
    assert detail["editable_copy"]["file_name"].endswith(".docx")

    res = client.get("/api/v1/sops/demo-sop-011-a/download", params={"format": "word"})
    assert res.status_code == 200
    assert (
        "SOP-011-A Site Initiation Visit Report Template v3.0 (DEMO).txt"
        in res.headers["content-disposition"]
    )
    event = client.get("/api/v1/audit-events").json()["items"][0]
    assert event["summary"].endswith("as Word") and event["details"]["format"] == "word"


def test_sops_are_not_issued_as_word(client: TestClient) -> None:
    res = client.get("/api/v1/sops/demo-sop-011/download", params={"format": "word"})
    assert res.status_code == 400
    # The Word copy cannot be fetched directly by its own id either: it is not a listed document.
    assert client.get("/api/v1/sops/demo-sop-011-a-word/download").status_code == 404


def test_refresh(client: TestClient) -> None:
    assert client.post("/api/v1/sops/refresh").status_code == 204


def test_me(make_client) -> None:  # type: ignore[no-untyped-def]
    body = make_client(Role.CRA).get("/api/v1/me").json()
    assert body["role"] == "cra"
    assert body["role_label"] == "Clinical Research Associate"
    assert "sop.download" in body["permissions"]
    assert "connector.manage" not in body["permissions"]


def test_viewer_can_read_but_not_download(make_client) -> None:  # type: ignore[no-untyped-def]
    viewer = make_client(Role.VIEWER)
    assert viewer.get("/api/v1/sops").status_code == 200
    assert viewer.get("/api/v1/sops/demo-sop-011/download").status_code == 403


def test_only_admin_manages_connectors(make_client) -> None:  # type: ignore[no-untyped-def]
    assert make_client(Role.PROJECT_MANAGER).get("/api/v1/connectors/sharepoint").status_code == 403
    res = make_client(Role.ADMIN).get("/api/v1/connectors/sharepoint")
    assert res.status_code == 200
    assert res.json()["info"]["mode"] == "mock"
    assert res.json()["check"]["ok"] is False


def test_audit_requires_permission(make_client) -> None:  # type: ignore[no-untyped-def]
    assert make_client(Role.CRA).get("/api/v1/audit-events").status_code == 403
    assert make_client(Role.PROJECT_MANAGER).get("/api/v1/audit-events").status_code == 200


def test_content_disposition_handles_unicode_and_quotes() -> None:
    header = content_disposition('SOP "Café".docx')
    assert 'filename="SOP _Caf__.docx"' in header
    assert "filename*=UTF-8''SOP%20%22Caf%C3%A9%22.docx" in header


def test_review_due_window() -> None:
    doc = MockSopConnector("t")._docs[0]
    now = datetime(2026, 1, 1, tzinfo=UTC)
    soon = doc.model_copy(update={"review_date": now + timedelta(days=10), "status": SopStatus.EFFECTIVE})
    later = doc.model_copy(update={"review_date": now + timedelta(days=90)})
    draft = soon.model_copy(update={"status": SopStatus.DRAFT})
    assert is_review_due(soon, now)
    assert not is_review_due(later, now)
    assert not is_review_due(draft, now)
