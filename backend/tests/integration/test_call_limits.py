"""API seam: Call limits (spec 20, ticket 20-07).

An Agent's Maximum Call length and daily Call minutes budget are Operational Settings. Ending a
Call, however it ends, adds its minutes (rounded up, timed by the platform's clock) to the
Agent's counter for the UTC date; once the day's minutes reach the budget, starting a Call is
refused with the Unavailable text, the Agent gets its Budget alert and the Owners are emailed
once. A Conversation has one Call at a time and an IP address at most two at once with one
Agent. A Beat task
ends Calls that reach the Maximum Call length or have had no turn for 60 seconds (which also
closes Calls whose browser vanished), and ending a Conversation ends its Call. The Playground
doesn't count.
"""

import asyncio
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select, text

from app.conversations.models import Call, Conversation
from app.embed.tasks import clear_budget_alerts, end_idle_calls
from app.mail.outbox import OutboxMailer
from app.worker.celery_app import END_IDLE_CALLS_TASK, celery_app
from tests.agents import agents_path
from tests.agents import start_conversation as start_playground
from tests.conftest import BASE_URL, MemberFactory, SignedUpMember, TenantFactory
from tests.fakes.clock import ControllableClock
from tests.integration.test_bedrock_credentials import audit_events
from tests.integration.test_calls import (
    UNAVAILABLE,
    calling_agent,
    end_call,
    secret_of,
    start_call,
    started,
    the_call,
    turn,
)
from tests.integration.test_embed import conversation_token, settings_path
from tests.integration.test_widget_resume import end as end_conversation

CHANGED = "agent.operational_settings_changed"

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
async def visitor(visitor_from: VisitorFactory) -> httpx.AsyncClient:
    return await visitor_from()


@pytest.fixture
async def voice(visitor_from: VisitorFactory) -> httpx.AsyncClient:
    """The voice layer's servers."""
    return await visitor_from("192.0.2.200")


async def limits(owner: SignedUpMember, agent: dict[str, Any], **fields: Any) -> None:
    response = await owner.client.patch(
        settings_path(owner, agent["project_id"], agent["id"]), json=fields
    )
    assert response.status_code == 200, response.text


async def minutes(member: SignedUpMember, agent: dict[str, Any]) -> dict[str, Any]:
    response = await member.client.get(
        agents_path(member, agent["project_id"], agent["id"]) + "/call-minutes"
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def alert(member: SignedUpMember, agent: dict[str, Any]) -> tuple[bool, list[bool]]:
    """The Agent's Call minutes alert on its own page and in the Project's Agent list."""
    one = await member.client.get(agents_path(member, agent["project_id"], agent["id"]))
    listed = await member.client.get(agents_path(member, agent["project_id"]))
    assert one.status_code == listed.status_code == 200
    return one.json()["call_budget_exhausted"], [a["call_budget_exhausted"] for a in listed.json()]


def budget_emails(outbox: OutboxMailer) -> list[tuple[str, str]]:
    return [(e.to, e.subject) for e in outbox.sent if "Call minutes" in e.subject]


async def run_reaper(now: datetime | None = None) -> int:
    """Runs the Beat task that ends idle and over-long Calls, as the worker does; returns how
    many it ended (Calls other tests left open count too)."""
    kwargs = {} if now is None else {"now": now.isoformat()}
    result = await asyncio.to_thread(end_idle_calls.apply, kwargs=kwargs)
    ended: int = result.get()
    return ended


async def run_midnight(now: datetime) -> None:
    await asyncio.to_thread(clear_budget_alerts.apply, kwargs={"now": now.isoformat()})


async def a_call(visitor: httpx.AsyncClient, agent: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """A Conversation token and the Call started in it."""
    token = await conversation_token(visitor, agent["public_id"])
    return token, await started(visitor, agent["public_id"], token)


def refusal(reason: str) -> tuple[int, dict[str, str]]:
    return 503, {"detail": UNAVAILABLE, "reason": reason}


# The two limits are Operational Settings


async def test_a_new_agent_has_a_ten_minute_maximum_and_a_sixty_minute_budget_an_editor_changes(
    app: FastAPI, owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    agent = await calling_agent(app, owner)
    path = settings_path(owner, agent["project_id"], agent["id"])
    before = (await editor.client.get(path)).json()
    assert (before["max_call_minutes"], before["call_minutes_budget"]) == (10, 60)

    response = await editor.client.patch(
        path, json={"max_call_minutes": 5, "call_minutes_budget": 120}
    )

    assert response.status_code == 200, response.text
    assert (response.json()["max_call_minutes"], response.json()["call_minutes_budget"]) == (5, 120)
    event = (await audit_events(owner, CHANGED))[0]
    assert event["before"] == {"max_call_minutes": 10, "call_minutes_budget": 60}
    assert event["after"] == {"max_call_minutes": 5, "call_minutes_budget": 120}


@pytest.mark.parametrize(
    "fields",
    [
        {"max_call_minutes": 0},
        {"max_call_minutes": 61},
        {"max_call_minutes": None},
        {"call_minutes_budget": 0},
        {"call_minutes_budget": 1_000_001},
        {"call_minutes_budget": None},
    ],
)
async def test_a_limit_out_of_range_is_refused(
    app: FastAPI, owner: SignedUpMember, fields: dict[str, Any]
) -> None:
    agent = await calling_agent(app, owner)

    response = await owner.client.patch(
        settings_path(owner, agent["project_id"], agent["id"]), json=fields
    )

    assert response.status_code == 422


# Minutes


async def test_ending_a_call_adds_its_minutes_rounded_up_to_todays_counter(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    agent = await calling_agent(app, owner)
    assert await minutes(owner, agent) == {
        "date": "2026-11-05",
        "minutes_used": 0,
        "call_minutes_budget": 60,
        "exhausted": False,
        "resets_at": "2026-11-06T00:00:00Z",
    }
    token, call = await a_call(visitor, agent)
    clock.advance(timedelta(seconds=61))

    await end_call(visitor, agent["public_id"], token)

    ended = await the_call(app, call["call_id"])
    assert (ended.minutes, ended.end_reason) == (2, "visitor")
    assert (await minutes(owner, agent))["minutes_used"] == 2
    # A second Call adds to the same day's counter.
    second_token, _ = await a_call(visitor, agent)
    clock.advance(timedelta(seconds=30))
    await end_call(visitor, agent["public_id"], second_token)
    assert (await minutes(owner, agent))["minutes_used"] == 3


async def test_the_counter_is_per_agent_and_hidden_from_other_organisations(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    tenant_factory: TenantFactory,
) -> None:
    busy = await calling_agent(app, owner)
    quiet = await calling_agent(app, owner)
    token, _ = await a_call(visitor, busy)
    clock.advance(timedelta(minutes=3))
    await end_call(visitor, busy["public_id"], token)
    stranger = await tenant_factory()

    assert (await minutes(owner, busy))["minutes_used"] == 3
    assert (await minutes(owner, quiet))["minutes_used"] == 0
    response = await stranger.client.get(
        f"/api/organisations/{stranger.organisation_id}/projects/{busy['project_id']}"
        f"/agents/{busy['id']}/call-minutes"
    )
    assert response.status_code == 404


# The Maximum Call length


async def test_the_start_says_how_long_the_call_may_last_and_its_token_lasts_that_long(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    voice: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    agent = await calling_agent(app, owner)
    await limits(owner, agent, max_call_minutes=3)
    _, call = await a_call(visitor, agent)
    secret = await secret_of(app, agent)
    assert call["max_call_minutes"] == 3

    clock.advance(timedelta(minutes=3))
    at_the_limit = await turn(voice, agent["public_id"], secret, call["call_token"], "Hi")
    clock.advance(timedelta(seconds=1))
    past_it = await turn(voice, agent["public_id"], secret, call["call_token"], "Hi")

    assert (at_the_limit.status_code, past_it.status_code) == (200, 403)


async def test_a_call_that_reaches_the_maximum_call_length_is_ended_by_the_platform(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    voice: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    agent = await calling_agent(app, owner)
    await limits(owner, agent, max_call_minutes=2)
    _, call = await a_call(visitor, agent)
    secret = await secret_of(app, agent)
    start = clock.now()
    # The Visitor keeps talking, so the Call is never silent.
    for seconds in (30, 30, 30, 29):
        clock.advance(timedelta(seconds=seconds))
        await turn(voice, agent["public_id"], secret, call["call_token"], "Hi")
    await run_reaper(clock.now())  # 1 s before the limit
    assert (await the_call(app, call["call_id"])).ended_at is None

    clock.advance(timedelta(seconds=20))
    assert await run_reaper(clock.now()) >= 1

    ended = await the_call(app, call["call_id"])
    assert (ended.ended_at, ended.minutes, ended.end_reason) == (
        start + timedelta(minutes=2),
        2,
        "max_length",
    )
    assert (await minutes(owner, agent))["minutes_used"] == 2


async def test_changing_the_maximum_during_a_call_applies_to_the_next_call(
    app: FastAPI,
    owner: SignedUpMember,
    visitor_from: VisitorFactory,
    voice: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    agent = await calling_agent(app, owner)
    secret = await secret_of(app, agent)
    await limits(owner, agent, max_call_minutes=5)
    _, longer = await a_call(await visitor_from("203.0.113.20"), agent)
    await limits(owner, agent, max_call_minutes=2)
    _, shorter = await a_call(await visitor_from("203.0.113.21"), agent)
    await limits(owner, agent, max_call_minutes=10)
    start = clock.now()
    # Both Visitors keep talking, so neither Call is silent.
    for _ in range(10):
        clock.advance(timedelta(seconds=30))
        for call in (longer, shorter):
            await turn(voice, agent["public_id"], secret, call["call_token"], "Hi")
        await run_reaper(clock.now() - timedelta(seconds=1))
    await run_reaper(clock.now())

    cut = await the_call(app, shorter["call_id"])
    whole = await the_call(app, longer["call_id"])
    assert (cut.ended_at, cut.end_reason) == (start + timedelta(minutes=2), "max_length")
    assert (whole.ended_at, whole.end_reason) == (start + timedelta(minutes=5), "max_length")


# Silence


async def test_a_call_with_no_turn_for_60_seconds_is_ended_by_the_beat_task(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    voice: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    schedule = celery_app.conf.beat_schedule["end-idle-calls"]
    assert schedule == {"task": END_IDLE_CALLS_TASK, "schedule": 15.0}
    agent = await calling_agent(app, owner)
    _, talking = await a_call(visitor, agent)
    # A browser that vanished as soon as the Call started: no turn ever comes.
    _, vanished = await a_call(visitor, agent)
    start = clock.now()
    clock.advance(timedelta(seconds=30))
    await turn(voice, agent["public_id"], await secret_of(app, agent), talking["call_token"], "Hi")
    clock.advance(timedelta(seconds=59))  # 59 s since the turn, 89 s since the start

    await run_reaper(clock.now())
    assert (await the_call(app, talking["call_id"])).ended_at is None
    gone = await the_call(app, vanished["call_id"])
    assert (gone.ended_at, gone.minutes, gone.end_reason) == (
        start + timedelta(seconds=60),
        1,
        "silence",
    )

    clock.advance(timedelta(seconds=10))
    await run_reaper(clock.now())
    quiet = await the_call(app, talking["call_id"])
    assert (quiet.ended_at, quiet.minutes) == (start + timedelta(seconds=90), 2)
    assert (await minutes(owner, agent))["minutes_used"] == 3


async def test_the_beat_task_runs_on_the_system_clock(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent = await calling_agent(app, owner)
    _, call = await a_call(visitor, agent)  # started on the test clock, long ago

    assert await run_reaper() >= 1

    assert (await the_call(app, call["call_id"])).end_reason == "silence"


async def test_a_turn_racing_the_end_of_its_call_is_refused(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    voice: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    agent = await calling_agent(app, owner)
    secret = await secret_of(app, agent)
    _, call = await a_call(visitor, agent)
    clock.advance(timedelta(seconds=20))
    async with app.state.sessionmaker() as ender:
        # Another transaction is ending the Call as the turn arrives.
        held = await ender.scalar(
            select(Call).where(Call.id == uuid.UUID(call["call_id"])).with_for_update()
        )
        assert held is not None
        held.ended_at = clock.now()
        await ender.flush()
        racing = asyncio.create_task(
            turn(voice, agent["public_id"], secret, call["call_token"], "Hi")
        )
        await until_a_transaction_waits_on_a_lock(app)
        await ender.commit()
    response = await racing

    assert response.status_code == 403
    assert (await the_call(app, call["call_id"])).last_turn_at is None


async def until_a_transaction_waits_on_a_lock(app: FastAPI) -> None:
    async with app.state.sessionmaker() as watcher:
        for _ in range(500):
            waiting = await watcher.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity"
                    " WHERE datname = current_database() AND wait_event_type = 'Lock'"
                )
            )
            await watcher.rollback()
            if waiting:
                return
            await asyncio.sleep(0.01)
    raise AssertionError("the turn never waited on the Call's lock")


# Ending the Conversation


async def test_ending_a_conversation_ends_its_call(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    agent = await calling_agent(app, owner)
    token, call = await a_call(visitor, agent)
    clock.advance(timedelta(seconds=45))

    await end_conversation(visitor, agent["public_id"], token)

    ended = await the_call(app, call["call_id"])
    assert (ended.ended_at, ended.minutes, ended.end_reason) == (
        clock.now(),
        1,
        "conversation_ended",
    )
    assert (await minutes(owner, agent))["minutes_used"] == 1


async def test_deleting_a_conversation_ends_its_call(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    agent = await calling_agent(app, owner)
    _, call = await a_call(visitor, agent)
    conversation_id = (await the_call(app, call["call_id"])).conversation_id
    clock.advance(timedelta(seconds=10))

    response = await owner.client.delete(
        f"/api/organisations/{owner.organisation_id}/projects/{agent['project_id']}"
        f"/conversations/{conversation_id}"
    )

    assert response.status_code == 204, response.text
    ended = await the_call(app, call["call_id"])
    assert (ended.ended_at, ended.end_reason) == (clock.now(), "conversation_ended")


# One Call per Conversation, two per IP address


async def test_a_conversation_has_one_call_at_a_time(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await calling_agent(app, owner)
    token, _ = await a_call(visitor, agent)

    response = await start_call(visitor, agent["public_id"], token)

    assert (response.status_code, response.json()) == refusal("call_open")
    await end_call(visitor, agent["public_id"], token)
    assert (await start_call(visitor, agent["public_id"], token)).status_code == 201


async def test_an_ip_address_holds_at_most_two_calls_at_once_with_an_agent(
    app: FastAPI, owner: SignedUpMember, visitor_from: VisitorFactory
) -> None:
    agent = await calling_agent(app, owner)
    elsewhere = await calling_agent(app, owner)
    visitor = await visitor_from("203.0.113.10")
    first_token, _ = await a_call(visitor, agent)
    await a_call(visitor, agent)
    token = await conversation_token(visitor, agent["public_id"])

    response = await start_call(visitor, agent["public_id"], token)

    assert (response.status_code, response.json()) == refusal("too_many_calls")
    other = await visitor_from("203.0.113.11")
    assert (await a_call(other, agent))[1]["call_id"]
    assert (await a_call(visitor, elsewhere))[1]["call_id"]
    await end_call(visitor, agent["public_id"], first_token)
    assert (await start_call(visitor, agent["public_id"], token)).status_code == 201


# The Call minutes budget


async def test_once_the_budget_is_spent_calls_are_refused_the_alert_raised_and_owners_emailed_once(
    app: FastAPI,
    owner: SignedUpMember,
    member_factory: MemberFactory,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    outbox: OutboxMailer,
) -> None:
    second_owner = await member_factory(owner, "owner")
    await member_factory(owner, "editor")
    agent = await calling_agent(app, owner)
    await limits(owner, agent, call_minutes_budget=2)
    token, _ = await a_call(visitor, agent)
    clock.advance(timedelta(seconds=100))
    await end_call(visitor, agent["public_id"], token)
    # The day's minutes reached the budget: no alert until a Call is refused.
    assert (await minutes(owner, agent))["exhausted"] is True
    assert await alert(owner, agent) == (False, [False])

    refused = [await start_call(visitor, agent["public_id"], token) for _ in range(2)]

    assert [(r.status_code, r.json()) for r in refused] == [refusal("call_minutes_exhausted")] * 2
    assert await alert(owner, agent) == (True, [True])
    subject = f"{agent['name']} has used its daily Call minutes budget"
    assert sorted(budget_emails(outbox)) == sorted(
        [(owner.email, subject), (second_owner.email, subject)]
    )
    email = next(e for e in outbox.sent if e.to == owner.email and e.subject == subject)
    assert "2 minutes" in email.text
    assert f"/agents/{agent['id']}" in email.text


async def test_the_minutes_of_calls_still_open_count_against_the_budget(
    app: FastAPI,
    owner: SignedUpMember,
    visitor_from: VisitorFactory,
    clock: ControllableClock,
) -> None:
    agent = await calling_agent(app, owner)
    await limits(owner, agent, call_minutes_budget=2)
    await a_call(await visitor_from("203.0.113.30"), agent)
    clock.advance(timedelta(seconds=61))
    # One open minute and a bit: 2 minutes, rounded up, of the budget of 2.
    late = await visitor_from("203.0.113.31")
    token = await conversation_token(late, agent["public_id"])

    response = await start_call(late, agent["public_id"], token)

    assert (response.status_code, response.json()) == refusal("call_minutes_exhausted")


async def test_a_new_utc_date_starts_a_new_counter_and_clears_the_alert(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    outbox: OutboxMailer,
) -> None:
    agent = await calling_agent(app, owner)
    await limits(owner, agent, call_minutes_budget=1)
    token, _ = await a_call(visitor, agent)
    clock.advance(timedelta(seconds=30))
    await end_call(visitor, agent["public_id"], token)
    assert (await start_call(visitor, agent["public_id"], token)).status_code == 503
    assert await alert(owner, agent) == (True, [True])

    await run_midnight(datetime(2026, 11, 5, 23, 59, tzinfo=UTC))
    assert await alert(owner, agent) == (True, [True])
    clock.advance(datetime(2026, 11, 6, 0, 0, tzinfo=UTC) - clock.now())
    await run_midnight(clock.now())

    assert await alert(owner, agent) == (False, [False])
    assert (await minutes(owner, agent))["minutes_used"] == 0
    token = await conversation_token(visitor, agent["public_id"])
    assert (await start_call(visitor, agent["public_id"], token)).status_code == 201
    # The new day can alert again.
    clock.advance(timedelta(seconds=30))
    await end_call(visitor, agent["public_id"], token)
    assert (await start_call(visitor, agent["public_id"], token)).status_code == 503
    assert len(budget_emails(outbox)) == 2


async def test_raising_the_budget_lets_calls_start_again_at_once(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent = await calling_agent(app, owner)
    await limits(owner, agent, call_minutes_budget=1)
    token, _ = await a_call(visitor, agent)
    clock.advance(timedelta(seconds=30))
    await end_call(visitor, agent["public_id"], token)
    assert (await start_call(visitor, agent["public_id"], token)).status_code == 503

    await limits(owner, agent, call_minutes_budget=5)

    assert (await start_call(visitor, agent["public_id"], token)).status_code == 201


# The Playground


async def test_playground_calls_dont_count(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock
) -> None:
    agent = await calling_agent(app, owner)
    conversation = await start_playground(owner, agent["project_id"], agent["id"])
    async with app.state.sessionmaker() as session:
        playground = await session.get_one(Conversation, uuid.UUID(conversation["id"]))
        call = Call(
            organisation_id=playground.organisation_id,
            conversation_id=playground.id,
            agent_version_id=uuid.UUID(agent["version"]["id"]),
            started_at=clock.now(),
            ip="203.0.113.10",
            max_call_minutes=10,
        )
        session.add(call)
        await session.commit()
        call_id = call.id
    clock.advance(timedelta(minutes=5))

    await run_reaper(clock.now())

    assert (await the_call(app, str(call_id))).minutes == 1
    assert (await minutes(owner, agent))["minutes_used"] == 0
