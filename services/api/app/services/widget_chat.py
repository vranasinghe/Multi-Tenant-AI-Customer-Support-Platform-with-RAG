"""Opaque, short-lived widget capability bound to exactly one tenant/bot/conversation."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError, unauthenticated
from app.core.rate_limit import Limit
from app.models.conversations import Conversation, WidgetSession
from app.models.identity import utcnow
from app.models.tenancy import Organization
from app.services import conversations
from app.services.container import AppServices
from app.services.public_view import public_branding
from app.services.tenancy.context import set_org_context
from app.services.widget_domains import resolve, resolve_in


async def issue_session(
    services: AppServices, org_id: uuid.UUID, chatbot_id: uuid.UUID
) -> dict[str, Any]:
    await services.limiter.check(str(org_id), Limit("widget-issue", 30, 60))
    await services.limiter.check(str(org_id), Limit("chat-create", 30, 60))
    async with services.session_factory() as db:
        await set_org_context(db, org_id)
        bot = await conversations.bot_for(db, org_id, chatbot_id, public=True)
        row = Conversation(org_id=org_id, chatbot_id=chatbot_id, created_by=None, channel="widget")
        db.add(row)
        await db.flush()
        token = f"{org_id}.{secrets.token_urlsafe(32)}"
        expires = utcnow() + timedelta(minutes=services.settings.widget_session_minutes)
        db.add(
            WidgetSession(
                org_id=org_id,
                chatbot_id=chatbot_id,
                conversation_id=row.id,
                public_key=bot.public_key,
                expires_at=expires,
                token_hash=hashlib.sha256(token.encode()).hexdigest(),
            )
        )
        await db.commit()
        return {"token": token, "conversation_id": row.id, "expires_at": expires}


async def authenticate(
    services: AppServices, authorization: str | None, *, consume: bool = False
) -> tuple[uuid.UUID, uuid.UUID]:
    async with services.session_factory() as db:
        result = await authenticate_in(services, db, authorization, consume=consume)
        if consume:
            await db.commit()
        return result


async def authenticate_in(
    services: AppServices, db: AsyncSession, authorization: str | None, *, consume: bool = False
) -> tuple[uuid.UUID, uuid.UUID]:
    if not authorization or not authorization.startswith("Bearer ") or len(authorization) > 256:
        raise unauthenticated()
    token = authorization[7:]
    try:
        claimed_org = uuid.UUID(token.split(".", 1)[0])
    except ValueError:
        raise unauthenticated() from None
    # This untrusted hint only scopes the credential lookup, never authorizes a request.
    await set_org_context(db, claimed_org)
    session = await db.scalar(
        select(WidgetSession).where(
            WidgetSession.org_id == claimed_org,
            WidgetSession.token_hash == hashlib.sha256(token.encode()).hexdigest(),
            WidgetSession.expires_at > utcnow(),
        )
    )
    if session is None:
        raise unauthenticated()
    org = await db.get(Organization, session.org_id)
    if org is None or org.status != "active" or org.deleted_at is not None:
        raise unauthenticated()
    bot = await conversations.bot_for(db, session.org_id, session.chatbot_id, public=True)
    if not secrets.compare_digest(bot.public_key, session.public_key):
        raise unauthenticated()
    if session.public_origin:
        resolved = await resolve_in(db, bot.public_key, session.public_origin)
        if resolved != (session.org_id, session.chatbot_id):
            raise unauthenticated()
    if consume:
        result = await db.execute(
            update(WidgetSession)
            .where(
                WidgetSession.id == session.id,
                WidgetSession.org_id == session.org_id,
                WidgetSession.message_count < services.settings.widget_messages_per_session,
            )
            .values(message_count=WidgetSession.message_count + 1)
            .returning(WidgetSession.id)
        )
        if result.scalar_one_or_none() is None:
            raise ApiError(429, "session_limit", "Start a new chat session")

    return session.org_id, session.conversation_id


async def bootstrap(
    services: AppServices, key: str, parent: str, resume: str | None
) -> dict[str, Any]:

    org, bot_id = await resolve(services, key, parent)
    async with services.session_factory() as db:
        await set_org_context(db, org)
        await resolve_in(db, key, parent)
        bot = await conversations.bot_for(db, org, bot_id, public=True)
        existing = None
        if resume:
            existing = await db.scalar(
                select(WidgetSession)
                .where(
                    WidgetSession.org_id == org,
                    WidgetSession.chatbot_id == bot_id,
                    WidgetSession.public_origin == parent,
                    WidgetSession.public_key == key,
                    WidgetSession.resume_hash == hashlib.sha256(resume.encode()).hexdigest(),
                    WidgetSession.resume_expires_at > utcnow(),
                )
                .with_for_update()
            )
        if existing is None:
            await services.limiter.check(str(org), Limit("chat-create", 30, 60))
            conversation = Conversation(
                org_id=org, chatbot_id=bot_id, created_by=None, channel="widget"
            )
            db.add(conversation)
            await db.flush()
            resume = secrets.token_urlsafe(32)
            existing = WidgetSession(
                org_id=org,
                chatbot_id=bot_id,
                conversation_id=conversation.id,
                public_key=key,
                public_origin=parent,
                resume_hash=hashlib.sha256(resume.encode()).hexdigest(),
                resume_expires_at=utcnow() + timedelta(days=bot.widget_retention_days)
                if bot.widget_retention_days
                else utcnow() + timedelta(minutes=services.settings.widget_session_minutes),
            )
            db.add(existing)
        token = f"{org}.{secrets.token_urlsafe(32)}"
        existing.token_hash = hashlib.sha256(token.encode()).hexdigest()
        assert existing.resume_expires_at is not None  # noqa: S101
        existing.expires_at = min(
            utcnow() + timedelta(minutes=services.settings.widget_session_minutes),
            existing.resume_expires_at,
        )
        await db.commit()
        return {
            "token": token,
            "resume_token": resume,
            "expires_at": existing.expires_at,
            "retain_until": existing.resume_expires_at,
            "retention_days": bot.widget_retention_days,
            "name": bot.name,
            "welcome": bot.welcome_message,
            "branding": public_branding(bot.widget_settings),
        }
