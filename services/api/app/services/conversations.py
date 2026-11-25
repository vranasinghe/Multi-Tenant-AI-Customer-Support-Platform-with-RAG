"""Shared orchestration for dashboard and restricted widget conversations."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import anyio
from fastapi.encoders import jsonable_encoder
from redis.exceptions import RedisError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError, not_found
from app.core.ids import new_id
from app.core.logging import get_logger
from app.core.rate_limit import Limit
from app.integrations.llm import ProviderError
from app.models.chatbots import Chatbot
from app.models.conversations import ChatUsage, Conversation, Message
from app.models.identity import utcnow
from app.models.tenancy import Organization
from app.rag.retrieval import RenderedEvidence, authorize_chunks, search
from app.schemas.conversations import SendMessage
from app.services.chat_access import ChatAccess
from app.services.chat_controls import Lease, acquire, cost, reserve
from app.services.chat_prompt import (
    CitationStream,
    assemble,
    citations_for,
    strip_unknown_citations,
    token_bound,
)
from app.services.chatbots.registry import MODELS_BY_ID
from app.services.container import AppServices
from app.services.tenancy.context import set_org_context

log = get_logger(__name__)


async def find_conversation(
    services: AppServices, org_id: uuid.UUID, conversation_id: uuid.UUID
) -> Conversation:
    async with services.session_factory() as db:
        await set_org_context(db, org_id)
        row = await db.scalar(
            select(Conversation).where(
                Conversation.org_id == org_id, Conversation.id == conversation_id
            )
        )
        if row is None:
            raise not_found()
        return row


async def bot_for(
    db: AsyncSession, org_id: uuid.UUID, bot_id: uuid.UUID, *, public: bool = False
) -> Chatbot:
    org = await db.get(Organization, org_id)
    if org is None or org.status != "active" or org.deleted_at is not None:
        raise ApiError(403, "org_restricted", "Organization is unavailable")
    bot = await db.scalar(
        select(Chatbot).where(
            Chatbot.id == bot_id, Chatbot.org_id == org_id, Chatbot.deleted_at.is_(None)
        )
    )
    if bot is None:
        raise not_found()
    if bot.status in {"paused", "archived"} or (public and bot.status != "active"):
        raise ApiError(409, "chatbot_unavailable", "This chatbot is unavailable")
    return bot


async def save_feedback(
    services: AppServices,
    org_id: uuid.UUID,
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    rating: int,
) -> None:
    async with services.session_factory() as db:
        await set_org_context(db, org_id)
        result = await db.execute(
            update(Message)
            .where(
                Message.org_id == org_id,
                Message.conversation_id == conversation_id,
                Message.id == message_id,
                Message.role == "assistant",
                Message.status.in_(["complete", "fallback"]),
            )
            .values(feedback=rating or None)
            .returning(Message.id)
        )
        if result.scalar_one_or_none() is None:
            raise not_found()
        await db.commit()


async def create(
    services: AppServices,
    org_id: uuid.UUID,
    bot_id: uuid.UUID,
    user_id: uuid.UUID | None,
    *,
    channel: str = "playground",
) -> Conversation:
    await services.limiter.check(str(org_id), Limit("chat-create", 30, 60))
    async with services.session_factory() as db:
        await set_org_context(db, org_id)
        await bot_for(db, org_id, bot_id, public=channel == "widget")
        conversation = Conversation(
            org_id=org_id, chatbot_id=bot_id, created_by=user_id, channel=channel
        )
        db.add(conversation)
        await db.commit()
        return conversation


async def transcript(
    services: AppServices, org_id: uuid.UUID, conversation_id: uuid.UUID
) -> dict[str, Any]:
    conversation = await find_conversation(services, org_id, conversation_id)
    async with services.session_factory() as db:
        await set_org_context(db, org_id)
        rows = (
            await db.scalars(
                select(Message)
                .where(Message.org_id == org_id, Message.conversation_id == conversation_id)
                .order_by(Message.created_at.desc(), Message.id.desc())
                .limit(200)
            )
        ).all()
        return {
            "conversation": {
                "id": str(conversation.id),
                "chatbot_id": str(conversation.chatbot_id),
                "channel": conversation.channel,
            },
            "messages": [message_out(m) for m in reversed(rows)],
        }


def message_out(message: Message) -> dict[str, Any]:
    return {
        "id": str(message.id),
        "role": message.role,
        "content": message.content,
        "status": message.status,
        "citations": message.citations,
        "input_tokens": message.input_tokens,
        "output_tokens": message.output_tokens,
        "estimated_cost_usd": str(message.estimated_cost_usd),
        "usage_estimated": message.usage_estimated,
        "error_code": message.error_code,
        "feedback": message.feedback,
        "latency_ms": message.latency_ms,
    }


@dataclass
class Turn:
    org_id: uuid.UUID
    conversation_id: uuid.UUID
    message_id: uuid.UUID
    bot: Chatbot
    prompt: list[dict[str, str]]
    chunks: RenderedEvidence
    lease: Lease
    reserved_tokens: int
    reserved_cost: Decimal
    prices: tuple[float, float]
    fallback: bool


async def prepare(
    services: AppServices,
    org_id: uuid.UUID,
    conversation_id: uuid.UUID,
    body: SendMessage,
    *,
    access: ChatAccess | None = None,
    authorization: str | None = None,
) -> Turn:
    try:
        async with asyncio.timeout(services.settings.embedding_timeout_seconds + 30):
            return await _prepare(
                services, org_id, conversation_id, body, access=access, authorization=authorization
            )
    except TimeoutError:
        raise ApiError(
            503, "chat_timeout", "Chat preparation timed out. Please try again."
        ) from None


async def _prepare(  # noqa: PLR0912, PLR0915
    services: AppServices,
    org_id: uuid.UUID,
    conversation_id: uuid.UUID,
    body: SendMessage,
    *,
    access: ChatAccess | None = None,
    authorization: str | None = None,
) -> Turn:
    s = services.settings
    await services.limiter.check(str(org_id), Limit("chat-org", s.chat_requests_per_minute, 60))
    deadline = asyncio.get_running_loop().time() + s.chat_admission_wait_seconds
    while True:
        try:
            lease = await acquire(services.redis, org_id, conversation_id, s)
            break
        except ApiError as exc:
            if exc.code != "chat_busy" or asyncio.get_running_loop().time() >= deadline:
                raise
            await asyncio.sleep(0.01)
    pending_turn: tuple[uuid.UUID, Decimal] | None = None
    try:
        async with services.chat_work.setup():
            async with services.session_factory() as db:
                await set_org_context(db, org_id)
                conversation = await db.scalar(
                    select(Conversation).where(
                        Conversation.org_id == org_id, Conversation.id == conversation_id
                    )
                )
                if conversation is None or (
                    access is not None and conversation.channel != "playground"
                ):
                    raise not_found()
                bot = await bot_for(
                    db, org_id, conversation.chatbot_id, public=conversation.channel == "widget"
                )
                if bot.model not in MODELS_BY_ID or bot.model not in s.chat_model_prices:
                    raise ApiError(
                        409, "model_unavailable", "Configure a supported model and its prices"
                    )
                query = body.content
                n = min(
                    body.context_messages
                    if body.context_messages is not None
                    else s.chat_context_messages,
                    s.chat_context_messages,
                )
                rows = list(
                    (
                        await db.scalars(
                            select(Message)
                            .where(
                                Message.org_id == org_id,
                                Message.conversation_id == conversation_id,
                                Message.status == "complete",
                            )
                            .order_by(Message.created_at.desc(), Message.id.desc())
                            .limit(n + 2)
                        )
                    ).all()
                )
                rows.reverse()
                history: list[dict[str, str]] = []
                for i in range(len(rows) - 1):
                    if rows[i].role == "user" and rows[i + 1].role == "assistant":
                        history.extend(
                            [
                                {"role": "user", "content": rows[i].content},
                                {"role": "assistant", "content": rows[i + 1].content},
                            ]
                        )
                history = history[-(n // 2) * 2 :] if n >= 2 else []
                # Resolve short follow-ups using this tenant's most recent question.
                if history:
                    query = history[-2]["content"] + "\n" + query
            # No database connection is held during embedding; the setup permit bounds work.
            try:
                vector = await services.chat_work.query(
                    services.embedder, query, s.embedding_timeout_seconds
                )
            except Exception:
                raise ApiError(
                    503, "retrieval_unavailable", "Knowledge search is temporarily unavailable"
                ) from None
            async with services.session_factory() as db:
                await set_org_context(db, org_id)
                if access is not None:
                    await access.validate(db, s)
                if authorization is not None:
                    from app.services.widget_chat import authenticate_in  # noqa: PLC0415

                    resolved = await authenticate_in(services, db, authorization)
                    if resolved != (org_id, conversation_id):
                        raise not_found()
                bot = await bot_for(
                    db, org_id, conversation.chatbot_id, public=conversation.channel == "widget"
                )
                chunks = await search(
                    db,
                    org_id=org_id,
                    chatbot_id=bot.id,
                    query_vector=vector,
                    question=query,
                    embedding_model=services.embedder.model_id,
                    top_k=bot.retrieval_top_k,
                    candidates=s.retrieval_candidates,
                    min_vector_score=s.chat_min_vector_score,
                )
                chunks = await authorize_chunks(
                    db,
                    chunks,
                    org_id=org_id,
                    chatbot_id=bot.id,
                    embedding_model=services.embedder.model_id,
                )
                prefs = f"{bot.instructions}\nTone: {bot.tone}; length: {bot.response_length}."
                if bot.language_mode == "fixed":
                    prefs += f" Respond in {bot.language}."
                try:
                    prompt, evidence = assemble(
                        prefs,
                        chunks,
                        body.content,
                        history,
                        budget=min(
                            s.chat_input_token_budget,
                            MODELS_BY_ID[bot.model].context_window - bot.max_output_tokens,
                        ),
                    )
                except ValueError:
                    raise ApiError(
                        422, "context_limit", "Shorten your question or chatbot instructions"
                    ) from None
                fallback = not evidence
                if not fallback and s.llm_provider == "disabled":
                    raise ApiError(
                        503, "provider_not_configured", "Chat provider is not configured"
                    )
                input_bound = token_bound(prompt)
                # Reserve all attempts, including uncertain usage on cancellation/provider failures.
                tokens = (
                    0
                    if fallback
                    else (input_bound + bot.max_output_tokens * 4) * (s.llm_retries + 1)
                )
                prices = s.chat_model_prices[bot.model]
                amount = (
                    Decimal(0)
                    if fallback
                    else cost(input_bound, bot.max_output_tokens * 4, prices) * (s.llm_retries + 1)
                )
                message_id = new_id()
                await reserve(
                    db,
                    org_id=org_id,
                    conversation_id=conversation_id,
                    message_id=message_id,
                    model=bot.model,
                    tokens=tokens,
                    amount=amount,
                    settings=s,
                )
                now = utcnow()
                persisted = await db.scalar(
                    select(Conversation).where(
                        Conversation.org_id == org_id, Conversation.id == conversation_id
                    )
                )
                if persisted is None:
                    raise not_found()
                persisted.last_message_at = now
                persisted.updated_at = now
                if not persisted.preview:
                    persisted.preview = body.content[:180]
                db.add(
                    Message(
                        org_id=org_id,
                        conversation_id=conversation_id,
                        role="user",
                        content=body.content,
                    )
                )
                db.add(
                    Message(
                        id=message_id,
                        org_id=org_id,
                        conversation_id=conversation_id,
                        role="assistant",
                        status="streaming",
                    )
                )
                pending_turn = (message_id, amount)
                await db.commit()
                return Turn(
                    org_id,
                    conversation_id,
                    message_id,
                    bot,
                    prompt,
                    evidence,
                    lease,
                    tokens,
                    amount,
                    prices,
                    fallback,
                )
    except BaseException:
        with anyio.CancelScope(shield=True):
            if pending_turn is not None:
                await interrupt_pending(services, org_id, *pending_turn)
            try:
                await lease.release(services.redis)
            except RedisError:
                log.error("chat.lease_release_failed", conversation_id=str(conversation_id))
        raise


def event(name: str, payload: Any) -> str:
    return f"event: {name}\ndata: {json.dumps(jsonable_encoder(payload), ensure_ascii=False)}\n\n"


async def close_pending_turn(services: AppServices, turn: Turn) -> None:
    """Covers a socket disappearing before the streaming generator ever starts."""
    try:
        await interrupt_pending(services, turn.org_id, turn.message_id, turn.reserved_cost)
    finally:
        try:
            await turn.lease.release(services.redis)
        except RedisError:
            log.error("chat.lease_release_failed", message_id=str(turn.message_id))


async def interrupt_pending(
    services: AppServices, org_id: uuid.UUID, message_id: uuid.UUID, reserved_cost: Decimal
) -> None:
    try:
        async with asyncio.timeout(10), services.session_factory() as db:
            await set_org_context(db, org_id)
            await db.execute(
                update(Message)
                .where(
                    Message.org_id == org_id,
                    Message.id == message_id,
                    Message.status == "streaming",
                )
                .values(
                    status="interrupted",
                    error_code="client_disconnected",
                    estimated_cost_usd=reserved_cost,
                )
            )
            # No automatic refund of uncertain usage; mark durable accounting terminal.
            await db.execute(
                update(ChatUsage)
                .where(
                    ChatUsage.org_id == org_id,
                    ChatUsage.id == message_id,
                    ChatUsage.state == "reserved",
                )
                .values(state="settled")
            )
            await db.commit()
    except Exception:
        log.error("chat.close_pending_failed", message_id=str(message_id))


async def stream(services: AppServices, turn: Turn) -> AsyncGenerator[str]:  # noqa: PLR0912, PLR0915
    content = ""
    marker_stream = CitationStream(turn.chunks)
    received_bytes = 0
    status = "interrupted"
    started = asyncio.get_running_loop().time()
    first_token_at: float | None = None
    error: str | None = None
    input_tokens = output_tokens = 0
    charged = turn.reserved_tokens
    amount = turn.reserved_cost
    estimated = True
    citations: list[dict[str, Any]] = []
    try:
        yield event(
            "meta", {"conversation_id": turn.conversation_id, "message_id": turn.message_id}
        )
        if turn.fallback:
            content = (
                turn.bot.fallback_message
                or "I don't have enough information to answer. Please contact support."
            )
            content = strip_unknown_citations(content, turn.chunks)
            status = "fallback"
            first_token_at = asyncio.get_running_loop().time()
            yield event("delta", {"text": content})
        else:
            async with asyncio.timeout(services.settings.llm_timeout_seconds):
                provider_stream = services.chat_provider.stream(
                    turn.prompt,
                    model=turn.bot.model,
                    max_tokens=turn.bot.max_output_tokens,
                    temperature=float(turn.bot.temperature),
                )
                try:
                    async for part in provider_stream:
                        received_bytes += len(part.text.encode("utf-8"))
                        if received_bytes > turn.bot.max_output_tokens * 4:
                            raise ProviderError("output_limit")
                        piece = marker_stream.feed(part.text)
                        if piece:
                            if first_token_at is None:
                                first_token_at = asyncio.get_running_loop().time()
                            content += piece
                            yield event("delta", {"text": piece})
                        if part.input_tokens is not None and part.output_tokens is not None:
                            input_tokens, output_tokens = part.input_tokens, part.output_tokens
                            if (
                                input_tokens > token_bound(turn.prompt)
                                or output_tokens > turn.bot.max_output_tokens
                            ):
                                raise ProviderError("invalid_provider_usage")
                            # Previous failed attempts conservatively remain charged at their bound.
                            prior = max(0, part.attempts - 1)
                            charged = min(
                                turn.reserved_tokens,
                                input_tokens
                                + output_tokens
                                + prior
                                * (turn.reserved_tokens // (services.settings.llm_retries + 1)),
                            )
                            amount = min(
                                turn.reserved_cost,
                                cost(input_tokens, output_tokens, turn.prices)
                                + prior * turn.reserved_cost / (services.settings.llm_retries + 1),
                            )
                            estimated = prior > 0
                finally:
                    await provider_stream.aclose()
                marker_stream.finish()
                if not content.strip():
                    raise ProviderError("empty_provider_response")
                status = "complete"
                # With no provider usage (demo or incompatible provider), keep the reservation.
                if input_tokens == output_tokens == 0:
                    input_tokens = token_bound(turn.prompt)
                    output_tokens = len(content.encode("utf-8"))
    except TimeoutError:
        status, error = "failed", "provider_timeout"
    except ProviderError as exc:
        status, error = "failed", str(exc)
    except (asyncio.CancelledError, GeneratorExit):
        status, error = "interrupted", "client_disconnected"
        raise
    except Exception:
        status, error = "failed", "chat_failed"
        log.error("chat.generation_failed", message_id=str(turn.message_id))
    finally:
        # Interrupted/failed partial output retains only source snapshots actually rendered.
        marker_stream.finish()
        citations = citations_for(content, turn.chunks) if turn.bot.show_sources else []
        # Finalize even when Starlette cancels the response's task group on disconnect.
        with anyio.CancelScope(shield=True):
            try:
                async with asyncio.timeout(10), services.session_factory() as db:
                    await set_org_context(db, turn.org_id)
                    latency_ms = (
                        int((first_token_at - started) * 1000)
                        if first_token_at is not None
                        else None
                    )
                    await db.execute(
                        update(Message)
                        .where(Message.org_id == turn.org_id, Message.id == turn.message_id)
                        .values(
                            content=content,
                            status=status,
                            citations=citations,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            estimated_cost_usd=amount,
                            usage_estimated=estimated,
                            error_code=error,
                            latency_ms=latency_ms,
                        )
                    )
                    if status == "fallback":
                        from app.services.conversation_events import (  # noqa: PLC0415
                            latest_user_question,
                            load_conversation,
                            record_unanswered,
                        )

                        conversation = await load_conversation(
                            db, turn.org_id, turn.conversation_id
                        )
                        question, user_message_id = await latest_user_question(
                            db, turn.org_id, turn.conversation_id
                        )
                        if question:
                            await record_unanswered(
                                db,
                                conversation=conversation,
                                question=question,
                                reason="insufficient_evidence",
                                message_id=user_message_id,
                                actor_type="system",
                                actor_id=None,
                            )
                    await db.execute(
                        update(Conversation)
                        .where(
                            Conversation.org_id == turn.org_id,
                            Conversation.id == turn.conversation_id,
                        )
                        .values(last_message_at=utcnow(), updated_at=utcnow())
                    )
                    await db.execute(
                        update(ChatUsage)
                        .where(ChatUsage.org_id == turn.org_id, ChatUsage.id == turn.message_id)
                        .values(
                            state="settled",
                            charged_tokens=charged,
                            estimated_cost_usd=amount,
                        )
                    )
                    await db.commit()
            except Exception:
                # Reservation remains charged if finalization fails. No silent overspend.
                log.error("chat.finalization_failed", message_id=str(turn.message_id))
            finally:
                try:
                    await turn.lease.release(services.redis)
                except RedisError:
                    log.error("chat.lease_release_failed", message_id=str(turn.message_id))
    if error:
        yield event(
            "error", {"code": error, "message": "The answer could not finish. Please try again."}
        )
    yield event(
        "done",
        {
            "id": str(turn.message_id),
            "role": "assistant",
            "content": content,
            "status": status,
            "citations": citations,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost_usd": str(amount),
            "usage_estimated": estimated,
            "error_code": error,
            "feedback": None,
        },
    )
