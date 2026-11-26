"""AUD-04: only operator-listed proxies may change the resolved client IP or scheme.

The middleware cases run the installed Uvicorn stack built from the same options the launcher
passes, and read the result through `RequestMeta`, as the rate limiters do. All addresses are
synthetic documentation ranges (RFC 5737 / RFC 3849). The real runtime image is covered by
tests/integration/test_runtime_proxy_trust.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from fastapi import Request
from pydantic import ValidationError
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app import server
from app.core.config import Settings
from app.core.request_meta import RequestMeta
from tests.conftest import make_settings

PROXY = "192.0.2.10"
DIRECT = "198.51.100.99"
CLIENT = "203.0.113.7"
EVERY_INTERFACE = "0.0.0.0"  # noqa: S104 -- the container bind address under test
API_ROOT = Path(__file__).resolve().parents[3]


def trusting(value: str) -> Settings:
    return make_settings(forwarded_allow_ips=value)


async def resolve(
    trusted: str, peer: str, headers: list[tuple[str, str]]
) -> tuple[str | None, str]:
    """(client IP, scheme) the application sees for one request from `peer`."""
    seen: dict[str, Any] = {}

    async def application(scope: Any, receive: Any, send: Any) -> None:
        seen["ip"] = RequestMeta.from_request(Request(scope)).ip
        seen["scheme"] = scope["scheme"]

    config = uvicorn.Config(
        application, interface="asgi3", **server.proxy_options(trusting(trusted))
    )
    config.load()
    scope = {
        "type": "http",
        "scheme": "http",
        "client": (peer, 40000),
        "headers": [(name.encode(), value.encode("latin1")) for name, value in headers],
    }
    await config.loaded_app(scope, None, None)
    return seen["ip"], seen["scheme"]


def forwarded(*chain: str, proto: str = "https") -> list[tuple[str, str]]:
    return [*[("x-forwarded-for", value) for value in chain], ("x-forwarded-proto", proto)]


# ------------------------------------------------------------------ configuration


def test_default_configuration_trusts_no_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FORWARDED_ALLOW_IPS", raising=False)

    assert make_settings().forwarded_allow_ips == []


@pytest.mark.parametrize("value", ["", "   "])
def test_blank_configuration_trusts_no_proxy(value: str) -> None:
    assert trusting(value).forwarded_allow_ips == []


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("192.0.2.10", ["192.0.2.10"]),
        ("192.0.2.10, 198.51.100.4", ["192.0.2.10", "198.51.100.4"]),
        ("127.0.0.1", ["127.0.0.1"]),
        ("2001:db8::10", ["2001:db8::10"]),
        ("2001:DB8:0:0:0:0:0:10", ["2001:db8::10"]),
        ("::1", ["::1"]),
        ("10.20.0.0/16", ["10.20.0.0/16"]),
        ("10.0.0.0/8", ["10.0.0.0/8"]),
        ("192.0.2.10/32", ["192.0.2.10/32"]),
        ("2001:db8:ffff::/48", ["2001:db8:ffff::/48"]),
        ("2a06:98c0::/29", ["2a06:98c0::/29"]),
        ("192.0.2.0/24,2001:db8::/32", ["192.0.2.0/24", "2001:db8::/32"]),
    ],
)
def test_valid_addresses_and_networks_are_accepted(value: str, expected: list[str]) -> None:
    assert trusting(value).forwarded_allow_ips == expected


def test_value_is_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "192.0.2.10,10.20.0.0/16")

    assert make_settings().forwarded_allow_ips == ["192.0.2.10", "10.20.0.0/16"]


@pytest.mark.parametrize("app_env", ["local", "test", "staging"])
@pytest.mark.parametrize(
    "value",
    [
        # wildcards
        "*",
        "192.0.2.10,*",
        "*.example.com",
        # unrestricted or near-unrestricted networks
        "0.0.0.0/0",
        "::/0",
        "0.0.0.0/1,128.0.0.0/1",
        "10.0.0.0/7",
        "2000::/3",
        "fc00::/7",
        EVERY_INTERFACE,
        "::",
        # malformed, ambiguous or unsupported spellings
        "localhost",
        "proxy.internal",
        "192.0.2",
        "192.0.2.256",
        "192.000.002.010",
        "3221225994",
        "192.0.2.10:8080",
        "[2001:db8::10]",
        "fe80::1%eth0",
        "::ffff:192.0.2.10",
        "::ffff:192.0.2.0/120",
        "192.0.2.10/24",
        "192.0.2.0/255.255.255.0",
        "192.0.2.0/0.0.0.255",
        "192.0.2.0/",
        "192.0.2.0/33",
        "192.0.2.0/+24",
        "192.0.2.0/024",
        "192.0.2.10,",
        ",192.0.2.10",
        "192.0.2.10,,198.51.100.4",
        "192.0.2.10;198.51.100.4",
        "192.0.2.10 198.51.100.4",
        "unix:",
    ],
)
def test_unsafe_or_malformed_configuration_is_rejected(app_env: str, value: str) -> None:
    with pytest.raises(ValidationError, match="FORWARDED_ALLOW_IPS"):
        make_settings(app_env=app_env, forwarded_allow_ips=value)


def test_wildcard_cannot_arrive_as_a_list() -> None:
    with pytest.raises(ValidationError, match="FORWARDED_ALLOW_IPS"):
        make_settings(forwarded_allow_ips=["*"])


def test_production_rejects_wildcard_without_echoing_the_value() -> None:
    with pytest.raises(ValidationError) as raised:
        make_settings(app_env="production", forwarded_allow_ips="operator-secret-typo")

    assert "forwarded_allow_ips" in str(raised.value)
    assert "operator-secret-typo" not in str(raised.value)


@pytest.mark.parametrize("name", ["UVICORN_FORWARDED_ALLOW_IPS", "UVICORN_PROXY_HEADERS"])
def test_uvicorn_variables_cannot_override_the_policy(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.setenv(name, "*")

    with pytest.raises(ValidationError, match=name):
        make_settings()


# ------------------------------------------------------------------ untrusted peers


@pytest.mark.parametrize("trusted", ["", PROXY, "192.0.2.0/24", "2001:db8:ffff::/48"])
@pytest.mark.parametrize(
    "headers",
    [
        forwarded(CLIENT),
        forwarded(f"{CLIENT}, {PROXY}"),
        forwarded(CLIENT, PROXY),
        forwarded("127.0.0.1"),
        forwarded("garbage, , ,"),
        [("forwarded", f"for={CLIENT};proto=https"), ("x-real-ip", CLIENT)],
    ],
    ids=["single", "chain", "duplicate", "loopback", "malformed", "other-headers"],
)
async def test_untrusted_direct_peer_cannot_change_identity_or_scheme(
    trusted: str, headers: list[tuple[str, str]]
) -> None:
    assert await resolve(trusted, DIRECT, headers) == (DIRECT, "http")


@pytest.mark.parametrize("peer", ["127.0.0.1", "::1", "10.0.0.1", "172.18.0.5"])
async def test_loopback_and_private_peers_are_not_trusted_by_default(peer: str) -> None:
    assert await resolve("", peer, forwarded(CLIENT)) == (peer, "http")


# ------------------------------------------------------------------ trusted proxies


@pytest.mark.parametrize(
    ("trusted", "peer", "client"),
    [
        (PROXY, PROXY, CLIENT),
        ("192.0.2.0/24", "192.0.2.200", CLIENT),
        ("2001:db8:ffff::10", "2001:db8:ffff::10", "2001:db8::7"),
        ("2001:db8:ffff::/48", "2001:db8:ffff:1::2", CLIENT),
        (PROXY, PROXY, "2001:db8::7"),
    ],
    ids=["ipv4", "ipv4-network", "ipv6", "ipv6-network", "ipv6-client"],
)
async def test_trusted_single_hop(trusted: str, peer: str, client: str) -> None:
    assert await resolve(trusted, peer, forwarded(client)) == (client, "https")


@pytest.mark.parametrize(
    ("chain", "expected"),
    [
        # edge appends the real client, inner trusted hops append the previous hop
        ([f"{CLIENT}, 192.0.2.20, 192.0.2.21"], CLIENT),
        # a client-supplied prefix sits to the left of the first untrusted address
        ([f"203.0.113.200, {CLIENT}, 192.0.2.20"], CLIENT),
        ([f"192.0.2.99, {CLIENT}"], CLIENT),
        # an untrusted address inside the chain ends the walk, whatever precedes it
        ([f"{CLIENT}, {DIRECT}, 192.0.2.20"], DIRECT),
        # repeated header lines are one chain, in order
        (["203.0.113.200", f"{CLIENT}, 192.0.2.20"], CLIENT),
        ([CLIENT, "192.0.2.20"], CLIENT),
        # every hop trusted: the originator is the leftmost entry
        (["192.0.2.30, 192.0.2.20"], "192.0.2.30"),
        # a port suffix is not part of the identity
        ([f"{CLIENT}:55555"], CLIENT),
        (["[2001:db8::7]:443"], "2001:db8::7"),
    ],
)
async def test_trusted_multi_hop_chains(chain: list[str], expected: str) -> None:
    ip, _ = await resolve("192.0.2.0/24", PROXY, forwarded(*chain))

    assert ip == expected


@pytest.mark.parametrize("chain", [[], [""], [","], ["   "], [", , "]])
async def test_empty_chain_keeps_the_real_peer(chain: list[str]) -> None:
    ip, _ = await resolve(PROXY, PROXY, forwarded(*chain))

    assert ip == PROXY


@pytest.mark.parametrize(
    "junk", ["garbage", "unknown", "999.1.1.1", "<script>", "203.0.113.7 spoof"]
)
async def test_junk_left_of_the_appended_client_is_ignored(junk: str) -> None:
    ip, _ = await resolve(PROXY, PROXY, forwarded(f"{junk}, {CLIENT}"))

    assert ip == CLIENT


async def test_unsanitised_junk_from_a_trusted_proxy_is_not_an_address() -> None:
    """Uvicorn does not validate entries; the ingress contract requires the proxy to append or
    replace. If it forwards junk anyway, no address is invented and no coarse prefix recorded."""
    ip, _ = await resolve(PROXY, PROXY, forwarded("garbage"))

    assert ip == "garbage"
    assert RequestMeta(ip, None, None, None).ip_prefix is None


@pytest.mark.parametrize(
    "proto", ["", "HTTPS", "Https", "javascript", "https, http", "http,https", "ftp", "https;x"]
)
async def test_forged_scheme_values_are_ignored(proto: str) -> None:
    assert (await resolve(PROXY, PROXY, forwarded(CLIENT, proto=proto)))[1] == "http"


async def test_last_scheme_header_from_the_proxy_wins() -> None:
    headers = [("x-forwarded-proto", "https"), ("x-forwarded-proto", "http")]

    assert (await resolve(PROXY, PROXY, headers))[1] == "http"


async def test_forged_variations_share_one_rate_limit_identity() -> None:
    attempts = [
        forwarded(f"198.51.100.{n}") if n % 2 else forwarded(f"junk-{n}", f"::{n}")
        for n in range(1, 30)
    ]

    direct = {(await resolve(PROXY, DIRECT, headers))[0] for headers in attempts}
    proxied = {
        (await resolve(PROXY, PROXY, forwarded(f"198.51.100.{n}, {CLIENT}")))[0]
        for n in range(1, 30)
    }

    assert direct == {DIRECT}
    assert proxied == {CLIENT}


# ------------------------------------------------------------------ launcher and image


@pytest.mark.parametrize(
    "value", ["", PROXY, "192.0.2.0/24, 2001:db8:ffff::/48"], ids=["none", "one", "networks"]
)
def test_launcher_gives_uvicorn_exactly_the_validated_policy(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: calls.append((app, kw)))
    monkeypatch.setattr(server, "get_settings", lambda: trusting(value))
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "*")  # must not be consulted behind Settings' back

    server.main(["--host", EVERY_INTERFACE, "--port", "8000"])

    ((app, kwargs),) = calls
    assert app == "app.main:create_app"
    assert kwargs["factory"] is True
    assert kwargs["access_log"] is False
    assert (kwargs["host"], kwargs["port"], kwargs["reload"]) == (EVERY_INTERFACE, 8000, False)

    async def application(scope: Any, receive: Any, send: Any) -> None: ...

    policy = {name: kwargs[name] for name in ("proxy_headers", "forwarded_allow_ips")}
    config = uvicorn.Config(application, interface="asgi3", **policy)
    config.load()
    expected = trusting(value).forwarded_allow_ips
    if not expected:
        assert not isinstance(config.loaded_app, ProxyHeadersMiddleware)
        return
    assert isinstance(config.loaded_app, ProxyHeadersMiddleware)
    trust = config.loaded_app.trusted_hosts
    assert not trust.always_trust
    assert not trust.trusted_literals
    effective = {str(item) for item in (*trust.trusted_hosts, *trust.trusted_networks)}
    assert effective == set(expected)


def test_launcher_defaults_to_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: calls.append(kw))
    monkeypatch.setattr(server, "get_settings", make_settings)

    server.main(["--reload"])

    assert (calls[0]["host"], calls[0]["port"], calls[0]["reload"]) == ("127.0.0.1", 8000, True)


@pytest.mark.parametrize(
    "argument",
    [["--forwarded-allow-ips", "*"], ["--forwarded-allow-ips=*"], ["--proxy-headers"]],
)
def test_launcher_rejects_proxy_arguments(
    monkeypatch: pytest.MonkeyPatch, argument: list[str]
) -> None:
    monkeypatch.setattr(uvicorn, "run", lambda *a, **kw: pytest.fail("server started"))
    monkeypatch.setattr(server, "get_settings", make_settings)

    with pytest.raises(SystemExit) as raised:
        server.main(argument)

    assert raised.value.code == 2


@pytest.mark.parametrize(
    ("stage", "extra"), [("dev", ["--reload"]), ("runtime", [])], ids=["dev", "runtime"]
)
def test_image_stages_start_through_the_launcher(stage: str, extra: list[str]) -> None:
    dockerfile = (API_ROOT / "Dockerfile").read_text(encoding="utf-8")
    section = dockerfile.split(f" AS {stage}\n", 1)[1].split("\nFROM ", 1)[0]
    command = next(line for line in section.splitlines() if line.startswith("CMD ["))

    assert json.loads(command.removeprefix("CMD ")) == [
        "python", "-m", "app.server", "--host", EVERY_INTERFACE, "--port", "8000", *extra
    ]  # fmt: skip
    assert 'FORWARDED_ALLOW_IPS=""' in dockerfile.split(" AS dev\n", 1)[0]
    assert "--forwarded-allow-ips" not in dockerfile
