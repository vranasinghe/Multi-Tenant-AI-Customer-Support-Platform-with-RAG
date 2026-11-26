"""Inbox, first-class conversation events, analytics, CSV export and retention."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import Settings
from tests.integration.api.conftest import Actor, Api
from tests.integration.api.test_conversations import conversation, done, send
from tests.integration.api.test_knowledge_documents import new_bot
from tests.integration.api.test_widget import boot
from tests.integration.api.test_widget import setup as widget_setup

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def enable_chat(api_settings: Settings) -> None:
    api_settings.llm_provider = "demo"


def _invite(api: Api, owner: Actor, role: str) -> Actor:
    member = api.signup(verified=True)
    owner.post(f"/orgs/{owner.org_id}/invitations", {"email": member.email, "role": role})
    token = api.mailbox.last_token(member.email, path="invite")
    assert member.post("/invitations/accept", {"token": token}).status_code == 200
    return member


def _mark_widget(api: Api, conversation_id: str) -> None:
    api.sql("UPDATE conversations SET channel = 'widget' WHERE id = :id", id=conversation_id)


def test_inbox_search_filters_pagination_and_detail(api: Api) -> None:
    actor = api.signup()
    bot = new_bot(actor)
    first = conversation(actor, bot)
    done(send(actor, first, "What is the returns policy?"))
    second = conversation(actor, bot)
    done(send(actor, second, "Shipping to Canada?"))
    listed = actor.get(f"/orgs/{actor.org_id}/conversations?limit=1")
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["total"] == 2 and body["has_more"] is True and len(body["data"]) == 1
    more = actor.get(f"/orgs/{actor.org_id}/conversations?limit=1&cursor={body['next_cursor']}")
    assert more.status_code == 200
    assert more.json()["data"][0]["id"] != body["data"][0]["id"]
    found = actor.get(f"/orgs/{actor.org_id}/conversations?q=Canada")
    assert found.json()["total"] == 1
    assert "Canada" in found.json()["data"][0]["preview"]
    detail = actor.get(f"/orgs/{actor.org_id}/conversations/{second}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "open"
    assert len(detail.json()["messages"]) == 2


def test_status_handoff_satisfaction_are_persisted_events_not_inferred(api: Api) -> None:
    actor = api.signup()
    bot = new_bot(actor)
    conv = conversation(actor, bot)
    done(send(actor, conv, "What is the returns policy?"))
    _mark_widget(api, conv)
    summary = actor.get(f"/orgs/{actor.org_id}/analytics/summary").json()
    # An AI answer does not count as resolved.
    assert summary["conversations"] == 1
    assert summary["resolved"] == 0
    assert summary["open"] == 1
    assert summary["resolution_rate"] is None
    assert (
        actor.patch(
            f"/orgs/{actor.org_id}/conversations/{conv}", {"status": "resolved"}
        ).status_code
        == 200
    )
    csat = actor.put(f"/orgs/{actor.org_id}/conversations/{conv}/satisfaction", {"score": 5})
    assert csat.status_code == 200
    handoff = actor.post(
        f"/orgs/{actor.org_id}/conversations/{conv}/handoff",
        {"reason": "Customer asked for a person"},
    )
    assert handoff.status_code == 201
    detail = actor.get(f"/orgs/{actor.org_id}/conversations/{conv}").json()
    assert detail["status"] == "handed_off"
    assert detail["satisfaction_score"] == 5
    kinds = {event["kind"] for event in detail["events"]}
    assert {"status_changed", "satisfaction_submitted", "handoff_requested"} <= kinds
    events = api.sql(
        "SELECT kind FROM conversation_events WHERE org_id=:org AND conversation_id=:id",
        org=actor.org_id,
        id=conv,
    )
    assert {row[0] for row in events} >= kinds


def test_unanswered_is_recorded_on_fallback_and_groups_knowledge_gaps(api: Api) -> None:
    actor, _bot, key, _domain = widget_setup(api)
    issued = boot(api, key)
    assert issued.status_code == 200, issued.text
    token = issued.json()["token"]
    response = api.client.post(
        "/public/v1/chat/messages",
        json={"content": "Explain astrophysics quasars galaxies?"},
        headers={"Authorization": f"Bearer {token}"},
    )
    done(response)
    unanswered = actor.get(f"/orgs/{actor.org_id}/unanswered").json()["data"]
    assert unanswered
    assert unanswered[0]["count"] >= 1
    gaps = actor.get(f"/orgs/{actor.org_id}/knowledge-gaps").json()["data"]
    assert gaps[0]["representative"]
    row = api.sql("SELECT reason FROM unanswered_questions WHERE org_id=:org", org=actor.org_id)
    assert row[0][0] == "insufficient_evidence"


def test_analytics_excludes_playground_includes_usage_and_is_tenant_scoped(
    api: Api,
) -> None:
    owner = api.signup()
    bot = new_bot(owner)
    playground = conversation(owner, bot)
    done(send(owner, playground, "Explain astrophysics quasars galaxies?"))
    widget = conversation(owner, bot)
    done(send(owner, widget, "Widget question"))
    _mark_widget(api, widget)
    # Fallback turns do not charge tokens; usage still exists as settled zero-cost rows.
    other = api.signup()
    other_bot = new_bot(other)
    other_conv = conversation(other, other_bot)
    done(send(other, other_conv, "Other tenant"))
    _mark_widget(api, other_conv)

    mine = owner.get(f"/orgs/{owner.org_id}/analytics/summary").json()
    theirs = other.get(f"/orgs/{other.org_id}/analytics/summary").json()
    assert mine["conversations"] == 1
    assert mine["unanswered"] == 0
    assert theirs["conversations"] == 1
    assert owner.get(f"/orgs/{owner.org_id}/conversations?channel=playground").json()["total"] == 1
    foreign = owner.get(f"/orgs/{other.org_id}/analytics/summary")
    assert foreign.status_code == 404
    daily = owner.get(
        f"/orgs/{owner.org_id}/analytics/timeseries?metric=conversations&interval=day"
    )
    assert daily.status_code == 200
    assert sum(point["value"] for point in daily.json()["points"]) == 1
    monthly = owner.get(
        f"/orgs/{owner.org_id}/analytics/timeseries?metric=conversations&interval=month"
    )
    assert monthly.status_code == 200
    tokens = owner.get(f"/orgs/{owner.org_id}/analytics/timeseries?metric=tokens&interval=day")
    assert tokens.status_code == 200


def test_csv_export_requires_export_permission_and_stays_on_tenant(api: Api) -> None:
    owner = api.signup()
    bot = new_bot(owner)
    conv = conversation(owner, bot)
    done(send(owner, conv, "Export me"))
    viewer = _invite(api, owner, "viewer")
    agent = _invite(api, owner, "agent")
    created = owner.post(f"/orgs/{owner.org_id}/conversations/exports", {})
    assert created.status_code == 201, created.text
    export_id = created.json()["id"]
    download = owner.get(f"/orgs/{owner.org_id}/exports/{export_id}/download")
    assert download.status_code == 200
    assert "text/csv" in download.headers["content-type"]
    assert conv in download.text
    assert viewer.post(f"/orgs/{owner.org_id}/conversations/exports", {}).status_code == 403
    assert agent.post(f"/orgs/{owner.org_id}/conversations/exports", {}).status_code == 403
    other = api.signup()
    assert other.get(f"/orgs/{owner.org_id}/exports/{export_id}/download").status_code == 404
    assert owner.get(f"/orgs/{other.org_id}/exports/{export_id}/download").status_code == 404
    assert other.get(f"/orgs/{other.org_id}/exports/{export_id}").status_code == 404


def test_delete_keeps_usage_and_retention_is_org_scoped(api: Api) -> None:
    actor = api.signup()
    bot = new_bot(actor)
    conv = conversation(actor, bot)
    done(send(actor, conv, "Delete later"))
    usage_before = api.sql("SELECT count(*) FROM chat_usage WHERE org_id=:org", org=actor.org_id)[
        0
    ][0]
    assert actor.delete(f"/orgs/{actor.org_id}/conversations/{conv}").status_code == 204
    assert actor.get(f"/orgs/{actor.org_id}/conversations/{conv}").status_code == 404
    usage_after = api.sql("SELECT count(*) FROM chat_usage WHERE org_id=:org", org=actor.org_id)[0][
        0
    ]
    assert usage_after == usage_before

    keep = conversation(actor, bot)
    old = conversation(actor, bot)
    api.sql(
        "UPDATE conversations SET last_message_at = :ts WHERE id = :id",
        ts=datetime.now(UTC) - timedelta(days=400),
        id=old,
    )
    retention = actor.get(f"/orgs/{actor.org_id}/conversation-retention")
    assert retention.status_code == 200
    assert retention.json()["conversation_retention_days"] == 365

    from app.services.retention import purge_org

    async def run() -> int:
        async with api.client.app.state.services.session_factory() as db:  # type: ignore[attr-defined]
            from app.services.tenancy.context import set_org_context

            await set_org_context(db, uuid.UUID(actor.org_id))
            deleted = await purge_org(db, uuid.UUID(actor.org_id))
            await db.commit()
            return deleted

    deleted = api.client.portal.call(run)  # type: ignore[union-attr]
    assert deleted >= 1
    ids = {row["id"] for row in actor.get(f"/orgs/{actor.org_id}/conversations").json()["data"]}
    assert keep in ids
    assert old not in ids


def test_widget_customer_can_submit_csat_and_handoff(api: Api) -> None:
    actor, bot, key, _ = widget_setup(api)
    issued = boot(api, key)
    assert issued.status_code == 200, issued.text
    token = issued.json()["token"]
    listed = actor.get(f"/orgs/{actor.org_id}/conversations?channel=widget")
    assert listed.status_code == 200, listed.text
    conv = listed.json()["data"][0]["id"]
    headers = {"Authorization": f"Bearer {token}"}
    csat = api.client.put(
        "/public/v1/chat/satisfaction",
        json={"score": 4},
        headers=headers,
    )
    assert csat.status_code == 200, csat.text
    handoff = api.client.post(
        "/public/v1/chat/handoff",
        json={"reason": "Need a person"},
        headers=headers,
    )
    assert handoff.status_code == 201, handoff.text
    detail = actor.get(f"/orgs/{actor.org_id}/conversations/{conv}").json()
    assert detail["satisfaction_score"] == 4
    assert detail["handoff_status"] == "requested"


def test_viewer_cannot_mutate_conversation_outcome(api: Api) -> None:
    owner = api.signup()
    bot = new_bot(owner)
    conv = conversation(owner, bot)
    viewer = _invite(api, owner, "viewer")
    assert (
        viewer.patch(
            f"/orgs/{owner.org_id}/conversations/{conv}", {"status": "resolved"}
        ).status_code
        == 403
    )
    assert viewer.delete(f"/orgs/{owner.org_id}/conversations/{conv}").status_code == 403
    listed = viewer.get(f"/orgs/{owner.org_id}/conversations")
    assert listed.status_code == 200
    analytics = viewer.get(f"/orgs/{owner.org_id}/analytics/summary")
    assert analytics.status_code == 200
