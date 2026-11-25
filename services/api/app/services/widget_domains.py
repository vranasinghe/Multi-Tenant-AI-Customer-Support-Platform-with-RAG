"""Exact origins, DNS ownership proofs, and expiring verification; no caller-controlled fetches."""

from __future__ import annotations

import asyncio
import ipaddress
import re
import secrets
import uuid
from typing import Any
from urllib.parse import urlsplit

import dns.resolver
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.core.ids import new_id
from app.models.chatbots import Chatbot
from app.services.container import AppServices
from app.services.tenancy.context import set_org_context


def origin(value: str, local: bool = False) -> str:
    p = urlsplit(value)
    if (
        p.scheme not in ({"http", "https"} if local else {"https"})
        or not p.hostname
        or p.username
        or p.password
        or p.path not in ("", "/")
        or p.query
        or p.fragment
    ):
        raise ValueError("Use an exact HTTPS origin without a path, credentials or wildcard")
    host = p.hostname.lower().encode("idna").decode()
    if "*" in host or any(c.isspace() for c in host):
        raise ValueError("Wildcards are not supported")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ((ip and not ip.is_global) or host == "localhost") and not local:
        raise ValueError("A public hostname is required")
    if ip is None and (
        len(host) > 253
        or not re.fullmatch(
            r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*", host
        )
    ):
        raise ValueError("Invalid DNS hostname")
    port = p.port
    display = f"[{host}]" if ":" in host else host
    return f"{p.scheme}://{display}" + (
        f":{port}" if port and port != (443 if p.scheme == "https" else 80) else ""
    )


async def resolve(services: AppServices, key: str, parent: str) -> tuple[uuid.UUID, uuid.UUID]:
    async with services.session_factory() as db:
        return await resolve_in(db, key, parent)


async def resolve_in(db: AsyncSession, key: str, parent: str) -> tuple[uuid.UUID, uuid.UUID]:
    row = (
        await db.execute(
            text("SELECT * FROM app.resolve_widget(:key,:origin)"),
            {"key": key, "origin": parent},
        )
    ).first()
    if row is None:
        raise ApiError(403, "origin_not_allowed", "This site is not verified for this chatbot")
    return row.org_id, row.chatbot_id


async def configured_bot(db: AsyncSession, org: uuid.UUID, bot: uuid.UUID) -> Chatbot:
    row = await db.scalar(
        select(Chatbot).where(
            Chatbot.org_id == org, Chatbot.id == bot, Chatbot.deleted_at.is_(None)
        )
    )
    if row is None:
        raise ApiError(404, "not_found", "Chatbot not found")
    return row


async def config(services: AppServices, org: uuid.UUID, bot: uuid.UUID) -> dict[str, Any]:

    async with services.session_factory() as db:
        await set_org_context(db, org)
        b = await configured_bot(db, org, bot)
        rows = (
            (
                await db.execute(
                    text(
                        """SELECT id,origin,token,verified_until FROM chatbot_domains WHERE org_id=:org AND chatbot_id=:bot ORDER BY origin"""  # noqa: E501
                    ),
                    {"org": org, "bot": bot},
                )
            )
            .mappings()
            .all()
        )
        return {"domains": [dict(r) for r in rows], "retention_days": b.widget_retention_days}


def dns_proof(host: str) -> list[str]:
    return [
        b"".join(r.strings).decode("ascii")
        for r in dns.resolver.resolve("_acs-widget." + host, "TXT", lifetime=5)
    ]


async def add(services: AppServices, org: uuid.UUID, bot: uuid.UUID, value: str) -> None:

    try:
        value = origin(value, services.settings.app_env in {"local", "test"})
    except ValueError as exc:
        raise ApiError(422, "invalid_origin", str(exc)) from None
    async with services.session_factory() as db:
        await set_org_context(db, org)
        await configured_bot(db, org, bot)
        # Serialize the per-bot domain cap with the chatbot row.
        await db.execute(
            text("SELECT id FROM chatbots WHERE org_id=:org AND id=:bot FOR UPDATE"),
            {"org": org, "bot": bot},
        )
        count = await db.scalar(
            text("SELECT count(*) FROM chatbot_domains WHERE org_id=:org AND chatbot_id=:bot"),
            {"org": org, "bot": bot},
        )
        if count >= 20:
            raise ApiError(409, "domain_limit", "Maximum 20 allowed origins")
        await db.execute(
            text(
                """INSERT INTO chatbot_domains(id,org_id,chatbot_id,origin,token) VALUES(:id,:org,:bot,:origin,:token) ON CONFLICT(org_id,chatbot_id,origin) DO NOTHING"""  # noqa: E501
            ),
            {
                "id": new_id(),
                "org": org,
                "bot": bot,
                "origin": value,
                "token": "acs-widget=" + secrets.token_urlsafe(24),
            },
        )
        await db.commit()


async def verify(services: AppServices, org: uuid.UUID, bot: uuid.UUID, id: uuid.UUID) -> None:
    async with services.session_factory() as db:
        await set_org_context(db, org)
        row = (
            await db.execute(
                text(
                    "SELECT origin,token FROM chatbot_domains WHERE org_id=:org AND chatbot_id=:bot AND id=:id"  # noqa: E501
                ),
                {"org": org, "bot": bot, "id": id},
            )
        ).first()
        if row is None:
            raise ApiError(404, "not_found", "Origin not found")
        host = urlsplit(row.origin).hostname or ""
        development = services.settings.app_env in {"local", "test"} and host in {
            "localhost",
            "127.0.0.1",
            "::1",
        }
        try:
            valid = development or row.token in await asyncio.to_thread(dns_proof, host)
        except Exception:
            valid = False
        await db.execute(
            text("""UPDATE chatbot_domains SET verified_until=
            CASE WHEN :valid THEN now()+interval '7 days' ELSE NULL END
            WHERE org_id=:org AND chatbot_id=:bot AND id=:id"""),
            {"valid": valid, "org": org, "bot": bot, "id": id},
        )
        await db.commit()
        if not valid:
            raise ApiError(
                422, "verification_failed", "DNS TXT proof was not found; verification was revoked"
            )
