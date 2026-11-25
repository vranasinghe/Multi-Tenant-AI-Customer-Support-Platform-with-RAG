"""Request/response models for knowledge sources, documents and retrieval."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, Field, StringConstraints

from app.schemas.auth import OutModel, StrictModel

_PATTERN_OK = re.compile(r"^/[A-Za-z0-9._~!$&'()*+,;=:@%/?\-\[\]]*$")


def _pattern(value: str) -> str:
    if not _PATTERN_OK.match(value):
        msg = "Must start with / and contain only URL path characters and * ? wildcards"
        raise ValueError(msg)
    return value


UrlPattern = Annotated[str, StringConstraints(max_length=200), AfterValidator(_pattern)]
SourceName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
SearchText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class CreateWebsiteSourceRequest(StrictModel):
    url: Annotated[str, StringConstraints(strip_whitespace=True, min_length=8, max_length=2048)]
    name: SourceName | None = None
    max_pages: Annotated[int, Field(ge=1, le=1000)] = 50
    max_depth: Annotated[int, Field(ge=0, le=10)] = 2
    include: Annotated[list[UrlPattern], Field(max_length=20)] = Field(default_factory=list)
    exclude: Annotated[list[UrlPattern], Field(max_length=20)] = Field(default_factory=list)
    # The user must affirm they are allowed to crawl and index this site.
    confirm_authorized: Literal[True]


class SearchRequest(StrictModel):
    query: SearchText
    top_k: Annotated[int, Field(ge=1, le=12)] | None = None
    mode: Literal["vector", "keyword", "hybrid"] = "hybrid"
    min_score: Annotated[float, Field(ge=0, le=1)] | None = None


class JobOut(OutModel):
    id: uuid.UUID
    kind: str
    status: str
    stage: str | None
    attempt: int
    max_attempts: int
    error_code: str | None
    stats: dict[str, Any]
    queued_at: datetime
    finished_at: datetime | None


class DocumentOut(OutModel):
    id: uuid.UUID
    source_id: uuid.UUID
    title: str
    uri: str
    mime_type: str | None
    size_bytes: int
    status: str
    error_code: str | None
    error_message: str | None
    page_count: int | None
    chunk_count: int
    token_count: int | None
    version: int
    embedding_model: str | None
    needs_reindex: bool
    job: JobOut | None
    created_at: datetime
    updated_at: datetime


class DocumentList(OutModel):
    data: list[DocumentOut]
    embedding_model: str


class SourceOut(OutModel):
    id: uuid.UUID
    kind: str
    name: str
    status: str
    config: dict[str, Any]
    stats: dict[str, Any]
    last_synced_at: datetime | None
    created_at: datetime
    job: JobOut | None


class SourceList(OutModel):
    data: list[SourceOut]


class ChunkOut(OutModel):
    id: uuid.UUID
    ordinal: int
    content: str
    heading_path: list[str]
    page_start: int | None
    page_end: int | None
    token_count: int


class ChunkList(OutModel):
    data: list[ChunkOut]
    total: int


class SearchResultOut(OutModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    source_id: uuid.UUID
    document_title: str
    uri: str
    ordinal: int
    content: str
    heading_path: list[str]
    page_start: int | None
    page_end: int | None
    score: float
    vector_score: float
    vector_rank: int | None
    keyword_rank: int | None


class SearchResponse(OutModel):
    results: list[SearchResultOut]
    mode: str
    embedding_model: str
    took_ms: int


class ReindexResponse(OutModel):
    queued: int
    skipped: int
    embedding_model: str


class UploadLimits(OutModel):
    max_bytes: int
    extensions: list[str]
    max_documents: int
    max_pages_per_crawl: int
