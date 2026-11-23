"""Microsoft Entra ID sign-in (user decision 2026-11-19).

The website signs people in with Microsoft and sends their access token for this app once to
`POST /auth/session`. The token is checked here and kept in an HttpOnly cookie, so every API call and
every plain download link (Excel, SOPs) carries it without extra code. The cookie is the Microsoft
token itself: nothing is stored on the server, and it expires when the token does.

Roles come from the app roles on the Avi.Intelligence app registration only (nothing else in the
organisation's Microsoft setup). Anyone at Avion who signs in without a role is a Viewer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jwt
from jwt import PyJWKClient

from app.auth.rbac import CurrentUser, Role
from app.core.config import Settings

COOKIE = "avi_session"
SCOPE_NAME = "access_as_user"

# When someone has more than one role, the one with the most access wins.
ROLE_PRIORITY: tuple[Role, ...] = (
    Role.ADMIN,
    Role.DIRECTOR,
    Role.PROJECT_MANAGER,
    Role.DATA_MANAGER,
    Role.QA,
    Role.SAFETY,
    Role.CLINICAL_OPERATIONS,
    Role.CRA,
    Role.CTA,
    Role.BUSINESS_DEVELOPMENT,
    Role.VIEWER,
)


# The app roles Avion created in Entra (user decision 2026-11-23): their Value -> our role. Compared
# without case, spaces or punctuation. ENTRA_ROLE_MAP in .env adds more.
DEFAULT_ROLE_MAP: dict[str, Role] = {
    "superadmin": Role.ADMIN,
    "director": Role.DIRECTOR,
    "clinops": Role.CLINICAL_OPERATIONS,
    "dm": Role.DATA_MANAGER,
    "datamanager": Role.DATA_MANAGER,
    "datamanagement": Role.DATA_MANAGER,
    "qa": Role.QA,
    "pm": Role.PROJECT_MANAGER,
    "projectmanager": Role.PROJECT_MANAGER,
}


def _key(value: object) -> str:
    return "".join(ch for ch in str(value).lower() if ch.isalnum())


@lru_cache
def role_map(raw_json: str | None) -> dict[str, Role]:
    """Our own role names, the built-in Entra names, then any from ENTRA_ROLE_MAP (unknown roles ignored)."""
    out = {_key(r.value): r for r in Role} | dict(DEFAULT_ROLE_MAP)
    if raw_json:
        try:
            extra = json.loads(raw_json)
        except json.JSONDecodeError:
            extra = {}
        for name, value in extra.items() if isinstance(extra, dict) else []:
            try:
                out[_key(name)] = Role(str(value).strip().lower())
            except ValueError:
                continue
    return out


class TokenError(Exception):
    """The token is missing, expired, forged or for another app or organisation."""


@dataclass(frozen=True)
class EntraConfig:
    tenant_id: str
    client_id: str

    @property
    def scope(self) -> str:
        return f"api://{self.client_id}/{SCOPE_NAME}"

    @property
    def authority(self) -> str:
        return f"https://login.microsoftonline.com/{self.tenant_id}"


def entra_config(settings: Settings) -> EntraConfig | None:
    if settings.entra_tenant_id and settings.entra_client_id:
        return EntraConfig(settings.entra_tenant_id, settings.entra_client_id)
    return None


@lru_cache
def _jwks(tenant_id: str) -> PyJWKClient:
    # Microsoft's public signing keys for the organisation (cached; refetched when a new key appears).
    return PyJWKClient(
        f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys", cache_keys=True, lifespan=3600
    )


def signing_key(token: str, tenant_id: str) -> Any:
    """Separate so tests can supply their own key (tests never call Microsoft)."""
    return _jwks(tenant_id).get_signing_key_from_jwt(token).key


def verify_token(token: str, cfg: EntraConfig) -> dict[str, Any]:
    tid = cfg.tenant_id
    try:
        claims: dict[str, Any] = jwt.decode(
            token,
            signing_key(token, tid),
            algorithms=["RS256"],
            audience=[cfg.client_id, f"api://{cfg.client_id}"],
            issuer=[f"https://login.microsoftonline.com/{tid}/v2.0", f"https://sts.windows.net/{tid}/"],
            options={"require": ["exp", "iss", "aud", "oid", "tid"]},
            leeway=60,
        )
    except (jwt.PyJWTError, OSError) as exc:
        raise TokenError(str(exc)) from exc
    if claims.get("tid") != tid:
        raise TokenError("Token is for another organisation.")
    # A person's delegated token, not an app-only one.
    if SCOPE_NAME not in str(claims.get("scp", "")).split():
        raise TokenError("Token is not a sign-in token for Avi.Intelligence.")
    return claims


def role_of(claims: dict[str, Any], names: dict[str, Role] | None = None) -> Role:
    names = names if names is not None else role_map(None)
    held = {names[_key(r)] for r in claims.get("roles", []) or [] if _key(r) in names}
    for role in ROLE_PRIORITY:
        if role in held:
            return role
    return Role.VIEWER


def user_from_claims(claims: dict[str, Any], names: dict[str, Role] | None = None) -> CurrentUser:
    email = str(claims.get("preferred_username") or claims.get("email") or claims.get("upn") or "")
    return CurrentUser(
        id=str(claims["oid"]),
        name=str(claims.get("name") or email or "Avion user"),
        email=email,
        role=role_of(claims, names),
    )
