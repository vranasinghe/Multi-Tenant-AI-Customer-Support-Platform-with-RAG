"""Chatbot use cases: list, create, read, update, soft delete, public-key rotation.

Every function takes a verified ``TenantContext``: the org context GUC is already set, so RLS
restricts all reads/writes to the caller's organization. Queries also filter on ``org_id``
explicitly, so the intent is visible and a policy mistake would still not leak data.
"""

from __future__ import annotations

import secrets
import string
import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.errors import ApiError, not_found, validation_error
from app.models.chatbots import Chatbot
from app.models.identity import User, utcnow
from app.models.tenancy import Organization
from app.schemas.chatbots import CreateChatbotRequest, UpdateChatbotRequest, WidgetSettings
from app.services.chatbots.registry import (
    DEFAULT_MODEL,
    LANGUAGES,
    MIN_OUTPUT_TOKENS,
    MODELS_BY_ID,
)
from app.services.tenancy.audit import record_audit

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.request_meta import RequestMeta
    from app.services.tenancy.context import TenantContext

_KEY_ALPHABET = string.ascii_letters + string.digits
_NAME_INDEX = "uq_chatbots_org_name_active"

#: Fields whose *values* are recorded in the audit log on change. Free-text fields (instructions,
#: messages) are recorded by name only, so the audit trail never copies customer content.
_AUDIT_VALUE_FIELDS = frozenset(
    {
        "name",
        "status",
        "tone",
        "response_length",
        "language_mode",
        "language",
        "model",
        "temperature",
        "max_output_tokens",
        "strict_grounding",
        "show_sources",
        "retrieval_top_k",
    }
)


def generate_public_key() -> str:
    return "pk_live_" + "".join(secrets.choice(_KEY_ALPHABET) for _ in range(24))


def _name_taken() -> ApiError:
    return ApiError(
        409,
        "chatbot_name_taken",
        "Conflict",
        detail="A chatbot with this name already exists in this organization.",
        errors=[{"field": "name", "code": "taken", "message": "This name is already in use"}],
    )


def _validate_catalog(
    *, model: str, max_output_tokens: int, language_mode: str, language: str | None
) -> None:
    info = MODELS_BY_ID.get(model)
    if info is None:
        raise validation_error("model", "Choose one of the available models", code="not_allowed")
    if not MIN_OUTPUT_TOKENS <= max_output_tokens <= info.max_output_tokens:
        raise validation_error(
            "max_output_tokens",
            f"{info.label} supports {MIN_OUTPUT_TOKENS}-{info.max_output_tokens} output tokens",
            code="out_of_range",
        )
    if language is not None and language not in LANGUAGES:
        raise validation_error("language", "Choose a supported language", code="not_allowed")
    if language_mode == "fixed" and language is None:
        raise validation_error(
            "language", "Choose a language, or let the bot match the visitor", code="required"
        )


def _is_name_conflict(exc: IntegrityError) -> bool:
    return _NAME_INDEX in str(exc.orig)


async def _name_in_use(
    db: AsyncSession, org_id: uuid.UUID, name: str, *, exclude: uuid.UUID | None = None
) -> bool:
    stmt = select(Chatbot.id).where(
        Chatbot.org_id == org_id,
        Chatbot.deleted_at.is_(None),
        func.lower(Chatbot.name) == name.lower(),
    )
    if exclude is not None:
        stmt = stmt.where(Chatbot.id != exclude)
    return (await db.scalar(stmt.limit(1))) is not None


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def list_chatbots(
    db: AsyncSession,
    ctx: TenantContext,
    *,
    status: str | None = None,
    query: str | None = None,
    limit: int = 100,
) -> list[tuple[Chatbot, User | None]]:
    stmt = (
        select(Chatbot, User)
        .outerjoin(User, User.id == Chatbot.created_by)
        .where(Chatbot.org_id == ctx.org.id, Chatbot.deleted_at.is_(None))
        .order_by(Chatbot.created_at.desc(), Chatbot.id.desc())
        .limit(limit)
    )
    if status:
        stmt = stmt.where(Chatbot.status == status)
    if query:
        stmt = stmt.where(Chatbot.name.ilike(f"%{_escape_like(query)}%", escape="\\"))
    return [(row[0], row[1]) for row in (await db.execute(stmt)).all()]


async def get_chatbot(db: AsyncSession, ctx: TenantContext, chatbot_id: uuid.UUID) -> Chatbot:
    chatbot = await db.scalar(
        select(Chatbot).where(
            Chatbot.id == chatbot_id,
            Chatbot.org_id == ctx.org.id,
            Chatbot.deleted_at.is_(None),
        )
    )
    if chatbot is None:
        raise not_found()
    return chatbot


async def creator_of(db: AsyncSession, chatbot: Chatbot) -> User | None:
    return await db.get(User, chatbot.created_by) if chatbot.created_by else None


async def create_chatbot(
    db: AsyncSession,
    ctx: TenantContext,
    body: CreateChatbotRequest,
    *,
    limit: int,
    meta: RequestMeta,
) -> Chatbot:
    model = body.model or DEFAULT_MODEL
    language = body.language if body.language_mode == "fixed" else None
    _validate_catalog(
        model=model,
        max_output_tokens=body.max_output_tokens,
        language_mode=body.language_mode,
        language=language,
    )

    # Serialize creates per organization: lock the org row, then count. Concurrent requests
    # queue on the lock, so the allowance can't be exceeded by racing creates.
    await db.execute(select(Organization.id).where(Organization.id == ctx.org.id).with_for_update())
    active = await db.scalar(
        select(func.count())
        .select_from(Chatbot)
        .where(Chatbot.org_id == ctx.org.id, Chatbot.deleted_at.is_(None))
    )
    if (active or 0) >= limit:
        raise ApiError(
            402,
            "plan_limit_reached",
            "Plan limit reached",
            detail=f"Your plan allows {limit} chatbots. Delete one to create another.",
        )
    if await _name_in_use(db, ctx.org.id, body.name):
        raise _name_taken()

    chatbot = Chatbot(
        org_id=ctx.org.id,
        name=body.name,
        description=body.description,
        status=body.status,
        public_key=generate_public_key(),
        instructions=body.instructions,
        tone=body.tone,
        response_length=body.response_length,
        welcome_message=body.welcome_message,
        fallback_message=body.fallback_message,
        language_mode=body.language_mode,
        language=language,
        model=model,
        temperature=Decimal(str(round(body.temperature, 2))),
        max_output_tokens=body.max_output_tokens,
        strict_grounding=body.strict_grounding,
        show_sources=body.show_sources,
        retrieval_top_k=body.retrieval_top_k,
        widget_settings=body.widget_settings.model_dump(),
        created_by=ctx.user.id,
    )
    db.add(chatbot)
    try:
        await db.flush()
    except IntegrityError as exc:  # a concurrent rename/create won the race for the name
        if _is_name_conflict(exc):
            raise _name_taken() from exc
        raise
    await record_audit(
        db,
        org_id=ctx.org.id,
        actor_id=ctx.user.id,
        action="chatbot.created",
        target_type="chatbot",
        target_id=chatbot.id,
        metadata={"name": chatbot.name, "model": chatbot.model, "status": chatbot.status},
        meta=meta,
    )
    return chatbot


def _current_value(chatbot: Chatbot, field: str) -> Any:
    value = getattr(chatbot, field)
    return float(value) if isinstance(value, Decimal) else value


def _validate_merged(chatbot: Chatbot, patch: dict[str, Any]) -> None:
    """Validate the merged result, not just the patch: e.g. switching to a model with a smaller
    output limit must still satisfy the stored ``max_output_tokens``. Normalizes ``language``
    in ``patch`` (cleared whenever the bot follows the visitor's language)."""
    merged = {
        field: patch.get(field, _current_value(chatbot, field))
        for field in ("model", "max_output_tokens", "language_mode", "language")
    }
    if merged["language_mode"] == "auto":
        merged["language"] = None
    _validate_catalog(**merged)
    if "language" in patch or merged["language"] != chatbot.language:
        patch["language"] = merged["language"]


def _apply_patch(chatbot: Chatbot, patch: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Set changed scalar fields. Returns audited value changes and names of changed text."""
    changes: dict[str, Any] = {}
    changed_text: list[str] = []
    for field, raw in patch.items():
        current = _current_value(chatbot, field)
        value = round(raw, 2) if field == "temperature" else raw
        if current == value:
            continue
        setattr(chatbot, field, Decimal(str(value)) if field == "temperature" else value)
        if field in _AUDIT_VALUE_FIELDS:
            changes[field] = {"from": current, "to": value}
        else:
            changed_text.append(field)
    return changes, changed_text


def _apply_widget_patch(chatbot: Chatbot, widget_patch: dict[str, Any] | None) -> list[str]:
    if not widget_patch:
        return []
    current = WidgetSettings.model_validate(chatbot.widget_settings).model_dump()
    merged = {**current, **widget_patch}
    if merged == current:
        return []
    chatbot.widget_settings = WidgetSettings.model_validate(merged).model_dump()
    return [f"widget_settings.{key}" for key in sorted(widget_patch) if current[key] != merged[key]]


async def update_chatbot(
    db: AsyncSession,
    ctx: TenantContext,
    chatbot_id: uuid.UUID,
    body: UpdateChatbotRequest,
    *,
    meta: RequestMeta,
) -> Chatbot:
    # Lock the row so two concurrent PATCHes are validated against each other's result.
    chatbot = await db.scalar(
        select(Chatbot)
        .where(
            Chatbot.id == chatbot_id,
            Chatbot.org_id == ctx.org.id,
            Chatbot.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if chatbot is None:
        raise not_found()

    patch = body.model_dump(exclude_unset=True)
    widget_patch = patch.pop("widget_settings", None)
    _validate_merged(chatbot, patch)

    new_name = patch.get("name")
    if (
        new_name is not None
        and new_name.lower() != chatbot.name.lower()
        and await _name_in_use(db, ctx.org.id, new_name, exclude=chatbot.id)
    ):
        raise _name_taken()

    changes, changed_text = _apply_patch(chatbot, patch)
    changed_text.extend(_apply_widget_patch(chatbot, widget_patch))

    if not changes and not changed_text:
        return chatbot
    try:
        await db.flush()
    except IntegrityError as exc:
        if _is_name_conflict(exc):
            raise _name_taken() from exc
        raise
    await db.refresh(chatbot)
    await record_audit(
        db,
        org_id=ctx.org.id,
        actor_id=ctx.user.id,
        action="chatbot.updated",
        target_type="chatbot",
        target_id=chatbot.id,
        metadata={**changes, **({"fields": sorted(changed_text)} if changed_text else {})},
        meta=meta,
    )
    return chatbot


async def delete_chatbot(
    db: AsyncSession, ctx: TenantContext, chatbot_id: uuid.UUID, *, meta: RequestMeta
) -> None:
    """Soft delete: the row disappears from every list and its public key stops resolving at
    once; a purge job removes it (and, later, its knowledge) after the undo window."""
    chatbot = await get_chatbot(db, ctx, chatbot_id)
    chatbot.deleted_at = utcnow()
    await db.flush()
    await record_audit(
        db,
        org_id=ctx.org.id,
        actor_id=ctx.user.id,
        action="chatbot.deleted",
        target_type="chatbot",
        target_id=chatbot.id,
        metadata={"name": chatbot.name},
        meta=meta,
    )


async def rotate_public_key(
    db: AsyncSession, ctx: TenantContext, chatbot_id: uuid.UUID, *, meta: RequestMeta
) -> Chatbot:
    chatbot = await get_chatbot(db, ctx, chatbot_id)
    chatbot.public_key = generate_public_key()
    await db.flush()
    await db.refresh(chatbot)
    await record_audit(
        db,
        org_id=ctx.org.id,
        actor_id=ctx.user.id,
        action="chatbot.public_key_rotated",
        target_type="chatbot",
        target_id=chatbot.id,
        meta=meta,
    )
    return chatbot
