"""A2 exact provider input vs SSE/transcript, with real tenant RLS/Redis and synthetic output."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator
from dataclasses import replace
from typing import Any

import pytest

from app.core.config import Settings
from app.integrations.llm import CompletionEvent, ProviderError
from app.rag.retrieval import RetrievedChunk
from app.rag.runtime import Runtime
from app.schemas.conversations import SendMessage
from app.services import conversations
from app.services.public_view import public_citation
from tests.integration.api.conftest import Actor, Api
from tests.integration.api.test_conversations import conversation, done, send
from tests.integration.api.test_knowledge_documents import ingest, new_bot

pytestmark = pytest.mark.integration


class ScriptedProvider:
    def __init__(self) -> None:
        self.prompts: list[list[dict[str, str]]] = []
        self.parts = ["Answer [", "1", "] repeated [1]. Omitted [", "2] bad [01] [", "999]."]
        self.fail = False
        self.closed = False

    async def stream(
        self, messages: list[dict[str, str]], *, model: str, max_tokens: int, temperature: float
    ) -> AsyncGenerator[CompletionEvent]:
        self.prompts.append(messages)
        try:
            for part in self.parts:
                yield CompletionEvent(text=part)
            if self.fail:
                raise ProviderError("provider_unavailable")
            yield CompletionEvent(input_tokens=100, output_tokens=20)
        finally:
            self.closed = True


@pytest.fixture
def prepared(
    api: Api, api_settings: Settings, runtime: Runtime, job_queue: Any
) -> tuple[Actor, str, str, ScriptedProvider, list[RetrievedChunk]]:
    api_settings.llm_provider = "demo"
    provider = ScriptedProvider()
    app: Any = api.client.app
    app.state.services = replace(app.state.services, chat_provider=provider)
    actor = api.signup()
    bot = new_bot(actor)
    candidates = []
    for name in ["first.txt", "omitted.txt"]:
        doc = ingest(
            api,
            runtime,
            job_queue,
            actor,
            bot,
            name,
            ("Returns within thirty days. " + name).encode(),
            "text/plain",
        )
        candidates.append(candidate(api, doc["id"]))
    api.sql(
        "UPDATE document_chunks SET content=:body WHERE id=:id",
        body="&" * 2500,
        id=str(candidates[0].chunk_id),
    )
    return actor, bot, conversation(actor, bot), provider, candidates


def candidate(api: Api, document_id: str) -> RetrievedChunk:
    rows = api.sql(
        "SELECT c.id,c.document_id,d.source_id,d.title,d.uri,c.ordinal,c.content,c.heading_path,c.page_start,c.page_end "
        "FROM document_chunks c JOIN documents d ON d.id=c.document_id WHERE d.id=:id ORDER BY c.ordinal LIMIT 1",
        id=document_id,
    )
    row = rows[0]
    return RetrievedChunk(
        chunk_id=row[0],
        document_id=row[1],
        source_id=row[2],
        document_title=row[3],
        uri=row[4],
        ordinal=row[5],
        content=row[6],
        heading_path=row[7],
        page_start=row[8],
        page_end=row[9],
        score=1.0,
        vector_score=1.0,
    )


def inject(monkeypatch: pytest.MonkeyPatch, candidates: list[RetrievedChunk]) -> None:
    async def retrieved(*args: Any, **kwargs: Any) -> list[RetrievedChunk]:
        return candidates

    monkeypatch.setattr(conversations, "search", retrieved)


def deltas(response: Any) -> str:
    return "".join(
        json.loads(frame.split("data: ", 1)[1])["text"]
        for frame in response.text.split("\n\n")
        if frame.startswith("event: delta")
    )


@pytest.mark.parametrize("public", [False, True])
def test_omitted_source_cannot_reach_sse_or_persisted_citations(
    api: Api,
    prepared: tuple[Actor, str, str, ScriptedProvider, list[RetrievedChunk]],
    monkeypatch: pytest.MonkeyPatch,
    public: bool,
) -> None:
    actor, bot, conv, provider, candidates = prepared
    inject(monkeypatch, candidates)
    if public:
        actor.patch(f"/orgs/{actor.org_id}/chatbots/{bot}", {"status": "active"})
        session = actor.post(f"/orgs/{actor.org_id}/chatbots/{bot}/widget-sessions").json()
        conv = session["conversation_id"]
        response = api.client.post(
            "/public/v1/chat/messages",
            headers={"Authorization": "Bearer " + session["token"]},
            json={"content": "Returns?"},
        )
    else:
        response = send(actor, conv, "Returns?")
    result = done(response)
    assert result["status"] == "complete"
    assert deltas(response) == result["content"] == "Answer [1] repeated [1]. Omitted  bad  ."
    prompt = provider.prompts[-1][-1]["content"]
    assert '<source id="1"' in prompt and '<source id="2"' not in prompt
    assert "omitted.txt" not in prompt
    stored = actor.get(f"/orgs/{actor.org_id}/conversations/{conv}").json()["messages"][-1]
    assert [c["chunk_id"] for c in stored["citations"]] == [str(candidates[0].chunk_id)]
    assert stored["content"] == deltas(response)
    # A visitor is told the same citations, without the records behind them (WIDGET-PRIV-01).
    expected = [public_citation(c) for c in stored["citations"]] if public else stored["citations"]
    assert result["citations"] == expected
    assert "prompt" not in result and "chunks" not in result


def test_authorization_filters_foreign_candidates_and_restores_canonical_metadata(
    api: Api,
    runtime: Runtime,
    job_queue: Any,
    prepared: tuple[Actor, str, str, ScriptedProvider, list[RetrievedChunk]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor, _, conv, provider, candidates = prepared
    foreign = []
    for owner in [actor, api.signup()]:
        bot = new_bot(owner)
        doc = ingest(
            api,
            runtime,
            job_queue,
            owner,
            bot,
            "FOREIGN.txt",
            b"FOREIGN confidential returns.",
            "text/plain",
        )
        foreign.append(candidate(api, doc["id"]))
    forged = replace(
        candidates[0],
        document_title="FORGED",
        uri="https://forged.test",
        content="FORGED",
        document_id=foreign[0].document_id,
    )
    inject(monkeypatch, [*foreign, forged, forged])
    result = done(send(actor, conv, "Returns?"))
    prompt = provider.prompts[-1][-1]["content"]
    assert "FOREIGN" not in prompt and "FORGED" not in prompt
    assert [c["id"] for c in result["citations"]] == [1]
    assert result["citations"][0]["document_id"] == str(candidates[0].document_id)
    assert result["citations"][0]["title"] == "first.txt"


@pytest.mark.parametrize("mutation", ["deleted", "superseded", "model", "bot_deleted"])
def test_stale_candidates_cannot_render_or_invoke_provider(
    api: Api,
    prepared: tuple[Actor, str, str, ScriptedProvider, list[RetrievedChunk]],
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    actor, bot, conv, provider, candidates = prepared
    inject(monkeypatch, candidates[:1])
    if mutation == "deleted":
        assert (
            actor.delete(
                f"/orgs/{actor.org_id}/chatbots/{bot}/documents/{candidates[0].document_id}"
            ).status_code
            == 204
        )
    elif mutation == "superseded":
        api.sql(
            "UPDATE documents SET version=version+1 WHERE id=:id", id=str(candidates[0].document_id)
        )
    elif mutation == "model":
        api.sql(
            "UPDATE document_chunks SET embedding_model='retired-model' WHERE id=:id",
            id=str(candidates[0].chunk_id),
        )
    else:
        assert actor.delete(f"/orgs/{actor.org_id}/chatbots/{bot}").status_code == 204
    response = send(actor, conv, "Returns?")
    if mutation == "bot_deleted":
        assert response.status_code == 404
    else:
        result = done(response)
        assert result["status"] == "fallback" and result["citations"] == []
    assert provider.prompts == []


@pytest.mark.parametrize("terminal", ["failed", "interrupted"])
def test_partial_citation_snapshots_match_output_after_failure_or_disconnect(
    api: Api,
    prepared: tuple[Actor, str, str, ScriptedProvider, list[RetrievedChunk]],
    monkeypatch: pytest.MonkeyPatch,
    terminal: str,
) -> None:
    actor, _, conv, provider, candidates = prepared
    inject(monkeypatch, candidates)
    provider.parts = ["Partial [", "1] bad [999]", " unfinished [1"]
    if terminal == "failed":
        provider.fail = True
        response = send(actor, conv, "Returns?")
        result = done(response)
        assert result["status"] == "failed" and result["content"] == deltas(response)
        observed = deltas(response)
    else:
        app: Any = api.client.app

        async def interrupt() -> str:
            turn = await conversations.prepare(
                app.state.services,
                uuid.UUID(actor.org_id),
                uuid.UUID(conv),
                SendMessage(content="Returns?"),
            )
            stream = conversations.stream(app.state.services, turn)
            await anext(stream)  # meta
            first, second = await anext(stream), await anext(stream)
            await stream.aclose()
            return deltas(type("Response", (), {"text": first + second})())

        assert api.client.portal
        observed = api.client.portal.call(interrupt)
    stored = actor.get(f"/orgs/{actor.org_id}/conversations/{conv}").json()["messages"][-1]
    assert stored["status"] == terminal and stored["content"] == observed
    assert [c["chunk_id"] for c in stored["citations"]] == [str(candidates[0].chunk_id)]
    assert provider.closed


def test_empty_rendered_evidence_sanitizes_configured_fallback(
    api: Api,
    api_settings: Settings,
    prepared: tuple[Actor, str, str, ScriptedProvider, list[RetrievedChunk]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor, bot, conv, provider, candidates = prepared
    api.sql(
        "UPDATE documents SET title=:title WHERE id=:id",
        title="&" * 300,
        id=str(candidates[0].document_id),
    )
    api_settings.chat_input_token_budget = 2000
    api.sql("UPDATE chatbots SET fallback_message='Contact support [1]' WHERE id=:id", id=bot)
    inject(monkeypatch, candidates[:1])
    result = done(send(actor, conv, "Returns?"))
    assert result["status"] == "fallback" and result["content"] == "Contact support "
    assert result["citations"] == [] and provider.prompts == []
