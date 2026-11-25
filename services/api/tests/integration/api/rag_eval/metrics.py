"""Retrieval metrics. Pure functions, no I/O.

A retrieved chunk is *relevant* when it contains the question's gold answer phrase (chunk-level
labels survive changes to chunk size). ``rank`` is 1-based; ``None`` means nothing relevant was
retrieved within the cutoff.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

_SPACES = re.compile(r"\s+")


def normalize(text: str) -> str:
    return _SPACES.sub(" ", text.lower()).strip()


def first_relevant_rank(contents: Sequence[str], golds: Iterable[str]) -> int | None:
    """Rank (1-based) of the first chunk containing any gold phrase."""
    phrases = [normalize(g) for g in golds]
    for rank, content in enumerate(contents, start=1):
        body = normalize(content)
        if any(phrase in body for phrase in phrases):
            return rank
    return None


def recall_at_k(ranks: Sequence[int | None], k: int) -> float:
    """Share of questions with a relevant chunk in the top ``k``."""
    if not ranks:
        return 0.0
    return sum(1 for r in ranks if r is not None and r <= k) / len(ranks)


def mrr(ranks: Sequence[int | None], cutoff: int = 10) -> float:
    """Mean reciprocal rank (0 for a miss or a hit beyond ``cutoff``)."""
    if not ranks:
        return 0.0
    return sum(1.0 / r for r in ranks if r is not None and r <= cutoff) / len(ranks)


def summarize(ranks: Sequence[int | None], ks: Sequence[int] = (1, 3, 5)) -> dict[str, float]:
    result = {f"recall@{k}": round(recall_at_k(ranks, k), 3) for k in ks}
    result["mrr@10"] = round(mrr(ranks), 3)
    result["n"] = float(len(ranks))
    return result


def false_accept_rate(top_scores: Sequence[float | None], threshold: float) -> float:
    """Share of irrelevant questions for which anything scored at/above ``threshold``."""
    if not top_scores:
        return 0.0
    return sum(1 for s in top_scores if s is not None and s >= threshold) / len(top_scores)
