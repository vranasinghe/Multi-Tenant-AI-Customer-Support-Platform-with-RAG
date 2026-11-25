"""First-class persisted conversation events: status, CSAT, handoff, unanswered."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError, not_found
from app.core.request_meta import RequestMeta
from app.models.chatbots import Chatbot
from app.models.conversations import Conversation, ConversationEvent, Message, UnansweredQuestion
from app.models.identity import utcnow
from app.services.analytics_metrics import cluster_key, is_positive_csat, normalize_question
from app.services.tenancy.audit import record_audit

ActorType = Literal["user", "customer", "system"]


async def load_conversation(
    db: AsyncSession, org_id: uuid.UUID, conversation_id: uuid.UUID
) -> Conversation:
    row = await db.scalar(
        select(Conversation).where(
            Conversation.org_id == org_id, Conversation.id == conversation_id
        )
    )
    if row is None:
        raise not_found()
    return row


async def chatbot_name(db: AsyncSession, org_id: uuid.UUID, chatbot_id: uuid.UUID) -> str:
    name = await db.scalar(
        select(Chatbot.name).where(Chatbot.org_id == org_id, Chatbot.id == chatbot_id)
    )
    return name or "Chatbot"


def add_event(
    db: AsyncSession,
    *,
    conversation: Conversation,
    kind: str,
    payload: dict[str, Any],
    actor_type: ActorType,
    actor_id: uuid.UUID | None,
) -> ConversationEvent:
    event = ConversationEvent(
        org_id=conversation.org_id,
        conversation_id=conversation.id,
        chatbot_id=conversation.chatbot_id,
        kind=kind,
        payload=payload,
        actor_type=actor_type,
        actor_id=actor_id,
    )
    db.add(event)
    conversation.updated_at = utcnow()
    return event


async def set_status(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    conversation_id: uuid.UUID,
    status: str,
    actor_id: uuid.UUID,
    meta: RequestMeta,
) -> Conversation:
    conversation = await load_conversation(db, org_id, conversation_id)
    previous = conversation.status
    if previous == status:
        return conversation
    conversation.status = status
    add_event(
        db,
        conversation=conversation,
        kind="status_changed",
        payload={"from": previous, "to": status},
        actor_type="user",
        actor_id=actor_id,
    )
    await record_audit(
        db,
        org_id=org_id,
        actor_id=actor_id,
        action="conversation.status_changed",
        target_type="conversation",
        target_id=conversation_id,
        metadata={"from": previous, "to": status},
        meta=meta,
    )
    await db.flush()
    return conversation


async def save_satisfaction(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    conversation_id: uuid.UUID,
    score: int,
    comment: str | None,
    actor_type: ActorType,
    actor_id: uuid.UUID | None,
) -> Conversation:
    conversation = await load_conversation(db, org_id, conversation_id)
    conversation.satisfaction_score = score
    conversation.satisfaction_comment = comment
    add_event(
        db,
        conversation=conversation,
        kind="satisfaction_submitted",
        payload={"score": score, "positive": is_positive_csat(score)},
        actor_type=actor_type,
        actor_id=actor_id,
    )
    await db.flush()
    return conversation


async def request_handoff(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    conversation_id: uuid.UUID,
    reason: str,
    contact: str | None,
    actor_type: ActorType,
    actor_id: uuid.UUID | None,
    meta: RequestMeta | None = None,
) -> Conversation:
    conversation = await load_conversation(db, org_id, conversation_id)
    conversation.handoff_status = "requested"
    conversation.handoff_reason = reason
    conversation.handoff_contact = contact
    conversation.status = "handed_off"
    add_event(
        db,
        conversation=conversation,
        kind="handoff_requested",
        payload={"reason": reason, "has_contact": bool(contact)},
        actor_type=actor_type,
        actor_id=actor_id,
    )
    if meta is not None and actor_id is not None:
        await record_audit(
            db,
            org_id=org_id,
            actor_id=actor_id,
            action="conversation.handoff_requested",
            target_type="conversation",
            target_id=conversation_id,
            metadata={"reason": reason},
            meta=meta,
        )
    await db.flush()
    return conversation


async def update_handoff(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    conversation_id: uuid.UUID,
    status: str,
    actor_id: uuid.UUID,
    meta: RequestMeta,
) -> Conversation:
    conversation = await load_conversation(db, org_id, conversation_id)
    if conversation.handoff_status is None:
        raise ApiError(409, "handoff_missing", "This conversation has no handoff request")
    previous = conversation.handoff_status
    conversation.handoff_status = status
    if status == "cancelled" and conversation.status == "handed_off":
        conversation.status = "open"
        add_event(
            db,
            conversation=conversation,
            kind="status_changed",
            payload={"from": "handed_off", "to": "open"},
            actor_type="user",
            actor_id=actor_id,
        )
    add_event(
        db,
        conversation=conversation,
        kind="handoff_updated",
        payload={"from": previous, "to": status},
        actor_type="user",
        actor_id=actor_id,
    )
    await record_audit(
        db,
        org_id=org_id,
        actor_id=actor_id,
        action="conversation.handoff_updated",
        target_type="conversation",
        target_id=conversation_id,
        metadata={"from": previous, "to": status},
        meta=meta,
    )
    await db.flush()
    return conversation


async def record_unanswered(
    db: AsyncSession,
    *,
    conversation: Conversation,
    question: str,
    reason: str,
    message_id: uuid.UUID | None,
    actor_type: ActorType,
    actor_id: uuid.UUID | None,
) -> UnansweredQuestion:
    normalized = normalize_question(question)
    row = UnansweredQuestion(
        org_id=conversation.org_id,
        conversation_id=conversation.id,
        chatbot_id=conversation.chatbot_id,
        message_id=message_id,
        question=question[:4000],
        normalized_question=normalized,
        cluster_key=cluster_key(question),
        channel=conversation.channel,
        reason=reason,
    )
    db.add(row)
    add_event(
        db,
        conversation=conversation,
        kind="unanswered_recorded",
        payload={"reason": reason, "cluster_key": row.cluster_key},
        actor_type=actor_type,
        actor_id=actor_id,
    )
    await db.flush()
    return row


async def latest_user_question(
    db: AsyncSession, org_id: uuid.UUID, conversation_id: uuid.UUID
) -> tuple[str, uuid.UUID | None]:
    row = await db.scalar(
        select(Message)
        .where(
            Message.org_id == org_id,
            Message.conversation_id == conversation_id,
            Message.role == "user",
        )
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(1)
    )
    if row is None:
        return "", None
    return row.content, row.id
