from __future__ import annotations

from typing import Any

import pytest

from app.services import widget_domains
from tests.integration.api.conftest import Actor, Api
from tests.integration.api.test_knowledge_documents import new_bot

pytestmark = pytest.mark.integration


def setup(api: Api) -> tuple[Actor, str, str, str]:
    actor = api.signup()
    bot = new_bot(actor)
    assert (
        actor.patch(f"/orgs/{actor.org_id}/chatbots/{bot}", {"status": "active"}).status_code == 200
    )
    key = actor.get(f"/orgs/{actor.org_id}/chatbots/{bot}").json()["public_key"]
    base = f"/orgs/{actor.org_id}/chatbots/{bot}"
    assert actor.post(base + "/domains", {"origin": "http://localhost:3000"}).status_code == 201
    domain = actor.get(base + "/widget-config").json()["domains"][0]["id"]
    assert actor.post(base + f"/domains/{domain}/verify").status_code == 200
    return actor, bot, key, domain


def boot(api: Api, key: str, **extra: Any) -> Any:
    return api.client.post(
        "/public/v1/widget/sessions",
        json={"key": key, "parent_origin": "http://localhost:3000", **extra},
    )


def test_frame_ownership_and_public_scope(api: Api) -> None:
    actor, bot, key, domain = setup(api)
    frame = api.client.get(
        f"/widget/frame/{key}",
        params={"parent_origin": "http://localhost:3000", "instance": "test"},
    )
    assert frame.status_code == 200
    assert "frame-ancestors http://localhost:3000" in frame.headers["content-security-policy"]
    assert "no-store" in frame.headers["cache-control"]
    assert (
        api.client.get(
            f"/widget/frame/{key}",
            params={"parent_origin": "https://evil.test", "instance": "test"},
        ).status_code
        == 403
    )
    issued = boot(api, key)
    assert issued.status_code == 200, issued.text
    token = issued.json()["token"]
    api.client.cookies.clear()
    assert (
        api.client.get(
            f"/api/v1/orgs/{actor.org_id}/chatbots/{bot}",
            headers={"Authorization": "Bearer " + token},
        ).status_code
        == 401
    )
    assert actor.delete(f"/orgs/{actor.org_id}/chatbots/{bot}/domains/{domain}").status_code == 204
    assert (
        api.client.get("/public/v1/chat", headers={"Authorization": "Bearer " + token}).status_code
        == 403
    )


def test_resumption_is_bound_to_origin_bot_and_expiry(api: Api) -> None:
    _, _, key, _ = setup(api)
    a = boot(api, key).json()
    assert (
        boot(
            api, key, parent_origin="https://evil.test", resume_token=a["resume_token"]
        ).status_code
        == 403
    )
    resumed = boot(api, key, resume_token=a["resume_token"]).json()
    assert resumed["resume_token"] == a["resume_token"] and resumed["token"] != a["token"]
    assert api.sql("SELECT count(*) FROM widget_sessions WHERE public_key=:key", key=key)[0][0] == 1
    _, _, other, _ = setup(api)
    fresh = boot(api, other, resume_token=a["resume_token"]).json()
    assert fresh["resume_token"] != a["resume_token"]
    api.sql("UPDATE widget_sessions SET resume_expires_at=now()-interval '1 day'")
    assert (
        boot(api, key, resume_token=a["resume_token"]).json()["resume_token"] != a["resume_token"]
    )


def test_dns_proof_and_failed_reverification_revokes(
    api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor, bot, _, _ = setup(api)
    base = f"/orgs/{actor.org_id}/chatbots/{bot}"
    actor.post(base + "/domains", {"origin": "https://www.business.test"})
    d = next(
        d
        for d in actor.get(base + "/widget-config").json()["domains"]
        if d["origin"].startswith("https:")
    )
    monkeypatch.setattr(widget_domains, "dns_proof", lambda _: [d["token"]])
    assert actor.post(base + f"/domains/{d['id']}/verify").status_code == 200
    monkeypatch.setattr(widget_domains, "dns_proof", lambda _: [])
    assert actor.post(base + f"/domains/{d['id']}/verify").status_code == 422
    assert (
        next(r for r in actor.get(base + "/widget-config").json()["domains"] if r["id"] == d["id"])[
            "verified_until"
        ]
        is None
    )


def test_tenant_origin_permissions_and_retention(api: Api) -> None:
    actor, bot, key, _ = setup(api)
    other = api.signup()
    base = f"/orgs/{actor.org_id}/chatbots/{bot}"
    assert other.get(base + "/widget-config").status_code == 404
    assert other.post(base + "/domains", {"origin": "https://evil.test"}).status_code == 404
    a = boot(api, key).json()
    assert actor.patch(base + "/widget-retention", {"days": 0}).status_code == 200
    fresh = boot(api, key, resume_token=a["resume_token"]).json()
    assert fresh["retention_days"] == 0 and fresh["resume_token"] != a["resume_token"]
    assert actor.post(base + "/domains", {"origin": "https://*.evil.test"}).status_code == 422
    assert (
        api.client.post(
            "/public/v1/widget/sessions",
            json={"key": key, "parent_origin": "http://localhost:3000", "admin": True},
        ).status_code
        == 422
    )
