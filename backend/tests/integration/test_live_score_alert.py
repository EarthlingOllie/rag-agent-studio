"""Task seam and API seam: the Live score drop alert (spec 15). Visitors chat through the widget
API with the Agent's Live sample rate at 100%, so every reply gets a Live Verdict, judged eagerly
by a scripted judge that fails a reply whose question has ``WRONG`` in it and passes the others.
The hourly ``usage_daily`` rollup Beat task, which runs the alerts after the rollup, is called
directly as a task. Editors publish, revert and bulk revert through the API and read the alert on
the Agent; Owners' emails are read from the in-memory outbox the task is given in place of the
real mailer.

Assertions are on HTTP responses and sent emails only."""

from datetime import timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

import app.analytics.tasks as analytics_tasks
from app.mail.outbox import OutboxMailer
from tests.conftest import (
    STUDIO_URL,
    ClientFactory,
    MemberFactory,
    SignedUpMember,
    TenantFactory,
)
from tests.fakes.clock import ControllableClock
from tests.integration.test_agent_revert import reverted
from tests.integration.test_bulk_versions import bulk_reverted
from tests.integration.test_guardrail_analytics import get_agent, listed_agents
from tests.integration.test_judging_guidance import saved
from tests.integration.test_live_score import chat, judged_agent
from tests.integration.test_version_metrics import publish_next, roll_up


@pytest.fixture
async def visitor(new_client: ClientFactory) -> httpx.AsyncClient:
    """A browser on someone's website: no Studio session."""
    return await new_client()


@pytest.fixture
def task_outbox(outbox: OutboxMailer, monkeypatch: pytest.MonkeyPatch) -> OutboxMailer:
    """The rollup task builds its own mailer from the settings; here it sends through the
    app's in-memory outbox, so the test can read what it sent."""
    monkeypatch.setattr(analytics_tasks, "build_mailer", lambda settings: outbox)
    return outbox


async def replies(
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    agent: dict[str, Any],
    passing: int,
    failing: int = 0,
) -> None:
    """``passing`` Visitor replies that pass their Live Verdict and ``failing`` that fail it."""
    await chat(visitor, clock, agent, *["fine"] * passing, *["WRONG"] * failing)


async def alerted(owner: SignedUpMember, agent: dict[str, Any]) -> bool:
    found: bool = (await get_agent(owner, agent))["live_score_drop_alert"]
    return found


def drop_emails(outbox: OutboxMailer, *members: SignedUpMember) -> list[str]:
    """Who the Live score drop alert emailed, of these Members (the test database holds other
    tests' Agents too, which the hourly check also looks at)."""
    to = {member.email for member in members}
    return sorted(e.to for e in outbox.sent if "Live score dropped" in e.subject and e.to in to)


async def next_live(owner: SignedUpMember, agent: dict[str, Any], prompt: str) -> str:
    """Publishes the next Version; its ID."""
    version: dict[str, Any] = await publish_next(owner, agent, prompt)
    return str(version["id"])


async def dropped(
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    app: FastAPI,
) -> dict[str, Any]:
    """An Agent whose v1 passed all of 30 judged replies and whose v2, now Live, passed 20 of 30:
    a clear drop, found by the hourly run. With ``v1`` and ``v2``, the Versions' IDs."""
    agent = await judged_agent(app, owner)
    agent["v1"] = str(agent["v1"]["id"])
    await replies(visitor, clock, agent, 30)
    clock.advance(timedelta(days=1))
    agent["v2"] = await next_live(owner, agent, "Answer briefly.")
    await replies(visitor, clock, agent, 20, 10)
    await roll_up(clock.now())
    return agent


# Raising it


async def test_a_clear_drop_raises_the_alert_and_emails_every_owner_once(
    app: FastAPI,
    owner: SignedUpMember,
    member_factory: MemberFactory,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    task_outbox: OutboxMailer,
) -> None:
    second_owner = await member_factory(owner, "owner")
    editor = await member_factory(owner, "editor")
    agent = await judged_agent(app, owner)
    v1 = str(agent["v1"]["id"])
    await replies(visitor, clock, agent, 30)
    clock.advance(timedelta(days=1))
    v2 = await next_live(owner, agent, "Answer briefly.")
    await replies(visitor, clock, agent, 20, 10)
    before = await alerted(owner, agent)

    await roll_up(clock.now())

    assert before is False
    assert await alerted(owner, agent) is True
    assert await alerted(editor, agent) is True
    (listed,) = await listed_agents(owner, agent)
    assert listed["live_score_drop_alert"] is True
    assert drop_emails(task_outbox, owner, second_owner, editor) == sorted(
        [owner.email, second_owner.email]
    )
    email = next(e for e in task_outbox.sent if e.to == owner.email)
    assert email.subject == f"{agent['name']}'s Live score dropped"
    assert "v2's Live score is 67% (20 of 30 judged replies)" in email.text
    assert "v1's was 100% (30 of 30) over its last 30 days as Live" in email.text
    project = f"{STUDIO_URL}/organisations/{owner.organisation_id}/projects/{agent['project_id']}"
    assert f"{project}/analytics?agent={agent['id']}&a={v1}&b={v2}" in email.text
    assert f"{project}/conversations?agent={agent['id']}&live=failed" in email.text

    # The drop lasts: the alert stays and nobody is emailed again.
    clock.advance(timedelta(hours=1))
    await replies(visitor, clock, agent, 0, 1)
    await roll_up(clock.now())
    assert await alerted(owner, agent) is True
    assert len(drop_emails(task_outbox, owner, second_owner)) == 2


async def test_no_alert_until_the_live_version_has_30_judged_live_verdicts(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    task_outbox: OutboxMailer,
) -> None:
    agent = await judged_agent(app, owner)
    await replies(visitor, clock, agent, 30)
    clock.advance(timedelta(days=1))
    await next_live(owner, agent, "Answer briefly.")
    await replies(visitor, clock, agent, 0, 29)
    await roll_up(clock.now())
    assert await alerted(owner, agent) is False

    await replies(visitor, clock, agent, 0, 1)
    await roll_up(clock.now())
    assert await alerted(owner, agent) is True


async def test_no_alert_without_a_previous_live_version(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    task_outbox: OutboxMailer,
) -> None:
    agent = await judged_agent(app, owner)
    await replies(visitor, clock, agent, 0, 30)

    await roll_up(clock.now())

    assert await alerted(owner, agent) is False
    assert drop_emails(task_outbox, owner) == []


async def test_no_alert_when_the_previous_live_version_has_under_30_judged_live_verdicts(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    task_outbox: OutboxMailer,
) -> None:
    agent = await judged_agent(app, owner)
    await replies(visitor, clock, agent, 29)
    clock.advance(timedelta(days=1))
    await next_live(owner, agent, "Answer briefly.")
    await replies(visitor, clock, agent, 0, 30)

    await roll_up(clock.now())

    assert await alerted(owner, agent) is False


async def test_the_previous_version_counts_over_its_last_30_days_as_live(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    task_outbox: OutboxMailer,
) -> None:
    # v1 failed 30 replies long ago, then passed all of 30 in its last 30 days as Live: only
    # those count, so v2's 80% is a clear drop (counting all of v1's, 50%, it would be a rise).
    agent = await judged_agent(app, owner)
    await replies(visitor, clock, agent, 0, 30)
    clock.advance(timedelta(days=31))
    await replies(visitor, clock, agent, 30)
    clock.advance(timedelta(days=1))
    await next_live(owner, agent, "Answer briefly.")
    await replies(visitor, clock, agent, 24, 6)

    await roll_up(clock.now())

    assert await alerted(owner, agent) is True


async def test_a_significant_drop_of_under_5_points_does_not_alert(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    task_outbox: OutboxMailer,
) -> None:
    # 100% of 75 against 96% of 75: z = 1.75, past the one-sided 95% (1.645), but 4 points.
    agent = await judged_agent(app, owner)
    await replies(visitor, clock, agent, 75)
    clock.advance(timedelta(days=1))
    await next_live(owner, agent, "Answer briefly.")
    await replies(visitor, clock, agent, 72, 3)

    await roll_up(clock.now())

    assert await alerted(owner, agent) is False


# Under the current Judging setup only (spec 19)


async def test_saving_guidance_mid_way_never_raises_the_alert(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    task_outbox: OutboxMailer,
) -> None:
    # v1 passed all of 30 under the Evaluation Model alone; then guidance is saved half way
    # through v2's replies. v2's 20 of 30 under the new Judging setup would be a clear drop
    # against v1's 30 of 30, but v1 has no Live Verdict under it: no alert, however many follow.
    agent = await judged_agent(app, owner)
    await replies(visitor, clock, agent, 30)
    clock.advance(timedelta(days=1))
    await next_live(owner, agent, "Answer briefly.")
    await replies(visitor, clock, agent, 15)
    await saved(owner, "Be strict about grounding.")
    await replies(visitor, clock, agent, 20, 10)

    await roll_up(clock.now())
    clock.advance(timedelta(hours=1))
    await replies(visitor, clock, agent, 0, 30)
    await roll_up(clock.now())

    assert await alerted(owner, agent) is False
    assert drop_emails(task_outbox, owner) == []


async def test_saving_guidance_quiets_a_raised_alert(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    task_outbox: OutboxMailer,
) -> None:
    agent = await dropped(owner, visitor, clock, app)
    assert await alerted(owner, agent) is True

    await saved(owner, "Be strict about grounding.")
    clock.advance(timedelta(hours=1))
    await replies(visitor, clock, agent, 0, 30)
    await roll_up(clock.now())

    # v2's 30 failures are under the new Judging setup, v1's 30 passes under the old one.
    assert await alerted(owner, agent) is False


async def test_only_the_previous_versions_live_verdicts_under_the_current_setup_count(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    task_outbox: OutboxMailer,
) -> None:
    # v1 failed 30 replies before guidance was saved and passed 30 after: only those 30 count,
    # so v2's 80% is a clear drop (counting all of v1's, 50%, it would be a rise).
    agent = await judged_agent(app, owner)
    await replies(visitor, clock, agent, 0, 30)
    await saved(owner, "Be strict about grounding.")
    await replies(visitor, clock, agent, 30)
    clock.advance(timedelta(days=1))
    await next_live(owner, agent, "Answer briefly.")
    await replies(visitor, clock, agent, 24, 6)

    await roll_up(clock.now())

    assert await alerted(owner, agent) is True


async def test_no_alert_when_the_previous_version_has_under_30_under_the_current_setup(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    task_outbox: OutboxMailer,
) -> None:
    agent = await judged_agent(app, owner)
    await replies(visitor, clock, agent, 30)
    await saved(owner, "Be strict about grounding.")
    await replies(visitor, clock, agent, 29)
    clock.advance(timedelta(days=1))
    await next_live(owner, agent, "Answer briefly.")
    await replies(visitor, clock, agent, 0, 30)

    await roll_up(clock.now())

    assert await alerted(owner, agent) is False


# Clearing it


async def test_the_alert_clears_when_the_drop_is_no_longer_clear_and_a_later_drop_alerts_again(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    task_outbox: OutboxMailer,
) -> None:
    # v1: 27 of 30 (90%). v2: 18 of 30 (60%), a clear drop.
    agent = await judged_agent(app, owner)
    await replies(visitor, clock, agent, 27, 3)
    clock.advance(timedelta(days=1))
    await next_live(owner, agent, "Answer briefly.")
    await replies(visitor, clock, agent, 18, 12)
    await roll_up(clock.now())
    assert await alerted(owner, agent) is True

    # v2 recovers to 48 of 60 (80%): 10 points lower, but not clearly (z = 1.2).
    clock.advance(timedelta(hours=1))
    await replies(visitor, clock, agent, 30)
    await roll_up(clock.now())
    assert await alerted(owner, agent) is False
    assert len(drop_emails(task_outbox, owner)) == 1

    # Then drops to 48 of 90 (53%): alerted again, with a new email.
    clock.advance(timedelta(hours=1))
    await replies(visitor, clock, agent, 0, 30)
    await roll_up(clock.now())
    assert await alerted(owner, agent) is True
    assert len(drop_emails(task_outbox, owner)) == 2


async def test_publishing_another_version_clears_the_alert(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    task_outbox: OutboxMailer,
) -> None:
    agent = await dropped(owner, visitor, clock, app)

    await next_live(owner, agent, "Answer with care.")

    assert await alerted(owner, agent) is False
    # v3 has no judged replies yet: the next run doesn't raise it.
    await roll_up(clock.now())
    assert await alerted(owner, agent) is False


async def test_reverting_clears_the_alert(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    task_outbox: OutboxMailer,
) -> None:
    agent = await dropped(owner, visitor, clock, app)

    await reverted(owner, agent["project_id"], agent["id"])

    assert await alerted(owner, agent) is False
    # v1 is Live again; only its replies since count, so its earlier 30 don't.
    await roll_up(clock.now())
    assert await alerted(owner, agent) is False


async def test_a_bulk_operation_clears_the_alert(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    task_outbox: OutboxMailer,
) -> None:
    agent = await dropped(owner, visitor, clock, app)

    await bulk_reverted(owner, agent["project_id"], [agent["id"]])

    assert await alerted(owner, agent) is False


async def test_each_agent_has_its_own_alert(
    app: FastAPI,
    owner: SignedUpMember,
    tenant_factory: TenantFactory,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    task_outbox: OutboxMailer,
) -> None:
    agent = await dropped(owner, visitor, clock, app)
    stranger = await tenant_factory()
    calm = await judged_agent(app, stranger)

    await roll_up(clock.now())

    assert await alerted(owner, agent) is True
    assert await alerted(stranger, calm) is False
    assert drop_emails(task_outbox, stranger) == []
