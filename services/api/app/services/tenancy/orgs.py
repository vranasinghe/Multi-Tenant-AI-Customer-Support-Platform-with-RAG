"""Organization use cases: create, list, update."""

from __future__ import annotations

import re
import secrets
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.core.ids import new_id
from app.models.tenancy import Membership, Organization
from app.services.tenancy.audit import record_audit
from app.services.tenancy.context import set_org_context, set_user_context
from app.services.tenancy.policy import Role

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.request_meta import RequestMeta
    from app.models.identity import User


def make_slug(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "org"
    return f"{base}-{secrets.token_hex(3)}"


async def create_organization(
    db: AsyncSession, *, creator: User, name: str, meta: RequestMeta
) -> tuple[Organization, Membership]:
    """New org with ``creator`` as its owner. Sets the tenant context for the new org id, which
    is generated here, so a client can never pick or collide with an existing tenant."""
    org_id = new_id()
    await set_user_context(db, creator.id)
    await set_org_context(db, org_id)
    org = Organization(id=org_id, name=name, slug=make_slug(name), created_by=creator.id)
    db.add(org)
    await db.flush()
    membership = Membership(org_id=org_id, user_id=creator.id, role=Role.OWNER.value)
    db.add(membership)
    await db.flush()
    await record_audit(
        db,
        org_id=org_id,
        actor_id=creator.id,
        action="org.created",
        target_type="organization",
        target_id=org_id,
        metadata={"name": name},
        meta=meta,
    )
    return org, membership


async def list_user_orgs(db: AsyncSession, user_id: uuid.UUID) -> list[tuple[Organization, str]]:
    """Orgs the user belongs to (RLS: only the user's own memberships are visible without an
    org context)."""
    await set_user_context(db, user_id)
    stmt = (
        select(Organization, Membership.role)
        .join(Membership, Membership.org_id == Organization.id)
        .where(Membership.user_id == user_id, Organization.deleted_at.is_(None))
        .order_by(Organization.created_at)
    )
    return [(row[0], row[1]) for row in (await db.execute(stmt)).all()]


async def update_organization(
    db: AsyncSession,
    *,
    org: Organization,
    actor_id: uuid.UUID,
    name: str | None,
    settings: dict[str, Any] | None,
    meta: RequestMeta,
) -> None:
    changes: dict[str, Any] = {}
    if name is not None and name != org.name:
        changes["name"] = {"from": org.name, "to": name}
        org.name = name
    if settings:
        merged = {**org.settings, **settings}
        if merged != org.settings:
            changes["settings"] = sorted(settings)
            org.settings = merged
    if not changes:
        return
    await db.flush()
    await record_audit(
        db,
        org_id=org.id,
        actor_id=actor_id,
        action="org.updated",
        target_type="organization",
        target_id=org.id,
        metadata=changes,
        meta=meta,
    )
