"""Audit regressions: expected safe behavior; failures are evidence, not fixes."""

import uuid

from app.rag.retrieval import RetrievedChunk
from app.services.chat_prompt import assemble, citations_for


def source(content: str) -> RetrievedChunk:
    return RetrievedChunk(
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
        "audit",
        "https://example.test",
        0,
        content,
        [],
        1,
        1,
        0.9,
        0.9,
    )


def test_citations_must_only_reference_sources_actually_rendered() -> None:
    first, second = source("&" * 2500), source("SECOND_SOURCE_FACT")
    prompt, selected = assemble("", [first, second], "Question?", [], budget=16000)
    actual_ids = {
        str(c.document_id)
        for i, c in enumerate(selected, 1)
        if f'<source id="{i}"' in prompt[-1]["content"]
    }
    cited = {c["document_id"] for c in citations_for("Answer [2]", selected)}
    assert cited <= actual_ids, (
        "Citation accepted for selected passage omitted by escaped context budget"
    )


def test_production_embedding_transport_must_require_https() -> None:
    import pytest
    from pydantic import ValidationError

    from tests.conftest import make_settings

    with pytest.raises(ValidationError):
        make_settings(
            app_env="production",
            log_format="json",
            email_backend="smtp",
            web_base_url="https://app.example.test",
            database_url="postgresql+psycopg://platform_app:fixture@db.internal/audit",
            redis_url="rediss://cache.internal/0",
            embedding_provider="openai_compatible",
            embedding_api_key="audit-fixture-key",
            embedding_base_url="http://provider.example.test/v1",
        )
