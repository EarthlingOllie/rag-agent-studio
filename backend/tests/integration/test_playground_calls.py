"""API seam: Playground Calls (spec 20, ticket 20-13).

An Editor calls the Agent's Draft from the Playground. The Call uses the Agent's Call settings and
its remote agent in the voice layer (the scripted fake here); its turns reach the same turn
endpoint as a Visitor's, with a Playground Call token, and are answered by the Draft with the
Project Instructions the Editor picked. Both sides are saved as Spoken Messages of the Playground
Conversation, each reply with its Trace, Searches and sources. Playground Calls stay out of
metrics, the Token Budget and the Call minutes budget; their Voice Cost and their replies' model
Cost count in Organisation cost.

Turns are driven as the voice layer drives them: by posting to the turn endpoint directly, or
through the fake voice layer's own route, as the Studio's scripted call client does.
"""

import json
import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.conversations.models import Call
from app.embed.tokens import TokenSigner
from app.voice.fake import FakeVoiceLayer
from tests.agents import answer_with, create_agent, playground_path, save_draft, start_conversation
from tests.conftest import ClientFactory, MemberFactory, SignedUpMember
from tests.fakes.clock import ControllableClock
from tests.integration.test_agent_versions import knowledgeable_project, published
from tests.integration.test_agentic_streaming import ANSWER, PRE_SEARCH, Scripted, Search
from tests.integration.test_call_limits import minutes, run_reaper
from tests.integration.test_call_settings import add_elevenlabs_credential, calling_on, change
from tests.integration.test_calls import (
    fake_turn_path,
    secret_of,
    spoken,
    started,
    the_call,
    turn,
)
from tests.integration.test_embed import conversation_token
from tests.integration.test_organisation_cost import org_cost
from tests.integration.test_playground_instructions import versions
from tests.integration.test_projects import archive
from tests.integration.test_spoken_replies import pieces
from tests.integration.test_token_budget import usage
from tests.integration.test_version_metrics import metrics

UNAVAILABLE = "This assistant is temporarily unavailable. Please try again later."
CALLS_OFF = (
    "Calling is off for this Agent. Turn it on in Embed & limits, Call settings, to call the Draft."
)
DRAFT_PROMPT = "Answer as the Draft does."
SEARCHING = "Searching the knowledge base… "


@pytest.fixture
async def voice(new_client: ClientFactory) -> httpx.AsyncClient:
    """The voice layer's servers: no Studio session."""
    return await new_client()


@pytest.fixture
async def visitor(new_client: ClientFactory) -> httpx.AsyncClient:
    return await new_client()


@pytest.fixture
def voice_layer(app: FastAPI) -> FakeVoiceLayer:
    layer: FakeVoiceLayer = app.state.voice_layer
    return layer


async def calling_agent(app: FastAPI, owner: SignedUpMember, **draft: Any) -> dict[str, Any]:
    """A live Agent over the leave policy with calling on, whose Draft has moved on since it was
    published: its system prompt is ``DRAFT_PROMPT``."""
    project_id = await knowledgeable_project(app, owner)
    agent: dict[str, Any] = await create_agent(owner, project_id)
    agent["version"] = await published(owner, project_id, agent["id"])
    saved = await save_draft(
        owner,
        project_id,
        agent["id"],
        {"behaviour": {"system_prompt": DRAFT_PROMPT}, "retrieval": {"mode": "automatic"}, **draft},
    )
    assert saved.status_code == 200, saved.text
    await calling_on(owner, agent, (await add_elevenlabs_credential(owner))["id"])
    return agent


def calls_path(member: SignedUpMember, agent: dict[str, Any], conversation_id: str) -> str:
    return playground_path(member, agent["project_id"], agent["id"], conversation_id, "calls")


async def start_call(
    member: SignedUpMember, agent: dict[str, Any], conversation_id: str, **body: Any
) -> httpx.Response:
    return await member.client.post(calls_path(member, agent, conversation_id), json=body or None)


async def a_call(
    member: SignedUpMember, agent: dict[str, Any], **body: Any
) -> tuple[str, dict[str, Any]]:
    """A new Playground Conversation and the Call started in it."""
    conversation = await start_conversation(member, agent["project_id"], agent["id"])
    response = await start_call(member, agent, conversation["id"], **body)
    assert response.status_code == 201, response.text
    call: dict[str, Any] = response.json()
    return conversation["id"], call


async def end_call(
    member: SignedUpMember, agent: dict[str, Any], conversation_id: str
) -> httpx.Response:
    return await member.client.delete(calls_path(member, agent, conversation_id) + "/current")


async def read_back(
    member: SignedUpMember, agent: dict[str, Any], conversation_id: str
) -> dict[str, Any]:
    response = await member.client.get(
        playground_path(member, agent["project_id"], agent["id"], conversation_id)
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def say(
    app: FastAPI, voice: httpx.AsyncClient, agent: dict[str, Any], call: dict[str, Any], words: str
) -> httpx.Response:
    return await turn(
        voice, agent["public_id"], await secret_of(app, agent), call["call_token"], words
    )


def echoed(response: httpx.Response) -> list[str]:
    """The texts the echoing model was given, as the voice layer was told them."""
    return [part[2] for part in json.loads(spoken(response))]


# Starting a Playground Call


async def test_an_editor_calls_the_draft_and_each_spoken_reply_is_saved_with_its_trace(
    app: FastAPI,
    owner: SignedUpMember,
    member_factory: MemberFactory,
    voice: httpx.AsyncClient,
    voice_layer: FakeVoiceLayer,
) -> None:
    agent = await calling_agent(app, owner)
    editor = await member_factory(owner, "editor")

    conversation_id, call = await a_call(editor, agent)

    # What the Studio joins the voice layer with: the Agent's own remote agent, its greeting
    # opening the empty Conversation, and a Playground Call token lasting the Maximum Call length.
    assert call["join"]["voice_layer"] == "fake"
    assert call["join"]["greet"] is True
    assert call["max_call_minutes"] == 10
    assert voice_layer.greetings == ["Hello, you're through to the front desk."]
    assert call["call_token"].startswith("wp1.")
    assert (await read_back(editor, agent, conversation_id))["call_open"] is True

    heard = echoed(await say(app, voice, agent, call, "How much leave do I get?"))

    # The Draft answers, not the Live Version.
    assert DRAFT_PROMPT in heard
    question, reply = (await read_back(editor, agent, conversation_id))["messages"]
    assert [(m["role"], m["spoken"]) for m in (question, reply)] == [
        ("user", True),
        ("assistant", True),
    ]
    assert question["content"] == "How much leave do I get?"
    assert (reply["config_source"], reply["agent_version_id"]) == ("draft", None)
    assert reply["instructions_source"] == "draft"
    assert Decimal(reply["cost_usd"]) > 0
    trace = await editor.client.get(
        playground_path(
            editor,
            agent["project_id"],
            agent["id"],
            conversation_id,
            "messages",
            reply["id"],
            "trace",
        )
    )
    assert trace.status_code == 200, trace.text
    assert trace.json()["config_source"] == "draft"
    (chunk,) = trace.json()["chunks"]
    assert chunk["document_name"] == "leave.txt"
    saved = await the_call(app, call["call_id"])
    assert (saved.agent_version_id, saved.instructions_version_id) == (None, None)


async def test_a_playground_call_answers_with_the_picked_project_instructions(
    app: FastAPI, owner: SignedUpMember, voice: httpx.AsyncClient
) -> None:
    agent = await calling_agent(app, owner)
    ids = await versions(owner, agent["project_id"])

    picked_id, picked = await a_call(owner, agent, instructions_version_id=ids[1])
    draft_id, draft = await a_call(owner, agent, instructions_version_id=None)

    assert "Answer in English." in echoed(await say(app, voice, agent, picked, "Hi"))
    assert "Answer in Welsh." in echoed(await say(app, voice, agent, draft, "Hi"))
    (_, reply) = (await read_back(owner, agent, picked_id))["messages"]
    assert (reply["instructions_source"], reply["instructions_version_number"]) == ("version", 1)
    (_, reply) = (await read_back(owner, agent, draft_id))["messages"]
    assert (reply["instructions_source"], reply["instructions_version_id"]) == ("draft", None)


async def test_an_instructions_version_of_another_project_is_refused(
    app: FastAPI, owner: SignedUpMember
) -> None:
    agent = await calling_agent(app, owner)
    conversation = await start_conversation(owner, agent["project_id"], agent["id"])

    response = await start_call(
        owner, agent, conversation["id"], instructions_version_id=str(uuid.uuid4())
    )

    assert response.status_code == 422, response.text
    assert response.json()["detail"] == "That Instructions Version isn't one of this Project's."


async def test_with_calling_off_the_playground_says_how_to_turn_it_on(
    app: FastAPI, owner: SignedUpMember
) -> None:
    agent = await calling_agent(app, owner)
    turned_off = await change(owner, agent, calls_enabled=False)
    assert turned_off.status_code == 200, turned_off.text
    conversation = await start_conversation(owner, agent["project_id"], agent["id"])

    response = await start_call(owner, agent, conversation["id"])

    assert (response.status_code, response.json()["detail"]) == (409, CALLS_OFF)


async def test_one_call_at_a_time_in_a_playground_conversation(
    app: FastAPI, owner: SignedUpMember
) -> None:
    agent = await calling_agent(app, owner)
    conversation_id, _ = await a_call(owner, agent)

    again = await start_call(owner, agent, conversation_id)

    assert again.status_code == 409, again.text
    assert again.json()["detail"] == (
        "This Playground Conversation already has a Call open. End it first."
    )


async def test_a_voice_layer_that_cant_start_the_call_records_none(
    app: FastAPI, owner: SignedUpMember, voice_layer: FakeVoiceLayer
) -> None:
    agent = await calling_agent(app, owner)
    conversation = await start_conversation(owner, agent["project_id"], agent["id"])
    voice_layer.failing = True

    response = await start_call(owner, agent, conversation["id"])

    assert response.status_code == 502, response.text
    assert (await read_back(owner, agent, conversation["id"]))["call_open"] is False


async def test_a_call_in_a_conversation_with_messages_opens_with_the_draft_listening(
    app: FastAPI, owner: SignedUpMember, voice: httpx.AsyncClient, voice_layer: FakeVoiceLayer
) -> None:
    agent = await calling_agent(app, owner)
    conversation_id, call = await a_call(owner, agent)
    await say(app, voice, agent, call, "Hello?")
    assert (await end_call(owner, agent, conversation_id)).status_code == 204

    again = await start_call(owner, agent, conversation_id)

    assert again.status_code == 201, again.text
    assert again.json()["join"]["greet"] is False
    assert len(voice_layer.greetings) == 1


async def test_an_archived_agent_or_project_starts_no_playground_call(
    app: FastAPI, owner: SignedUpMember
) -> None:
    agent = await calling_agent(app, owner)
    conversation = await start_conversation(owner, agent["project_id"], agent["id"])
    archived = await owner.client.post(
        playground_path(owner, agent["project_id"], agent["id"]).removesuffix(
            "/playground/conversations"
        )
        + "/archive"
    )
    assert archived.status_code == 200, archived.text

    by_agent = await start_call(owner, agent, conversation["id"])
    await archive(owner, agent["project_id"])
    by_project = await start_call(owner, agent, conversation["id"])

    assert (by_agent.status_code, by_project.status_code) == (409, 409)


async def test_a_playground_call_is_not_found_outside_its_agent(
    app: FastAPI, owner: SignedUpMember
) -> None:
    agent = await calling_agent(app, owner)
    other = await create_agent(owner, agent["project_id"], name="Other")
    conversation = await start_conversation(owner, agent["project_id"], other["id"])

    started_elsewhere = await start_call(owner, agent, conversation["id"])
    ended_elsewhere = await end_call(owner, agent, conversation["id"])

    assert (started_elsewhere.status_code, ended_elsewhere.status_code) == (404, 404)


# Its turns


async def test_an_agentic_drafts_searches_show_their_queries_and_its_sources(
    app: FastAPI, owner: SignedUpMember, voice: httpx.AsyncClient
) -> None:
    agent = await calling_agent(app, owner, retrieval={"mode": "agentic"})
    answer_with(
        app,
        Scripted(
            [*PRE_SEARCH, Search("leave")], ["Let me check more. ", Search("annual leave")], ANSWER
        ),
    )
    conversation_id, call = await a_call(owner, agent)

    heard = spoken(await say(app, voice, agent, call, "How much leave?"))

    assert heard == SEARCHING + "You get 25 days of annual leave a year."
    (_, reply) = (await read_back(owner, agent, conversation_id))["messages"]
    assert reply["content"] == "".join(ANSWER)
    assert reply["searches"] == ["leave", "annual leave"]
    (cited,) = reply["citations"]
    assert (cited["label"], cited["document_name"], cited["rank"]) == ("C1", "leave.txt", 1)
    assert cited["chunk_id"] is not None


async def test_a_reply_that_made_no_search_and_cited_nothing_shows_neither(
    app: FastAPI, owner: SignedUpMember, voice: httpx.AsyncClient
) -> None:
    agent = await calling_agent(app, owner)
    answer_with(app, pieces("Hello! ", "How can I help?"))
    conversation_id, call = await a_call(owner, agent)
    await say(app, voice, agent, call, "Hi")

    question, reply = (await read_back(owner, agent, conversation_id))["messages"]

    assert (question["searches"], question["citations"]) == ([], [])
    assert (reply["searches"], reply["citations"]) == ([], [])


async def test_the_fake_voice_layer_holds_a_playground_call_through_the_turn_endpoint(
    app: FastAPI, owner: SignedUpMember, voice: httpx.AsyncClient
) -> None:
    agent = await calling_agent(app, owner)
    conversation_id, call = await a_call(owner, agent)

    response = await voice.post(
        fake_turn_path(call["join"]["conversation_token"]),
        json={"words": "How much leave?", "call_token": call["call_token"]},
    )

    assert response.status_code == 200, response.text
    assert DRAFT_PROMPT in response.json()["agent_response"]
    assert len((await read_back(owner, agent, conversation_id))["messages"]) == 2


async def test_a_tampered_ended_or_cross_kind_playground_call_token_is_refused(
    app: FastAPI, owner: SignedUpMember, voice: httpx.AsyncClient, visitor: httpx.AsyncClient
) -> None:
    agent = await calling_agent(app, owner)
    conversation_id, call = await a_call(owner, agent)
    token = await conversation_token(visitor, agent["public_id"])
    visitors_call = await started(visitor, agent["public_id"], token)
    signer: TokenSigner = app.state.widget_tokens
    expires_at = app.state.clock.now() + timedelta(minutes=5)
    # A Playground Call token for a Visitor's Call, and a Call token for a Playground Call.
    forged_playground = signer.playground_call(
        uuid.UUID(visitors_call["call_id"]),
        (await the_call(app, visitors_call["call_id"])).conversation_id,
        expires_at=expires_at,
    )
    forged_visitor = signer.call(
        uuid.UUID(call["call_id"]), uuid.UUID(conversation_id), expires_at=expires_at
    )

    tampered = await say(app, voice, agent, {"call_token": call["call_token"] + "x"}, "Hi")
    as_playground = await say(app, voice, agent, {"call_token": forged_playground}, "Hi")
    as_visitor = await say(app, voice, agent, {"call_token": forged_visitor}, "Hi")
    assert (await end_call(owner, agent, conversation_id)).status_code == 204
    ended = await say(app, voice, agent, call, "Hi")

    assert [r.status_code for r in (tampered, as_playground, as_visitor, ended)] == [403] * 4
    assert (await read_back(owner, agent, conversation_id))["messages"] == []


async def test_a_draft_that_cant_answer_speaks_the_unavailable_text_and_ends_the_call(
    app: FastAPI, owner: SignedUpMember, voice: httpx.AsyncClient
) -> None:
    agent = await calling_agent(app, owner)
    _, call = await a_call(owner, agent)
    await archive(owner, agent["project_id"])

    response = await say(app, voice, agent, call, "Hi")

    assert spoken(response) == UNAVAILABLE
    saved = await the_call(app, call["call_id"])
    assert saved.end_reason == "unavailable"
    assert saved.ended_at is not None


# Ending, and what a Playground Call counts toward


async def test_the_editor_ends_the_call_and_it_is_costed_and_kept_out_of_the_budgets(
    app: FastAPI,
    owner: SignedUpMember,
    voice: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    agent = await calling_agent(app, owner)
    conversation_id, call = await a_call(owner, agent)
    await say(app, voice, agent, call, "How much leave?")
    open_minutes = (await minutes(owner, agent))["minutes_used"]
    clock.advance(timedelta(seconds=50))
    await say(app, voice, agent, call, "And notice?")
    clock.advance(timedelta(seconds=11))

    ended = await end_call(owner, agent, conversation_id)
    again = await end_call(owner, agent, conversation_id)

    assert (ended.status_code, again.status_code) == (204, 204)
    saved = await the_call(app, call["call_id"])
    # 61 seconds rounds up to 2 minutes, at ElevenLabs' platform price of $0.10 a minute.
    assert (saved.end_reason, saved.minutes) == ("editor", 2)
    assert saved.voice_cost_usd == Decimal("0.2")
    assert (await read_back(owner, agent, conversation_id))["call_open"] is False
    # Neither the open Call nor the ended one counts toward the Call minutes budget, and its
    # replies use none of the Token Budget.
    assert open_minutes == 0
    assert (await minutes(owner, agent))["minutes_used"] == 0
    assert (await usage(owner, agent))["tokens_used"] == 0
    # Kept out of the Agent's metrics.
    (kpis,) = (await metrics(owner, agent, start="2026-11-05", end="2026-11-05"))["versions"]
    assert (kpis["conversations"], kpis["messages"]) == (0, 0)
    assert Decimal(kpis["cost"]["total_usd"]) == 0
    # Its Voice Cost and its replies' model Cost count in Organisation cost.
    (row,) = (await org_cost(owner, start="2026-11-05", end="2026-11-05", group_by="agent"))["rows"]
    assert Decimal(row["voice_usd"]) == Decimal("0.2")
    assert Decimal(row["playground_usd"]) > 0
    assert Decimal(row["visitor_usd"]) == 0


async def test_a_silent_playground_call_is_ended_by_the_platform(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock
) -> None:
    agent = await calling_agent(app, owner)
    _, call = await a_call(owner, agent)
    clock.advance(timedelta(seconds=61))

    await run_reaper(clock.now())

    saved: Call = await the_call(app, call["call_id"])
    assert (saved.end_reason, saved.minutes) == ("silence", 1)
