"""AUD-04: forwarding-header trust as observed through the real runtime image over HTTP.

The container runs its own entrypoint (the image CMD), so this covers the launch configuration,
not a stand-alone helper. Opt-in because it drives the Docker CLI from the host:

    docker build --target runtime -t acs-api:aud04 services/api
    # with a migrated Postgres and a Redis on a Docker network:
    RUNTIME_PROXY_IMAGE=acs-api:aud04 RUNTIME_PROXY_STACK_NETWORK=<network>
    RUNTIME_PROXY_REDIS_CONTAINER=<container> RUNTIME_PROXY_DATABASE_URL=<url>
    pytest tests/integration/test_runtime_proxy_trust.py

Peers get fixed addresses on a throwaway network: one is configured as the trusted proxy, one is
a direct, untrusted caller. All identities are synthetic documentation addresses (RFC 5737/3849).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from collections.abc import Iterator
from typing import Any

import pytest

IMAGE = os.environ.get("RUNTIME_PROXY_IMAGE", "")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not IMAGE, reason="set RUNTIME_PROXY_IMAGE (drives Docker from the host)"),
]

SUBNET = "172.30.254.0/24"
API_IP, PROXY_IP, DIRECT_IP = "172.30.254.2", "172.30.254.10", "172.30.254.20"
NETWORK = "aud04-proxy-net"
API_NAME = "aud04-proxy-api"
REDIS_DB = "14"

# Runs inside a peer container. Takes a JSON list of requests, prints a JSON list of responses.
CLIENT = """
import http.client, json, sys
out = []
for item in json.loads(sys.argv[1]):
    conn = http.client.HTTPConnection(sys.argv[2], 8000, timeout=20)
    body = item.get("body", "").encode()
    own_host = any(name.lower() == "host" for name, _ in item.get("headers", []))
    conn.putrequest(item.get("method", "GET"), item["path"], skip_host=own_host)
    for name, value in item.get("headers", []):
        conn.putheader(name, value)
    conn.putheader("Content-Length", str(len(body)))
    conn.endheaders(body)
    reply = conn.getresponse()
    reply.read()
    out.append({"status": reply.status, "location": reply.getheader("location")})
    conn.close()
print(json.dumps(out))
"""


def docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603  # fixed CLI, arguments are test constants
        ["docker", *args],  # noqa: S607
        check=check,
        capture_output=True,
        text=True,
        timeout=180,
    )


def environment(trusted: str | None, app_env: str = "test") -> list[str]:
    values = {
        "APP_ENV": app_env,
        "LOG_FORMAT": "json",
        "DATABASE_URL": os.environ["RUNTIME_PROXY_DATABASE_URL"],
        "REDIS_URL": f"redis://redis:6379/{REDIS_DB}",
        "CORS_ALLOWED_ORIGINS": "http://localhost:3000",
        "LLM_PROVIDER": "disabled",
        "EMBEDDING_PROVIDER": "hash",
        "STORAGE_BACKEND": "memory",
    }
    if trusted is not None:
        values["FORWARDED_ALLOW_IPS"] = trusted
    return [part for key, value in values.items() for part in ("-e", f"{key}={value}")]


def startup(*env: str) -> tuple[int | None, str]:
    """Start the image's own CMD; return (exit code, logs). None means it kept running."""
    name = "aud04-startup"
    docker("rm", "-f", name, check=False)
    docker("run", "-d", "--name", name, *env, IMAGE)
    try:
        deadline = time.monotonic() + 20
        code: int | None = None
        while time.monotonic() < deadline and code is None:
            state = docker("inspect", "-f", "{{.State.Running}} {{.State.ExitCode}}", name)
            running, exit_code = state.stdout.split()
            code = None if running == "true" else int(exit_code)
            time.sleep(0.5)
        logs = docker("logs", name, check=False)
        return code, logs.stdout + logs.stderr
    finally:
        docker("rm", "-f", name, check=False)


def flush_rate_limits() -> None:
    container = os.environ["RUNTIME_PROXY_REDIS_CONTAINER"]
    docker("exec", container, "redis-cli", "-n", REDIS_DB, "flushdb")


def rate_limit_keys() -> list[str]:
    container = os.environ["RUNTIME_PROXY_REDIS_CONTAINER"]
    result = docker("exec", container, "redis-cli", "-n", REDIS_DB, "--scan", "--pattern", "rl:*")
    return result.stdout.split()


def limiter_identities(candidates: list[str]) -> set[str]:
    """Which of the candidate addresses the login IP limiter actually counted."""
    keys = rate_limit_keys()
    return {
        address
        for address in candidates
        if any(
            key.startswith(f"rl:login_ip_min:{hashlib.sha256(address.encode()).hexdigest()[:32]}:")
            for key in keys
        )
    }


@pytest.fixture(scope="module")
def network() -> Iterator[str]:
    docker("rm", "-f", API_NAME, check=False)
    docker("network", "rm", NETWORK, check=False)
    docker("network", "create", "--subnet", SUBNET, NETWORK)
    try:
        yield NETWORK
    finally:
        docker("rm", "-f", API_NAME, check=False)
        docker("network", "rm", NETWORK, check=False)


class Api:
    def __init__(self, trusted: str | None) -> None:
        docker("rm", "-f", API_NAME, check=False)
        docker(
            "create",
            "--name",
            API_NAME,
            "--network",
            os.environ["RUNTIME_PROXY_STACK_NETWORK"],
            *environment(trusted),
            IMAGE,
        )
        docker("network", "connect", "--ip", API_IP, NETWORK, API_NAME)
        docker("start", API_NAME)
        deadline = time.monotonic() + 40
        probe = (
            "import urllib.request;"
            "urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"
        )
        while docker("exec", API_NAME, "python", "-c", probe, check=False).returncode:
            if time.monotonic() > deadline:
                pytest.fail(docker("logs", "--tail", "30", API_NAME, check=False).stdout)
            time.sleep(0.5)
        flush_rate_limits()

    def send(self, peer: str, requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = docker(
            "run",
            "--rm",
            "--network",
            NETWORK,
            "--ip",
            peer,
            IMAGE,
            "python",
            "-c",
            CLIENT,
            json.dumps(requests),
            API_IP,
        )
        return list(json.loads(result.stdout))


def login(index: int, *forwarded: str) -> dict[str, Any]:
    headers = [
        ["Content-Type", "application/json"],
        ["Origin", "http://localhost:3000"],
        ["X-Requested-With", "platform"],
        *[["X-Forwarded-For", value] for value in forwarded],
    ]
    body = json.dumps({"email": f"nobody-{index}@example.com", "password": "synthetic-password-1"})
    return {"method": "POST", "path": "/api/v1/auth/login", "headers": headers, "body": body}


def slash_redirect(*protos: str) -> dict[str, Any]:
    """`/healthz/` redirects using the request's effective scheme, which exposes it over HTTP."""
    headers = [["Host", "api.test"], *[["X-Forwarded-Proto", value] for value in protos]]
    return {"path": "/healthz/", "headers": headers}


@pytest.mark.usefixtures("network")
@pytest.mark.parametrize("trusted", [None, "", PROXY_IP], ids=["unset", "empty", "proxy-only"])
def test_direct_peer_cannot_choose_identity(trusted: str | None) -> None:
    api = Api(trusted)

    forged = [f"198.51.100.{n}" for n in range(1, 26)]
    replies = api.send(DIRECT_IP, [login(n, ip) for n, ip in enumerate(forged)])
    statuses = [reply["status"] for reply in replies]

    # 10 per minute per IP; 25 attempts stay above the limit even across one window boundary.
    assert statuses.count(429) >= 5, statuses
    assert limiter_identities([DIRECT_IP, *forged]) == {DIRECT_IP}


@pytest.mark.usefixtures("network")
@pytest.mark.parametrize("trusted", [None, PROXY_IP], ids=["unset", "proxy-only"])
def test_direct_peer_cannot_choose_scheme(trusted: str | None) -> None:
    redirect = Api(trusted).send(DIRECT_IP, [slash_redirect("https")])[0]

    assert redirect["location"] == "http://api.test/healthz"


@pytest.mark.usefixtures("network")
def test_trusted_proxy_chain_resolves_the_first_untrusted_client() -> None:
    api = Api(f"{PROXY_IP}, 192.0.2.0/24, 2001:db8:ffff::/48")
    seen = ["203.0.113.7", "203.0.113.8", "2001:db8::9", "203.0.113.200", "192.0.2.5", PROXY_IP]

    def identity(*forwarded: str) -> set[str]:
        flush_rate_limits()
        assert api.send(PROXY_IP, [login(0, *forwarded)])[0]["status"] == 401
        return limiter_identities(seen)

    assert identity("203.0.113.7") == {"203.0.113.7"}  # single hop
    # Client-supplied prefix, real client appended by the edge, then two trusted hops.
    assert identity("203.0.113.200, 203.0.113.8, 2001:db8:ffff::1, 192.0.2.5") == {"203.0.113.8"}
    assert identity("203.0.113.200", "2001:db8::9, 192.0.2.5") == {"2001:db8::9"}  # duplicates
    assert identity("") == {PROXY_IP}  # empty chain: keep the real peer
    assert api.send(PROXY_IP, [slash_redirect("https")])[0]["location"] == (
        "https://api.test/healthz"
    )
    for bad in (["javascript"], ["https, http"], ["HTTPS"]):
        reply = api.send(PROXY_IP, [slash_redirect(*bad)])[0]
        assert reply["location"] == "http://api.test/healthz", bad


@pytest.mark.parametrize("app_env", ["staging", "production"])
@pytest.mark.parametrize("value", ["*", "0.0.0.0/0", "::/0", "not-an-address"])
def test_unsafe_deployed_configuration_stops_startup(app_env: str, value: str) -> None:
    code, output = startup(*environment(value, app_env))

    assert code not in (None, 0), f"server started with {value!r}"
    assert "FORWARDED_ALLOW_IPS" in output or "forwarded_allow_ips" in output, output[-2000:]


@pytest.mark.parametrize(
    "extra",
    [["-e", "UVICORN_FORWARDED_ALLOW_IPS=*"], ["-e", "UVICORN_PROXY_HEADERS=true"]],
    ids=["uvicorn-trust-variable", "uvicorn-proxy-variable"],
)
def test_uvicorn_environment_overrides_stop_startup(extra: list[str]) -> None:
    code, output = startup(*environment(""), *extra)

    assert code not in (None, 0), "server started with a Uvicorn override"
    assert "uvicorn_" in output.lower()


def test_image_declares_no_proxy_trust() -> None:
    config = json.loads(docker("image", "inspect", IMAGE).stdout)[0]["Config"]

    assert "*" not in " ".join(config["Cmd"] or [])
    assert "FORWARDED_ALLOW_IPS=" in config["Env"]
