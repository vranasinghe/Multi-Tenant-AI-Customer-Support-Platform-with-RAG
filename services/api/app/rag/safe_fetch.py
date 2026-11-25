"""SSRF-safe HTTP fetching for website ingestion (docs/SECURITY.md §7).

The crawler fetches attacker-influenced URLs from inside our network, so every request goes
through this module and these rules:

1. Only ``http``/``https``, no credentials in the URL, only allow-listed ports (80/443 by default).
2. The hostname is resolved **once per hop**; *every* returned address must be public. A name that
   resolves to even one loopback/private/link-local/CGNAT/multicast/reserved address (including
   cloud metadata ``169.254.169.254`` and IPv6 forms, IPv4-mapped and NAT64/6to4/Teredo
   encodings) is refused.
3. The socket then connects to that **validated IP** (TLS still verifies the hostname via SNI), so
   a DNS answer that changes between the check and the connection (DNS rebinding) cannot redirect
   the request.
4. Redirects are followed manually, at most N, and each hop repeats 1-3. A redirect to a private
   address, a different scheme downgrade, or an out-of-scope host is refused.
5. Hard limits: connect/read timeout, a total deadline, a maximum body size (read in chunks, never
   trusting ``Content-Length``), ``Accept-Encoding: identity`` (no compression bombs).

The resolver and IP policy are injectable for tests only; production code never overrides them.
"""

from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import SplitResult, urljoin, urlsplit

from app.rag.errors import IngestionError, TransientIngestionError

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_INTERNAL_SUFFIXES = (".localhost", ".local", ".internal", ".intranet", ".lan", ".home.arpa")
_CHUNK = 64 * 1024

Resolver = Callable[[str, int], list[str]]
IpPolicy = Callable[[str], bool]


class BlockedDestinationError(IngestionError):
    def __init__(self, detail: str) -> None:
        super().__init__("blocked_destination", detail)


class FetchStatusError(IngestionError):
    """The server answered with a non-success status."""

    def __init__(self, status: int, url: str) -> None:
        super().__init__("fetch_failed", f"HTTP {status}")
        self.status = status
        self.url = url


def is_public_ip(address: str) -> bool:
    """True only for globally routable unicast addresses."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address):
        # Re-check any IPv4 address embedded in an IPv6 one (::ffff:a.b.c.d, 6to4, Teredo, NAT64).
        embedded: list[ipaddress.IPv4Address] = []
        if ip.ipv4_mapped:
            embedded.append(ip.ipv4_mapped)
        if ip.sixtofour:
            embedded.append(ip.sixtofour)
        if ip.teredo:
            embedded.extend(ip.teredo)
        if ip in ipaddress.ip_network("64:ff9b::/96"):
            embedded.append(ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF))
        if any(not is_public_ip(str(v4)) for v4 in embedded):
            return False
        if ip in ipaddress.ip_network("64:ff9b:1::/48") or ip in ipaddress.ip_network("::/96"):
            return False
    return ip.is_global and not ip.is_multicast


def system_resolver(host: str, port: int) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        if exc.errno == socket.EAI_AGAIN:  # temporary resolver failure: worth retrying
            raise TransientIngestionError("fetch_failed", "DNS lookup failed") from exc
        raise IngestionError("fetch_failed", "host does not exist") from exc
    return sorted({str(info[4][0]) for info in infos})


@dataclass(frozen=True)
class Destination:
    url: str
    host: str
    port: int
    ip: str
    secure: bool
    parts: SplitResult


@dataclass
class FetchResult:
    url: str  # final URL after redirects
    status: int
    content_type: str
    body: bytes
    etag: str | None = None
    redirects: int = 0
    headers: dict[str, str] = field(default_factory=dict)


def parse_url(url: str, allowed_ports: list[int]) -> tuple[SplitResult, str, int]:
    """Syntactic checks that need no DNS. Returns (parts, ascii host, port)."""
    if len(url) > 2048 or any(c in url for c in "\r\n\t\x00 "):
        raise BlockedDestinationError("malformed URL")
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"}:
        raise BlockedDestinationError("scheme must be http or https")
    if parts.username is not None or parts.password is not None:
        raise BlockedDestinationError("credentials in URL")
    host = parts.hostname
    if not host:
        raise BlockedDestinationError("missing host")
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError as exc:
        raise BlockedDestinationError("invalid port") from exc
    if port not in allowed_ports:
        raise BlockedDestinationError(f"port {port} is not allowed")
    try:
        ascii_host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise BlockedDestinationError("invalid host name") from exc
    lowered = ascii_host.lower().rstrip(".")
    if (
        lowered == "localhost"
        or lowered.endswith(_INTERNAL_SUFFIXES)
        or ("." not in lowered and not _is_ip(lowered))
    ):
        raise BlockedDestinationError("internal host name")
    return parts, lowered, port


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return True


def resolve_destination(
    url: str,
    allowed_ports: list[int],
    *,
    resolver: Resolver = system_resolver,
    ip_policy: IpPolicy = is_public_ip,
) -> Destination:
    """Validate ``url`` and pin it to one verified public IP."""
    parts, host, port = parse_url(url, allowed_ports)
    addresses = resolver(host, port)
    if not addresses:
        raise TransientIngestionError("fetch_failed", "host did not resolve")
    rejected = [a for a in addresses if not ip_policy(a)]
    if rejected:
        # Any non-public answer poisons the whole name: attackers mix public and private records.
        raise BlockedDestinationError("host resolves to a non-public address")
    ipv4_first = sorted(addresses, key=lambda a: (":" in a, a))
    return Destination(
        url=url, host=host, port=port, ip=ipv4_first[0], secure=parts.scheme == "https", parts=parts
    )


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, dest: Destination, timeout: float) -> None:
        super().__init__(dest.host, dest.port, timeout=timeout)
        self._pinned_ip = dest.ip

    def connect(self) -> None:
        self.sock = socket.create_connection((self._pinned_ip, self.port), self.timeout)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, dest: Destination, timeout: float) -> None:
        super().__init__(
            dest.host, dest.port, timeout=timeout, context=ssl.create_default_context()
        )
        self._pinned_ip = dest.ip

    def connect(self) -> None:
        raw = socket.create_connection((self._pinned_ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(raw, server_hostname=self.host)  # type: ignore[attr-defined]


class SafeFetcher:
    def __init__(
        self,
        *,
        user_agent: str,
        timeout: float = 10.0,
        total_timeout: float = 20.0,
        max_bytes: int = 5 * 1024 * 1024,
        max_redirects: int = 5,
        allowed_ports: list[int] | None = None,
        resolver: Resolver = system_resolver,
        ip_policy: IpPolicy = is_public_ip,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.user_agent = user_agent
        self.timeout = timeout
        self.total_timeout = total_timeout
        self.max_bytes = max_bytes
        self.max_redirects = max_redirects
        self.allowed_ports = allowed_ports or [80, 443]
        self._resolver = resolver
        self._ip_policy = ip_policy
        self._clock = clock

    def check(self, url: str) -> Destination:
        """Validate a URL without fetching it (used when a source is created)."""
        return resolve_destination(
            url, self.allowed_ports, resolver=self._resolver, ip_policy=self._ip_policy
        )

    def fetch(
        self,
        url: str,
        *,
        accept: str = "text/html,application/xhtml+xml;q=0.9,text/plain;q=0.5",
        host_ok: Callable[[str], bool] | None = None,
        max_bytes: int | None = None,
        if_none_match: str | None = None,
    ) -> FetchResult:
        """GET ``url``. ``host_ok`` (if given) must approve every host in the redirect chain."""
        deadline = self._clock() + self.total_timeout
        limit = max_bytes or self.max_bytes
        current = url
        scheme_was_https = url.lower().startswith("https://")
        for hop in range(self.max_redirects + 1):
            dest = resolve_destination(
                current, self.allowed_ports, resolver=self._resolver, ip_policy=self._ip_policy
            )
            if host_ok is not None and not host_ok(dest.host):
                raise BlockedDestinationError("redirect leaves the allowed site")
            if scheme_was_https and not dest.secure:
                raise BlockedDestinationError("redirect downgrades https to http")
            scheme_was_https = dest.secure
            response, body = self._request(dest, accept, limit, deadline, if_none_match)
            status = response.status
            if status in _REDIRECT_STATUSES:
                location = response.getheader("Location")
                if not location:
                    raise FetchStatusError(status, current)
                current = urljoin(current, location)
                continue
            if status == 304:
                return FetchResult(
                    current, 304, "", b"", etag=response.getheader("ETag"), redirects=hop
                )
            if not 200 <= status < 300:
                if status == 429 or status >= 500:
                    raise TransientIngestionError("fetch_failed", f"HTTP {status}")
                raise FetchStatusError(status, current)
            return FetchResult(
                url=current,
                status=status,
                content_type=(response.getheader("Content-Type") or "")
                .split(";", 1)[0]
                .strip()
                .lower(),
                body=body,
                etag=response.getheader("ETag"),
                redirects=hop,
                headers={k.lower(): v for k, v in response.getheaders()},
            )
        raise BlockedDestinationError("too many redirects")

    def _request(
        self,
        dest: Destination,
        accept: str,
        limit: int,
        deadline: float,
        if_none_match: str | None,
    ) -> tuple[http.client.HTTPResponse, bytes]:
        remaining = deadline - self._clock()
        if remaining <= 0:
            raise TransientIngestionError("fetch_failed", "deadline exceeded")
        timeout = min(self.timeout, remaining)
        conn: http.client.HTTPConnection = (
            _PinnedHTTPSConnection(dest, timeout)
            if dest.secure
            else _PinnedHTTPConnection(dest, timeout)
        )
        path = dest.parts.path or "/"
        if dest.parts.query:
            path = f"{path}?{dest.parts.query}"
        headers = {
            "User-Agent": self.user_agent,
            "Accept": accept,
            "Accept-Encoding": "identity",
            "Connection": "close",
        }
        if if_none_match:
            headers["If-None-Match"] = if_none_match
        try:
            conn.request("GET", path, headers=headers)
            response = conn.getresponse()
            if response.status in _REDIRECT_STATUSES or response.status == 304:
                return response, b""
            declared = response.getheader("Content-Length")
            if declared and declared.isdigit() and int(declared) > limit:
                raise IngestionError("too_large", "response is larger than allowed")
            chunks: list[bytes] = []
            total = 0
            while True:
                if self._clock() > deadline:
                    raise TransientIngestionError("fetch_failed", "deadline exceeded")
                chunk = response.read(_CHUNK)
                if not chunk:
                    break
                total += len(chunk)
                if total > limit:
                    raise IngestionError("too_large", "response is larger than allowed")
                chunks.append(chunk)
            return response, b"".join(chunks)
        except TimeoutError as exc:
            raise TransientIngestionError("fetch_failed", "timeout") from exc
        except (OSError, http.client.HTTPException, ssl.SSLError) as exc:
            raise TransientIngestionError("fetch_failed", type(exc).__name__) from exc
        finally:
            conn.close()
