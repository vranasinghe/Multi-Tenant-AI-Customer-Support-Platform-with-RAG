"""Pure metric definitions. Rates are never inferred from “the AI answered”.

See docs/analytics-metrics.md. These functions are the source of truth for tests and rollups.
"""

from __future__ import annotations

import re
from typing import Final

DEFAULT_RETENTION_DAYS: Final[int] = 365
MIN_RETENTION_DAYS: Final[int] = 1
MAX_RETENTION_DAYS: Final[int] = 730
POSITIVE_CSAT_MIN: Final[int] = 4
PRODUCTION_CHANNELS: Final[frozenset[str]] = frozenset({"widget"})
PLAYGROUND_CHANNEL: Final[str] = "playground"

_NON_ALNUM = re.compile(r"[^a-z0-9\s]+")
_WS = re.compile(r"\s+")
STOPWORDS: Final[frozenset[str]] = frozenset(
    {
        "a",
        "an",
        "the",
        "to",
        "for",
        "of",
        "and",
        "or",
        "is",
        "are",
        "do",
        "does",
        "did",
        "can",
        "you",
        "your",
        "me",
        "my",
        "we",
        "our",
        "please",
        "how",
        "what",
        "when",
        "where",
        "why",
        "which",
        "i",
        "in",
        "on",
        "at",
        "with",
    }
)


def ratio(numerator: int, denominator: int) -> float | None:
    """Return numerator/denominator, or None when the rate is undefined."""
    if denominator <= 0:
        return None
    return numerator / denominator


def resolution_rate(*, resolved: int, unresolved: int, handed_off: int) -> float | None:
    """Share of *closed* conversations that staff marked resolved.

    Open conversations are excluded. An assistant reply does not count as resolved.
    """
    return ratio(resolved, resolved + unresolved + handed_off)


def satisfaction_rate(*, positive: int, submitted: int) -> float | None:
    """Share of CSAT submissions scored 4 or 5. Message thumbs are a different metric."""
    return ratio(positive, submitted)


def is_positive_csat(score: int) -> bool:
    return score >= POSITIVE_CSAT_MIN


def grounded_rate(*, grounded: int, ungrounded: int) -> float | None:
    """Share of finished assistant replies that included at least one citation snapshot."""
    return ratio(grounded, grounded + ungrounded)


def thumbs_up_ratio(*, up: int, down: int) -> float | None:
    """Share of thumbs that are up, among messages that have thumbs. Unrated replies excluded."""
    return ratio(up, up + down)


def unanswered_rate(*, unanswered: int, user_messages: int) -> float | None:
    """Unanswered events per customer question. Not 1 - grounded_rate."""
    return ratio(unanswered, user_messages)


def normalize_question(text: str) -> str:
    cleaned = _NON_ALNUM.sub(" ", text.casefold())
    return _WS.sub(" ", cleaned).strip()


def cluster_key(text: str) -> str:
    """Stable grouping key: significant tokens, sorted.

    Paraphrases share a key when tokens overlap.
    """
    tokens = [
        token
        for token in normalize_question(text).split()
        if token not in STOPWORDS and len(token) > 1
    ]
    if not tokens:
        return normalize_question(text)
    return " ".join(sorted(set(tokens)))


def jaccard(left: str, right: str) -> float:
    a, b = set(left.split()), set(right.split())
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def merge_cluster_keys(keys: list[str], *, threshold: float = 0.6) -> dict[str, str]:
    """Map each key to a canonical representative when token Jaccard ≥ threshold."""
    unique = list(dict.fromkeys(keys))
    parent = {key: key for key in unique}

    def find(item: str) -> str:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    for i, left in enumerate(unique):
        for right in unique[i + 1 :]:
            if jaccard(left, right) >= threshold:
                a, b = find(left), find(right)
                if a != b:
                    parent[b] = a
    return {key: find(key) for key in unique}


def retention_days(settings: dict[str, object] | None) -> int:
    raw = (settings or {}).get("conversation_retention_days")
    if isinstance(raw, int) and MIN_RETENTION_DAYS <= raw <= MAX_RETENTION_DAYS:
        return raw
    if isinstance(raw, str) and raw.isdigit():
        value = int(raw)
        if MIN_RETENTION_DAYS <= value <= MAX_RETENTION_DAYS:
            return value
    return DEFAULT_RETENTION_DAYS
