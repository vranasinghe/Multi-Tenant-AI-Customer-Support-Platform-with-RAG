"""WIDGET-PRIV-01 (AUD-07): what a website visitor can read, field by field.

Field sets are exact: a new internal field must not reach the public surface by default.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.core.config import Settings
from app.rag.queue import RecordingJobQueue
from app.rag.runtime import Runtime
from app.services.public_view import public_citation
from tests.integration.api.conftest import Actor, Api
from tests.integration.api.test_knowledge_documents import ingest
from tests.integration.api.test_widget import boot
from tests.integration.api.test_widget import setup as widget_setup

pytestmark = pytest.mark.integration

MESSAGE = {"id", "role", "content", "status", "feedback", "citations"}
CITATION = {"id", "title", "uri"}
EVENTS = {"meta": {"message_id"}, "delta": {"text"}, "done": MESSAGE}
SESSION = {
    "token",
    "resume_token",
    "expires_at",
    "retain_until",
    "retention_days",
    "name",
    "welcome",
    "branding",
}
BRANDING = {
    "primary_color",
    "accent_color",
    "avatar_url",
    "position",
    "launcher_label",
    "show_branding",
}


@pytest.fixture(autouse=True)
def demo(api_settings: Settings) -> None:
    api_settings.llm_provider = "demo"


def visitor(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue
) -> tuple[Actor, dict[str, Any], dict[str, str]]:
    owner, bot, key, _ = widget_setup(api)
    ingest(
        api,
        runtime,
        job_queue,
        owner,
        bot,
        "returns.txt",
        b"Returns are allowed within thirty days of delivery with a receipt.",
        "text/plain",
    )
    session = boot(api, key)
    assert session.status_code == 200, session.text
    api.client.cookies.clear()
    return owner, session.json(), {"Authorization": "Bearer " + session.json()["token"]}


def events(text: str) -> list[tuple[str, dict[str, Any]]]:
    found = []
    for frame in filter(None, text.split("\n\n")):
        name, data = frame.split("\n", 1)
        found.append((name.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return found


def test_public_stream_and_history_use_the_public_fields_only(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue
) -> None:
    owner, session, headers = visitor(api, runtime, job_queue)
    assert set(session) == SESSION and set(session["branding"]) <= BRANDING

    sent = api.client.post(
        "/public/v1/chat/messages", headers=headers, json={"content": "Are returns allowed?"}
    )
    stream = events(sent.text)
    history = api.client.get("/public/v1/chat", headers=headers).json()

    assert {name for name, _ in stream} == {"meta", "delta", "done"}
    for name, payload in stream:
        assert set(payload) == EVENTS[name], name
    done = stream[-1][1]
    assert done["citations"] and all(set(c) == CITATION for c in done["citations"])
    assert done["citations"][0] == {"id": 1, "title": "returns.txt", "uri": ""}
    assert set(history) == {"messages"}
    assert [set(m) for m in history["messages"]] == [MESSAGE, MESSAGE]
    assert history["messages"][-1] == done
    assert history["messages"][0]["role"] == "user" and history["messages"][0]["citations"] == []

    # The dashboard transcript of the same conversation, and the accounting, keep everything.
    [row] = api.sql("SELECT conversation_id FROM messages WHERE id = :id", id=done["id"])
    full = owner.get(f"/orgs/{owner.org_id}/conversations/{row[0]}").json()["messages"][-1]
    assert {"input_tokens", "output_tokens", "estimated_cost_usd", "usage_estimated"} <= set(full)
    assert {"document_id", "chunk_id", "uri", "page", "title", "id"} == set(full["citations"][0])
    assert full["content"] == done["content"]
    assert full["input_tokens"] > 0
    [usage] = api.sql("SELECT state, charged_tokens FROM chat_usage WHERE id = :id", id=done["id"])
    assert usage[0] == "settled" and usage[1] > 0

    feedback = api.client.put(
        f"/public/v1/chat/messages/{done['id']}/feedback", headers=headers, json={"rating": 1}
    )
    assert feedback.json() == {"status": "ok"}
    assert (
        api.client.get("/public/v1/chat", headers=headers).json()["messages"][-1]["feedback"] == 1
    )


def test_a_failed_public_answer_reports_no_diagnostic(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue
) -> None:
    from dataclasses import replace

    from app.integrations.llm import ProviderError

    class Failing:
        async def stream(self, *_: Any, **__: Any) -> Any:
            nothing: tuple[Any, ...] = ()
            for item in nothing:
                yield item
            raise ProviderError("invalid_provider_usage")

    _, _, headers = visitor(api, runtime, job_queue)
    app: Any = api.client.app
    app.state.services = replace(app.state.services, chat_provider=Failing())

    sent = api.client.post(
        "/public/v1/chat/messages", headers=headers, json={"content": "Are returns allowed?"}
    )

    stream = dict(events(sent.text))
    assert stream["error"] == {
        "code": "answer_failed",
        "message": "The answer could not finish. Please try again.",
    }
    assert stream["done"]["status"] == "failed" and set(stream["done"]) == MESSAGE
    assert "invalid_provider_usage" not in sent.text


@pytest.mark.parametrize(
    ("uri", "public"),
    [
        ("https://docs.example.com/returns", "https://docs.example.com/returns"),
        ("returns.txt", ""),
        ("http://intranet.example.com/page", ""),
        ("https://user:secret@example.com/x", ""),
        ("javascript:alert(1)", ""),
        ("https://[broken", ""),
    ],
)
def test_a_citation_keeps_only_a_safe_public_link(uri: str, public: str) -> None:
    stored = {
        "id": 3,
        "title": "Returns",
        "uri": uri,
        "page": 2,
        "document_id": "d",
        "chunk_id": "c",
    }

    assert public_citation(stored) == {"id": 3, "title": "Returns", "uri": public}


def test_the_frame_accepts_only_a_well_formed_instance_key(api: Api) -> None:
    _, _, key, _ = widget_setup(api)
    query = {"parent_origin": "http://localhost:3000", "instance": "n1"}

    def frame(**extra: str) -> Any:
        return api.client.get(f"/widget/frame/{key}", params={**query, **extra})

    assert "data-instance-key" not in frame().text
    assert 'data-instance-key="footer-2"' in frame(instance_key="footer-2").text
    for bad in ('"><script>', "a b", "x" * 33, ""):
        assert frame(instance_key=bad).status_code == 422, bad
