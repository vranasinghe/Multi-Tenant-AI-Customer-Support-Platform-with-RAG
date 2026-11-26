"""Fixtures for HTTP-level integration tests: a real app over a migrated Postgres and Redis."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import httpx2 as httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from redis import Redis
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import Settings
from app.main import create_app
from app.rag.queue import RecordingJobQueue
from app.rag.runtime import Runtime
from app.rag.safe_fetch import SafeFetcher
from app.rag.storage import MemoryObjectStore
from tests.conftest import make_settings
from tests.support.database import TestDatabase
from tests.support.email import Mailbox
from tests.support.rag import make_runtime

ORIGIN = "https://app.test"
PASSWORD = "correct horse battery staple"
COOKIE = "__Host-session"


def _redis_test_url() -> str:
    base = os.environ.get("REDIS_URL")
    if not base:
        pytest.skip("REDIS_URL is required for API integration tests")
    return make_url(base).set(database="15").render_as_string(hide_password=False)


@pytest.fixture(autouse=True)
def redis_client() -> Redis:
    client: Redis = Redis.from_url(_redis_test_url())
    client.flushdb()
    return client


@pytest.fixture
def api_settings(test_database: TestDatabase) -> Settings:
    return make_settings(
        database_url=test_database.app_url.render_as_string(hide_password=False),
        redis_url=_redis_test_url(),
        cors_allowed_origins=[ORIGIN],
        web_base_url=ORIGIN,
        argon2_memory_kib=8,
        argon2_time_cost=1,
        rate_limit_signup_per_hour=1000,
        rate_limit_invite_lookup_per_minute=1000,
        rate_limit_search_per_minute=100_000,
        rate_limit_upload_per_minute=100_000,
        upload_max_bytes=64 * 1024,
        chunk_size_tokens=60,
        chunk_overlap_tokens=10,
        ingest_retry_base_seconds=0,
    )


@pytest.fixture
def mailbox() -> Mailbox:
    return Mailbox()


@pytest.fixture
def object_store() -> MemoryObjectStore:
    return MemoryObjectStore()


@pytest.fixture
def job_queue() -> RecordingJobQueue:
    return RecordingJobQueue()


@pytest.fixture
def web_fetcher() -> SafeFetcher:
    """Public-looking DNS answers without touching the network (never fetches in API tests)."""
    return SafeFetcher(
        user_agent="ACSBot/test",
        resolver=lambda host, _port: ["10.0.0.5"] if host.startswith("evil") else ["93.184.216.34"],
    )


@pytest.fixture
def app(
    api_settings: Settings,
    mailbox: Mailbox,
    object_store: MemoryObjectStore,
    job_queue: RecordingJobQueue,
    web_fetcher: SafeFetcher,
) -> FastAPI:
    return create_app(
        api_settings,
        email_sender=mailbox,
        object_store=object_store,
        job_queue=job_queue,
        fetcher=web_fetcher,
    )


@pytest.fixture
def runtime(
    api_settings: Settings, test_database: TestDatabase, object_store: MemoryObjectStore
) -> Iterator[Runtime]:
    """Worker-side collaborators on the same test database and in-memory object store."""
    engine = create_engine(test_database.app_url)
    yield make_runtime(api_settings, engine, object_store)
    engine.dispose()


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, base_url="https://testserver", raise_server_exceptions=False) as c:
        yield c


class _Unset:
    """Sentinel: 'use the actor's own session cookie' (None means 'send no cookie')."""


UNSET = _Unset()


@dataclass
class Actor:
    """A user with an independent cookie. All actors share one TestClient (one event loop)."""

    api: Api
    email: str
    password: str = PASSWORD
    name: str = "Test User"
    cookie: str | None = None
    user_id: str = ""
    org_id: str = ""

    def request(
        self,
        method: str,
        path: str,
        *,
        csrf: bool = True,
        cookie: str | _Unset | None = UNSET,
        **kwargs: Any,
    ) -> httpx.Response:
        headers = {"Origin": ORIGIN, "X-Requested-With": "platform"} if csrf else {}
        headers.update(kwargs.pop("headers", {}))
        token = self.cookie if isinstance(cookie, _Unset) else cookie
        if token:
            headers["Cookie"] = f"{COOKIE}={token}"
        self.api.client.cookies.clear()
        response = self.api.client.request(method, f"/api/v1{path}", headers=headers, **kwargs)
        self.api.client.cookies.clear()
        return response

    def get(self, path: str, **kw: Any) -> httpx.Response:
        return self.request("GET", path, **kw)

    def post(self, path: str, json: Any = None, **kw: Any) -> httpx.Response:
        return self.request("POST", path, json={} if json is None else json, **kw)

    def patch(self, path: str, json: Any, **kw: Any) -> httpx.Response:
        return self.request("PATCH", path, json=json, **kw)

    def put(self, path: str, json: Any, **kw: Any) -> httpx.Response:
        return self.request("PUT", path, json=json, **kw)

    def delete(self, path: str, **kw: Any) -> httpx.Response:
        return self.request("DELETE", path, **kw)

    def login(self, password: str | None = None) -> httpx.Response:
        # Like a browser, present the current session cookie (if any) so rotation is exercised.
        response = self.post(
            "/auth/login", {"email": self.email, "password": password or self.password}
        )
        if response.status_code == 200:
            self.cookie = session_cookie(response)
        return response


def session_cookie(response: httpx.Response) -> str | None:
    for header in response.headers.get_list("set-cookie"):
        if header.startswith(f"{COOKIE}="):
            value = header.split(";", 1)[0].split("=", 1)[1]
            return value or None
    return None


@dataclass
class Api:
    client: TestClient
    mailbox: Mailbox
    owner_engine: Engine
    actors: list[Actor] = field(default_factory=list)

    def anonymous(self) -> Actor:
        return Actor(api=self, email="anonymous@example.com")

    def signup(
        self,
        *,
        email: str | None = None,
        org_name: str | None = None,
        verified: bool = True,
        name: str = "Test User",
    ) -> Actor:
        address = email or f"user-{uuid.uuid4().hex[:10]}@example.com"
        actor = Actor(api=self, email=address, name=name)
        response = actor.post(
            "/auth/signup",
            {
                "email": address,
                "password": PASSWORD,
                "name": name,
                "org_name": org_name or f"Org of {address.split('@')[0]}",
            },
            cookie=None,
        )
        assert response.status_code == 201, response.text
        body = response.json()
        actor.cookie = session_cookie(response)
        actor.user_id = body["user"]["id"]
        actor.org_id = body["org"]["id"]
        if verified:
            self.verify_email(actor)
        self.actors.append(actor)
        return actor

    def verify_email(self, actor: Actor) -> None:
        token = self.mailbox.last_token(actor.email, path="verify-email")
        response = actor.post("/auth/verify-email", {"token": token}, cookie=None)
        assert response.status_code == 200, response.text

    def sql(self, statement: str, **params: Any) -> Any:
        with self.owner_engine.begin() as conn:
            result = conn.execute(text(statement), params)
            return result.all() if result.returns_rows else result.rowcount


@pytest.fixture
def api(client: TestClient, mailbox: Mailbox, owner_engine: Engine) -> Api:
    return Api(client=client, mailbox=mailbox, owner_engine=owner_engine)
