"""Role-based access control.

Authentication is a development stub for now: every request runs as a configurable local user.
Microsoft Entra ID sign-in replaces `get_current_user` in a later phase; route code stays the same
because it depends only on `require(permission)`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from fastapi import Depends, HTTPException, status

from app.core.config import get_settings


class Role(StrEnum):
    ADMIN = "admin"
    PROJECT_MANAGER = "project_manager"
    CRA = "cra"
    DATA_MANAGER = "data_manager"
    SAFETY = "safety"
    VIEWER = "viewer"


class Permission(StrEnum):
    SOP_READ = "sop.read"
    SOP_DOWNLOAD = "sop.download"
    CONNECTOR_MANAGE = "connector.manage"
    AUDIT_READ = "audit.read"
    ASSISTANT_USE = "assistant.use"


ROLE_LABELS: dict[Role, str] = {
    Role.ADMIN: "Administrator",
    Role.PROJECT_MANAGER: "Project Manager",
    Role.CRA: "Clinical Research Associate",
    Role.DATA_MANAGER: "Data Manager",
    Role.SAFETY: "Safety / Pharmacovigilance",
    Role.VIEWER: "Viewer",
}

_ALL_STAFF = {Permission.SOP_READ, Permission.SOP_DOWNLOAD, Permission.ASSISTANT_USE}

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.ADMIN: frozenset(Permission),
    Role.PROJECT_MANAGER: frozenset(_ALL_STAFF | {Permission.AUDIT_READ}),
    Role.CRA: frozenset(_ALL_STAFF),
    Role.DATA_MANAGER: frozenset(_ALL_STAFF),
    Role.SAFETY: frozenset(_ALL_STAFF),
    Role.VIEWER: frozenset({Permission.SOP_READ, Permission.ASSISTANT_USE}),
}


@dataclass(frozen=True)
class CurrentUser:
    id: str
    name: str
    email: str
    role: Role
    tenant_id: str = "avion"

    @property
    def permissions(self) -> frozenset[Permission]:
        return ROLE_PERMISSIONS[self.role]

    def can(self, permission: Permission) -> bool:
        return permission in self.permissions


def get_current_user() -> CurrentUser:
    settings = get_settings()
    if settings.app_env == "production":
        # Never fall back to an implicit user in production.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign-in is not configured.")
    try:
        role = Role(settings.dev_user_role)
    except ValueError:
        role = Role.VIEWER
    return CurrentUser(id="dev-user", name="Local Developer", email="dev@localhost", role=role)


def require(permission: Permission) -> Callable[..., CurrentUser]:
    def dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:  # noqa: B008
        if not user.can(permission):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Missing permission: {permission.value}")
        return user

    return dependency
