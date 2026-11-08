"""API seam: rate limits. Visitors who flood an Agent are slowed per Conversation (its token)
and per IP address, with sliding one-minute windows kept in Redis and limits taken from the
Agent's Operational Settings. A refused message streams an ``unavailable`` event carrying the
Agent's unavailable text; nothing is saved and the refusal isn't counted. The Playground is
exempt."""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text

from tests.agents import answer_with, ask, parse_sse, start_conversation, use_default_model
from tests.conftest import BASE_URL, MemberFactory, SignedUpMember
from tests.fakes.clock import ControllableClock
from tests.integration.test_bedrock_credentials import audit_events
from tests.integration.test_embed import conversation_token, live_agent, send, settings_path
from tests.integration.test_playground import echo

DEFAULT_UNAVAILABLE = "This assistant is temporarily unavailable. Please try again later."
CHANGED = "agent.operational_settings_changed"
UNAVAILABLE = ("unavailable", {"reason": "rate_limited", "message": DEFAULT_UNAVAILABLE})

VisitorFactory = Callable[..., Awaitable[httpx.AsyncClient]]


@pytest.fixture
async def visitor_from(app: FastAPI) -> AsyncIterator[VisitorFactory]:
    """Opens a Visitor's client (no Studio session) whose connection comes from ``ip``."""
    async with AsyncExitStack() as stack:

        async def open_client(ip: str = "203.0.113.10") -> httpx.AsyncClient:
            transport = httpx.ASGITransport(app=app, client=(ip, 50000))
            return await stack.enter_async_context(
                httpx.AsyncClient(transport=transport, base_url=BASE_URL)
            )

        yield open_client


@pytest.fixture
async def owner(app: FastAPI, owner: SignedUpMember) -> SignedUpMember:
    """An Owner whose Organisation's Default Model answers (echoing the prompt)."""
    answer_with(app, echo)
    await use_default_model(owner)
    return owner


async def limit(owner: SignedUpMember, agent: dict[str, Any], **limits: int) -> None:
    response = await owner.client.patch(
        settings_path(owner, agent["project_id"], agent["id"]), json=limits
    )
    assert response.status_code == 200, response.text


async def outcome(
    visitor: httpx.AsyncClient,
    agent: dict[str, Any],
    token: str,
    headers: dict[str, str] | None = None,
) -> str:
    """``answered`` or ``refused`` for one message, checking the refusal's event."""
    response = await visitor.post(
        f"/api/widget/agents/{agent['public_id']}/messages",
        json={"content": "Hello?"},
        headers={"Authorization": f"Bearer {token}", **(headers or {})},
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(response.text)
    if events[-1][0] == "done":
        return "answered"
    assert events == [UNAVAILABLE]
    return "refused"


async def message_count(app: FastAPI, agent: dict[str, Any]) -> int:
    async with app.state.sessionmaker() as session:
        count: int = await session.scalar(
            text(
                "SELECT count(*) FROM messages m JOIN conversations c ON c.id = m.conversation_id"
                " JOIN agents a ON a.id = c.agent_id WHERE a.public_id = :public_id"
            ),
            {"public_id": agent["public_id"]},
        )
    return count


# The limits are Operational Settings


async def test_a_new_agent_has_default_rate_limits(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    agent = await live_agent(owner)

    response = await editor.client.get(settings_path(editor, agent["project_id"], agent["id"]))

    assert response.status_code == 200, response.text
    assert response.json()["conversation_messages_per_minute"] == 10
    assert response.json()["ip_messages_per_minute"] == 30


async def test_an_editor_sets_the_rate_limits_and_the_change_is_audited(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    agent = await live_agent(owner)
    path = settings_path(editor, agent["project_id"], agent["id"])

    response = await editor.client.patch(
        path, json={"conversation_messages_per_minute": 4, "ip_messages_per_minute": 12}
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "allowed_origins": [],
        "unavailable_text": DEFAULT_UNAVAILABLE,
        "conversation_messages_per_minute": 4,
        "ip_messages_per_minute": 12,
        "daily_token_budget": 1_000_000,
    }
    assert (await editor.client.get(path)).json() == response.json()
    events = await audit_events(owner, CHANGED)
    assert [(e["actor"]["id"], e["before"], e["after"]) for e in events] == [
        (
            editor.member_id,
            {"conversation_messages_per_minute": 10, "ip_messages_per_minute": 30},
            {"conversation_messages_per_minute": 4, "ip_messages_per_minute": 12},
        )
    ]
    # Changing only one leaves the other.
    one = await editor.client.patch(path, json={"ip_messages_per_minute": 40})
    assert one.json()["conversation_messages_per_minute"] == 4
    assert one.json()["ip_messages_per_minute"] == 40


@pytest.mark.parametrize(
    "change",
    [
        {"conversation_messages_per_minute": 0},
        {"conversation_messages_per_minute": 1001},
        {"ip_messages_per_minute": 0},
        {"ip_messages_per_minute": 10001},
        {"ip_messages_per_minute": None},
        {"conversation_messages_per_minute": "lots"},
    ],
)
async def test_rate_limits_out_of_range_are_refused(
    owner: SignedUpMember, change: dict[str, Any]
) -> None:
    agent = await live_agent(owner)
    path = settings_path(owner, agent["project_id"], agent["id"])

    response = await owner.client.patch(path, json=change)

    assert response.status_code == 422, response.text
    found = (await owner.client.get(path)).json()
    assert (found["conversation_messages_per_minute"], found["ip_messages_per_minute"]) == (10, 30)
    assert await audit_events(owner, CHANGED) == []


# Per Conversation


async def test_a_conversation_over_its_limit_is_refused_until_its_sliding_window_frees_up(
    app: FastAPI, owner: SignedUpMember, visitor_from: VisitorFactory, clock: ControllableClock
) -> None:
    agent = await live_agent(owner)
    await limit(owner, agent, conversation_messages_per_minute=2)
    visitor = await visitor_from()
    token = await conversation_token(visitor, agent["public_id"])

    assert await outcome(visitor, agent, token) == "answered"  # t=0
    clock.advance(30)
    assert await outcome(visitor, agent, token) == "answered"  # t=30
    clock.advance(29)
    assert await outcome(visitor, agent, token) == "refused"  # t=59: two in the last minute
    # The refused question wasn't saved: two questions and two answers.
    assert await message_count(app, agent) == 4
    clock.advance(1)
    # t=60: the first message has left the window. A fixed window would admit two now.
    assert await outcome(visitor, agent, token) == "answered"
    assert await outcome(visitor, agent, token) == "refused"
    clock.advance(30)
    # t=90: the t=30 message has left too; refusals were never counted.
    assert await outcome(visitor, agent, token) == "answered"


async def test_another_conversation_has_its_own_limit(
    owner: SignedUpMember, visitor_from: VisitorFactory, clock: ControllableClock
) -> None:
    agent = await live_agent(owner)
    await limit(owner, agent, conversation_messages_per_minute=1)
    visitor = await visitor_from()
    first = await conversation_token(visitor, agent["public_id"])
    second = await conversation_token(visitor, agent["public_id"])

    assert await outcome(visitor, agent, first) == "answered"
    assert await outcome(visitor, agent, first) == "refused"
    assert await outcome(visitor, agent, second) == "answered"


async def test_a_new_limit_applies_to_the_next_message(
    owner: SignedUpMember, visitor_from: VisitorFactory, clock: ControllableClock
) -> None:
    agent = await live_agent(owner)
    await limit(owner, agent, conversation_messages_per_minute=1)
    visitor = await visitor_from()
    token = await conversation_token(visitor, agent["public_id"])
    assert await outcome(visitor, agent, token) == "answered"
    assert await outcome(visitor, agent, token) == "refused"

    await limit(owner, agent, conversation_messages_per_minute=3)

    assert await outcome(visitor, agent, token) == "answered"


async def test_a_refusal_carries_the_agents_own_unavailable_text(
    owner: SignedUpMember, visitor_from: VisitorFactory, clock: ControllableClock
) -> None:
    agent = await live_agent(owner)
    path = settings_path(owner, agent["project_id"], agent["id"])
    await owner.client.patch(
        path, json={"conversation_messages_per_minute": 1, "unavailable_text": "Busy; back soon."}
    )
    visitor = await visitor_from()
    token = await conversation_token(visitor, agent["public_id"])
    await send(visitor, agent["public_id"], token, "Hello?")

    response = await send(visitor, agent["public_id"], token, "Hello again?")

    assert parse_sse(response.text) == [
        ("unavailable", {"reason": "rate_limited", "message": "Busy; back soon."})
    ]


# Per IP


async def test_an_ip_over_its_limit_is_refused_across_conversations_and_others_are_not(
    owner: SignedUpMember, visitor_from: VisitorFactory, clock: ControllableClock
) -> None:
    agent = await live_agent(owner)
    await limit(owner, agent, ip_messages_per_minute=3)
    flooder = await visitor_from("203.0.113.7")
    tokens = [await conversation_token(flooder, agent["public_id"]) for _ in range(4)]
    neighbour = await visitor_from("203.0.113.8")
    other = await conversation_token(neighbour, agent["public_id"])

    assert [await outcome(flooder, agent, token) for token in tokens] == [
        "answered",
        "answered",
        "answered",
        "refused",
    ]
    assert await outcome(neighbour, agent, other) == "answered"
    clock.advance(60)
    assert await outcome(flooder, agent, tokens[3]) == "answered"


async def test_an_ips_count_is_per_agent(
    owner: SignedUpMember, visitor_from: VisitorFactory, clock: ControllableClock
) -> None:
    busy = await live_agent(owner)
    quiet = await live_agent(owner)
    await limit(owner, busy, ip_messages_per_minute=1)
    visitor = await visitor_from()
    busy_token = await conversation_token(visitor, busy["public_id"])
    quiet_token = await conversation_token(visitor, quiet["public_id"])

    assert await outcome(visitor, busy, busy_token) == "answered"
    assert await outcome(visitor, busy, busy_token) == "refused"
    assert await outcome(visitor, quiet, quiet_token) == "answered"


async def test_forwarded_addresses_count_only_through_trusted_proxies(
    settings_env: pytest.MonkeyPatch,
    owner: SignedUpMember,
    visitor_from: VisitorFactory,
    clock: ControllableClock,
) -> None:
    agent = await live_agent(owner)
    await limit(owner, agent, ip_messages_per_minute=1)
    # The load balancer, a trusted proxy (see the `app` override below), forwards two Visitors.
    balancer = await visitor_from("10.0.1.5")
    first = await conversation_token(balancer, agent["public_id"])
    second = await conversation_token(balancer, agent["public_id"])
    one = {"X-Forwarded-For": "198.51.100.1"}
    # The Visitor's own claim (left) is ignored: the balancer saw 198.51.100.2.
    two = {"X-Forwarded-For": "198.51.100.1, 198.51.100.2"}

    assert await outcome(balancer, agent, first, one) == "answered"
    assert await outcome(balancer, agent, first, one) == "refused"
    assert await outcome(balancer, agent, second, two) == "answered"
    # A Visitor connecting directly can't pose as someone else: its own address counts.
    direct = await visitor_from("198.51.100.3")
    token = await conversation_token(direct, agent["public_id"])
    assert await outcome(direct, agent, token, {"X-Forwarded-For": "198.51.100.9"}) == "answered"
    assert await outcome(direct, agent, token, {"X-Forwarded-For": "198.51.100.10"}) == "refused"


@pytest.fixture
def settings_env(settings_env: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    # The app's load balancers: a subnet, as a deployment would list its VPC's.
    settings_env.setenv("TRUSTED_PROXIES", "10.0.0.0/16, 2001:db8::1")
    return settings_env


# Exemptions and edges


async def test_the_playground_is_exempt(
    app: FastAPI, owner: SignedUpMember, visitor_from: VisitorFactory, clock: ControllableClock
) -> None:
    agent = await live_agent(owner)
    await limit(owner, agent, conversation_messages_per_minute=1, ip_messages_per_minute=1)
    conversation_id = (await start_conversation(owner, agent["project_id"], agent["id"]))["id"]

    for _ in range(3):
        response = await ask(owner, agent["project_id"], agent["id"], conversation_id, "Hello?")
        assert response.status_code == 200, response.text
        assert parse_sse(response.text)[-1][0] == "done"
    # And the Playground's messages don't use up the Visitors' allowance.
    visitor = await visitor_from()
    token = await conversation_token(visitor, agent["public_id"])
    assert await outcome(visitor, agent, token) == "answered"


async def test_an_invalid_token_is_refused_before_admission(
    owner: SignedUpMember, visitor_from: VisitorFactory, clock: ControllableClock
) -> None:
    agent = await live_agent(owner)
    await limit(owner, agent, ip_messages_per_minute=1)
    visitor = await visitor_from()

    for _ in range(2):
        response = await send(visitor, agent["public_id"], "not-a-token", "Hello?")
        assert response.status_code == 401
    # Bad tokens don't use up the IP's allowance.
    token = await conversation_token(visitor, agent["public_id"])
    assert await outcome(visitor, agent, token) == "answered"
