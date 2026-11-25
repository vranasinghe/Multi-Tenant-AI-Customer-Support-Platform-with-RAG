"""Single-use tokens must hold under true concurrency, not just back-to-back requests."""

from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.core.errors import ApiError
from app.core.request_meta import RequestMeta
from app.models.identity import User
from app.services.identity import tokens
from app.services.tenancy import invitations
from tests.support.database import TestDatabase

pytestmark = pytest.mark.integration

RACERS = 12
META = RequestMeta(ip=None, ip_prefix=None, user_agent=None, request_id="test")


def _engine(url: URL) -> AsyncEngine:
    return create_async_engine(url, pool_size=RACERS, max_overflow=0)


async def test_email_token_is_spent_by_exactly_one_of_many_concurrent_requests(
    test_database: TestDatabase,
) -> None:
    engine = _engine(test_database.app_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        user = User(email=f"race-{uuid.uuid4().hex[:8]}@example.com", name="Racer")
        db.add(user)
        await db.flush()
        token = await tokens.issue_email_token(
            db, user_id=user.id, purpose="reset_password", ttl=timedelta(minutes=30)
        )
        await db.commit()

    async def attempt() -> bool:
        async with factory() as session:
            spent = await tokens.consume_email_token(session, token=token, purpose="reset_password")
            await session.commit()
            return spent is not None

    results = await asyncio.gather(*(attempt() for _ in range(RACERS)))
    await engine.dispose()

    assert results.count(True) == 1


async def test_invitation_is_accepted_by_exactly_one_of_many_concurrent_requests(
    test_database: TestDatabase,
) -> None:
    engine = _engine(test_database.app_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    owner_engine = create_async_engine(test_database.owner_url)

    org_id, invitee_email = uuid.uuid4(), f"invitee-{uuid.uuid4().hex[:8]}@example.com"
    owner_id, invitee_id = uuid.uuid4(), uuid.uuid4()
    token = "t" * 43
    from app.core.security import hash_token

    async with owner_engine.begin() as conn:
        for uid, mail in ((owner_id, f"o-{org_id}@example.com"), (invitee_id, invitee_email)):
            await conn.execute(
                text("INSERT INTO users (id, email, name) VALUES (:i, :e, 'U')"),
                {"i": uid, "e": mail},
            )
        await conn.execute(
            text("INSERT INTO organizations (id, name, slug) VALUES (:i, 'Race Org', :s)"),
            {"i": org_id, "s": f"race-{org_id}"},
        )
        await conn.execute(
            text(
                "INSERT INTO memberships (id, org_id, user_id, role) VALUES (:i, :o, :u, 'owner')"
            ),
            {"i": uuid.uuid4(), "o": org_id, "u": owner_id},
        )
        await conn.execute(
            text(
                "INSERT INTO invitations (id, org_id, email, role, token_hash, expires_at) "
                "VALUES (:i, :o, :e, 'agent', :h, now() + interval '1 day')"
            ),
            {"i": uuid.uuid4(), "o": org_id, "e": invitee_email, "h": hash_token(token)},
        )
    invitee = User(id=invitee_id, email=invitee_email, name="U")

    async def attempt() -> bool:
        async with factory() as session:
            try:
                await invitations.accept_invitation(session, user=invitee, token=token, meta=META)
                await session.commit()
            except ApiError:
                return False
            except Exception:  # unique violation on (org_id, user_id) also means "lost the race"
                return False
            return True

    results = await asyncio.gather(*(attempt() for _ in range(RACERS)))
    async with owner_engine.connect() as conn:
        members = await conn.scalar(
            text("SELECT count(*) FROM memberships WHERE org_id = :o AND user_id = :u"),
            {"o": org_id, "u": invitee_id},
        )
    await engine.dispose()
    await owner_engine.dispose()

    assert results.count(True) == 1
    assert members == 1
