"""A throwaway local web server plus a fetcher wired to it, for crawler tests.

Production code blocks loopback addresses on purpose. Tests reach this server by injecting a
resolver (``site.test`` → 127.0.0.1) and an IP policy that allows *only* 127.0.0.1; neither
override exists in production configuration.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app.rag.safe_fetch import SafeFetcher

Response = tuple[int, dict[str, str], bytes]
Handler = Callable[[str], Response]


def html_page(title: str, body: str, *, links: list[str] | None = None, head: str = "") -> bytes:
    nav = "<nav><a href='/'>Home</a> <a href='/about'>About</a></nav>"
    anchors = "".join(f"<a href='{href}'>link</a> " for href in links or [])
    return (
        f"<!doctype html><html><head><title>{title}</title>{head}</head><body>{nav}"
        f"<main><h1>{title}</h1>{body}<p>{anchors}</p></main>"
        "<footer>Copyright footer boilerplate text</footer></body></html>"
    ).encode()


@dataclass
class Site:
    port: int
    routes: dict[str, Response | Handler] = field(default_factory=dict)
    requests: list[str] = field(default_factory=list)
    delay: float = 0.0

    @property
    def base(self) -> str:
        return f"http://site.test:{self.port}"

    def page(self, path: str, title: str, body: str, *, links: list[str] | None = None) -> None:
        self.routes[path] = (
            200,
            {"Content-Type": "text/html; charset=utf-8"},
            html_page(title, body, links=links),
        )

    def text(self, path: str, body: str, content_type: str = "text/plain") -> None:
        self.routes[path] = (200, {"Content-Type": content_type}, body.encode())

    def redirect(self, path: str, to: str, status: int = 302) -> None:
        self.routes[path] = (status, {"Location": to}, b"")

    def fetcher(self, **overrides: object) -> SafeFetcher:
        kwargs: dict[str, object] = {
            "user_agent": "ACSBot/1.0 (test)",
            "timeout": 3.0,
            "total_timeout": 6.0,
            "max_bytes": 200_000,
            "allowed_ports": [self.port],
            "resolver": lambda host, _port: (
                ["127.0.0.1"] if host.endswith(".test") else ["203.0.113.9"]
            ),
            "ip_policy": lambda ip: ip == "127.0.0.1",
        }
        kwargs.update(overrides)
        return SafeFetcher(**kwargs)  # type: ignore[arg-type]


@contextmanager
def serve() -> Iterator[Site]:
    site = Site(port=0)

    class H(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            site.requests.append(self.path)
            if site.delay:
                time.sleep(site.delay)
            route = site.routes.get(self.path.split("#")[0])
            if route is None:
                status, headers, body = 404, {"Content-Type": "text/plain"}, b"not found"
            elif callable(route):
                status, headers, body = route(self.path)
            else:
                status, headers, body = route
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args: object) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), H)
    site.port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield site
    finally:
        server.shutdown()
        server.server_close()
