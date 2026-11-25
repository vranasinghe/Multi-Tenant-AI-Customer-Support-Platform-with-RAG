"""Chatbot CRUD API: validation, RBAC, tenant isolation, plan limit, audit (docs/API_SPEC.md §2.3,
ROADMAP AC2.1)."""

from __future__ import annotations

import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

from tests.integration.api.conftest import Actor, Api

pytestmark = pytest.mark.integration


def _bots(org_id: str) -> str:
    return f"/orgs/{org_id}/chatbots"


def _create(actor: Actor, **fields: Any) -> dict[str, Any]:
    body = {"name": f"Bot {uuid.uuid4().hex[:6]}", **fields}
    response = actor.post(_bots(actor.org_id), body)
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


def _join(api: Api, owner: Actor, role: str) -> Actor:
    member = api.signup()
    owner.post(f"/orgs/{owner.org_id}/invitations", {"email": member.email, "role": role})
    token = api.mailbox.last_token(member.email, path="invite")
    assert member.post("/invitations/accept", {"token": token}).status_code == 200
    member.org_id = owner.org_id
    return member


def _field_errors(response: Any) -> set[str]:
    return {e["field"] for e in response.json().get("errors", [])}


# ------------------------------------------------------------------------- create & read


def test_create_returns_defaults_and_unique_public_key(api: Api) -> None:
    owner = api.signup()

    first = _create(owner, name="Support Bot", instructions="Help Acme customers.")
    second = _create(owner)

    assert first["status"] == "draft"
    assert first["model"] == "gpt-4.1-mini"
    assert first["temperature"] == 0.2
    assert first["language_mode"] == "auto"
    assert first["language"] is None
    assert first["widget_settings"]["primary_color"] == "#4F46E5"
    assert first["created_by"] == {"id": owner.user_id, "name": owner.name}
    assert re.fullmatch(r"pk_live_[A-Za-z0-9]{24}", first["public_key"])
    assert first["public_key"] != second["public_key"]


def test_full_configuration_round_trips(api: Api) -> None:
    owner = api.signup()
    config = {
        "name": "Concierge",
        "description": "Answers booking questions",
        "status": "active",
        "instructions": "Be precise.\nAlways cite policy.",
        "tone": "friendly",
        "response_length": "detailed",
        "welcome_message": "Hello!",
        "fallback_message": "Please email us.",
        "language_mode": "fixed",
        "language": "si",
        "model": "gpt-4.1",
        "temperature": 0.55,
        "max_output_tokens": 1200,
        "strict_grounding": False,
        "show_sources": False,
        "retrieval_top_k": 9,
        "widget_settings": {
            "primary_color": "#0f766e",
            "accent_color": "#ffffff",
            "avatar_url": "https://cdn.example.com/a.png",
            "position": "bottom-left",
            "launcher_label": "Ask us",
            "show_branding": False,
        },
    }

    created = _create(owner, **config)
    fetched = owner.get(f"{_bots(owner.org_id)}/{created['id']}").json()

    for key, value in config.items():
        if key == "widget_settings":
            continue
        assert fetched[key] == value, key
    assert fetched["widget_settings"]["primary_color"] == "#0F766E"  # normalized
    assert fetched["widget_settings"]["position"] == "bottom-left"


def test_list_filters_by_status_and_search_and_hides_deleted(api: Api) -> None:
    owner = api.signup()
    live = _create(owner, name="Sales assistant", status="active")
    _create(owner, name="Support helper")
    gone = _create(owner, name="Sales old")
    assert owner.delete(f"{_bots(owner.org_id)}/{gone['id']}").status_code == 204

    everything = owner.get(_bots(owner.org_id)).json()
    active = owner.get(f"{_bots(owner.org_id)}?status=active").json()["data"]
    search = owner.get(f"{_bots(owner.org_id)}?q=sales").json()["data"]
    wildcard = owner.get(f"{_bots(owner.org_id)}?q=%25").json()["data"]

    assert {b["name"] for b in everything["data"]} == {"Sales assistant", "Support helper"}
    assert everything["limit"] >= 1
    assert [b["id"] for b in active] == [live["id"]]
    assert [b["id"] for b in search] == [live["id"]]
    assert wildcard == []  # LIKE wildcards in the query are escaped


def test_options_catalog_matches_validation(api: Api) -> None:
    owner = api.signup()

    options = owner.get(f"/orgs/{owner.org_id}/chatbot-options").json()

    model_ids = {m["id"] for m in options["models"]}
    assert "gpt-4.1-mini" in model_ids
    assert [m["id"] for m in options["models"] if m["default"]] == ["gpt-4.1-mini"]
    assert {"code": "en", "label": "English"} in options["languages"]
    assert options["tones"] == ["professional", "friendly", "concise", "custom"]


# ---------------------------------------------------------------------------- validation


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"name": ""}, "name"),
        ({"name": "   "}, "name"),
        ({"name": "x" * 81}, "name"),
        ({"name": "ok", "instructions": "x" * 4001}, "instructions"),
        ({"name": "ok", "welcome_message": "x" * 501}, "welcome_message"),
        ({"name": "bad\x00null"}, "name"),
        ({"name": "ok", "temperature": 1.5}, "temperature"),
        ({"name": "ok", "max_output_tokens": 10}, "max_output_tokens"),
        ({"name": "ok", "retrieval_top_k": 13}, "retrieval_top_k"),
        ({"name": "ok", "tone": "sarcastic"}, "tone"),
        ({"name": "ok", "status": "archived"}, "status"),
        ({"name": "ok", "model": "gpt-99"}, "model"),
        ({"name": "ok", "language_mode": "fixed"}, "language"),
        ({"name": "ok", "language_mode": "fixed", "language": "xx"}, "language"),
        ({"name": "ok", "model": "gpt-4.1-nano", "max_output_tokens": 4096}, "max_output_tokens"),
        (
            {"name": "ok", "widget_settings": {"primary_color": "red"}},
            "widget_settings.primary_color",
        ),
        (
            {"name": "ok", "widget_settings": {"avatar_url": "http://insecure.example/a.png"}},
            "widget_settings.avatar_url",
        ),
        (
            {"name": "ok", "widget_settings": {"avatar_url": "javascript:alert(1)"}},
            "widget_settings.avatar_url",
        ),
    ],
)
def test_create_rejects_invalid_configuration(api: Api, body: dict[str, Any], field: str) -> None:
    owner = api.signup()

    response = owner.post(_bots(owner.org_id), body)

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "validation_error"
    assert field in _field_errors(response)


def test_server_controlled_fields_cannot_be_set(api: Api) -> None:
    owner = api.signup()
    other = api.signup()

    for extra in (
        {"org_id": other.org_id},
        {"public_key": "pk_live_" + "a" * 24},
        {"created_by": other.user_id},
        {"id": str(uuid.uuid4())},
    ):
        response = owner.post(_bots(owner.org_id), {"name": "Bot", **extra})
        assert response.status_code == 422, extra
    bot = _create(owner)
    patch = owner.patch(f"{_bots(owner.org_id)}/{bot['id']}", {"public_key": "pk_live_" + "b" * 24})
    assert patch.status_code == 422


def test_duplicate_names_conflict_case_insensitively_but_deleted_names_are_free(api: Api) -> None:
    owner = api.signup()
    bot = _create(owner, name="Helper")

    duplicate = owner.post(_bots(owner.org_id), {"name": "helper"})
    owner.delete(f"{_bots(owner.org_id)}/{bot['id']}")
    reused = owner.post(_bots(owner.org_id), {"name": "HELPER"})

    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "chatbot_name_taken"
    assert reused.status_code == 201


def test_same_name_is_allowed_in_different_organizations(api: Api) -> None:
    a, b = api.signup(), api.signup()

    assert a.post(_bots(a.org_id), {"name": "Support"}).status_code == 201
    assert b.post(_bots(b.org_id), {"name": "Support"}).status_code == 201


# -------------------------------------------------------------------------------- update


def test_patch_is_a_merge_patch(api: Api) -> None:
    owner = api.signup()
    bot = _create(owner, name="Original", instructions="Keep me", tone="friendly")

    response = owner.patch(
        f"{_bots(owner.org_id)}/{bot['id']}",
        {"name": "Renamed", "widget_settings": {"primary_color": "#111111"}},
    )

    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["name"] == "Renamed"
    assert updated["instructions"] == "Keep me"
    assert updated["tone"] == "friendly"
    assert updated["widget_settings"]["primary_color"] == "#111111"
    assert updated["widget_settings"]["launcher_label"] == bot["widget_settings"]["launcher_label"]
    assert updated["updated_at"] >= bot["updated_at"]


def test_patch_validates_against_the_merged_configuration(api: Api) -> None:
    owner = api.signup()
    bot = _create(owner, model="gpt-4.1", max_output_tokens=4000)
    path = f"{_bots(owner.org_id)}/{bot['id']}"

    smaller_model = owner.patch(path, {"model": "gpt-4.1-nano"})
    fixed_without_language = owner.patch(path, {"language_mode": "fixed"})
    nulls = owner.patch(path, {"name": None})
    both = owner.patch(path, {"model": "gpt-4.1-nano", "max_output_tokens": 1000})

    assert smaller_model.status_code == 422
    assert "max_output_tokens" in _field_errors(smaller_model)
    assert fixed_without_language.status_code == 422
    assert nulls.status_code == 422
    assert both.status_code == 200


def test_switching_back_to_auto_language_clears_the_language(api: Api) -> None:
    owner = api.signup()
    bot = _create(owner, language_mode="fixed", language="fr")

    updated = owner.patch(f"{_bots(owner.org_id)}/{bot['id']}", {"language_mode": "auto"}).json()

    assert updated["language_mode"] == "auto"
    assert updated["language"] is None


def test_avatar_can_be_cleared_with_null(api: Api) -> None:
    owner = api.signup()
    bot = _create(owner, widget_settings={"avatar_url": "https://cdn.example.com/x.png"})

    updated = owner.patch(
        f"{_bots(owner.org_id)}/{bot['id']}", {"widget_settings": {"avatar_url": None}}
    ).json()

    assert updated["widget_settings"]["avatar_url"] is None


def test_rotate_public_key_issues_a_new_key(api: Api) -> None:
    owner = api.signup()
    bot = _create(owner)

    rotated = owner.post(f"{_bots(owner.org_id)}/{bot['id']}/rotate-public-key")

    assert rotated.status_code == 200
    assert rotated.json()["public_key"] != bot["public_key"]


# -------------------------------------------------------------------------------- delete


def test_delete_is_soft_and_hides_the_chatbot_everywhere(api: Api) -> None:
    owner = api.signup()
    bot = _create(owner)
    path = f"{_bots(owner.org_id)}/{bot['id']}"

    assert owner.delete(path).status_code == 204

    assert owner.get(path).status_code == 404
    assert owner.patch(path, {"name": "zombie"}).status_code == 404
    assert owner.delete(path).status_code == 404
    assert owner.get(_bots(owner.org_id)).json()["data"] == []
    rows = api.sql("SELECT deleted_at FROM chatbots WHERE id = :id", id=bot["id"])
    assert rows[0][0] is not None  # kept for the undo window, not hard-deleted


def test_runtime_role_cannot_hard_delete_chatbots(api: Api) -> None:
    rows = api.sql(
        "SELECT has_table_privilege('platform_app', 'chatbots', 'DELETE'), "
        "has_table_privilege('platform_app', 'chatbots', 'INSERT')"
    )
    assert rows[0] == (False, True)


# ---------------------------------------------------------------------------------- RBAC


def test_role_matrix(api: Api) -> None:
    owner = api.signup()
    bot = _create(owner)
    path = f"{_bots(owner.org_id)}/{bot['id']}"
    viewer = _join(api, owner, "viewer")
    agent = _join(api, owner, "agent")
    admin = _join(api, owner, "admin")

    assert viewer.get(path).status_code == 200
    assert viewer.get(_bots(owner.org_id)).status_code == 200
    assert viewer.post(_bots(owner.org_id), {"name": "nope"}).status_code == 403
    assert viewer.patch(path, {"name": "nope"}).status_code == 403
    assert viewer.post(f"{path}/rotate-public-key").status_code == 403
    assert viewer.delete(path).status_code == 403

    assert agent.post(_bots(owner.org_id), {"name": "agent bot"}).status_code == 201
    assert agent.patch(path, {"description": "edited by agent"}).status_code == 200
    assert agent.delete(path).status_code == 403  # chatbot:delete is admin+

    assert admin.delete(path).status_code == 204


def test_unverified_users_cannot_create_chatbots(api: Api) -> None:
    owner = api.signup(verified=False)

    response = owner.post(_bots(owner.org_id), {"name": "Bot"})

    assert response.status_code == 403
    assert response.json()["code"] == "email_not_verified"


def test_restricted_org_is_read_only(api: Api) -> None:
    owner = api.signup()
    bot = _create(owner)
    api.sql("UPDATE organizations SET status = 'restricted' WHERE id = :id", id=owner.org_id)

    assert owner.get(_bots(owner.org_id)).status_code == 200
    blocked = owner.patch(f"{_bots(owner.org_id)}/{bot['id']}", {"name": "x"})
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "org_restricted"


# ------------------------------------------------------------------------------ isolation


def test_chatbots_of_another_org_are_invisible_and_untouchable(api: Api) -> None:
    a, b = api.signup(), api.signup()
    b_bot = _create(b, name="Secret bot")
    foreign = f"{_bots(b.org_id)}/{b_bot['id']}"
    idor = f"{_bots(a.org_id)}/{b_bot['id']}"  # my org in the URL, their chatbot id

    probes = {
        "list foreign": a.get(_bots(b.org_id)),
        "create foreign": a.post(_bots(b.org_id), {"name": "planted"}),
        "get foreign": a.get(foreign),
        "patch foreign": a.patch(foreign, {"name": "pwned"}),
        "delete foreign": a.delete(foreign),
        "rotate foreign": a.post(f"{foreign}/rotate-public-key"),
        "get idor": a.get(idor),
        "patch idor": a.patch(idor, {"name": "pwned"}),
        "delete idor": a.delete(idor),
        "rotate idor": a.post(f"{idor}/rotate-public-key"),
    }

    assert {k: r.status_code for k, r in probes.items()} == dict.fromkeys(probes, 404)
    assert a.get(_bots(a.org_id)).json()["data"] == []
    still = b.get(foreign).json()
    assert still["name"] == "Secret bot"
    assert still["public_key"] == b_bot["public_key"]
    assert not any("Secret bot" in r.text for r in probes.values())


def test_rls_hides_chatbots_without_org_context(api: Api, app_engine: Any) -> None:
    owner = api.signup()
    _create(owner)

    with app_engine.connect() as conn:
        from sqlalchemy import text

        assert conn.execute(text("SELECT count(*) FROM chatbots")).scalar_one() == 0


# ----------------------------------------------------------------------- limits & audit


def test_plan_limit_is_enforced_under_concurrency(api: Api) -> None:
    owner = api.signup()
    limit = owner.get(_bots(owner.org_id)).json()["limit"]
    api.sql(
        "INSERT INTO chatbots (id, org_id, name, public_key, model) "
        "SELECT gen_random_uuid(), CAST(:org AS uuid), 'seed ' || g, "
        "'pk_live_' || lpad(g::text, 24, '0'), 'gpt-4.1-mini' "
        "FROM generate_series(1, :n) AS g",
        org=owner.org_id,
        n=limit - 2,
    )

    def attempt(i: int) -> int:
        return owner.post(_bots(owner.org_id), {"name": f"racer {i}"}).status_code

    with ThreadPoolExecutor(max_workers=6) as pool:
        codes = list(pool.map(attempt, range(6)))

    assert sorted(codes) == [201, 201, 402, 402, 402, 402]
    count = api.sql(
        "SELECT count(*) FROM chatbots WHERE org_id = :org AND deleted_at IS NULL",
        org=owner.org_id,
    )
    assert count[0][0] == limit


def test_every_change_is_audited_without_copying_content(api: Api) -> None:
    owner = api.signup()
    bot = _create(owner, name="Audited")
    path = f"{_bots(owner.org_id)}/{bot['id']}"
    owner.patch(path, {"name": "Audited 2", "instructions": "SECRET-INSTRUCTIONS"})
    owner.post(f"{path}/rotate-public-key")
    owner.delete(path)

    entries = owner.get(f"/orgs/{owner.org_id}/audit-logs").json()["data"]
    actions = [e["action"] for e in entries if e["target_id"] == bot["id"]]

    assert actions == [
        "chatbot.deleted",
        "chatbot.public_key_rotated",
        "chatbot.updated",
        "chatbot.created",
    ]
    updated = next(e for e in entries if e["action"] == "chatbot.updated")
    assert updated["metadata"]["name"] == {"from": "Audited", "to": "Audited 2"}
    assert updated["metadata"]["fields"] == ["instructions"]
    assert "SECRET-INSTRUCTIONS" not in str(entries)


def test_no_op_patch_writes_no_audit_entry(api: Api) -> None:
    owner = api.signup()
    bot = _create(owner, name="Same")

    owner.patch(f"{_bots(owner.org_id)}/{bot['id']}", {"name": "Same"})

    entries = owner.get(f"/orgs/{owner.org_id}/audit-logs?action=chatbot.updated").json()
    assert entries["data"] == []
