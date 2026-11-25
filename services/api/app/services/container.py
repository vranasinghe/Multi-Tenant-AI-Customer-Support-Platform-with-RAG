"""Process-wide collaborators built once at startup (see app.main lifespan)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.core.logging import get_logger
from app.services.chat_work import ChatWork

if TYPE_CHECKING:
    from fastapi import BackgroundTasks
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.core.config import Settings
    from app.core.rate_limit import LoginGuard, RateLimiter
    from app.core.security import PasswordService
    from app.integrations.email import EmailMessage, EmailSender
    from app.integrations.llm import ChatProvider
    from app.rag.embeddings import Embedder
    from app.rag.queue import JobQueue
    from app.rag.safe_fetch import SafeFetcher
    from app.rag.storage import ObjectStore

log = get_logger(__name__)


@dataclass(frozen=True)
class AppServices:
    settings: Settings
    session_factory: async_sessionmaker[AsyncSession]
    redis: Redis
    passwords: PasswordService
    limiter: RateLimiter
    login_guard: LoginGuard
    email_sender: EmailSender
    store: ObjectStore
    jobs: JobQueue
    embedder: Embedder
    fetcher: SafeFetcher
    chat_provider: ChatProvider
    chat_work: ChatWork


class MailQueue:
    """Schedules emails to go out after the response (and therefore after the commit).

    Delivery failures are logged without the recipient and never fail the request. Tokens are
    handed to the sender in-process only; they are not put on the Celery/Redis broker.
    """

    def __init__(self, sender: EmailSender, background: BackgroundTasks) -> None:
        self._sender = sender
        self._background = background

    def send(self, message: EmailMessage) -> None:
        self._background.add_task(self._deliver, message)

    async def _deliver(self, message: EmailMessage) -> None:
        try:
            await self._sender.send(message)
        except Exception:
            log.exception("email.send_failed", subject=message.subject)
