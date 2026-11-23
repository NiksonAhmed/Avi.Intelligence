"""Microsoft Entra ID sign-in (user decision 2026-11-19). Tokens are signed with a test key: tests never call
Microsoft."""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth import entra
from app.auth.rbac import Role
from app.core.config import get_settings
from app.db.session import get_db
from app.main import create_app

TENANT = "11111111-1111-1111-1111-111111111111"
CLIENT = "22222222-2222-2222-2222-222222222222"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def token(*, key: Any = KEY, **overrides: Any) -> str:
    now = int(time.time())
    claims: dict[str, Any] = {
        "iss": f"https://login.microsoftonline.com/{TENANT}/v2.0",
        "aud": CLIENT,
        "tid": TENANT,
        "oid": "oid-1",
        "name": "Avion Person",
        "preferred_username": "person@avion.example",
        "scp": "access_as_user",
        "iat": now,
        "nbf": now,
        "exp": now + 3600,
    }
    claims.update(overrides)
    return jwt.encode({k: v for k, v in claims.items() if v is not None}, key, algorithm="RS256")


def bearer(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture
def entra_on(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("ENTRA_TENANT_ID", TENANT)
    monkeypatch.setenv("ENTRA_CLIENT_ID", CLIENT)
    monkeypatch.setattr(entra, "signing_key", lambda _token, _tenant: KEY.public_key())
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def api(db_session: Session) -> TestClient:
    app = create_app()  # the real sign-in, not the test user
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


def test_config_is_public_and_says_which_sign_in(api: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    assert api.get("/api/v1/auth/config").json() == {
        "mode": "development",
        "tenant_id": None,
        "client_id": None,
        "authority": None,
        "scope": None,
    }
    monkeypatch.setenv("ENTRA_TENANT_ID", TENANT)
    monkeypatch.setenv("ENTRA_CLIENT_ID", CLIENT)
    get_settings.cache_clear()
    try:
        body = api.get("/api/v1/auth/config").json()
    finally:
        get_settings.cache_clear()
    assert body["mode"] == "entra" and body["scope"] == f"api://{CLIENT}/access_as_user"
    assert body["authority"] == f"https://login.microsoftonline.com/{TENANT}"


@pytest.mark.usefixtures("entra_on")
def test_admin_role_from_the_app_registration(api: TestClient) -> None:
    me = api.get("/api/v1/me", headers=bearer(token(roles=["admin"]))).json()
    assert me["role"] == "admin" and me["auth_mode"] == "entra"
    assert me["name"] == "Avion Person" and me["email"] == "person@avion.example" and me["id"] == "oid-1"


@pytest.mark.usefixtures("entra_on")
def test_everyone_else_is_a_viewer(api: TestClient) -> None:
    t = token()  # signed in, no role on the app
    assert api.get("/api/v1/me", headers=bearer(t)).json()["role"] == "viewer"
    assert api.get("/api/v1/site-feasibility", headers=bearer(t)).status_code == 200  # all staff may view
    assert api.get("/api/v1/audit-events", headers=bearer(t)).status_code == 403  # Admin only


def test_role_choice() -> None:
    assert entra.role_of({"roles": ["cra", "project_manager"]}) == Role.PROJECT_MANAGER  # most access wins
    assert entra.role_of({"roles": ["Admin"]}) == Role.ADMIN  # case does not matter
    assert entra.role_of({"roles": ["SomethingElse"]}) == Role.VIEWER
    assert entra.role_of({}) == Role.VIEWER


@pytest.mark.usefixtures("entra_on")
@pytest.mark.parametrize(
    "bad",
    [
        pytest.param(lambda: None, id="no token"),
        pytest.param(lambda: token(exp=int(time.time()) - 3600), id="expired"),
        pytest.param(lambda: token(aud="another-app"), id="another app"),
        pytest.param(lambda: token(tid="33333333-3333-3333-3333-333333333333"), id="another organisation"),
        pytest.param(lambda: token(iss="https://evil.example/"), id="wrong issuer"),
        pytest.param(lambda: token(scp=None, roles=["admin"]), id="app-only token"),
        pytest.param(lambda: token(key=OTHER_KEY, roles=["admin"]), id="forged"),
        pytest.param(lambda: "not-a-token", id="garbage"),
    ],
)
def test_bad_tokens_are_refused(api: TestClient, bad: Any) -> None:
    t = bad()
    assert api.get("/api/v1/me", headers=bearer(t) if t else {}).status_code == 401


@pytest.mark.usefixtures("entra_on")
def test_session_cookie_carries_the_sign_in_for_links_and_downloads(api: TestClient) -> None:
    r = api.post("/api/v1/auth/session", headers=bearer(token(roles=["admin"])))
    assert r.status_code == 204
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "path=/api" in cookie
    # No header: the cookie alone signs the request in (as plain Excel links do).
    assert api.get("/api/v1/me").json()["role"] == "admin"
    assert api.get("/api/v1/site-feasibility/export.xlsx").status_code == 200
    # Renewing the cookie is not a new sign-in; only the first is audited.
    assert api.post("/api/v1/auth/session", headers=bearer(token(roles=["admin"]))).status_code == 204
    events = api.get("/api/v1/audit-events").json()["items"]
    assert [e["action"] for e in events].count("user.signed_in") == 1
    # Signing out clears it.
    assert api.delete("/api/v1/auth/session").status_code == 204
    assert api.get("/api/v1/me").status_code == 401


@pytest.mark.usefixtures("entra_on")
def test_session_needs_a_valid_token(api: TestClient) -> None:
    assert api.post("/api/v1/auth/session").status_code == 401
    assert api.post("/api/v1/auth/session", headers=bearer(token(aud="x"))).status_code == 401


def test_session_is_refused_when_sign_in_is_off(api: TestClient) -> None:
    assert api.post("/api/v1/auth/session", headers=bearer("x")).status_code == 404


def test_production_still_needs_sign_in(api: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()
    try:
        assert api.get("/api/v1/me").status_code == 401
    finally:
        get_settings.cache_clear()


def test_avions_entra_roles() -> None:
    """The app roles Avion created in Entra (user decision 2026-11-23)."""
    names = entra.role_map(None)
    assert entra.role_of({"roles": ["SuperAdmin"]}, names) == Role.ADMIN
    assert entra.role_of({"roles": ["Director"]}, names) == Role.DIRECTOR
    assert entra.role_of({"roles": ["ClinOps"]}, names) == Role.CLINICAL_OPERATIONS
    assert entra.role_of({"roles": ["DM"]}, names) == Role.DATA_MANAGER
    assert entra.role_of({"roles": ["Data Manager"]}, names) == Role.DATA_MANAGER
    assert entra.role_of({"roles": ["DataManagement"]}, names) == Role.DATA_MANAGER  # as created in Entra
    assert entra.role_of({"roles": ["QA"]}, names) == Role.QA
    assert entra.role_of({"roles": ["PM"]}, names) == Role.PROJECT_MANAGER
    assert entra.role_of({"roles": ["ClinOps", "Director"]}, names) == Role.DIRECTOR  # most access wins
    assert entra.role_of({"roles": ["admin"]}, names) == Role.ADMIN  # our own names still work
    extra = entra.role_map('{"Physicist": "clinical_operations", "Bad": "no-such-role"}')
    assert entra.role_of({"roles": ["Physicist"]}, extra) == Role.CLINICAL_OPERATIONS
    assert entra.role_of({"roles": ["Bad"]}, extra) == Role.VIEWER
    assert entra.role_of({"roles": ["Physicist"]}, entra.role_map("not json")) == Role.VIEWER


def test_director_sees_everything_but_the_settings() -> None:
    from app.auth.rbac import ROLE_PERMISSIONS, Permission

    director = ROLE_PERMISSIONS[Role.DIRECTOR]
    assert Permission.AUDIT_READ in director and Permission.DM_EXPORT not in director  # Admin and DM only
    assert Permission.TASK_ASSIGN_STUDY in director and Permission.TASK_ASSIGN_SOP in director
    assert Permission.CONNECTOR_MANAGE not in director and Permission.WORK_MANAGE not in director
    assert ROLE_PERMISSIONS[Role.CLINICAL_OPERATIONS] == ROLE_PERMISSIONS[Role.CRA]


@pytest.mark.usefixtures("entra_on")
def test_signed_in_director_and_clinops(api: TestClient) -> None:
    me = api.get("/api/v1/me", headers=bearer(token(roles=["Director"]))).json()
    assert me["role"] == "director" and me["role_label"] == "Director"
    assert api.get("/api/v1/audit-events", headers=bearer(token(roles=["Director"]))).status_code == 200
    assert (
        api.get("/api/v1/connectors/sharepoint", headers=bearer(token(roles=["Director"]))).status_code == 403
    )
    views = api.get("/api/v1/overview", headers=bearer(token(roles=["Director"]))).json()["views"]
    assert len(views) > 1  # may look at other roles' Overviews
    clin = api.get("/api/v1/overview", headers=bearer(token(roles=["ClinOps"]))).json()
    assert clin["view"] == "clinical_operations" and len(clin["views"]) == 1
