"""API seam and task seam: retention and tombstones.

Visitors chat through the widget API (answers from a ``FunctionModel``) and give Message
Feedback with comments; the daily purge Beat task is called directly as a task, as of the
controllable clock's time, beside the ``usage_daily`` rollup task; Owners set the Retention
Window and delete Conversations through the Studio API. Assertions are on HTTP responses only:
the Conversations viewer (Message text, ``purged_at``, feedback comments), the Version metrics
endpoint (identical before and after a purge), the Trace (tombstones) and Audit Events."""

import asyncio
from datetime import datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.retention.tasks import purge_expired
from app.worker.celery_app import PURGE_TASK, ROLL_UP_TASK, celery_app
from tests.conftest import ClientFactory, MemberFactory, SignedUpMember, TenantFactory
from tests.documents import project_path, upload
from tests.fakes.clock import ControllableClock
from tests.integration.test_agent_archive import archive as archive_agent
from tests.integration.test_conversations import (
    conversations_path,
    listed,
    opened,
    playground_chat,
    trace_of,
)
from tests.integration.test_document_editions import audit_events
from tests.integration.test_embed import send
from tests.integration.test_input_guardrail import ATTACK, REASON, guard
from tests.integration.test_projects import archive as archive_project
from tests.integration.test_version_metrics import (
    chat,
    live_agent,
    metrics,
    rate,
    roll_up,
    thumb,
)

EXPENSES = "Claim expenses within 30 days of spending."


@pytest.fixture
async def visitor(new_client: ClientFactory) -> httpx.AsyncClient:
    """A browser on someone's website: no Studio session."""
    return await new_client()


async def purge(at: datetime) -> None:
    """Runs the purge Beat task as Beat would at ``at`` (in a thread: the task runs its own
    event loop)."""
    result = await asyncio.to_thread(purge_expired.apply, kwargs={"at": at.isoformat()})
    result.get()


def organisation_path(member: SignedUpMember) -> str:
    return f"/api/organisations/{member.organisation_id}"


async def set_window(member: SignedUpMember, days: Any) -> httpx.Response:
    return await member.client.put(
        f"{organisation_path(member)}/retention-window", json={"retention_days": days}
    )


async def conversation_messages(
    member: SignedUpMember, project_id: str
) -> list[list[dict[str, Any]]]:
    """Every Conversation's Messages in the Project, oldest Conversation first."""
    page = await listed(member, project_id, page_size=100)
    return [
        (await opened(member, project_id, row["id"]))["messages"] for row in reversed(page["items"])
    ]


def texts(messages: list[dict[str, Any]]) -> list[str]:
    return [m["content"] for m in messages]


def comments(messages: list[dict[str, Any]]) -> list[str | None]:
    return [m["feedback"]["comment"] for m in messages if m["feedback"] is not None]


# Tombstones


async def test_a_trace_keeps_a_deleted_documents_name_as_a_tombstone(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await live_agent(app, owner)
    project_id = agent["project_id"]
    expenses = await upload(app, owner, project_id, "expenses.txt", EXPENSES.encode())
    await chat(visitor, agent, "Leave and expenses?")
    (item,) = (await listed(owner, project_id))["items"]
    reply = (await opened(owner, project_id, item["id"]))["messages"][1]
    path = trace_of(owner, project_id, item["id"], reply["id"])
    before = (await owner.client.get(path)).json()["chunks"]
    by_name = {c["document_name"]: c for c in before}
    assert by_name["expenses.txt"]["document_deleted"] is False
    assert by_name["expenses.txt"]["text"] == EXPENSES

    deleted = await owner.client.delete(
        f"{project_path(owner, project_id)}/documents/{expenses['id']}"
    )
    assert deleted.status_code == 204, deleted.text

    response = await owner.client.get(path)
    assert response.status_code == 200, response.text
    after = response.json()["chunks"]
    # The Trace still lists every retrieval in the same order; the deleted Document's Chunk
    # keeps the Document's name, with its IDs and text gone.
    assert [c["document_name"] for c in after] == [c["document_name"] for c in before]
    tombstone = next(c for c in after if c["document_name"] == "expenses.txt")
    assert tombstone | {"score": None, "relevance": None} == {
        "chunk_id": None,
        "document_id": None,
        "document_name": "expenses.txt",
        "document_deleted": True,
        "text": None,
        "score": None,
        "relevance": None,
        "rank": by_name["expenses.txt"]["rank"],
        "cited": by_name["expenses.txt"]["cited"],
        "excluded_reason": by_name["expenses.txt"]["excluded_reason"],
    }
    assert tombstone["score"] == by_name["expenses.txt"]["score"]
    kept = next(c for c in after if c["document_name"] == "leave.txt")
    assert kept == by_name["leave.txt"]


# The Retention Window setting


async def test_the_retention_window_defaults_to_90_days_and_owner_changes_are_audited(
    owner: SignedUpMember, member_factory: MemberFactory, clock: ControllableClock
) -> None:
    editor = await member_factory(owner, "editor")
    read = await editor.client.get(organisation_path(editor))
    assert read.status_code == 200, read.text
    assert read.json()["retention_days"] == 90
    clock.advance(timedelta(hours=1))

    response = await set_window(owner, 30)

    assert response.status_code == 200, response.text
    assert response.json()["retention_days"] == 30
    assert (await editor.client.get(organisation_path(editor))).json()["retention_days"] == 30
    (event,) = await audit_events(owner, "organisation.retention_window_changed")
    assert event["actor"]["id"] == owner.member_id
    assert event["target"] == {"type": "organisation", "id": owner.organisation_id}
    assert (event["before"], event["after"]) == ({"retention_days": 90}, {"retention_days": 30})
    assert datetime.fromisoformat(event["occurred_at"]) == clock.now()
    # Setting the same value again changes and records nothing.
    again = await set_window(owner, 30)
    assert (again.status_code, again.json()["retention_days"]) == (200, 30)
    assert len(await audit_events(owner, "organisation.retention_window_changed")) == 1


async def test_only_owners_change_the_retention_window_within_its_range(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")

    refused = await set_window(editor, 30)

    assert refused.status_code == 403, refused.text
    for days in (6, 3651, "ninety", None):
        response = await set_window(owner, days)
        assert response.status_code == 422, (days, response.text)
    for days in (7, 3650):
        response = await set_window(owner, days)
        assert (response.status_code, response.json()["retention_days"]) == (200, days)
    assert (await owner.client.get(organisation_path(owner))).json()["retention_days"] == 3650


# The daily purge


async def chat_and_feedback(
    visitor: httpx.AsyncClient, agent: dict[str, Any], question: str, comment: str
) -> str:
    """A Visitor Conversation of two replies: a thumbs up with a comment, a thumbs down, and a
    rating of 4. Returns its Conversation token."""
    token, (first, second) = await chat(visitor, agent, question, "And sick days?")
    response = await visitor.put(
        f"/api/widget/agents/{agent['public_id']}/messages/{first}/feedback",
        json={"rating": "up", "comment": comment},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    await thumb(visitor, agent, token, second, "down")
    await rate(visitor, agent, token, 4)
    return token


async def all_metrics(owner: SignedUpMember, agent: dict[str, Any]) -> dict[str, Any]:
    return await metrics(owner, agent, start="2026-11-01", end="2026-12-31")


async def test_messages_older_than_the_window_lose_their_text_and_comments_and_metrics_stay(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent = await live_agent(app, owner)
    project_id = agent["project_id"]
    assert (await set_window(owner, 7)).status_code == 200
    # Nov 5, 09:00: an old Conversation; Nov 6, 09:00: a newer one.
    await chat_and_feedback(visitor, agent, "How much leave?", "Very clear, thanks")
    clock.advance(timedelta(days=1))
    await chat_and_feedback(visitor, agent, "Parental leave?", "Helpful")
    # Nov 12, 10:00: the first Conversation is more than 7 days old; the rollups are final.
    clock.advance(timedelta(days=6, hours=1))
    await roll_up(clock.now())
    before = await all_metrics(owner, agent)
    assert before["versions"][0]["messages"] == 4

    await purge(clock.now())

    old, new = await conversation_messages(owner, project_id)
    assert texts(old) == ["", "", "", ""]
    assert {m["purged_at"] for m in old} == {clock.now().isoformat().replace("+00:00", "Z")}
    # The feedback and its numbers stay; only the comment goes.
    assert [m["feedback"]["rating"] for m in old if m["feedback"]] == ["up", "down"]
    assert comments(old) == [None, None]
    assert [m["input_tokens"] > 0 for m in old if m["role"] == "assistant"] == [True, True]
    assert texts(new)[0] == "Parental leave?"
    assert {m["purged_at"] for m in new} == {None}
    assert comments(new) == ["Helpful", None]
    old_row, new_row = reversed((await listed(owner, project_id))["items"])
    assert (old_row["preview"], old_row["message_count"]) == (None, 4)
    assert (old_row["thumbs_up"], old_row["thumbs_down"], old_row["rating"]) == (1, 1, 4)
    assert new_row["preview"] == "Parental leave?"
    assert await all_metrics(owner, agent) == before

    # A day later the newer Conversation goes too, and a purged Message isn't purged again.
    clock.advance(timedelta(days=1))
    await roll_up(clock.now())
    await purge(clock.now())

    old_again, new = await conversation_messages(owner, project_id)
    assert old_again == old
    assert texts(new) == ["", "", "", ""]
    assert comments(new) == [None, None]
    assert await all_metrics(owner, agent) == before


async def test_guardrail_reasons_are_purged_with_the_text_and_verdicts_stay(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    # A classifier's reason can quote or paraphrase the Visitor's message.
    guard(app)
    agent = await live_agent(app, owner)
    project_id = agent["project_id"]
    await chat(visitor, agent, ATTACK)
    (row,) = (await listed(owner, project_id))["items"]
    reply = (await opened(owner, project_id, row["id"]))["messages"][1]
    path = trace_of(owner, project_id, row["id"], reply["id"])
    (before,) = (await owner.client.get(path)).json()["guardrail_outcomes"]
    assert before["reason"] == REASON
    clock.advance(timedelta(days=91))
    await roll_up(clock.now())

    await purge(clock.now())

    (after,) = (await owner.client.get(path)).json()["guardrail_outcomes"]
    assert after == before | {"reason": ""}


async def test_the_purge_waits_until_the_rollup_of_the_day_is_final(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent = await live_agent(app, owner)
    project_id = agent["project_id"]
    assert (await set_window(owner, 7)).status_code == 200
    await chat(visitor, agent, "How much leave?")
    clock.advance(timedelta(minutes=1))
    await playground_chat(owner, project_id, agent["id"], "Testing")
    # Ten days on, the rollup task hasn't run since Nov 5.
    clock.advance(timedelta(days=10))

    await purge(clock.now())

    # Playground Messages never go into the rollups, so they are purged; the Visitor's wait.
    visitor_messages, playground_messages = await conversation_messages(owner, project_id)
    assert texts(visitor_messages)[0] == "How much leave?"
    assert texts(playground_messages) == ["", ""]

    await roll_up(clock.now())
    before = await all_metrics(owner, agent)
    await purge(clock.now())

    visitor_messages, _ = await conversation_messages(owner, project_id)
    assert texts(visitor_messages) == ["", ""]
    assert await all_metrics(owner, agent) == before


async def test_the_beat_schedule_purges_daily_after_the_rollup_finalises_the_day(
    app: FastAPI,
) -> None:
    schedule = {e["task"]: e["schedule"] for e in celery_app.conf.beat_schedule.values()}
    purge_at, roll_up_at = schedule[PURGE_TASK], schedule[ROLL_UP_TASK]
    assert (purge_at.hour, purge_at.minute) == ({0}, {35})
    # The 00:05 rollup finalises the previous day half an hour before.
    assert 0 in roll_up_at.hour
    assert max(roll_up_at.minute) < min(purge_at.minute)


async def test_without_a_time_the_purge_runs_as_of_now(owner: SignedUpMember) -> None:
    result = await asyncio.to_thread(purge_expired.apply)

    # An Organisation with no Messages has nothing to purge.
    assert result.get() == 0


async def test_archived_agents_and_projects_are_purged_too(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    archived = await live_agent(app, owner)
    in_archived_project = await live_agent(app, owner)
    assert (await set_window(owner, 7)).status_code == 200
    await chat_and_feedback(visitor, archived, "How much leave?", "Clear")
    await chat_and_feedback(visitor, in_archived_project, "Sick days?", "Thanks")
    response = await archive_agent(owner, archived["project_id"], archived["id"])
    assert response.status_code == 200, response.text
    response = await archive_project(owner, in_archived_project["project_id"])
    assert response.status_code == 200, response.text
    clock.advance(timedelta(days=8))
    await roll_up(clock.now())

    await purge(clock.now())

    for agent in (archived, in_archived_project):
        (messages,) = await conversation_messages(owner, agent["project_id"])
        assert texts(messages) == ["", "", "", ""]
        assert comments(messages) == [None, None]


async def test_each_organisation_is_purged_by_its_own_window(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    tenant_factory: TenantFactory,
) -> None:
    short = await live_agent(app, owner)
    other_owner = await tenant_factory()
    default = await live_agent(app, other_owner)
    assert (await set_window(owner, 7)).status_code == 200
    await chat(visitor, short, "How much leave?")
    await chat(visitor, default, "How much leave?")
    clock.advance(timedelta(days=30))
    await roll_up(clock.now())

    await purge(clock.now())

    (purged,) = await conversation_messages(owner, short["project_id"])
    (kept,) = await conversation_messages(other_owner, default["project_id"])
    assert texts(purged) == ["", ""]
    assert texts(kept)[0] == "How much leave?"


# Deleting a Conversation on request


async def test_an_owner_deletes_a_conversation_on_request(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent = await live_agent(app, owner)
    project_id = agent["project_id"]
    token = await chat_and_feedback(visitor, agent, "My name is Ada; how much leave?", "Ta")
    clock.advance(timedelta(minutes=1))
    await chat(visitor, agent, "Sick days?")
    kept_row, deleted_row = (await listed(owner, project_id))["items"]
    before = await all_metrics(owner, agent)
    clock.advance(timedelta(minutes=5))

    response = await owner.client.delete(conversations_path(owner, project_id, deleted_row["id"]))

    assert response.status_code == 204, response.text
    detail = await opened(owner, project_id, deleted_row["id"])
    now = clock.now().isoformat().replace("+00:00", "Z")
    assert detail["deleted_at"] == now
    assert texts(detail["messages"]) == ["", "", "", ""]
    assert {m["purged_at"] for m in detail["messages"]} == {now}
    assert comments(detail["messages"]) == [None, None]
    assert detail["rating"]["score"] == 4
    rows = {row["id"]: row for row in (await listed(owner, project_id))["items"]}
    assert rows[deleted_row["id"]]["deleted_at"] == now
    assert rows[deleted_row["id"]]["preview"] is None
    assert rows[kept_row["id"]]["deleted_at"] is None
    assert rows[kept_row["id"]]["preview"] == "Sick days?"
    # The metrics are the same; the Visitor's Conversation token no longer works.
    assert await all_metrics(owner, agent) == before
    resumed = await visitor.get(
        f"/api/widget/agents/{agent['public_id']}/conversation",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resumed.status_code == 401
    assert (await send(visitor, agent["public_id"], token, "Hello?")).status_code == 401
    (event,) = await audit_events(owner, "conversation.deleted")
    assert event["actor"]["id"] == owner.member_id
    assert event["target"] == {"type": "conversation", "id": deleted_row["id"]}
    assert event["before"] == {
        "project_id": project_id,
        "agent_id": agent["id"],
        "is_playground": False,
    }
    assert event["after"] == {"purged_messages": 4}
    assert datetime.fromisoformat(event["occurred_at"]) == clock.now()
    # Deleting it again changes and records nothing.
    clock.advance(timedelta(minutes=5))
    again = await owner.client.delete(conversations_path(owner, project_id, deleted_row["id"]))
    assert again.status_code == 204
    assert (await opened(owner, project_id, deleted_row["id"]))["deleted_at"] == now
    assert len(await audit_events(owner, "conversation.deleted")) == 1


async def test_a_playground_conversation_can_be_deleted_too(
    app: FastAPI, owner: SignedUpMember
) -> None:
    agent = await live_agent(app, owner)
    conversation_id = await playground_chat(owner, agent["project_id"], agent["id"], "Testing")

    response = await owner.client.delete(
        conversations_path(owner, agent["project_id"], conversation_id)
    )

    assert response.status_code == 204, response.text
    detail = await opened(owner, agent["project_id"], conversation_id)
    assert texts(detail["messages"]) == ["", ""]
    (event,) = await audit_events(owner, "conversation.deleted")
    assert event["before"]["is_playground"] is True


async def test_only_owners_delete_conversations_and_only_in_their_project(
    app: FastAPI,
    owner: SignedUpMember,
    member_factory: MemberFactory,
    visitor: httpx.AsyncClient,
) -> None:
    editor = await member_factory(owner, "editor")
    agent = await live_agent(app, owner)
    other = await live_agent(app, owner)
    await chat(visitor, agent, "How much leave?")
    (row,) = (await listed(owner, agent["project_id"]))["items"]

    refused = await editor.client.delete(conversations_path(editor, agent["project_id"], row["id"]))
    elsewhere = await owner.client.delete(conversations_path(owner, other["project_id"], row["id"]))
    unknown = await owner.client.delete(
        conversations_path(owner, agent["project_id"], "00000000-0000-0000-0000-000000000000")
    )
    no_project = await owner.client.delete(
        conversations_path(owner, "00000000-0000-0000-0000-000000000000", row["id"])
    )

    assert refused.status_code == 403
    assert (elsewhere.status_code, unknown.status_code, no_project.status_code) == (404, 404, 404)
    (messages,) = await conversation_messages(owner, agent["project_id"])
    assert texts(messages)[0] == "How much leave?"
    assert await audit_events(owner, "conversation.deleted") == []
