"""Migrations that change the schema run only on their own throwaway databases (MIG-01).

The round-trip used to downgrade the session's shared database. Whether it passed then depended
on what earlier tests had left behind: one usage record whose conversation had been deleted (which
0007 allows and the 0006 schema cannot represent) was enough to fail it. Each test here owns its
data, and that limitation is asserted explicitly instead of being met by accident.
"""

from __future__ import annotations

import subprocess
import sys
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import Connection, create_engine, inspect, text

from app.services.readiness import ALEMBIC_INI
from tests.support.database import TestDatabase, temporary_database

pytestmark = pytest.mark.integration

PHASE7_TABLES = (
    "conversation_events",
    "unanswered_questions",
    "analytics_daily",
    "conversation_exports",
)
# Tables that exist before and after 0007 and must keep every row across it.
CORE_TABLES = (
    "organizations",
    "chatbots",
    "documents",
    "document_chunks",
    "conversations",
    "messages",
    "widget_sessions",
    "chat_usage",
)
TENANT_TABLES = ("documents", "document_chunks", "conversations", "messages", "chat_usage")


@pytest.fixture
def database(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestDatabase]:
    with temporary_database() as scratch:
        monkeypatch.setenv(
            "MIGRATION_DATABASE_URL", scratch.owner_url.render_as_string(hide_password=False)
        )
        yield scratch


def migrate(target: str, direction: str) -> subprocess.CompletedProcess[bytes]:
    # Run CLI migrations in their own process so Alembic logging cannot disable app loggers.
    return subprocess.run(  # noqa: S603  # fixed interpreter/CLI; target values are test constants
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), direction, target],
        check=True,
        capture_output=True,
    )


def query(database: TestDatabase, statement: str, **params: Any) -> list[tuple[Any, ...]]:
    engine = create_engine(database.owner_url)
    try:
        with engine.begin() as conn:
            result = conn.execute(text(statement), params)
            return [tuple(row) for row in result] if result.returns_rows else []
    finally:
        engine.dispose()


def counts(database: TestDatabase, tables: tuple[str, ...]) -> dict[str, int]:
    return {t: query(database, f"SELECT count(*) FROM {t}")[0][0] for t in tables}  # noqa: S608


def seed_tenant(conn: Connection, label: str) -> dict[str, uuid.UUID]:
    """One organization's history as written before 0007 (columns that exist in 0006 only)."""
    ids = {
        name: uuid.uuid4()
        for name in ("org", "user", "bot", "source", "document", "chunk", "playground", "widget")
    }

    def run(statement: str, **extra: Any) -> None:
        conn.execute(text(statement), {**ids, **extra})

    run(
        "INSERT INTO organizations (id, name, slug) VALUES (:org, :n, :s)",
        n=label,
        s=f"org-{label}",
    )
    run("INSERT INTO users (id, email, name) VALUES (:user, :e, 'U')", e=f"{label}@example.com")
    run(
        "INSERT INTO memberships (id, org_id, user_id, role) VALUES (:m, :org, :user, 'owner')",
        m=uuid.uuid4(),
    )
    run(
        "INSERT INTO chatbots (id, org_id, name, public_key, model) "
        "VALUES (:bot, :org, 'Bot', :k, 'gpt-4.1-mini')",
        k=f"pk_live_{uuid.uuid4().hex[:24]}",
    )
    run(
        "INSERT INTO knowledge_sources (id, org_id, chatbot_id, kind, name) "
        "VALUES (:source, :org, :bot, 'file', 'policy')"
    )
    run(
        "INSERT INTO documents (id, org_id, chatbot_id, source_id, title, uri) "
        "VALUES (:document, :org, :bot, :source, 'policy', 'policy.txt')"
    )
    run(
        "INSERT INTO document_chunks (id, org_id, chatbot_id, document_id, document_version, "
        "ordinal, content, token_count, embedding, embedding_model) VALUES (:chunk, :org, :bot, "
        ":document, 1, 0, 'synthetic policy', 2, array_fill(0.25, ARRAY[1536])::vector, 'hash-v1')"
    )
    for channel, conversation in (("playground", ids["playground"]), ("widget", ids["widget"])):
        run(
            "INSERT INTO conversations (id, org_id, chatbot_id, channel, created_at) "
            "VALUES (:c, :org, :bot, :ch, now() - interval '3 days')",
            c=conversation,
            ch=channel,
        )
        for role, content, age in (
            ("user", f"{channel} first question", 2),
            ("assistant", f"{channel} answer", 1),
        ):
            run(
                "INSERT INTO messages (id, org_id, conversation_id, role, content, status, "
                "created_at) VALUES (:id, :org, :c, :role, :content, 'complete', "
                "now() - make_interval(days => :age))",
                id=uuid.uuid4(),
                c=conversation,
                role=role,
                content=content,
                age=age,
            )
        run(
            "INSERT INTO chat_usage (id, org_id, conversation_id, model, period, charged_tokens, "
            "estimated_cost_usd, state) VALUES (:id, :org, :c, 'gpt-4.1-mini', '2026-11', 110, "
            "0.001, 'settled')",
            id=uuid.uuid4(),
            c=conversation,
        )
    run(
        "INSERT INTO widget_sessions (id, org_id, chatbot_id, conversation_id, token_hash, "
        "public_key, expires_at) VALUES (:id, :org, :bot, :widget, :h, 'pk', "
        "now() + interval '1 hour')",
        id=uuid.uuid4(),
        h=uuid.uuid4().hex,
    )
    return ids


def seed(database: TestDatabase) -> list[dict[str, uuid.UUID]]:
    engine = create_engine(database.owner_url)
    try:
        with engine.begin() as conn:
            return [seed_tenant(conn, label) for label in ("alpha", "beta")]
    finally:
        engine.dispose()


def assert_protections(database: TestDatabase, tables: tuple[str, ...]) -> None:
    for table in tables:
        assert query(
            database,
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = :t",
            t=table,
        ) == [(True, True)], table
    assert query(database, "SELECT conname FROM pg_constraint WHERE NOT convalidated") == [], (
        "an unvalidated constraint would not protect existing rows"
    )


def assert_tenant_isolation(
    database: TestDatabase, org: uuid.UUID, tables: tuple[str, ...]
) -> None:
    engine = create_engine(database.app_url)
    try:
        with engine.begin() as conn:
            for table in tables:
                visible = f"SELECT count(*) FROM {table}"  # noqa: S608
                assert conn.execute(text(visible)).scalar() == 0, f"{table} without tenant"
            conn.execute(text("SELECT set_config('app.current_org_id', :o, true)"), {"o": str(org)})
            for table in tables:
                others = f"SELECT count(*) FROM {table} WHERE org_id <> :o"  # noqa: S608
                own = f"SELECT count(*) FROM {table}"  # noqa: S608
                assert conn.execute(text(others), {"o": org}).scalar() == 0, table
                assert conn.execute(text(own)).scalar(), table
    finally:
        engine.dispose()


def revision(database: TestDatabase) -> str:
    return str(query(database, "SELECT version_num FROM alembic_version")[0][0])


def usage_rows(database: TestDatabase) -> list[tuple[Any, ...]]:
    return query(
        database,
        "SELECT id, org_id, conversation_id, charged_tokens, estimated_cost_usd, state "
        "FROM chat_usage ORDER BY id",
    )


def test_chat_migration_roundtrip(database: TestDatabase) -> None:
    assert database.name.startswith("chatbot_test_")
    engine = create_engine(database.owner_url)
    try:
        migrate("0004", "downgrade")
        assert "conversations" not in inspect(engine).get_table_names()
    finally:
        migrate("head", "upgrade")
        engine.dispose()
    engine = create_engine(database.owner_url)
    try:
        assert {"conversations", "messages", "widget_sessions", "chat_usage"} <= set(
            inspect(engine).get_table_names()
        )
    finally:
        engine.dispose()


def test_upgrade_from_0006_keeps_history_and_backfills_the_inbox(database: TestDatabase) -> None:
    migrate("0006", "downgrade")
    alpha, beta = seed(database)
    before = counts(database, CORE_TABLES)
    usage = usage_rows(database)
    vectors = query(database, "SELECT id, embedding::text FROM document_chunks ORDER BY id")

    migrate("head", "upgrade")

    assert revision(database) == "0007"
    assert counts(database, CORE_TABLES) == before
    assert usage_rows(database) == usage
    assert query(database, "SELECT id, embedding::text FROM document_chunks ORDER BY id") == vectors
    rows = query(
        database,
        "SELECT c.channel, c.status, c.preview, c.last_message_at = "
        "(SELECT max(created_at) FROM messages m WHERE m.conversation_id = c.id) "
        "FROM conversations c WHERE c.org_id = :o ORDER BY c.channel",
        o=alpha["org"],
    )
    assert rows == [
        ("playground", "open", "playground first question", True),
        ("widget", "open", "widget first question", True),
    ]
    assert_protections(database, (*TENANT_TABLES, *PHASE7_TABLES, "widget_sessions"))
    for org in (alpha["org"], beta["org"]):
        assert_tenant_isolation(database, org, TENANT_TABLES)
    foreign = query(
        database,
        "SELECT conrelid::regclass::text FROM pg_constraint WHERE contype = 'f' "
        "AND confrelid = 'conversations'::regclass ORDER BY 1",
    )
    # chat_usage deliberately has no key to conversations from 0007 on: usage outlives them.
    assert foreign == [("messages",), ("widget_sessions",)]


def test_downgrade_to_0006_and_back_keeps_everything_0006_can_hold(database: TestDatabase) -> None:
    migrate("0006", "downgrade")
    seed(database)
    migrate("head", "upgrade")
    before = counts(database, CORE_TABLES)
    usage = usage_rows(database)

    migrate("0006", "downgrade")

    assert revision(database) == "0006"
    assert counts(database, CORE_TABLES) == before
    assert usage_rows(database) == usage
    tables = {r[0] for r in query(database, "SELECT tablename FROM pg_tables")}
    assert not tables & set(PHASE7_TABLES)  # 0007-only data cannot be kept below 0007
    assert_protections(database, TENANT_TABLES)
    migrate("head", "upgrade")
    assert revision(database) == "0007"
    assert counts(database, CORE_TABLES) == before
    assert usage_rows(database) == usage


def test_downgrade_is_refused_without_loss_once_a_conversation_was_deleted(
    database: TestDatabase,
) -> None:
    """Known limitation: 0006 requires every usage record to have a conversation. The downgrade
    must then fail as a whole; recovery is forward, never by deleting usage."""
    migrate("0006", "downgrade")
    alpha, _ = seed(database)
    migrate("head", "upgrade")
    query(database, "DELETE FROM conversations WHERE id = :c", c=alpha["playground"])
    query(
        database,
        "INSERT INTO analytics_daily (org_id, chatbot_id, day, channel, conversations) "
        "VALUES (:o, :b, current_date, 'widget', 7)",
        o=alpha["org"],
        b=alpha["bot"],
    )
    before = counts(database, (*CORE_TABLES, *PHASE7_TABLES))
    usage = usage_rows(database)

    with pytest.raises(subprocess.CalledProcessError) as failure:
        migrate("0006", "downgrade")

    assert b"chat_usage_org_id_conversation_id_fkey" in failure.value.stderr
    assert revision(database) == "0007"
    assert counts(database, (*CORE_TABLES, *PHASE7_TABLES)) == before
    assert usage_rows(database) == usage
    assert_protections(database, (*TENANT_TABLES, *PHASE7_TABLES))
