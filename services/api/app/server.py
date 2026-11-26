"""API process launcher: `python -m app.server`.

Proxy trust comes only from validated settings and is passed to Uvicorn explicitly, so neither
Uvicorn's own environment handling (which trusts loopback by default) nor a command-line flag
can widen it. With no trusted proxy configured the proxy-header middleware is not installed.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from typing import Any

import uvicorn

from app.core.config import Settings, get_settings


def proxy_options(settings: Settings) -> dict[str, Any]:
    trusted = list(settings.forwarded_allow_ips)
    return {"proxy_headers": bool(trusted), "forwarded_allow_ips": trusted}


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.server", allow_abbrev=False)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="development only")
    args = parser.parse_args(argv)
    uvicorn.run(
        "app.main:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
        access_log=False,  # requests are logged by the application, without full IPs
        **proxy_options(get_settings()),
    )


if __name__ == "__main__":
    main()
