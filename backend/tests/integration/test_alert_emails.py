"""API seam plus task seam: alert emails always arrive (spec 21, ADR-0020). The Token Budget
exhausted, Evaluation budget spent, Block rate alert and Live score drop alert emails reach every
Owner even when the process died between raising the alert and sending it, or a send failed part
way through the Owners.

A kill comes from arming the in-memory outbox's kill switch at the send to an Owner, which stops
the process there without running its error handling; a refused send from telling the outbox to
refuse an address once. Alerts are raised the way they are today (a Visitor spending the Token
Budget, a judgement spending the Evaluation budget, the hourly rollup task), and the sweeper is
called directly as a task, as Beat would call it. Assertions are on HTTP responses and on the
emails in the outbox."""

import asyncio
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

import app.analytics.tasks as analytics_tasks
import app.jobs.tasks as job_tasks
from app.jobs.faults import JobKilled
from app.jobs.tasks import sweep_jobs
from app.mail.outbox import OutboxMailer
from tests.conftest import ClientFactory, MemberFactory, SignedUpMember
from tests.fakes.clock import ControllableClock
from tests.fakes.jobs import RecordingJobPublisher
from tests.integration.test_embed import conversation_token
from tests.integration.test_evaluation_budget import dear as dear
from tests.integration.test_evaluation_budget import emails_about_the_budget, sampled_agent
from tests.integration.test_evaluation_cost import price_table as price_table
from tests.integration.test_guardrail_analytics import (
    BENIGN,
    SPIKE_SUBJECT,
    ask_all,
    baseline,
    get_agent,
    guarded_agent,
    spike_emails,
)
from tests.integration.test_input_guardrail import ATTACK
from tests.integration.test_live_score_alert import drop_emails, dropped
from tests.integration.test_live_verdicts import reply
from tests.integration.test_token_budget import agent as agent
from tests.integration.test_token_budget import alert, budget, budget_emails, outcome
from tests.integration.test_version_metrics import roll_up
from tests.jobs import settle_jobs_in_flight

TOKEN_BUDGET_SUBJECT = "HR helper has used its daily Token Budget"


@pytest.fixture
async def visitor(new_client: ClientFactory) -> httpx.AsyncClient:
    """A browser on someone's website: no Studio session."""
    return await new_client()


@pytest.fixture
def task_outbox(outbox: OutboxMailer, monkeypatch: pytest.MonkeyPatch) -> OutboxMailer:
    """The rollup task and the sweeper build their own mailer from the settings; here they send
    through the app's in-memory outbox, so the test can read what they sent."""
    monkeypatch.setattr(analytics_tasks, "build_mailer", lambda settings: outbox)
    monkeypatch.setattr(job_tasks, "build_mailer", lambda settings: outbox)
    return outbox


@pytest.fixture(autouse=True)
async def no_alert_emails_left_by_earlier_tests(app: FastAPI) -> None:
    """The test database is shared by the tests a worker runs, one after another, so an earlier
    test may have left an alert email unsent (a kill, a refused send). The sweeper would send
    those too, so each test here starts with them settled: every sweep then sends only the
    test's own."""
    await settle_jobs_in_flight(app)


async def sweep(clock: ControllableClock) -> None:
    """Runs the sweeper task as Beat would, as of the controllable clock's time (in a thread: the
    task runs its own event loop)."""
    result = await asyncio.to_thread(sweep_jobs.apply, kwargs={"at": clock.now().isoformat()})
    result.get(disable_sync_subtasks=False)


def emails_to(outbox: OutboxMailer, subject: str) -> Callable[..., list[str]]:
    """Who has been sent the email with this subject, of the given Members, in sorted order."""

    def to(*members: SignedUpMember) -> list[str]:
        wanted = {member.email for member in members}
        return sorted(e.to for e in outbox.sent if e.subject == subject and e.to in wanted)

    return to


async def spiking(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> dict[str, Any]:
    """A guarded Agent with a calm week behind it, rolled up, then an attack in the hour (6 of 8
    messages blocked) that the next rollup finds."""
    agent = await guarded_agent(app, owner)
    await baseline(visitor, clock, agent)
    await roll_up(clock.now())
    await ask_all(visitor, clock, agent, *[ATTACK] * 3, BENIGN)
    await ask_all(visitor, clock, agent, *[ATTACK] * 3, BENIGN)
    return agent


async def test_a_kill_between_raising_the_block_rate_alert_and_emailing_is_sent_by_the_next_sweep(
    app: FastAPI,
    owner: SignedUpMember,
    member_factory: MemberFactory,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    task_outbox: OutboxMailer,
) -> None:
    second_owner = await member_factory(owner, "owner")
    editor = await member_factory(owner, "editor")
    agent = await spiking(app, owner, visitor, clock)
    first, *_ = sorted([owner.email, second_owner.email])
    task_outbox.kill_switch.arm(f"send to {first}")

    # The rollup raises the alert, then dies before any Owner is emailed.
    with pytest.raises(JobKilled):
        await roll_up(clock.now())

    assert (await get_agent(owner, agent))["block_rate_alert"] is True
    assert spike_emails(task_outbox, owner, second_owner, editor) == []

    await sweep(clock)

    assert sorted(spike_emails(task_outbox, owner, second_owner, editor)) == sorted(
        [(owner.email, SPIKE_SUBJECT), (second_owner.email, SPIKE_SUBJECT)]
    )
    email = next(e for e in task_outbox.sent if e.to == owner.email)
    assert "6 of the last hour's 8 Visitor messages (75%)" in email.text

    # Each Owner is emailed once: later sweeps and rollups send nothing more.
    clock.advance(timedelta(minutes=1))
    await sweep(clock)
    await roll_up(clock.now())
    await sweep(clock)
    assert len(spike_emails(task_outbox, owner, second_owner, editor)) == 2


async def test_a_refused_send_is_completed_for_the_rest_of_the_owners_by_the_sweep(
    app: FastAPI,
    owner: SignedUpMember,
    member_factory: MemberFactory,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    task_outbox: OutboxMailer,
) -> None:
    second_owner = await member_factory(owner, "owner")
    agent = await spiking(app, owner, visitor, clock)
    task_outbox.refuse(owner.email)

    # The rollup finishes: the Owner the mail server refused is left for the sweeper.
    await roll_up(clock.now())

    assert (await get_agent(owner, agent))["block_rate_alert"] is True
    assert spike_emails(task_outbox, owner, second_owner) == [(second_owner.email, SPIKE_SUBJECT)]

    await sweep(clock)

    assert sorted(spike_emails(task_outbox, owner, second_owner)) == sorted(
        [(owner.email, SPIKE_SUBJECT), (second_owner.email, SPIKE_SUBJECT)]
    )
    await sweep(clock)
    assert len(spike_emails(task_outbox, owner, second_owner)) == 2


async def test_a_live_score_drop_email_killed_part_way_through_the_owners_is_completed(
    app: FastAPI,
    owner: SignedUpMember,
    member_factory: MemberFactory,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    task_outbox: OutboxMailer,
) -> None:
    second_owner = await member_factory(owner, "owner")
    first, then = sorted([owner.email, second_owner.email])
    task_outbox.kill_switch.arm(f"send to {then}")

    # The rollup raises the alert, emails the first Owner and dies before the second.
    with pytest.raises(JobKilled):
        await dropped(owner, visitor, clock, app)

    assert drop_emails(task_outbox, owner, second_owner) == [first]

    await sweep(clock)

    assert drop_emails(task_outbox, owner, second_owner) == sorted([first, then])
    await sweep(clock)
    assert drop_emails(task_outbox, owner, second_owner) == sorted([first, then])


async def test_a_kill_between_raising_the_token_budget_alert_and_emailing_is_sent_by_the_sweep(
    owner: SignedUpMember,
    member_factory: MemberFactory,
    agent: dict[str, Any],
    visitor: httpx.AsyncClient,
    outbox: OutboxMailer,
    task_outbox: OutboxMailer,
    clock: ControllableClock,
) -> None:
    second_owner = await member_factory(owner, "owner")
    sent = emails_to(outbox, TOKEN_BUDGET_SUBJECT)
    token = await conversation_token(visitor, agent["public_id"])
    assert await outcome(visitor, agent, token) == "answered"
    await budget(owner, agent, 50)
    first, *_ = sorted([owner.email, second_owner.email])
    outbox.kill_switch.arm(f"send to {first}")

    # The API process raises the alert on the first refusal, then dies before emailing.
    with pytest.raises(JobKilled):
        await outcome(visitor, agent, token)

    assert await alert(owner, agent) == (True, [True])
    assert sent(owner, second_owner) == []

    await sweep(clock)

    assert sent(owner, second_owner) == sorted([owner.email, second_owner.email])
    # Raised once for the day: later refusals and sweeps send nothing more.
    assert await outcome(visitor, agent, token) == "refused"
    await sweep(clock)
    assert len(budget_emails(outbox)) == 2


@pytest.mark.usefixtures("dear")
async def test_a_kill_between_spending_the_evaluation_budget_and_emailing_is_sent_by_the_sweep(
    app: FastAPI,
    owner: SignedUpMember,
    member_factory: MemberFactory,
    new_client: ClientFactory,
    task_outbox: OutboxMailer,
    clock: ControllableClock,
    jobs: RecordingJobPublisher,
) -> None:
    second_owner = await member_factory(owner, "owner")
    agent = await sampled_agent(app, owner, "0.01")
    first, *_ = sorted([owner.email, second_owner.email])
    task_outbox.kill_switch.arm(f"send to {first}")

    # The judgement takes the spend past the budget, commits, and dies before emailing.
    await reply(await new_client(), agent)

    assert [job.task for job in jobs.killed] == ["evaluation.live_verdict"]
    assert emails_about_the_budget(task_outbox) == []

    await sweep(clock)

    assert sorted(emails_about_the_budget(task_outbox)) == sorted([owner.email, second_owner.email])
    await sweep(clock)
    assert len(emails_about_the_budget(task_outbox)) == 2
