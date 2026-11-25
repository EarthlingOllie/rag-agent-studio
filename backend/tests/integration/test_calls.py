"""API seam: a Visitor calls an Agent (spec 20, ticket 20-04).

The widget starts a Call in its Conversation with the Conversation token and gets back what the
browser joins the voice layer with, and a Call token. The voice layer (the scripted fake here)
then sends each turn to the turn endpoint, the OpenAI-compatible chat completions route under
the Agent's public ID, with the Agent's per-Agent secret and the Call token as extra body. Both
sides of a spoken turn are saved as Spoken Messages, and the widget ends the Call.

Turns are driven as the voice layer drives them: by posting to the turn endpoint directly, or
through the fake voice layer's own route, as the widget's scripted call client does.
"""

import json
import re
import uuid
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic_ai.exceptions import ModelAuthenticationError, ModelHTTPError
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo
from sqlalchemy import func, select

from app.agents.models import Agent
from app.conversations.models import Call, Conversation, Message
from app.embed.tokens import TokenSigner
from app.mail.outbox import OutboxMailer
from app.voice.fake import FakeVoiceLayer
from app.voice.remote import call_secret
from tests.agents import answer_with, create_agent, parse_sse, save_draft
from tests.conftest import ClientFactory, SignedUpMember
from tests.fakes.clock import ControllableClock
from tests.integration.test_agent_archive import archive as archive_agent
from tests.integration.test_agent_versions import knowledgeable_project, published
from tests.integration.test_call_settings import add_elevenlabs_credential, calling_on
from tests.integration.test_conversations import trace_of
from tests.integration.test_embed import boot, conversation_token, live_agent, send, tamper
from tests.integration.test_input_guardrail import ATTACK, guard
from tests.integration.test_playground import echo
from tests.integration.test_playground_errors import failing
from tests.integration.test_widget_resume import bearer, resume
from tests.integration.test_widget_resume import end as end_conversation

UNAVAILABLE = "This assistant is temporarily unavailable. Please try again later."
REFUSAL = "Sorry, I can't help with that request."


@pytest.fixture
async def visitor(new_client: ClientFactory) -> httpx.AsyncClient:
    """A browser on someone's website: no Studio session."""
    return await new_client()


@pytest.fixture
async def voice(new_client: ClientFactory) -> httpx.AsyncClient:
    """The voice layer's servers: no Studio session, no Conversation token."""
    return await new_client()


@pytest.fixture
def voice_layer(app: FastAPI) -> FakeVoiceLayer:
    layer: FakeVoiceLayer = app.state.voice_layer
    return layer


async def calling_agent(app: FastAPI, owner: SignedUpMember) -> dict[str, Any]:
    """A live Agent over the leave policy, answering with the echoing model, with calling on."""
    project_id = await knowledgeable_project(app, owner)
    created: dict[str, Any] = await create_agent(owner, project_id)
    created["version"] = await published(owner, project_id, created["id"])
    credential = await add_elevenlabs_credential(owner)
    await calling_on(owner, created, credential["id"])
    return created


def calls_path(public_id: str, *rest: str) -> str:
    return "/".join([f"/api/widget/agents/{public_id}/conversation/calls", *rest])


def turn_path(public_id: str) -> str:
    return f"/api/widget/agents/{public_id}/llm/v1/chat/completions"


async def start_call(visitor: httpx.AsyncClient, public_id: str, token: str) -> httpx.Response:
    return await visitor.post(calls_path(public_id), headers=bearer(token))


async def started(visitor: httpx.AsyncClient, public_id: str, token: str) -> dict[str, Any]:
    response = await start_call(visitor, public_id, token)
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def end_call(visitor: httpx.AsyncClient, public_id: str, token: str) -> httpx.Response:
    return await visitor.delete(calls_path(public_id, "current"), headers=bearer(token))


async def secret_of(app: FastAPI, agent: dict[str, Any]) -> str:
    async with app.state.sessionmaker() as session:
        row = await session.get_one(Agent, uuid.UUID(agent["id"]))
        found = call_secret(app.state.envelope, row)
    assert found is not None
    return found


async def turn(
    voice: httpx.AsyncClient,
    public_id: str,
    secret: str,
    call_token: str,
    words: str,
    *,
    history: list[dict[str, Any]] | None = None,
) -> httpx.Response:
    """A turn as the voice layer sends it: OpenAI chat completions with its own history."""
    return await voice.post(
        turn_path(public_id),
        headers={"Authorization": f"Bearer {secret}"},
        json={
            "model": "custom-llm",
            "stream": True,
            "messages": [*(history or []), {"role": "user", "content": words}],
            "elevenlabs_extra_body": {"call_token": call_token},
        },
    )


def spoken(response: httpx.Response) -> str:
    """The text a turn endpoint stream gives the voice layer to speak, checking its framing."""
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    lines = [line for line in response.text.split("\n\n") if line]
    assert lines[-1] == "data: [DONE]"
    chunks = [json.loads(line.removeprefix("data: ")) for line in lines[:-1]]
    assert {c["object"] for c in chunks} == {"chat.completion.chunk"}
    assert len({c["id"] for c in chunks}) == 1
    assert chunks[-1]["choices"] == [{"index": 0, "delta": {}, "finish_reason": "stop"}]
    for chunk in chunks[:-1]:
        assert chunk["choices"][0]["finish_reason"] is None
        assert chunk["choices"][0]["delta"]["role"] == "assistant"
    return "".join(c["choices"][0]["delta"]["content"] for c in chunks[:-1])


async def call_count(app: FastAPI, agent: dict[str, Any]) -> int:
    """How many Calls the Agent's Conversations have recorded."""
    async with app.state.sessionmaker() as session:
        return int(
            await session.scalar(
                select(func.count())
                .select_from(Call)
                .join(Conversation, Conversation.id == Call.conversation_id)
                .where(Conversation.agent_id == uuid.UUID(agent["id"]))
            )
            or 0
        )


async def the_call(app: FastAPI, call_id: str) -> Call:
    async with app.state.sessionmaker() as session:
        found: Call = await session.get_one(Call, uuid.UUID(call_id))
    return found


# Whether the Agent takes Calls


async def test_the_shell_says_whether_the_agent_takes_calls(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    typing_only = await live_agent(owner)
    calling = await calling_agent(app, owner)

    off = boot(await visitor.get(f"/widget/a/{typing_only['public_id']}"))
    on = boot(await visitor.get(f"/widget/a/{calling['public_id']}"))

    assert (off["calls"], on["calls"]) == (False, True)


# Starting a Call


async def test_a_visitor_starts_a_call_and_gets_what_the_browser_joins_with_and_a_call_token(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    voice_layer: FakeVoiceLayer,
    clock: ControllableClock,
) -> None:
    agent = await calling_agent(app, owner)
    token = await conversation_token(visitor, agent["public_id"])

    body = await started(visitor, agent["public_id"], token)

    ((remote_agent_id, join_token),) = voice_layer.calls
    assert body["join"] == {"voice_layer": "fake", "conversation_token": join_token}
    assert remote_agent_id in voice_layer.remote_agents
    # The Call token is signed and bound to the Call and its Conversation.
    call = await the_call(app, body["call_id"])
    signer: TokenSigner = app.state.widget_tokens
    assert signer.call_ids(body["call_token"], now=clock.now()) == (
        call.id,
        call.conversation_id,
    )
    # The Call records its Conversation, when it started and the Version that was Live.
    assert (call.started_at, call.ended_at) == (clock.now(), None)
    assert str(call.agent_version_id) == agent["version"]["id"]


async def test_an_agent_with_calling_off_takes_no_calls(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await live_agent(owner)
    token = await conversation_token(visitor, agent["public_id"])

    response = await start_call(visitor, agent["public_id"], token)

    assert (response.status_code, response.json()) == (
        409,
        {"detail": "This assistant doesn't take Calls."},
    )
    assert await call_count(app, agent) == 0


async def test_starting_a_call_needs_a_good_conversation_token(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await calling_agent(app, owner)
    token = await conversation_token(visitor, agent["public_id"])

    for authorization in ({}, bearer(tamper(token)), {"Authorization": f"Basic {token}"}):
        response = await visitor.post(calls_path(agent["public_id"]), headers=authorization)
        assert response.status_code == 401, response.text
    assert await call_count(app, agent) == 0


async def test_a_retired_agent_takes_no_calls(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await calling_agent(app, owner)
    token = await conversation_token(visitor, agent["public_id"])
    await archive_agent(owner, agent["project_id"], agent["id"])

    response = await start_call(visitor, agent["public_id"], token)

    assert response.status_code == 404
    assert response.json()["detail"] == "This assistant is no longer available."


async def test_admission_control_refuses_a_call_over_the_rate_limit(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await calling_agent(app, owner)
    await owner.client.patch(
        f"/api/organisations/{owner.organisation_id}/projects/{agent['project_id']}"
        f"/agents/{agent['id']}/operational-settings",
        json={"conversation_messages_per_minute": 1},
    )
    token = await conversation_token(visitor, agent["public_id"])
    await started(visitor, agent["public_id"], token)

    response = await start_call(visitor, agent["public_id"], token)

    assert (response.status_code, response.json()) == (
        503,
        {"detail": UNAVAILABLE, "reason": "rate_limited"},
    )
    assert await call_count(app, agent) == 1


async def test_admission_control_refuses_a_call_once_the_token_budget_is_spent(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await calling_agent(app, owner)
    path = (
        f"/api/organisations/{owner.organisation_id}/projects/{agent['project_id']}"
        f"/agents/{agent['id']}"
    )
    await owner.client.patch(f"{path}/operational-settings", json={"daily_token_budget": 1})
    token = await conversation_token(visitor, agent["public_id"])
    await send(visitor, agent["public_id"], token, "How much leave?")  # spends the budget

    response = await start_call(visitor, agent["public_id"], token)

    assert (response.status_code, response.json()) == (
        503,
        {"detail": UNAVAILABLE, "reason": "budget_exhausted"},
    )
    assert (await owner.client.get(path)).json()["budget_exhausted"] is True
    outbox: OutboxMailer = app.state.mailer
    assert [e.subject for e in outbox.sent if "Token Budget" in e.subject] != []
    assert await call_count(app, agent) == 0


async def test_a_voice_layer_that_cant_start_the_call_gets_the_unavailable_text(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, voice_layer: FakeVoiceLayer
) -> None:
    agent = await calling_agent(app, owner)
    token = await conversation_token(visitor, agent["public_id"])
    voice_layer.failing = True

    response = await start_call(visitor, agent["public_id"], token)

    assert (response.status_code, response.json()) == (
        503,
        {"detail": UNAVAILABLE, "reason": "voice_unavailable"},
    )
    assert await call_count(app, agent) == 0


# The turn endpoint


async def test_a_spoken_turn_is_answered_by_the_live_version_and_saved_as_spoken_messages(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    voice: httpx.AsyncClient,
) -> None:
    agent = await calling_agent(app, owner)
    token = await conversation_token(visitor, agent["public_id"])
    typed = parse_sse((await send(visitor, agent["public_id"], token, "How much leave?")).text)
    call = await started(visitor, agent["public_id"], token)
    secret = await secret_of(app, agent)

    response = await turn(
        voice,
        agent["public_id"],
        secret,
        call["call_token"],
        "And how much notice do I give?",
        history=[
            {"role": "system", "content": "The voice layer's own prompt."},
            {"role": "user", "content": "Words the voice layer remembers."},
            {"role": "assistant", "content": "A reply the voice layer remembers."},
        ],
    )

    # Only the last user message is taken; the earlier typed turn comes from the Conversation.
    parts = [part[2] for part in json.loads(spoken(response))]
    assert "And how much notice do I give?" in parts[-1]
    assert "How much leave?" in parts
    assert not any("voice layer" in part for part in parts)
    # Both sides are saved as Spoken Messages, after the typed ones.
    messages = (await resume(visitor, agent["public_id"], token)).json()["messages"]
    assert [(m["role"], m["spoken"]) for m in messages] == [
        ("user", False),
        ("assistant", False),
        ("user", True),
        ("assistant", True),
    ]
    assert messages[1]["id"] == typed[-1][1]["message_id"]
    assert messages[2]["content"] == "And how much notice do I give?"
    # The echoing reply cites nothing.
    assert messages[3]["citations"] == []
    # The reply has its Trace, Cost and Message attribution, like a typed one.
    conversations = await owner.client.get(
        f"/api/organisations/{owner.organisation_id}/projects/{agent['project_id']}/conversations"
    )
    (item,) = conversations.json()["items"]
    trace = await owner.client.get(
        trace_of(owner, agent["project_id"], item["id"], messages[3]["id"])
    )
    assert trace.status_code == 200, trace.text
    assert (trace.json()["config_source"], trace.json()["agent_version_id"]) == (
        "version",
        agent["version"]["id"],
    )
    async with app.state.sessionmaker() as session:
        saved = await session.get_one(Message, uuid.UUID(messages[3]["id"]))
        question = await session.get_one(Message, uuid.UUID(messages[2]["id"]))
    assert saved.cost_usd is not None
    assert (str(saved.call_id), str(question.call_id)) == (call["call_id"], call["call_id"])


async def test_the_words_may_come_as_content_parts(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, voice: httpx.AsyncClient
) -> None:
    agent = await calling_agent(app, owner)
    token = await conversation_token(visitor, agent["public_id"])
    call = await started(visitor, agent["public_id"], token)

    response = await voice.post(
        turn_path(agent["public_id"]),
        headers={"Authorization": f"Bearer {await secret_of(app, agent)}"},
        json={
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "How much "},
                        {"type": "image_url", "image_url": {"url": "https://example.test/a.png"}},
                        {"type": "text", "text": "leave?"},
                    ],
                }
            ],
            "elevenlabs_extra_body": {"call_token": call["call_token"]},
        },
    )

    assert "How much leave?" in json.loads(spoken(response))[-1][2]


@pytest.mark.parametrize(
    ("messages", "detail"),
    [
        ([{"role": "system", "content": "No user turn."}], "The last user message has no words."),
        ([{"role": "user", "content": "   "}], "The last user message has no words."),
        ([{"role": "user", "content": None}], "The last user message has no words."),
        (
            [{"role": "user", "content": "x" * 5000}],
            "The last user message is longer than 4000 characters.",
        ),
    ],
)
async def test_a_turn_without_usable_words_is_refused_without_a_model_call(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    voice: httpx.AsyncClient,
    messages: list[dict[str, Any]],
    detail: str,
) -> None:
    agent = await calling_agent(app, owner)
    built = answer_with(app, echo)
    token = await conversation_token(visitor, agent["public_id"])
    call = await started(visitor, agent["public_id"], token)

    response = await voice.post(
        turn_path(agent["public_id"]),
        headers={"Authorization": f"Bearer {await secret_of(app, agent)}"},
        json={"messages": messages, "elevenlabs_extra_body": {"call_token": call["call_token"]}},
    )

    assert (response.status_code, response.json()["detail"]) == (422, detail)
    assert built == []


async def test_a_wrong_secret_is_refused_without_a_model_call(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    voice: httpx.AsyncClient,
) -> None:
    agent = await calling_agent(app, owner)
    other = await calling_agent(app, owner)
    built = answer_with(app, echo)
    token = await conversation_token(visitor, agent["public_id"])
    call = await started(visitor, agent["public_id"], token)
    secret = await secret_of(app, agent)
    other_secret = await secret_of(app, other)

    refused = [
        await turn(voice, agent["public_id"], tamper(secret), call["call_token"], "Hi"),
        await turn(voice, agent["public_id"], other_secret, call["call_token"], "Hi"),
        await turn(voice, agent["public_id"], "", call["call_token"], "Hi"),
        await voice.post(
            turn_path(agent["public_id"]),
            headers={"Authorization": f"Basic {secret}"},
            json={"messages": [{"role": "user", "content": "Hi"}]},
        ),
        await turn(voice, "agt_nobody", secret, call["call_token"], "Hi"),
    ]

    assert [(r.status_code, r.json()["detail"]) for r in refused] == [
        (401, "The API key isn't this Agent's.")
    ] * len(refused)
    assert built == []


async def test_an_agent_with_calling_off_has_no_secret_to_answer_with(
    app: FastAPI, owner: SignedUpMember, voice: httpx.AsyncClient
) -> None:
    agent = await live_agent(owner)

    response = await turn(voice, agent["public_id"], "anything", "wk1.x.y.z.sig", "Hi")

    assert response.status_code == 401


async def test_a_tampered_expired_or_cross_conversation_call_token_is_refused_without_a_model_call(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    voice: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    agent = await calling_agent(app, owner)
    other_agent = await calling_agent(app, owner)
    built = answer_with(app, echo)
    token = await conversation_token(visitor, agent["public_id"])
    call = await started(visitor, agent["public_id"], token)
    second_token = await conversation_token(visitor, agent["public_id"])
    second = await started(visitor, agent["public_id"], second_token)
    elsewhere_token = await conversation_token(visitor, other_agent["public_id"])
    elsewhere = await started(visitor, other_agent["public_id"], elsewhere_token)
    secret = await secret_of(app, agent)
    signer: TokenSigner = app.state.widget_tokens
    # A correctly signed token binding this Call to another of the Agent's Conversations.
    crossed = signer.call(
        uuid.UUID(call["call_id"]),
        (await the_call(app, second["call_id"])).conversation_id,
        now=clock.now(),
    )

    refused = [
        await turn(voice, agent["public_id"], secret, tamper(call["call_token"]), "Hi"),
        await turn(voice, agent["public_id"], secret, crossed, "Hi"),
        # A good token of another Agent's Call.
        await turn(voice, agent["public_id"], secret, elsewhere["call_token"], "Hi"),
        await turn(voice, agent["public_id"], secret, "", "Hi"),
        await voice.post(
            turn_path(agent["public_id"]),
            headers={"Authorization": f"Bearer {secret}"},
            json={"messages": [{"role": "user", "content": "Hi"}]},
        ),
    ]
    clock.advance(timedelta(minutes=10, seconds=1))
    refused.append(await turn(voice, agent["public_id"], secret, call["call_token"], "Hi"))

    assert [(r.status_code, r.json()["detail"]) for r in refused] == [
        (403, "The Call token is invalid or expired, or the Call has ended.")
    ] * len(refused)
    assert built == []


async def test_a_call_token_lasts_the_maximum_call_length(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    voice: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    agent = await calling_agent(app, owner)
    token = await conversation_token(visitor, agent["public_id"])
    call = await started(visitor, agent["public_id"], token)
    clock.advance(timedelta(minutes=10))

    response = await turn(
        voice, agent["public_id"], await secret_of(app, agent), call["call_token"], "Hi"
    )

    assert response.status_code == 200, response.text


async def test_an_ended_call_takes_no_more_turns(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    voice: httpx.AsyncClient,
) -> None:
    agent = await calling_agent(app, owner)
    built = answer_with(app, echo)
    token = await conversation_token(visitor, agent["public_id"])
    call = await started(visitor, agent["public_id"], token)
    await end_call(visitor, agent["public_id"], token)

    response = await turn(
        voice, agent["public_id"], await secret_of(app, agent), call["call_token"], "Hi"
    )

    assert response.status_code == 403
    assert built == []


async def test_a_blocked_turn_speaks_the_refusal_text(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, voice: httpx.AsyncClient
) -> None:
    agent = await calling_agent(app, owner)
    await save_draft(
        owner,
        agent["project_id"],
        agent["id"],
        {"guardrails": {"input_mode": "block", "refusal_text": REFUSAL}},
    )
    await published(owner, agent["project_id"], agent["id"])
    guard(app)
    token = await conversation_token(visitor, agent["public_id"])
    call = await started(visitor, agent["public_id"], token)

    response = await turn(
        voice, agent["public_id"], await secret_of(app, agent), call["call_token"], ATTACK
    )

    assert spoken(response) == REFUSAL


async def leaks(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
    yield "My secret is " + re.findall(r"\b[0-9a-f]{20}\b", str(messages))[0]


async def test_a_leaking_reply_speaks_the_replacement(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, voice: httpx.AsyncClient
) -> None:
    agent = await calling_agent(app, owner)
    await save_draft(
        owner, agent["project_id"], agent["id"], {"behaviour": {"fallback_text": "Can't say."}}
    )
    await published(owner, agent["project_id"], agent["id"])
    answer_with(app, leaks)
    token = await conversation_token(visitor, agent["public_id"])
    call = await started(visitor, agent["public_id"], token)

    response = await turn(
        voice, agent["public_id"], await secret_of(app, agent), call["call_token"], "Secret?"
    )

    assert spoken(response).endswith("Can't say.")


async def test_a_provider_failure_speaks_the_unavailable_text(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, voice: httpx.AsyncClient
) -> None:
    agent = await calling_agent(app, owner)
    error = ModelHTTPError.for_category(
        ModelAuthenticationError, status_code=401, model_name="gpt-4.1-mini"
    )
    answer_with(app, failing(error))
    token = await conversation_token(visitor, agent["public_id"])
    call = await started(visitor, agent["public_id"], token)

    response = await turn(
        voice, agent["public_id"], await secret_of(app, agent), call["call_token"], "Hi"
    )

    assert spoken(response) == UNAVAILABLE


async def test_a_turn_over_the_rate_limit_speaks_the_unavailable_text(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, voice: httpx.AsyncClient
) -> None:
    agent = await calling_agent(app, owner)
    await owner.client.patch(
        f"/api/organisations/{owner.organisation_id}/projects/{agent['project_id']}"
        f"/agents/{agent['id']}/operational-settings",
        json={"conversation_messages_per_minute": 1},
    )
    token = await conversation_token(visitor, agent["public_id"])
    # Starting the Call takes the minute's one place.
    call = await started(visitor, agent["public_id"], token)

    response = await turn(
        voice, agent["public_id"], await secret_of(app, agent), call["call_token"], "Hi"
    )

    assert spoken(response) == UNAVAILABLE
    assert (await resume(visitor, agent["public_id"], token)).json()["messages"] == []


async def test_a_turn_for_an_agent_retired_mid_call_is_refused(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, voice: httpx.AsyncClient
) -> None:
    agent = await calling_agent(app, owner)
    token = await conversation_token(visitor, agent["public_id"])
    call = await started(visitor, agent["public_id"], token)
    secret = await secret_of(app, agent)
    async with app.state.sessionmaker() as session:
        row = await session.get_one(Agent, uuid.UUID(agent["id"]))
        row.live_version_id = None
        await session.commit()

    response = await turn(voice, agent["public_id"], secret, call["call_token"], "Hi")

    assert response.status_code == 404


async def test_a_turn_without_a_model_to_answer_with_is_unavailable(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, voice: httpx.AsyncClient
) -> None:
    agent = await live_agent(owner)  # The Organisation has no Default Model.
    credential = await add_elevenlabs_credential(owner)
    await calling_on(owner, agent, credential["id"])
    token = await conversation_token(visitor, agent["public_id"])
    call = await started(visitor, agent["public_id"], token)

    response = await turn(
        voice, agent["public_id"], await secret_of(app, agent), call["call_token"], "Hi"
    )

    assert (response.status_code, response.json()["detail"]) == (503, UNAVAILABLE)


# Ending a Call


async def test_ending_a_call_records_its_end_and_keeps_the_spoken_messages(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    voice: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    agent = await calling_agent(app, owner)
    token = await conversation_token(visitor, agent["public_id"])
    call = await started(visitor, agent["public_id"], token)
    await turn(voice, agent["public_id"], await secret_of(app, agent), call["call_token"], "Hi")
    clock.advance(timedelta(seconds=90))

    response = await end_call(visitor, agent["public_id"], token)

    assert response.status_code == 204
    assert (await the_call(app, call["call_id"])).ended_at == clock.now()
    messages = (await resume(visitor, agent["public_id"], token)).json()["messages"]
    assert [m["spoken"] for m in messages] == [True, True]
    # Ending again changes nothing.
    clock.advance(timedelta(seconds=5))
    assert (await end_call(visitor, agent["public_id"], token)).status_code == 204
    assert (await the_call(app, call["call_id"])).ended_at == clock.now() - timedelta(seconds=5)


async def test_ending_a_call_needs_a_good_conversation_token(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await calling_agent(app, owner)
    token = await conversation_token(visitor, agent["public_id"])
    call = await started(visitor, agent["public_id"], token)

    response = await end_call(visitor, agent["public_id"], tamper(token))

    assert response.status_code == 401
    assert (await the_call(app, call["call_id"])).ended_at is None


async def test_an_ended_conversations_token_starts_no_call(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await calling_agent(app, owner)
    token = await conversation_token(visitor, agent["public_id"])
    await end_conversation(visitor, agent["public_id"], token)

    assert (await start_call(visitor, agent["public_id"], token)).status_code == 401


# The scripted fake voice layer, as the widget's scripted call client drives it


def fake_turn_path(join_token: str) -> str:
    return f"/api/widget/fake-voice/calls/{join_token}/turns"


async def test_the_fake_voice_layer_holds_a_scripted_call_through_the_turn_endpoint(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await calling_agent(app, owner)
    token = await conversation_token(visitor, agent["public_id"])
    call = await started(visitor, agent["public_id"], token)
    join = call["join"]["conversation_token"]

    first = await visitor.post(
        fake_turn_path(join), json={"words": "How much leave?", "call_token": call["call_token"]}
    )
    second = await visitor.post(
        fake_turn_path(join), json={"words": "Thanks!", "call_token": call["call_token"]}
    )

    assert first.status_code == second.status_code == 200, first.text
    parts = [part[2] for part in json.loads(second.json()["agent_response"])]
    assert "Thanks!" in parts[-1]
    # The Agent remembers the first spoken turn from the Conversation (the fake sends its own
    # transcript too, which the turn endpoint ignores).
    assert "How much leave?" in parts
    assert parts.count("How much leave?") == 1
    messages = (await resume(visitor, agent["public_id"], token)).json()["messages"]
    assert [m["spoken"] for m in messages] == [True] * 4


async def test_the_fake_voice_layer_reports_a_refused_or_unknown_call(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await calling_agent(app, owner)
    token = await conversation_token(visitor, agent["public_id"])
    call = await started(visitor, agent["public_id"], token)
    await end_call(visitor, agent["public_id"], token)

    refused = await visitor.post(
        fake_turn_path(call["join"]["conversation_token"]),
        json={"words": "Hello?", "call_token": call["call_token"]},
    )
    unknown = await visitor.post(
        fake_turn_path("fake-call-nope"), json={"words": "Hello?", "call_token": "x"}
    )

    assert refused.status_code == unknown.status_code == 502
    assert "The Call token is invalid" in refused.json()["detail"]
    assert unknown.json()["detail"] == "The fake voice layer has no such Call."


async def test_the_fake_voice_route_is_not_found_with_another_voice_layer(
    app: FastAPI, visitor: httpx.AsyncClient
) -> None:
    app.state.voice_layer = object()

    response = await visitor.post(
        fake_turn_path("fake-call-1"), json={"words": "Hello?", "call_token": "x"}
    )

    assert response.status_code == 404
