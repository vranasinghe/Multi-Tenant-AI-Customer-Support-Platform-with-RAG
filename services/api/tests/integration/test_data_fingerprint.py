"""`verify-data`: the evidence that a restored backup is the data that was backed up (MIG-02)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text

from app.core.data_check import fingerprint
from app.rag.storage import MemoryObjectStore
from tests.integration.test_chat_migration import database, query, seed
from tests.support.database import TestDatabase

__all__ = ["database"]

pytestmark = pytest.mark.integration


def take(database: TestDatabase, store: MemoryObjectStore) -> dict:  # type: ignore[type-arg]
    engine = create_engine(database.owner_url)
    try:
        with engine.connect() as connection:
            return fingerprint(connection, store)
    finally:
        engine.dispose()


def test_the_fingerprint_notices_changed_rows_protections_and_missing_originals(
    database: TestDatabase,
) -> None:
    alpha, _ = seed(database)
    store = MemoryObjectStore()
    key = f"orgs/{alpha['org']}/original"
    store.put(key, b"synthetic", content_type="text/plain")
    query(
        database,
        "UPDATE documents SET storage_key = :k, size_bytes = 9 WHERE id = :d",
        k=key,
        d=alpha["document"],
    )

    first = take(database, store)

    assert first["revision"] == "0007"
    assert first["tables"]["messages"]["rows"] == 8
    assert first["tables"]["document_chunks"]["rows"] == 2
    assert first["objects"] == {"referenced": 1, "problems": []}
    assert first["unprotected_tables"] == []
    assert take(database, store) == first  # the same data gives the same answer

    query(
        database,
        "UPDATE messages SET content = content || '.' WHERE id = "
        "(SELECT id FROM messages ORDER BY id LIMIT 1)",
    )
    changed = take(database, store)
    assert changed["tables"]["messages"] != first["tables"]["messages"]
    assert changed["tables"]["document_chunks"] == first["tables"]["document_chunks"]

    engine = create_engine(database.owner_url)
    with engine.begin() as connection:
        # messages keeps a second, owner-only policy, so check-rls alone would not notice this.
        connection.execute(text("DROP POLICY tenant_isolation ON messages"))
        connection.execute(text("ALTER TABLE documents NO FORCE ROW LEVEL SECURITY"))
    engine.dispose()
    store.delete(key)
    broken = take(database, store)
    assert broken["protections"] != first["protections"]
    assert [p["problem"] for p in broken["objects"]["problems"]] == ["missing"]
    assert broken["objects"]["problems"][0]["id"] == str(uuid.UUID(str(alpha["document"])))
    assert broken["unprotected_tables"] == ["documents"]
