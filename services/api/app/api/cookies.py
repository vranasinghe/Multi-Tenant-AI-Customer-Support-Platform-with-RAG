"""Session cookie helpers (docs/SECURITY.md §3).

``__Host-`` prefix: browsers only accept the cookie if it is Secure, has Path=/ and **no Domain**,
so subdomains cannot overwrite or fixate it. HttpOnly keeps it from scripts; SameSite=Lax blocks
cross-site POSTs; the absolute lifetime matches the server-side expiry.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import Response

    from app.core.config import Settings

SESSION_COOKIE = "__Host-session"


def set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_absolute_days * 86400,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="lax")
