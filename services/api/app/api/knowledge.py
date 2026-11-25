"""Knowledge endpoints (docs/API_SPEC.md §2.4): uploads, website sources, documents, search.

Uploads are a raw request body (``POST .../documents?filename=...``) rather than multipart, so the
size limit is enforced while streaming and no extra parser is exposed to untrusted input.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from app.api.deps import DbDep, MetaDep, ServicesDep, require
from app.core.errors import ApiError
from app.core.rate_limit import Limit
from app.models.knowledge import Document, IngestionJob, KnowledgeSource
from app.rag.files import EXTENSIONS
from app.schemas.knowledge import (
    ChunkList,
    ChunkOut,
    CreateWebsiteSourceRequest,
    DocumentList,
    DocumentOut,
    JobOut,
    ReindexResponse,
    SearchRequest,
    SearchResponse,
    SearchResultOut,
    SourceList,
    SourceOut,
    UploadLimits,
)
from app.services.knowledge import service
from app.services.tenancy.context import TenantContext

router = APIRouter(prefix="/orgs/{org_id}/chatbots/{chatbot_id}", tags=["knowledge"])

KnowledgeRead = Annotated[TenantContext, Depends(require("knowledge:read"))]
KnowledgeWrite = Annotated[TenantContext, Depends(require("knowledge:write", verified=True))]
KnowledgeEdit = Annotated[TenantContext, Depends(require("knowledge:write"))]
ChatbotTest = Annotated[TenantContext, Depends(require("chatbot:test"))]


def job_out(job: IngestionJob | None) -> JobOut | None:
    if job is None:
        return None
    return JobOut(
        id=job.id,
        kind=job.kind,
        status=job.status,
        stage=job.stage,
        attempt=job.attempt,
        max_attempts=job.max_attempts,
        error_code=job.error_code,
        stats=job.stats or {},
        queued_at=job.queued_at,
        finished_at=job.finished_at,
    )


def document_out(document: Document, job: IngestionJob | None, current_model: str) -> DocumentOut:
    return DocumentOut(
        id=document.id,
        source_id=document.source_id,
        title=document.title,
        uri=document.uri,
        mime_type=document.mime_type,
        size_bytes=document.size_bytes,
        status=document.status,
        error_code=document.error_code,
        error_message=document.error_message,
        page_count=document.page_count,
        chunk_count=document.chunk_count,
        token_count=document.token_count,
        version=document.version,
        embedding_model=document.embedding_model,
        needs_reindex=document.status == "ready" and document.embedding_model != current_model,
        job=job_out(job),
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


def source_out(source: KnowledgeSource, job: IngestionJob | None) -> SourceOut:
    config = {k: v for k, v in source.config.items() if k not in {"authorized_by"}}
    return SourceOut(
        id=source.id,
        kind=source.kind,
        name=source.name,
        status=source.status,
        config=config,
        stats=source.stats or {},
        last_synced_at=source.last_synced_at,
        created_at=source.created_at,
        job=job_out(job),
    )


@router.get("/knowledge/limits")
async def knowledge_limits(
    org_id: uuid.UUID, chatbot_id: uuid.UUID, ctx: KnowledgeRead, svc: ServicesDep
) -> UploadLimits:
    s = svc.settings
    return UploadLimits(
        max_bytes=s.upload_max_bytes,
        extensions=sorted(EXTENSIONS),
        max_documents=s.max_documents_per_chatbot,
        max_pages_per_crawl=s.crawl_max_pages_limit,
    )


# ------------------------------------------------------------------------------ documents


@router.post("/documents", status_code=status.HTTP_201_CREATED)
async def upload_document(
    org_id: uuid.UUID,
    chatbot_id: uuid.UUID,
    request: Request,
    ctx: KnowledgeWrite,
    db: DbDep,
    svc: ServicesDep,
    meta: MetaDep,
    filename: Annotated[str, Query(min_length=1, max_length=255)],
) -> DocumentOut:
    limit = svc.settings.upload_max_bytes
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise ApiError(413, "file_too_large", "Upload rejected", detail="The file is too large.")
    await svc.limiter.check(
        str(ctx.org.id), Limit("upload", svc.settings.rate_limit_upload_per_minute, 60)
    )
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > limit:
            raise ApiError(
                413, "file_too_large", "Upload rejected", detail="The file is too large."
            )
    document, job = await service.create_upload(
        db,
        ctx,
        chatbot_id,
        svc,
        filename=filename,
        declared_type=request.headers.get("content-type"),
        data=bytes(body),
        meta=meta,
    )
    await db.commit()
    svc.jobs.enqueue(org_id=ctx.org.id, job_id=job.id, kind=job.kind)
    return document_out(document, job, svc.embedder.model_id)


@router.get("/documents")
async def list_documents(
    org_id: uuid.UUID,
    chatbot_id: uuid.UUID,
    ctx: KnowledgeRead,
    db: DbDep,
    svc: ServicesDep,
    source_id: uuid.UUID | None = None,
    status_filter: Annotated[
        str | None, Query(alias="status", pattern="^(queued|processing|ready|failed)$")
    ] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> DocumentList:
    documents = await service.list_documents(
        db, ctx, chatbot_id, source_id=source_id, status=status_filter, query=q or None
    )
    jobs = await service.latest_jobs(db, ctx.org.id, document_ids=[d.id for d in documents])
    model = svc.embedder.model_id
    return DocumentList(
        data=[document_out(d, jobs.get(d.id), model) for d in documents], embedding_model=model
    )


@router.get("/documents/{document_id}")
async def get_document(
    org_id: uuid.UUID,
    chatbot_id: uuid.UUID,
    document_id: uuid.UUID,
    ctx: KnowledgeRead,
    db: DbDep,
    svc: ServicesDep,
) -> DocumentOut:
    document = await service.get_document(db, ctx, chatbot_id, document_id)
    jobs = await service.latest_jobs(db, ctx.org.id, document_ids=[document.id])
    return document_out(document, jobs.get(document.id), svc.embedder.model_id)


@router.get("/documents/{document_id}/chunks")
async def list_chunks(
    org_id: uuid.UUID,
    chatbot_id: uuid.UUID,
    document_id: uuid.UUID,
    ctx: KnowledgeRead,
    db: DbDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
) -> ChunkList:
    chunks, total = await service.list_chunks(
        db, ctx, chatbot_id, document_id, limit=limit, offset=offset
    )
    return ChunkList(
        data=[
            ChunkOut(
                id=c.id,
                ordinal=c.ordinal,
                content=c.content,
                heading_path=list(c.heading_path or []),
                page_start=c.page_start,
                page_end=c.page_end,
                token_count=c.token_count,
            )
            for c in chunks
        ],
        total=total,
    )


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    org_id: uuid.UUID,
    chatbot_id: uuid.UUID,
    document_id: uuid.UUID,
    ctx: KnowledgeEdit,
    db: DbDep,
    meta: MetaDep,
) -> None:
    await service.delete_document(db, ctx, chatbot_id, document_id, meta=meta)
    await db.commit()


@router.post("/documents/{document_id}/reprocess")
async def reprocess_document(
    org_id: uuid.UUID,
    chatbot_id: uuid.UUID,
    document_id: uuid.UUID,
    ctx: KnowledgeEdit,
    db: DbDep,
    svc: ServicesDep,
    meta: MetaDep,
) -> DocumentOut:
    job = await service.reprocess_document(db, ctx, chatbot_id, document_id, svc, meta=meta)
    document = await service.get_document(db, ctx, chatbot_id, document_id)
    await db.commit()
    svc.jobs.enqueue(org_id=ctx.org.id, job_id=job.id, kind=job.kind)
    return document_out(document, job, svc.embedder.model_id)


@router.post("/reindex")
async def reindex(
    org_id: uuid.UUID,
    chatbot_id: uuid.UUID,
    ctx: KnowledgeEdit,
    db: DbDep,
    svc: ServicesDep,
    meta: MetaDep,
    force: bool = False,
) -> ReindexResponse:
    jobs = await service.reindex_chatbot(db, ctx, chatbot_id, svc, force=force, meta=meta)
    await db.commit()
    for job in jobs:
        svc.jobs.enqueue(org_id=ctx.org.id, job_id=job.id, kind=job.kind)
    return ReindexResponse(queued=len(jobs), skipped=0, embedding_model=svc.embedder.model_id)


# --------------------------------------------------------------------------------- sources


@router.get("/sources")
async def list_sources(
    org_id: uuid.UUID, chatbot_id: uuid.UUID, ctx: KnowledgeRead, db: DbDep
) -> SourceList:
    sources = await service.list_sources(db, ctx, chatbot_id)
    jobs = await service.latest_jobs(db, ctx.org.id, source_ids=[s.id for s in sources])
    return SourceList(data=[source_out(s, jobs.get(s.id)) for s in sources])


@router.post("/sources", status_code=status.HTTP_201_CREATED)
async def create_source(
    org_id: uuid.UUID,
    chatbot_id: uuid.UUID,
    body: CreateWebsiteSourceRequest,
    ctx: KnowledgeWrite,
    db: DbDep,
    svc: ServicesDep,
    meta: MetaDep,
) -> SourceOut:
    await svc.limiter.check(str(ctx.org.id), Limit("crawl_create", 20, 3600))
    source, job = await service.create_website_source(db, ctx, chatbot_id, svc, body, meta=meta)
    await db.commit()
    svc.jobs.enqueue(org_id=ctx.org.id, job_id=job.id, kind=job.kind)
    return source_out(source, job)


@router.post("/sources/{source_id}/sync")
async def sync_source(
    org_id: uuid.UUID,
    chatbot_id: uuid.UUID,
    source_id: uuid.UUID,
    ctx: KnowledgeEdit,
    db: DbDep,
    svc: ServicesDep,
    meta: MetaDep,
) -> SourceOut:
    await svc.limiter.check(str(ctx.org.id), Limit("crawl_sync", 30, 3600))
    job = await service.sync_source(db, ctx, chatbot_id, source_id, svc, meta=meta)
    source = await service.get_source(db, ctx, chatbot_id, source_id)
    await db.commit()
    svc.jobs.enqueue(org_id=ctx.org.id, job_id=job.id, kind=job.kind)
    return source_out(source, job)


@router.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(
    org_id: uuid.UUID,
    chatbot_id: uuid.UUID,
    source_id: uuid.UUID,
    ctx: KnowledgeEdit,
    db: DbDep,
    meta: MetaDep,
) -> None:
    await service.delete_source(db, ctx, chatbot_id, source_id, meta=meta)
    await db.commit()


# ---------------------------------------------------------------------------------- search


@router.post("/retrieval/search")
async def search(
    org_id: uuid.UUID,
    chatbot_id: uuid.UUID,
    body: SearchRequest,
    ctx: ChatbotTest,
    db: DbDep,
    svc: ServicesDep,
) -> SearchResponse:
    """Retrieval debugger: what the chatbot would see for a question (no generation)."""
    await svc.limiter.check(
        str(ctx.user.id), Limit("retrieval_search", svc.settings.rate_limit_search_per_minute, 60)
    )
    results, took_ms = await service.search_chatbot(db, ctx, chatbot_id, svc, body)
    return SearchResponse(
        results=[
            SearchResultOut(
                chunk_id=r.chunk_id,
                document_id=r.document_id,
                source_id=r.source_id,
                document_title=r.document_title,
                uri=r.uri,
                ordinal=r.ordinal,
                content=r.content,
                heading_path=r.heading_path,
                page_start=r.page_start,
                page_end=r.page_end,
                score=round(r.score, 6),
                vector_score=round(r.vector_score, 6),
                vector_rank=r.vector_rank,
                keyword_rank=r.keyword_rank,
            )
            for r in results
        ],
        mode=body.mode,
        embedding_model=svc.embedder.model_id,
        took_ms=took_ms,
    )
