"""Embedding providers.

``embedding_model`` is the version tag stored on every chunk and document. Retrieval only compares
vectors of the *current* model, so switching models never mixes incompatible vector spaces; old
documents show as "needs reindex" until they are reprocessed.

* ``HashingEmbedder`` ("hash-v1"): deterministic, offline, free. It maps words (and word pairs)
  into a fixed-size vector with feature hashing, so similarity reflects **shared vocabulary only**:
  it has no notion of synonyms or meaning. It exists so the whole pipeline (and CI) runs without
  an API key; it is refused in production. Measured quality is in ``tests/rag_eval``.
* ``OpenAICompatibleEmbedder``: any ``/embeddings`` endpoint following the OpenAI contract.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import re
import time
from typing import TYPE_CHECKING, Protocol

import httpx2 as httpx

from app.core.provider_urls import provider_url
from app.models.knowledge import EMBEDDING_DIM
from app.rag.errors import IngestionError, TransientIngestionError

if TYPE_CHECKING:
    from app.core.config import Settings

_WORD = re.compile(r"\w+", re.UNICODE)
_STOPWORDS = frozenset(
    (
        "a an and are as at be but by do does for from had has have how i if in into is "
        "it its of on or our s so than that the their then there these they this to was "
        "we were what when where which who why will with you your can could should "
        "would may might"
    ).split()
)


class Embedder(Protocol):
    model_id: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


def _stem(word: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def tokenize(text: str) -> list[str]:
    words = [_stem(w) for w in _WORD.findall(text.lower())]
    return [w for w in words if w not in _STOPWORDS and len(w) > 1]


class HashingEmbedder:
    def __init__(self, model_id: str = "hash-v1", dimensions: int = EMBEDDING_DIM) -> None:
        self.model_id = model_id
        self.dimensions = dimensions

    def _bucket(self, feature: str) -> tuple[int, float]:
        digest = hashlib.blake2b(feature.encode(), digest_size=8).digest()
        value = int.from_bytes(digest, "big")
        return value % self.dimensions, 1.0 if (value >> 63) & 1 else -1.0

    def _embed(self, text: str) -> list[float]:
        tokens = tokenize(text)
        counts: dict[str, float] = {}
        for token in tokens:
            counts[token] = counts.get(token, 0.0) + 1.0
        for left, right in itertools.pairwise(tokens):
            key = f"{left}_{right}"
            counts[key] = counts.get(key, 0.0) + 0.5
        vector = [0.0] * self.dimensions
        for feature, count in counts.items():
            index, sign = self._bucket(feature)
            vector[index] += sign * (1.0 + math.log(count))
        norm = math.sqrt(sum(v * v for v in vector))
        if norm == 0.0:  # no usable words: a fixed unit vector keeps the DB column valid
            vector[0] = 1.0
            return vector
        return [v / norm for v in vector]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


class OpenAICompatibleEmbedder:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model_id: str,
        dimensions: int,
        batch_size: int,
        timeout: float,
        allow_insecure_local: bool = False,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._url = provider_url(base_url, allow_loopback_http=allow_insecure_local) + "/embeddings"
        self._key = api_key
        self._allow_insecure_local = allow_insecure_local
        self._transport = transport
        self.model_id = model_id
        self.dimensions = dimensions
        self._batch = batch_size
        self._timeout = timeout

    def _request(self, inputs: list[str]) -> list[list[float]]:
        body = json.dumps(
            {"model": self.model_id, "input": inputs, "dimensions": self.dimensions}
        ).encode()
        deadline = time.monotonic() + self._timeout
        try:
            with (
                httpx.Client(
                    timeout=httpx.Timeout(self._timeout, connect=min(self._timeout, 5)),
                    follow_redirects=False,
                    trust_env=False,
                    verify=True,
                    transport=self._transport,
                ) as client,
                client.stream(
                    "POST",
                    self._url,
                    content=body,
                    headers={
                        "Authorization": f"Bearer {self._key}",
                        "Content-Type": "application/json",
                    },
                ) as response,
            ):
                status = response.status_code
                if status == 429 or status >= 500:
                    raise TransientIngestionError("embedding_failed", f"HTTP {status}")
                if not 200 <= status < 300:
                    raise IngestionError("embedding_failed", "provider request rejected")
                data = bytearray()
                # Check every raw read, without buffering an arbitrary provider body or accepting
                # an endless slow drip. One blocked read is still bounded by the read timeout.
                for part in response.iter_bytes():
                    if time.monotonic() >= deadline:
                        raise TransientIngestionError("embedding_failed", "provider timeout")
                    if len(data) + len(part) > 32 * 1024 * 1024:
                        raise IngestionError("embedding_failed", "malformed response")
                    data.extend(part)
                payload = json.loads(data)
        except (httpx.HTTPError, TimeoutError, OSError, json.JSONDecodeError, UnicodeError):
            # No response bodies, URLs, keys or transport exception chains in application logs.
            raise TransientIngestionError("embedding_failed", "provider transport failed") from None
        try:
            items = payload["data"]
            # OpenAI returns an ``index`` per item; some compatible providers (Google Gemini)
            # omit it and return the vectors in input order, so only reorder when it is present.
            ordered = (
                sorted(items, key=lambda item: item["index"])
                if all(isinstance(item, dict) and "index" in item for item in items)
                else items
            )
            vectors = [[float(x) for x in item["embedding"]] for item in ordered]
        except (KeyError, TypeError, ValueError):
            raise IngestionError("embedding_failed", "malformed response") from None
        if len(vectors) != len(inputs) or any(len(v) != self.dimensions for v in vectors):
            raise IngestionError("embedding_failed", "unexpected embedding shape")
        return vectors

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch):
            vectors.extend(self._request(texts[start : start + self._batch]))
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self._request([text])[0]


def build_embedder(settings: Settings) -> Embedder:
    settings.validate_provider_transport()
    if settings.embedding_dimensions != EMBEDDING_DIM:
        msg = f"EMBEDDING_DIMENSIONS must be {EMBEDDING_DIM} (the database column width)"
        raise ValueError(msg)
    if settings.embedding_provider == "hash":
        return HashingEmbedder(settings.embedding_model, settings.embedding_dimensions)
    if settings.embedding_api_key is None or not settings.embedding_api_key.get_secret_value():
        msg = "EMBEDDING_API_KEY is required for the openai_compatible provider"
        raise ValueError(msg)
    return OpenAICompatibleEmbedder(
        base_url=settings.embedding_base_url,
        api_key=settings.embedding_api_key.get_secret_value(),
        model_id=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        batch_size=settings.embedding_batch_size,
        timeout=settings.embedding_timeout_seconds,
        allow_insecure_local=settings.allow_insecure_local_providers,
    )
