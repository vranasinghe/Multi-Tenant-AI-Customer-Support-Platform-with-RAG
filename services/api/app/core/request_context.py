"""Request id propagation, access logging and last-resort error handling (pure ASGI middleware).

- Accepts a well-formed incoming `X-Request-ID` (8-128 chars of [A-Za-z0-9._-]) or mints one.
- Binds it to structlog context so every log line in the request carries it.
- Echoes it on the response and exposes it on `request.state.request_id`.
- Logs one access line per request with status and duration.
- Converts unhandled exceptions into an RFC 9457 problem response that includes the request id.
"""

from __future__ import annotations

import re
import time
import uuid
from typing import TYPE_CHECKING

import structlog
from sqlalchemy.exc import TimeoutError as PoolTimeout
from starlette.datastructures import Headers, MutableHeaders

from app.core.errors import problem_response
from app.core.logging import get_logger

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "x-request-id"
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{8,128}$")
QUIET_PATHS = frozenset({"/healthz", "/readyz"})

log = get_logger("app.access")


def resolve_request_id(incoming: str | None) -> str:
    if incoming and REQUEST_ID_PATTERN.fullmatch(incoming):
        return incoming
    return str(uuid.uuid4())


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = resolve_request_id(Headers(scope=scope).get(REQUEST_ID_HEADER))
        scope.setdefault("state", {})["request_id"] = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        status_code = 500
        response_started = False
        started = time.perf_counter()

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except PoolTimeout:
            if response_started:
                raise
            status_code = 503
            response = problem_response(
                status=503,
                code="chat_unavailable",
                title="Database capacity is busy",
                request_id=request_id,
                headers={"Retry-After": "1"},
            )
            await response(scope, receive, send_with_request_id)
        except Exception:
            log.exception("request.unhandled_exception")
            if response_started:
                raise
            status_code = 500
            response = problem_response(
                status=500,
                code="internal_error",
                title="Internal Server Error",
                detail="An unexpected error occurred.",
                request_id=request_id,
            )
            await response(scope, receive, send_with_request_id)
        finally:
            path = scope.get("path", "")
            log_method = log.debug if path in QUIET_PATHS and status_code < 400 else log.info
            log_method(
                "request.completed",
                method=scope.get("method"),
                path=path,
                status=status_code,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            structlog.contextvars.clear_contextvars()
