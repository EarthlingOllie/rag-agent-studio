"""API seam: Conversation Rating. A Visitor rates their Conversation from 1 to 5 from the widget
(authenticated by its Conversation token), can change the rating, and can dismiss the rating
prompt; the dismissal is saved so the widget doesn't ask again. Every rating and change goes
into an append-only change log. A rating (and each change) belongs to the Agent Version of the
last Agent reply before it, stored when written. Editors read ratings in the Conversations
viewer and filter Conversations by them.

Visitors use a client with no Studio session; answers come from the ``FunctionModel``."""

from datetime import timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from tests.conftest import ClientFactory, MemberFactory, SignedUpMember
from tests.fakes.clock import ControllableClock
from tests.integration.test_agent_revert import reverted
from tests.integration.test_agent_versions import published
from tests.integration.test_conversations import (
    conversations_path,
    listed,
    opened,
    playground_chat,
)
from tests.integration.test_embed import conversation_token, tamper
from tests.integration.test_message_feedback import bearer, live, reply


@pytest.fixture
async def visitor(new_client: ClientFactory) -> httpx.AsyncClient:
    """A browser on someone's website: no Studio session."""
    return await new_client()


def rating_path(public_id: str) -> str:
    return f"/api/widget/agents/{public_id}/conversation/rating"


async def rate(
    visitor: httpx.AsyncClient, public_id: str, token: str, score: Any
) -> httpx.Response:
    return await visitor.put(rating_path(public_id), json={"score": score}, headers=bearer(token))


async def dismiss(visitor: httpx.AsyncClient, public_id: str, token: str) -> httpx.Response:
    return await visitor.post(f"{rating_path(public_id)}/dismissal", headers=bearer(token))


async def resumed_rating(visitor: httpx.AsyncClient, public_id: str, token: str) -> dict[str, Any]:
    response = await visitor.get(
        f"/api/widget/agents/{public_id}/conversation", headers=bearer(token)
    )
    assert response.status_code == 200, response.text
    rating: dict[str, Any] = response.json()["rating"]
    return rating


def stamp(when: Any) -> str:
    return str(when.isoformat().replace("+00:00", "Z"))


async def test_a_visitor_rates_the_conversation_and_sees_it_when_they_come_back(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await live(app, owner)
    public_id = agent["public_id"]
    token = await conversation_token(visitor, public_id)
    await reply(visitor, public_id, token, "How much leave?")
    assert await resumed_rating(visitor, public_id, token) == {
        "score": None,
        "prompt_dismissed": False,
    }

    response = await rate(visitor, public_id, token, 4)

    assert response.status_code == 200, response.text
    assert response.json() == {"score": 4, "prompt_dismissed": False}
    assert await resumed_rating(visitor, public_id, token) == {
        "score": 4,
        "prompt_dismissed": False,
    }


async def test_a_dismissal_of_the_prompt_is_saved_and_the_visitor_can_still_rate(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await live(app, owner)
    public_id = agent["public_id"]
    token = await conversation_token(visitor, public_id)
    await reply(visitor, public_id, token, "How much leave?")

    response = await dismiss(visitor, public_id, token)

    assert response.status_code == 204, response.text
    assert await resumed_rating(visitor, public_id, token) == {
        "score": None,
        "prompt_dismissed": True,
    }
    # Dismissing again is harmless; rating afterwards (on "End chat") keeps the dismissal.
    assert (await dismiss(visitor, public_id, token)).status_code == 204
    assert (await rate(visitor, public_id, token, 2)).json() == {
        "score": 2,
        "prompt_dismissed": True,
    }


async def test_the_prompt_can_be_dismissed_before_any_reply(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await live(app, owner)
    public_id = agent["public_id"]
    token = await conversation_token(visitor, public_id)

    assert (await dismiss(visitor, public_id, token)).status_code == 204
    assert await resumed_rating(visitor, public_id, token) == {
        "score": None,
        "prompt_dismissed": True,
    }


async def test_there_is_nothing_to_rate_before_the_agent_has_replied(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await live(app, owner)
    public_id = agent["public_id"]
    token = await conversation_token(visitor, public_id)

    response = await rate(visitor, public_id, token, 5)

    assert (response.status_code, response.json()) == (
        409,
        {"detail": "There is nothing to rate yet."},
    )
    assert (await resumed_rating(visitor, public_id, token))["score"] is None


@pytest.mark.parametrize("score", [0, 6, -1, None, "four", 3.5])
async def test_a_score_outside_1_to_5_is_refused(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, score: Any
) -> None:
    agent = await live(app, owner)
    public_id = agent["public_id"]
    token = await conversation_token(visitor, public_id)
    await reply(visitor, public_id, token, "How much leave?")

    response = await rate(visitor, public_id, token, score)

    assert response.status_code == 422, response.text
    assert (await resumed_rating(visitor, public_id, token))["score"] is None


async def test_rating_needs_a_valid_conversation_token_for_that_agent(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent = await live(app, owner)
    public_id = agent["public_id"]
    token = await conversation_token(visitor, public_id)
    await reply(visitor, public_id, token, "How much leave?")
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
        rated = await rate(visitor, path_agent, bad_token, 3)
        dismissed = await dismiss(visitor, path_agent, bad_token)

        assert rated.status_code == 401, (path_agent, bad_token)
        assert dismissed.status_code == 401, (path_agent, bad_token)
    no_header = await visitor.put(rating_path(public_id), json={"score": 3})
    assert no_header.status_code == 401
    assert await resumed_rating(visitor, public_id, token) == {
        "score": None,
        "prompt_dismissed": False,
    }
    clock.advance(timedelta(hours=24, seconds=1))
    assert (await rate(visitor, public_id, token, 3)).status_code == 401
    assert (await dismiss(visitor, public_id, token)).status_code == 401


async def test_each_conversation_has_its_own_rating(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, new_client: ClientFactory
) -> None:
    agent = await live(app, owner)
    public_id = agent["public_id"]
    token = await conversation_token(visitor, public_id)
    await reply(visitor, public_id, token, "How much leave?")
    stranger = await new_client()
    their_token = await conversation_token(stranger, public_id)
    await reply(stranger, public_id, their_token, "Can I carry leave over?")

    await rate(visitor, public_id, token, 5)
    await dismiss(stranger, public_id, their_token)

    assert await resumed_rating(visitor, public_id, token) == {
        "score": 5,
        "prompt_dismissed": False,
    }
    assert await resumed_rating(stranger, public_id, their_token) == {
        "score": None,
        "prompt_dismissed": True,
    }


# Changes, attribution and the Conversations viewer


async def test_changing_a_rating_is_recorded_in_the_change_log(
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
    await reply(visitor, public_id, token, "How much leave?")
    first = clock.now()
    await rate(visitor, public_id, token, 2)
    clock.advance(60)
    await dismiss(visitor, public_id, token)
    dismissed = clock.now()
    clock.advance(60)
    second = clock.now()
    changed = await rate(visitor, public_id, token, 4)
    # Giving the same score again changes nothing, so it isn't logged.
    clock.advance(60)
    await rate(visitor, public_id, token, 4)

    assert changed.json() == {"score": 4, "prompt_dismissed": True}
    (item,) = (await listed(editor, project_id))["items"]
    detail = await opened(editor, project_id, item["id"])
    assert item["rating"] == 4
    assert detail["rating"] == {
        "score": 4,
        "agent_version_number": 1,
        "rated_at": stamp(second),
        "prompt_dismissed_at": stamp(dismissed),
        "changes": [
            {
                "score": 2,
                "previous_score": None,
                "agent_version_number": 1,
                "changed_at": stamp(first),
            },
            {
                "score": 4,
                "previous_score": 2,
                "agent_version_number": 1,
                "changed_at": stamp(second),
            },
        ],
    }


async def test_a_rating_belongs_to_the_version_of_the_last_reply_before_it(
    app: FastAPI,
    owner: SignedUpMember,
    member_factory: MemberFactory,
    visitor: httpx.AsyncClient,
) -> None:
    editor = await member_factory(owner, "editor")
    agent = await live(app, owner)
    project_id, public_id = agent["project_id"], agent["public_id"]
    token = await conversation_token(visitor, public_id)
    await reply(visitor, public_id, token, "Asked of v1")
    await published(owner, project_id, agent["id"])
    await reply(visitor, public_id, token, "Asked of v2")
    # v1 is Live again, but the last reply before the rating was v2's: the rating is v2's.
    assert (await reverted(owner, project_id, agent["id"]))["number"] == 1
    await rate(visitor, public_id, token, 3)
    conversation_id = (await listed(editor, project_id))["items"][0]["id"]
    rated = (await opened(editor, project_id, conversation_id))["rating"]
    assert rated["agent_version_number"] == 2

    # v1 answers again, then the Visitor changes their rating: the change (and the rating
    # now) belong to v1; the logged first rating stays v2's.
    await reply(visitor, public_id, token, "Asked of v1 again")
    await rate(visitor, public_id, token, 5)
    # A later publish moves nothing.
    await published(owner, project_id, agent["id"])

    rating = (await opened(editor, project_id, conversation_id))["rating"]
    assert rating["agent_version_number"] == 1
    assert [(c["score"], c["agent_version_number"]) for c in rating["changes"]] == [
        (3, 2),
        (5, 1),
    ]


async def test_the_detail_shows_a_dismissal_without_a_rating_and_nothing_when_untouched(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent = await live(app, owner)
    project_id, public_id = agent["project_id"], agent["public_id"]
    token = await conversation_token(visitor, public_id)
    await reply(visitor, public_id, token, "How much leave?")
    await dismiss(visitor, public_id, token)
    untouched = await conversation_token(visitor, public_id)
    clock.advance(60)
    await reply(visitor, public_id, untouched, "And sick days?")

    newest, oldest = (await listed(owner, project_id))["items"]

    assert (newest["rating"], oldest["rating"]) == (None, None)
    assert (await opened(owner, project_id, newest["id"]))["rating"] is None
    assert (await opened(owner, project_id, oldest["id"]))["rating"] == {
        "score": None,
        "agent_version_number": None,
        "rated_at": None,
        "prompt_dismissed_at": stamp(clock.now() - timedelta(seconds=60)),
        "changes": [],
    }


async def test_the_list_shows_each_conversations_rating_and_filters_by_it(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent = await live(app, owner)
    project_id, public_id = agent["project_id"], agent["public_id"]

    async def chat(question: str, *scores: int, dismissed: bool = False) -> None:
        token = await conversation_token(visitor, public_id)
        await reply(visitor, public_id, token, question)
        for score in scores:
            await rate(visitor, public_id, token, score)
        if dismissed:
            await dismiss(visitor, public_id, token)
        clock.advance(60)

    await chat("Loved", 5)
    await chat("Hated", 1)
    # "Changed" goes from 5 to 1: only the current score counts.
    await chat("Changed", 5, 1)
    await chat("Dismissed", dismissed=True)
    await chat("Silent")
    await playground_chat(owner, project_id, agent["id"], "Playground")

    def previews(page: dict[str, Any]) -> list[str]:
        return [item["preview"] for item in page["items"]]

    everything = await listed(owner, project_id)
    assert [(i["preview"], i["rating"]) for i in everything["items"]] == [
        ("Playground", None),
        ("Silent", None),
        ("Dismissed", None),
        ("Changed", 1),
        ("Hated", 1),
        ("Loved", 5),
    ]
    assert previews(await listed(owner, project_id, rating="1")) == ["Changed", "Hated"]
    assert previews(await listed(owner, project_id, rating="5")) == ["Loved"]
    assert previews(await listed(owner, project_id, rating="3")) == []
    assert previews(await listed(owner, project_id, rating="any")) == [
        "Changed",
        "Hated",
        "Loved",
    ]
    none = await listed(owner, project_id, rating="none")
    assert previews(none) == ["Playground", "Silent", "Dismissed"]
    assert none["total"] == 3
    combined = await listed(owner, project_id, rating="none", playground="false")
    assert previews(combined) == ["Silent", "Dismissed"]
    for bad in ("0", "6", "great"):
        refused = await owner.client.get(
            conversations_path(owner, project_id), params={"rating": bad}
        )
        assert refused.status_code == 422, bad


async def test_the_rating_filter_follows_a_changed_rating(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await live(app, owner)
    project_id, public_id = agent["project_id"], agent["public_id"]
    token = await conversation_token(visitor, public_id)
    await reply(visitor, public_id, token, "How much leave?")
    await rate(visitor, public_id, token, 1)
    await rate(visitor, public_id, token, 5)

    assert (await listed(owner, project_id, rating="1"))["total"] == 0
    assert (await listed(owner, project_id, rating="5"))["total"] == 1
