"""Chatbot endpoints (docs/API_SPEC.md §2.3). Every route resolves the caller's membership for the
org in the path (404 for non-members) and declares exactly one permission."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import DbDep, MetaDep, SettingsDep, require
from app.models.chatbots import Chatbot
from app.models.identity import User
from app.schemas.chatbots import (
    ChatbotCreator,
    ChatbotList,
    ChatbotOptions,
    ChatbotOut,
    CreateChatbotRequest,
    LanguageOut,
    ModelOut,
    Status,
    UpdateChatbotRequest,
    WidgetSettings,
)
from app.services.chatbots import service
from app.services.chatbots.registry import (
    DEFAULT_MODEL,
    LANGUAGES,
    MODELS,
    RESPONSE_LENGTHS,
    STATUSES,
    TONES,
)
from app.services.tenancy.context import TenantContext

router = APIRouter(prefix="/orgs/{org_id}", tags=["chatbots"])

ChatbotRead = Annotated[TenantContext, Depends(require("chatbot:read"))]
# Creating a chatbot needs a verified email (AC1.1); edits follow the role only.
ChatbotCreate = Annotated[TenantContext, Depends(require("chatbot:write", verified=True))]
ChatbotWrite = Annotated[TenantContext, Depends(require("chatbot:write"))]
ChatbotDelete = Annotated[TenantContext, Depends(require("chatbot:delete"))]


def chatbot_out(chatbot: Chatbot, creator: User | None) -> ChatbotOut:
    return ChatbotOut(
        id=chatbot.id,
        name=chatbot.name,
        description=chatbot.description,
        status=chatbot.status,
        public_key=chatbot.public_key,
        instructions=chatbot.instructions,
        tone=chatbot.tone,
        response_length=chatbot.response_length,
        welcome_message=chatbot.welcome_message,
        fallback_message=chatbot.fallback_message,
        language_mode=chatbot.language_mode,
        language=chatbot.language,
        model=chatbot.model,
        temperature=float(chatbot.temperature),
        max_output_tokens=chatbot.max_output_tokens,
        strict_grounding=chatbot.strict_grounding,
        show_sources=chatbot.show_sources,
        retrieval_top_k=chatbot.retrieval_top_k,
        widget_settings=WidgetSettings.model_validate(chatbot.widget_settings),
        created_by=ChatbotCreator(id=creator.id, name=creator.name) if creator else None,
        created_at=chatbot.created_at,
        updated_at=chatbot.updated_at,
    )


@router.get("/chatbot-options")
async def chatbot_options(
    org_id: uuid.UUID, ctx: ChatbotRead, settings: SettingsDep
) -> ChatbotOptions:
    """The catalog the dashboard renders its pickers from (same data the API validates with)."""
    return ChatbotOptions(
        models=[
            ModelOut(
                id=m.id,
                label=m.label,
                provider=m.provider,
                description=m.description,
                max_output_tokens=m.max_output_tokens,
                tier=m.tier,
                default=m.id == DEFAULT_MODEL,
            )
            for m in MODELS
        ],
        languages=[LanguageOut(code=code, label=label) for code, label in LANGUAGES.items()],
        tones=list(TONES),
        response_lengths=list(RESPONSE_LENGTHS),
        statuses=list(STATUSES),
        chatbot_limit=settings.chatbot_limit_per_org,
    )


@router.get("/chatbots")
async def list_chatbots(
    org_id: uuid.UUID,
    ctx: ChatbotRead,
    db: DbDep,
    settings: SettingsDep,
    status_filter: Annotated[Status | None, Query(alias="status")] = None,
    q: Annotated[str | None, Query(max_length=80)] = None,
) -> ChatbotList:
    rows = await service.list_chatbots(db, ctx, status=status_filter, query=q or None)
    return ChatbotList(
        data=[chatbot_out(bot, creator) for bot, creator in rows],
        limit=settings.chatbot_limit_per_org,
    )


@router.post("/chatbots", status_code=status.HTTP_201_CREATED)
async def create_chatbot(
    org_id: uuid.UUID,
    body: CreateChatbotRequest,
    ctx: ChatbotCreate,
    db: DbDep,
    settings: SettingsDep,
    meta: MetaDep,
) -> ChatbotOut:
    chatbot = await service.create_chatbot(
        db, ctx, body, limit=settings.chatbot_limit_per_org, meta=meta
    )
    await db.commit()
    return chatbot_out(chatbot, ctx.user)


@router.get("/chatbots/{chatbot_id}")
async def get_chatbot(
    org_id: uuid.UUID, chatbot_id: uuid.UUID, ctx: ChatbotRead, db: DbDep
) -> ChatbotOut:
    chatbot = await service.get_chatbot(db, ctx, chatbot_id)
    return chatbot_out(chatbot, await service.creator_of(db, chatbot))


@router.patch("/chatbots/{chatbot_id}")
async def update_chatbot(
    org_id: uuid.UUID,
    chatbot_id: uuid.UUID,
    body: UpdateChatbotRequest,
    ctx: ChatbotWrite,
    db: DbDep,
    meta: MetaDep,
) -> ChatbotOut:
    chatbot = await service.update_chatbot(db, ctx, chatbot_id, body, meta=meta)
    creator = await service.creator_of(db, chatbot)
    await db.commit()
    return chatbot_out(chatbot, creator)


@router.delete("/chatbots/{chatbot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chatbot(
    org_id: uuid.UUID, chatbot_id: uuid.UUID, ctx: ChatbotDelete, db: DbDep, meta: MetaDep
) -> None:
    await service.delete_chatbot(db, ctx, chatbot_id, meta=meta)
    await db.commit()


@router.post("/chatbots/{chatbot_id}/rotate-public-key")
async def rotate_public_key(
    org_id: uuid.UUID, chatbot_id: uuid.UUID, ctx: ChatbotWrite, db: DbDep, meta: MetaDep
) -> ChatbotOut:
    chatbot = await service.rotate_public_key(db, ctx, chatbot_id, meta=meta)
    creator = await service.creator_of(db, chatbot)
    await db.commit()
    return chatbot_out(chatbot, creator)
