"""CSRF defence for the cookie-authenticated dashboard API (docs/SECURITY.md §3, ARCH §7.1).

Layered on SameSite=Lax cookies: every state-changing request must carry the custom header
``X-Requested-With: platform`` (a header cross-site forms cannot set, and cross-origin scripts can
only send after a CORS preflight that the origin allowlist rejects), and any ``Origin`` header
must be on the allowlist. No state-changing GET endpoints exist.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.datastructures import Headers

from app.core.errors import problem_response
from app.core.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Collection

    from starlette.types import ASGIApp, Receive, Scope, Send

CSRF_HEADER = "x-requested-with"
CSRF_VALUE = "platform"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

log = get_logger(__name__)


class CsrfMiddleware:
    def __init__(
        self, app: ASGIApp, *, allowed_origins: Collection[str], protected_prefix: str = "/api/"
    ) -> None:
        self.app = app
        self._allowed = frozenset(allowed_origins)
        self._prefix = protected_prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] in SAFE_METHODS
            or not scope["path"].startswith(self._prefix)
        ):
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        origin = headers.get("origin")
        failure: tuple[str, str] | None = None
        if origin is not None and origin not in self._allowed:
            failure = ("origin_not_allowed", "Cross-origin request not allowed")
        elif headers.get(CSRF_HEADER) != CSRF_VALUE:
            failure = ("csrf_check_failed", "Missing or invalid CSRF header")

        if failure is None:
            await self.app(scope, receive, send)
            return

        code, title = failure
        log.warning("security.csrf_rejected", code=code, path=scope["path"])
        response = problem_response(
            status=403,
            code=code,
            title=title,
            request_id=scope.get("state", {}).get("request_id"),
        )
        await response(scope, receive, send)
