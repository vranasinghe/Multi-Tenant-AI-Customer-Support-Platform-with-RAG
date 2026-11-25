"""Full-stack ingestion smoke test: real API process, real Celery worker, real S3-compatible
storage, real Postgres/pgvector. Nothing is mocked or injected.

Opt-in (needs the whole Docker stack running, including the worker):

    docker compose exec -e LIVE_INGESTION=1 api pytest tests/integration/test_live_ingestion.py
"""

from __future__ import annotations

import os
import re
import time
import uuid
from typing import Any

import httpx2 as httpx
import pytest

from app.core.config import get_settings
from app.rag.storage import S3ObjectStore
from app.workers.celery_app import celery_app
from tests.support.documents import make_pdf

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("LIVE_INGESTION") != "1", reason="set LIVE_INGESTION=1"),
]

API = os.environ.get("LIVE_API_URL", "http://127.0.0.1:8000")
MAILPIT = os.environ.get("LIVE_MAILPIT_URL", "http://mailpit:8025")
ORIGIN = os.environ.get("LIVE_ORIGIN", "http://localhost:3000")
PASSWORD = "live-" + uuid.uuid4().hex  # throwaway, generated per run


class Session:
    def __init__(self) -> None:
        self.http = httpx.Client(base_url=f"{API}/api/v1", timeout=30)
        self.cookie: str | None = None

    def call(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        headers = {"Origin": ORIGIN, "X-Requested-With": "platform", **kwargs.pop("headers", {})}
        if self.cookie:
            headers["Cookie"] = self.cookie
        return self.http.request(method, path, headers=headers, **kwargs)


def wait_for(predicate: Any, *, timeout: float = 60, what: str = "condition") -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.5)
    pytest.fail(f"timed out waiting for {what}")


def test_upload_index_search_delete_across_real_services() -> None:
    session = Session()
    email = f"live-{uuid.uuid4().hex[:10]}@example.com"
    signup = session.call(
        "POST",
        "/auth/signup",
        json={"email": email, "password": PASSWORD, "name": "Live", "org_name": "Live Org"},
    )
    assert signup.status_code == 201, signup.text
    session.cookie = "; ".join(
        h.split(";", 1)[0] for h in signup.headers.get_list("set-cookie") if h.startswith("__Host-")
    )
    org = signup.json()["org"]["id"]

    def verification_token() -> str | None:
        found = httpx.get(f"{MAILPIT}/api/v1/search", params={"query": f"to:{email}"}).json()
        if not found.get("messages"):
            return None
        body = httpx.get(f"{MAILPIT}/api/v1/message/{found['messages'][0]['ID']}").json()["Text"]
        match = re.search(r"verify-email\?token=([A-Za-z0-9_-]+)", body)
        return match.group(1) if match else None

    token = wait_for(verification_token, what="verification email")
    assert session.call("POST", "/auth/verify-email", json={"token": token}).status_code == 200

    bot = session.call("POST", f"/orgs/{org}/chatbots", json={"name": "Live bot"}).json()["id"]
    base = f"/orgs/{org}/chatbots/{bot}"
    pdf = make_pdf(
        [
            "The Reno warehouse ships standard orders within two business days of payment.",
            "Unworn items can be returned within thirty days for a complete refund.",
        ]
    )

    uploaded = session.call(
        "POST",
        f"{base}/documents",
        params={"filename": "policies.pdf"},
        content=pdf,
        headers={"Content-Type": "application/pdf"},
    )
    assert uploaded.status_code == 201, uploaded.text
    document_id = uploaded.json()["id"]
    assert uploaded.json()["status"] == "queued"

    def ready() -> dict[str, Any] | None:
        doc: dict[str, Any] = session.call("GET", f"{base}/documents/{document_id}").json()
        assert doc["status"] != "failed", doc
        return doc if doc["status"] == "ready" else None

    document = wait_for(ready, what="the worker to finish indexing")
    assert document["page_count"] == 2 and document["chunk_count"] >= 1
    assert document["job"]["status"] == "succeeded"

    store = S3ObjectStore(get_settings())
    listing = store._client.list_objects_v2(Bucket=get_settings().s3_bucket, Prefix=f"orgs/{org}/")
    assert listing["KeyCount"] == 1

    found = session.call(
        "POST", f"{base}/retrieval/search", json={"query": "how many days to return for a refund"}
    ).json()["results"]
    assert found and "thirty days" in found[0]["content"] and found[0]["page_end"] == 2

    assert session.call("DELETE", f"{base}/documents/{document_id}").status_code == 204
    assert (
        session.call("POST", f"{base}/retrieval/search", json={"query": "refund"}).json()["results"]
        == []
    )

    celery_app.send_task("ingest.sweep", queue="default").get(timeout=60)  # real maintenance task
    listing = store._client.list_objects_v2(Bucket=get_settings().s3_bucket, Prefix=f"orgs/{org}/")
    assert listing["KeyCount"] == 0
