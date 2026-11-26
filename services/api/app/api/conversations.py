"""Cookie-authenticated dashboard conversations and member-provisioned public chat sessions."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

import anyio
from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from starlette.types import Receive, Scope, Send

from app.api.deps import DbDep, MetaDep, ServicesDep, require, require_chat
from app.core.errors import ApiError
from app.models.conversations import Conversation
from app.schemas.conversations import (
    ExportCreate,
    Feedback,
    HandoffRequestBody,
    HandoffUpdateBody,
    MarkUnansweredBody,
    SatisfactionBody,
    SendMessage,
    StatusBody,
)
from app.services import analytics as analytics_service
from app.services import conversation_events, exports, inbox, retention
from app.services import conversations as service
from app.services.chat_access import ChatAccess
from app.services.tenancy.context import TenantContext, set_org_context
from app.services.widget_chat import issue_session


def no_cache(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(
    prefix="/orgs/{org_id}", tags=["conversations"], dependencies=[Depends(no_cache)]
)
ChatTest = Annotated[ChatAccess, Depends(require_chat("chatbot:test", verified=True))]
ChatRead = Annotated[ChatAccess, Depends(require_chat("conversation:read"))]
ChannelManage = Annotated[ChatAccess, Depends(require_chat("channel:manage", verified=True))]
InboxRead = Annotated[TenantContext, Depends(require("conversation:read"))]
InboxWrite = Annotated[TenantContext, Depends(require("conversation:write"))]
InboxDelete = Annotated[TenantContext, Depends(require("conversation:delete"))]
InboxExport = Annotated[TenantContext, Depends(require("conversation:export"))]


class ChatStreamingResponse(StreamingResponse):
    """Watch disconnects on all ASGI versions and deterministically close the upstream iterator."""

    def __init__(self, turn: service.Turn, services: ServicesDep) -> None:
        self.turn = turn
        self.services = services
        self.generator = service.stream(services, turn)
        super().__init__(
            self.generator,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            async with anyio.create_task_group() as group:

                async def output() -> None:
                    try:
                        await self.stream_response(send)
                    except OSError:
                        pass  # disconnected socket; close/finalize in the outer finally
                    finally:
                        group.cancel_scope.cancel()

                async def disconnected() -> None:
                    await self.listen_for_disconnect(receive)
                    group.cancel_scope.cancel()

                group.start_soon(output)
                group.start_soon(disconnected)
        finally:
            with anyio.CancelScope(shield=True):
                await self.generator.aclose()
                await service.close_pending_turn(self.services, self.turn)


def sse_response(turn: service.Turn, services: ServicesDep) -> StreamingResponse:
    return ChatStreamingResponse(turn, services)


@router.post("/chatbots/{chatbot_id}/conversations", status_code=201)
async def create_conversation(
    org_id: uuid.UUID, chatbot_id: uuid.UUID, ctx: ChatTest, services: ServicesDep
) -> dict[str, Any]:
    row = await service.create(services, ctx.org_id, chatbot_id, ctx.user_id)
    return {"id": row.id, "chatbot_id": row.chatbot_id, "channel": row.channel}


@router.get("/chatbots/{chatbot_id}/conversations")
async def list_conversations(
    org_id: uuid.UUID, chatbot_id: uuid.UUID, ctx: ChatRead, db: DbDep
) -> dict[str, Any]:
    await set_org_context(db, ctx.org_id)
    rows = (
        await db.scalars(
            select(Conversation)
            .where(Conversation.org_id == ctx.org_id, Conversation.chatbot_id == chatbot_id)
            .order_by(Conversation.created_at.desc())
            .limit(50)
        )
    ).all()
    return {
        "data": [
            {"id": row.id, "channel": row.channel, "created_at": row.created_at} for row in rows
        ]
    }


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    org_id: uuid.UUID, conversation_id: uuid.UUID, ctx: ChatRead, services: ServicesDep
) -> dict[str, Any]:
    async with services.session_factory() as db:
        await set_org_context(db, ctx.org_id)
        detail = await inbox.get_detail(db, ctx.org_id, conversation_id, service.message_out)
    detail["conversation"] = {
        "id": str(detail["id"]),
        "chatbot_id": str(detail["chatbot_id"]),
        "channel": detail["channel"],
    }
    return detail


@router.get("/conversations/{conversation_id}/messages")
async def list_messages(
    org_id: uuid.UUID,
    conversation_id: uuid.UUID,
    ctx: ChatRead,
    services: ServicesDep,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = inbox.MESSAGE_PAGE_DEFAULT,
) -> dict[str, Any]:
    """Transcript pages, newest first: ``next_cursor`` leads to earlier messages."""
    async with services.session_factory() as db:
        await set_org_context(db, ctx.org_id)
        return await inbox.list_messages(
            db, ctx.org_id, conversation_id, service.message_out, cursor=cursor, limit=limit
        )


@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    org_id: uuid.UUID,
    conversation_id: uuid.UUID,
    body: SendMessage,
    ctx: ChatTest,
    services: ServicesDep,
) -> StreamingResponse:
    return sse_response(
        await service.prepare(services, ctx.org_id, conversation_id, body, access=ctx), services
    )


@router.put("/conversations/{conversation_id}/messages/{message_id}/feedback")
async def feedback(
    org_id: uuid.UUID,
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    body: Feedback,
    ctx: ChatTest,
    services: ServicesDep,
) -> dict[str, str]:
    await service.save_feedback(services, ctx.org_id, conversation_id, message_id, body.rating)
    return {"status": "ok"}


@router.post("/chatbots/{chatbot_id}/widget-sessions", status_code=201)
async def create_widget_session(
    org_id: uuid.UUID, chatbot_id: uuid.UUID, ctx: ChannelManage, services: ServicesDep
) -> dict[str, Any]:
    # Phase 5 deliberately provides no anonymous issuance by public key alone.
    return await issue_session(services, ctx.org_id, chatbot_id)


@router.get("/conversations")
async def inbox_list(
    org_id: uuid.UUID,
    ctx: InboxRead,
    db: DbDep,
    chatbot_id: uuid.UUID | None = None,
    channel: str | None = None,
    status: str | None = None,
    from_at: Annotated[datetime | None, Query(alias="from")] = None,
    to_at: Annotated[datetime | None, Query(alias="to")] = None,
    feedback: str | None = None,
    satisfaction: str | None = None,
    unanswered: bool | None = None,
    grounded: bool | None = None,
    q: str | None = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> dict[str, Any]:
    return await inbox.list_conversations(
        db,
        ctx.org.id,
        chatbot_id=chatbot_id,
        channel=channel,
        status=status,
        from_at=from_at,
        to_at=to_at,
        feedback=feedback,
        satisfaction=satisfaction,
        unanswered=unanswered,
        grounded=grounded,
        q=q,
        cursor=cursor,
        limit=limit,
    )


@router.patch("/conversations/{conversation_id}")
async def update_status(
    org_id: uuid.UUID,
    conversation_id: uuid.UUID,
    body: StatusBody,
    ctx: InboxWrite,
    db: DbDep,
    meta: MetaDep,
) -> dict[str, Any]:
    row = await conversation_events.set_status(
        db,
        org_id=ctx.org.id,
        conversation_id=conversation_id,
        status=body.status,
        actor_id=ctx.user.id,
        meta=meta,
    )
    await db.commit()
    return {"id": row.id, "status": row.status}


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    org_id: uuid.UUID,
    conversation_id: uuid.UUID,
    ctx: InboxDelete,
    db: DbDep,
    meta: MetaDep,
) -> None:
    await inbox.delete_conversation(
        db, org_id=ctx.org.id, conversation_id=conversation_id, actor_id=ctx.user.id, meta=meta
    )
    await db.commit()


@router.put("/conversations/{conversation_id}/satisfaction")
async def record_satisfaction(
    org_id: uuid.UUID,
    conversation_id: uuid.UUID,
    body: SatisfactionBody,
    ctx: InboxWrite,
    db: DbDep,
) -> dict[str, Any]:
    row = await conversation_events.save_satisfaction(
        db,
        org_id=ctx.org.id,
        conversation_id=conversation_id,
        score=body.score,
        comment=body.comment,
        actor_type="user",
        actor_id=ctx.user.id,
    )
    await db.commit()
    return {"id": row.id, "satisfaction_score": row.satisfaction_score}


@router.post("/conversations/{conversation_id}/handoff", status_code=201)
async def create_handoff(
    org_id: uuid.UUID,
    conversation_id: uuid.UUID,
    body: HandoffRequestBody,
    ctx: InboxWrite,
    db: DbDep,
    meta: MetaDep,
) -> dict[str, Any]:
    row = await conversation_events.request_handoff(
        db,
        org_id=ctx.org.id,
        conversation_id=conversation_id,
        reason=body.reason,
        contact=body.contact,
        actor_type="user",
        actor_id=ctx.user.id,
        meta=meta,
    )
    await db.commit()
    return {"id": row.id, "status": row.status, "handoff_status": row.handoff_status}


@router.patch("/conversations/{conversation_id}/handoff")
async def change_handoff(
    org_id: uuid.UUID,
    conversation_id: uuid.UUID,
    body: HandoffUpdateBody,
    ctx: InboxWrite,
    db: DbDep,
    meta: MetaDep,
) -> dict[str, Any]:
    row = await conversation_events.update_handoff(
        db,
        org_id=ctx.org.id,
        conversation_id=conversation_id,
        status=body.status,
        actor_id=ctx.user.id,
        meta=meta,
    )
    await db.commit()
    return {"id": row.id, "status": row.status, "handoff_status": row.handoff_status}


@router.post("/conversations/{conversation_id}/unanswered", status_code=201)
async def mark_unanswered(
    org_id: uuid.UUID,
    conversation_id: uuid.UUID,
    body: MarkUnansweredBody,
    ctx: InboxWrite,
    db: DbDep,
) -> dict[str, str]:
    conversation = await conversation_events.load_conversation(db, ctx.org.id, conversation_id)
    question, message_id = await conversation_events.latest_user_question(
        db, ctx.org.id, conversation_id
    )
    if not question:
        raise ApiError(409, "no_question", "This conversation has no customer question to mark")
    await conversation_events.record_unanswered(
        db,
        conversation=conversation,
        question=question,
        reason=body.reason,
        message_id=message_id,
        actor_type="user",
        actor_id=ctx.user.id,
    )
    await db.commit()
    return {"status": "ok"}


@router.get("/unanswered")
async def list_unanswered(
    org_id: uuid.UUID,
    ctx: InboxRead,
    db: DbDep,
    chatbot_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    return {
        "data": await analytics_service.unanswered_groups(db, ctx.org.id, chatbot_id=chatbot_id)
    }


@router.get("/chatbots/{chatbot_id}/unanswered")
async def list_bot_unanswered(
    org_id: uuid.UUID, chatbot_id: uuid.UUID, ctx: InboxRead, db: DbDep
) -> dict[str, Any]:
    return {
        "data": await analytics_service.unanswered_groups(db, ctx.org.id, chatbot_id=chatbot_id)
    }


@router.get("/knowledge-gaps")
async def list_knowledge_gaps(
    org_id: uuid.UUID,
    ctx: InboxRead,
    db: DbDep,
    chatbot_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    return {"data": await analytics_service.knowledge_gaps(db, ctx.org.id, chatbot_id=chatbot_id)}


@router.get("/conversation-retention")
async def get_retention(org_id: uuid.UUID, ctx: InboxRead, db: DbDep) -> dict[str, int]:
    return await retention.load_retention(db, ctx.org.id)


@router.post("/conversations/exports", status_code=201)
async def create_export(
    org_id: uuid.UUID,
    body: ExportCreate,
    ctx: InboxExport,
    db: DbDep,
    meta: MetaDep,
    services: ServicesDep,
) -> dict[str, Any]:
    row = await exports.create_export(
        db,
        services.store,
        org_id=ctx.org.id,
        actor_id=ctx.user.id,
        meta=meta,
        chatbot_id=body.chatbot_id,
        channel=body.channel,
        from_at=body.from_at,
        to_at=body.to_at,
        status=body.status,
    )
    await db.commit()
    return exports.export_out(row)


@router.get("/exports/{export_id}")
async def get_export(
    org_id: uuid.UUID, export_id: uuid.UUID, ctx: InboxExport, db: DbDep
) -> dict[str, Any]:
    return exports.export_out(await exports.get_export(db, ctx.org.id, export_id))


@router.get("/exports/{export_id}/download")
async def download_export(
    org_id: uuid.UUID,
    export_id: uuid.UUID,
    ctx: InboxExport,
    db: DbDep,
    services: ServicesDep,
) -> Response:
    data = await exports.download_export(db, services.store, ctx.org.id, export_id)
    return Response(
        content=data,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="conversations-{export_id}.csv"',
            "Cache-Control": "no-store",
        },
    )
