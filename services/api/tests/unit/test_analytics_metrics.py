from app.services.analytics_metrics import (
    cluster_key,
    grounded_rate,
    is_positive_csat,
    merge_cluster_keys,
    normalize_question,
    ratio,
    resolution_rate,
    retention_days,
    satisfaction_rate,
    thumbs_up_ratio,
    unanswered_rate,
)


def test_resolution_rate_excludes_open_and_does_not_treat_ai_replies_as_resolved() -> None:
    assert resolution_rate(resolved=2, unresolved=2, handed_off=1) == 0.4
    assert resolution_rate(resolved=0, unresolved=0, handed_off=0) is None
    # Ten conversations that the AI answered, but staff never closed them, is undefined — not 100%.
    assert resolution_rate(resolved=0, unresolved=0, handed_off=0) is None


def test_satisfaction_rate_uses_csat_not_message_thumbs() -> None:
    assert satisfaction_rate(positive=3, submitted=4) == 0.75
    assert satisfaction_rate(positive=0, submitted=0) is None
    assert is_positive_csat(4) is True
    assert is_positive_csat(3) is False


def test_grounded_and_thumbs_and_unanswered_are_separate() -> None:
    assert grounded_rate(grounded=8, ungrounded=2) == 0.8
    assert thumbs_up_ratio(up=9, down=1) == 0.9
    assert unanswered_rate(unanswered=3, user_messages=10) == 0.3
    assert ratio(1, 0) is None


def test_cluster_keys_group_near_paraphrases() -> None:
    assert normalize_question("Ship to Canada?") == "ship to canada"
    left = cluster_key("Can you ship to Canada?")
    right = cluster_key("Do you ship to Canada")
    merged = merge_cluster_keys([left, right, cluster_key("reset password")])
    assert merged[left] == merged[right]
    assert merged[left] != merged[cluster_key("reset password")]


def test_retention_days_default_and_bounds() -> None:
    assert retention_days({}) == 365
    assert retention_days({"conversation_retention_days": 30}) == 30
    assert retention_days({"conversation_retention_days": 0}) == 365
    assert retention_days({"conversation_retention_days": "90"}) == 90
