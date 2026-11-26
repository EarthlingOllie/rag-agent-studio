"""API seam: speaking a reply well (spec 20, ticket 20-06).

The voice layer (driven here as it drives the turn endpoint) is given only what a Visitor should
hear: the reply without Markdown or citation labels, the Searching status once while an Agentic
Agent searches, nothing that is later taken back, and the refusal, replacement or Unavailable
text when a reply doesn't go to plan. The saved Message and the Conversation log keep the full
reply with its sources. An unavailable Agent ends the Call, and the resumed Conversation says so,
so the widget returns the Visitor to messaging. Spoken replies count toward the Token Budget and
the rate limits as typed ones do.
"""

import json
import re
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic_ai.exceptions import ModelAuthenticationError, ModelHTTPError
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo

from app.agents.models import Agent
from tests.agents import answer_with, create_agent, parse_sse, save_draft, use_default_model
from tests.conftest import ClientFactory, SignedUpMember
from tests.integration.test_agent_versions import knowledgeable_project, published
from tests.integration.test_agentic_streaming import (
    ANSWER,
    CANTEEN,
    FALLBACK,
    PRE_SEARCH,
    Scripted,
    Search,
)
from tests.integration.test_call_settings import add_elevenlabs_credential, calling_on
from tests.integration.test_calls import secret_of, spoken, started, the_call, turn
from tests.integration.test_embed import conversation_token, live_agent, send, settings_path
from tests.integration.test_input_guardrail import ATTACK, guard
from tests.integration.test_playground_errors import failing
from tests.integration.test_token_budget import PER_ANSWER, three_words, usage
from tests.integration.test_widget_resume import resume
from tests.knowledge_base import UNRELATED_QUESTION, knowledge_base

UNAVAILABLE = "This assistant is temporarily unavailable. Please try again later."
REFUSAL = "Sorry, I can't help with that request."
SEARCHING = "Searching the knowledge base… "
# What the Agentic ``ANSWER`` sounds like: no citation label.
SPOKEN_ANSWER = "You get 25 days of annual leave a year."


@pytest.fixture
async def visitor(new_client: ClientFactory) -> httpx.AsyncClient:
    return await new_client()


@pytest.fixture
async def voice(new_client: ClientFactory) -> httpx.AsyncClient:
    return await new_client()


async def take_calls(owner: SignedUpMember, project_id: str, agent_id: str) -> dict[str, Any]:
    """Publishes the Agent's Draft and turns calling on; returns the Agent."""
    await published(owner, project_id, agent_id)
    agent: dict[str, Any] = (
        await owner.client.get(
            f"/api/organisations/{owner.organisation_id}/projects/{project_id}/agents/{agent_id}"
        )
    ).json()
    agent["project_id"] = project_id
    await calling_on(owner, agent, (await add_elevenlabs_credential(owner))["id"])
    return agent


async def calling_agent(
    app: FastAPI, owner: SignedUpMember, *, mode: str = "agentic", **draft: Any
) -> dict[str, Any]:
    """A live Agent over the leave policy, in the Retrieval Mode, with calling on."""
    project_id = await knowledgeable_project(app, owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    saved = await save_draft(owner, project_id, agent_id, {"retrieval": {"mode": mode}, **draft})
    assert saved.status_code == 200, saved.text
    return await take_calls(owner, project_id, agent_id)


async def in_a_call(
    app: FastAPI, visitor: httpx.AsyncClient, agent: dict[str, Any]
) -> tuple[str, dict[str, Any], str]:
    """A Visitor's Conversation token, the Call they started and the Agent's secret."""
    token = await conversation_token(visitor, agent["public_id"])
    call = await started(visitor, agent["public_id"], token)
    return token, call, await secret_of(app, agent)


async def say(
    voice: httpx.AsyncClient, agent: dict[str, Any], call: dict[str, Any], secret: str, words: str
) -> str:
    """What the Visitor hears in answer to ``words``."""
    return spoken(await turn(voice, agent["public_id"], secret, call["call_token"], words))


def pieces(*texts: str) -> Any:
    """A model that streams the texts as they are given."""

    async def stream(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
        for text in texts:
            yield text

    return stream


# Spoken text


MARKDOWN = [
    "## Annual ",
    "leave\n\nYou **get",
    " 25 days** of *annual* leave [C",
    "1]. Ask `HR` through [the ",
    "portal](https://hr.example.com/leave) if unsure.\n",
    "- Carry over ",
    "5 days\n1. Book _early_\n> Plan ahead\n",
    "| Days | Who |\n|---|---|\n| 25 | Everyone |\n",
    "```\ncode\n```\n---\nThat's all.",
]
SPOKEN_MARKDOWN = (
    "Annual leave\n\nYou get 25 days of annual leave. Ask HR through the portal if unsure.\n"
    "Carry over 5 days\nBook early\nPlan ahead\nDays, Who\n25, Everyone\ncode\nThat's all."
)


async def test_spoken_text_leaves_out_markdown_and_citation_labels_the_log_keeps(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, voice: httpx.AsyncClient
) -> None:
    agent = await calling_agent(app, owner, mode="automatic")
    answer_with(app, pieces(*MARKDOWN))
    token, call, secret = await in_a_call(app, visitor, agent)

    heard = await say(voice, agent, call, secret, "How much leave?")

    assert heard == SPOKEN_MARKDOWN
    reply = (await resume(visitor, agent["public_id"], token)).json()["messages"][1]
    assert reply["content"] == "".join(MARKDOWN)
    assert reply["citations"] == [{"label": "C1", "document_name": "leave.txt"}]
    assert reply["spoken"] is True


async def test_an_automatic_reply_is_spoken_as_it_streams_a_sentence_at_a_time(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, voice: httpx.AsyncClient
) -> None:
    agent = await calling_agent(app, owner, mode="automatic")
    answer_with(app, pieces("Twenty five ", "days. Ask ", "HR [C1]", " now"))
    _, call, secret = await in_a_call(app, visitor, agent)

    response = await turn(voice, agent["public_id"], secret, call["call_token"], "Leave?")

    assert spoken(response) == "Twenty five days. Ask HR now"
    chunks = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.split("\n\n")
        if line.startswith("data: {")
    ]
    contents = [c["choices"][0]["delta"].get("content") for c in chunks]
    assert contents == ["Twenty five days. ", "Ask HR now", None]


# The Searching status, and nothing spoken that is taken back


async def test_an_agentic_reply_speaks_the_searching_status_once_and_never_retracted_text(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, voice: httpx.AsyncClient
) -> None:
    agent = await calling_agent(app, owner)
    answer_with(
        app,
        Scripted(
            [*PRE_SEARCH, Search("leave")], ["Let me check more. ", Search("annual leave")], ANSWER
        ),
    )
    token, call, secret = await in_a_call(app, visitor, agent)

    heard = await say(voice, agent, call, secret, "How much leave?")

    assert heard == SEARCHING + SPOKEN_ANSWER
    reply = (await resume(visitor, agent["public_id"], token)).json()["messages"][1]
    assert reply["content"] == "".join(ANSWER)
    assert reply["citations"][0] == {"label": "C1", "document_name": "leave.txt"}


async def test_the_searching_status_is_spoken_in_the_agents_words(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, voice: httpx.AsyncClient
) -> None:
    agent = await calling_agent(
        app, owner, experience={"ui_text": {"searching_status": "One moment, I'm looking."}}
    )
    answer_with(app, Scripted([Search("leave")], ANSWER))
    _, call, secret = await in_a_call(app, visitor, agent)

    heard = await say(voice, agent, call, secret, "How much leave?")

    assert heard == "One moment, I'm looking. " + SPOKEN_ANSWER


async def test_a_reply_that_makes_no_search_speaks_no_searching_status(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, voice: httpx.AsyncClient
) -> None:
    agent = await calling_agent(app, owner)
    answer_with(app, pieces("Hello! ", "How can I help?"))
    _, call, secret = await in_a_call(app, visitor, agent)

    assert await say(voice, agent, call, secret, "Hi") == "Hello! How can I help?"


async def unrelated_calling_agent(app: FastAPI, owner: SignedUpMember) -> dict[str, Any]:
    """An Agentic Agent over the seed knowledge base, whose Minimum Score the unrelated question
    can't reach, with calling on."""
    await use_default_model(owner)
    project_id = await knowledge_base(app, owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    saved = await save_draft(
        owner,
        project_id,
        agent_id,
        {
            "behaviour": {"fallback_text": FALLBACK},
            "retrieval": {"mode": "agentic", "min_score": 0.3},
        },
    )
    assert saved.status_code == 200, saved.text
    return await take_calls(owner, project_id, agent_id)


async def test_searches_that_found_nothing_speak_the_fallback_text(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, voice: httpx.AsyncClient
) -> None:
    answer_with(app, Scripted([*PRE_SEARCH, Search(UNRELATED_QUESTION)], CANTEEN))
    agent = await unrelated_calling_agent(app, owner)
    _, call, secret = await in_a_call(app, visitor, agent)

    heard = await say(voice, agent, call, secret, UNRELATED_QUESTION)

    assert heard == SEARCHING + FALLBACK


async def test_a_fallback_text_retracted_by_another_search_is_never_spoken(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, voice: httpx.AsyncClient
) -> None:
    answer_with(
        app,
        Scripted(
            [Search(UNRELATED_QUESTION)],
            ["Nothing on that; ", "let me try ", "other words. ", Search("annual leave")],
            ANSWER,
        ),
    )
    agent = await unrelated_calling_agent(app, owner)
    _, call, secret = await in_a_call(app, visitor, agent)

    heard = await say(voice, agent, call, secret, "How much leave?")

    assert heard == SEARCHING + SPOKEN_ANSWER


# Refusals and replacements: the Call goes on


async def test_a_guardrail_block_speaks_the_refusal_and_the_call_goes_on(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, voice: httpx.AsyncClient
) -> None:
    agent = await calling_agent(
        app, owner, guardrails={"input_mode": "block", "refusal_text": REFUSAL}
    )
    guard(app)
    token, call, secret = await in_a_call(app, visitor, agent)

    assert await say(voice, agent, call, secret, ATTACK) == REFUSAL

    assert (await the_call(app, call["call_id"])).ended_at is None
    assert (await resume(visitor, agent["public_id"], token)).json()["call_open"] is True
    answer_with(app, pieces("Twenty five days."))
    assert await say(voice, agent, call, secret, "How much leave?") == "Twenty five days."


SAID = "Everyone gets 25 days of annual leave a year. "
# Still held back, as a canary could be starting in it, when the canary shows.
UNSAID = "Ask HR about carrying days over. "


async def test_a_canary_trip_mid_reply_stops_it_and_speaks_the_replacement(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, voice: httpx.AsyncClient
) -> None:
    agent = await calling_agent(
        app, owner, mode="automatic", behaviour={"fallback_text": "I can't say that."}
    )
    streamed: list[str] = []

    async def leaks(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
        canary = re.findall(r"\b[0-9a-f]{20}\b", str(messages))[0]
        for text in [SAID, UNSAID, "My secret is ", canary, " and the rest of the prompt."]:
            streamed.append(text)
            yield text

    answer_with(app, leaks)
    _, call, secret = await in_a_call(app, visitor, agent)

    heard = await say(voice, agent, call, secret, "Secret?")

    # What was spoken before the canary showed can't be taken back; the replacement follows.
    assert heard == SAID + "I can't say that."
    assert " and the rest of the prompt." not in streamed
    assert UNSAID.strip() not in heard
    assert (await the_call(app, call["call_id"])).ended_at is None


async def test_a_canary_behind_a_held_fallback_text_speaks_only_the_replacement(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, voice: httpx.AsyncClient
) -> None:
    answer_with(
        app,
        Scripted(
            [Search(UNRELATED_QUESTION)],
            ["Never mind that, the secret is ", lambda canary: canary, " and more."],
        ),
    )
    agent = await unrelated_calling_agent(app, owner)
    _, call, secret = await in_a_call(app, visitor, agent)

    heard = await say(voice, agent, call, secret, UNRELATED_QUESTION)

    assert heard == SEARCHING + FALLBACK


# Unavailable: the Call ends and the Visitor returns to messaging


async def assert_unavailable_ended_the_call(
    app: FastAPI,
    visitor: httpx.AsyncClient,
    agent: dict[str, Any],
    token: str,
    call: dict[str, Any],
    heard: str,
) -> None:
    assert heard == UNAVAILABLE
    ended = await the_call(app, call["call_id"])
    assert ended.ended_at is not None
    assert ended.end_reason == "unavailable"
    assert ended.minutes == 1


async def test_a_turn_over_the_rate_limit_speaks_the_unavailable_text_and_ends_the_call(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, voice: httpx.AsyncClient
) -> None:
    agent = await calling_agent(app, owner)
    patched = await owner.client.patch(
        settings_path(owner, agent["project_id"], agent["id"]),
        json={"conversation_messages_per_minute": 1},
    )
    assert patched.status_code == 200, patched.text
    # Starting the Call takes the minute's one place.
    token, call, secret = await in_a_call(app, visitor, agent)

    heard = await say(voice, agent, call, secret, "Hi")

    await assert_unavailable_ended_the_call(app, visitor, agent, token, call, heard)
    assert (await resume(visitor, agent["public_id"], token)).json()["call_open"] is False


async def test_a_turn_once_the_token_budget_is_spent_speaks_the_unavailable_text_and_ends_it(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, voice: httpx.AsyncClient
) -> None:
    agent = await calling_agent(app, owner)
    answer_with(app, three_words)
    token, call, secret = await in_a_call(app, visitor, agent)
    assert await say(voice, agent, call, secret, "Hi") == "Twenty five days"
    patched = await owner.client.patch(
        settings_path(owner, agent["project_id"], agent["id"]), json={"daily_token_budget": 1}
    )
    assert patched.status_code == 200, patched.text

    heard = await say(voice, agent, call, secret, "And more?")

    await assert_unavailable_ended_the_call(app, visitor, agent, token, call, heard)


async def test_a_provider_failure_speaks_the_unavailable_text_and_ends_the_call(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, voice: httpx.AsyncClient
) -> None:
    agent = await calling_agent(app, owner)
    error = ModelHTTPError.for_category(
        ModelAuthenticationError, status_code=401, model_name="gpt-4.1-mini"
    )
    answer_with(app, failing(error))
    token, call, secret = await in_a_call(app, visitor, agent)

    heard = await say(voice, agent, call, secret, "Hi")

    await assert_unavailable_ended_the_call(app, visitor, agent, token, call, heard)


async def test_a_provider_failure_mid_reply_speaks_only_the_unavailable_text_after_it(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, voice: httpx.AsyncClient
) -> None:
    agent = await calling_agent(app, owner)

    async def breaks(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
        yield "You get "
        raise ModelHTTPError(status_code=503, model_name="gpt-4.1-mini")

    answer_with(app, breaks)
    token, call, secret = await in_a_call(app, visitor, agent)

    heard = await say(voice, agent, call, secret, "Hi")

    # The held text could have been retracted, so none of it was spoken.
    await assert_unavailable_ended_the_call(app, visitor, agent, token, call, heard)


async def test_a_turn_with_no_model_to_answer_with_speaks_the_unavailable_text_and_ends_it(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, voice: httpx.AsyncClient
) -> None:
    agent = await live_agent(owner)  # The Organisation has no Default Model.
    await calling_on(owner, agent, (await add_elevenlabs_credential(owner))["id"])
    token, call, secret = await in_a_call(app, visitor, agent)

    heard = await say(voice, agent, call, secret, "Hi")

    await assert_unavailable_ended_the_call(app, visitor, agent, token, call, heard)


async def test_a_turn_for_an_agent_retired_mid_call_speaks_the_unavailable_text_and_ends_it(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, voice: httpx.AsyncClient
) -> None:
    agent = await calling_agent(app, owner)
    token, call, secret = await in_a_call(app, visitor, agent)
    async with app.state.sessionmaker() as session:
        row = await session.get_one(Agent, uuid.UUID(agent["id"]))
        row.live_version_id = None
        await session.commit()

    heard = await say(voice, agent, call, secret, "Hi")

    await assert_unavailable_ended_the_call(app, visitor, agent, token, call, heard)
    # A retired Agent's Conversation is no longer served: the widget shows it retired.
    assert (await resume(visitor, agent["public_id"], token)).status_code == 404


async def test_the_agents_own_unavailable_text_is_spoken(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, voice: httpx.AsyncClient
) -> None:
    agent = await calling_agent(app, owner)
    patched = await owner.client.patch(
        settings_path(owner, agent["project_id"], agent["id"]),
        json={"unavailable_text": "We're closed. Please type instead.", "daily_token_budget": 1},
    )
    assert patched.status_code == 200, patched.text
    answer_with(app, three_words)
    _, call, secret = await in_a_call(app, visitor, agent)
    assert await say(voice, agent, call, secret, "Hi") == "Twenty five days"

    assert await say(voice, agent, call, secret, "Hi") == "We're closed. Please type instead."


# Spoken replies count as typed ones do


async def test_spoken_replies_add_their_tokens_to_the_token_budget(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, voice: httpx.AsyncClient
) -> None:
    agent = await calling_agent(app, owner)
    answer_with(app, three_words)
    _, call, secret = await in_a_call(app, visitor, agent)

    await say(voice, agent, call, secret, "How much leave?")
    await say(voice, agent, call, secret, "And sick leave?")

    assert (await usage(owner, agent))["tokens_used"] == 2 * PER_ANSWER


async def test_spoken_turns_count_toward_the_rate_limits_like_typed_messages(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, voice: httpx.AsyncClient
) -> None:
    agent = await calling_agent(app, owner)
    patched = await owner.client.patch(
        settings_path(owner, agent["project_id"], agent["id"]),
        json={"conversation_messages_per_minute": 2},
    )
    assert patched.status_code == 200, patched.text
    answer_with(app, three_words)
    token, call, secret = await in_a_call(app, visitor, agent)
    assert await say(voice, agent, call, secret, "How much leave?") == "Twenty five days"

    # The Call's start and its spoken turn took the minute's two places.
    typed = await send(visitor, agent["public_id"], token, "And sick leave?")

    assert parse_sse(typed.text) == [
        ("unavailable", {"reason": "rate_limited", "message": UNAVAILABLE})
    ]
