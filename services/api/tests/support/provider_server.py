"""Bounded loopback HTTP/TLS server with fictional content and no request logging."""

from __future__ import annotations

import contextlib
import ssl
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CERTS = Path(__file__).parent / "provider_tls"
Reply = tuple[int, dict[str, str], bytes]


@dataclass
class Server:
    url: str = ""
    requests: list[tuple[str, str | None, bytes]] = field(default_factory=list)


@contextmanager
def serve(reply: Callable[[], Reply], *, certificate: str | None = None) -> Iterator[Server]:
    state = Server()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body = self.rfile.read(min(int(self.headers.get("Content-Length", "0")), 2**20))
            state.requests.append((self.path, self.headers.get("Authorization"), body))
            status, headers, data = reply()
            with contextlib.suppress(BrokenPipeError, ConnectionResetError, ssl.SSLError):
                self.send_response(status)
                for key, value in headers.items():
                    self.send_header(key, value)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    if certificate:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(CERTS / (certificate + ".pem"), CERTS / "fixture-key.pem")
        server.socket = context.wrap_socket(server.socket, server_side=True)
    state.url = f"{'https' if certificate else 'http'}://127.0.0.1:{server.server_port}/v1"
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
    thread.start()
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()


def trusted_context() -> ssl.SSLContext:
    context = ssl.create_default_context(cafile=str(CERTS / "ca.pem"))
    assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
    return context
