"""Sign-in endpoints: what the website needs to start Microsoft sign-in, and the session cookie."""

from __future__ import annotations

import time
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.audit.service import record_event
from app.auth import entra
from app.auth.rbac import bearer_token
from app.core.config import get_settings
from app.db.session import get_db

router = APIRouter(prefix="/auth", tags=["Sign-in"])


class AuthConfig(BaseModel):
    mode: Literal["entra", "development"]
    tenant_id: str | None = None
    client_id: str | None = None
    authority: str | None = None
    scope: str | None = None


@router.get("/config", response_model=AuthConfig)
def auth_config() -> AuthConfig:
    """Public (no sign-in): the website reads this before it can sign anyone in. None of it is secret."""
    cfg = entra.entra_config(get_settings())
    if cfg is None:
        return AuthConfig(mode="development")
    return AuthConfig(
        mode="entra",
        tenant_id=cfg.tenant_id,
        client_id=cfg.client_id,
        authority=cfg.authority,
        scope=cfg.scope,
    )


def _secure(request: Request) -> bool:
    forwarded = request.headers.get("x-forwarded-proto", "")
    return get_settings().app_env == "production" or request.url.scheme == "https" or forwarded == "https"


@router.post("/session", status_code=status.HTTP_204_NO_CONTENT)
def start_session(request: Request, response: Response, db: Annotated[Session, Depends(get_db)]) -> None:
    """Checks the Microsoft token sent in the Authorization header and keeps it in an HttpOnly cookie."""
    cfg = entra.entra_config(get_settings())
    if cfg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Microsoft sign-in is not switched on.")
    token = bearer_token(request)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please sign in.")
    try:
        claims = entra.verify_token(token, cfg)
    except entra.TokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign-in failed. Please sign in again.") from exc
    user = entra.user_from_claims(claims, entra.role_map(get_settings().entra_role_map))
    response.set_cookie(
        entra.COOKIE,
        token,
        max_age=max(0, int(claims["exp"]) - int(time.time())),
        path="/api",
        httponly=True,
        secure=_secure(request),
        samesite="strict",
    )
    # The website renews the cookie before the token expires; only a fresh sign-in is audited.
    if entra.COOKIE not in request.cookies:
        record_event(
            db,
            user,
            action="user.signed_in",
            entity_type="user",
            entity_id=user.id,
            summary=f"Signed in with Microsoft as {user.role.value}",
            # The app-role values Microsoft sent (e.g. ["SuperAdmin"]): shows why someone got their role.
            details={"role": user.role.value, "entra_roles": [str(r) for r in claims.get("roles", []) or []]},
            request=request,
        )


@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT)
def end_session(request: Request, response: Response) -> None:
    response.delete_cookie(
        entra.COOKIE, path="/api", httponly=True, secure=_secure(request), samesite="strict"
    )
