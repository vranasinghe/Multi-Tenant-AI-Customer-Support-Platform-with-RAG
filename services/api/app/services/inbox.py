"""Organization-scoped conversation inbox: search, filters, pagination, delete.

Both lists page by keyset: conversations by latest activity, ``(last_message_at, id)`` descending,
and a transcript backwards from its newest message, ``(created_at, id)`` descending. A cursor is
only a position. It names the list it came from (organization, filters, direction) and is refused
anywhere else, but it grants nothing: every page applies the same tenant predicates and RLS.
Pages are not a snapshot: a conversation that receives a message moves to the top.
"""

from __future__ import annotations

import base64
import hashlib
import json
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy import and_, delete, exists, func, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError, not_found
from app.core.request_meta import RequestMeta
from app.models.chatbots import Chatbot
from app.models.conversations import Conversation, ConversationEvent, Message, UnansweredQuestion
from app.models.identity import utcnow
from app.services.analytics import rebuild_analytics_daily
from app.services.conversation_events import chatbot_name, load_conversation
from app.services.tenancy.audit import record_audit

MessageOut = Callable[[Message], dict[str, Any]]

PAGE_DEFAULT = 25
PAGE_MAX = 100
MESSAGE_PAGE_DEFAULT = 50
#: Newest messages returned with a conversation, as before cursors existed.
DETAIL_MESSAGES = 200
CURSOR_MAX_LENGTH = 256


def cursor_scope(*parts: object) -> str:
    """Fingerprint of the list a cursor belongs to (not a signature: it protects no data)."""
    canonical = json.dumps(parts, default=str, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def encode_cursor(stamp: datetime, ident: uuid.UUID, scope: str) -> str:
    return base64.urlsafe_b64encode(f"{stamp.isoformat()}|{ident}|{scope}".encode()).decode()


def decode_cursor(cursor: str, scope: str) -> tuple[datetime, uuid.UUID]:
    """The position named by ``cursor``, or ``400 invalid_cursor``."""
    invalid = ApiError(400, "invalid_cursor", "Invalid cursor")
    if len(cursor) > CURSOR_MAX_LENGTH:
        raise invalid
    try:
        stamp, ident, issued_for = (
            base64.b64decode(cursor.encode("ascii"), altchars=b"-_", validate=True)
            .decode()
            .split("|")
        )
        position = datetime.fromisoformat(stamp), uuid.UUID(ident)
    except ValueError as exc:  # covers base64 and Unicode errors
        raise invalid from exc
    if position[0].tzinfo is None or issued_for != scope:
        raise invalid
    return position


def _search_pattern(q: str) -> str:
    cleaned = q.replace("%", " ").replace("_", " ").replace("\\", " ").strip()
    return f"%{cleaned[:200]}%"


def _inbox_filters(
    org_id: uuid.UUID,
    *,
    chatbot_id: uuid.UUID | None,
    channel: str | None,
    status: str | None,
    from_at: datetime | None,
    to_at: datetime | None,
    feedback: str | None,
    satisfaction: str | None,
    unanswered: bool | None,
    grounded: bool | None,
    q: str | None,
) -> list[Any]:
    filters: list[Any] = [Conversation.org_id == org_id]
    if chatbot_id is not None:
        filters.append(Conversation.chatbot_id == chatbot_id)
    if channel is not None:
        filters.append(Conversation.channel == channel)
    if status is not None:
        filters.append(Conversation.status == status)
    if from_at is not None:
        filters.append(Conversation.last_message_at >= from_at)
    if to_at is not None:
        filters.append(Conversation.last_message_at <= to_at)
    if satisfaction == "positive":
        filters.append(Conversation.satisfaction_score >= 4)
    elif satisfaction == "negative":
        filters.append(Conversation.satisfaction_score.is_not(None))
        filters.append(Conversation.satisfaction_score <= 2)
    if unanswered:
        filters.append(
            exists(
                select(UnansweredQuestion.id).where(
                    UnansweredQuestion.org_id == org_id,
                    UnansweredQuestion.conversation_id == Conversation.id,
                )
            )
        )
    if grounded is False:
        filters.append(
            exists(
                select(Message.id).where(
                    Message.org_id == org_id,
                    Message.conversation_id == Conversation.id,
                    Message.role == "assistant",
                    or_(Message.status == "fallback", Message.citations == []),
                )
            )
        )
    if feedback in {"positive", "negative"}:
        rating = 1 if feedback == "positive" else -1
        filters.append(
            exists(
                select(Message.id).where(
                    Message.org_id == org_id,
                    Message.conversation_id == Conversation.id,
                    Message.feedback == rating,
                )
            )
        )
    if q and q.strip():
        filters.append(
            exists(
                select(Message.id).where(
                    Message.org_id == org_id,
                    Message.conversation_id == Conversation.id,
                    Message.content.ilike(_search_pattern(q)),
                )
            )
        )
    return filters


def _base_query(org_id: uuid.UUID, **filters: Any) -> Any:
    return (
        select(Conversation, Chatbot.name)
        .join(
            Chatbot,
            and_(Chatbot.id == Conversation.chatbot_id, Chatbot.org_id == Conversation.org_id),
        )
        .where(*_inbox_filters(org_id, **filters))
        .order_by(Conversation.last_message_at.desc(), Conversation.id.desc())
    )


async def list_conversations(
    db: AsyncSession,
    org_id: uuid.UUID,
    *,
    chatbot_id: uuid.UUID | None = None,
    channel: str | None = None,
    status: str | None = None,
    from_at: datetime | None = None,
    to_at: datetime | None = None,
    feedback: str | None = None,
    satisfaction: str | None = None,
    unanswered: bool | None = None,
    grounded: bool | None = None,
    q: str | None = None,
    cursor: str | None = None,
    limit: int = PAGE_DEFAULT,
) -> dict[str, Any]:
    limit = min(max(limit, 1), PAGE_MAX)
    kwargs = {
        "chatbot_id": chatbot_id,
        "channel": channel,
        "status": status,
        "from_at": from_at,
        "to_at": to_at,
        "feedback": feedback,
        "satisfaction": satisfaction,
        "unanswered": unanswered,
        "grounded": grounded,
        "q": q,
    }
    scope = cursor_scope("conversations:last_message_at.desc", org_id, kwargs)
    stmt = _base_query(org_id, **kwargs)
    if cursor:
        stmt = stmt.where(
            tuple_(Conversation.last_message_at, Conversation.id)
            < tuple_(*decode_cursor(cursor, scope))
        )
    total = await db.scalar(
        select(func.count()).select_from(_base_query(org_id, **kwargs).subquery())
    )
    rows = (await db.execute(stmt.limit(limit + 1))).all()
    page = rows[:limit]
    ids = [row[0].id for row in page]
    unanswered_counts: dict[uuid.UUID, int] = {}
    if ids:
        counted = await db.execute(
            select(UnansweredQuestion.conversation_id, func.count())
            .where(
                UnansweredQuestion.org_id == org_id,
                UnansweredQuestion.conversation_id.in_(ids),
            )
            .group_by(UnansweredQuestion.conversation_id)
        )
        unanswered_counts = {row[0]: int(row[1]) for row in counted.all() if row[0] is not None}
    data = [
        {
            "id": conversation.id,
            "chatbot_id": conversation.chatbot_id,
            "chatbot_name": name,
            "channel": conversation.channel,
            "status": conversation.status,
            "preview": conversation.preview,
            "satisfaction_score": conversation.satisfaction_score,
            "handoff_status": conversation.handoff_status,
            "unanswered_count": unanswered_counts.get(conversation.id, 0),
            "last_message_at": conversation.last_message_at,
            "created_at": conversation.created_at,
        }
        for conversation, name in page
    ]
    has_more = len(rows) > limit
    next_cursor = None
    if has_more and page:
        last = page[-1][0]
        next_cursor = encode_cursor(last.last_message_at, last.id, scope)
    return {
        "data": data,
        "next_cursor": next_cursor,
        "has_more": has_more,
        "total": int(total or 0),
    }


def _stored_message(row: Message, message_out: MessageOut) -> dict[str, Any]:
    return {**message_out(row), "created_at": row.created_at}


async def _messages_before(
    db: AsyncSession,
    org_id: uuid.UUID,
    conversation_id: uuid.UUID,
    *,
    cursor: str | None,
    limit: int,
) -> tuple[list[Message], str | None]:
    """The ``limit`` messages before ``cursor`` (or the newest), oldest first, plus the cursor
    that leads further back."""
    scope = cursor_scope("messages:created_at.desc", org_id, conversation_id)
    stmt = (
        select(Message)
        .where(Message.org_id == org_id, Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(limit + 1)
    )
    if cursor:
        stmt = stmt.where(
            tuple_(Message.created_at, Message.id) < tuple_(*decode_cursor(cursor, scope))
        )
    rows = list((await db.scalars(stmt)).all())
    older = None
    if len(rows) > limit:
        rows = rows[:limit]
        older = encode_cursor(rows[-1].created_at, rows[-1].id, scope)
    return rows[::-1], older


async def list_messages(
    db: AsyncSession,
    org_id: uuid.UUID,
    conversation_id: uuid.UUID,
    message_out: MessageOut,
    *,
    cursor: str | None = None,
    limit: int = MESSAGE_PAGE_DEFAULT,
) -> dict[str, Any]:
    await load_conversation(db, org_id, conversation_id)  # 404 before any cursor is looked at
    rows, older = await _messages_before(
        db, org_id, conversation_id, cursor=cursor, limit=min(max(limit, 1), PAGE_MAX)
    )
    return {
        "data": [_stored_message(row, message_out) for row in rows],
        "next_cursor": older,
        "has_more": older is not None,
    }


async def get_detail(
    db: AsyncSession, org_id: uuid.UUID, conversation_id: uuid.UUID, message_out: MessageOut
) -> dict[str, Any]:
    conversation = await load_conversation(db, org_id, conversation_id)
    name = await chatbot_name(db, org_id, conversation.chatbot_id)
    messages, older = await _messages_before(
        db, org_id, conversation_id, cursor=None, limit=DETAIL_MESSAGES
    )
    events = (
        await db.scalars(
            select(ConversationEvent)
            .where(
                ConversationEvent.org_id == org_id,
                ConversationEvent.conversation_id == conversation_id,
            )
            .order_by(ConversationEvent.created_at.desc())
            .limit(50)
        )
    ).all()
    return {
        "id": conversation.id,
        "chatbot_id": conversation.chatbot_id,
        "chatbot_name": name,
        "channel": conversation.channel,
        "status": conversation.status,
        "preview": conversation.preview,
        "satisfaction_score": conversation.satisfaction_score,
        "satisfaction_comment": conversation.satisfaction_comment,
        "handoff_status": conversation.handoff_status,
        "handoff_reason": conversation.handoff_reason,
        "handoff_contact": conversation.handoff_contact,
        "created_at": conversation.created_at,
        "last_message_at": conversation.last_message_at,
        "messages": [_stored_message(row, message_out) for row in messages],
        "older_cursor": older,
        "events": [
            {
                "id": event.id,
                "kind": event.kind,
                "payload": event.payload,
                "actor_type": event.actor_type,
                "created_at": event.created_at,
            }
            for event in events
        ],
    }


async def delete_conversation(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    conversation_id: uuid.UUID,
    actor_id: uuid.UUID,
    meta: RequestMeta,
) -> None:
    conversation = await load_conversation(db, org_id, conversation_id)
    await rebuild_analytics_daily(db, org_id)
    await record_audit(
        db,
        org_id=org_id,
        actor_id=actor_id,
        action="conversation.deleted",
        target_type="conversation",
        target_id=conversation_id,
        metadata={"channel": conversation.channel, "status": conversation.status},
        meta=meta,
    )
    result = await db.execute(
        delete(Conversation).where(
            Conversation.org_id == org_id, Conversation.id == conversation_id
        )
    )
    if result.rowcount == 0:  # type: ignore[attr-defined]
        raise not_found()


def touch_conversation(conversation: Conversation, content: str) -> None:
    now = utcnow()
    conversation.last_message_at = now
    conversation.updated_at = now
    if not conversation.preview:
        conversation.preview = content[:180]
