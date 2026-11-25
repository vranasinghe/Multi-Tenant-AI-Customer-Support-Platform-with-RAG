"""Cancellable OpenAI-compatible SSE transport. Never log request/response bodies or keys."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Protocol

import httpx2 as httpx

from app.core.config import Settings


class ProviderError(Exception):
    """Sanitized provider failure, safe to map to a public error code."""


@dataclass(frozen=True)
class CompletionEvent:
    text: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    attempts: int = 1


class ChatProvider(Protocol):
    def stream(
        self, messages: list[dict[str, str]], *, model: str, max_tokens: int, temperature: float
    ) -> AsyncGenerator[CompletionEvent]: ...


class CompatibleProvider:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        settings.validate_provider_transport()
        self.settings = settings
        self.transport = transport

    async def stream(  # noqa: PLR0912
        self, messages: list[dict[str, str]], *, model: str, max_tokens: int, temperature: float
    ) -> AsyncGenerator[CompletionEvent]:
        settings = self.settings
        try:
            settings.validate_provider_transport()
        except ValueError:
            raise ProviderError("provider_unavailable") from None
        if not settings.llm_api_key:
            raise ProviderError("provider_unavailable")
        # No redirects: credentials must never be forwarded to a different provider host.
        async with httpx.AsyncClient(
            timeout=settings.llm_timeout_seconds,
            follow_redirects=False,
            transport=self.transport,
            trust_env=False,
            verify=True,
        ) as client:
            for attempt in range(settings.llm_retries + 1):
                emitted = False
                try:
                    async with client.stream(
                        "POST",
                        settings.llm_base_url.rstrip("/") + "/chat/completions",
                        headers={
                            "Authorization": "Bearer " + settings.llm_api_key.get_secret_value()
                        },
                        json={
                            "model": model,
                            "messages": messages,
                            "stream": True,
                            "stream_options": {"include_usage": True},
                            "max_tokens": max_tokens,
                            "temperature": temperature,
                        },
                    ) as response:
                        if (
                            response.status_code in {429, 502, 503, 504}
                            and attempt < settings.llm_retries
                        ):
                            await asyncio.sleep(min(0.25 * 2**attempt, 2))
                            continue
                        if response.status_code != 200:
                            raise ProviderError("provider_unavailable")
                        usage: tuple[int, int] | None = None
                        async for line in response.aiter_lines():
                            if len(line) > 128_000:
                                raise ProviderError("invalid_provider_response")
                            if not line.startswith("data:"):
                                continue
                            data = line[5:].strip()
                            if data == "[DONE]":
                                yield CompletionEvent(
                                    input_tokens=usage[0] if usage else None,
                                    output_tokens=usage[1] if usage else None,
                                    attempts=attempt + 1,
                                )
                                return
                            payload = json.loads(data)
                            if "error" in payload:
                                raise ProviderError("provider_unavailable")
                            if payload.get("usage"):
                                raw = payload["usage"]
                                a, b = raw["prompt_tokens"], raw["completion_tokens"]
                                if type(a) is not int or type(b) is not int or min(a, b) < 0:
                                    raise ProviderError("invalid_provider_response")
                                usage = a, b
                            choices = payload.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {}).get("content")
                                if delta:
                                    if not isinstance(delta, str):
                                        raise ProviderError("invalid_provider_response")
                                    emitted = True
                                    yield CompletionEvent(text=delta, attempts=attempt + 1)
                        raise ProviderError("incomplete_provider_stream")
                except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError) as exc:
                    if (
                        not emitted
                        and isinstance(exc, httpx.ConnectError)
                        and attempt < settings.llm_retries
                    ):
                        await asyncio.sleep(min(0.25 * 2**attempt, 2))
                        continue
                    raise ProviderError("provider_unavailable") from None


class DemoProvider:
    """Explicit offline demonstration fixture; not an AI model."""

    async def stream(
        self, messages: list[dict[str, str]], *, model: str, max_tokens: int, temperature: float
    ) -> AsyncGenerator[CompletionEvent]:
        answer = "Demo response: this confirms the streaming pipeline works. Check source [1]."
        for word in answer.split(" "):
            await asyncio.sleep(0.02)
            yield CompletionEvent(text=word + " ")


class DisabledProvider:
    async def stream(
        self, messages: list[dict[str, str]], *, model: str, max_tokens: int, temperature: float
    ) -> AsyncGenerator[CompletionEvent]:
        raise ProviderError("provider_not_configured")
        yield CompletionEvent()  # type: ignore[unreachable]  # pragma: no cover


def build_chat_provider(settings: Settings) -> ChatProvider:
    if settings.llm_provider == "demo":
        return DemoProvider()
    if settings.llm_provider == "openai_compatible":
        return CompatibleProvider(settings)
    return DisabledProvider()
