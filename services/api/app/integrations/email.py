"""Email provider abstraction (docs/ARCHITECTURE.md §1: boring, replaceable vendors).

``SmtpEmailSender`` talks to Mailpit locally or any SMTP relay. ``LogEmailSender`` is a
development fallback that logs the whole message, including links carrying tokens, which is why
production refuses ``EMAIL_BACKEND=log``.
"""

from __future__ import annotations

import asyncio
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage as MimeMessage
from typing import TYPE_CHECKING, Protocol

from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.core.config import Settings

log = get_logger(__name__)


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    text: str


class EmailSender(Protocol):
    async def send(self, message: EmailMessage) -> None: ...


class LogEmailSender:
    """Development only: prints the whole message (including links with tokens)."""

    async def send(self, message: EmailMessage) -> None:
        log.info("email.dev_log", to=message.to, subject=message.subject, body=message.text)


class SmtpEmailSender:
    def __init__(self, settings: Settings) -> None:
        self._host = settings.smtp_host
        self._port = settings.smtp_port
        self._username = settings.smtp_username
        self._password = (
            settings.smtp_password.get_secret_value() if settings.smtp_password else None
        )
        self._starttls = settings.smtp_starttls
        self._from = settings.email_from

    async def send(self, message: EmailMessage) -> None:
        await asyncio.to_thread(self._send_sync, message)

    def _send_sync(self, message: EmailMessage) -> None:
        mime = MimeMessage()
        mime["From"] = self._from
        mime["To"] = message.to
        mime["Subject"] = message.subject
        mime.set_content(message.text)
        with smtplib.SMTP(self._host, self._port, timeout=10) as smtp:
            if self._starttls:
                smtp.starttls()
            if self._username and self._password:
                smtp.login(self._username, self._password)
            smtp.send_message(mime)


def build_email_sender(settings: Settings) -> EmailSender:
    if settings.email_backend == "smtp":
        return SmtpEmailSender(settings)
    return LogEmailSender()
