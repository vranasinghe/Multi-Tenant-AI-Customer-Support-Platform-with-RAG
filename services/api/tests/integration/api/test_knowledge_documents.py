"""Document ingestion end to end through the HTTP API, with workers run in-process.

Covers: upload validation, processing states and errors, chunk metadata, deletion (vectors,
storage, jobs), reprocessing, quotas, RBAC and cross-tenant isolation.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.rag.maintenance import purge_storage
from app.rag.queue import RecordingJobQueue
from app.rag.runtime import Runtime
from app.rag.storage import MemoryObjectStore
from tests.integration.api.conftest import Actor, Api
from tests.support.documents import (
    make_blank_pdf,
    make_docx,
    make_encrypted_pdf,
    make_pdf,
)
from tests.support.rag import rows, run_jobs, scalar

pytestmark = pytest.mark.integration

PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

SHIPPING = (
    "Standard shipping to the United States takes three to five business days. "
    "Express shipping takes one to two business days and costs extra. "
    "Orders over fifty dollars qualify for free standard shipping."
)
RETURNS = (
    "Items may be returned within thirty days of delivery for a full refund. "
    "Returned items must be unused and in their original packaging."
)


def new_bot(actor: Actor, name: str | None = None) -> str:
    response = actor.post(
        f"/orgs/{actor.org_id}/chatbots", {"name": name or f"Bot {uuid.uuid4().hex[:6]}"}
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def docs_path(actor: Actor, bot: str) -> str:
    return f"/orgs/{actor.org_id}/chatbots/{bot}"


def upload(
    actor: Actor,
    bot: str,
    filename: str,
    data: bytes,
    content_type: str = "application/octet-stream",
) -> Any:
    return actor.request(
        "POST",
        f"{docs_path(actor, bot)}/documents",
        params={"filename": filename},
        content=data,
        headers={"Content-Type": content_type},
    )


def get_doc(actor: Actor, bot: str, document_id: str) -> dict[str, Any]:
    response = actor.get(f"{docs_path(actor, bot)}/documents/{document_id}")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def search(actor: Actor, bot: str, query: str, **extra: Any) -> list[dict[str, Any]]:
    response = actor.post(f"{docs_path(actor, bot)}/retrieval/search", {"query": query, **extra})
    assert response.status_code == 200, response.text
    results: list[dict[str, Any]] = response.json()["results"]
    return results


def ingest(
    api: Api,
    rt: Runtime,
    queue: RecordingJobQueue,
    actor: Actor,
    bot: str,
    name: str,
    data: bytes,
    ctype: str,
) -> dict[str, Any]:
    response = upload(actor, bot, name, data, ctype)
    assert response.status_code == 201, response.text
    run_jobs(rt, queue)
    return get_doc(actor, bot, response.json()["id"])


# ---------------------------------------------------------------------- happy paths


def test_each_supported_format_reaches_ready_with_chunks_and_metadata(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue
) -> None:
    owner = api.signup()
    bot = new_bot(owner)

    pdf = ingest(
        api, runtime, job_queue, owner, bot, "policy.pdf", make_pdf([SHIPPING, RETURNS]), PDF
    )
    docx = ingest(
        api,
        runtime,
        job_queue,
        owner,
        bot,
        "handbook.docx",
        make_docx(
            [
                ("h1", "Warranty"),
                ("p", "Every product has a two year limited warranty."),
                ("h2", "Claims"),
                ("p", "Claims need a receipt and the serial number."),
            ]
        ),
        DOCX,
    )
    txt = ingest(
        api,
        runtime,
        job_queue,
        owner,
        bot,
        "faq.txt",
        b"# Support hours\n\nWe answer email weekdays from nine to five.",
        "text/plain",
    )

    for doc in (pdf, docx, txt):
        assert doc["status"] == "ready", doc
        assert doc["chunk_count"] >= 1 and doc["version"] == 1
        assert doc["job"]["status"] == "succeeded"
        assert doc["embedding_model"] == "hash-v1" and doc["needs_reindex"] is False
    assert pdf["page_count"] == 2

    pdf_chunks = owner.get(f"{docs_path(owner, bot)}/documents/{pdf['id']}/chunks").json()
    assert {c["page_start"] for c in pdf_chunks["data"]} == {1, 2}
    docx_chunks = owner.get(f"{docs_path(owner, bot)}/documents/{docx['id']}/chunks").json()["data"]
    assert [c["heading_path"] for c in docx_chunks] == [["Warranty"], ["Warranty", "Claims"]]
    sources = owner.get(f"{docs_path(owner, bot)}/sources").json()["data"]
    assert len(sources) == 1 and sources[0]["kind"] == "file"
    assert sources[0]["status"] == "ready" and sources[0]["stats"]["documents"] == 3


def test_upload_returns_immediately_in_queued_state_and_enqueues_one_job(
    api: Api, job_queue: RecordingJobQueue
) -> None:
    owner = api.signup()
    bot = new_bot(owner)

    response = upload(owner, bot, "a.txt", b"hello world document", "text/plain")

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "queued" and body["chunk_count"] == 0 and body["title"] == "a.txt"
    assert [(k, str(j)) for _, j, k in job_queue.jobs] == [("process_document", body["job"]["id"])]
    assert "storage_key" not in body and "file_hash" not in body


def test_retrieval_finds_the_right_document_and_reports_provenance(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue
) -> None:
    owner = api.signup()
    bot = new_bot(owner)
    ingest(api, runtime, job_queue, owner, bot, "shipping.txt", SHIPPING.encode(), "text/plain")
    returns = ingest(
        api, runtime, job_queue, owner, bot, "returns.txt", RETURNS.encode(), "text/plain"
    )

    results = search(owner, bot, "How many days do I have to return an item for a refund?")

    assert results[0]["document_id"] == returns["id"]
    assert results[0]["document_title"] == "returns.txt"
    assert "thirty days" in results[0]["content"]
    assert results[0]["vector_rank"] == 1 and results[0]["keyword_rank"] == 1
    assert 0 < results[0]["vector_score"] <= 1


@pytest.mark.parametrize("mode", ["vector", "keyword", "hybrid"])
def test_all_retrieval_modes_work(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue, mode: str
) -> None:
    owner = api.signup()
    bot = new_bot(owner)
    ingest(api, runtime, job_queue, owner, bot, "shipping.txt", SHIPPING.encode(), "text/plain")

    results = search(owner, bot, "express shipping cost", mode=mode, top_k=3)

    assert results and "Express shipping" in results[0]["content"]


def test_min_score_returns_nothing_for_irrelevant_questions(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue
) -> None:
    owner = api.signup()
    bot = new_bot(owner)
    ingest(api, runtime, job_queue, owner, bot, "shipping.txt", SHIPPING.encode(), "text/plain")

    assert (
        search(owner, bot, "what is the airspeed velocity of an unladen swallow", min_score=0.3)
        == []
    )
    assert search(owner, bot, "express shipping cost", min_score=0.3) != []


# ---------------------------------------------------------------- upload validation


@pytest.mark.parametrize(
    ("filename", "data", "ctype", "status", "code"),
    [
        ("virus.pdf", b"MZ\x90\x00\x03\x00\x00\x00", PDF, 415, "unsupported_media_type"),
        ("notes.exe", b"MZ\x90\x00", "application/octet-stream", 415, "unsupported_media_type"),
        ("page.html", b"<html>", "text/html", 415, "unsupported_media_type"),
        ("fake.docx", make_pdf(["x"]), DOCX, 415, "unsupported_media_type"),
        ("a.txt", b"\x00\x01\x02\x03", "text/plain", 415, "unsupported_media_type"),
        ("a.pdf", make_pdf(["x"]), "text/plain", 415, "unsupported_media_type"),
        ("locked.docx", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64, DOCX, 422, "encrypted"),
        ("empty.txt", b"", "text/plain", 422, "empty_file"),
        ("big.txt", b"x" * (70 * 1024), "text/plain", 413, "file_too_large"),
    ],
)
def test_invalid_uploads_are_rejected_before_anything_is_stored(
    api: Api,
    object_store: MemoryObjectStore,
    job_queue: RecordingJobQueue,
    filename: str,
    data: bytes,
    ctype: str,
    status: int,
    code: str,
) -> None:
    owner = api.signup()
    bot = new_bot(owner)

    response = upload(owner, bot, filename, data, ctype)

    assert (response.status_code, response.json()["code"]) == (status, code)
    assert object_store.keys() == [] and job_queue.jobs == []
    assert owner.get(f"{docs_path(owner, bot)}/documents").json()["data"] == []


def test_oversized_declared_content_length_is_refused_early(api: Api) -> None:
    owner = api.signup()
    bot = new_bot(owner)

    response = upload(owner, bot, "a.txt", b"x" * (65 * 1024), "text/plain")

    assert response.status_code == 413


def test_filenames_are_sanitized_and_never_become_storage_keys(
    api: Api, object_store: MemoryObjectStore
) -> None:
    owner = api.signup()
    bot = new_bot(owner)

    response = upload(
        owner,
        bot,
        "../../etc/pass" + chr(0x202E) + "wd.txt",
        b"some harmless text here",
        "text/plain",
    )

    assert response.status_code == 201
    assert response.json()["title"] == "passwd.txt"
    [key] = object_store.keys()
    assert key.startswith(f"orgs/{owner.org_id}/chatbots/{bot}/documents/")
    assert "passwd" not in key and ".." not in key


def test_identical_upload_is_a_conflict_even_under_another_name(api: Api) -> None:
    owner = api.signup()
    bot = new_bot(owner)
    data = b"exactly the same bytes in both uploads"
    assert upload(owner, bot, "one.txt", data, "text/plain").status_code == 201

    again = upload(owner, bot, "two.txt", data, "text/plain")

    assert again.status_code == 409 and again.json()["code"] == "duplicate_document"
    other_bot = new_bot(owner)
    assert upload(owner, other_bot, "one.txt", data, "text/plain").status_code == 201


def test_storage_outage_at_upload_leaves_no_trace(
    api: Api, object_store: MemoryObjectStore, job_queue: RecordingJobQueue
) -> None:
    owner = api.signup()
    bot = new_bot(owner)
    object_store.fail_next_put = 1

    response = upload(owner, bot, "a.txt", b"hello hello hello", "text/plain")

    assert response.status_code == 503 and response.json()["code"] == "storage_unavailable"
    assert owner.get(f"{docs_path(owner, bot)}/documents").json()["data"] == []
    assert job_queue.jobs == []
    assert upload(owner, bot, "a.txt", b"hello hello hello", "text/plain").status_code == 201


# ------------------------------------------------------------- processing failures


@pytest.mark.parametrize(
    ("name", "data", "ctype", "code"),
    [
        ("scan.pdf", make_blank_pdf(2), PDF, "no_text"),
        ("locked.pdf", make_encrypted_pdf(), PDF, "encrypted"),
        ("broken.pdf", b"%PDF-1.4\nthis is garbage, not a pdf at all", PDF, "corrupt"),
        ("empty.docx", make_docx([("p", "   ")]), DOCX, "no_text"),
        ("blank.txt", b"   \n\n   \n", "text/plain", "no_text"),
    ],
)
def test_unreadable_documents_fail_with_a_stable_code_and_a_safe_message(
    api: Api,
    runtime: Runtime,
    job_queue: RecordingJobQueue,
    name: str,
    data: bytes,
    ctype: str,
    code: str,
) -> None:
    owner = api.signup()
    bot = new_bot(owner)

    doc = ingest(api, runtime, job_queue, owner, bot, name, data, ctype)

    assert doc["status"] == "failed" and doc["error_code"] == code
    assert doc["error_message"] and "Traceback" not in doc["error_message"]
    assert doc["job"]["status"] == "failed" and doc["job"]["error_code"] == code
    assert doc["chunk_count"] == 0
    assert (
        scalar(
            api.owner_engine,
            "SELECT count(*) FROM document_chunks WHERE document_id = :d",
            d=doc["id"],
        )
        == 0
    )
    assert search(owner, bot, "anything at all") == []


def test_same_content_in_a_different_format_is_flagged_as_a_duplicate(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue
) -> None:
    owner = api.signup()
    bot = new_bot(owner)
    first = ingest(api, runtime, job_queue, owner, bot, "a.txt", SHIPPING.encode(), "text/plain")
    second = ingest(
        api, runtime, job_queue, owner, bot, "b.docx", make_docx([("p", SHIPPING)]), DOCX
    )

    assert first["status"] == "ready"
    assert second["status"] == "failed" and second["error_code"] == "duplicate_content"
    assert len(search(owner, bot, "shipping business days")) == len(
        owner.get(f"{docs_path(owner, bot)}/documents/{first['id']}/chunks").json()["data"]
    )


# ------------------------------------------------------------ delete & reprocess


def test_delete_removes_chunks_vectors_jobs_and_eventually_the_stored_original(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue, object_store: MemoryObjectStore
) -> None:
    owner = api.signup()
    bot = new_bot(owner)
    doc = ingest(
        api, runtime, job_queue, owner, bot, "shipping.txt", SHIPPING.encode(), "text/plain"
    )
    keep = ingest(
        api, runtime, job_queue, owner, bot, "returns.txt", RETURNS.encode(), "text/plain"
    )
    assert search(owner, bot, "express shipping")[0]["document_id"] == doc["id"]
    assert len(object_store.keys()) == 2

    assert owner.delete(f"{docs_path(owner, bot)}/documents/{doc['id']}").status_code == 204

    # gone immediately, in the same transaction as the delete
    assert all(r["document_id"] != doc["id"] for r in search(owner, bot, "express shipping"))
    assert (
        scalar(
            api.owner_engine,
            "SELECT count(*) FROM document_chunks WHERE document_id = :d",
            d=doc["id"],
        )
        == 0
    )
    assert (
        scalar(
            api.owner_engine,
            "SELECT count(*) FROM ingestion_jobs WHERE document_id = :d",
            d=doc["id"],
        )
        == 0
    )
    assert owner.get(f"{docs_path(owner, bot)}/documents/{doc['id']}").status_code == 404
    assert [d["id"] for d in owner.get(f"{docs_path(owner, bot)}/documents").json()["data"]] == [
        keep["id"]
    ]
    # the original is queued for removal and then deleted by the maintenance job
    assert (
        scalar(
            api.owner_engine,
            "SELECT count(*) FROM storage_deletions WHERE org_id = :o",
            o=owner.org_id,
        )
        == 1
    )
    assert len(object_store.keys()) == 2
    assert purge_storage(runtime) >= 1
    assert len(object_store.keys()) == 1 and "returns" not in object_store.keys()[0]
    assert (
        scalar(
            api.owner_engine,
            "SELECT count(*) FROM storage_deletions WHERE org_id = :o",
            o=owner.org_id,
        )
        == 0
    )
    assert owner.delete(f"{docs_path(owner, bot)}/documents/{doc['id']}").status_code == 404


def test_storage_purge_retries_failures_and_never_touches_foreign_keys(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue, object_store: MemoryObjectStore
) -> None:
    owner, other = api.signup(), api.signup()
    other_bot = new_bot(other)
    ingest(api, runtime, job_queue, other, other_bot, "theirs.txt", SHIPPING.encode(), "text/plain")
    [their_key] = object_store.keys()
    # a corrupted outbox row in org A that points into org B's prefix
    api.sql(
        "INSERT INTO storage_deletions (id, org_id, storage_key) VALUES (gen_random_uuid(), :o, :k)",
        o=owner.org_id,
        k=their_key,
    )

    purge_storage(runtime)

    assert object_store.keys() == [their_key]  # untouched
    pending = scalar(
        api.owner_engine,
        "SELECT count(*) FROM storage_deletions WHERE org_id = :o",
        o=owner.org_id,
    )
    assert pending == 0  # the bogus row was dropped without touching the file


def test_reprocess_publishes_a_new_version_without_duplicating_chunks(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue
) -> None:
    owner = api.signup()
    bot = new_bot(owner)
    doc = ingest(
        api,
        runtime,
        job_queue,
        owner,
        bot,
        "shipping.txt",
        (SHIPPING + " " + RETURNS).encode(),
        "text/plain",
    )
    chunks_before = doc["chunk_count"]
    assert chunks_before >= 2

    response = owner.post(f"{docs_path(owner, bot)}/documents/{doc['id']}/reprocess")
    assert response.status_code == 200 and response.json()["status"] == "queued"
    run_jobs(runtime, job_queue)

    after = get_doc(owner, bot, doc["id"])
    assert (
        after["status"] == "ready"
        and after["version"] == 2
        and after["chunk_count"] == chunks_before
    )
    assert (
        scalar(
            api.owner_engine,
            "SELECT count(*) FROM document_chunks WHERE document_id = :d",
            d=doc["id"],
        )
        == chunks_before
    )
    assert (
        scalar(
            api.owner_engine,
            "SELECT min(document_version) FROM document_chunks WHERE document_id = :d",
            d=doc["id"],
        )
        == 2
    )


def test_failed_document_can_be_retried_after_a_storage_blip_and_second_reprocess_conflicts(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue, object_store: MemoryObjectStore
) -> None:
    owner = api.signup()
    bot = new_bot(owner)
    response = upload(owner, bot, "a.txt", SHIPPING.encode(), "text/plain")
    doc_id = response.json()["id"]
    key = object_store.keys()[0]
    original = object_store._objects.pop(key)  # the original goes missing
    run_jobs(runtime, job_queue)
    failed = get_doc(owner, bot, doc_id)
    assert failed["status"] == "failed" and failed["error_code"] == "storage_error"

    object_store.put(key, original, content_type="text/plain")
    retry = owner.post(f"{docs_path(owner, bot)}/documents/{doc_id}/reprocess")
    assert retry.status_code == 200
    assert owner.post(f"{docs_path(owner, bot)}/documents/{doc_id}/reprocess").status_code == 409
    run_jobs(runtime, job_queue)

    assert get_doc(owner, bot, doc_id)["status"] == "ready"
    assert owner.post(f"{docs_path(owner, bot)}/documents/{doc_id}/reprocess").status_code == 200


# ---------------------------------------------------------------- limits & RBAC


def test_document_and_storage_quotas_are_enforced(api: Api) -> None:
    owner = api.signup()
    bot = new_bot(owner)
    api.sql("UPDATE organizations SET settings = settings WHERE id = :o", o=owner.org_id)
    # fill the chatbot up to its document quota directly in the database
    limit = 500
    source = upload(owner, bot, "seed.txt", b"seed document text", "text/plain").json()["source_id"]
    api.sql(
        "INSERT INTO documents (id, org_id, chatbot_id, source_id, title, uri, status) "
        "SELECT gen_random_uuid(), CAST(:o AS uuid), CAST(:b AS uuid), CAST(:s AS uuid), 'd' || g, 'u' || g, 'ready' "
        "FROM generate_series(1, :n) g",
        o=owner.org_id,
        b=bot,
        s=source,
        n=limit - 1,
    )

    blocked = upload(owner, bot, "one-too-many.txt", b"another document", "text/plain")

    assert blocked.status_code == 402 and blocked.json()["code"] == "plan_limit_reached"


def test_viewers_can_read_but_not_change_knowledge(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue
) -> None:
    owner = api.signup()
    bot = new_bot(owner)
    doc = ingest(api, runtime, job_queue, owner, bot, "a.txt", SHIPPING.encode(), "text/plain")
    viewer, agent = api.signup(), api.signup()
    for actor, role in ((viewer, "viewer"), (agent, "agent")):
        owner.post(f"/orgs/{owner.org_id}/invitations", {"email": actor.email, "role": role})
        token = api.mailbox.last_token(actor.email, path="invite")
        assert actor.post("/invitations/accept", {"token": token}).status_code == 200
        actor.org_id = owner.org_id
    base = docs_path(owner, bot)

    assert viewer.get(f"{base}/documents").status_code == 200
    assert viewer.get(f"{base}/documents/{doc['id']}/chunks").status_code == 200
    assert viewer.get(f"{base}/sources").status_code == 200
    assert upload(viewer, bot, "v.txt", b"viewer upload", "text/plain").status_code == 403
    assert viewer.delete(f"{base}/documents/{doc['id']}").status_code == 403
    assert viewer.post(f"{base}/documents/{doc['id']}/reprocess").status_code == 403
    assert viewer.post(f"{base}/reindex").status_code == 403
    assert viewer.post(f"{base}/retrieval/search", {"query": "shipping"}).status_code == 403

    assert agent.post(f"{base}/retrieval/search", {"query": "shipping"}).status_code == 200
    assert upload(agent, bot, "ok.txt", b"agent upload text", "text/plain").status_code == 201
    assert agent.delete(f"{base}/documents/{doc['id']}").status_code == 204


def test_unverified_users_cannot_upload_and_restricted_orgs_are_read_only(api: Api) -> None:
    owner = api.signup()
    bot = new_bot(owner)
    api.sql("UPDATE users SET email_verified_at = NULL WHERE id = :u", u=owner.user_id)

    unverified = upload(owner, bot, "a.txt", b"text for the doc", "text/plain")

    assert unverified.status_code == 403 and unverified.json()["code"] == "email_not_verified"
    assert owner.get(f"{docs_path(owner, bot)}/documents").status_code == 200

    api.sql("UPDATE users SET email_verified_at = now() WHERE id = :u", u=owner.user_id)
    api.sql("UPDATE organizations SET status = 'restricted' WHERE id = :o", o=owner.org_id)
    restricted = upload(owner, bot, "a.txt", b"text for the doc", "text/plain")

    assert restricted.status_code == 403 and restricted.json()["code"] == "org_restricted"
    assert owner.get(f"{docs_path(owner, bot)}/documents").status_code == 200


# --------------------------------------------------------------- tenant isolation


def test_other_tenants_cannot_see_search_or_delete_my_documents(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue
) -> None:
    a, b = api.signup(), api.signup()
    a_bot, b_bot = new_bot(a), new_bot(b)
    doc = ingest(api, runtime, job_queue, a, a_bot, "secret.txt", SHIPPING.encode(), "text/plain")
    base_a, doc_path = docs_path(a, a_bot), f"/documents/{doc['id']}"

    probes = {
        "list (foreign org path)": b.get(f"{base_a}/documents"),
        "get (foreign org path)": b.get(f"{base_a}{doc_path}"),
        "get (idor under my org)": b.get(f"{docs_path(b, b_bot)}{doc_path}"),
        "get (idor, my bot, their org)": b.get(f"/orgs/{b.org_id}/chatbots/{a_bot}{doc_path}"),
        "chunks (idor)": b.get(f"{docs_path(b, b_bot)}{doc_path}/chunks"),
        "delete (idor)": b.delete(f"{docs_path(b, b_bot)}{doc_path}"),
        "reprocess (idor)": b.post(f"{docs_path(b, b_bot)}{doc_path}/reprocess"),
        "search (foreign)": b.post(f"{base_a}/retrieval/search", {"query": "shipping"}),
        "search (their bot id under my org)": b.post(
            f"/orgs/{b.org_id}/chatbots/{a_bot}/retrieval/search", {"query": "shipping"}
        ),
        "upload (foreign)": upload(b, a_bot, "x.txt", b"planted", "text/plain"),
        "sources (foreign)": b.get(f"{base_a}/sources"),
    }

    assert {k: r.status_code for k, r in probes.items()} == dict.fromkeys(probes, 404)
    assert get_doc(a, a_bot, doc["id"])["status"] == "ready"
    assert not any("shipping" in r.text.lower() for r in probes.values())


def test_identical_content_in_two_tenants_never_crosses_in_retrieval(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue
) -> None:
    """Chunks with *identical* embeddings in two orgs (and two bots in one org)."""
    a, b = api.signup(), api.signup()
    a1, a2, b1 = new_bot(a), new_bot(a), new_bot(b)
    ids = {}
    for label, actor, bot in (("a1", a, a1), ("a2", a, a2), ("b1", b, b1)):
        ids[label] = ingest(
            api, runtime, job_queue, actor, bot, "same.txt", SHIPPING.encode(), "text/plain"
        )["id"]

    for label, actor, bot in (("a1", a, a1), ("a2", a, a2), ("b1", b, b1)):
        for mode in ("vector", "keyword", "hybrid"):
            found = search(actor, bot, "standard shipping business days", mode=mode)
            assert found and {r["document_id"] for r in found} == {ids[label]}, (label, mode)


def test_retrieval_ignores_deleted_chatbots_and_unpublished_versions(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue
) -> None:
    owner = api.signup()
    bot = new_bot(owner)
    doc = ingest(api, runtime, job_queue, owner, bot, "a.txt", SHIPPING.encode(), "text/plain")
    assert search(owner, bot, "express shipping")

    # a document being reprocessed keeps serving its last published version
    api.sql("UPDATE documents SET status = 'processing' WHERE id = :d", d=doc["id"])
    assert search(owner, bot, "express shipping")
    api.sql("UPDATE documents SET status = 'ready' WHERE id = :d", d=doc["id"])
    # chunks of a version the document no longer points at are invisible
    api.sql("UPDATE documents SET version = version + 1 WHERE id = :d", d=doc["id"])
    assert search(owner, bot, "express shipping") == []
    api.sql("UPDATE documents SET version = version - 1 WHERE id = :d", d=doc["id"])
    # deleting the chatbot hides everything it indexed
    assert owner.delete(f"/orgs/{owner.org_id}/chatbots/{bot}").status_code == 204
    assert (
        owner.post(f"{docs_path(owner, bot)}/retrieval/search", {"query": "shipping"}).status_code
        == 404
    )
    assert rows(api.owner_engine, "SELECT 1 FROM document_chunks WHERE chatbot_id = :b", b=bot)


def test_audit_log_records_actions_without_filenames_or_content(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue
) -> None:
    owner = api.signup()
    bot = new_bot(owner)
    doc = ingest(
        api, runtime, job_queue, owner, bot, "my-secret-merger.txt", SHIPPING.encode(), "text/plain"
    )
    owner.post(f"{docs_path(owner, bot)}/documents/{doc['id']}/reprocess")
    owner.delete(f"{docs_path(owner, bot)}/documents/{doc['id']}")

    entries = owner.get(f"/orgs/{owner.org_id}/audit-logs").json()["data"]
    actions = {e["action"] for e in entries if e["target_id"] == doc["id"]}

    assert actions == {"document.uploaded", "document.reprocessed", "document.deleted"}
    assert "my-secret-merger" not in str(entries) and "shipping" not in str(entries).lower()
