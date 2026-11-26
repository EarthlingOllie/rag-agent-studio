"""API seam and task seam: reviewing Calls in the Studio (spec 20, ticket 20-12).

A Visitor calls an Agent through the widget API with the fake voice layer, whose turns are posted
to the turn endpoint as the voice layer posts them. Editors then read the Conversations viewer
(Spoken Messages and interrupted replies marked, a row per Call, a "Has a Call" filter), the
Analytics time series (Calls and Call minutes per day, from the daily rollups) and the Version
KPIs, Live Verdicts and Evaluation prefill, where a spoken reply counts as any reply does. The
rollup and purge Beat tasks are run as tasks.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from tests.agents import agents_path, save_draft
from tests.conftest import ClientFactory, SignedUpMember
from tests.documents import project_path
from tests.fakes.clock import ControllableClock
from tests.integration.test_agent_versions import published
from tests.integration.test_branded_widget import shell_of
from tests.integration.test_calls import (
    calling_agent,
    end_call,
    interrupt,
    secret_of,
    started,
    turn,
)
from tests.integration.test_conversations import listed, opened
from tests.integration.test_embed import boot, conversation_token, send
from tests.integration.test_evaluation_set import prefill
from tests.integration.test_live_verdicts import sampling, scripted
from tests.integration.test_message_feedback import give
from tests.integration.test_playground import echo
from tests.integration.test_playground_calls import a_call as a_playground_call
from tests.integration.test_playground_calls import end_call as end_playground_call
from tests.integration.test_retention import purge, set_window
from tests.integration.test_time_series import points, series
from tests.integration.test_version_metrics import metrics, roll_up


@pytest.fixture
async def visitor(new_client: ClientFactory) -> httpx.AsyncClient:
    """A browser on someone's website: no Studio session."""
    return await new_client()


@pytest.fixture
async def voice(new_client: ClientFactory) -> httpx.AsyncClient:
    """The voice layer's servers: no Studio session, no Conversation token."""
    return await new_client()


async def spoken_turns(
    app: FastAPI,
    agent: dict[str, Any],
    visitor: httpx.AsyncClient,
    voice: httpx.AsyncClient,
    token: str,
    *words: str,
) -> dict[str, Any]:
    """A Call in the Visitor's Conversation saying each of ``words``; the started Call."""
    call = await started(visitor, agent["public_id"], token)
    secret = await secret_of(app, agent)
    for said in words:
        response = await turn(voice, agent["public_id"], secret, call["call_token"], said)
        assert response.status_code == 200, response.text
    return call


async def only_conversation(owner: SignedUpMember, agent: dict[str, Any]) -> dict[str, Any]:
    (row,) = (await listed(owner, agent["project_id"], agent_id=agent["id"]))["items"]
    return await opened(owner, agent["project_id"], row["id"])


# The Conversations viewer


async def test_the_viewer_marks_spoken_messages_their_call_and_interrupted_replies(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    voice: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    agent = await calling_agent(app, owner)
    token = await conversation_token(visitor, agent["public_id"])
    assert (await send(visitor, agent["public_id"], token, "Typed first")).status_code == 200
    call = await spoken_turns(app, agent, visitor, voice, token, "How much leave?", "And notice?")
    assert (await interrupt(visitor, agent["public_id"], token)).status_code == 204
    clock.advance(timedelta(seconds=61))
    assert (await end_call(visitor, agent["public_id"], token)).status_code == 204

    detail = await only_conversation(owner, agent)

    assert [(m["role"], m["spoken"], m["interrupted"]) for m in detail["messages"]] == [
        ("user", False, False),
        ("assistant", False, False),
        ("user", True, False),
        ("assistant", True, False),
        ("user", True, False),
        ("assistant", True, True),
    ]
    assert [m["call_id"] for m in detail["messages"]] == [None, None, *[call["call_id"]] * 4]
    (row,) = detail["calls"]
    assert (row["id"], row["minutes"]) == (call["call_id"], 2)
    assert row["started_at"] <= detail["messages"][2]["created_at"]


async def test_the_has_a_call_filter_narrows_the_list_in_the_project_and_the_agent_view(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    voice: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    agent = await calling_agent(app, owner)
    typed = await conversation_token(visitor, agent["public_id"])
    assert (await send(visitor, agent["public_id"], typed, "Only typed")).status_code == 200
    clock.advance(timedelta(seconds=1))
    called = await conversation_token(visitor, agent["public_id"])
    await spoken_turns(app, agent, visitor, voice, called, "Spoken")
    clock.advance(timedelta(seconds=150))
    assert (await end_call(visitor, agent["public_id"], called)).status_code == 204
    # A Call with nothing said yet still makes a Conversation one with a Call.
    silent = await conversation_token(visitor, agent["public_id"])
    await started(visitor, agent["public_id"], silent)
    project_id = agent["project_id"]

    with_call = await listed(owner, project_id, has_call="true")
    in_agent_view = await listed(owner, project_id, agent_id=agent["id"], has_call="true")
    without = await listed(owner, project_id, has_call="false")
    every = await listed(owner, project_id)

    assert [row["preview"] for row in with_call["items"]] == [None, "Spoken"]
    assert in_agent_view["items"] == with_call["items"]
    assert [row["preview"] for row in without["items"]] == ["Only typed"]
    assert every["total"] == 3
    # Each listed Conversation says how many Calls it had and their minutes so far.
    assert [(row["calls"], row["call_minutes"]) for row in every["items"]] == [
        (1, 0),
        (1, 3),
        (0, 0),
    ]


# Analytics


async def a_call(
    visitor: httpx.AsyncClient, agent: dict[str, Any], clock: ControllableClock, seconds: int
) -> None:
    """A Visitor's Call of ``seconds`` by the platform's clock, ended by the Visitor."""
    token = await conversation_token(visitor, agent["public_id"])
    await started(visitor, agent["public_id"], token)
    clock.advance(timedelta(seconds=seconds))
    assert (await end_call(visitor, agent["public_id"], token)).status_code == 204


async def test_analytics_shows_calls_and_call_minutes_per_day_from_the_rollups(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent = await calling_agent(app, owner)
    # 5 November: Calls of 61 and 30 seconds (2 and 1 minutes, rounded up), and a Playground
    # Call, which never counts.
    await a_call(visitor, agent, clock, 61)
    await a_call(visitor, agent, clock, 30)
    conversation_id, _ = await a_playground_call(owner, agent)
    clock.advance(timedelta(seconds=200))
    assert (await end_playground_call(owner, agent, conversation_id)).status_code == 204
    # 6 November: the 5th is finalised; today a Call of five minutes, and one still open.
    clock.advance(datetime(2026, 11, 6, 1, tzinfo=UTC) - clock.now())
    await roll_up(clock.now())
    await a_call(visitor, agent, clock, 300)
    await started(
        visitor, agent["public_id"], await conversation_token(visitor, agent["public_id"])
    )
    days = {"start": "2026-11-04", "end": "2026-11-06"}

    calls = await series(owner, agent, metric="calls", **days)
    minutes = await series(owner, agent, metric="call_minutes", **days)

    assert points(calls) == [
        ("2026-11-04", "2026-11-04", 0, 0),
        ("2026-11-05", "2026-11-05", 2, 2),
        ("2026-11-06", "2026-11-06", 1, 1),
    ]
    assert points(minutes) == [
        ("2026-11-04", "2026-11-04", 0, 0),
        ("2026-11-05", "2026-11-05", 3, 2),
        ("2026-11-06", "2026-11-06", 5, 1),
    ]
    # Rolling up again changes nothing.
    await roll_up(clock.now())
    assert points(await series(owner, agent, metric="call_minutes", **days)) == points(minutes)


# The Purge


async def test_the_purge_clears_spoken_text_like_typed_and_keeps_calls_minutes_and_voice_cost(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    voice: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    agent = await calling_agent(app, owner)
    assert (await set_window(owner, 7)).status_code == 200
    token = await conversation_token(visitor, agent["public_id"])
    assert (await send(visitor, agent["public_id"], token, "Typed")).status_code == 200
    await spoken_turns(app, agent, visitor, voice, token, "How much leave?")
    assert (await interrupt(visitor, agent["public_id"], token)).status_code == 204
    clock.advance(timedelta(seconds=61))
    assert (await end_call(visitor, agent["public_id"], token)).status_code == 204
    # Eight days on, the rollups are final and the Conversation is older than the window.
    clock.advance(timedelta(days=8))
    await roll_up(clock.now())
    days = {"start": "2026-11-05", "end": "2026-11-05"}
    before = await only_conversation(owner, agent)
    kpis = await metrics(owner, agent, **days)
    minutes = points(await series(owner, agent, metric="call_minutes", **days))

    await purge(clock.now())

    after = await only_conversation(owner, agent)
    assert [m["content"] for m in after["messages"]] == ["", "", "", ""]
    assert all(m["purged_at"] is not None for m in after["messages"])
    # What marks them stays: spoken, their Call and the interruption.
    assert [(m["spoken"], m["call_id"], m["interrupted"]) for m in after["messages"]] == [
        (m["spoken"], m["call_id"], m["interrupted"]) for m in before["messages"]
    ]
    assert after["calls"] == before["calls"]
    (call,) = after["calls"]
    assert (call["minutes"], Decimal(call["voice_cost_usd"])) == (2, Decimal("0.2"))
    assert await metrics(owner, agent, **days) == kpis
    assert (
        points(await series(owner, agent, metric="call_minutes", **days))
        == minutes
        == [("2026-11-05", "2026-11-05", 2, 1)]
    )


# A spoken reply is a reply


async def spoken_reply(owner: SignedUpMember, agent: dict[str, Any]) -> dict[str, Any]:
    """The one spoken Agent Message of the Agent's only Conversation."""
    detail = await only_conversation(owner, agent)
    found: list[dict[str, Any]] = [
        m for m in detail["messages"] if m["role"] == "assistant" and m["spoken"]
    ]
    (reply,) = found
    return reply


async def test_a_spoken_reply_counts_in_the_version_kpis_as_a_typed_one_does(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    voice: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    agent = await calling_agent(app, owner)
    token = await conversation_token(visitor, agent["public_id"])
    await spoken_turns(app, agent, visitor, voice, token, "How much annual leave do I get?")
    replied = await spoken_reply(owner, agent)
    given = await give(visitor, agent["public_id"], token, replied["id"], rating="up")
    assert given.status_code == 200, given.text

    (version,) = (await metrics(owner, agent, start="2026-11-05", end="2026-11-05"))["versions"]

    assert (version["conversations"], version["messages"]) == (1, 1)
    assert version["tokens"]["mean"] == replied["input_tokens"] + replied["output_tokens"]
    assert (version["thumbs_up"]["up"], version["thumbs_up"]["n"]) == (1, 1)


async def test_a_spoken_reply_is_chosen_for_a_live_verdict_and_judged(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    voice: httpx.AsyncClient,
) -> None:
    agent = await calling_agent(app, owner)
    # Replies echo as before; the judge is the fake chat model's, judging by rule.
    scripted(app, echo)
    await sampling(owner, agent, 100)
    token = await conversation_token(visitor, agent["public_id"])
    await spoken_turns(app, agent, visitor, voice, token, "How much annual leave do I get?")
    replied = await spoken_reply(owner, agent)
    detail = await only_conversation(owner, agent)

    response = await owner.client.get(
        f"/api/organisations/{owner.organisation_id}/projects/{agent['project_id']}"
        f"/conversations/{detail['id']}/messages/{replied['id']}/trace"
    )

    assert response.status_code == 200, response.text
    verdict = response.json()["live_verdict"]
    assert verdict["status"] == "judged"
    assert verdict["agent_version_id"] == agent["version"]["id"]


async def test_a_spoken_reply_prefills_an_evaluation_case_with_the_words_it_answered(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    voice: httpx.AsyncClient,
) -> None:
    agent = await calling_agent(app, owner)
    token = await conversation_token(visitor, agent["public_id"])
    await spoken_turns(app, agent, visitor, voice, token, "How much annual leave do I get?")
    replied = await spoken_reply(owner, agent)

    response = await prefill(owner, agent["project_id"], agent["id"], replied["id"])

    assert response.status_code == 200, response.text
    assert response.json()["question"] == "How much annual leave do I get?"


# The Launcher's two choices, reworded per Agent


async def test_the_message_and_call_choices_are_ui_text_in_the_draft_versions_diffs_and_widget(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await calling_agent(app, owner)
    project_id, agent_id = agent["project_id"], agent["id"]
    before = boot(await shell_of(visitor, agent))
    draft = (await owner.client.get(agents_path(owner, project_id, agent_id))).json()["draft"]
    ui_text = {"message_choice": " Type to Hana ", "call_choice": "Talk to Hana"}
    draft["experience"]["ui_text"] |= ui_text

    saved = await save_draft(owner, project_id, agent_id, draft)
    v2 = await published(owner, project_id, agent_id)
    after = boot(await shell_of(visitor, agent))
    diff = await owner.client.get(
        f"{project_path(owner, project_id)}/agents/{agent_id}/diff",
        params={"from": agent["version"]["id"], "to": v2["id"]},
    )

    # The built-in words until a Version holds others.
    assert (before["ui_text"]["message_choice"], before["ui_text"]["call_choice"]) == (None, None)
    assert saved.status_code == 200, saved.text
    assert saved.json()["draft"]["experience"]["ui_text"]["message_choice"] == "Type to Hana"
    assert v2["config"]["experience"]["ui_text"]["call_choice"] == "Talk to Hana"
    assert (after["ui_text"]["message_choice"], after["ui_text"]["call_choice"]) == (
        "Type to Hana",
        "Talk to Hana",
    )
    assert diff.status_code == 200, diff.text
    assert [(c["path"], c["before"], c["after"]) for c in diff.json()["changes"]] == [
        ("experience.ui_text.message_choice", None, "Type to Hana"),
        ("experience.ui_text.call_choice", None, "Talk to Hana"),
    ]
