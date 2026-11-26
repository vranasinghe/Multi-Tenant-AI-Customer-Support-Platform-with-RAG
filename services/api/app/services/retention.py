"""Tenant-scoped conversation retention. Analytics rollups are kept; message content is not."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.conversations import Conversation, ConversationEvent, UnansweredQuestion
from app.models.identity import utcnow
from app.models.tenancy import Organization
from app.services.analytics import rebuild_analytics_daily, rebuild_analytics_daily_sync
from app.services.analytics_metrics import retention_days
from app.services.tenancy.context import set_org_context


async def purge_org(db: AsyncSession, org_id: uuid.UUID, *, days: int | None = None) -> int:
    org = await db.get(Organization, org_id)
    if org is None:
        return 0
    keep = days if days is not None else retention_days(org.settings)
    cutoff = utcnow() - timedelta(days=keep)
    await rebuild_analytics_daily(db, org_id)
    result = await db.execute(
        delete(Conversation).where(
            Conversation.org_id == org_id, Conversation.last_message_at < cutoff
        )
    )
    await db.execute(
        delete(UnansweredQuestion).where(
            UnansweredQuestion.org_id == org_id, UnansweredQuestion.created_at < cutoff
        )
    )
    await db.execute(
        delete(ConversationEvent).where(
            ConversationEvent.org_id == org_id, ConversationEvent.created_at < cutoff
        )
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


async def purge_all_orgs(session_factory: Any) -> dict[str, int]:
    purged = 0
    orgs = 0
    async with session_factory() as db:
        rows = (
            await db.execute(
                text("SELECT org_id, retention_days FROM app.list_orgs_for_conversation_jobs()")
            )
        ).all()
    for org_id, days in rows:
        orgs += 1
        async with session_factory() as db:
            await set_org_context(db, org_id)
            purged += await purge_org(db, org_id, days=int(days))
            await db.commit()
    return {"organizations": orgs, "conversations": purged}


def list_orgs_sync(session: Session) -> list[tuple[uuid.UUID, int]]:
    rows = session.execute(
        text("SELECT org_id, retention_days FROM app.list_orgs_for_conversation_jobs()")
    )
    return [(row.org_id, int(row.retention_days)) for row in rows]


def snapshot_org_sync(session: Session) -> int:
    return rebuild_analytics_daily_sync(session)


def purge_org_sync(session: Session, org_id: uuid.UUID, days: int) -> int:
    cutoff = utcnow() - timedelta(days=days)
    rebuild_analytics_daily_sync(session)
    deleted = session.execute(
        delete(Conversation).where(
            Conversation.org_id == org_id, Conversation.last_message_at < cutoff
        )
    )
    session.execute(
        delete(UnansweredQuestion).where(
            UnansweredQuestion.org_id == org_id, UnansweredQuestion.created_at < cutoff
        )
    )
    session.execute(
        delete(ConversationEvent).where(
            ConversationEvent.org_id == org_id, ConversationEvent.created_at < cutoff
        )
    )
    return int(deleted.rowcount or 0)  # type: ignore[attr-defined]


async def load_retention(db: AsyncSession, org_id: uuid.UUID) -> dict[str, int]:
    org = await db.get(Organization, org_id)
    days = retention_days(org.settings if org else None)
    return {
        "conversation_retention_days": days,
        "default_days": 365,
        "min_days": 1,
        "max_days": 730,
    }
