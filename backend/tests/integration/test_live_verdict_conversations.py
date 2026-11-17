"""API seam: Live Verdicts in the Conversations viewer (spec 15). An Editor filters the list by
its replies' Live Verdicts (passed, failed, error, not judged), together with the other filters,
sees how many of each Conversation's replies failed theirs, and adds a failed reply to the
Evaluation Set as spec 14 does.

Replies come from a scripted ``FunctionModel`` and are judged eagerly after each widget reply, by a
judge each test scripts (see ``tests.integration.test_live_verdicts``).
"""

from datetime import timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo

from tests.agents import parse_sse
from tests.conftest import ClientFactory, MemberFactory, SignedUpMember
from tests.fakes.clock import ControllableClock
from tests.integration.test_conversations import listed, playground_chat
from tests.integration.test_embed import conversation_token, send
from tests.integration.test_evaluation_expectations import add_case, source
from tests.integration.test_evaluation_set import prefill
from tests.integration.test_live_verdicts import (
    PASSED,
    QUESTION,
    judged,
    live_agent,
    message_id,
    sampling,
    scripted,
)

FAILED = {"passed": False, "reason": "Talks about pay, not leave."}


def judging(app: FastAPI, outcome: str) -> None:
    """From now on every reply is judged ``passed`` or ``failed``, or the judge errors."""
    if outcome == "error":

        def outage(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            raise ModelHTTPError(status_code=503, model_name="gpt-4.1-mini")

        scripted(app, judgement=outage)
    else:
        scripted(app, judgement=judged(PASSED, PASSED if outcome == "passed" else FAILED))


async def conversation(
    app: FastAPI, visitor: httpx.AsyncClient, agent: dict[str, Any], *outcomes: str
) -> list[str]:
    """A Visitor Conversation, started a minute after the last, with one reply judged as each of
    ``outcomes`` says, in order; the replies' Message IDs."""
    later(app)
    token = await conversation_token(visitor, agent["public_id"])
    replies = []
    for outcome in outcomes:
        judging(app, outcome)
        response = await send(visitor, agent["public_id"], token, QUESTION)
        assert response.status_code == 200, response.text
        replies.append(message_id(parse_sse(response.text)))
    return replies


def later(app: FastAPI) -> None:
    """Moves the clock on, so the next Conversation lists before the last."""
    clock = app.state.clock
    assert isinstance(clock, ControllableClock)
    clock.advance(timedelta(minutes=1))


async def unsampled(visitor: httpx.AsyncClient, agent: dict[str, Any]) -> None:
    """A Visitor Conversation with one reply, asked before any reply is sampled."""
    token = await conversation_token(visitor, agent["public_id"])
    assert (await send(visitor, agent["public_id"], token, QUESTION)).status_code == 200


def failed_counts(page: dict[str, Any]) -> list[int]:
    return [item["failed_live_verdicts"] for item in page["items"]]


async def ids(member: SignedUpMember, agent: dict[str, Any], **filters: Any) -> set[str]:
    page = await listed(member, agent["project_id"], **filters)
    return {item["id"] for item in page["items"]}


async def conversation_ids(member: SignedUpMember, agent: dict[str, Any]) -> list[str]:
    """The Project's Conversations, oldest first."""
    page = await listed(member, agent["project_id"])
    return [item["id"] for item in reversed(page["items"])]


@pytest.mark.usefixtures("clock")
async def test_each_conversation_shows_how_many_of_its_replies_failed_their_live_verdict(
    app: FastAPI,
    owner: SignedUpMember,
    member_factory: MemberFactory,
    new_client: ClientFactory,
) -> None:
    scripted(app)
    agent = await live_agent(app, owner)
    await unsampled(await new_client(), agent)
    await sampling(owner, agent, 100)
    await conversation(app, await new_client(), agent, "failed", "passed", "failed", "error")
    await conversation(app, await new_client(), agent, "passed")
    editor = await member_factory(owner, "editor")

    page = await listed(editor, agent["project_id"])

    # Newest first: two failed of four judged-or-errored replies, none, and an unsampled one.
    assert failed_counts(page) == [0, 2, 0]


@pytest.mark.usefixtures("clock")
@pytest.mark.parametrize(
    ("live_verdict", "expected"),
    [
        ("failed", {"failed", "mixed"}),
        ("passed", {"passed", "mixed"}),
        ("error", {"error"}),
        ("not_judged", {"unsampled", "playground"}),
    ],
)
async def test_the_list_is_filtered_by_its_replies_live_verdicts(
    app: FastAPI,
    owner: SignedUpMember,
    new_client: ClientFactory,
    live_verdict: str,
    expected: set[str],
) -> None:
    scripted(app)
    agent = await live_agent(app, owner)
    names = ["unsampled", "playground", "failed", "passed", "error", "mixed"]
    await unsampled(await new_client(), agent)
    later(app)
    await playground_chat(owner, agent["project_id"], agent["id"], QUESTION)
    await sampling(owner, agent, 100)
    for outcomes in (["failed"], ["passed"], ["error"], ["passed", "failed"]):
        await conversation(app, await new_client(), agent, *outcomes)
    named = dict(zip(await conversation_ids(owner, agent), names, strict=True))

    found = await ids(owner, agent, live_verdict=live_verdict)

    assert {named[i] for i in found} == expected


@pytest.mark.usefixtures("clock")
async def test_the_live_verdict_filter_combines_with_the_other_filters(
    app: FastAPI, owner: SignedUpMember, new_client: ClientFactory
) -> None:
    scripted(app)
    agent = await live_agent(app, owner)
    await sampling(owner, agent, 100)
    await conversation(app, await new_client(), agent, "failed")
    await conversation(app, await new_client(), agent, "passed")
    failed, passed = await conversation_ids(owner, agent)

    assert await ids(owner, agent, live_verdict="failed", agent_id=agent["id"]) == {failed}
    assert await ids(owner, agent, live_verdict="failed", playground="true") == set()
    assert await ids(owner, agent, live_verdict="passed", playground="false") == {passed}
    page = await listed(owner, agent["project_id"], live_verdict="failed", feedback="none")
    assert (page["total"], [i["id"] for i in page["items"]]) == (1, [failed])


async def test_an_unknown_live_verdict_filter_is_refused(owner: SignedUpMember) -> None:
    response = await owner.client.get(
        f"/api/organisations/{owner.organisation_id}/projects/"
        "00000000-0000-0000-0000-000000000000/conversations",
        params={"live_verdict": "pending"},
    )

    assert response.status_code == 422


@pytest.mark.usefixtures("clock")
async def test_a_reply_that_failed_its_live_verdict_is_added_to_the_evaluation_set(
    app: FastAPI,
    owner: SignedUpMember,
    member_factory: MemberFactory,
    new_client: ClientFactory,
) -> None:
    scripted(app)
    agent = await live_agent(app, owner)
    await sampling(owner, agent, 100)
    (reply,) = await conversation(app, await new_client(), agent, "failed")
    editor = await member_factory(owner, "editor")
    (listed_failed,) = (await listed(editor, agent["project_id"], live_verdict="failed"))["items"]

    offered = await prefill(editor, agent["project_id"], agent["id"], reply)

    assert offered.status_code == 200, offered.text
    assert offered.json()["question"] == QUESTION
    # The reply cited the leave policy, which is offered as an Expected source.
    assert offered.json()["expected_sources"] != []
    case = await add_case(
        editor,
        agent["project_id"],
        agent["id"],
        question=offered.json()["question"],
        expected_sources=[
            source(s["document_id"], s["passage"]) for s in offered.json()["expected_sources"]
        ],
        source="from_message",
    )
    assert case["source"] == "from_message"
    # As in spec 14, the case keeps no link to the Conversation or the reply.
    assert listed_failed["id"] not in str(case)
    assert reply not in str(case)
