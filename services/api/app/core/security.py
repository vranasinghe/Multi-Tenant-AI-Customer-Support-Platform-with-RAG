"""Credential primitives: opaque tokens, password hashing and password policy.

docs/SECURITY.md §3: Argon2id (OWASP baseline m=19 MiB, t=2, p=1), 256-bit random tokens stored
only as SHA-256 hashes, enumeration-resistant verification (dummy hash for unknown users).
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

TOKEN_BYTES = 32
PASSWORD_MIN_LENGTH = 10
PASSWORD_MAX_LENGTH = 128

# Small offline blocklist; a breach-corpus (HIBP k-anonymity) check can be layered on later.
_COMMON_PASSWORDS = frozenset(
    {
        "password",
        "password1",
        "password12",
        "password123",
        "password1234",
        "passw0rd123",
        "1234567890",
        "12345678910",
        "123456789012",
        "qwertyuiop",
        "qwerty12345",
        "qwerty123456",
        "iloveyou123",
        "letmein1234",
        "welcome1234",
        "administrator",
        "abcdefghij",
        "abc1234567",
        "1q2w3e4r5t",
        "changeme123",
    }
)


def new_token() -> str:
    """A fresh 256-bit URL-safe secret. Only its hash is ever stored."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> bytes:
    """SHA-256 of a high-entropy token (a slow hash is unnecessary for 256-bit secrets)."""
    return hashlib.sha256(token.encode("utf-8")).digest()


class PasswordPolicyError(ValueError):
    """The candidate password does not satisfy the policy (message is user-safe)."""


def validate_password_policy(password: str, *, email: str) -> None:
    if len(password) < PASSWORD_MIN_LENGTH:
        msg = f"Password must be at least {PASSWORD_MIN_LENGTH} characters."
        raise PasswordPolicyError(msg)
    if len(password) > PASSWORD_MAX_LENGTH:
        msg = f"Password must be at most {PASSWORD_MAX_LENGTH} characters."
        raise PasswordPolicyError(msg)
    lowered = password.lower()
    if lowered in _COMMON_PASSWORDS:
        msg = "That password is too common."
        raise PasswordPolicyError(msg)
    local_part = email.split("@", 1)[0].lower()
    if len(local_part) >= 3 and local_part in lowered:
        msg = "Password must not contain your email address."
        raise PasswordPolicyError(msg)


class PasswordService:
    """Argon2id hashing off the event loop; constant-work verification for unknown users."""

    def __init__(
        self, *, memory_kib: int = 19456, time_cost: int = 2, parallelism: int = 1
    ) -> None:
        self._hasher = PasswordHasher(
            memory_cost=memory_kib, time_cost=time_cost, parallelism=parallelism
        )
        # Verified when the account does not exist, so timing doesn't reveal existence.
        self._dummy_hash = self._hasher.hash(secrets.token_urlsafe(16))

    async def hash(self, password: str) -> str:
        return await asyncio.to_thread(self._hasher.hash, password)

    async def verify(self, password_hash: str | None, password: str) -> bool:
        return await asyncio.to_thread(self._verify_sync, password_hash, password)

    def _verify_sync(self, password_hash: str | None, password: str) -> bool:
        if password_hash is None:
            with contextlib.suppress(VerificationError):
                self._hasher.verify(self._dummy_hash, password)
            return False
        try:
            return self._hasher.verify(password_hash, password)
        except (VerificationError, InvalidHashError):
            return False

    def needs_rehash(self, password_hash: str) -> bool:
        return self._hasher.check_needs_rehash(password_hash)
