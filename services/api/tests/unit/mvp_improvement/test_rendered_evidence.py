"""A2 deterministic provenance/budget tests: no model or semantic quality claims."""

from __future__ import annotations

import html
from dataclasses import FrozenInstanceError, replace

import pytest
from defusedxml import ElementTree

from app.rag.retrieval import EMPTY_CONTEXT, render_evidence
from app.services.chat_prompt import CitationStream, assemble, citations_for, token_bound
from tests.unit.audit.test_prompt_evidence import source


@pytest.mark.parametrize("body", ["&<>\"'" * 600, "සිංහල 中文 🙂 &<>" * 300, "plain" * 2000])
def test_exact_escaped_utf8_budget_and_immutable_snapshot(body: str) -> None:
    candidate = replace(source(body), document_title='Title & "', uri="https://example.test/?a=<b>")
    for budget in [len(EMPTY_CONTEXT.encode()), 150, 201, 511, 12000]:
        rendered = render_evidence([candidate], max_bytes=budget)
        assert len(rendered.text.encode("utf-8")) <= budget
        root = ElementTree.fromstring(rendered.text)  # balanced tags and complete escape units
        assert len(root) == len(rendered.sources)
        for element, snapshot in zip(root, rendered.sources, strict=True):
            assert element.attrib["id"] == str(snapshot.id)
            assert element.text == "\n" + snapshot.content + "\n"
            assert snapshot.markup in rendered.text
            assert html.escape(snapshot.content, quote=True) in snapshot.markup
            assert candidate.content.startswith(snapshot.content)
            with pytest.raises(FrozenInstanceError):
                snapshot.content = "changed"  # type: ignore[misc]  # deliberate frozen mutation
        assert isinstance(rendered.sources, tuple)


def test_metadata_overhead_skips_source_before_assigning_ids() -> None:
    oversized = replace(source("hidden"), document_title="&" * 2000)
    empty, valid = source(" \n"), source("VISIBLE")
    rendered = render_evidence([oversized, empty, valid], max_bytes=500)
    assert [s.chunk_id for s in rendered.sources] == [valid.chunk_id]
    assert [s.id for s in rendered.sources] == [1]
    assert "hidden" not in rendered.text
    assert citations_for("Valid [1] absent [2]", rendered.sources)[0]["chunk_id"] == str(
        valid.chunk_id
    )
    assert citations_for("Absent [2]", rendered.sources) == []


def test_partial_source_excludes_following_candidate_and_mutable_inputs() -> None:
    first, omitted = source("&" * 2500), source("MUST_NOT_APPEAR")
    candidates = [first, omitted]
    prompt, evidence = assemble("", candidates, "Question?", [], budget=16000)
    assert len(evidence) == 1 and "MUST_NOT_APPEAR" not in prompt[-1]["content"]
    assert evidence[0].content != first.content
    first.heading_path.append("mutated")
    candidates.clear()
    assert evidence[0].markup in prompt[-1]["content"]
    assert citations_for("Repeated [1] [1] omitted [2]", evidence) == citations_for("[1]", evidence)


def test_full_prompt_budget_includes_history_question_and_metadata() -> None:
    chunks = [replace(source("සිංහල &" * 3000), document_title="&" * 50)]
    history = [{"role": "user", "content": "past" * 200}, {"role": "assistant", "content": "old"}]
    for budget in [1400, 2000, 4000, 16000]:
        prompt, evidence = assemble("preferences &", chunks, "中文 &?", history, budget=budget)
        assert token_bound(prompt) <= budget
        assert all(s.markup in prompt[-1]["content"] for s in evidence)
        if budget == 16000:
            assert len(prompt) == 4
        else:
            assert len(prompt) == 2
    with pytest.raises(ValueError, match="context_limit"):
        assemble("X" * 4000, chunks, "?", [], budget=1000)
    assert history[0]["content"] == "past" * 200


def test_empty_evidence_has_no_accepted_ids() -> None:
    prompt, evidence = assemble("", [source("\n ")], "?", [], budget=16000)
    assert EMPTY_CONTEXT in prompt[-1]["content"] and evidence == ()
    assert citations_for("Invented [1]", evidence) == []
    parser = CitationStream(evidence)
    assert parser.feed("Invented [1]") + parser.finish() == "Invented "
    with pytest.raises(ValueError, match="context_limit"):
        render_evidence([], max_bytes=1)


@pytest.mark.parametrize(
    "marker",
    [
        "[0]",
        "[01]",
        "[2]",
        "[9999999]",
        "[-1]",
        "[+1]",
        "[ 1 ]",
        "[1,2]",
        "[1.0]",
        "[\u0661]",
        "[[1]]",
        "[1x]",
        "[" + "a" * 80 + "]",
        "[1",
    ],
)
def test_invalid_markers_never_escape_across_any_delta_boundary(marker: str) -> None:
    evidence = render_evidence([source("valid")]).sources
    text = "Before " + marker + " after [1] [1] [note]"
    expected = "Before  after [1] [1] [note]" if marker.endswith("]") else "Before "
    for split in range(len(text) + 1):
        parser = CitationStream(evidence)
        output = parser.feed(text[:split]) + parser.feed(text[split:]) + parser.finish()
        assert output == expected
        assert len(citations_for(output, evidence)) == (1 if marker.endswith("]") else 0)


def test_one_character_deltas_and_bounded_unterminated_marker() -> None:
    evidence = render_evidence([source("one"), source("two")]).sources
    parser = CitationStream(evidence)
    output = "".join(parser.feed(c) for c in "A [1] B [2] bad [999] again [1].")
    assert output + parser.finish() == "A [1] B [2] bad  again [1]."
    assert parser.accepted == {1, 2}
    assert [c["id"] for c in citations_for(output, evidence)] == [1, 2]
    assert parser.feed("[" + "1" * 100000) == ""
    assert len(parser.pending) <= 64
    assert parser.finish() == ""
