"""Public transport: bearer capability only, never accepts dashboard cookies as authorization."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header
from fastapi.responses import StreamingResponse

from app.api.conversations import no_cache, sse_response
from app.api.deps import MetaDep, ServicesDep
from app.core.rate_limit import Limit
from app.schemas.conversations import Feedback, HandoffRequestBody, SatisfactionBody, SendMessage
from app.services import conversation_events, conversations, widget_chat
from app.services.public_view import public_message
from app.services.tenancy.context import set_org_context

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
    return {"messages": [public_message(m) for m in result["messages"]]}


@router.put("/chat/messages/{message_id}/feedback")
async def feedback(
    message_id: uuid.UUID, body: Feedback, services: ServicesDep, authorization: Bearer = None
) -> dict[str, str]:
    org_id, conversation_id = await widget_chat.authenticate(services, authorization)
    await conversations.save_feedback(services, org_id, conversation_id, message_id, body.rating)
    return {"status": "ok"}


@router.put("/chat/satisfaction")
async def satisfaction(
    body: SatisfactionBody, services: ServicesDep, authorization: Bearer = None
) -> dict[str, Any]:
    org_id, conversation_id = await widget_chat.authenticate(services, authorization)
    async with services.session_factory() as db:
        await set_org_context(db, org_id)
        row = await conversation_events.save_satisfaction(
            db,
            org_id=org_id,
            conversation_id=conversation_id,
            score=body.score,
            comment=body.comment,
            actor_type="customer",
            actor_id=None,
        )
        await db.commit()
        return {"status": "ok", "satisfaction_score": row.satisfaction_score}


@router.post("/chat/handoff", status_code=201)
async def handoff(
    body: HandoffRequestBody, services: ServicesDep, authorization: Bearer = None
) -> dict[str, Any]:
    org_id, conversation_id = await widget_chat.authenticate(services, authorization)
    async with services.session_factory() as db:
        await set_org_context(db, org_id)
        row = await conversation_events.request_handoff(
            db,
            org_id=org_id,
            conversation_id=conversation_id,
            reason=body.reason,
            contact=body.contact,
            actor_type="customer",
            actor_id=None,
        )
        await db.commit()
        return {"status": "ok", "handoff_status": row.handoff_status}
