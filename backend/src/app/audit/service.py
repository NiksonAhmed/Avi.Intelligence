from __future__ import annotations

import logging
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.auth.rbac import CurrentUser

from .models import AuditEvent

log = logging.getLogger("audit")


def record_event(
    db: Session,
    user: CurrentUser,
    *,
    action: str,
    entity_type: str,
    entity_id: str | None,
    summary: str,
    details: dict[str, Any] | None = None,
    request: Request | None = None,
) -> AuditEvent:
    event = AuditEvent(
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_name=user.name,
        actor_role=user.role.value,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary[:500],
        details=details or {},
        ip_address=request.client.host if request and request.client else None,
    )
    db.add(event)
    db.commit()
    log.info(
        "audit.event",
        extra={"action": action, "entity_type": entity_type, "entity_id": entity_id, "actor": user.id},
    )
    return event
