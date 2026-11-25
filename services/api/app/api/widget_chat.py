"""Public transport: bearer capability only, never accepts dashboard cookies as authorization."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header
from fastapi.responses import StreamingResponse

from app.api.conversations import no_cache, sse_response
from app.api.deps import MetaDep, ServicesDep
from app.core.rate_limit import Limit
from app.schemas.conversations import Feedback, SendMessage
from app.services import conversations, widget_chat

router = APIRouter(tags=["restricted-widget-chat"], dependencies=[Depends(no_cache)])
Bearer = Annotated[str | None, Header(alias="Authorization")]


@router.post("/chat/messages")
async def message(
    body: SendMessage, services: ServicesDep, meta: MetaDep, authorization: Bearer = None
) -> StreamingResponse:
    await services.limiter.check(meta.ip or "unknown", Limit("widget-ip", 30, 60))
    org_id, conversation_id = await widget_chat.authenticate(services, authorization, consume=True)
    await services.limiter.check(authorization or "", Limit("widget-session", 10, 60))
    return sse_response(
        await conversations.prepare(
            services, org_id, conversation_id, body, authorization=authorization
        ),
        services,
    )


@router.get("/chat")
async def history(services: ServicesDep, authorization: Bearer = None) -> dict[str, Any]:
    org_id, conversation_id = await widget_chat.authenticate(services, authorization)
    result = await conversations.transcript(services, org_id, conversation_id)
    return {"messages": result["messages"]}


@router.put("/chat/messages/{message_id}/feedback")
async def feedback(
    message_id: uuid.UUID, body: Feedback, services: ServicesDep, authorization: Bearer = None
) -> dict[str, str]:
    org_id, conversation_id = await widget_chat.authenticate(services, authorization)
    await conversations.save_feedback(services, org_id, conversation_id, message_id, body.rating)
    return {"status": "ok"}
