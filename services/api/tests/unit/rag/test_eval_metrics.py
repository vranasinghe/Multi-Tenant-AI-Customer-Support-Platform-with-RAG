from __future__ import annotations

import math

from tests.integration.api.rag_eval.metrics import (
    false_accept_rate,
    first_relevant_rank,
    mrr,
    normalize,
    recall_at_k,
    summarize,
)


def test_first_relevant_rank_is_case_and_whitespace_insensitive() -> None:
    chunks = ["nothing here", "Orders over $75  qualify\nfor free shipping", "other"]
    assert first_relevant_rank(chunks, ["QUALIFY for free shipping"]) == 2
    assert first_relevant_rank(chunks, ["absent phrase"]) is None
    assert first_relevant_rank(chunks, ["absent", "nothing here"]) == 1
    assert first_relevant_rank([], ["x"]) is None


def test_recall_at_k_counts_hits_within_k() -> None:
    ranks = [1, 3, None, 6, 2]
    assert recall_at_k(ranks, 1) == 0.2
    assert recall_at_k(ranks, 3) == 0.6
    assert recall_at_k(ranks, 10) == 0.8
    assert recall_at_k([], 5) == 0.0


def test_mrr_uses_reciprocal_of_first_hit_and_cutoff() -> None:
    assert math.isclose(mrr([1, 2, None, 4]), (1 + 0.5 + 0 + 0.25) / 4)
    assert mrr([11, None], cutoff=10) == 0.0
    assert mrr([]) == 0.0


def test_summarize_reports_counts() -> None:
    summary = summarize([1, None, 2])
    assert summary == {
        "recall@1": 0.333,
        "recall@3": 0.667,
        "recall@5": 0.667,
        "mrr@10": 0.5,
        "n": 3.0,
    }


def test_false_accept_rate() -> None:
    assert false_accept_rate([0.1, 0.5, None, 0.3], 0.3) == 0.5
    assert false_accept_rate([], 0.3) == 0.0


def test_normalize() -> None:
    assert normalize("  A\tB \n C ") == "a b c"
