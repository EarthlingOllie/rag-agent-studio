"""API seam: spend controls on Agent replies (cluster C5).

- The Token Budget holds under concurrency: admission reserves an estimate of each reply's
  cost atomically, so messages sent while replies are still streaming can't all pass the same
  "under budget" check (WID-F1). The reservation is settled with the reply's actual usage, and
  given back when the response ends without recording one, however it ends. A reply can cost
  more than it reserved, so an Agent answers a few replies at once, one per address: the day
  ends at most that many replies over its budget, and one client can't hold the Agent.
- The widget API answers browsers only from the widget itself or a site on the Agent's Allowed
  Origins: a request whose ``Origin`` (or, without one, ``Referer``) names another site gets
  403 (WID-F2). Clients that send neither header are bounded per Agent as well as per
  Conversation and address.
- The Playground has its own limits, separate from Visitors': a rate limit per Member and per
  Organisation, and a daily Playground Token Budget per Organisation that its replies count
  against (AGT-F1), with a cap on the answers streaming at once. A refused question gets 429
  and isn't saved.
"""

import asyncio
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, MutableMapping
from contextlib import AsyncExitStack
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic_ai.exceptions import ModelAuthenticationError, ModelHTTPError
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo

from app.embed.admission import (
    AGENT_MESSAGES_PER_MINUTE,
    LEASE_SECONDS,
    LONGEST_REPLY_SECONDS,
    REPLIES_IN_FLIGHT,
    RESERVED_TOKENS,
    Admission,
    Limits,
    PlaygroundLimits,
    Refusal,
    Reservation,
)
from app.playground.api import playground_limits
from tests.agents import (
    answer_with,
    ask,
    create_agent,
    parse_sse,
    playground_path,
    start_conversation,
    use_default_model,
)
from tests.conftest import BASE_URL, STUDIO_URL, ClientFactory, MemberFactory, SignedUpMember
from tests.fakes.clock import ControllableClock
from tests.integration.test_agent_versions import knowledgeable_project, published
from tests.integration.test_embed import (
    boot,
    conversation_token,
    conversations_path,
    live_agent,
    messages_path,
    send,
)
from tests.integration.test_playground_errors import failing
from tests.integration.test_rate_limits import message_count
from tests.integration.test_token_budget import PER_ANSWER, alert, budget, three_words, usage

DEFAULT_UNAVAILABLE = "This assistant is temporarily unavailable. Please try again later."
BUSY = ("unavailable", {"reason": "rate_limited", "message": DEFAULT_UNAVAILABLE})


@pytest.fixture
async def visitor(new_client: ClientFactory) -> httpx.AsyncClient:
    """A browser on someone's website: no Studio session."""
    return await new_client()


AddressedClients = Callable[[int], Awaitable[httpx.AsyncClient]]


@pytest.fixture
async def visitors_at(app: FastAPI) -> AsyncIterator[AddressedClients]:
    """Browsers on someone's website, each from its own address (``203.0.113.n``)."""
    async with AsyncExitStack() as stack:

        async def open_client(n: int) -> httpx.AsyncClient:
            transport = httpx.ASGITransport(app=app, client=(f"203.0.113.{n}", 123))
            return await stack.enter_async_context(
                httpx.AsyncClient(transport=transport, base_url=BASE_URL)
            )

        yield open_client


@pytest.fixture
async def agent(app: FastAPI, owner: SignedUpMember) -> dict[str, Any]:
    """A live Agent over a Project holding the leave policy, so questions reach the model."""
    project_id = await knowledgeable_project(app, owner)
    answer_with(app, three_words)
    created: dict[str, Any] = await create_agent(owner, project_id)
    await published(owner, project_id, created["id"])
    return created


class Gate:
    """A model whose replies wait, mid-stream, until the test lets them finish."""

    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        # One item per reply that has reached the gate.
        self.arrivals: asyncio.Queue[None] = asyncio.Queue()

    async def stream(self, messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
        self.entered.set()
        self.arrivals.put_nowait(None)
        await self.release.wait()
        yield "Twenty five days"


class CostlyGate(Gate):
    """A gated model whose every reply costs far more than an admitted reply reserves."""

    async def stream(self, messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
        self.entered.set()
        self.arrivals.put_nowait(None)
        await self.release.wait()
        yield "day " * 20_000


async def outcome_of(response: httpx.Response) -> str:
    assert response.status_code == 200, response.text
    events = parse_sse(response.text)
    if events[-1][0] == "done":
        return "answered"
    assert events == [BUSY], events
    return "refused"


async def browser_leaves(
    app: FastAPI,
    client: httpx.AsyncClient,
    path: str,
    content: str,
    *,
    headers: dict[str, str] | None = None,
    gate: Gate | None = None,
    dropped: bool = False,
) -> None:
    """Sends a message straight to the app as a browser that then goes away: mid-reply, once
    ``gate`` has a reply waiting at the model, or (without a gate) before reading anything, so
    the response's stream never starts. ``dropped``: the server cancels the request instead of
    seeing a disconnect message (as a server does when the connection is lost)."""
    request = client.build_request("POST", path, json={"content": content}, headers=headers)
    started = asyncio.Event()
    leave = asyncio.Event()
    asked = False

    async def receive() -> dict[str, Any]:
        nonlocal asked
        if not asked:
            asked = True
            return {"type": "http.request", "body": request.content, "more_body": False}
        await leave.wait()
        return {"type": "http.disconnect"}

    async def send(message: MutableMapping[str, Any]) -> None:
        if message["type"] == "http.response.start":
            started.set()
            if gate is None:
                await asyncio.Event().wait()  # never reads the response

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "headers": [(k.lower(), v) for (k, v) in request.headers.raw],
        "scheme": request.url.scheme,
        "path": request.url.path,
        "raw_path": request.url.raw_path,
        "query_string": b"",
        "server": (request.url.host, request.url.port),
        "client": ("127.0.0.1", 123),  # the address the test clients use
        "root_path": "",
    }
    call = asyncio.create_task(app(scope, receive, send))
    await asyncio.wait_for((started if gate is None else gate.entered).wait(), 10)
    if dropped:
        call.cancel()
        await asyncio.wait([call], timeout=10)
        assert call.cancelled()
        return
    leave.set()
    await asyncio.wait_for(call, 10)


# WID-F1: the Token Budget holds under concurrency


async def test_messages_sent_while_a_reply_streams_cannot_overspend_the_token_budget(
    app: FastAPI, owner: SignedUpMember, agent: dict[str, Any], visitor: httpx.AsyncClient
) -> None:
    await budget(owner, agent, 100)
    gate = Gate()
    answer_with(app, gate.stream)
    tokens = [await conversation_token(visitor, agent["public_id"]) for _ in range(4)]
    first = asyncio.create_task(send(visitor, agent["public_id"], tokens[0], "How much leave?"))
    await asyncio.wait_for(gate.entered.wait(), 10)

    # The first reply is still streaming: its reserved cost already holds the budget, so the
    # other Visitors are asked to try again rather than all passing the same check. (Were they
    # admitted, their replies would wait at the gate too, so give them a moment, then open it.)
    others = [
        asyncio.create_task(send(visitor, agent["public_id"], t, "How much leave?"))
        for t in tokens[1:]
    ]
    await asyncio.wait(others, timeout=5)
    gate.release.set()

    assert [await outcome_of(await r) for r in others] == ["refused"] * 3
    assert await outcome_of(await first) == "answered"
    # Only the one reply was paid for, and the budget isn't spent, so no alert.
    assert (await usage(owner, agent))["tokens_used"] == PER_ANSWER
    assert await alert(owner, agent) == (False, [False])
    # Once it has finished, its reservation is settled with its actual usage: room again.
    assert await outcome_of(await send(visitor, agent["public_id"], tokens[1], "And?")) == (
        "answered"
    )


async def send_at_once(
    gate: Gate, agent: dict[str, Any], visitors: list[httpx.AsyncClient]
) -> list[str]:
    """Each Visitor sends a message while the replies admitted are held at ``gate``; then the
    gate opens. The outcome of each message, in order."""
    tokens = [await conversation_token(v, agent["public_id"]) for v in visitors]
    sent = [
        asyncio.create_task(send(v, agent["public_id"], t, "How much leave?"))
        for v, t in zip(visitors, tokens, strict=True)
    ]
    # Refused messages are answered at once; admitted ones wait at the gate. Give the refused
    # ones a moment, then open it.
    await asyncio.wait(sent, timeout=5)
    gate.release.set()
    return [await outcome_of(await r) for r in sent]


async def test_an_agent_answers_visitors_on_different_addresses_at_once_up_to_a_cap(
    app: FastAPI, owner: SignedUpMember, agent: dict[str, Any], visitors_at: AddressedClients
) -> None:
    # One Visitor's reply doesn't hold the Agent for everyone: several are answered at once,
    # up to the Agent's replies in flight.
    await budget(owner, agent, 1_000_000)
    gate = Gate()
    answer_with(app, gate.stream)
    visitors = [await visitors_at(n) for n in range(REPLIES_IN_FLIGHT + 2)]

    outcomes = await send_at_once(gate, agent, visitors)

    # (Which messages are admitted depends on which reaches admission first.)
    assert sorted(outcomes) == ["answered"] * REPLIES_IN_FLIGHT + ["refused"] * 2


async def test_one_address_has_one_reply_in_flight(
    app: FastAPI, owner: SignedUpMember, agent: dict[str, Any], visitors_at: AddressedClients
) -> None:
    # One client can't take every place the Agent has.
    await budget(owner, agent, 1_000_000)
    gate = Gate()
    answer_with(app, gate.stream)
    same = await visitors_at(1)

    outcomes = await send_at_once(gate, agent, [same, same, await visitors_at(2)])

    assert sorted(outcomes[:2]) == ["answered", "refused"]
    assert outcomes[2] == "answered"


async def test_concurrent_replies_costing_more_than_their_reservation_overspend_by_at_most_the_cap(
    app: FastAPI, owner: SignedUpMember, agent: dict[str, Any], visitors_at: AddressedClients
) -> None:
    # Room for two replies' reservations, plus a token: the held reservations admit three
    # replies, each of which then costs more than twice what it reserved.
    daily = 2 * RESERVED_TOKENS + 1
    await budget(owner, agent, daily)
    gate = CostlyGate()
    answer_with(app, gate.stream)
    visitors = [await visitors_at(n) for n in range(REPLIES_IN_FLIGHT + 2)]

    outcomes = await send_at_once(gate, agent, visitors)

    answered = outcomes.count("answered")
    assert 1 <= answered <= REPLIES_IN_FLIGHT
    # The day ends at most the replies in flight over its budget, however much each costs; the
    # budget is now spent.
    assert (await usage(owner, agent))["tokens_used"] > daily
    assert await message_count(app, agent) == 2 * answered
    later = await send(
        visitors[0],
        agent["public_id"],
        await conversation_token(visitors[0], agent["public_id"]),
        "And?",
    )
    assert parse_sse(later.text)[-1][1]["reason"] == "budget_exhausted"


async def test_a_failed_reply_gives_back_its_reservation(
    app: FastAPI, owner: SignedUpMember, agent: dict[str, Any], visitor: httpx.AsyncClient
) -> None:
    await budget(owner, agent, 100)
    error = ModelHTTPError.for_category(
        ModelAuthenticationError, status_code=401, model_name="gpt-4.1-mini"
    )
    answer_with(app, failing(error))
    token = await conversation_token(visitor, agent["public_id"])
    failed = await send(visitor, agent["public_id"], token, "How much leave?")
    assert parse_sse(failed.text)[-1][0] == "error"

    answer_with(app, three_words)

    assert await outcome_of(await send(visitor, agent["public_id"], token, "Again?")) == "answered"
    assert (await usage(owner, agent))["tokens_used"] == PER_ANSWER


async def test_a_turn_that_cannot_be_prepared_gives_back_its_reservation(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    # Published while the Organisation has no Default Model: messages are admitted, then
    # can't be answered.
    created = await live_agent(owner)
    await budget(owner, created, 100)
    token = await conversation_token(visitor, created["public_id"])
    unavailable = await send(visitor, created["public_id"], token, "How much leave?")
    assert unavailable.status_code == 503, unavailable.text

    await use_default_model(owner)
    answer_with(app, three_words)

    answered = await send(visitor, created["public_id"], token, "Again?")
    assert await outcome_of(answered) == "answered"


@pytest.mark.parametrize(
    ("mid_reply", "dropped"),
    [(True, False), (False, False), (True, True)],
    ids=["mid-reply", "before-reading", "connection-dropped"],
)
async def test_a_visitor_who_goes_away_gives_back_the_agents_place_at_once(
    app: FastAPI,
    owner: SignedUpMember,
    agent: dict[str, Any],
    visitor: httpx.AsyncClient,
    mid_reply: bool,
    dropped: bool,
) -> None:
    await budget(owner, agent, 100)
    gate = Gate()
    answer_with(app, gate.stream)
    token = await conversation_token(visitor, agent["public_id"])

    await browser_leaves(
        app,
        visitor,
        messages_path(agent["public_id"]),
        "How much leave?",
        headers={"Authorization": f"Bearer {token}"},
        gate=gate if mid_reply else None,
        dropped=dropped,
    )
    answer_with(app, three_words)

    # No time has passed: the reply that was abandoned holds neither the budget nor a place.
    assert await outcome_of(await send(visitor, agent["public_id"], token, "Again?")) == "answered"


# WID-F2: the widget API checks the browser's Origin


FOREIGN = "https://elsewhere.example.net"
SHOP = "https://shop.example.com"


async def widget_requests(
    visitor: httpx.AsyncClient, public_id: str, token: str, headers: dict[str, str]
) -> list[int]:
    """The status of each widget API route for a browser sending ``headers``."""
    bootstrap = boot(await visitor.get(f"/widget/a/{public_id}"))["bootstrap_token"]
    bearer = {"Authorization": f"Bearer {token}", **headers}
    conversation = f"/api/widget/agents/{public_id}/conversation"
    return [
        (
            await visitor.post(
                conversations_path(public_id), json={"bootstrap_token": bootstrap}, headers=headers
            )
        ).status_code,
        (
            await visitor.post(messages_path(public_id), json={"content": "Hi?"}, headers=bearer)
        ).status_code,
        (await visitor.get(conversation, headers=bearer)).status_code,
        (await visitor.delete(conversation, headers=bearer)).status_code,
    ]


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": FOREIGN},
        {"Origin": "null"},
        {"Origin": "https://shop.example.com.elsewhere.example.net"},
        {"Origin": "http://shop.example.com"},
        {"Referer": f"{FOREIGN}/pricing?q=1"},
        {"Referer": "not a url"},
    ],
)
async def test_a_browser_on_a_site_not_on_the_allowed_origins_is_refused(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, headers: dict[str, str]
) -> None:
    agent = await live_agent(owner, SHOP)
    token = await conversation_token(visitor, agent["public_id"])
    saved = await message_count(app, agent)

    statuses = await widget_requests(visitor, agent["public_id"], token, headers)

    assert statuses == [403, 403, 403, 403]
    assert await message_count(app, agent) == saved
    # The Conversation wasn't ended either: its token still works from the widget.
    resumed = await visitor.get(
        f"/api/widget/agents/{agent['public_id']}/conversation",
        headers={"Authorization": f"Bearer {token}", "Origin": STUDIO_URL},
    )
    assert resumed.status_code == 200, resumed.text


@pytest.mark.parametrize(
    "headers",
    [
        # The widget itself: its iframe is served from the Studio's origin.
        {"Origin": STUDIO_URL},
        {"Origin": SHOP},
        {"Origin": "https://help.example.org"},
        {"Origin": "http://localhost:3000"},
        {"Referer": f"{SHOP}/help"},
        # No Origin or Referer: not a browser's cross-site request.
        {},
    ],
)
async def test_the_widget_and_allowed_sites_are_answered(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, headers: dict[str, str]
) -> None:
    agent = await live_agent(owner, SHOP, "https://*.example.org", "http://localhost:*")
    token = await conversation_token(visitor, agent["public_id"])

    statuses = await widget_requests(visitor, agent["public_id"], token, headers)

    # Created; answered (no Default Model here, so its unavailable text); read; ended.
    assert statuses == [201, 503, 200, 204]


async def test_an_unknown_agent_from_another_site_is_refused(
    visitor: httpx.AsyncClient,
) -> None:
    response = await visitor.post(
        conversations_path("agt_unknown"), json={"bootstrap_token": "x"}, headers={"Origin": SHOP}
    )

    assert response.status_code == 403, response.text


async def test_an_agent_has_a_rate_limit_across_every_conversation_and_address(
    app: FastAPI, clock: ControllableClock
) -> None:
    # Clients that send no Origin are bounded per Agent too, not only per IP and Conversation.
    admission = Admission(app.state.redis, clock)
    limits = Limits(
        public_id=f"agt_{uuid.uuid4().hex}",
        conversation_messages_per_minute=10,
        ip_messages_per_minute=10,
        daily_token_budget=1_000_000,
        agent_messages_per_minute=3,
    )
    other = Limits(
        public_id=f"agt_{uuid.uuid4().hex}",
        conversation_messages_per_minute=10,
        ip_messages_per_minute=10,
        daily_token_budget=1_000_000,
        agent_messages_per_minute=3,
    )

    async def admit(agent: Limits, n: int) -> Refusal | None:
        found = await admission.admit(agent, f"token-{n}", f"203.0.113.{n}")
        if isinstance(found, Reservation):
            await admission.release(found)
            return None
        return found

    assert [await admit(limits, n) for n in range(4)] == [None, None, None, Refusal.AGENT_RATE]
    assert await admit(other, 9) is None
    clock.advance(61)
    assert await admit(limits, 5) is None


async def test_usage_recorded_without_its_reservation_frees_the_agents_reply_in_flight(
    app: FastAPI, clock: ControllableClock
) -> None:
    # A caller that records a reply's usage but not its reservation (the attack panel) must not
    # leave the address's place in flight held until the reservation lapses.
    admission = Admission(app.state.redis, clock)
    # (Reservations outlive a test in Redis, so each test's Agents are new.)
    public_id = f"agt_{uuid.uuid4().hex}"
    limits = Limits(public_id, 10, 10, 1_000_000)
    assert isinstance(await admission.admit(limits, "token-1", "203.0.113.1"), Reservation)
    assert await admission.admit(limits, "token-2", "203.0.113.1") is Refusal.BUDGET_IN_USE

    assert await admission.record_usage(public_id, 40) == 40

    assert isinstance(await admission.admit(limits, "token-2", "203.0.113.1"), Reservation)


def test_an_agent_has_a_default_rate_limit_and_replies_in_flight() -> None:
    limits = Limits("agt_x", 10, 30, 100_000)
    assert (
        limits.agent_messages_per_minute,
        limits.replies_in_flight,
        limits.replies_in_flight_per_address,
    ) == (AGENT_MESSAGES_PER_MINUTE, 4, 1)
    # A reply's place lapses this long after its response stops renewing it, and no reply
    # renews it for longer than the longest a reply may stream.
    assert (LEASE_SECONDS, LONGEST_REPLY_SECONDS) == (30, 300)


async def test_a_reservation_no_response_holds_lapses_after_its_lease(
    app: FastAPI, clock: ControllableClock
) -> None:
    # A reply whose response never got going (the process holding it died) holds its place
    # only until its lease lapses, not for as long as any reply may stream.
    admission = Admission(app.state.redis, clock)
    limits = Limits(f"agt_{uuid.uuid4().hex}", 10, 10, 1_000_000)
    assert isinstance(await admission.admit(limits, "token-1", "203.0.113.1"), Reservation)
    assert await admission.admit(limits, "token-2", "203.0.113.1") is Refusal.BUDGET_IN_USE

    clock.advance(LEASE_SECONDS + 1)

    assert isinstance(await admission.admit(limits, "token-2", "203.0.113.1"), Reservation)


async def test_a_reservation_is_held_while_its_response_lasts_up_to_the_longest_reply(
    app: FastAPI, clock: ControllableClock
) -> None:
    admission = Admission(app.state.redis, clock)
    limits = Limits(f"agt_{uuid.uuid4().hex}", 10, 10, 1_000_000)
    reservation = await admission.admit(limits, "token-1", "203.0.113.1")
    assert isinstance(reservation, Reservation)
    holding = asyncio.create_task(admission.hold(reservation, every=0.01))

    async def renewed() -> None:
        await asyncio.sleep(0.1)  # several renewals on the real clock

    # Renewed while the response lasts: still held well past one lease.
    for _ in range(3):
        clock.advance(LEASE_SECONDS - 1)
        await renewed()
    assert await admission.admit(limits, "token-2", "203.0.113.1") is Refusal.BUDGET_IN_USE

    # A response that lasts longer than any reply may stream stops being renewed.
    clock.advance(LONGEST_REPLY_SECONDS)
    await asyncio.wait_for(holding, 1)
    clock.advance(LEASE_SECONDS + 1)
    assert isinstance(await admission.admit(limits, "token-2", "203.0.113.1"), Reservation)


async def test_a_settled_reservation_is_not_renewed(app: FastAPI, clock: ControllableClock) -> None:
    admission = Admission(app.state.redis, clock)
    limits = Limits(f"agt_{uuid.uuid4().hex}", 10, 10, 1_000_000)
    reservation = await admission.admit(limits, "token-1", "203.0.113.1")
    assert isinstance(reservation, Reservation)
    holding = asyncio.create_task(admission.hold(reservation, every=0.01))
    await admission.record_usage(limits.public_id, 40, reservation)
    await asyncio.sleep(0.05)

    assert isinstance(await admission.admit(limits, "token-2", "203.0.113.1"), Reservation)
    holding.cancel()


async def test_one_member_has_a_capped_share_of_the_playgrounds_answers_in_flight(
    app: FastAPI, clock: ControllableClock
) -> None:
    admission = Admission(app.state.redis, clock)
    organisation, member, other = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    limits = PlaygroundLimits(answers_in_flight=4, answers_in_flight_per_member=1)

    assert isinstance(await admission.admit_playground(limits, organisation, member), Reservation)
    assert await admission.admit_playground(limits, organisation, member) is (Refusal.BUDGET_IN_USE)
    assert isinstance(await admission.admit_playground(limits, organisation, other), Reservation)


# AGT-F1: the Playground's own limits


def playground_limited(app: FastAPI, **limits: int) -> None:
    app.dependency_overrides[playground_limits] = lambda: PlaygroundLimits(**limits)


async def asked(member: SignedUpMember, agent: dict[str, Any], conversation: str) -> str:
    """``answered``, or the reason a Playground question got 429."""
    response = await ask(member, agent["project_id"], agent["id"], conversation, "How much leave?")
    if response.status_code == 429:
        detail: str = response.json()["detail"]
        return detail
    assert response.status_code == 200, response.text
    assert parse_sse(response.text)[-1][0] == "done", response.text
    return "answered"


async def playground_messages(
    member: SignedUpMember, agent: dict[str, Any], conversation: str
) -> int:
    response = await member.client.get(
        playground_path(member, agent["project_id"], agent["id"], conversation)
    )
    assert response.status_code == 200, response.text
    return len(response.json()["messages"])


TOO_FAST = "You're sending Playground questions too fast. Wait a minute, then try again."
BUSY_PLAYGROUND = (
    "Your Organisation's answers still being written hold the Playground for now (its Token "
    "Budget or how many may be written at once). Try again when they finish."
)
SPENT = (
    "Your Organisation has used today's Playground Token Budget. It starts again at midnight UTC."
)


def test_the_playground_has_default_limits() -> None:
    assert playground_limits() == PlaygroundLimits(
        member_messages_per_minute=20,
        organisation_messages_per_minute=120,
        daily_token_budget=2_000_000,
        answers_in_flight=4,
        answers_in_flight_per_member=2,
    )


async def test_an_organisations_playground_answers_in_flight_are_capped(
    app: FastAPI, owner: SignedUpMember, agent: dict[str, Any]
) -> None:
    # However much each answer costs, at most this many are written at once, so the day ends at
    # most that many answers over the Playground Token Budget.
    playground_limited(app, answers_in_flight=2)
    gate = CostlyGate()
    answer_with(app, gate.stream)
    conversations = [
        (await start_conversation(owner, agent["project_id"], agent["id"]))["id"] for _ in range(3)
    ]
    streaming = [asyncio.create_task(asked(owner, agent, c)) for c in conversations[:2]]
    async with asyncio.timeout(10):
        for _ in streaming:
            await gate.arrivals.get()

    # (Were it admitted, its answer would wait at the gate too, so give it a moment first.)
    third = asyncio.create_task(asked(owner, agent, conversations[2]))
    await asyncio.wait([third], timeout=5)
    gate.release.set()

    assert await third == BUSY_PLAYGROUND
    assert [await s for s in streaming] == ["answered", "answered"]


async def test_each_member_has_a_playground_rate_limit(
    app: FastAPI, owner: SignedUpMember, agent: dict[str, Any], clock: ControllableClock
) -> None:
    playground_limited(app, member_messages_per_minute=2)
    conversation = (await start_conversation(owner, agent["project_id"], agent["id"]))["id"]

    assert await asked(owner, agent, conversation) == "answered"
    assert await asked(owner, agent, conversation) == "answered"
    assert await asked(owner, agent, conversation) == TOO_FAST
    # The refused question wasn't saved: two questions, two answers.
    assert await playground_messages(owner, agent, conversation) == 4

    clock.advance(60)
    assert await asked(owner, agent, conversation) == "answered"


async def test_the_organisation_has_a_playground_rate_limit_across_its_members(
    app: FastAPI,
    owner: SignedUpMember,
    member_factory: MemberFactory,
    agent: dict[str, Any],
    clock: ControllableClock,
) -> None:
    playground_limited(app, organisation_messages_per_minute=2)
    editor = await member_factory(owner, "editor")
    mine = (await start_conversation(owner, agent["project_id"], agent["id"]))["id"]
    theirs = (await start_conversation(editor, agent["project_id"], agent["id"]))["id"]

    assert await asked(owner, agent, mine) == "answered"
    assert await asked(editor, agent, theirs) == "answered"
    assert await asked(editor, agent, theirs) == TOO_FAST


async def test_playground_replies_count_against_the_organisations_playground_budget(
    app: FastAPI,
    owner: SignedUpMember,
    agent: dict[str, Any],
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    playground_limited(app, daily_token_budget=60)
    conversation = (await start_conversation(owner, agent["project_id"], agent["id"]))["id"]

    assert await asked(owner, agent, conversation) == "answered"  # 53 of 60
    assert await asked(owner, agent, conversation) == "answered"  # 106: spent
    assert await asked(owner, agent, conversation) == SPENT
    assert await playground_messages(owner, agent, conversation) == 4
    # Separate from the Agent's Visitor budget, which the Playground still doesn't use.
    assert (await usage(owner, agent))["tokens_used"] == 0
    token = await conversation_token(visitor, agent["public_id"])
    assert await outcome_of(await send(visitor, agent["public_id"], token, "Hi?")) == "answered"

    clock.advance(15 * 60 * 60)  # midnight UTC: a new day's Playground budget
    assert await asked(owner, agent, conversation) == "answered"


async def test_a_playground_question_sent_while_answers_stream_cannot_overspend(
    app: FastAPI, owner: SignedUpMember, agent: dict[str, Any]
) -> None:
    playground_limited(app, daily_token_budget=100)
    gate = Gate()
    answer_with(app, gate.stream)
    conversation = (await start_conversation(owner, agent["project_id"], agent["id"]))["id"]
    first = asyncio.create_task(asked(owner, agent, conversation))
    await asyncio.wait_for(gate.entered.wait(), 10)

    second = asyncio.create_task(asked(owner, agent, conversation))
    await asyncio.wait([second], timeout=5)
    gate.release.set()

    assert await second == BUSY_PLAYGROUND
    assert await first == "answered"
    assert await asked(owner, agent, conversation) == "answered"


async def test_a_failed_or_unprepared_playground_question_gives_back_its_reservation(
    app: FastAPI, owner: SignedUpMember, agent: dict[str, Any]
) -> None:
    playground_limited(app, daily_token_budget=100)
    conversation = (await start_conversation(owner, agent["project_id"], agent["id"]))["id"]
    error = ModelHTTPError.for_category(
        ModelAuthenticationError, status_code=401, model_name="gpt-4.1-mini"
    )
    answer_with(app, failing(error))
    failed = await ask(owner, agent["project_id"], agent["id"], conversation, "Hi?")
    assert parse_sse(failed.text)[-1][0] == "error"
    missing = await ask(owner, agent["project_id"], agent["id"], str(uuid.uuid4()), "Hi?")
    assert missing.status_code == 404, missing.text

    answer_with(app, three_words)

    assert await asked(owner, agent, conversation) == "answered"


@pytest.mark.parametrize("mid_reply", [True, False], ids=["mid-reply", "before-reading"])
async def test_a_member_who_goes_away_gives_back_the_playgrounds_place_at_once(
    app: FastAPI, owner: SignedUpMember, agent: dict[str, Any], mid_reply: bool
) -> None:
    playground_limited(app, answers_in_flight=1)
    gate = Gate()
    answer_with(app, gate.stream)
    conversation = (await start_conversation(owner, agent["project_id"], agent["id"]))["id"]

    await browser_leaves(
        app,
        owner.client,
        playground_path(owner, agent["project_id"], agent["id"], conversation, "messages"),
        "How much leave?",
        gate=gate if mid_reply else None,
    )
    answer_with(app, three_words)

    assert await asked(owner, agent, conversation) == "answered"
