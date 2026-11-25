"""In-memory email sender for tests: captures messages so tests can follow emailed links."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.integrations.email import EmailMessage

_TOKEN_RE = re.compile(r"[?&]token=([A-Za-z0-9_-]+)")


@dataclass
class Mailbox:
    messages: list[EmailMessage] = field(default_factory=list)

    async def send(self, message: EmailMessage) -> None:
        self.messages.append(message)

    def to(self, address: str) -> list[EmailMessage]:
        return [m for m in self.messages if m.to.lower() == address.lower()]

    def tokens(self, address: str, *, path: str) -> list[str]:
        """Tokens from links like ``/<path>?token=...`` in mails to ``address``, oldest first."""
        found: list[str] = []
        for message in self.to(address):
            for line in message.text.splitlines():
                if f"/{path}?" in line and (match := _TOKEN_RE.search(line)):
                    found.append(match.group(1))
        return found

    def last_token(self, address: str, *, path: str) -> str:
        tokens = self.tokens(address, path=path)
        assert tokens, f"no /{path} link emailed to {address}: {[m.subject for m in self.messages]}"
        return tokens[-1]
