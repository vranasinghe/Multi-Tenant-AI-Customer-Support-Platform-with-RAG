"""Tenant context: the transaction-local GUCs that Row-Level Security policies read.

``set_config(..., is_local => true)`` scopes values to the current transaction, so nothing leaks
to the next request on a pooled connection (and it is safe with PgBouncer transaction pooling).
Values are only ever derived server-side: the user id from a validated session, the org id from
a membership row the database returned for that user.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.identity import User
    from app.models.tenancy import Organization
    from app.services.tenancy.policy import Role

_SET = text("SELECT set_config(:name, :value, true)")


async def set_user_context(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.execute(_SET, {"name": "app.current_user_id", "value": str(user_id)})


async def set_org_context(db: AsyncSession, org_id: uuid.UUID) -> None:
    await db.execute(_SET, {"name": "app.current_org_id", "value": str(org_id)})


@dataclass(frozen=True)
class TenantContext:
    """Result of verifying, server-side, that ``user`` is a member of ``org`` with ``role``."""

    user: User
    org: Organization
    role: Role
    membership_id: uuid.UUID
