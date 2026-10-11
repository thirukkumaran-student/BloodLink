"""Audit trail helper (owner: D1)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from bloodlink_api.core.clock import utcnow
from bloodlink_api.core.context import Principal
from bloodlink_api.db.models.identity import AuditLog


def record(
    db: Session,
    *,
    action: str,
    actor: Principal | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    detail: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    """Append an audit entry. Never store patient identity or clinical detail."""
    entry = AuditLog(
        actor_user_id=actor.user_id if actor else None,
        actor_role=actor.role if actor else None,
        organization_id=actor.organization_id if actor else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        detail=detail,
        ip_address=ip_address,
        created_at=utcnow(),
    )
    db.add(entry)
    return entry
