"""Seed a disposable stack through its public API, and check a restored copy through it too.

    python -m tests.support.restore_probe seed            # prints the state to keep
    python -m tests.support.restore_probe check '<state>'  # against the restored stack

For ``scripts/ci/restore-rehearsal.sh``, inside the api container. Synthetic data and demo
providers only. The state holds a throwaway password for the account it creates.
"""

from __future__ import annotations

import json
import re
import sys
import time
import uuid
from typing import Any

import httpx2 as httpx

from app.workers.celery_app import celery_app
from tests.support.documents import make_pdf

API = "http://127.0.0.1:8000"
MAILPIT = "http://mailpit:8025"
HEADERS = {"X-Requested-With": "platform"}
QUESTION = "How many days do I have to return an unworn item?"


class Client:
    def __init__(self, origin: str) -> None:
        self.http = httpx.Client(base_url=f"{API}/api/v1", timeout=60)
        self.headers = {**HEADERS, "Origin": origin}

    def call(self, method: str, path: str, expect: int = 200, **kwargs: Any) -> Any:
        headers = {**self.headers, **kwargs.pop("headers", {})}
        response = self.http.request(method, path, headers=headers, **kwargs)
        if response.status_code != expect:
            raise SystemExit(f"{method} {path}: HTTP {response.status_code} {response.text[:300]}")
        if path.startswith("/auth/") and (cookies := response.headers.get_list("set-cookie")):
            self.headers["Cookie"] = "; ".join(
                c.split(";", 1)[0] for c in cookies if c.startswith("__Host-")
            )
        return response


def wait_for(read: Any, what: str) -> Any:
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if value := read():
            return value
        time.sleep(0.5)
    raise SystemExit(f"timed out waiting for {what}")


def read_models(client: Client, state: dict[str, Any]) -> dict[str, Any]:
    """What a user sees: the transcript, retrieval over stored vectors and the inbox."""
    org, bot = state["org"], state["bot"]
    detail = client.call("GET", f"/orgs/{org}/conversations/{state['conversation']}").json()
    found = client.call(
        "POST", f"/orgs/{org}/chatbots/{bot}/retrieval/search", json={"query": QUESTION}
    ).json()["results"]
    inbox = client.call("GET", f"/orgs/{org}/conversations").json()
    return {
        "messages": [[m["role"], m["content"], len(m["citations"])] for m in detail["messages"]],
        "search": [[r["document_id"], r["content"]] for r in found],
        "inbox": sorted(item["id"] for item in inbox["data"]),
    }


def seed(origin: str) -> dict[str, Any]:
    client = Client(origin)
    email = f"restore-{uuid.uuid4().hex[:10]}@example.com"
    password = "restore-" + uuid.uuid4().hex
    created = client.call(
        "POST",
        "/auth/signup",
        201,
        json={"email": email, "password": password, "name": "Restore", "org_name": "Restore Org"},
    )
    org = created.json()["org"]["id"]

    def token() -> str | None:
        found = httpx.get(f"{MAILPIT}/api/v1/search", params={"query": f"to:{email}"}).json()
        if not found.get("messages"):
            return None
        body = httpx.get(f"{MAILPIT}/api/v1/message/{found['messages'][0]['ID']}").json()["Text"]
        match = re.search(r"verify-email\?token=([A-Za-z0-9_-]+)", body)
        return match.group(1) if match else None

    client.call("POST", "/auth/verify-email", json={"token": wait_for(token, "the email")})
    bot = client.call("POST", f"/orgs/{org}/chatbots", 201, json={"name": "Restore"}).json()["id"]
    base = f"/orgs/{org}/chatbots/{bot}"

    def upload(name: str, page: str) -> str:
        document = client.call(
            "POST",
            f"{base}/documents",
            201,
            params={"filename": name},
            content=make_pdf([page]),
            headers={"Content-Type": "application/pdf"},
        ).json()["id"]
        wait_for(
            lambda: client.call("GET", f"{base}/documents/{document}").json()["status"] == "ready",
            "indexing",
        )
        return str(document)

    upload("returns.pdf", "Unworn items can be returned within thirty days for a refund.")
    upload("shipping.pdf", "Standard orders ship within two business days of payment.")

    def chat() -> str:
        conversation = client.call("POST", f"{base}/conversations", 201).json()["id"]
        answer = client.call(
            "POST",
            f"/orgs/{org}/conversations/{conversation}/messages",
            json={"content": QUESTION},
        )
        if "event: done" not in answer.text:
            raise SystemExit(f"no completed answer: {answer.text[:300]}")
        return str(conversation)

    kept, deleted = chat(), chat()
    # Usage must outlive this conversation: the case a downgrade below 0007 cannot hold.
    client.call("DELETE", f"/orgs/{org}/conversations/{deleted}", 204)
    celery_app.send_task("analytics.rollup").get(timeout=60)
    state = {"email": email, "password": password, "org": org, "bot": bot, "conversation": kept}
    return {**state, "expected": read_models(client, state)}


def check(origin: str, state: dict[str, Any]) -> None:
    client = Client(origin)
    client.call("POST", "/auth/login", json={k: state[k] for k in ("email", "password")})
    seen = read_models(client, state)
    for key, value in state["expected"].items():
        if seen[key] != value or not value:
            raise SystemExit(f"restored {key} differs from the source")
    sys.stdout.write(
        f"restored application reads match: {len(seen['messages'])} messages, "
        f"{len(seen['search'])} search results, {len(seen['inbox'])} conversations\n"
    )


if __name__ == "__main__":
    from app.core.config import get_settings

    web = get_settings().cors_allowed_origins[0]
    if sys.argv[1] == "seed":
        sys.stdout.write("STATE " + json.dumps(seed(web)) + "\n")
    else:
        check(web, json.loads(sys.argv[2]))
