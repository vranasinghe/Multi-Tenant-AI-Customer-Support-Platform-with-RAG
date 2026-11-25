"""Logs must never carry secrets or PII (docs/SECURITY.md §14): no passwords, tokens, session
cookies, raw emails or password hashes — user ids only."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.core.config import Settings
from app.main import create_app
from tests.integration.api.conftest import Api
from tests.support.email import Mailbox

pytestmark = pytest.mark.integration


def test_auth_flows_do_not_log_secrets_or_emails(
    api_settings: Settings,
    mailbox: Mailbox,
    owner_engine: Engine,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = api_settings.model_copy(update={"log_level": "DEBUG", "log_format": "json"})
    email = f"hygiene-{uuid.uuid4().hex[:8]}@example.com"
    password = "a very distinctive passphrase 8841"
    new_password = "another very distinctive passphrase 7720"
    with TestClient(
        create_app(settings, email_sender=mailbox), base_url="https://testserver"
    ) as client:
        api = Api(client=client, mailbox=mailbox, owner_engine=owner_engine)
        actor = api.anonymous()
        actor.email = email
        signup = actor.post(
            "/auth/signup",
            {"email": email, "password": password, "name": "Hygiene", "org_name": "Hygiene Org"},
            cookie=None,
        )
        cookie = signup.headers["set-cookie"].split(";")[0].split("=", 1)[1]
        actor.post("/auth/login", {"email": email, "password": "wrong wrong wrong"}, cookie=None)
        actor.post("/auth/forgot-password", {"email": email}, cookie=None)
        reset_token = mailbox.last_token(email, path="reset-password")
        verify_token = mailbox.last_token(email, path="verify-email")
        actor.post(
            "/auth/reset-password", {"token": reset_token, "password": new_password}, cookie=None
        )
        actor.get("/me", cookie=cookie)

    output = capsys.readouterr()
    logs = output.out + output.err
    assert logs, "expected captured log output"
    for secret in (password, new_password, cookie, reset_token, verify_token, email):
        assert secret not in logs
    assert "argon2" not in logs
