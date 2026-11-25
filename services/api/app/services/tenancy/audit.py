"""Append-only audit trail for sensitive tenant actions (docs/SECURITY.md §14).

Callers must have set the org context (the INSERT policy requires it). Metadata must never hold
secrets, tokens or passwords; emails are limited to what the audited action is about.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.models.identity import User
from app.models.tenancy import AuditLog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.request_meta import RequestMeta


async def record_audit(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    action: str,
    meta: RequestMeta,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
    metadata: dict[str, Any] | None = None,
    actor_type: str = "user",
) -> None:
    db.add(
        AuditLog(
            org_id=org_id,
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            meta=metadata or {},
            ip_prefix=meta.ip_prefix,
            request_id=meta.request_id,
        )
    )
    await db.flush()


async def list_audit_logs(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    limit: int,
    before: tuple[datetime, uuid.UUID] | None,
    action: str | None,
) -> list[tuple[AuditLog, User | None]]:
    stmt = (
        select(AuditLog, User)
        .outerjoin(User, User.id == AuditLog.actor_id)
        .where(AuditLog.org_id == org_id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit + 1)
    )
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if before:
        stmt = stmt.where(
            (AuditLog.created_at < before[0])
            | ((AuditLog.created_at == before[0]) & (AuditLog.id < before[1]))
        )
    return [(row[0], row[1]) for row in (await db.execute(stmt)).all()]
