"""Bound chat JSON before parsing it, including clients that omit Content-Length."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.errors import problem_response

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Message, Receive, Scope, Send


class ChatBodyLimit:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] not in {"POST", "PUT"}
            or not ("/conversations/" in scope["path"] or scope["path"].startswith("/public/v1/"))
        ):
            await self.app(scope, receive, send)
            return
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > 24_000:
                response = problem_response(
                    status=413, code="body_too_large", title="Chat request is too large"
                )
                await response(scope, receive, send)
                return
            if not message.get("more_body", False):
                break
        delivered = False

        async def replay() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)
