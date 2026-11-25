"""Embedding model versioning, reindexing, and the SQL-level retrieval filters."""

from __future__ import annotations

import uuid
from dataclasses import replace

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.rag import retrieval
from app.rag.embeddings import HashingEmbedder
from app.rag.queue import RecordingJobQueue
from app.rag.runtime import Runtime
from app.services.tenancy.context import set_org_context
from tests.integration.api.conftest import Api
from tests.integration.api.test_knowledge_documents import (
    RETURNS,
    SHIPPING,
    docs_path,
    get_doc,
    ingest,
    new_bot,
    search,
)
from tests.support.database import TestDatabase
from tests.support.rag import rows, run_jobs, scalar

pytestmark = pytest.mark.integration

TXT = "text/plain"


def switch_model(api: Api, runtime: Runtime, model: str) -> None:
    """Pretend the deployment moved to another embedding model (API and workers)."""
    embedder = HashingEmbedder(model)
    runtime.embedder = embedder
    services = api.client.app.state.services  # type: ignore[attr-defined]
    api.client.app.state.services = replace(services, embedder=embedder)  # type: ignore[attr-defined]


def test_changing_the_embedding_model_marks_documents_and_never_mixes_vector_spaces(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue
) -> None:
    owner = api.signup()
    bot = new_bot(owner)
    first = ingest(api, runtime, job_queue, owner, bot, "ship.txt", SHIPPING.encode(), TXT)
    second = ingest(api, runtime, job_queue, owner, bot, "ret.txt", RETURNS.encode(), TXT)
    assert search(owner, bot, "express shipping")

    switch_model(api, runtime, "hash-v2")

    listing = owner.get(f"{docs_path(owner, bot)}/documents").json()
    assert listing["embedding_model"] == "hash-v2"
    assert [d["needs_reindex"] for d in listing["data"]] == [True, True]
    assert [d["embedding_model"] for d in listing["data"]] == ["hash-v1", "hash-v1"]
    assert search(owner, bot, "express shipping") == []  # old vectors are not compared to new ones

    response = owner.post(f"{docs_path(owner, bot)}/reindex")
    assert response.status_code == 200
    assert response.json() == {"queued": 2, "skipped": 0, "embedding_model": "hash-v2"}
    assert run_jobs(runtime, job_queue) == ["done", "done"]

    for doc in (first, second):
        after = get_doc(owner, bot, doc["id"])
        assert after["embedding_model"] == "hash-v2" and after["needs_reindex"] is False
        assert after["version"] == 2 and after["status"] == "ready"
    models = rows(
        api.owner_engine,
        "SELECT DISTINCT embedding_model FROM document_chunks WHERE chatbot_id = :b",
        b=bot,
    )
    assert models == [("hash-v2",)]
    assert search(owner, bot, "express shipping")[0]["document_id"] == first["id"]
    assert owner.post(f"{docs_path(owner, bot)}/reindex").json()["queued"] == 0  # nothing stale


def test_only_documents_of_the_current_model_are_searchable_during_a_partial_reindex(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue
) -> None:
    owner = api.signup()
    bot = new_bot(owner)
    old = ingest(api, runtime, job_queue, owner, bot, "ship.txt", SHIPPING.encode(), TXT)
    switch_model(api, runtime, "hash-v2")
    new = ingest(api, runtime, job_queue, owner, bot, "ret.txt", RETURNS.encode(), TXT)

    results = search(owner, bot, "shipping returns refund business days", top_k=10)

    assert {r["document_id"] for r in results} == {new["id"]}
    assert old["id"] not in {r["document_id"] for r in results}


def test_forced_reindex_reprocesses_everything_and_keeps_chunk_counts_stable(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue
) -> None:
    owner = api.signup()
    bot = new_bot(owner)
    doc = ingest(api, runtime, job_queue, owner, bot, "ship.txt", SHIPPING.encode() * 3, TXT)
    count = doc["chunk_count"]

    assert owner.post(f"{docs_path(owner, bot)}/reindex").json()["queued"] == 0
    assert owner.post(f"{docs_path(owner, bot)}/reindex?force=true").json()["queued"] == 1
    run_jobs(runtime, job_queue)

    after = get_doc(owner, bot, doc["id"])
    assert after["version"] == 2 and after["chunk_count"] == count
    assert (
        scalar(
            api.owner_engine,
            "SELECT count(*) FROM document_chunks WHERE document_id = :d",
            d=doc["id"],
        )
        == count
    )


def test_reindex_respects_tenancy_and_permissions(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue
) -> None:
    a, b = api.signup(), api.signup()
    a_bot, b_bot = new_bot(a), new_bot(b)
    ingest(api, runtime, job_queue, a, a_bot, "ship.txt", SHIPPING.encode(), TXT)
    switch_model(api, runtime, "hash-v2")

    assert b.post(f"{docs_path(a, a_bot)}/reindex").status_code == 404
    assert b.post(f"/orgs/{b.org_id}/chatbots/{a_bot}/reindex").status_code == 404
    assert b.post(f"{docs_path(b, b_bot)}/reindex").json()["queued"] == 0
    assert job_queue.jobs == []


def test_hnsw_and_fts_indexes_exist_on_chunks(api: Api) -> None:
    definitions = " ".join(
        r[0]
        for r in rows(
            api.owner_engine, "SELECT indexdef FROM pg_indexes WHERE tablename = 'document_chunks'"
        )
    )
    assert "USING hnsw (embedding vector_cosine_ops)" in definitions
    assert "USING gin (fts)" in definitions


async def test_sql_filters_hide_deleted_chatbots_and_foreign_tenants(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue, test_database: TestDatabase
) -> None:
    """Retrieval queried directly (below the HTTP layer) is still tenant- and chatbot-scoped."""
    a, b = api.signup(), api.signup()
    a_bot, b_bot = new_bot(a), new_bot(b)
    ingest(api, runtime, job_queue, a, a_bot, "ship.txt", SHIPPING.encode(), TXT)
    ingest(api, runtime, job_queue, b, b_bot, "ship.txt", SHIPPING.encode(), TXT)
    engine = create_async_engine(test_database.app_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    embedder = HashingEmbedder()
    vector = embedder.embed_query("express shipping")

    async def run(org: str, bot: str, *, context_org: str | None = None) -> int:
        async with factory() as db, db.begin():
            await set_org_context(db, uuid.UUID(context_org or org))
            found = await retrieval.search(
                db,
                org_id=uuid.UUID(org),
                chatbot_id=uuid.UUID(bot),
                query_vector=vector,
                question="express shipping",
                embedding_model=embedder.model_id,
            )
            return len(found)

    try:
        assert await run(a.org_id, a_bot) > 0
        # asking for A's data while the transaction is scoped to B: RLS hides it even though the
        # SQL names A's org and chatbot explicitly
        assert await run(a.org_id, a_bot, context_org=b.org_id) == 0
        # no org context at all: nothing is visible
        async with factory() as db, db.begin():
            await db.execute(text("SELECT 1"))
            assert (
                await db.execute(text("SELECT count(*) FROM document_chunks"))
            ).scalar_one() == 0
        # a chatbot id from another org never matches, even with the right org context
        assert await run(a.org_id, b_bot) == 0
        # soft-deleting the chatbot hides every chunk it owns
        assert a.delete(f"/orgs/{a.org_id}/chatbots/{a_bot}").status_code == 204
        assert await run(a.org_id, a_bot) == 0
        assert (
            scalar(
                api.owner_engine,
                "SELECT count(*) FROM document_chunks WHERE chatbot_id = :b",
                b=a_bot,
            )
            > 0
        )
    finally:
        await engine.dispose()
