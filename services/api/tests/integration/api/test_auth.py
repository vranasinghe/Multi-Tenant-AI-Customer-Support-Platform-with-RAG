"""Registration, login, sessions, email verification and password recovery (HTTP level)."""

from __future__ import annotations

import uuid
from typing import Any, cast

import pytest
from httpx2 import Response
from redis import Redis

from tests.integration.api.conftest import COOKIE, ORIGIN, PASSWORD, Api, session_cookie

pytestmark = pytest.mark.integration


def _signup_body(email: str, **over: object) -> dict[str, object]:
    return {"email": email, "password": PASSWORD, "name": "Dana Lee", "org_name": "Acme", **over}


def _problem(response: Response) -> dict[str, Any]:
    assert response.headers["content-type"].startswith("application/problem+json")
    return cast("dict[str, Any]", response.json())


# --------------------------------------------------------------------------- signup


def test_signup_creates_user_org_owner_membership_and_session(api: Api) -> None:
    actor = api.anonymous()
    email = f"dana-{uuid.uuid4().hex[:8]}@example.com"

    response = actor.post("/auth/signup", _signup_body(email), cookie=None)

    assert response.status_code == 201
    body = response.json()
    assert body["user"]["email"] == email
    assert body["user"]["email_verified"] is False
    assert body["org"]["role"] == "owner"
    assert "password" not in response.text
    rows = api.sql(
        "SELECT m.role, o.name FROM memberships m JOIN organizations o ON o.id = m.org_id "
        "JOIN users u ON u.id = m.user_id WHERE u.email = :e",
        e=email,
    )
    assert [tuple(r) for r in rows] == [("owner", "Acme")]


def test_signup_session_cookie_has_protective_attributes(api: Api) -> None:
    actor = api.anonymous()

    response = actor.post(
        "/auth/signup", _signup_body(f"c-{uuid.uuid4().hex[:8]}@example.com"), cookie=None
    )

    header = next(h for h in response.headers.get_list("set-cookie") if h.startswith(COOKIE))
    lowered = header.lower()
    assert "httponly" in lowered
    assert "secure" in lowered
    assert "samesite=lax" in lowered
    assert "path=/" in lowered
    assert "domain" not in lowered  # __Host- prefix forbids Domain
    assert "max-age" in lowered


def test_signup_stores_argon2id_hash_and_hashed_tokens_only(api: Api) -> None:
    email = f"h-{uuid.uuid4().hex[:8]}@example.com"
    actor = api.anonymous()
    response = actor.post("/auth/signup", _signup_body(email), cookie=None)
    cookie = session_cookie(response)
    emailed = api.mailbox.last_token(email, path="verify-email")

    (password_hash,) = api.sql("SELECT password_hash FROM users WHERE email = :e", e=email)[0]
    session_hashes = api.sql("SELECT token_hash FROM sessions")
    token_hashes = api.sql("SELECT token_hash FROM email_tokens")

    assert password_hash.startswith("$argon2id$")
    assert PASSWORD not in password_hash
    flat = {bytes(r[0]) for r in (*session_hashes, *token_hashes)}
    assert cookie is not None
    assert cookie.encode() not in flat
    assert emailed.encode() not in flat
    assert all(len(h) == 32 for h in flat)


def test_signup_sends_verification_email(api: Api) -> None:
    email = f"v-{uuid.uuid4().hex[:8]}@example.com"

    api.anonymous().post("/auth/signup", _signup_body(email), cookie=None)

    assert len(api.mailbox.tokens(email, path="verify-email")) == 1


@pytest.mark.parametrize(
    "override",
    [
        {"password": "short"},
        {"password": "password123"},
        {"email": "not-an-email"},
        {"name": ""},
        {"org_name": ""},
        {"org_id": str(uuid.uuid4())},  # mass assignment: unknown fields are rejected
        {"role": "owner"},
    ],
)
def test_signup_rejects_invalid_or_unexpected_input(api: Api, override: dict[str, object]) -> None:
    body = _signup_body(f"i-{uuid.uuid4().hex[:8]}@example.com") | override

    response = api.anonymous().post("/auth/signup", body, cookie=None)

    assert response.status_code == 422
    assert _problem(response)["code"] == "validation_error"


def test_signup_rejects_password_containing_email_local_part(api: Api) -> None:
    response = api.anonymous().post(
        "/auth/signup",
        _signup_body("johnsmith@example.com", password="johnsmith-is-great"),
        cookie=None,
    )

    assert response.status_code == 422


def test_signup_with_existing_email_looks_identical_and_creates_nothing(api: Api) -> None:
    existing = api.signup()
    before = api.sql("SELECT count(*) FROM users")[0][0]

    response = api.anonymous().post("/auth/signup", _signup_body(existing.email), cookie=None)

    assert response.status_code == 201
    assert set(response.json()) == {"user", "org"}
    assert session_cookie(response) is None  # no session for someone else's account
    assert api.sql("SELECT count(*) FROM users")[0][0] == before
    assert any("tried to sign up" in m.subject.lower() for m in api.mailbox.to(existing.email))


def test_signup_email_is_case_insensitive(api: Api) -> None:
    existing = api.signup(email=f"Case-{uuid.uuid4().hex[:6]}@Example.com")
    before = api.sql("SELECT count(*) FROM users")[0][0]

    api.anonymous().post("/auth/signup", _signup_body(existing.email.upper()), cookie=None)

    assert api.sql("SELECT count(*) FROM users")[0][0] == before


# ---------------------------------------------------------------------------- login


def test_login_succeeds_and_lists_orgs(api: Api) -> None:
    user = api.signup()

    response = user.login()

    assert response.status_code == 200
    assert response.json()["orgs"][0]["role"] == "owner"
    assert session_cookie(response) is not None
    assert user.get("/me").status_code == 200


def test_login_unknown_email_and_wrong_password_are_indistinguishable(api: Api) -> None:
    user = api.signup()
    anon = api.anonymous()

    wrong_pw = anon.post("/auth/login", {"email": user.email, "password": "wrong password!!"})
    unknown = anon.post(
        "/auth/login", {"email": "nobody@example.com", "password": "wrong password!!"}
    )

    assert wrong_pw.status_code == unknown.status_code == 401
    a, b = _problem(wrong_pw), _problem(unknown)
    a.pop("request_id"), b.pop("request_id")
    assert a == b
    assert a["code"] == "invalid_credentials"
    assert session_cookie(wrong_pw) is None


def test_disabled_user_cannot_log_in_and_looks_like_bad_credentials(api: Api) -> None:
    user = api.signup()
    api.sql("UPDATE users SET status = 'disabled' WHERE email = :e", e=user.email)

    response = user.login()

    assert response.status_code == 401
    assert _problem(response)["code"] == "invalid_credentials"


def test_sixth_failed_login_in_a_minute_is_rate_limited(api: Api) -> None:
    user = api.signup()
    anon = api.anonymous()

    statuses = [
        anon.post("/auth/login", {"email": user.email, "password": "wrong password!!"}).status_code
        for _ in range(5)
    ]
    sixth = anon.post("/auth/login", {"email": user.email, "password": "wrong password!!"})

    assert statuses == [401] * 5
    assert sixth.status_code == 429
    assert int(sixth.headers["retry-after"]) > 0
    assert _problem(sixth)["code"] == "rate_limited"


def test_locked_account_rejects_even_the_correct_password(api: Api) -> None:
    user = api.signup()
    for _ in range(5):
        api.anonymous().post("/auth/login", {"email": user.email, "password": "wrong password!!"})

    assert user.login().status_code == 429


def test_rate_limiting_applies_to_unknown_emails_too(api: Api) -> None:
    anon = api.anonymous()
    for _ in range(5):
        anon.post("/auth/login", {"email": "ghost@example.com", "password": "wrong password!!"})

    assert (
        anon.post("/auth/login", {"email": "ghost@example.com", "password": "x"}).status_code == 429
    )


def test_login_rotates_session_and_revokes_the_presented_one(api: Api) -> None:
    user = api.signup()
    old_cookie = user.cookie

    response = user.login()
    new_cookie = session_cookie(response)

    assert new_cookie
    assert new_cookie != old_cookie
    assert user.get("/me", cookie=old_cookie).status_code == 401  # fixation defence


# --------------------------------------------------------------------- sessions


def test_protected_endpoints_require_a_valid_session(api: Api) -> None:
    anon = api.anonymous()

    assert anon.get("/me", cookie=None).status_code == 401
    assert anon.get("/me", cookie="not-a-real-token").status_code == 401
    assert _problem(anon.get("/me", cookie=None))["code"] == "unauthenticated"


def test_logout_revokes_the_session_server_side(api: Api) -> None:
    user = api.signup()
    stolen = user.cookie

    response = user.post("/auth/logout")

    assert response.status_code == 204
    cleared = next(h for h in response.headers.get_list("set-cookie") if h.startswith(COOKIE))
    assert "max-age=0" in cleared.lower() or "expires=" in cleared.lower()
    assert user.get("/me", cookie=stolen).status_code == 401  # AC1.2
    assert (
        api.sql(
            "SELECT count(*) FROM sessions WHERE revoked_at IS NULL AND user_id = :u",
            u=user.user_id,
        )[0][0]
        == 0
    )


def test_expired_session_is_rejected(api: Api) -> None:
    user = api.signup()
    api.sql("UPDATE sessions SET expires_at = now() - interval '1 minute'")

    assert user.get("/me").status_code == 401


def test_idle_session_is_rejected(api: Api) -> None:
    user = api.signup()
    api.sql("UPDATE sessions SET last_seen_at = now() - interval '15 days'")

    assert user.get("/me").status_code == 401


def test_disabling_user_blocks_existing_sessions_immediately(api: Api) -> None:
    user = api.signup()
    api.sql("UPDATE users SET status = 'disabled' WHERE email = :e", e=user.email)

    assert user.get("/me").status_code == 401


def test_list_and_revoke_other_sessions(api: Api) -> None:
    user = api.signup()
    user.login()  # rotates; creates exactly one live session
    other = user.post("/auth/login", {"email": user.email, "password": PASSWORD}, cookie=None)
    other_cookie = session_cookie(other)

    listing = user.get("/me/sessions").json()["data"]
    revoke = user.delete("/me/sessions")  # everyone but the current one

    assert len(listing) >= 2
    assert sum(1 for s in listing if s["current"]) == 1
    assert revoke.status_code == 204
    assert user.get("/me", cookie=other_cookie).status_code == 401
    assert user.get("/me").status_code == 200


def test_user_cannot_revoke_someone_elses_session(api: Api) -> None:
    alice, bob = api.signup(), api.signup()
    (alice_session,) = api.sql("SELECT s.id FROM sessions s WHERE s.user_id = :u", u=alice.user_id)[
        0
    ]

    response = bob.delete(f"/me/sessions/{alice_session}")

    assert response.status_code == 404
    assert alice.get("/me").status_code == 200


# --------------------------------------------------------------------- verification


def test_unverified_user_cannot_create_org_until_verified(api: Api) -> None:
    user = api.signup(verified=False)

    blocked = user.post("/orgs", {"name": "Second"})
    api.verify_email(user)
    allowed = user.post("/orgs", {"name": "Second"})

    assert blocked.status_code == 403
    assert _problem(blocked)["code"] == "email_not_verified"
    assert allowed.status_code == 201


def test_verification_token_works_once(api: Api) -> None:
    user = api.signup(verified=False)
    token = api.mailbox.last_token(user.email, path="verify-email")

    first = user.post("/auth/verify-email", {"token": token}, cookie=None)
    second = user.post("/auth/verify-email", {"token": token}, cookie=None)

    assert first.status_code == 200
    assert second.status_code == 400
    assert _problem(second)["code"] == "invalid_token"


def test_expired_verification_token_is_rejected(api: Api) -> None:
    user = api.signup(verified=False)
    token = api.mailbox.last_token(user.email, path="verify-email")
    api.sql("UPDATE email_tokens SET expires_at = now() - interval '1 second'")

    assert user.post("/auth/verify-email", {"token": token}, cookie=None).status_code == 400


def test_garbage_verification_token_is_rejected(api: Api) -> None:
    assert api.anonymous().post("/auth/verify-email", {"token": "x" * 43}).status_code == 400


def test_resend_verification_invalidates_the_previous_link(api: Api) -> None:
    user = api.signup(verified=False)
    first = api.mailbox.last_token(user.email, path="verify-email")

    assert user.post("/auth/resend-verification").status_code == 202
    second = api.mailbox.last_token(user.email, path="verify-email")

    assert first != second
    assert user.post("/auth/verify-email", {"token": first}, cookie=None).status_code == 400
    assert user.post("/auth/verify-email", {"token": second}, cookie=None).status_code == 200


def test_resend_verification_is_rate_limited_per_hour(api: Api) -> None:
    user = api.signup(verified=False)

    codes = [user.post("/auth/resend-verification").status_code for _ in range(4)]

    assert codes == [202, 202, 202, 429]


# ------------------------------------------------------------------ password reset


def test_forgot_password_response_is_identical_for_known_and_unknown_emails(api: Api) -> None:
    user = api.signup()
    anon = api.anonymous()

    known = anon.post("/auth/forgot-password", {"email": user.email})
    unknown = anon.post("/auth/forgot-password", {"email": "nobody@example.com"})

    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert len(api.mailbox.tokens(user.email, path="reset-password")) == 1
    assert api.mailbox.to("nobody@example.com") == []


def test_forgot_password_is_rate_limited_per_email(api: Api) -> None:
    user = api.signup()
    anon = api.anonymous()

    codes = [
        anon.post("/auth/forgot-password", {"email": user.email}).status_code for _ in range(4)
    ]

    assert codes == [202, 202, 202, 429]


def test_reset_password_token_works_once_and_revokes_all_sessions(api: Api) -> None:
    user = api.signup()
    old_cookie = user.cookie
    api.anonymous().post("/auth/forgot-password", {"email": user.email})
    token = api.mailbox.last_token(user.email, path="reset-password")
    new_password = "a brand new passphrase"

    first = api.anonymous().post("/auth/reset-password", {"token": token, "password": new_password})
    second = api.anonymous().post(
        "/auth/reset-password", {"token": token, "password": "another passphrase!"}
    )

    assert first.status_code == 200
    assert second.status_code == 400  # AC1.3: single use
    assert _problem(second)["code"] == "invalid_token"
    assert user.get("/me", cookie=old_cookie).status_code == 401
    assert user.login().status_code == 401  # old password gone
    assert user.login(new_password).status_code == 200


def test_expired_reset_token_is_rejected(api: Api) -> None:
    user = api.signup()
    api.anonymous().post("/auth/forgot-password", {"email": user.email})
    token = api.mailbox.last_token(user.email, path="reset-password")
    api.sql("UPDATE email_tokens SET expires_at = now() - interval '1 second'")

    response = api.anonymous().post(
        "/auth/reset-password", {"token": token, "password": "a brand new passphrase"}
    )

    assert response.status_code == 400


def test_reset_token_expires_after_30_minutes(api: Api) -> None:
    user = api.signup()
    api.anonymous().post("/auth/forgot-password", {"email": user.email})

    (minutes,) = api.sql(
        "SELECT round(extract(epoch FROM expires_at - created_at) / 60) FROM email_tokens "
        "WHERE purpose = 'reset_password' AND user_id = :u",
        u=user.user_id,
    )[0]

    assert minutes == 30


def test_a_newer_reset_request_invalidates_older_links(api: Api) -> None:
    user = api.signup()
    anon = api.anonymous()
    anon.post("/auth/forgot-password", {"email": user.email})
    old = api.mailbox.last_token(user.email, path="reset-password")
    anon.post("/auth/forgot-password", {"email": user.email})

    response = anon.post(
        "/auth/reset-password", {"token": old, "password": "a brand new passphrase"}
    )

    assert response.status_code == 400


def test_verification_token_cannot_be_used_to_reset_a_password(api: Api) -> None:
    user = api.signup(verified=False)
    token = api.mailbox.last_token(user.email, path="verify-email")

    response = api.anonymous().post(
        "/auth/reset-password", {"token": token, "password": "a brand new passphrase"}
    )

    assert response.status_code == 400
    assert user.login(PASSWORD).status_code == 200


def test_reset_enforces_password_policy_without_consuming_the_token(api: Api) -> None:
    user = api.signup()
    api.anonymous().post("/auth/forgot-password", {"email": user.email})
    token = api.mailbox.last_token(user.email, path="reset-password")

    weak = api.anonymous().post("/auth/reset-password", {"token": token, "password": "short"})
    ok = api.anonymous().post(
        "/auth/reset-password", {"token": token, "password": "a brand new passphrase"}
    )

    assert weak.status_code == 422
    assert ok.status_code == 200


def test_reset_clears_a_login_lockout(api: Api, redis_client: Redis) -> None:
    user = api.signup()
    for _ in range(5):
        api.anonymous().post("/auth/login", {"email": user.email, "password": "wrong password!!"})
    api.anonymous().post("/auth/forgot-password", {"email": user.email})
    token = api.mailbox.last_token(user.email, path="reset-password")

    api.anonymous().post(
        "/auth/reset-password", {"token": token, "password": "a brand new passphrase"}
    )

    # Lockout (not the per-minute counter, which simply ages out) must be gone.
    assert redis_client.keys("login_lock:*") == []
    for key in redis_client.keys("rl:login_email_min:*"):
        redis_client.delete(key)
    assert user.login("a brand new passphrase").status_code == 200


def test_change_password_requires_current_password_and_revokes_other_sessions(api: Api) -> None:
    user = api.signup()
    other = session_cookie(
        user.post("/auth/login", {"email": user.email, "password": PASSWORD}, cookie=None)
    )

    wrong = user.post(
        "/me/password",
        {"current_password": "nope nope nope", "new_password": "a brand new passphrase"},
    )
    ok = user.post(
        "/me/password", {"current_password": PASSWORD, "new_password": "a brand new passphrase"}
    )

    assert wrong.status_code == 400
    assert ok.status_code == 204
    assert user.get("/me", cookie=other).status_code == 401
    fresh = session_cookie(ok)
    assert fresh
    assert user.get("/me", cookie=fresh).status_code == 200


# ------------------------------------------------------------------------ CSRF


@pytest.mark.parametrize("path", ["/auth/login", "/auth/logout", "/orgs"])
def test_state_changing_request_without_custom_header_is_forbidden(api: Api, path: str) -> None:
    user = api.signup()

    response = user.post(path, {"email": user.email, "password": PASSWORD, "name": "x"}, csrf=False)

    assert response.status_code == 403
    assert _problem(response)["code"] == "csrf_check_failed"


def test_state_changing_request_with_foreign_origin_is_forbidden(api: Api) -> None:
    user = api.signup()

    response = user.post("/auth/logout", headers={"Origin": "https://evil.example"})

    assert response.status_code == 403
    assert _problem(response)["code"] == "origin_not_allowed"
    assert user.get("/me").status_code == 200  # session untouched


def test_safe_methods_do_not_need_the_csrf_header(api: Api) -> None:
    user = api.signup()

    assert user.get("/me", csrf=False).status_code == 200


def test_cors_preflight_allows_only_configured_origin(api: Api) -> None:
    allowed = api.client.options(
        "/api/v1/auth/login",
        headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST"},
    )
    denied = api.client.options(
        "/api/v1/auth/login",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )

    assert allowed.headers["access-control-allow-origin"] == ORIGIN
    assert allowed.headers["access-control-allow-credentials"] == "true"
    assert "access-control-allow-origin" not in denied.headers
