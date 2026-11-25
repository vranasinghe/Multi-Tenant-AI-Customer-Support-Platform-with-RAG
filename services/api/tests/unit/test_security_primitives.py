"""Token and password primitives (docs/SECURITY.md §3)."""

from __future__ import annotations

import pytest

from app.core.security import (
    PasswordPolicyError,
    PasswordService,
    hash_token,
    new_token,
    validate_password_policy,
)


def test_tokens_are_256_bit_and_unique() -> None:
    first, second = new_token(), new_token()

    assert first != second
    assert len(first) >= 43  # 32 random bytes, urlsafe base64 without padding


def test_hash_token_is_deterministic_sha256_bytes() -> None:
    digest = hash_token("abc")

    assert isinstance(digest, bytes)
    assert len(digest) == 32
    assert digest == hash_token("abc")
    assert digest != hash_token("abd")


@pytest.mark.parametrize(
    ("password", "email", "reason"),
    [
        ("short", "a@example.com", "at least 10"),
        ("x" * 129, "a@example.com", "at most 128"),
        ("password123", "a@example.com", "too common"),
        ("alicewonderland1", "alice@example.com", "email"),
    ],
)
def test_password_policy_rejects(password: str, email: str, reason: str) -> None:
    with pytest.raises(PasswordPolicyError, match=reason):
        validate_password_policy(password, email=email)


def test_password_policy_accepts_long_passphrase_without_composition_rules() -> None:
    validate_password_policy("correct horse battery staple", email="alice@example.com")


async def test_password_hash_verify_roundtrip_uses_argon2id() -> None:
    service = PasswordService(memory_kib=8, time_cost=1, parallelism=1)

    hashed = await service.hash("a long passphrase here")

    assert hashed.startswith("$argon2id$")
    assert await service.verify(hashed, "a long passphrase here") is True
    assert await service.verify(hashed, "wrong passphrase!!") is False


async def test_verify_against_unknown_user_burns_time_and_returns_false() -> None:
    service = PasswordService(memory_kib=8, time_cost=1, parallelism=1)

    assert await service.verify(None, "anything at all") is False


async def test_needs_rehash_when_parameters_change() -> None:
    old = PasswordService(memory_kib=8, time_cost=1, parallelism=1)
    new = PasswordService(memory_kib=16, time_cost=2, parallelism=1)
    hashed = await old.hash("a long passphrase here")

    assert new.needs_rehash(hashed) is True
    assert old.needs_rehash(hashed) is False
