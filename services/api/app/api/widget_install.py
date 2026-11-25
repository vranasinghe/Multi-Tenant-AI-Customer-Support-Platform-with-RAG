from __future__ import annotations

import html
import secrets
import uuid
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import Field
from sqlalchemy import select, text

from app.api.conversations import no_cache
from app.api.deps import DbDep, MetaDep, ServicesDep, require, require_chat
from app.core.errors import ApiError
from app.core.rate_limit import Limit
from app.models.chatbots import Chatbot
from app.schemas.auth import StrictModel
from app.services import widget_chat, widget_domains
from app.services.chat_access import ChatAccess
from app.services.tenancy.context import TenantContext

router = APIRouter()
manage = APIRouter(prefix="/orgs/{org_id}/chatbots/{chatbot_id}", dependencies=[Depends(no_cache)])
Manage = Annotated[TenantContext, Depends(require("domain:manage", verified=True))]
Read = Annotated[ChatAccess, Depends(require_chat("chatbot:read"))]
ShortManage = Annotated[ChatAccess, Depends(require_chat("domain:manage", verified=True))]


class Domain(StrictModel):
    origin: str = Field(max_length=300)


class Retention(StrictModel):
    days: int = Field(ge=0, le=30)


class Session(StrictModel):
    key: str = Field(max_length=100)
    parent_origin: str = Field(max_length=300)
    resume_token: str | None = Field(default=None, max_length=100)


@manage.get("/widget-config")
async def config(
    org_id: uuid.UUID, chatbot_id: uuid.UUID, ctx: Read, services: ServicesDep
) -> dict[str, Any]:
    return await widget_domains.config(services, ctx.org_id, chatbot_id)


@manage.post("/domains", status_code=201)
async def add(
    org_id: uuid.UUID, chatbot_id: uuid.UUID, body: Domain, ctx: ShortManage, services: ServicesDep
) -> dict[str, str]:
    await widget_domains.add(services, ctx.org_id, chatbot_id, body.origin)
    return {"status": "ok"}


@manage.post("/domains/{domain_id}/verify")
async def verify(
    org_id: uuid.UUID,
    chatbot_id: uuid.UUID,
    domain_id: uuid.UUID,
    ctx: ShortManage,
    services: ServicesDep,
) -> dict[str, str]:
    await services.limiter.check(str(ctx.org_id), Limit("widget-verify", 10, 60))
    await widget_domains.verify(services, ctx.org_id, chatbot_id, domain_id)
    return {"status": "ok"}


@manage.delete("/domains/{domain_id}", status_code=204)
async def remove(
    org_id: uuid.UUID, chatbot_id: uuid.UUID, domain_id: uuid.UUID, ctx: Manage, db: DbDep
) -> None:
    await db.execute(
        text("DELETE FROM chatbot_domains WHERE org_id=:org AND chatbot_id=:bot AND id=:id"),
        {"org": ctx.org.id, "bot": chatbot_id, "id": domain_id},
    )
    await db.commit()


@manage.patch("/widget-retention")
async def retention(
    org_id: uuid.UUID, chatbot_id: uuid.UUID, body: Retention, ctx: Manage, db: DbDep
) -> dict[str, str]:
    bot = await db.scalar(
        select(Chatbot).where(
            Chatbot.org_id == ctx.org.id, Chatbot.id == chatbot_id, Chatbot.deleted_at.is_(None)
        )
    )
    if bot is None:
        raise ApiError(404, "not_found", "Chatbot not found")
    bot.widget_retention_days = body.days
    # Shortening retention invalidates longer-lived resume credentials immediately.
    await db.execute(
        text(
            """UPDATE widget_sessions SET resume_expires_at=least(resume_expires_at,now()+make_interval(days=>:days)), expires_at=least(expires_at,now()+make_interval(days=>:days)) WHERE org_id=:org AND chatbot_id=:bot AND public_origin IS NOT NULL"""  # noqa: E501
        ),
        {"days": body.days, "org": ctx.org.id, "bot": chatbot_id},
    )
    await db.commit()
    return {"status": "ok"}


@router.get("/widget/v1/loader.js")
def script() -> FileResponse:
    path = Path(__file__).resolve().parents[2] / "widget_assets" / "v1" / "loader.js"
    if not path.is_file():
        raise ApiError(503, "widget_not_built", "Build the widget distribution first")
    return FileResponse(
        path,
        media_type="text/javascript",
        headers={
            "Cache-Control": "public,max-age=3600",
            "X-Content-Type-Options": "nosniff",
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.get("/widget/frame/{key}")
async def frame(
    key: str,
    services: ServicesDep,
    meta: MetaDep,
    parent_origin: Annotated[str, Query(max_length=300)],
    instance: Annotated[str, Query(max_length=100)],
) -> HTMLResponse:
    await services.limiter.check(meta.ip or "unknown", Limit("widget-frame", 60, 60))
    try:
        parent = widget_domains.origin(
            parent_origin, services.settings.app_env in {"local", "test"}
        )
    except ValueError:
        raise ApiError(403, "origin_not_allowed", "Invalid parent origin") from None
    await widget_domains.resolve(services, key, parent)
    nonce = secrets.token_urlsafe(24)
    attrs = " ".join(
        f'data-{name}="{html.escape(value, quote=True)}"'
        for name, value in [("frame-key", key), ("parent-origin", parent), ("instance", instance)]
    )
    return HTMLResponse(
        f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><script nonce="{nonce}" src="/widget/v1/loader.js" {attrs}></script></body></html>',  # noqa: E501
        headers={
            "Cache-Control": "no-store",
            "Content-Security-Policy": f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'unsafe-inline'; connect-src 'self'; img-src https:; frame-ancestors {parent}; base-uri 'none'; form-action 'none'",  # noqa: E501
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/public/v1/widget/sessions", dependencies=[Depends(no_cache)])
async def session(body: Session, services: ServicesDep, meta: MetaDep) -> dict[str, Any]:
    await services.limiter.check(meta.ip or "unknown", Limit("widget-bootstrap-ip", 20, 60))
    try:
        parent = widget_domains.origin(
            body.parent_origin, services.settings.app_env in {"local", "test"}
        )
    except ValueError:
        raise ApiError(403, "origin_not_allowed", "Invalid origin") from None
    return await widget_chat.bootstrap(services, body.key, parent, body.resume_token)
