"""Live analytics from persisted events. Playground is excluded from product metrics, not usage."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, exists, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chatbots import Chatbot
from app.models.conversations import ChatUsage, Conversation, Message, UnansweredQuestion
from app.models.identity import utcnow
from app.services.analytics_metrics import (
    PRODUCTION_CHANNELS,
    grounded_rate,
    merge_cluster_keys,
    resolution_rate,
    satisfaction_rate,
    thumbs_up_ratio,
    unanswered_rate,
)


def period_bounds(from_at: datetime | None, to_at: datetime | None) -> tuple[datetime, datetime]:
    now = utcnow()
    end = to_at or now
    start = from_at or (end - timedelta(days=30))
    return start, end


def _channels(channel: str | None, *, usage: bool) -> list[Any]:
    if channel is not None:
        return [Conversation.channel == channel]
    if usage:
        return []
    return [Conversation.channel.in_(tuple(PRODUCTION_CHANNELS))]


def _unanswered_channel(channel: str | None) -> list[Any]:
    if channel is not None:
        return [UnansweredQuestion.channel == channel]
    return [UnansweredQuestion.channel.in_(tuple(PRODUCTION_CHANNELS))]


def conversation_filters(
    org_id: uuid.UUID,
    *,
    chatbot_id: uuid.UUID | None,
    channel: str | None,
    start: datetime,
    end: datetime,
    usage: bool = False,
) -> list[Any]:
    filters = [
        Conversation.org_id == org_id,
        Conversation.created_at >= start,
        Conversation.created_at <= end,
        *_channels(channel, usage=usage),
    ]
    if chatbot_id is not None:
        filters.append(Conversation.chatbot_id == chatbot_id)
    return filters


def _in_scoped_conversation(
    org_id: uuid.UUID, chatbot_id: uuid.UUID | None, channel: str | None, *, usage: bool
) -> Any:
    filters = [Conversation.org_id == org_id, Conversation.id == Message.conversation_id]
    filters.extend(_channels(channel, usage=usage))
    if chatbot_id is not None:
        filters.append(Conversation.chatbot_id == chatbot_id)
    return exists(select(Conversation.id).where(*filters))


async def _count(db: AsyncSession, stmt: Any) -> int:
    return int(await db.scalar(stmt) or 0)


async def _sum_int(db: AsyncSession, stmt: Any) -> int:
    return int(await db.scalar(stmt) or 0)


async def _sum_decimal(db: AsyncSession, stmt: Any) -> Decimal:
    value = await db.scalar(stmt)
    return Decimal("0") if value is None else Decimal(str(value))


async def compute_summary(
    db: AsyncSession,
    org_id: uuid.UUID,
    *,
    from_at: datetime | None = None,
    to_at: datetime | None = None,
    chatbot_id: uuid.UUID | None = None,
    channel: str | None = None,
    include_comparisons: bool = True,
) -> dict[str, Any]:
    start, end = period_bounds(from_at, to_at)
    conv = conversation_filters(
        org_id, chatbot_id=chatbot_id, channel=channel, start=start, end=end
    )
    conversations = await _count(db, select(func.count()).select_from(Conversation).where(*conv))
    resolved = await _count(
        db,
        select(func.count())
        .select_from(Conversation)
        .where(*conv, Conversation.status == "resolved"),
    )
    unresolved = await _count(
        db,
        select(func.count())
        .select_from(Conversation)
        .where(*conv, Conversation.status == "unresolved"),
    )
    handed_off = await _count(
        db,
        select(func.count())
        .select_from(Conversation)
        .where(*conv, Conversation.status == "handed_off"),
    )
    csat_submitted = await _count(
        db,
        select(func.count())
        .select_from(Conversation)
        .where(*conv, Conversation.satisfaction_score.is_not(None)),
    )
    csat_positive = await _count(
        db,
        select(func.count())
        .select_from(Conversation)
        .where(*conv, Conversation.satisfaction_score >= 4),
    )

    in_product = _in_scoped_conversation(org_id, chatbot_id, channel, usage=False)
    messages = [
        Message.org_id == org_id,
        Message.created_at >= start,
        Message.created_at <= end,
        in_product,
    ]
    user_messages = await _count(
        db, select(func.count()).select_from(Message).where(*messages, Message.role == "user")
    )
    finished = [
        *messages,
        Message.role == "assistant",
        Message.status.in_(("complete", "fallback")),
    ]
    grounded = await _count(
        db,
        select(func.count())
        .select_from(Message)
        .where(
            *finished, Message.status == "complete", func.jsonb_array_length(Message.citations) > 0
        ),
    )
    ungrounded = await _count(
        db,
        select(func.count())
        .select_from(Message)
        .where(
            *finished,
            or_(Message.status == "fallback", func.jsonb_array_length(Message.citations) == 0),
        ),
    )
    # A grounded complete reply must not also count as ungrounded.
    ungrounded = max(0, ungrounded - grounded)
    feedback_up = await _count(
        db, select(func.count()).select_from(Message).where(*messages, Message.feedback == 1)
    )
    feedback_down = await _count(
        db, select(func.count()).select_from(Message).where(*messages, Message.feedback == -1)
    )
    unanswered_filters = [
        UnansweredQuestion.org_id == org_id,
        UnansweredQuestion.created_at >= start,
        UnansweredQuestion.created_at <= end,
        *_unanswered_channel(channel),
    ]
    if chatbot_id is not None:
        unanswered_filters.append(UnansweredQuestion.chatbot_id == chatbot_id)
    unanswered = await _count(
        db, select(func.count()).select_from(UnansweredQuestion).where(*unanswered_filters)
    )

    usage_filters = [
        ChatUsage.org_id == org_id,
        ChatUsage.created_at >= start,
        ChatUsage.created_at <= end,
        ChatUsage.state == "settled",
    ]
    if chatbot_id is not None or channel is not None:
        usage_scope = conversation_filters(
            org_id, chatbot_id=chatbot_id, channel=channel, start=start, end=end, usage=True
        )
        usage_filters.append(
            ChatUsage.conversation_id.in_(select(Conversation.id).where(*usage_scope))
        )
    charged_tokens = await _sum_int(
        db, select(func.coalesce(func.sum(ChatUsage.charged_tokens), 0)).where(*usage_filters)
    )
    cost_usd = await _sum_decimal(
        db, select(func.coalesce(func.sum(ChatUsage.estimated_cost_usd), 0)).where(*usage_filters)
    )
    prompt_tokens = await _sum_int(
        db, select(func.coalesce(func.sum(Message.input_tokens), 0)).where(*messages)
    )
    completion_tokens = await _sum_int(
        db, select(func.coalesce(func.sum(Message.output_tokens), 0)).where(*messages)
    )
    latency = await db.scalar(
        select(func.percentile_cont(0.95).within_group(Message.latency_ms)).where(
            *finished, Message.latency_ms.is_not(None)
        )
    )
    comparisons: list[dict[str, Any]] = []
    if include_comparisons:
        comparisons = await chatbot_comparisons(
            db, org_id, from_at=start, to_at=end, channel=channel
        )
    return {
        "from": start,
        "to": end,
        "chatbot_id": str(chatbot_id) if chatbot_id else None,
        "channel": channel,
        "conversations": conversations,
        "messages_user": user_messages,
        "messages_assistant": grounded + ungrounded,
        "resolved": resolved,
        "unresolved": unresolved,
        "handed_off": handed_off,
        "open": max(0, conversations - resolved - unresolved - handed_off),
        "resolution_rate": resolution_rate(
            resolved=resolved, unresolved=unresolved, handed_off=handed_off
        ),
        "csat_submitted": csat_submitted,
        "csat_positive": csat_positive,
        "satisfaction_rate": satisfaction_rate(positive=csat_positive, submitted=csat_submitted),
        "grounded_answers": grounded,
        "ungrounded_answers": ungrounded,
        "grounded_rate": grounded_rate(grounded=grounded, ungrounded=ungrounded),
        "feedback_up": feedback_up,
        "feedback_down": feedback_down,
        "thumbs_up_ratio": thumbs_up_ratio(up=feedback_up, down=feedback_down),
        "unanswered": unanswered,
        "unanswered_rate": unanswered_rate(unanswered=unanswered, user_messages=user_messages),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "charged_tokens": charged_tokens,
        "estimated_cost_usd": str(cost_usd),
        "cost_is_estimate": True,
        "latency_p95_ms": int(latency) if latency is not None else None,
        "chatbots": comparisons,
        "definitions": {
            "resolution_rate": (
                "resolved / (resolved + unresolved + handed_off). Open conversations are excluded. "
                "An assistant reply is not a resolution."
            ),
            "satisfaction_rate": (
                "CSAT scores of 4 or 5 / CSAT submissions. Message thumbs are separate."
            ),
            "grounded_rate": (
                "Finished assistant replies that stored at least one citation "
                "/ finished assistant replies."
            ),
            "playground": (
                "Excluded from product metrics; included in token usage and estimated cost."
            ),
        },
    }


async def chatbot_comparisons(
    db: AsyncSession,
    org_id: uuid.UUID,
    *,
    from_at: datetime,
    to_at: datetime,
    channel: str | None,
) -> list[dict[str, Any]]:
    bots = (
        await db.execute(
            select(Chatbot.id, Chatbot.name).where(
                Chatbot.org_id == org_id, Chatbot.deleted_at.is_(None)
            )
        )
    ).all()
    rows: list[dict[str, Any]] = []
    for bot_id, name in bots:
        slice_ = await compute_summary(
            db,
            org_id,
            from_at=from_at,
            to_at=to_at,
            chatbot_id=bot_id,
            channel=channel,
            include_comparisons=False,
        )
        if slice_["conversations"] == 0 and slice_["charged_tokens"] == 0:
            continue
        rows.append(
            {
                "chatbot_id": bot_id,
                "chatbot_name": name,
                "conversations": slice_["conversations"],
                "resolution_rate": slice_["resolution_rate"],
                "satisfaction_rate": slice_["satisfaction_rate"],
                "grounded_rate": slice_["grounded_rate"],
                "unanswered": slice_["unanswered"],
                "charged_tokens": slice_["charged_tokens"],
                "estimated_cost_usd": slice_["estimated_cost_usd"],
            }
        )
    rows.sort(key=lambda item: int(item["conversations"]), reverse=True)
    return rows


async def timeseries(
    db: AsyncSession,
    org_id: uuid.UUID,
    *,
    metric: str,
    interval: str,
    from_at: datetime | None,
    to_at: datetime | None,
    chatbot_id: uuid.UUID | None,
    channel: str | None,
) -> dict[str, Any]:
    start, end = period_bounds(from_at, to_at)
    trunc = "month" if interval == "month" else "day"
    usage = metric in {"tokens", "cost"}
    conv = conversation_filters(
        org_id, chatbot_id=chatbot_id, channel=channel, start=start, end=end, usage=usage
    )
    if metric in {"tokens", "cost"}:
        column = ChatUsage.charged_tokens if metric == "tokens" else ChatUsage.estimated_cost_usd
        bucket = func.date_trunc(trunc, ChatUsage.created_at)
        stmt = (
            select(bucket.label("bucket"), func.coalesce(func.sum(column), 0).label("value"))
            .where(
                ChatUsage.org_id == org_id,
                ChatUsage.created_at >= start,
                ChatUsage.created_at <= end,
                ChatUsage.state == "settled",
            )
            .group_by(bucket)
            .order_by(bucket)
        )
        if chatbot_id is not None or channel is not None:
            stmt = stmt.where(ChatUsage.conversation_id.in_(select(Conversation.id).where(*conv)))
    else:
        bucket = func.date_trunc(trunc, Conversation.created_at)
        stmt = (
            select(bucket.label("bucket"), func.count().label("value"))
            .where(*conv)
            .group_by(bucket)
            .order_by(bucket)
        )
        if metric == "resolved":
            stmt = stmt.where(Conversation.status == "resolved")
    points = [
        {
            "t": row.bucket.isoformat() if hasattr(row.bucket, "isoformat") else str(row.bucket),
            "value": float(row.value),
        }
        for row in (await db.execute(stmt)).all()
    ]
    return {"metric": metric, "interval": trunc, "from": start, "to": end, "points": points}


async def knowledge_gaps(
    db: AsyncSession,
    org_id: uuid.UUID,
    *,
    chatbot_id: uuid.UUID | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    filters = [UnansweredQuestion.org_id == org_id, *_unanswered_channel(None)]
    if chatbot_id is not None:
        filters.append(UnansweredQuestion.chatbot_id == chatbot_id)
    rows = (
        await db.execute(
            select(UnansweredQuestion, Chatbot.name)
            .join(
                Chatbot,
                and_(
                    Chatbot.id == UnansweredQuestion.chatbot_id,
                    Chatbot.org_id == UnansweredQuestion.org_id,
                ),
            )
            .where(*filters)
            .order_by(UnansweredQuestion.created_at.desc())
            .limit(2000)
        )
    ).all()
    merged = merge_cluster_keys([row[0].cluster_key for row in rows])
    groups: dict[tuple[uuid.UUID, str], dict[str, Any]] = {}
    for question, bot_name in rows:
        canonical = merged.get(question.cluster_key, question.cluster_key)
        group = groups.setdefault(
            (question.chatbot_id, canonical),
            {
                "cluster_key": canonical,
                "representative": question.question,
                "count": 0,
                "chatbot_id": question.chatbot_id,
                "chatbot_name": bot_name,
                "last_asked_at": question.created_at,
                "reasons": {},
                "sample_conversation_ids": [],
            },
        )
        group["count"] += 1
        group["reasons"][question.reason] = int(group["reasons"].get(question.reason, 0)) + 1
        if question.created_at > group["last_asked_at"]:
            group["last_asked_at"] = question.created_at
            group["representative"] = question.question
        samples: list[uuid.UUID] = group["sample_conversation_ids"]
        if (
            question.conversation_id
            and question.conversation_id not in samples
            and len(samples) < 5
        ):
            samples.append(question.conversation_id)
    return sorted(groups.values(), key=lambda item: int(item["count"]), reverse=True)[:limit]


async def unanswered_groups(
    db: AsyncSession, org_id: uuid.UUID, *, chatbot_id: uuid.UUID | None = None
) -> list[dict[str, Any]]:
    gaps = await knowledge_gaps(db, org_id, chatbot_id=chatbot_id)
    out: list[dict[str, Any]] = []
    for item in gaps:
        reasons: dict[str, int] = item["reasons"]
        reason = max(reasons, key=lambda key: reasons[key]) if reasons else "insufficient_evidence"
        out.append(
            {
                "representative": item["representative"],
                "cluster_key": item["cluster_key"],
                "count": item["count"],
                "chatbot_id": item["chatbot_id"],
                "chatbot_name": item["chatbot_name"],
                "last_asked_at": item["last_asked_at"],
                "sample_conversation_ids": item["sample_conversation_ids"],
                "reason": reason,
            }
        )
    return out


# Upsert only. Never DELETE existing daily rows: after retention those days have no
# remaining conversations, and wiping them would erase the aggregates AC7.5 keeps.
UPSERT_ANALYTICS_DAILY = """
INSERT INTO analytics_daily (
  org_id, chatbot_id, day, channel, conversations, resolved, unresolved, handed_off,
  csat_submitted, csat_positive
)
SELECT org_id, chatbot_id, (created_at AT TIME ZONE 'UTC')::date, channel,
       count(*),
       count(*) FILTER (WHERE status = 'resolved'),
       count(*) FILTER (WHERE status = 'unresolved'),
       count(*) FILTER (WHERE status = 'handed_off'),
       count(*) FILTER (WHERE satisfaction_score IS NOT NULL),
       count(*) FILTER (WHERE satisfaction_score >= 4)
FROM conversations
WHERE org_id = app.current_org_id() AND channel <> 'playground'
GROUP BY org_id, chatbot_id, (created_at AT TIME ZONE 'UTC')::date, channel
ON CONFLICT (org_id, chatbot_id, day, channel) DO UPDATE SET
  conversations = EXCLUDED.conversations,
  resolved = EXCLUDED.resolved,
  unresolved = EXCLUDED.unresolved,
  handed_off = EXCLUDED.handed_off,
  csat_submitted = EXCLUDED.csat_submitted,
  csat_positive = EXCLUDED.csat_positive
"""


async def rebuild_analytics_daily(db: AsyncSession, org_id: uuid.UUID) -> int:
    """Snapshot product metrics so conversation deletion does not erase aggregates."""
    _ = org_id  # tenant filter is app.current_org_id()
    result = await db.execute(text(UPSERT_ANALYTICS_DAILY))
    await db.flush()
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


def rebuild_analytics_daily_sync(session: Any) -> int:
    result = session.execute(text(UPSERT_ANALYTICS_DAILY))
    return int(result.rowcount or 0)
