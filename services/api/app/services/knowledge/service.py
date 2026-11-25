"""Knowledge use cases (API side): uploads, website sources, documents, reprocessing, search.

Every function receives a verified ``TenantContext`` (org GUC already set) and re-checks that the
chatbot/source/document belongs to ``ctx.org`` in SQL; foreign ids behave exactly like missing
ones (404). Heavy work (extraction, embedding, crawling) happens in Celery workers; this layer
validates, records the job and returns quickly.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.core.errors import ApiError, not_found, validation_error
from app.core.ids import new_id
from app.models.chatbots import Chatbot
from app.models.identity import utcnow
from app.models.knowledge import (
    Document,
    DocumentChunk,
    IngestionJob,
    KnowledgeSource,
    StorageDeletion,
)
from app.models.tenancy import Organization
from app.rag import retrieval
from app.rag.errors import IngestionError, TransientIngestionError
from app.rag.files import validate_upload
from app.rag.pipeline import REFRESH_SOURCE_SQL
from app.rag.storage import StorageError, document_key
from app.services.chatbots.service import get_chatbot
from app.services.tenancy.audit import record_audit

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.request_meta import RequestMeta
    from app.schemas.knowledge import CreateWebsiteSourceRequest, SearchRequest
    from app.services.container import AppServices
    from app.services.tenancy.context import TenantContext


def _ingestion_to_api(exc: IngestionError) -> ApiError:
    status = {"unsupported_type": 415, "too_large": 413}.get(exc.code, 422)
    code = {"unsupported_type": "unsupported_media_type", "too_large": "file_too_large"}.get(
        exc.code, exc.code
    )
    return ApiError(status, code, "Upload rejected", detail=exc.user_message)


def _already_processing() -> ApiError:
    return ApiError(
        409, "already_processing", "Conflict", detail="This item is already being processed."
    )


# ---------------------------------------------------------------------------------- helpers


async def _lock_org(db: AsyncSession, ctx: TenantContext) -> None:
    """Serialize quota-sensitive writes for one organization (same technique as chatbot create)."""
    await db.execute(select(Organization.id).where(Organization.id == ctx.org.id).with_for_update())


async def _file_source(db: AsyncSession, ctx: TenantContext, chatbot: Chatbot) -> KnowledgeSource:
    source = await db.scalar(
        select(KnowledgeSource).where(
            KnowledgeSource.org_id == ctx.org.id,
            KnowledgeSource.chatbot_id == chatbot.id,
            KnowledgeSource.kind == "file",
        )
    )
    if source is None:
        source = KnowledgeSource(
            org_id=ctx.org.id,
            chatbot_id=chatbot.id,
            kind="file",
            name="Uploaded files",
            created_by=ctx.user.id,
        )
        db.add(source)
        await db.flush()
    return source


def _new_job(
    ctx: TenantContext,
    chatbot_id: uuid.UUID,
    source_id: uuid.UUID,
    document_id: uuid.UUID | None,
    kind: str,
    max_attempts: int,
) -> IngestionJob:
    return IngestionJob(
        id=new_id(),
        org_id=ctx.org.id,
        chatbot_id=chatbot_id,
        source_id=source_id,
        document_id=document_id,
        kind=kind,
        max_attempts=max_attempts,
        created_by=ctx.user.id,
    )


async def latest_jobs(
    db: AsyncSession,
    org_id: uuid.UUID,
    *,
    document_ids: list[uuid.UUID] | None = None,
    source_ids: list[uuid.UUID] | None = None,
) -> dict[uuid.UUID, IngestionJob]:
    """Most recent job per document (or per crawl source)."""
    column = IngestionJob.document_id if document_ids is not None else IngestionJob.source_id
    ids = document_ids if document_ids is not None else (source_ids or [])
    if not ids:
        return {}
    stmt = (
        select(IngestionJob)
        .where(IngestionJob.org_id == org_id, column.in_(ids))
        .order_by(IngestionJob.queued_at.desc(), IngestionJob.id.desc())
    )
    result: dict[uuid.UUID, IngestionJob] = {}
    for job in (await db.execute(stmt)).scalars():
        key = job.document_id if document_ids is not None else job.source_id
        if (
            key is not None
            and key not in result
            and (document_ids is not None or job.kind == "crawl")
        ):
            result[key] = job
    return result


# ------------------------------------------------------------------------------- uploads


async def create_upload(
    db: AsyncSession,
    ctx: TenantContext,
    chatbot_id: uuid.UUID,
    svc: AppServices,
    *,
    filename: str,
    declared_type: str | None,
    data: bytes,
    meta: RequestMeta,
) -> tuple[Document, IngestionJob]:
    settings = svc.settings
    chatbot = await get_chatbot(db, ctx, chatbot_id)
    if not data:
        raise ApiError(422, "empty_file", "Upload rejected", detail="The file is empty.")
    if len(data) > settings.upload_max_bytes:
        raise ApiError(
            413,
            "file_too_large",
            "Upload rejected",
            detail=f"Files can be at most {settings.upload_max_bytes // (1024 * 1024)} MB.",
        )
    try:
        valid = validate_upload(filename, declared_type, data[:4096])
    except IngestionError as exc:
        raise _ingestion_to_api(exc) from exc
    digest = hashlib.sha256(data).digest()

    await _lock_org(db, ctx)
    count = await db.scalar(
        select(func.count()).select_from(Document).where(Document.chatbot_id == chatbot.id)
    )
    used = await db.scalar(
        select(func.coalesce(func.sum(Document.size_bytes), 0)).where(Document.org_id == ctx.org.id)
    )
    if (count or 0) >= settings.max_documents_per_chatbot:
        raise ApiError(
            402,
            "plan_limit_reached",
            "Plan limit reached",
            detail=f"A chatbot can have up to {settings.max_documents_per_chatbot} documents.",
        )
    if int(used or 0) + len(data) > settings.org_storage_limit_bytes:
        raise ApiError(
            402, "plan_limit_reached", "Plan limit reached", detail="Storage limit reached."
        )
    existing = await db.scalar(
        select(Document.id).where(Document.chatbot_id == chatbot.id, Document.file_hash == digest)
    )
    if existing is not None:
        raise ApiError(
            409,
            "duplicate_document",
            "Conflict",
            detail="This exact file was already uploaded to this chatbot.",
            errors=[{"field": "file", "code": "duplicate", "message": str(existing)}],
        )

    source = await _file_source(db, ctx, chatbot)
    document_id = new_id()
    key = document_key(ctx.org.id, chatbot.id, document_id, 0)
    document = Document(
        id=document_id,
        org_id=ctx.org.id,
        chatbot_id=chatbot.id,
        source_id=source.id,
        title=valid.filename or "Untitled",
        uri=valid.filename or str(document_id),
        storage_key=key,
        mime_type=valid.mime_type,
        size_bytes=len(data),
        file_hash=digest,
        status="queued",
        created_by=ctx.user.id,
    )
    db.add(document)
    job = _new_job(
        ctx, chatbot.id, source.id, document_id, "process_document", settings.ingest_max_attempts
    )
    try:
        await db.flush()  # document must exist before the job references it
        db.add(job)
        await db.flush()
    except IntegrityError as exc:
        raise ApiError(
            409, "duplicate_document", "Conflict", detail="This file was already uploaded."
        ) from exc
    try:
        await asyncio.to_thread(svc.store.put, key, data, content_type=valid.mime_type)
    except StorageError as exc:
        raise ApiError(
            503, "storage_unavailable", "Service unavailable", detail="File storage is unavailable."
        ) from exc
    await db.execute(REFRESH_SOURCE_SQL, {"sid": source.id})
    await record_audit(
        db,
        org_id=ctx.org.id,
        actor_id=ctx.user.id,
        action="document.uploaded",
        target_type="document",
        target_id=document.id,
        metadata={
            "mime_type": valid.mime_type,
            "size_bytes": len(data),
            "chatbot_id": str(chatbot.id),
        },
        meta=meta,
    )
    return document, job


# --------------------------------------------------------------------------------- queries


async def get_document(
    db: AsyncSession, ctx: TenantContext, chatbot_id: uuid.UUID, document_id: uuid.UUID
) -> Document:
    document = await db.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.org_id == ctx.org.id,
            Document.chatbot_id == chatbot_id,
        )
    )
    if document is None:
        raise not_found()
    return document


async def list_documents(
    db: AsyncSession,
    ctx: TenantContext,
    chatbot_id: uuid.UUID,
    *,
    source_id: uuid.UUID | None,
    status: str | None,
    query: str | None,
    limit: int = 200,
) -> list[Document]:
    await get_chatbot(db, ctx, chatbot_id)
    stmt = (
        select(Document)
        .where(Document.org_id == ctx.org.id, Document.chatbot_id == chatbot_id)
        .order_by(Document.created_at.desc(), Document.id.desc())
        .limit(limit)
    )
    if source_id:
        stmt = stmt.where(Document.source_id == source_id)
    if status:
        stmt = stmt.where(Document.status == status)
    if query:
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = stmt.where(Document.title.ilike(f"%{escaped}%", escape="\\"))
    return list((await db.execute(stmt)).scalars())


async def list_chunks(
    db: AsyncSession,
    ctx: TenantContext,
    chatbot_id: uuid.UUID,
    document_id: uuid.UUID,
    *,
    limit: int,
    offset: int,
) -> tuple[list[DocumentChunk], int]:
    document = await get_document(db, ctx, chatbot_id, document_id)
    where = (
        DocumentChunk.org_id == ctx.org.id,
        DocumentChunk.document_id == document.id,
        DocumentChunk.document_version == document.version,
    )
    total = await db.scalar(select(func.count()).select_from(DocumentChunk).where(*where))
    rows = (
        await db.execute(
            select(DocumentChunk)
            .where(*where)
            .order_by(DocumentChunk.ordinal)
            .limit(limit)
            .offset(offset)
        )
    ).scalars()
    return list(rows), int(total or 0)


async def list_sources(
    db: AsyncSession, ctx: TenantContext, chatbot_id: uuid.UUID
) -> list[KnowledgeSource]:
    await get_chatbot(db, ctx, chatbot_id)
    stmt = (
        select(KnowledgeSource)
        .where(KnowledgeSource.org_id == ctx.org.id, KnowledgeSource.chatbot_id == chatbot_id)
        .order_by(KnowledgeSource.created_at, KnowledgeSource.id)
    )
    return list((await db.execute(stmt)).scalars())


async def get_source(
    db: AsyncSession, ctx: TenantContext, chatbot_id: uuid.UUID, source_id: uuid.UUID
) -> KnowledgeSource:
    source = await db.scalar(
        select(KnowledgeSource).where(
            KnowledgeSource.id == source_id,
            KnowledgeSource.org_id == ctx.org.id,
            KnowledgeSource.chatbot_id == chatbot_id,
        )
    )
    if source is None:
        raise not_found()
    return source


# ------------------------------------------------------------------------ delete / reprocess


async def delete_document(
    db: AsyncSession,
    ctx: TenantContext,
    chatbot_id: uuid.UUID,
    document_id: uuid.UUID,
    *,
    meta: RequestMeta,
) -> None:
    """Delete the document, its chunks/vectors and jobs in one transaction; queue the original's
    removal from storage (an outbox row, so a crash can't orphan the file forever)."""
    document = await get_document(db, ctx, chatbot_id, document_id)
    source_id, key = document.source_id, document.storage_key
    await db.execute(
        delete(Document).where(Document.id == document.id, Document.org_id == ctx.org.id)
    )
    if key:
        db.add(StorageDeletion(org_id=ctx.org.id, storage_key=key))
    await db.flush()
    await db.execute(REFRESH_SOURCE_SQL, {"sid": source_id})
    await record_audit(
        db,
        org_id=ctx.org.id,
        actor_id=ctx.user.id,
        action="document.deleted",
        target_type="document",
        target_id=document_id,
        metadata={"chatbot_id": str(chatbot_id)},
        meta=meta,
    )


async def reprocess_document(
    db: AsyncSession,
    ctx: TenantContext,
    chatbot_id: uuid.UUID,
    document_id: uuid.UUID,
    svc: AppServices,
    *,
    meta: RequestMeta,
) -> IngestionJob:
    document = await get_document(db, ctx, chatbot_id, document_id)
    if document.status in {"queued", "processing"}:
        raise _already_processing()
    job = _new_job(
        ctx,
        chatbot_id,
        document.source_id,
        document.id,
        "process_document",
        svc.settings.ingest_max_attempts,
    )
    db.add(job)
    document.status = "queued"
    document.error_code = None
    document.error_message = None
    try:
        await db.flush()
    except IntegrityError as exc:
        raise _already_processing() from exc
    await db.execute(REFRESH_SOURCE_SQL, {"sid": document.source_id})
    await record_audit(
        db,
        org_id=ctx.org.id,
        actor_id=ctx.user.id,
        action="document.reprocessed",
        target_type="document",
        target_id=document.id,
        meta=meta,
    )
    return job


async def reindex_chatbot(
    db: AsyncSession,
    ctx: TenantContext,
    chatbot_id: uuid.UUID,
    svc: AppServices,
    *,
    force: bool,
    meta: RequestMeta,
) -> list[IngestionJob]:
    """Queue reprocessing for documents indexed with an older embedding model (or all, if forced).

    Documents keep serving their previous chunks until the new version is published; documents
    indexed under another embedding model are invisible to search until then (vector spaces are
    never mixed).
    """
    await get_chatbot(db, ctx, chatbot_id)
    model = svc.embedder.model_id
    stmt = select(Document).where(
        Document.org_id == ctx.org.id,
        Document.chatbot_id == chatbot_id,
        Document.status.in_(("ready", "failed")),
        Document.storage_key.is_not(None),
    )
    if not force:
        stmt = stmt.where(Document.embedding_model.is_distinct_from(model))
    documents = list((await db.execute(stmt.limit(500))).scalars())
    jobs: list[IngestionJob] = []
    for document in documents:
        job = _new_job(
            ctx,
            chatbot_id,
            document.source_id,
            document.id,
            "process_document",
            svc.settings.ingest_max_attempts,
        )
        db.add(job)
        document.status = "queued"
        jobs.append(job)
    await db.flush()
    for source_id in {d.source_id for d in documents}:
        await db.execute(REFRESH_SOURCE_SQL, {"sid": source_id})
    if jobs:
        await record_audit(
            db,
            org_id=ctx.org.id,
            actor_id=ctx.user.id,
            action="chatbot.reindexed",
            target_type="chatbot",
            target_id=chatbot_id,
            metadata={"documents": len(jobs), "model": model},
            meta=meta,
        )
    return jobs


# ------------------------------------------------------------------------------- websites


async def create_website_source(
    db: AsyncSession,
    ctx: TenantContext,
    chatbot_id: uuid.UUID,
    svc: AppServices,
    body: CreateWebsiteSourceRequest,
    *,
    meta: RequestMeta,
) -> tuple[KnowledgeSource, IngestionJob]:
    settings = svc.settings
    chatbot = await get_chatbot(db, ctx, chatbot_id)
    if (
        body.max_pages > settings.crawl_max_pages_limit
        or body.max_depth > settings.crawl_max_depth_limit
    ):
        raise validation_error(
            "max_pages",
            f"At most {settings.crawl_max_pages_limit} pages and "
            f"depth {settings.crawl_max_depth_limit}.",
            code="out_of_range",
        )
    try:
        # Syntax + DNS check now for fast feedback; the crawler re-checks every request.
        await asyncio.to_thread(svc.fetcher.check, body.url)
    except IngestionError as exc:
        raise ApiError(
            422,
            exc.code,
            "Website rejected",
            detail=exc.user_message,
            errors=[{"field": "url", "code": exc.code, "message": exc.user_message}],
        ) from exc
    host = (urlsplit(body.url).hostname or "").lower()
    await _lock_org(db, ctx)
    source = KnowledgeSource(
        org_id=ctx.org.id,
        chatbot_id=chatbot.id,
        kind="website",
        name=(body.name or host)[:200],
        status="syncing",
        config={
            "start_url": body.url,
            "max_pages": body.max_pages,
            "max_depth": body.max_depth,
            "include": body.include,
            "exclude": body.exclude,
            "authorized_by": str(ctx.user.id),
            "authorized_at": utcnow().isoformat(),
        },
        created_by=ctx.user.id,
    )
    db.add(source)
    await db.flush()
    job = _new_job(ctx, chatbot.id, source.id, None, "crawl", settings.ingest_max_attempts)
    db.add(job)
    await db.flush()
    await record_audit(
        db,
        org_id=ctx.org.id,
        actor_id=ctx.user.id,
        action="source.created",
        target_type="source",
        target_id=source.id,
        metadata={"kind": "website", "host": host},
        meta=meta,
    )
    return source, job


async def sync_source(
    db: AsyncSession,
    ctx: TenantContext,
    chatbot_id: uuid.UUID,
    source_id: uuid.UUID,
    svc: AppServices,
    *,
    meta: RequestMeta,
) -> IngestionJob:
    source = await get_source(db, ctx, chatbot_id, source_id)
    if source.kind != "website":
        raise ApiError(
            422, "not_syncable", "Unprocessable", detail="Only website sources can be synced."
        )
    job = _new_job(ctx, chatbot_id, source.id, None, "crawl", svc.settings.ingest_max_attempts)
    db.add(job)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise _already_processing() from exc
    source.status = "syncing"
    await record_audit(
        db,
        org_id=ctx.org.id,
        actor_id=ctx.user.id,
        action="source.synced",
        target_type="source",
        target_id=source.id,
        meta=meta,
    )
    return job


async def delete_source(
    db: AsyncSession,
    ctx: TenantContext,
    chatbot_id: uuid.UUID,
    source_id: uuid.UUID,
    *,
    meta: RequestMeta,
) -> None:
    source = await get_source(db, ctx, chatbot_id, source_id)
    keys = (
        await db.execute(
            select(Document.storage_key).where(
                Document.source_id == source.id, Document.storage_key.is_not(None)
            )
        )
    ).scalars()
    for key in keys:
        db.add(StorageDeletion(org_id=ctx.org.id, storage_key=key))
    # Cascades remove documents, chunks (vectors) and jobs in this same transaction.
    await db.execute(delete(KnowledgeSource).where(KnowledgeSource.id == source.id))
    await record_audit(
        db,
        org_id=ctx.org.id,
        actor_id=ctx.user.id,
        action="source.deleted",
        target_type="source",
        target_id=source_id,
        metadata={"kind": source.kind},
        meta=meta,
    )


# ---------------------------------------------------------------------------------- search


async def search_chatbot(
    db: AsyncSession,
    ctx: TenantContext,
    chatbot_id: uuid.UUID,
    svc: AppServices,
    body: SearchRequest,
) -> tuple[list[retrieval.RetrievedChunk], int]:
    chatbot = await get_chatbot(db, ctx, chatbot_id)
    started = time.monotonic()
    try:
        vector = await asyncio.to_thread(svc.embedder.embed_query, body.query)
    except TransientIngestionError as exc:
        raise ApiError(
            503, "embedding_unavailable", "Service unavailable", detail=exc.user_message
        ) from exc
    except IngestionError as exc:
        raise ApiError(502, "embedding_failed", "Bad gateway", detail=exc.user_message) from exc
    results = await retrieval.search(
        db,
        org_id=ctx.org.id,
        chatbot_id=chatbot.id,
        query_vector=vector,
        question=body.query,
        embedding_model=svc.embedder.model_id,
        top_k=body.top_k or chatbot.retrieval_top_k,
        mode=body.mode,
        candidates=svc.settings.retrieval_candidates,
        min_vector_score=body.min_score
        if body.min_score is not None
        else svc.settings.retrieval_min_vector_score,
    )
    return results, int((time.monotonic() - started) * 1000)
