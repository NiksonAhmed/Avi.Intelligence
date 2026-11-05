"""Administration, current-user and audit-trail endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.models import AuditEvent
from app.audit.service import record_event
from app.auth.rbac import ROLE_LABELS, CurrentUser, Permission, get_current_user, require
from app.connectors.sharepoint import get_sop_connector
from app.connectors.sharepoint.models import ConnectionCheck, ConnectorInfo, SopConnector
from app.db.session import get_db

router = APIRouter()


class MeResponse(BaseModel):
    id: str
    name: str
    email: str
    role: str
    role_label: str
    permissions: list[str]
    auth_mode: str


@router.get("/me", response_model=MeResponse, tags=["Users"])
def me(user: Annotated[CurrentUser, Depends(get_current_user)]) -> MeResponse:
    return MeResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        role=user.role.value,
        role_label=ROLE_LABELS[user.role],
        permissions=sorted(p.value for p in user.permissions),
        auth_mode="development",
    )


class SharePointStatusResponse(BaseModel):
    info: ConnectorInfo
    check: ConnectionCheck


@router.get("/connectors/sharepoint", response_model=SharePointStatusResponse, tags=["Administration"])
async def sharepoint_status(
    request: Request,
    connector: Annotated[SopConnector, Depends(get_sop_connector)],
    user: Annotated[CurrentUser, Depends(require(Permission.CONNECTOR_MANAGE))],
    db: Annotated[Session, Depends(get_db)],
) -> SharePointStatusResponse:
    check = await connector.test_connection()
    record_event(
        db,
        user,
        action="connector.tested",
        entity_type="connector",
        entity_id="sharepoint",
        summary=f"Tested SharePoint connection ({'passed' if check.ok else 'failed'})",
        details={"ok": check.ok, "mode": connector.info().mode},
        request=request,
    )
    return SharePointStatusResponse(info=connector.info(), check=check)


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    occurred_at: datetime
    actor_name: str
    actor_role: str
    action: str
    entity_type: str
    entity_id: str | None
    summary: str
    details: dict[str, Any]


class AuditPage(BaseModel):
    items: list[AuditEventOut]
    total: int


@router.get("/audit-events", response_model=AuditPage, tags=["Audit"])
def list_audit_events(
    user: Annotated[CurrentUser, Depends(require(Permission.AUDIT_READ))],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditPage:
    base = select(AuditEvent).where(AuditEvent.tenant_id == user.tenant_id)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(base.order_by(AuditEvent.occurred_at.desc()).limit(limit).offset(offset)).all()
    return AuditPage(items=[AuditEventOut.model_validate(r) for r in rows], total=total)
