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

from app.auth.directory import get_person
from app.core.config import get_settings


class Role(StrEnum):
    ADMIN = "admin"
    PROJECT_MANAGER = "project_manager"
    CRA = "cra"
    CTA = "cta"
    DATA_MANAGER = "data_manager"
    SAFETY = "safety"
    QA = "qa"
    VIEWER = "viewer"


class Permission(StrEnum):
    SOP_READ = "sop.read"
    SOP_DOWNLOAD = "sop.download"
    CONNECTOR_MANAGE = "connector.manage"
    AUDIT_READ = "audit.read"
    ASSISTANT_USE = "assistant.use"
    STUDY_READ = "study.read"
    WORK_MANAGE = "work.manage"
    """Administrators: manage every task, risk and issue."""
    TASK_ASSIGN_STUDY = "task.assign.study"
    TASK_ASSIGN_SOP = "task.assign.sop"
    TASK_ASSIGN_VENDOR = "task.assign.vendor"
    TASK_ASSIGN_SYSTEM = "task.assign.system"
    TASK_ASSIGN_GENERAL = "task.assign.general"
    """task.assign.<category>: create, assign to anyone, edit and cancel tasks of that category."""
    TASK_CREATE_OWN = "task.create_own"
    """Create tasks assigned only to yourself, for your own tracking (never Procedures and SOPs)."""
    STUDY_SYNC = "study.sync"
    """Press Sync now to refresh the SimpleTrials copy (everyone; read-only towards SimpleTrials)."""
    CONFERENCE_VIEW = "conference.view"
    """See the Conferences page (where Avion's BD team is going): everyone."""
    CONFERENCE_COST = "conference.cost"
    """See conference costs: administrators only for now (no BD role yet)."""
    DM_VIEW = "dm.view"
    """See the Data Management tab (Viedoc queries, missing data)."""
    DM_SYNC = "dm.sync"
    """Run a Data Management sync from Viedoc now (everyone; read-only towards Viedoc)."""
    DM_EXPORT = "dm.export"
    """Download Data Management data (Excel files, exports): System Admin and Data Manager only."""


ROLE_LABELS: dict[Role, str] = {
    Role.ADMIN: "Administrator",
    Role.PROJECT_MANAGER: "Project Manager",
    Role.CRA: "Clinical Research Associate",
    Role.CTA: "Clinical Trials Associate",
    Role.DATA_MANAGER: "Data Manager",
    Role.SAFETY: "Pharmacovigilance",
    Role.QA: "Quality Assurance",
    Role.VIEWER: "Viewer",
}

_ALL_STAFF = {
    Permission.SOP_READ,
    Permission.SOP_DOWNLOAD,
    Permission.ASSISTANT_USE,
    Permission.STUDY_READ,
    Permission.TASK_CREATE_OWN,
    Permission.DM_VIEW,  # user decision: everyone may view Data Management (read-only)
    Permission.DM_SYNC,  # user decision: everyone may press Sync now
    Permission.STUDY_SYNC,  # user decision: everyone may sync SimpleTrials from a report
    Permission.CONFERENCE_VIEW,
}

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.ADMIN: frozenset(Permission),
    # Project Managers assign Study and General tasks (not Procedures and SOPs).
    Role.PROJECT_MANAGER: frozenset(
        _ALL_STAFF
        | {
            Permission.AUDIT_READ,
            Permission.TASK_ASSIGN_STUDY,
            Permission.TASK_ASSIGN_GENERAL,
            Permission.DM_VIEW,
        }
    ),
    Role.CRA: frozenset(_ALL_STAFF),  # view only: CRAs do not download (user decision)
    Role.CTA: frozenset(_ALL_STAFF),
    Role.DATA_MANAGER: frozenset(_ALL_STAFF | {Permission.DM_EXPORT}),
    Role.SAFETY: frozenset(_ALL_STAFF),
    # QA assigns Procedures and SOPs, Vendor, Computer system and General tasks.
    Role.QA: frozenset(
        _ALL_STAFF
        | {
            Permission.AUDIT_READ,
            Permission.TASK_ASSIGN_SOP,
            Permission.TASK_ASSIGN_VENDOR,
            Permission.TASK_ASSIGN_SYSTEM,
            Permission.TASK_ASSIGN_GENERAL,
            Permission.DM_VIEW,
        }
    ),
    Role.VIEWER: frozenset(
        {
            Permission.SOP_READ,
            Permission.ASSISTANT_USE,
            Permission.STUDY_READ,
            Permission.DM_VIEW,
            Permission.DM_SYNC,
            Permission.STUDY_SYNC,
            Permission.CONFERENCE_VIEW,
        }
    ),
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
    person = get_person(settings.dev_user_id) or get_person("dev-user")
    assert person is not None
    return CurrentUser(id=person.id, name=person.name, email=person.email, role=role)


def require(permission: Permission) -> Callable[..., CurrentUser]:
    def dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:  # noqa: B008
        if not user.can(permission):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Missing permission: {permission.value}")
        return user

    return dependency
