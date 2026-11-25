"""Cookie-authenticated dashboard conversations and member-provisioned public chat sessions."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

import anyio
from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from starlette.types import Receive, Scope, Send

from app.api.deps import DbDep, ServicesDep, require_chat
from app.models.conversations import Conversation
from app.schemas.conversations import Feedback, SendMessage
from app.services import conversations as service
from app.services.chat_access import ChatAccess
from app.services.tenancy.context import set_org_context
from app.services.widget_chat import issue_session


def no_cache(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(
    prefix="/orgs/{org_id}", tags=["conversations"], dependencies=[Depends(no_cache)]
)
ChatTest = Annotated[ChatAccess, Depends(require_chat("chatbot:test", verified=True))]
ChatRead = Annotated[ChatAccess, Depends(require_chat("conversation:read"))]
ChannelManage = Annotated[ChatAccess, Depends(require_chat("channel:manage", verified=True))]


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
    return await service.transcript(services, ctx.org_id, conversation_id)


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
