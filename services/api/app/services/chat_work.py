"""Process-local bounded preparation; cancellable query embedding without orphan threads."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import anyio

from app.core.errors import ApiError
from app.rag.embeddings import HashingEmbedder, OpenAICompatibleEmbedder

if TYPE_CHECKING:
    from app.core.config import Settings
    from app.rag.embeddings import Embedder


class AuthSlot:
    def __init__(self, semaphore: asyncio.Semaphore) -> None:
        self.semaphore = semaphore
        self.released = False

    def release(self) -> None:
        if not self.released:
            self.released = True
            self.semaphore.release()


class ChatWork:
    def __init__(self, settings: Settings) -> None:
        # Preparation limits do not reserve database slots; fairness is measured separately.
        total = settings.db_pool_size + settings.db_max_overflow
        self.capacity = min(settings.chat_setup_capacity, max(1, total - 2))
        self.active = 0
        self.peak = 0
        self.children: set[int] = set()
        self.auth_capacity = max(1, min(4, total - 2))
        self.auth_slots = asyncio.Semaphore(self.auth_capacity)

    @asynccontextmanager
    async def authentication(self) -> AsyncIterator[AuthSlot]:
        try:
            async with asyncio.timeout(2):
                await self.auth_slots.acquire()
        except TimeoutError:
            raise ApiError(
                503,
                "chat_unavailable",
                "Authentication capacity is busy",
                headers={"Retry-After": "1"},
            ) from None
        slot = AuthSlot(self.auth_slots)
        try:
            yield slot
        finally:
            slot.release()

    @asynccontextmanager
    async def setup(self) -> AsyncIterator[None]:
        if self.active >= self.capacity:
            raise ApiError(
                503, "chat_unavailable", "Chat setup is busy", headers={"Retry-After": "1"}
            )
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            yield
        finally:
            self.active -= 1

    async def query(
        self, embedder: Embedder, question: str, deadline_seconds: float
    ) -> list[float]:
        if type(embedder) is HashingEmbedder:
            # Bounded <=8k input; the pure local hash has no I/O or background work to abandon.
            return embedder.embed_query(question)
        if not isinstance(embedder, OpenAICompatibleEmbedder):
            raise ApiError(503, "retrieval_unavailable", "Unsupported query embedder")
        # Reuse the secured synchronous adapter in a killable fresh interpreter. No pickle,
        # inherited DB clients, proxy/trust environment or secrets in argv.
        payload = json.dumps(
            {
                "base_url": embedder._url.removesuffix("/embeddings"),
                "api_key": embedder._key,
                "model_id": embedder.model_id,
                "dimensions": embedder.dimensions,
                "batch_size": 1,
                "timeout": deadline_seconds,
                "allow_insecure_local": embedder._allow_insecure_local,
                "question": question,
            }
        ).encode()
        environment = {
            k: v
            for k, v in os.environ.items()
            if k in {"PATH", "SYSTEMROOT", "WINDIR", "PYTHONPATH"}
        }
        spawn = asyncio.create_task(
            asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "app.services.query_process",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                env=environment,
            )
        )
        try:
            proc = await asyncio.shield(spawn)
        except asyncio.CancelledError:
            # Cancellation during process creation must not orphan the eventual child.
            with anyio.CancelScope(shield=True):
                proc = await spawn
                if proc.returncode is None:
                    proc.kill()
                await proc.wait()
            raise
        self.children.add(proc.pid)
        try:
            async with asyncio.timeout(deadline_seconds):
                output, _ = await proc.communicate(payload)
                if proc.returncode or len(output) > 128_000:
                    raise ValueError("query failed")
                vector: list[float] = json.loads(output)
                return vector
        finally:
            with anyio.CancelScope(shield=True):
                if proc.returncode is None:
                    proc.kill()
                await proc.wait()
                self.children.discard(proc.pid)
