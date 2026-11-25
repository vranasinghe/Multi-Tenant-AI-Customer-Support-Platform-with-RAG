"""FastAPI dependencies: startup objects, DB session, authentication and tenant authorization.

Authorization pipeline for every org-scoped route (docs/ARCHITECTURE.md §6):

1. ``get_auth``: session cookie → SHA-256 → ``sessions`` row (not revoked/expired/idle, user
   active). Sets the ``app.current_user_id`` GUC from that row — never from client input.
2. ``get_tenant_context``: loads *the caller's own* membership for the ``org_id`` in the URL. A
   non-member gets 404 (existence is never revealed). Only then is ``app.current_org_id`` set,
   from the row the database returned.
3. ``require(permission)``: role → permission check (403), email verification (403), and
   read-only enforcement for restricted orgs.

The org id in the path is an untrusted claim that step 2 verifies on every request.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable, Coroutine
from dataclasses import dataclass
from typing import Annotated, Any, cast

from fastapi import BackgroundTasks, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.cookies import SESSION_COOKIE
from app.core.config import Settings
from app.core.errors import ApiError, forbidden, not_found, unauthenticated
from app.core.logging import get_logger
from app.core.request_meta import RequestMeta
from app.models.identity import User, utcnow
from app.models.tenancy import Membership, Organization
from app.services.chat_access import ChatAccess
from app.services.container import AppServices, MailQueue
from app.services.identity.sessions import find_active_session, touch_session
from app.services.readiness import ReadinessService
from app.services.tenancy.context import TenantContext, set_org_context, set_user_context
from app.services.tenancy.policy import Role, has_permission

log = get_logger(__name__)

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def get_app_settings(request: Request) -> Settings:
    return cast("Settings", request.app.state.settings)


def get_readiness_service(request: Request) -> ReadinessService:
    return cast("ReadinessService", request.app.state.readiness)


def get_services(request: Request) -> AppServices:
    return cast("AppServices", request.app.state.services)


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
ReadinessDep = Annotated[ReadinessService, Depends(get_readiness_service)]
ServicesDep = Annotated[AppServices, Depends(get_services)]


async def get_db(services: ServicesDep, request: Request) -> AsyncIterator[AsyncSession]:
    """One transaction-scoped session per request. Handlers commit explicitly; anything not
    committed (including every denied request) is rolled back on close."""
    path = request.url.path
    chat_path = (
        "/conversations" in path
        or "/domains" in path
        or path.endswith(("/widget-sessions", "/widget-config"))
    )
    if chat_path:
        async with services.chat_work.authentication() as slot:
            request.state.chat_auth_slot = slot
            async with services.session_factory() as session:
                yield session
    else:
        async with services.session_factory() as session:
            yield session


DbDep = Annotated[AsyncSession, Depends(get_db)]


def get_meta(request: Request) -> RequestMeta:
    return RequestMeta.from_request(request)


MetaDep = Annotated[RequestMeta, Depends(get_meta)]


def get_mail(services: ServicesDep, background: BackgroundTasks) -> MailQueue:
    return MailQueue(services.email_sender, background)


MailDep = Annotated[MailQueue, Depends(get_mail)]


@dataclass(frozen=True)
class AuthContext:
    user: User
    session_id: uuid.UUID
    session_token: str


async def get_auth(request: Request, db: DbDep, services: ServicesDep) -> AuthContext:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise unauthenticated()
    found = await find_active_session(db, token=token, settings=services.settings)
    if found is None:
        raise unauthenticated()
    user, session = found
    interval = services.settings.session_touch_interval_seconds
    if (utcnow() - session.last_seen_at).total_seconds() > interval:
        # Only authentication reads have run at this dependency boundary. Release their
        # checkout before the independent idle-touch transaction; never commit handler work.
        await db.commit()
        await touch_session(
            services.session_factory, session_id=session.id, settings=services.settings
        )
    await set_user_context(db, user.id)
    return AuthContext(user=user, session_id=session.id, session_token=token)


AuthDep = Annotated[AuthContext, Depends(get_auth)]


async def get_verified_auth(auth: AuthDep) -> AuthContext:
    if auth.user.email_verified_at is None:
        raise forbidden("Verify your email address to continue.", code="email_not_verified")
    return auth


VerifiedAuthDep = Annotated[AuthContext, Depends(get_verified_auth)]


async def get_tenant_context(org_id: uuid.UUID, auth: AuthDep, db: DbDep) -> TenantContext:
    # RLS already limits this query to the caller's own memberships; the explicit user filter
    # keeps the intent obvious and the plan tight.
    membership = await db.scalar(
        select(Membership).where(Membership.org_id == org_id, Membership.user_id == auth.user.id)
    )
    if membership is None:
        log.warning("security.cross_tenant_denied", user_id=str(auth.user.id))
        raise not_found()
    await set_org_context(db, membership.org_id)
    org = await db.get(Organization, membership.org_id)
    if org is None or org.deleted_at is not None:
        raise not_found()
    return TenantContext(
        user=auth.user, org=org, role=Role(membership.role), membership_id=membership.id
    )


TenantDep = Annotated[TenantContext, Depends(get_tenant_context)]

PERMISSION_ATTR = "__permission__"


def require(
    permission: str, *, verified: bool = False
) -> Callable[..., Coroutine[Any, Any, TenantContext]]:
    """Dependency factory: the one declared permission for a route (asserted by a test)."""

    async def dependency(ctx: TenantDep, request: Request) -> TenantContext:
        if not has_permission(ctx.role, permission):
            log.warning(
                "security.permission_denied",
                user_id=str(ctx.user.id),
                org_id=str(ctx.org.id),
                permission=permission,
            )
            raise forbidden()
        if verified and ctx.user.email_verified_at is None:
            raise forbidden("Verify your email address to continue.", code="email_not_verified")
        if request.method not in SAFE_METHODS and ctx.org.status != "active":
            raise ApiError(403, "org_restricted", "Organization is read-only")
        return ctx

    setattr(dependency, PERMISSION_ATTR, permission)
    return dependency


def require_chat(
    permission: str, *, verified: bool = False
) -> Callable[..., Coroutine[Any, Any, ChatAccess]]:
    """Reuse the audited resolver/policy, then close its transaction before service I/O."""
    checked = require(permission, verified=verified)
    checked_dependency = Depends(checked)

    async def dependency(
        auth: AuthDep,
        db: DbDep,
        request: Request,
        ctx: TenantContext = checked_dependency,
    ) -> ChatAccess:
        access = ChatAccess(ctx.org.id, ctx.user.id, auth.session_id, permission, verified)
        await db.rollback()
        slot = getattr(request.state, "chat_auth_slot", None)
        if slot is not None:
            slot.release()
        return access

    return dependency
