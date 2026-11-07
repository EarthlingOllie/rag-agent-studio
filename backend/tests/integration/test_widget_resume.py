"""API seam: a Visitor's Conversation lifecycle. The widget keeps its Conversation token and, on
the next page load within 24 hours of the last activity, gets the Conversation back; it can end
the Conversation, after which its token is refused. Visitors use a client with no Studio
session."""

from datetime import timedelta

import httpx
import pytest
from fastapi import FastAPI

from tests.agents import answer_with, create_agent, parse_sse
from tests.conftest import ClientFactory, SignedUpMember
from tests.fakes.clock import ControllableClock
from tests.integration.test_agent_archive import archive as archive_agent
from tests.integration.test_agent_versions import knowledgeable_project, published
from tests.integration.test_embed import (
    cites,
    conversation_token,
    live_agent,
    send,
    tamper,
)


@pytest.fixture
async def visitor(new_client: ClientFactory) -> httpx.AsyncClient:
    """A browser on someone's website: no Studio session."""
    return await new_client()


def conversation_path(public_id: str) -> str:
    return f"/api/widget/agents/{public_id}/conversation"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def resume(visitor: httpx.AsyncClient, public_id: str, token: str) -> httpx.Response:
    return await visitor.get(conversation_path(public_id), headers=bearer(token))


async def end(visitor: httpx.AsyncClient, public_id: str, token: str) -> httpx.Response:
    return await visitor.delete(conversation_path(public_id), headers=bearer(token))


async def chatting_agent(app: FastAPI, owner: SignedUpMember) -> str:
    """A live Agent with a Document to cite; returns its public ID."""
    project_id = await knowledgeable_project(app, owner)
    created = await create_agent(owner, project_id)
    await published(owner, project_id, created["id"])
    public_id: str = created["public_id"]
    return public_id


async def test_a_visitor_who_reloads_gets_their_conversation_back(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    public_id = await chatting_agent(app, owner)
    answer_with(app, cites)
    token = await conversation_token(visitor, public_id)
    first = parse_sse((await send(visitor, public_id, token, "How much leave?")).text)
    second = parse_sse((await send(visitor, public_id, token, "And sick days?")).text)

    response = await resume(visitor, public_id, token)

    assert response.status_code == 200, response.text
    assert response.json() == {
        "messages": [
            {"role": "user", "content": "How much leave?", "citations": []},
            {
                "role": "assistant",
                "content": "Leave is 25 days [C1].",
                "citations": [{"label": "C1", "document_name": "leave.txt"}],
            },
            {"role": "user", "content": "And sick days?", "citations": []},
            {
                "role": "assistant",
                "content": "Leave is 25 days [C1].",
                "citations": [{"label": "C1", "document_name": "leave.txt"}],
            },
        ]
    }
    assert first[-1][0] == second[-1][0] == "done"


async def test_a_new_conversation_has_no_messages_yet(
    owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await live_agent(owner)
    token = await conversation_token(visitor, agent["public_id"])

    response = await resume(visitor, agent["public_id"], token)

    assert response.status_code == 200, response.text
    assert response.json() == {"messages": []}


async def test_resume_works_within_24_hours_and_slides_the_window(
    owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent = await live_agent(owner)
    public_id = agent["public_id"]
    token = await conversation_token(visitor, public_id)

    # Each reload counts as activity, so the window slides on with it.
    for _ in range(3):
        clock.advance(timedelta(hours=23, minutes=59))
        assert (await resume(visitor, public_id, token)).status_code == 200
    clock.advance(timedelta(hours=24, seconds=1))

    response = await resume(visitor, public_id, token)

    assert response.status_code == 401
    assert response.json() == {
        "detail": "This chat has expired. Reload the page to start a new one."
    }


async def test_resume_is_refused_exactly_after_24_hours_of_silence(
    owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent = await live_agent(owner)
    public_id = agent["public_id"]
    expiring = await conversation_token(visitor, public_id)
    lasting = await conversation_token(visitor, public_id)

    clock.advance(timedelta(hours=24))
    assert (await resume(visitor, public_id, lasting)).status_code == 200
    clock.advance(timedelta(seconds=1))

    assert (await resume(visitor, public_id, expiring)).status_code == 401
    assert (await resume(visitor, public_id, lasting)).status_code == 200


async def test_resume_needs_a_valid_conversation_token_for_that_agent(
    owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await live_agent(owner)
    other = await live_agent(owner)
    token = await conversation_token(visitor, agent["public_id"])
    others = await conversation_token(visitor, other["public_id"])
    path = conversation_path(agent["public_id"])

    for headers in (
        {},
        {"Authorization": token},
        {"Authorization": "Bearer "},
        bearer(tamper(token)),
        bearer(others),
    ):
        for method in ("GET", "DELETE"):
            response = await visitor.request(method, path, headers=headers)
            assert response.status_code == 401, (method, headers)
    # None of those refusals ended the real Conversation.
    assert (await resume(visitor, agent["public_id"], token)).status_code == 200


async def test_a_retired_agent_cannot_be_resumed(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    project_id = await knowledgeable_project(app, owner)
    created = await create_agent(owner, project_id)
    await published(owner, project_id, created["id"])
    token = await conversation_token(visitor, created["public_id"])
    assert (await send(visitor, created["public_id"], token, "Hello")).status_code == 200
    assert (await archive_agent(owner, project_id, created["id"])).status_code == 200

    response = await resume(visitor, created["public_id"], token)

    assert response.status_code == 404
    assert response.json() == {"detail": "This assistant is no longer available."}


async def test_a_visitor_ends_their_conversation_and_its_token_is_refused_after(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    public_id = await chatting_agent(app, owner)
    token = await conversation_token(visitor, public_id)
    assert (await send(visitor, public_id, token, "Hello")).status_code == 200

    response = await end(visitor, public_id, token)

    assert response.status_code == 204, response.text
    assert (await resume(visitor, public_id, token)).status_code == 401
    assert (await send(visitor, public_id, token, "Still there?")).status_code == 401
    assert (await end(visitor, public_id, token)).status_code == 401
    # A new Conversation starts as usual.
    fresh = await conversation_token(visitor, public_id)
    assert (await resume(visitor, public_id, fresh)).json() == {"messages": []}


async def test_a_conversation_can_be_ended_after_its_agent_is_retired(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    project_id = await knowledgeable_project(app, owner)
    created = await create_agent(owner, project_id)
    await published(owner, project_id, created["id"])
    token = await conversation_token(visitor, created["public_id"])
    assert (await archive_agent(owner, project_id, created["id"])).status_code == 200

    response = await end(visitor, created["public_id"], token)

    assert response.status_code == 204
    assert (await resume(visitor, created["public_id"], token)).status_code == 401
