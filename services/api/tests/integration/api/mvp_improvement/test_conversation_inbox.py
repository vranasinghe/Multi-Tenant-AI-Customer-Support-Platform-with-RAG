"""AUD-06: the organization conversation inbox over real persisted conversations.

Widget and playground conversations are produced through their own APIs. Bulk fixtures for
pagination are inserted with SQL into a chatbot created the normal way.
"""

from __future__ import annotations

import base64
import json
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import Engine, event

from app.core.config import Settings
from app.rag.queue import RecordingJobQueue
from app.rag.runtime import Runtime
from tests.integration.api.conftest import Actor, Api
from tests.integration.api.test_conversation_analytics import _invite
from tests.integration.api.test_conversations import conversation, done, send
from tests.integration.api.test_knowledge_documents import docs_path, ingest, new_bot
from tests.integration.api.test_orgs_members import _membership_id
from tests.integration.api.test_widget import boot
from tests.integration.api.test_widget import setup as widget_setup

pytestmark = pytest.mark.integration

ROLES = ("owner", "admin", "agent", "viewer")


@pytest.fixture(autouse=True)
def enable_chat(api_settings: Settings) -> None:
    api_settings.llm_provider = "demo"


def inbox(actor: Actor, query: str = "", org: str | None = None) -> Any:
    return actor.get(f"/orgs/{org or actor.org_id}/conversations{query}")


def listed(actor: Actor, query: str = "") -> dict[str, Any]:
    response = inbox(actor, query)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def ids(body: dict[str, Any]) -> list[str]:
    return [row["id"] for row in body["data"]]


def every_page(actor: Actor, query: str) -> list[str]:
    found: list[str] = []
    cursor = ""
    for _ in range(200):
        body = listed(actor, f"?{query}{cursor}")
        found += ids(body)
        if not body["has_more"]:
            assert body["next_cursor"] is None
            return found
        cursor = f"&cursor={body['next_cursor']}"
    raise AssertionError("pagination never ended")


def transcript(actor: Actor, conv: str, query: str = "", org: str | None = None) -> Any:
    return actor.get(f"/orgs/{org or actor.org_id}/conversations/{conv}{query}")


def messages(actor: Actor, conv: str, query: str = "", org: str | None = None) -> Any:
    return actor.get(f"/orgs/{org or actor.org_id}/conversations/{conv}/messages{query}")


def widget_conversation(api: Api, text: str) -> tuple[Actor, str, str, str]:
    """A real widget visitor: capability session, one streamed turn. Returns the token too."""
    owner, bot, key, _ = widget_setup(api)
    token = boot(api, key).json()["token"]
    api.client.cookies.clear()
    sent = api.client.post(
        "/public/v1/chat/messages",
        json={"content": text},
        headers={"Authorization": "Bearer " + token, "Origin": "https://testserver"},
    )
    assert sent.status_code == 200, sent.text
    [row] = [r for r in listed(owner, "?channel=widget")["data"] if text in r["preview"]]
    return owner, bot, str(row["id"]), str(token)


def playground(actor: Actor, bot: str, text: str) -> str:
    conv = conversation(actor, bot)
    done(send(actor, conv, text))
    return conv


def seed_conversations(
    api: Api, org: str, bot: str, count: int, *, same_instant: bool = False
) -> None:
    api.sql(
        "INSERT INTO conversations (id, org_id, chatbot_id, channel, preview, created_at, "
        "last_message_at) SELECT gen_random_uuid(), :o, :b, 'widget', 'seeded ' || n, "
        "now() - interval '1 day' - (n * CAST(:step AS integer) || ' seconds')::interval, "
        "now() - interval '1 day' - (n * CAST(:step AS integer) || ' seconds')::interval "
        "FROM generate_series(1, :n) AS n",
        o=org,
        b=bot,
        n=count,
        step=0 if same_instant else 1,
    )


def seed_messages(api: Api, org: str, conv: str, count: int) -> None:
    # Pairs share an instant, so ordering needs the unique tie-breaker.
    api.sql(
        "INSERT INTO messages (id, org_id, conversation_id, role, content, status, created_at) "
        "SELECT (:p || '-0000-7000-8000-' || lpad(to_hex(n), 12, '0'))::uuid, :o, :c, "
        "CASE WHEN n % 2 = 1 THEN 'user' ELSE 'assistant' END, 'message ' || n, 'complete', "
        "timestamptz '2026-01-01' + ((n + 1) / 2 || ' seconds')::interval "
        "FROM generate_series(1, :n) AS n",
        o=org,
        c=conv,
        n=count,
        p=uuid.uuid4().hex[:8],  # unique per call; ordered by n within it
    )


def cursor_of(stamp: str, ident: str, scope: str) -> str:
    return base64.urlsafe_b64encode(f"{stamp}|{ident}|{scope}".encode()).decode()


def parts(cursor: str) -> list[str]:
    return base64.urlsafe_b64decode(cursor.encode()).decode().split("|")


# ---------------------------------------------------------------- persisted records


def test_widget_and_playground_conversations_are_listed_and_stay_listed(api: Api) -> None:
    owner, bot, widget, _ = widget_conversation(api, "Do you ship to Canada?")
    played = playground(owner, bot, "What is the returns policy?")

    first = listed(owner)

    rows = {row["id"]: row for row in first["data"]}
    assert first["total"] == 2 and set(rows) == {widget, played}
    assert ids(first) == [played, widget]  # latest activity first
    assert (rows[widget]["channel"], rows[played]["channel"]) == ("widget", "playground")
    name = owner.get(f"/orgs/{owner.org_id}/chatbots/{bot}").json()["name"]
    for row in rows.values():
        assert row["chatbot_id"] == bot and row["chatbot_name"] == name
        assert row["last_message_at"] > row["created_at"]
    assert listed(owner) == first
    for conv, question in ((widget, "Canada"), (played, "returns")):
        body = transcript(owner, conv).json()
        assert [m["role"] for m in body["messages"]] == ["user", "assistant"]
        assert question in body["messages"][0]["content"]
        assert body["messages"][0]["created_at"] <= body["messages"][1]["created_at"]
        assert body["older_cursor"] is None


def test_chatbot_channel_and_status_filters(api: Api) -> None:
    owner = api.signup()
    first, second = new_bot(owner), new_bot(owner, "Second bot")
    a = playground(owner, first, "About the first bot")
    b = playground(owner, second, "About the second bot")
    seed_conversations(api, owner.org_id, second, 1)
    owner.patch(f"/orgs/{owner.org_id}/conversations/{a}", {"status": "resolved"})

    assert ids(listed(owner, f"?chatbot_id={first}")) == [a]
    assert listed(owner, f"?chatbot_id={second}")["total"] == 2
    assert ids(listed(owner, f"?chatbot_id={second}&channel=playground")) == [b]
    assert ids(listed(owner, "?status=resolved")) == [a]
    assert ids(listed(owner, f"?chatbot_id={second}&status=resolved")) == []


def test_an_empty_organization_has_an_empty_inbox(api: Api) -> None:
    assert listed(api.signup()) == {
        "data": [],
        "next_cursor": None,
        "has_more": False,
        "total": 0,
    }


# ---------------------------------------------------------------- transcripts


def test_a_long_transcript_is_reviewable_completely_and_in_order(api: Api) -> None:
    owner = api.signup()
    conv = conversation(owner, new_bot(owner))
    seed_messages(api, owner.org_id, conv, 250)

    body = transcript(owner, conv).json()
    contents = [m["content"] for m in body["messages"]]
    assert contents == [f"message {n}" for n in range(51, 251)]  # the existing newest 200
    cursor = body["older_cursor"]
    pages = 0
    while cursor:
        page = messages(owner, conv, f"?limit=20&cursor={cursor}")
        assert page.status_code == 200, page.text
        data = page.json()
        assert len(data["data"]) <= 20
        assert data["has_more"] == (data["next_cursor"] is not None)
        contents = [m["content"] for m in data["data"]] + contents
        cursor = data["next_cursor"]
        pages += 1
    assert contents == [f"message {n}" for n in range(1, 251)] and pages == 3

    newest = messages(owner, conv).json()  # without a cursor: the newest page
    assert [m["content"] for m in newest["data"]] == [f"message {n}" for n in range(201, 251)]
    assert all(m["created_at"] for m in newest["data"])
    assert len(messages(owner, conv, "?limit=100").json()["data"]) == 100
    for bad in ("0", "101"):
        assert messages(owner, conv, f"?limit={bad}").status_code == 422
        assert inbox(owner, f"?limit={bad}").status_code == 422


def test_message_states_and_feedback_are_reported_as_stored(api: Api) -> None:
    owner = api.signup()
    conv = playground(owner, new_bot(owner), "Anything at all?")
    answer = transcript(owner, conv).json()["messages"][1]
    owner.put(
        f"/orgs/{owner.org_id}/conversations/{conv}/messages/{answer['id']}/feedback",
        {"rating": -1},
    )
    seed_messages(api, owner.org_id, conv, 3)
    for number, status in ((1, "interrupted"), (2, "failed"), (3, "fallback")):
        api.sql(
            "UPDATE messages SET status = :s WHERE conversation_id = :c AND content = :t",
            s=status,
            c=conv,
            t=f"message {number}",
        )

    found = {m["content"]: m for m in transcript(owner, conv).json()["messages"]}

    assert [found[f"message {n}"]["status"] for n in (1, 2, 3)] == [
        "interrupted",
        "failed",
        "fallback",
    ]
    assert next(m for m in found.values() if m["id"] == answer["id"])["feedback"] == -1


def test_stored_citations_stay_historical_and_private(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue
) -> None:
    owner = api.signup()
    bot = new_bot(owner)
    document = ingest(
        api,
        runtime,
        job_queue,
        owner,
        bot,
        "returns.txt",
        b"Returns are allowed within thirty days of delivery. Items must be unused.",
        "text/plain",
    )
    conv = playground(owner, bot, "Are returns allowed within thirty days?")
    cited = transcript(owner, conv).json()["messages"][1]["citations"]
    assert cited and cited[0]["document_id"] == document["id"]
    assert set(cited[0]) == {"id", "document_id", "chunk_id", "title", "uri", "page"}

    assert owner.delete(f"{docs_path(owner, bot)}/documents/{document['id']}").status_code == 204

    after = transcript(owner, conv)
    assert after.json()["messages"][1]["citations"] == cited
    assert messages(owner, conv).json()["data"][1]["citations"] == cited
    for leaked in ("storage_key", "embedded_text", "orgs/", "<source", "system"):
        assert leaked not in json.dumps(after.json()["messages"]), leaked


# ---------------------------------------------------------------- pagination


def test_every_conversation_is_returned_exactly_once_across_pages(api: Api) -> None:
    owner = api.signup()
    bot = new_bot(owner)
    seed_conversations(api, owner.org_id, bot, 40)
    seed_conversations(api, owner.org_id, bot, 40, same_instant=True)
    expected = [
        str(row[0])
        for row in api.sql(
            "SELECT id FROM conversations WHERE org_id = :o ORDER BY last_message_at DESC, id DESC",
            o=owner.org_id,
        )
    ]

    for limit in (1, 7, 25, 100):
        assert every_page(owner, f"limit={limit}") == expected, limit
    assert len(expected) == 80
    assert listed(owner, "?limit=7")["total"] == 80


def test_pages_are_not_a_snapshot_while_conversations_change(api: Api) -> None:
    """Documented behaviour: activity moves a conversation up; nothing is repeated."""
    owner = api.signup()
    bot = new_bot(owner)
    seed_conversations(api, owner.org_id, bot, 6)
    before = every_page(owner, "limit=100")
    first = listed(owner, "?limit=3")
    late = before[4]
    api.sql("UPDATE conversations SET last_message_at = now() WHERE id = :i", i=late)
    seed_conversations(api, owner.org_id, bot, 1)  # arrives while browsing (a day old stamp)

    second = listed(owner, f"?limit=3&cursor={first['next_cursor']}")

    seen = ids(first) + ids(second)
    assert len(seen) == len(set(seen))
    assert late not in seen  # moved above the cursor: it shows on the next refresh
    assert ids(listed(owner, "?limit=1")) == [late]


@pytest.mark.parametrize(
    "cursor",
    [
        "not-base64!",
        "AAAA",
        "x" * 600,
        base64.urlsafe_b64encode(b"only|two").decode(),
        cursor_of("yesterday", str(uuid.uuid4()), "0" * 16),
        cursor_of("2026-11-25T10:00:00", str(uuid.uuid4()), "0" * 16),  # no time zone
        cursor_of("2026-11-25T10:00:00+00:00", "not-a-uuid", "0" * 16),
        cursor_of("2026-11-25T10:00:00+00:00", str(uuid.uuid4()), "0" * 16),  # wrong scope
        base64.urlsafe_b64encode(b"\xff\xfe|\xff|\xff").decode(),
    ],
)
def test_a_malformed_cursor_is_refused_not_ignored(api: Api, cursor: str) -> None:
    owner = api.signup()
    conv = playground(owner, new_bot(owner), "hello")

    for response in (
        inbox(owner, f"?cursor={cursor}"),
        messages(owner, conv, f"?cursor={cursor}"),
    ):
        assert response.status_code == 400, response.text
        assert response.json()["code"] == "invalid_cursor"


def test_a_cursor_is_bound_to_its_organization_filters_and_list(api: Api) -> None:
    owner = api.signup()
    bot = new_bot(owner)
    seed_conversations(api, owner.org_id, bot, 5)
    one, two = playground(owner, bot, "first long one"), playground(owner, bot, "second long one")
    seed_messages(api, owner.org_id, one, 220)
    cursor = listed(owner, "?limit=2")["next_cursor"]
    older = transcript(owner, one).json()["older_cursor"]
    stranger = api.signup()
    new_bot(stranger)

    assert listed(owner, f"?limit=2&cursor={cursor}")["data"]  # same scope
    assert listed(owner, f"?limit=5&cursor={cursor}")["data"]  # page size is not scope
    for response in (
        inbox(owner, f"?channel=widget&cursor={cursor}"),
        inbox(owner, f"?chatbot_id={bot}&cursor={cursor}"),
        inbox(owner, f"?q=seeded&cursor={cursor}"),
        inbox(owner, f"?cursor={older}"),
        messages(owner, one, f"?cursor={cursor}"),
        messages(owner, two, f"?cursor={older}"),
        inbox(stranger, f"?cursor={cursor}"),
    ):
        assert (response.status_code, response.json()["code"]) == (400, "invalid_cursor")


def test_a_cursor_is_never_an_authorization(api: Api) -> None:
    owner = api.signup()
    bot = new_bot(owner)
    seed_conversations(api, owner.org_id, bot, 5)
    conv = playground(owner, bot, "tenant a words")
    seed_messages(api, owner.org_id, conv, 220)
    cursor = listed(owner, "?limit=2")["next_cursor"]
    older = transcript(owner, conv).json()["older_cursor"]
    stranger = api.signup()

    assert inbox(stranger, f"?cursor={cursor}", org=owner.org_id).status_code == 404
    assert messages(stranger, conv, f"?cursor={older}", org=owner.org_id).status_code == 404
    assert messages(stranger, conv, f"?cursor={older}").status_code == 404
    # A cursor forged for the stranger's own scope still only reads the stranger's own rows.
    seed_conversations(api, stranger.org_id, new_bot(stranger), 3)
    own = listed(stranger, "?limit=1")["next_cursor"]
    _, _, scope = parts(own)
    forged = cursor_of("2999-01-01T00:00:00+00:00", "ffffffff-ffff-ffff-ffff-ffffffffffff", scope)
    body = listed(stranger, f"?cursor={forged}")
    assert body["total"] == 3 and not set(ids(body)) & set(every_page(owner, "limit=100"))


# ---------------------------------------------------------------- authorization


def test_identifiers_from_another_organization_expose_nothing(api: Api) -> None:
    owner = api.signup()
    bot = new_bot(owner)
    conv = playground(owner, bot, "tenant a words")
    stranger = api.signup()
    new_bot(stranger)

    for response in (
        inbox(stranger, org=owner.org_id),
        transcript(stranger, conv, org=owner.org_id),
        messages(stranger, conv, org=owner.org_id),
        transcript(stranger, conv),
        messages(stranger, conv),
    ):
        assert response.status_code == 404, response.text
        assert "tenant a words" not in response.text
    body = listed(stranger, f"?chatbot_id={bot}")
    assert (body["data"], body["total"]) == ([], 0)


def test_unauthenticated_and_widget_capability_requests_are_refused(api: Api) -> None:
    owner, _, conv, token = widget_conversation(api, "visitor words")
    anonymous = api.anonymous()
    base = f"/orgs/{owner.org_id}/conversations"

    for path in (base, f"{base}/{conv}", f"{base}/{conv}/messages"):
        assert anonymous.get(path).status_code == 401, path
        api.client.cookies.clear()
        as_widget = api.client.get(f"/api/v1{path}", headers={"Authorization": "Bearer " + token})
        assert as_widget.status_code == 401, path
    # The visitor's own history keeps its existing shape.
    history = api.client.get("/public/v1/chat", headers={"Authorization": "Bearer " + token})
    assert history.status_code == 200
    assert set(history.json()) == {"messages"}
    assert "created_at" not in history.json()["messages"][0]


def test_every_role_reads_and_only_permitted_roles_change(api: Api) -> None:
    owner = api.signup()
    bot = new_bot(owner)
    conv = playground(owner, bot, "shared words")
    members = {"owner": owner, **{role: _invite(api, owner, role) for role in ROLES[1:]}}
    base = f"/orgs/{owner.org_id}/conversations/{conv}"

    for role, member in members.items():
        for response in (
            inbox(member, org=owner.org_id),
            transcript(member, conv, org=owner.org_id),
            messages(member, conv, org=owner.org_id),
        ):
            assert response.status_code == 200, (role, response.text)
        writes = member.patch(base, {"status": "resolved"}).status_code
        assert writes == (403 if role == "viewer" else 200), role
    for role in ("viewer", "agent"):
        assert members[role].delete(base).status_code == 403, role


def test_role_change_removal_and_logout_take_effect_on_the_next_page(api: Api) -> None:
    owner = api.signup()
    bot = new_bot(owner)
    seed_conversations(api, owner.org_id, bot, 5)
    member = _invite(api, owner, "viewer")
    membership = _membership_id(owner, member)
    conv = ids(listed(owner, "?limit=1"))[0]
    base = f"/orgs/{owner.org_id}/conversations"
    cursor = inbox(member, "?limit=2", org=owner.org_id).json()["next_cursor"]

    assert member.delete(f"{base}/{conv}").status_code == 403
    owner.patch(f"/orgs/{owner.org_id}/members/{membership}", {"role": "admin"})
    assert member.delete(f"{base}/{conv}").status_code == 204

    assert owner.delete(f"/orgs/{owner.org_id}/members/{membership}").status_code == 204
    gone = member.get(f"{base}?limit=2&cursor={cursor}")
    assert gone.status_code == 404, gone.text

    assert owner.post("/auth/logout").status_code in {200, 204}
    assert owner.get(base).status_code == 401


def test_a_restricted_organization_can_still_be_read(api: Api) -> None:
    owner = api.signup()
    conv = playground(owner, new_bot(owner), "kept words")
    api.sql("UPDATE organizations SET status = 'restricted' WHERE id = :o", o=owner.org_id)

    assert listed(owner)["total"] == 1
    assert transcript(owner, conv).status_code == 200
    assert messages(owner, conv).status_code == 200
    blocked = owner.patch(f"/orgs/{owner.org_id}/conversations/{conv}", {"status": "resolved"})
    assert (blocked.status_code, blocked.json()["code"]) == (403, "org_restricted")


# ---------------------------------------------------------------- deletion and bounds


def test_deleting_removes_the_transcript_and_keeps_recorded_usage(api: Api) -> None:
    owner = api.signup()
    conv = playground(owner, new_bot(owner), "to be removed")
    usage = "SELECT count(*), sum(charged_tokens) FROM chat_usage WHERE org_id = :o"
    [before] = api.sql(usage, o=owner.org_id)

    assert owner.delete(f"/orgs/{owner.org_id}/conversations/{conv}").status_code == 204

    assert listed(owner)["total"] == 0
    assert transcript(owner, conv).status_code == 404
    assert messages(owner, conv).status_code == 404
    [after] = api.sql(usage, o=owner.org_id)
    assert tuple(after) == tuple(before) and after[0] == 1


@pytest.fixture
def statements() -> Iterator[list[str]]:
    seen: list[str] = []

    def record(_conn: Any, _cursor: Any, statement: str, *_rest: Any) -> None:
        seen.append(statement)

    event.listen(Engine, "before_cursor_execute", record)
    yield seen
    event.remove(Engine, "before_cursor_execute", record)


def test_query_count_does_not_grow_with_the_rows_returned(api: Api, statements: list[str]) -> None:
    owner = api.signup()
    bot = new_bot(owner)
    small, large = playground(owner, bot, "small"), playground(owner, bot, "large")
    seed_messages(api, owner.org_id, large, 250)

    def count(call: Any) -> int:
        statements.clear()
        assert call().status_code == 200
        return len(statements)

    few = (count(lambda: inbox(owner, "?limit=100")), count(lambda: transcript(owner, small)))
    page_small = count(lambda: messages(owner, small, "?limit=100"))
    seed_conversations(api, owner.org_id, bot, 90)
    many = (count(lambda: inbox(owner, "?limit=100")), count(lambda: transcript(owner, large)))

    assert many == few
    assert count(lambda: messages(owner, large, "?limit=100")) == page_small
