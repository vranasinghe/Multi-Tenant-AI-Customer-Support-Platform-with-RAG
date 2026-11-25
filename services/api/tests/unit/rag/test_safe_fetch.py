"""SSRF defenses: IP policy, URL rules, DNS pinning/rebinding, redirects, limits."""

from __future__ import annotations

import pytest

from app.rag.errors import IngestionError, TransientIngestionError
from app.rag.safe_fetch import (
    BlockedDestinationError,
    is_public_ip,
    parse_url,
    resolve_destination,
)
from tests.support.site import serve

# --------------------------------------------------------------------------- IP policy


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "127.1.2.3",
        "10.0.0.5",
        "172.16.0.1",
        "172.31.255.255",
        "192.168.1.1",
        "169.254.169.254",  # cloud metadata (AWS/GCP/Azure)
        "169.254.170.2",  # ECS task metadata
        "100.64.0.1",  # carrier-grade NAT
        "0.0.0.0",  # noqa: S104
        "192.0.0.1",
        "198.18.0.1",
        "224.0.0.1",  # multicast
        "240.0.0.1",
        "255.255.255.255",
        "::1",
        "::",
        "fe80::1",  # link-local
        "fc00::1",  # unique local
        "fd00:ec2::254",  # AWS IPv6 metadata
        "::ffff:127.0.0.1",  # IPv4-mapped loopback
        "::ffff:10.0.0.1",
        "::ffff:169.254.169.254",
        "64:ff9b::7f00:1",  # NAT64 of 127.0.0.1
        "2002:7f00:1::",  # 6to4 of 127.0.0.1
        "ff02::1",
        "not-an-ip",
        "",
    ],
)
def test_non_public_addresses_are_rejected(address: str) -> None:
    assert is_public_ip(address) is False


@pytest.mark.parametrize("address", ["93.184.216.34", "8.8.8.8", "1.1.1.1", "2606:4700:4700::1111"])
def test_public_addresses_are_allowed(address: str) -> None:
    assert is_public_ip(address) is True


# ------------------------------------------------------------------------------- URLs


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/",
        "file:///etc/passwd",
        "gopher://example.com/",
        "javascript:alert(1)",
        "http://user:pass@example.com/",
        "http://localhost/",
        "http://LOCALHOST./",
        "http://foo.localhost/",
        "http://printer.local/",
        "http://metadata.internal/",
        "http://intranet/",  # single-label host
        "http://example.com:22/",
        "http://example.com:8080/",
        "http://example.com:99999/",
        "http:///nohost",
        "http://exa mple.com/",
        "http://example.com/\r\nHost: evil",
        "https://" + "a" * 3000 + ".com/",
    ],
)
def test_unsafe_urls_are_rejected_before_any_dns_lookup(url: str) -> None:
    with pytest.raises(BlockedDestinationError):
        parse_url(url, [80, 443])


def test_ip_literals_get_the_same_scrutiny() -> None:
    for url in ("http://127.0.0.1/", "http://[::1]/", "http://169.254.169.254/latest/meta-data/"):
        with pytest.raises(BlockedDestinationError):
            resolve_destination(url, [80], resolver=lambda h, _p: [h.strip("[]")])


# ------------------------------------------------------------- DNS answers and rebinding


def test_hostname_resolving_to_a_private_address_is_blocked() -> None:
    with pytest.raises(BlockedDestinationError):
        resolve_destination("http://evil.example/", [80], resolver=lambda *_: ["10.1.2.3"])


def test_mixed_public_and_private_answers_are_blocked() -> None:
    with pytest.raises(BlockedDestinationError):
        resolve_destination(
            "http://evil.example/", [80], resolver=lambda *_: ["93.184.216.34", "169.254.169.254"]
        )


def test_public_answer_is_pinned_and_ipv4_preferred() -> None:
    dest = resolve_destination(
        "https://ok.example/p?q=1",
        [443],
        resolver=lambda *_: ["2606:4700:4700::1111", "93.184.216.34"],
    )
    assert dest.ip == "93.184.216.34"
    assert dest.secure is True


def test_dns_rebinding_cannot_change_the_connected_address() -> None:
    """The resolver answers 'public' once, then 'private'. The fetch must use the first,
    validated answer and never ask again for the same hop."""
    answers = [["93.184.216.34"], ["127.0.0.1"], ["127.0.0.1"]]
    asked: list[str] = []

    def rebinding_resolver(host: str, _port: int) -> list[str]:
        asked.append(host)
        return answers[min(len(asked) - 1, len(answers) - 1)]

    dest = resolve_destination("http://rebind.example/", [80], resolver=rebinding_resolver)

    assert dest.ip == "93.184.216.34"
    assert asked == ["rebind.example"]  # exactly one lookup per hop


def test_dns_failures_are_classified() -> None:
    def nxdomain(*_: object) -> list[str]:
        return []

    with pytest.raises(TransientIngestionError):
        resolve_destination("http://nothing.example/", [80], resolver=nxdomain)


# --------------------------------------------------------------- real fetches (local server)


def test_fetch_follows_safe_redirects_and_returns_the_final_url() -> None:
    with serve() as site:
        site.redirect("/old", "/new")
        site.page("/new", "New", "<p>Welcome to the new page.</p>")

        result = site.fetcher().fetch(f"{site.base}/old")

        assert result.url == f"{site.base}/new"
        assert result.redirects == 1
        assert b"Welcome to the new page" in result.body


def test_redirect_to_a_private_address_is_refused() -> None:
    with serve() as site:
        site.redirect("/go", "http://169.254.169.254/latest/meta-data/")
        fetcher = site.fetcher(
            resolver=lambda host, _p: ["127.0.0.1"] if host.endswith(".test") else [host],
        )

        with pytest.raises(BlockedDestinationError):
            fetcher.fetch(f"{site.base}/go")
        assert site.requests == ["/go"]  # the metadata address was never contacted


def test_redirect_to_localhost_name_is_refused() -> None:
    with serve() as site:
        site.redirect("/go", "http://localhost:80/admin")
        with pytest.raises(BlockedDestinationError):
            site.fetcher().fetch(f"{site.base}/go")


def test_redirect_loops_are_cut_off() -> None:
    with serve() as site:
        site.redirect("/a", "/b")
        site.redirect("/b", "/a")
        with pytest.raises(BlockedDestinationError, match="redirect"):
            site.fetcher(max_redirects=4).fetch(f"{site.base}/a")


def test_redirect_leaving_the_allowed_host_is_refused() -> None:
    with serve() as site:
        site.redirect("/out", f"http://other.test:{site.port}/x")
        site.page("/x", "X", "<p>other site</p>")
        with pytest.raises(BlockedDestinationError, match="allowed site"):
            site.fetcher().fetch(f"{site.base}/out", host_ok=lambda h: h == "site.test")


def test_redirect_to_a_non_http_scheme_is_refused() -> None:
    with serve() as site:
        site.redirect("/ftp", "ftp://site.test/secret")
        site.redirect("/file", "file:///etc/passwd")
        for path in ("/ftp", "/file"):
            with pytest.raises(BlockedDestinationError, match="scheme"):
                site.fetcher().fetch(f"{site.base}{path}")


def test_oversized_bodies_are_aborted_by_declared_and_actual_size() -> None:
    with serve() as site:
        site.routes["/big"] = (200, {"Content-Type": "text/html"}, b"x" * 5000)
        with pytest.raises(IngestionError) as declared:
            site.fetcher(max_bytes=1000).fetch(f"{site.base}/big")
        assert declared.value.code == "too_large"

        # Server lies about (omits) Content-Length: the streaming cap still applies.
        import socket
        import threading

        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]

        def lie() -> None:
            conn, _ = listener.accept()
            conn.recv(4096)
            conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n")
            try:
                for _ in range(200):
                    conn.sendall(b"y" * 1000)
            except OSError:
                pass
            conn.close()

        threading.Thread(target=lie, daemon=True).start()
        with pytest.raises(IngestionError) as streamed:
            site.fetcher(max_bytes=10_000, allowed_ports=[port]).fetch(f"http://site.test:{port}/")
        listener.close()
        assert streamed.value.code == "too_large"


def test_slow_servers_hit_the_deadline() -> None:
    with serve() as site:
        site.page("/slow", "Slow", "<p>eventually</p>")
        site.delay = 1.5
        with pytest.raises(TransientIngestionError):
            site.fetcher(timeout=0.3, total_timeout=0.5).fetch(f"{site.base}/slow")


def test_server_errors_are_transient_and_client_errors_permanent() -> None:
    with serve() as site:
        site.routes["/boom"] = (503, {}, b"")
        site.routes["/limited"] = (429, {}, b"")
        with pytest.raises(TransientIngestionError):
            site.fetcher().fetch(f"{site.base}/boom")
        with pytest.raises(TransientIngestionError):
            site.fetcher().fetch(f"{site.base}/limited")
        with pytest.raises(IngestionError) as missing:
            site.fetcher().fetch(f"{site.base}/missing")
        assert not isinstance(missing.value, TransientIngestionError)
