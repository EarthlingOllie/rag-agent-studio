"""API seam: Message Feedback. A Visitor gives a thumbs up or down, with an optional comment, on
an Agent reply in their own Conversation (authenticated by its Conversation token), and can
change or remove it. The feedback belongs to the Agent Version of the reply, stored when it is
written. Editors read it in the Conversations viewer and filter Conversations by it.

Visitors use a client with no Studio session; answers come from the ``FunctionModel``."""

import uuid
from datetime import timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from tests.agents import create_agent, parse_sse
from tests.conftest import ClientFactory, MemberFactory, SignedUpMember
from tests.fakes.clock import ControllableClock
from tests.integration.test_agent_revert import reverted
from tests.integration.test_agent_versions import knowledgeable_project, published
from tests.integration.test_conversations import (
    conversations_path,
    listed,
    opened,
    playground_chat,
)
from tests.integration.test_embed import conversation_token, send, tamper


@pytest.fixture
async def visitor(new_client: ClientFactory) -> httpx.AsyncClient:
    """A browser on someone's website: no Studio session."""
    return await new_client()


def feedback_path(public_id: str, message_id: str) -> str:
    return f"/api/widget/agents/{public_id}/messages/{message_id}/feedback"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def give(
    visitor: httpx.AsyncClient, public_id: str, token: str, message_id: str, **body: Any
) -> httpx.Response:
    return await visitor.put(feedback_path(public_id, message_id), json=body, headers=bearer(token))


async def remove(
    visitor: httpx.AsyncClient, public_id: str, token: str, message_id: str
) -> httpx.Response:
    return await visitor.delete(feedback_path(public_id, message_id), headers=bearer(token))


async def resumed(visitor: httpx.AsyncClient, public_id: str, token: str) -> list[dict[str, Any]]:
    response = await visitor.get(
        f"/api/widget/agents/{public_id}/conversation", headers=bearer(token)
    )
    assert response.status_code == 200, response.text
    messages: list[dict[str, Any]] = response.json()["messages"]
    return messages


async def reply(visitor: httpx.AsyncClient, public_id: str, token: str, question: str) -> str:
    """Asks a question; returns the ID of the Agent's reply, from the stream's `done` event."""
    response = await send(visitor, public_id, token, question)
    assert response.status_code == 200, response.text
    event, data = parse_sse(response.text)[-1]
    assert event == "done", response.text
    message_id: str = data["message_id"]
    return message_id


async def live(app: FastAPI, owner: SignedUpMember) -> dict[str, Any]:
    """A live Agent in a Project with a Document; with its ``project_id``."""
    project_id = await knowledgeable_project(app, owner)
    agent: dict[str, Any] = await create_agent(owner, project_id)
    agent["version"] = await published(owner, project_id, agent["id"])
    return agent


async def test_a_visitor_gives_a_thumbs_up_and_sees_it_when_they_come_back(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await live(app, owner)
    public_id = agent["public_id"]
    token = await conversation_token(visitor, public_id)
    message_id = await reply(visitor, public_id, token, "How much leave?")

    response = await give(visitor, public_id, token, message_id, rating="up")

    assert response.status_code == 200, response.text
    assert response.json() == {"rating": "up", "comment": None}
    question, answer = await resumed(visitor, public_id, token)
    assert question["feedback"] is None
    assert answer["id"] == message_id
    assert answer["feedback"] == {"rating": "up", "comment": None}


async def test_a_visitor_changes_their_thumbs_and_adds_a_comment(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await live(app, owner)
    public_id = agent["public_id"]
    token = await conversation_token(visitor, public_id)
    message_id = await reply(visitor, public_id, token, "How much leave?")
    assert (await give(visitor, public_id, token, message_id, rating="up")).status_code == 200

    changed = await give(
        visitor, public_id, token, message_id, rating="down", comment="  It's 30 days here.  "
    )

    assert changed.status_code == 200, changed.text
    assert changed.json() == {"rating": "down", "comment": "It's 30 days here."}
    assert (await resumed(visitor, public_id, token))[1]["feedback"] == {
        "rating": "down",
        "comment": "It's 30 days here.",
    }
    # Giving it again replaces the whole feedback: leaving the comment out drops it.
    again = await give(visitor, public_id, token, message_id, rating="down")
    assert again.json() == {"rating": "down", "comment": None}
    blank = await give(visitor, public_id, token, message_id, rating="up", comment="   ")
    assert blank.json() == {"rating": "up", "comment": None}
    assert (await resumed(visitor, public_id, token))[1]["feedback"] == {
        "rating": "up",
        "comment": None,
    }


async def test_a_visitor_removes_their_feedback(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await live(app, owner)
    public_id = agent["public_id"]
    token = await conversation_token(visitor, public_id)
    message_id = await reply(visitor, public_id, token, "How much leave?")
    await give(visitor, public_id, token, message_id, rating="down", comment="Wrong")

    response = await remove(visitor, public_id, token, message_id)

    assert response.status_code == 204, response.text
    assert (await resumed(visitor, public_id, token))[1]["feedback"] is None
    # Removing again is harmless, and the thumbs can be given afresh.
    assert (await remove(visitor, public_id, token, message_id)).status_code == 204
    assert (await give(visitor, public_id, token, message_id, rating="up")).status_code == 200


async def test_each_reply_has_its_own_feedback(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await live(app, owner)
    public_id = agent["public_id"]
    token = await conversation_token(visitor, public_id)
    first = await reply(visitor, public_id, token, "How much leave?")
    second = await reply(visitor, public_id, token, "And sick days?")

    await give(visitor, public_id, token, first, rating="up")
    await give(visitor, public_id, token, second, rating="down", comment="Not answered")

    messages = await resumed(visitor, public_id, token)
    assert [m["feedback"] for m in messages] == [
        None,
        {"rating": "up", "comment": None},
        None,
        {"rating": "down", "comment": "Not answered"},
    ]


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"rating": "sideways"},
        {"rating": None},
        {"rating": "up", "comment": "x" * 1001},
        {"rating": "up", "comment": 5},
    ],
)
async def test_bad_feedback_is_refused(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, body: dict[str, Any]
) -> None:
    agent = await live(app, owner)
    public_id = agent["public_id"]
    token = await conversation_token(visitor, public_id)
    message_id = await reply(visitor, public_id, token, "How much leave?")

    response = await give(visitor, public_id, token, message_id, **body)

    assert response.status_code == 422, response.text
    assert (await resumed(visitor, public_id, token))[1]["feedback"] is None


async def test_a_comment_of_the_longest_length_is_kept(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await live(app, owner)
    public_id = agent["public_id"]
    token = await conversation_token(visitor, public_id)
    message_id = await reply(visitor, public_id, token, "How much leave?")

    response = await give(visitor, public_id, token, message_id, rating="down", comment="x" * 1000)

    assert response.status_code == 200, response.text
    assert response.json()["comment"] == "x" * 1000


async def test_feedback_is_only_allowed_on_replies_in_the_visitors_own_conversation(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    new_client: ClientFactory,
) -> None:
    agent = await live(app, owner)
    public_id = agent["public_id"]
    token = await conversation_token(visitor, public_id)
    mine = await reply(visitor, public_id, token, "How much leave?")
    (question,) = [m["id"] for m in await resumed(visitor, public_id, token) if m["role"] == "user"]
    stranger = await new_client()
    their_token = await conversation_token(stranger, public_id)
    theirs = await reply(stranger, public_id, their_token, "Can I carry leave over?")
    other_agent = await live(app, owner)
    elsewhere_token = await conversation_token(visitor, other_agent["public_id"])
    elsewhere = await reply(visitor, other_agent["public_id"], elsewhere_token, "Hello?")
    in_playground = await playground_chat(owner, agent["project_id"], agent["id"], "Testing")
    playground_reply = (await opened(owner, agent["project_id"], in_playground))["messages"][1]

    for message_id in (theirs, question, elsewhere, playground_reply["id"], str(uuid.uuid4())):
        given = await give(visitor, public_id, token, message_id, rating="down")
        removed = await remove(visitor, public_id, token, message_id)

        assert (given.status_code, given.json()) == (
            404,
            {"detail": "There is no such reply in this chat."},
        ), message_id
        assert removed.status_code == 404, message_id
    # The stranger's reply is untouched by the attempt, and the Visitor's own works.
    assert (await resumed(stranger, public_id, their_token))[1]["feedback"] is None
    assert (await give(visitor, public_id, token, mine, rating="up")).status_code == 200


async def test_feedback_needs_a_valid_conversation_token_for_that_agent(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await live(app, owner)
    public_id = agent["public_id"]
    token = await conversation_token(visitor, public_id)
    message_id = await reply(visitor, public_id, token, "How much leave?")
    other = await live(app, owner)
    ended_token = await conversation_token(visitor, public_id)
    await reply(visitor, public_id, ended_token, "Bye")
    ended = await visitor.delete(
        f"/api/widget/agents/{public_id}/conversation", headers=bearer(ended_token)
    )
    assert ended.status_code == 204

    attempts = [
        (public_id, tamper(token)),
        (public_id, "not-a-token"),
        (other["public_id"], token),
        (public_id, ended_token),
    ]
    for path_agent, bad_token in attempts:
        given = await give(visitor, path_agent, bad_token, message_id, rating="up")
        removed = await remove(visitor, path_agent, bad_token, message_id)

        assert given.status_code == 401, (path_agent, bad_token)
        assert removed.status_code == 401, (path_agent, bad_token)
    no_header = await visitor.put(feedback_path(public_id, message_id), json={"rating": "up"})
    assert no_header.status_code == 401
    wrong_scheme = await visitor.put(
        feedback_path(public_id, message_id),
        json={"rating": "up"},
        headers={"Authorization": f"Basic {token}"},
    )
    assert wrong_scheme.status_code == 401
    assert (await resumed(visitor, public_id, token))[1]["feedback"] is None


async def test_feedback_is_refused_once_the_conversation_token_has_expired(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent = await live(app, owner)
    public_id = agent["public_id"]
    token = await conversation_token(visitor, public_id)
    message_id = await reply(visitor, public_id, token, "How much leave?")
    clock.advance(timedelta(hours=24, seconds=1))

    response = await give(visitor, public_id, token, message_id, rating="up")

    assert response.status_code == 401, response.text


# Attribution and the Conversations viewer


def feedback_of(detail: dict[str, Any]) -> list[dict[str, Any] | None]:
    return [m["feedback"] for m in detail["messages"]]


async def test_feedback_belongs_to_the_replys_version_whatever_is_live_later(
    app: FastAPI,
    owner: SignedUpMember,
    member_factory: MemberFactory,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    editor = await member_factory(owner, "editor")
    agent = await live(app, owner)
    project_id, public_id = agent["project_id"], agent["public_id"]
    token = await conversation_token(visitor, public_id)
    on_v1 = await reply(visitor, public_id, token, "Asked of v1")
    await published(owner, project_id, agent["id"])
    on_v2 = await reply(visitor, public_id, token, "Asked of v2")
    # v1 is Live again: feedback given now on v2's reply still goes to v2, and v1's to v1.
    assert (await reverted(owner, project_id, agent["id"]))["number"] == 1
    await give(visitor, public_id, token, on_v2, rating="down", comment="Worse")
    clock.advance(60)
    await give(visitor, public_id, token, on_v1, rating="up")
    conversation_id = (await listed(editor, project_id))["items"][0]["id"]

    detail = await opened(editor, project_id, conversation_id)

    started = clock.now() - timedelta(seconds=60)
    assert feedback_of(detail) == [
        None,
        {
            "rating": "up",
            "comment": None,
            "agent_version_number": 1,
            "updated_at": clock.now().isoformat().replace("+00:00", "Z"),
        },
        None,
        {
            "rating": "down",
            "comment": "Worse",
            "agent_version_number": 2,
            "updated_at": started.isoformat().replace("+00:00", "Z"),
        },
    ]
    # A later publish leaves the stored attribution alone.
    await published(owner, project_id, agent["id"])
    again = await opened(editor, project_id, conversation_id)
    assert [f and f["agent_version_number"] for f in feedback_of(again)] == [None, 1, None, 2]


async def test_the_list_shows_each_conversations_thumbs_and_filters_by_feedback(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent = await live(app, owner)
    project_id, public_id = agent["project_id"], agent["public_id"]

    async def chat(question: str, *ratings: str) -> None:
        token = await conversation_token(visitor, public_id)
        for rating in ratings:
            message_id = await reply(visitor, public_id, token, question)
            if rating != "-":
                await give(visitor, public_id, token, message_id, rating=rating)
        clock.advance(60)

    await chat("Liked", "up", "up")
    await chat("Disliked", "down")
    await chat("Mixed", "up", "down", "-")
    await chat("Silent", "-")
    await playground_chat(owner, project_id, agent["id"], "Playground")

    def previews(page: dict[str, Any]) -> list[str]:
        return [item["preview"] for item in page["items"]]

    everything = await listed(owner, project_id)
    assert [(i["preview"], i["thumbs_up"], i["thumbs_down"]) for i in everything["items"]] == [
        ("Playground", 0, 0),
        ("Silent", 0, 0),
        ("Mixed", 1, 1),
        ("Disliked", 0, 1),
        ("Liked", 2, 0),
    ]
    assert previews(await listed(owner, project_id, feedback="up")) == ["Mixed", "Liked"]
    assert previews(await listed(owner, project_id, feedback="down")) == ["Mixed", "Disliked"]
    assert previews(await listed(owner, project_id, feedback="any")) == [
        "Mixed",
        "Disliked",
        "Liked",
    ]
    none = await listed(owner, project_id, feedback="none")
    assert previews(none) == ["Playground", "Silent"]
    assert none["total"] == 2
    combined = await listed(owner, project_id, feedback="down", playground="false")
    assert previews(combined) == ["Mixed", "Disliked"]
    bad = await owner.client.get(
        conversations_path(owner, project_id), params={"feedback": "sideways"}
    )
    assert bad.status_code == 422


async def test_removed_feedback_leaves_the_viewer(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await live(app, owner)
    project_id, public_id = agent["project_id"], agent["public_id"]
    token = await conversation_token(visitor, public_id)
    message_id = await reply(visitor, public_id, token, "How much leave?")
    await give(visitor, public_id, token, message_id, rating="down", comment="Wrong")
    await remove(visitor, public_id, token, message_id)

    (item,) = (await listed(owner, project_id))["items"]
    detail = await opened(owner, project_id, item["id"])

    assert (item["thumbs_up"], item["thumbs_down"]) == (0, 0)
    assert feedback_of(detail) == [None, None]
    assert (await listed(owner, project_id, feedback="any"))["total"] == 0
