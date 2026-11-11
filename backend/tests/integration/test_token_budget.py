"""API seam: the Token Budget. Each Agent has a daily Token Budget (an Operational Setting). Every
Visitor reply adds the tokens it actually used to the Agent's counter for that UTC date, kept in
Redis. Once the day's usage reaches the budget, admission control refuses Visitor messages with
an ``unavailable`` event carrying the Agent's unavailable text, the Agent carries an alert flag
(the Studio's badge) and every Owner gets one email for that day. The next UTC date starts a new
counter, and a Beat task clears the alert flags at midnight UTC. The Playground is exempt."""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from celery.schedules import crontab
from fastapi import FastAPI
from pydantic_ai.exceptions import ModelAuthenticationError, ModelHTTPError
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo

from app.embed.tasks import clear_budget_alerts
from app.mail.outbox import OutboxMailer
from app.worker.celery_app import CLEAR_BUDGET_ALERTS_TASK, celery_app
from tests.agents import agents_path, answer_with, ask, create_agent, parse_sse
from tests.agents import start_conversation as start_playground
from tests.conftest import STUDIO_URL, ClientFactory, MemberFactory, SignedUpMember, TenantFactory
from tests.fakes.clock import ControllableClock
from tests.integration.test_agent_versions import knowledgeable_project, published
from tests.integration.test_bedrock_credentials import audit_events
from tests.integration.test_embed import conversation_token, send, settings_path
from tests.integration.test_playground_errors import failing
from tests.integration.test_rate_limits import message_count

DEFAULT_UNAVAILABLE = "This assistant is temporarily unavailable. Please try again later."
EXHAUSTED = ("unavailable", {"reason": "budget_exhausted", "message": DEFAULT_UNAVAILABLE})
CHANGED = "agent.operational_settings_changed"
# The fake model counts 50 tokens of prompt overhead and one token per word it streams, so each
# answer of ``three_words`` uses 53 tokens.
PER_ANSWER = 53


async def three_words(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
    yield "Twenty five days"


@pytest.fixture
async def visitor(new_client: ClientFactory) -> httpx.AsyncClient:
    """A browser on someone's website: no Studio session."""
    return await new_client()


@pytest.fixture
async def agent(app: FastAPI, owner: SignedUpMember) -> dict[str, Any]:
    """A live Agent over a Project holding the leave policy, so questions reach the model."""
    project_id = await knowledgeable_project(app, owner)
    answer_with(app, three_words)
    created: dict[str, Any] = await create_agent(owner, project_id)
    await published(owner, project_id, created["id"])
    return created


async def budget(owner: SignedUpMember, agent: dict[str, Any], tokens: int) -> None:
    response = await owner.client.patch(
        settings_path(owner, agent["project_id"], agent["id"]), json={"daily_token_budget": tokens}
    )
    assert response.status_code == 200, response.text


def usage_path(member: SignedUpMember, agent: dict[str, Any]) -> str:
    return agents_path(member, agent["project_id"], agent["id"]) + "/token-usage"


async def usage(member: SignedUpMember, agent: dict[str, Any]) -> dict[str, Any]:
    response = await member.client.get(usage_path(member, agent))
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def outcome(visitor: httpx.AsyncClient, agent: dict[str, Any], token: str) -> str:
    """``answered`` or ``refused`` for one Visitor message, checking the refusal's event."""
    response = await send(visitor, agent["public_id"], token, "How much leave?")
    assert response.status_code == 200, response.text
    events = parse_sse(response.text)
    if events[-1][0] == "done":
        return "answered"
    assert events == [EXHAUSTED]
    return "refused"


async def alert(member: SignedUpMember, agent: dict[str, Any]) -> tuple[bool, list[bool]]:
    """The Agent's alert flag on its own page and in the Project's Agent list."""
    one = await member.client.get(agents_path(member, agent["project_id"], agent["id"]))
    listed = await member.client.get(agents_path(member, agent["project_id"]))
    assert one.status_code == listed.status_code == 200
    return one.json()["budget_exhausted"], [a["budget_exhausted"] for a in listed.json()]


def budget_emails(outbox: OutboxMailer) -> list[tuple[str, str]]:
    return [(e.to, e.subject) for e in outbox.sent if "Token Budget" in e.subject]


async def run_beat_task(now: datetime | None = None) -> None:
    """Runs the Beat task as the worker does (eagerly in tests), from a thread with its own
    event loop."""
    kwargs = {} if now is None else {"now": now.isoformat()}
    await asyncio.to_thread(clear_budget_alerts.apply, kwargs=kwargs)


# The budget is an Operational Setting


async def test_a_new_agent_has_a_daily_token_budget_an_editor_changes_with_an_audit_event(
    owner: SignedUpMember, member_factory: MemberFactory, agent: dict[str, Any]
) -> None:
    editor = await member_factory(owner, "editor")
    path = settings_path(editor, agent["project_id"], agent["id"])
    assert (await editor.client.get(path)).json()["daily_token_budget"] == 1_000_000

    response = await editor.client.patch(path, json={"daily_token_budget": 5000})

    assert response.status_code == 200, response.text
    assert response.json()["daily_token_budget"] == 5000
    assert (await editor.client.get(path)).json()["daily_token_budget"] == 5000
    events = await audit_events(owner, CHANGED)
    assert [(e["actor"]["id"], e["before"], e["after"]) for e in events] == [
        (editor.member_id, {"daily_token_budget": 1_000_000}, {"daily_token_budget": 5000})
    ]


@pytest.mark.parametrize("tokens", [0, -5, 1_000_000_001, None, "plenty"])
async def test_a_budget_out_of_range_is_refused(
    owner: SignedUpMember, agent: dict[str, Any], tokens: Any
) -> None:
    path = settings_path(owner, agent["project_id"], agent["id"])

    response = await owner.client.patch(path, json={"daily_token_budget": tokens})

    assert response.status_code == 422, response.text
    assert (await owner.client.get(path)).json()["daily_token_budget"] == 1_000_000
    assert await audit_events(owner, CHANGED) == []


# The daily counter


async def test_each_reply_adds_the_tokens_it_used_to_todays_counter(
    owner: SignedUpMember,
    member_factory: MemberFactory,
    agent: dict[str, Any],
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    editor = await member_factory(owner, "editor")
    assert await usage(editor, agent) == {
        "date": "2026-11-05",
        "tokens_used": 0,
        "daily_token_budget": 1_000_000,
        "exhausted": False,
        "resets_at": "2026-11-06T00:00:00Z",
    }
    token = await conversation_token(visitor, agent["public_id"])

    assert await outcome(visitor, agent, token) == "answered"
    assert (await usage(editor, agent))["tokens_used"] == PER_ANSWER
    other = await conversation_token(visitor, agent["public_id"])
    assert await outcome(visitor, agent, other) == "answered"

    # Every Conversation of the Agent counts against the same budget.
    assert (await usage(editor, agent))["tokens_used"] == 2 * PER_ANSWER


async def test_the_counter_is_per_agent(
    app: FastAPI, owner: SignedUpMember, agent: dict[str, Any], visitor: httpx.AsyncClient
) -> None:
    other = await create_agent(owner, agent["project_id"], "Another helper")
    await published(owner, agent["project_id"], other["id"])

    token = await conversation_token(visitor, agent["public_id"])
    assert await outcome(visitor, agent, token) == "answered"

    assert (await usage(owner, agent))["tokens_used"] == PER_ANSWER
    assert (await usage(owner, other))["tokens_used"] == 0


async def test_a_provider_failure_uses_none_of_the_budget(
    app: FastAPI, owner: SignedUpMember, agent: dict[str, Any], visitor: httpx.AsyncClient
) -> None:
    error = ModelHTTPError.for_category(
        ModelAuthenticationError, status_code=401, model_name="gpt-4.1-mini"
    )
    answer_with(app, failing(error))
    token = await conversation_token(visitor, agent["public_id"])

    response = await send(visitor, agent["public_id"], token, "How much leave?")

    assert parse_sse(response.text)[-1][0] == "error"
    assert (await usage(owner, agent))["tokens_used"] == 0


async def test_another_agents_usage_is_not_visible(
    owner: SignedUpMember, tenant_factory: TenantFactory, agent: dict[str, Any]
) -> None:
    stranger = await tenant_factory()

    response = await stranger.client.get(
        f"/api/organisations/{stranger.organisation_id}/projects/{agent['project_id']}"
        f"/agents/{agent['id']}/token-usage"
    )

    assert response.status_code == 404, response.text


# Exhaustion


async def test_an_exhausted_budget_refuses_visitors_raises_the_alert_and_emails_owners_once(
    app: FastAPI,
    owner: SignedUpMember,
    member_factory: MemberFactory,
    agent: dict[str, Any],
    visitor: httpx.AsyncClient,
    outbox: OutboxMailer,
    clock: ControllableClock,
) -> None:
    second_owner = await member_factory(owner, "owner")
    editor = await member_factory(owner, "editor")
    await budget(owner, agent, 100)
    token = await conversation_token(visitor, agent["public_id"])
    assert await outcome(visitor, agent, token) == "answered"  # 53 of 100
    assert await alert(owner, agent) == (False, [False])
    assert budget_emails(outbox) == []

    # This reply takes the day's usage to 106: the budget is spent.
    assert await outcome(visitor, agent, token) == "answered"

    assert await usage(editor, agent) == {
        "date": "2026-11-05",
        "tokens_used": 2 * PER_ANSWER,
        "daily_token_budget": 100,
        "exhausted": True,
        "resets_at": "2026-11-06T00:00:00Z",
    }
    assert await alert(editor, agent) == (True, [True])
    subject = "HR helper has used its daily Token Budget"
    assert sorted(budget_emails(outbox)) == sorted(
        [(owner.email, subject), (second_owner.email, subject)]
    )
    email = next(e for e in outbox.sent if e.to == owner.email and e.subject == subject)
    assert "100 tokens" in email.text
    assert "midnight UTC" in email.text
    assert (
        f"{STUDIO_URL}/organisations/{owner.organisation_id}/projects/{agent['project_id']}"
        f"/agents/{agent['id']}"
    ) in email.text

    # Every Visitor is refused now, and their question isn't saved.
    saved = await message_count(app, agent)
    assert await outcome(visitor, agent, token) == "refused"
    other = await conversation_token(visitor, agent["public_id"])
    assert await outcome(visitor, agent, other) == "refused"
    clock.advance(timedelta(hours=3))
    assert await outcome(visitor, agent, other) == "refused"
    assert await message_count(app, agent) == saved
    # Refusals use no tokens, and the Owners still have just one email each.
    assert (await usage(owner, agent))["tokens_used"] == 2 * PER_ANSWER
    assert len(budget_emails(outbox)) == 2


async def test_a_refusal_carries_the_agents_own_unavailable_text(
    owner: SignedUpMember, agent: dict[str, Any], visitor: httpx.AsyncClient
) -> None:
    path = settings_path(owner, agent["project_id"], agent["id"])
    await owner.client.patch(path, json={"daily_token_budget": 1, "unavailable_text": "Back soon."})
    token = await conversation_token(visitor, agent["public_id"])
    assert await outcome(visitor, agent, token) == "answered"

    response = await send(visitor, agent["public_id"], token, "And sick leave?")

    assert parse_sse(response.text) == [
        ("unavailable", {"reason": "budget_exhausted", "message": "Back soon."})
    ]


async def test_lowering_the_budget_below_todays_usage_refuses_at_once_and_alerts_once(
    owner: SignedUpMember, agent: dict[str, Any], visitor: httpx.AsyncClient, outbox: OutboxMailer
) -> None:
    token = await conversation_token(visitor, agent["public_id"])
    assert await outcome(visitor, agent, token) == "answered"
    assert await alert(owner, agent) == (False, [False])

    await budget(owner, agent, 50)

    # Nobody has been refused yet; the first refusal raises the alert and emails the Owner.
    assert await alert(owner, agent) == (False, [False])
    assert await outcome(visitor, agent, token) == "refused"
    assert await alert(owner, agent) == (True, [True])
    assert await outcome(visitor, agent, token) == "refused"
    assert budget_emails(outbox) == [(owner.email, "HR helper has used its daily Token Budget")]


async def test_raising_the_budget_makes_the_agent_available_again_at_once(
    owner: SignedUpMember, agent: dict[str, Any], visitor: httpx.AsyncClient
) -> None:
    await budget(owner, agent, 10)
    token = await conversation_token(visitor, agent["public_id"])
    assert await outcome(visitor, agent, token) == "answered"
    assert await outcome(visitor, agent, token) == "refused"

    await budget(owner, agent, 1000)

    assert await outcome(visitor, agent, token) == "answered"
    assert (await usage(owner, agent))["exhausted"] is False


# Midnight UTC


async def test_the_budget_resets_at_midnight_utc_and_a_new_day_can_alert_again(
    owner: SignedUpMember,
    agent: dict[str, Any],
    visitor: httpx.AsyncClient,
    outbox: OutboxMailer,
    clock: ControllableClock,
) -> None:
    await budget(owner, agent, 50)
    token = await conversation_token(visitor, agent["public_id"])
    assert await outcome(visitor, agent, token) == "answered"
    clock.advance(timedelta(hours=14, minutes=59, seconds=59))  # 23:59:59 UTC
    assert await outcome(visitor, agent, token) == "refused"

    clock.advance(1)  # 00:00:00 UTC on 6 November: a new counter

    assert (await usage(owner, agent))["tokens_used"] == 0
    assert (await usage(owner, agent))["date"] == "2026-11-06"
    assert await outcome(visitor, agent, token) == "answered"
    assert (await usage(owner, agent))["tokens_used"] == PER_ANSWER
    # The new day's budget is spent too: a second email, for the second day.
    assert await outcome(visitor, agent, token) == "refused"
    assert len(budget_emails(outbox)) == 2


async def test_the_beat_task_clears_the_alert_flags_at_midnight_utc(
    owner: SignedUpMember,
    agent: dict[str, Any],
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    schedule = celery_app.conf.beat_schedule["clear-token-budget-alerts"]
    assert schedule["task"] == CLEAR_BUDGET_ALERTS_TASK
    assert schedule["schedule"] == crontab(minute="0", hour="0")
    assert str(celery_app.conf.timezone) == "UTC"
    await budget(owner, agent, 1)
    token = await conversation_token(visitor, agent["public_id"])
    assert await outcome(visitor, agent, token) == "answered"  # exhausted at 09:00 on 5 Nov
    assert await alert(owner, agent) == (True, [True])

    # Late the same day, an alert raised that day stays.
    await run_beat_task(datetime(2026, 11, 5, 23, 59, tzinfo=UTC))
    assert await alert(owner, agent) == (True, [True])

    await run_beat_task(datetime(2026, 11, 6, 0, 0, tzinfo=UTC))

    assert await alert(owner, agent) == (False, [False])


async def test_the_beat_task_runs_on_the_system_clock(
    owner: SignedUpMember,
    agent: dict[str, Any],
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    await budget(owner, agent, 1)
    token = await conversation_token(visitor, agent["public_id"])
    assert await outcome(visitor, agent, token) == "answered"  # on the test clock, in the past

    await run_beat_task()

    assert await alert(owner, agent) == (False, [False])


# The Playground


async def test_the_playground_is_exempt(
    owner: SignedUpMember, agent: dict[str, Any], visitor: httpx.AsyncClient, outbox: OutboxMailer
) -> None:
    await budget(owner, agent, 1)
    conversation = await start_playground(owner, agent["project_id"], agent["id"])

    # The Playground uses none of the budget...
    for _ in range(3):
        response = await ask(
            owner, agent["project_id"], agent["id"], conversation["id"], "How much leave?"
        )
        assert parse_sse(response.text)[-1][0] == "done"
    assert (await usage(owner, agent))["tokens_used"] == 0
    assert await alert(owner, agent) == (False, [False])
    token = await conversation_token(visitor, agent["public_id"])
    assert await outcome(visitor, agent, token) == "answered"
    assert await outcome(visitor, agent, token) == "refused"

    # ...and still answers once Visitors are refused.
    response = await ask(
        owner, agent["project_id"], agent["id"], conversation["id"], "And sick leave?"
    )
    assert parse_sse(response.text)[-1][0] == "done"
    assert (await usage(owner, agent))["tokens_used"] == PER_ANSWER
