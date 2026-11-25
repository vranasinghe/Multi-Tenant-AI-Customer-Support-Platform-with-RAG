from __future__ import annotations

import json
import math
from collections.abc import Callable
from typing import Any

import httpx2 as httpx
import pytest

from app.core.config import Settings
from app.rag.embeddings import (
    HashingEmbedder,
    OpenAICompatibleEmbedder,
    build_embedder,
    tokenize,
)
from app.rag.errors import IngestionError, TransientIngestionError
from tests.conftest import make_settings


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def test_hash_embedder_is_deterministic_and_normalized() -> None:
    embedder = HashingEmbedder()

    first, second = (
        embedder.embed_query("Shipping times to Canada"),
        embedder.embed_query("Shipping times to Canada"),
    )

    assert first == second
    assert len(first) == 1536
    assert math.isclose(math.sqrt(sum(v * v for v in first)), 1.0, rel_tol=1e-9)


def test_similarity_reflects_shared_vocabulary_only() -> None:
    e = HashingEmbedder()
    query = e.embed_query("how long does shipping take")

    related = cosine(query, e.embed_documents(["Shipping takes 3 to 5 business days."])[0])
    unrelated = cosine(query, e.embed_documents(["Our office dog is called Biscuit."])[0])
    synonym_only = cosine(query, e.embed_documents(["Delivery requires several days."])[0])

    assert related > unrelated
    # Honest limitation: no semantic knowledge, so a pure synonym is barely closer than noise.
    assert synonym_only < related


def test_empty_text_still_yields_a_valid_unit_vector() -> None:
    vector = HashingEmbedder().embed_query("the and of")
    assert math.isclose(sum(v * v for v in vector), 1.0)


def test_tokenizer_drops_stopwords_and_light_stems() -> None:
    assert tokenize("The shipping of orders is delayed") == ["shipp", "order", "delay"]
    assert "the" not in tokenize("the cat")


def test_batch_embedding_matches_single_embedding() -> None:
    e = HashingEmbedder()
    texts = ["alpha beta", "gamma delta"]
    assert e.embed_documents(texts) == [e.embed_query(t) for t in texts]


# ------------------------------------------------------------------- OpenAI-compatible


def mock_client(
    monkeypatch: pytest.MonkeyPatch, handler: Callable[[httpx.Request], httpx.Response]
) -> None:
    client = httpx.Client
    monkeypatch.setattr(
        "app.rag.embeddings.httpx.Client",
        lambda **kwargs: client(**kwargs | {"transport": httpx.MockTransport(handler)}),
    )


def make_remote(batch: int = 2) -> OpenAICompatibleEmbedder:
    return OpenAICompatibleEmbedder(
        base_url="https://api.example.test/v1",
        api_key="k",
        model_id="m",
        dimensions=3,
        batch_size=batch,
        timeout=1,
    )


def test_remote_embedder_batches_requests_and_keeps_order(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        inputs = json.loads(request.content)["input"]
        calls.append(inputs)
        # return out of order to prove we sort by index
        data = [{"index": i, "embedding": [float(len(t)), 0.0, 1.0]} for i, t in enumerate(inputs)]
        return httpx.Response(200, json={"data": list(reversed(data))})

    mock_client(monkeypatch, handler)

    vectors = make_remote(batch=2).embed_documents(["a", "bb", "ccc", "dddd", "eeeee"])

    assert [len(c) for c in calls] == [2, 2, 1]
    assert [v[0] for v in vectors] == [1.0, 2.0, 3.0, 4.0, 5.0]


def test_remote_embedder_accepts_items_without_index_in_input_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Google Gemini's OpenAI-compatible endpoint returns vectors in input order, with no "index".
    def handler(request: httpx.Request) -> httpx.Response:
        inputs = json.loads(request.content)["input"]
        data = [{"object": "embedding", "embedding": [float(len(t)), 0.0, 1.0]} for t in inputs]
        return httpx.Response(200, json={"object": "list", "data": data})

    mock_client(monkeypatch, handler)

    vectors = make_remote(batch=2).embed_documents(["a", "bb", "ccc"])

    assert [v[0] for v in vectors] == [1.0, 2.0, 3.0]


@pytest.mark.parametrize("status", [429, 500, 503])
def test_remote_throttling_and_outages_are_transient(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    def boom(*_: object, **__: object) -> httpx.Response:
        return httpx.Response(status)

    mock_client(monkeypatch, boom)

    with pytest.raises(TransientIngestionError) as info:
        make_remote().embed_query("x")
    assert info.value.code == "embedding_failed"


def test_remote_client_errors_are_permanent(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_: object, **__: object) -> httpx.Response:
        return httpx.Response(401)

    mock_client(monkeypatch, boom)

    with pytest.raises(IngestionError) as info:
        make_remote().embed_query("x")
    assert not isinstance(info.value, TransientIngestionError)


def test_remote_network_failure_is_transient(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_: object, **__: object) -> httpx.Response:
        raise httpx.ConnectError("down")

    mock_client(monkeypatch, boom)

    with pytest.raises(TransientIngestionError):
        make_remote().embed_query("x")


def test_remote_rejects_wrong_dimensions(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_client(
        monkeypatch,
        lambda _: httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0, 2.0]}]}),
    )
    with pytest.raises(IngestionError, match="shape"):
        make_remote().embed_query("x")


def test_remote_rejects_malformed_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_client(monkeypatch, lambda _: httpx.Response(200, json={"oops": 1}))
    with pytest.raises(IngestionError, match="malformed"):
        make_remote().embed_query("x")


def test_remote_base_url_must_be_http() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        OpenAICompatibleEmbedder(
            base_url="file:///etc/passwd",
            api_key="k",
            model_id="m",
            dimensions=3,
            batch_size=1,
            timeout=1,
        )


# --------------------------------------------------------------------------- settings


def test_build_embedder_validates_dimensions_and_keys() -> None:
    assert isinstance(build_embedder(make_settings()), HashingEmbedder)
    with pytest.raises(ValueError, match="1536"):
        build_embedder(make_settings(embedding_dimensions=768))
    with pytest.raises(ValueError, match="EMBEDDING_API_KEY"):
        build_embedder(make_settings(embedding_provider="openai_compatible"))


def production(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "app_env": "production",
        "log_format": "json",
        "web_base_url": "https://app.example.com",
        "cors_allowed_origins": ["https://app.example.com"],
        "database_url": "postgresql+psycopg://app:s3cret@db.internal:5432/x",
        "migration_database_url": "postgresql+psycopg://owner:s3cret@db.internal:5432/x",
        "redis_url": "redis://redis.internal:6379/0",
        "email_backend": "smtp",
        "embedding_provider": "openai_compatible",
        "embedding_api_key": "k",
    }
    values.update(overrides)
    return make_settings(**values)


def test_production_refuses_the_local_embedding_baseline_and_memory_storage() -> None:
    production()  # a valid production config builds
    with pytest.raises(ValueError, match="EMBEDDING_PROVIDER"):
        production(embedding_provider="hash")
    with pytest.raises(ValueError, match="STORAGE_BACKEND"):
        production(storage_backend="memory")


def test_chunk_overlap_must_be_smaller_than_size() -> None:
    with pytest.raises(ValueError, match="CHUNK_OVERLAP"):
        make_settings(chunk_size_tokens=100, chunk_overlap_tokens=100)
