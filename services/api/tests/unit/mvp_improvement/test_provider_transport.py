"""A3 deterministic endpoint policy, real loopback TLS, redirects, proxies and safe failures."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
import traceback
from collections.abc import AsyncIterator
from typing import Any

import httpx2 as httpx
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.provider_urls import provider_url
from app.integrations.llm import CompatibleProvider, ProviderError
from app.rag.embeddings import OpenAICompatibleEmbedder
from app.rag.errors import IngestionError, TransientIngestionError
from app.services.chat_work import ChatWork
from tests.conftest import make_settings
from tests.support.provider_server import serve, trusted_context

SECRET = "A3_FICTIONAL_SECRET_DO_NOT_LOG"
CONTENT = "A3_FICTIONAL_DOCUMENT_DO_NOT_LOG"
VECTOR = [1.0] + [0.0] * 1535
JSON_VECTOR = json.dumps({"data": [{"index": 0, "embedding": VECTOR}]}).encode()


def remote(
    url: str = "https://provider.example.test/v1", **kwargs: Any
) -> OpenAICompatibleEmbedder:
    return OpenAICompatibleEmbedder(
        base_url=url,
        api_key=SECRET,
        model_id="fixture-v1",
        dimensions=1536,
        batch_size=2,
        timeout=kwargs.pop("timeout", 1),
        **kwargs,
    )


def configured(provider: str, url: str, **kwargs: Any) -> Settings:
    return make_settings(
        **{
            provider + "_provider": "openai_compatible",
            provider + "_base_url": url,
            provider + "_api_key": SECRET,
        },
        **kwargs,
    )


@pytest.mark.parametrize("environment", ["production", "staging"])
@pytest.mark.parametrize("provider", ["embedding", "llm"])
def test_deployed_http_is_rejected(environment: str, provider: str) -> None:
    with pytest.raises(ValidationError, match="HTTPS"):
        configured(provider, "http://provider.example.test/v1", app_env=environment)
    with pytest.raises(ValidationError, match="forbidden"):
        configured(
            provider,
            "https://provider.example.test/v1",
            app_env=environment,
            allow_insecure_local_providers=True,
        )


@pytest.mark.parametrize(
    "url",
    [
        "https://api.example.test/v1",
        "https://provider:8443/base/v1/",
        "https://127.0.0.1:443/v1",
        "https://[::1]:8443/v1",
        "https://xn--bcher-kva.example/v1",
    ],
)
@pytest.mark.parametrize("environment", ["local", "test", "staging", "production"])
def test_valid_https_urls(url: str, environment: str) -> None:
    settings = make_settings(
        embedding_provider="openai_compatible",
        embedding_api_key=SECRET,
        embedding_base_url=url,
        llm_provider="openai_compatible",
        llm_api_key=SECRET,
        llm_base_url=url,
        app_env=environment,
        email_backend="smtp",
        web_base_url="https://app.example.test",
        log_format="json",
    )
    assert settings.embedding_base_url == settings.llm_base_url == provider_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://user:SECRET@provider.test/v1",
        "https://:SECRET@provider.test/v1",
        "https://@provider.test/v1",
        "https://user%40provider.test/v1",
        "https://provider.test/v1?key=SECRET",
        "https://provider.test/v1?",
        "https://provider.test/v1#SECRET",
        "https://provider.test/v1#",
        "https://provider.test\\@evil.test/v1",
        " https://provider.test/v1",
        "https://provider.test/\nSECRET",
        "https://provider.test/\t",
        "https://provider.test/\x00",
        "https://provider.test/%0a",
        "https://provider.test/%3fkey=SECRET",
        "https://provider.test/a/../b",
        "https://provider.test//v1",
        "https:///provider.test",
        "https://provider.test:",
        "https://provider.test:0",
        "https://provider.test:65536",
        "https://provider.test:abc",
        "https://provider.test:0443",
        "https://provider.test:443:80",
        "https://[::1]extra/v1",
        "https://::1/v1",
        "https://[::1%25eth0]/v1",
        "https://127.1/v1",
        "https://2130706433/v1",
        "https://0x7f000001/v1",
        "https://0x7f.0.0.1/v1",
        "https://0177.0.0.1/v1",
        "https://provider.test./v1",
        "https://-host.test/v1",
        "https://a..test/v1",
        "https://a_b.test/v1",
        "https://bücher.test/v1",
        "ftp://provider.test/v1",
        "file:///tmp/provider",
        "https://provider.test/\u202e",
        "https://provider.test/\x7f",
    ],
)
@pytest.mark.parametrize("provider", ["embedding", "llm"])
def test_unsafe_url_components_fail_without_echoing_input(url: str, provider: str) -> None:
    with pytest.raises(ValidationError) as info:
        configured(provider, url)
    assert url not in str(info.value) and SECRET not in str(info.value)
    assert provider.upper() + "_BASE_URL" in str(info.value)


@pytest.mark.parametrize("environment", ["local", "test"])
@pytest.mark.parametrize(
    "url", ["http://localhost:8001/v1", "http://127.0.0.1:8001/v1", "http://[::1]:8001/v1"]
)
def test_loopback_http_requires_explicit_development_opt_in(environment: str, url: str) -> None:
    for provider in ["embedding", "llm"]:
        with pytest.raises(ValidationError, match="HTTPS"):
            configured(provider, url, app_env=environment)
        assert configured(provider, url, app_env=environment, allow_insecure_local_providers=True)


@pytest.mark.parametrize(
    "host",
    [
        "0.0.0.0",  # noqa: S104 -- rejection input, never a listening address
        "10.0.0.1",
        "192.168.0.1",
        "provider",
        "host.docker.internal",
        "localhost.evil.test",
        "127.0.0.1.evil.test",
        "[::ffff:127.0.0.1]",
        "[fe80::1]",
    ],
)
def test_local_opt_in_never_grants_lan_container_or_public_http(host: str) -> None:
    with pytest.raises(ValidationError):
        configured("embedding", f"http://{host}/v1", allow_insecure_local_providers=True)
    with pytest.raises(ValueError, match="HTTPS"):
        remote(f"http://{host}/v1", allow_insecure_local=True)


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
@pytest.mark.parametrize(
    "location", ["https://foreign.example.test/v1", "http://provider.example.test/v1", "/same-host"]
)
@pytest.mark.asyncio
async def test_both_adapters_reject_all_redirects(status: int, location: str) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status, headers={"Location": location}, text=SECRET + CONTENT)

    with pytest.raises(IngestionError) as info:
        remote(transport=httpx.MockTransport(handler)).embed_query(CONTENT)
    assert not info.value.retryable and info.value.code == "embedding_failed"
    assert SECRET not in str(info.value) and CONTENT not in str(info.value)
    assert len(calls) == 1
    calls.clear()
    provider = CompatibleProvider(
        configured("llm", "https://provider.example.test/v1"), httpx.MockTransport(handler)
    )
    with pytest.raises(ProviderError, match="provider_unavailable"):
        _ = [
            event
            async for event in provider.stream(
                [{"role": "user", "content": CONTENT}],
                model="fixture",
                max_tokens=30,
                temperature=0,
            )
        ]
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("certificate", "trust", "success"),
    [
        ("valid", True, True),
        ("valid", False, False),
        ("expired", True, False),
        ("wrong", True, False),
    ],
)
def test_real_embedding_tls_trust_hostname_and_expiry(
    certificate: str, trust: bool, success: bool
) -> None:
    with serve(lambda: (200, {}, JSON_VECTOR), certificate=certificate) as server:
        transport = (
            httpx.HTTPTransport(verify=trusted_context(), trust_env=False) if trust else None
        )
        embedder = remote(server.url, transport=transport)
        if success:
            assert embedder.embed_query(CONTENT) == VECTOR
            assert server.requests[0][1] == "Bearer " + SECRET
        else:
            with pytest.raises(TransientIngestionError, match="provider transport failed"):
                embedder.embed_query(CONTENT)
            assert server.requests == []  # TLS failure happened before credentials or text


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_real_tls_redirect_downgrade_never_contacts_destination(status: int) -> None:
    with (
        serve(lambda: (200, {}, JSON_VECTOR)) as destination,
        serve(
            lambda: (status, {"Location": destination.url + "/stolen"}, b""), certificate="valid"
        ) as source,
    ):
        with pytest.raises(IngestionError):
            remote(
                source.url, transport=httpx.HTTPTransport(verify=trusted_context(), trust_env=False)
            ).embed_query(CONTENT)
        assert len(source.requests) == 1 and destination.requests == []


@pytest.mark.asyncio
async def test_real_llm_tls_verification_is_preserved() -> None:
    for trust in [False, True]:
        with serve(lambda: (200, {}, b"data: [DONE]\n\n"), certificate="valid") as server:
            transport = (
                httpx.AsyncHTTPTransport(verify=trusted_context(), trust_env=False)
                if trust
                else None
            )
            settings = configured("llm", server.url, llm_retries=0)
            provider = CompatibleProvider(settings, transport)
            if trust:
                assert (
                    len(
                        [
                            part
                            async for part in provider.stream(
                                [], model="fixture", max_tokens=30, temperature=0
                            )
                        ]
                    )
                    == 1
                )
            else:
                with pytest.raises(ProviderError):
                    _ = [
                        part
                        async for part in provider.stream(
                            [], model="fixture", max_tokens=30, temperature=0
                        )
                    ]
                assert not server.requests


@pytest.mark.asyncio
async def test_proxy_and_certificate_environment_is_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with (
        serve(lambda: (500, {}, b"proxy trap")) as proxy,
        serve(lambda: (200, {}, JSON_VECTOR)) as server,
    ):
        for key in [
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
        ]:
            monkeypatch.setenv(key, proxy.url)
        monkeypatch.setenv("NO_PROXY", "")
        monkeypatch.setenv("no_proxy", "")
        monkeypatch.setenv("SSL_CERT_FILE", "/nonexistent/a3-cert")
        monkeypatch.setenv("SSL_CERT_DIR", "/nonexistent/a3-dir")
        assert remote(server.url, allow_insecure_local=True).embed_query(CONTENT) == VECTOR
        with serve(lambda: (200, {}, b"data: [DONE]\n\n")) as chat:
            settings = configured("llm", chat.url, allow_insecure_local_providers=True)
            provider = CompatibleProvider(settings)
            assert (
                len(
                    [
                        part
                        async for part in provider.stream(
                            [], model="fixture", max_tokens=30, temperature=0
                        )
                    ]
                )
                == 1
            )
        assert proxy.requests == []


@pytest.mark.parametrize("kind", ["connect", "read", "tls"])
def test_transport_errors_do_not_log_secrets_or_documents(
    kind: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)

    def handler(request: httpx.Request) -> httpx.Response:
        error = {
            "connect": httpx.ConnectTimeout,
            "read": httpx.ReadTimeout,
            "tls": httpx.ConnectError,
        }[kind]
        raise error(SECRET + CONTENT, request=request)

    with pytest.raises(TransientIngestionError) as info:
        remote(transport=httpx.MockTransport(handler)).embed_query(CONTENT)
    rendered = "".join(traceback.format_exception(info.value)) + caplog.text
    assert SECRET not in rendered and CONTENT not in rendered
    assert info.value.code == "embedding_failed" and info.value.retryable


def test_real_embedding_read_timeout_is_bounded() -> None:
    release = threading.Event()

    def reply() -> tuple[int, dict[str, str], bytes]:
        release.wait(0.3)
        return 200, {}, JSON_VECTOR

    with serve(reply) as server:
        started = time.monotonic()
        try:
            with pytest.raises(TransientIngestionError):
                remote(server.url, allow_insecure_local=True, timeout=0.05).embed_query(CONTENT)
            assert time.monotonic() - started < 1
        finally:
            release.set()


def test_batch_payload_dimensions_model_identity_and_ordering() -> None:
    batches: list[list[str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["model"] == "fixture-v1" and payload["dimensions"] == 1536
        assert str(request.url) == "https://provider.example.test/v1/embeddings"
        batches.append(payload["input"])
        data = [
            {"index": i, "embedding": [float(len(s))] + [0.0] * 1535}
            for i, s in enumerate(payload["input"])
        ]
        return httpx.Response(200, json={"data": list(reversed(data))})

    embedder = remote(transport=httpx.MockTransport(handler))
    vectors = embedder.embed_documents(["a", "bb", "ccc", "dddd", "eeeee"])
    assert [len(batch) for batch in batches] == [2, 2, 1]
    assert [v[0] for v in vectors] == [1, 2, 3, 4, 5]
    assert all(len(v) == 1536 for v in vectors) and embedder.model_id == "fixture-v1"
    bad = remote(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0]}]})
        )
    )
    with pytest.raises(IngestionError, match="shape"):
        bad.embed_query(CONTENT)


@pytest.mark.parametrize("status", [201, 202])
def test_embedding_preserves_compatible_success_statuses(status: int) -> None:
    embedder = remote(
        transport=httpx.MockTransport(lambda _: httpx.Response(status, content=JSON_VECTOR))
    )
    assert embedder.embed_query(CONTENT) == VECTOR


def test_slow_drip_deadline_closes_response(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = [0.0]
    closed = []

    class Drip(httpx.SyncByteStream):
        def __iter__(self) -> Any:
            yield b'{"data":'
            clock[0] = 2.0
            yield b"[]}"

        def close(self) -> None:
            closed.append(True)

    monkeypatch.setattr("app.rag.embeddings.time.monotonic", lambda: clock[0])
    embedder = remote(transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=Drip())))
    with pytest.raises(TransientIngestionError, match="provider timeout"):
        embedder.embed_query(CONTENT)
    assert closed


@pytest.mark.parametrize(
    "entrypoint",
    [
        "from app.main import create_app; create_app()",
        "from app.workers.celery_app import celery_app",
    ],
)
def test_api_and_worker_startup_reject_unsafe_configuration_without_secret_output(
    entrypoint: str,
) -> None:
    environment = {
        k: v for k, v in os.environ.items() if k in {"PATH", "SYSTEMROOT", "WINDIR", "PYTHONPATH"}
    }
    environment.update(
        APP_ENV="staging",
        DATABASE_URL="postgresql+psycopg://fixture:fixture@localhost/db",
        REDIS_URL="redis://localhost/0",
        EMBEDDING_PROVIDER="openai_compatible",
        EMBEDDING_API_KEY=SECRET,
        EMBEDDING_BASE_URL="http://user:" + SECRET + "@provider.test/v1",
        LLM_PROVIDER="disabled",
    )
    result = subprocess.run(  # noqa: S603 -- two fixed Python snippets above, no external input
        [sys.executable, "-c", entrypoint],
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode != 0
    assert "EMBEDDING_BASE_URL" in result.stderr and SECRET not in result.stdout + result.stderr


@pytest.mark.asyncio
async def test_query_child_does_not_inherit_proxy_or_certificate_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with (
        serve(lambda: (500, {}, b"trap")) as proxy,
        serve(lambda: (200, {}, JSON_VECTOR)) as server,
    ):
        for key in ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]:
            monkeypatch.setenv(key, proxy.url)
        work = ChatWork(make_settings())
        assert await work.query(remote(server.url, allow_insecure_local=True), CONTENT, 3) == VECTOR
        assert proxy.requests == [] and not work.children and work.active == 0
    # A parent SSL_CERT_FILE must not turn a private synthetic CA into implicit child trust.
    from tests.support.provider_server import CERTS

    monkeypatch.setenv("SSL_CERT_FILE", str(CERTS / "ca.pem"))
    with serve(lambda: (200, {}, JSON_VECTOR), certificate="valid") as tls:
        with pytest.raises(ValueError, match="query failed"):
            await work.query(remote(tls.url), CONTENT, 3)
        assert not tls.requests and not work.children


@pytest.mark.asyncio
async def test_llm_errors_are_sanitized_and_partial_output_is_never_retried(
    caplog: pytest.LogCaptureFixture,
) -> None:
    calls = 0

    class BrokenStream(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield b'data: {"choices":[{"delta":{"content":"safe"}}]}\n\n'
            raise httpx.ReadError(SECRET + CONTENT)

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, stream=BrokenStream())

    provider = CompatibleProvider(
        configured("llm", "https://provider.test/v1"), httpx.MockTransport(handler)
    )
    events = []

    async def consume() -> None:
        async for part in provider.stream(
            [{"role": "user", "content": CONTENT}], model="fixture", max_tokens=30, temperature=0
        ):
            events.append(part.text)

    with pytest.raises(ProviderError) as info:
        await consume()
    assert events == ["safe"] and calls == 1
    assert (
        SECRET not in str(info.value) + caplog.text and CONTENT not in str(info.value) + caplog.text
    )
