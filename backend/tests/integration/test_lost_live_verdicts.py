"""API seam plus task seam for Live Verdicts whose judging job was lost or whose worker died
(spec 21, ticket 21-07, ADR-0020).

A sampled reply whose job never reached the queue, or whose worker died while it was judged, is
sent again by the sweeper once it has been Pending longer than its threshold, once at most; a
Live Verdict still Pending after that is an Error, which the Live score leaves out. A re-sent
job whose first copy is somehow still running stores one judgement and records its spend once.

A lost message comes from the Job publisher fake; a worker that dies while the judge is asked is
a judge that raises ``JobKilled``, which skips the job's error handling as a kill would. The
sweeper is called directly as a task with the controllable clock moved past the threshold.
Judge calls are counted on the scripted chat model; outcomes and spend are read through the API.
"""

import asyncio
import threading
from datetime import timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo
from sqlalchemy import update

from app.core.settings import load_settings
from app.evaluation.fake_judge import fake_judgement
from app.evaluation.models import LiveVerdict
from app.jobs.faults import JobKilled
from tests.conftest import ClientFactory, SignedUpMember
from tests.fakes.clock import ControllableClock
from tests.fakes.jobs import RecordingJobPublisher
from tests.integration.test_conversations import conversations_path, listed
from tests.integration.test_evaluation_budget import budget, judged_cost
from tests.integration.test_interrupted_ingestion import app as app
from tests.integration.test_interrupted_ingestion import exporter as exporter
from tests.integration.test_interrupted_ingestion import recovered, sweep
from tests.integration.test_live_score import DAY, live_score
from tests.integration.test_live_verdicts import (
    live_agent,
    live_verdict,
    message_id,
    reply,
    sampling,
    scripted,
)
from tests.jobs import settle_jobs_in_flight

JUDGE = "evaluation.live_verdict"
LOST = (
    "Judging was lost and sent again without finishing; this reply is left out of the Live score."
)
THRESHOLD = timedelta(minutes=5)


@pytest.fixture(autouse=True)
async def no_jobs_left_by_earlier_tests(app: FastAPI) -> None:
    """Earlier tests on this database may have left Live Verdicts Pending; each test here
    starts with them settled, so every sweep sees only the test's own rows."""
    await settle_jobs_in_flight(app)


@pytest.fixture
async def visitor(new_client: ClientFactory) -> httpx.AsyncClient:
    """A browser on someone's website: no Studio session."""
    return await new_client()


class Judge:
    """The fake chat model's judge, counting its calls. Told to, it kills the worker on its next
    call, or holds its next call until released (the first copy of a job still running)."""

    def __init__(self) -> None:
        self.calls = 0
        self.kill_next = False
        self.hold_next = False
        self.holding = threading.Event()
        self.release = threading.Event()

    def __call__(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        self.calls += 1
        if self.kill_next:
            self.kill_next = False
            raise JobKilled("judge")
        if self.hold_next:
            self.hold_next = False
            self.holding.set()
            assert self.release.wait(timeout=30)
        return fake_judgement(messages, info)


@pytest.fixture
async def judge(app: FastAPI) -> Judge:
    counting = Judge()
    scripted(app, judgement=counting)
    return counting


async def sampled(app: FastAPI, owner: SignedUpMember) -> dict[str, Any]:
    agent = await live_agent(app, owner)
    agent["v1"] = agent["version"]
    await sampling(owner, agent, 100)
    return agent


async def status_of(
    owner: SignedUpMember, agent: dict[str, Any], events: list[tuple[str, Any]]
) -> str:
    verdict = await live_verdict(owner, agent, events)
    assert verdict is not None
    status: str = verdict["status"]
    return status


async def spent(owner: SignedUpMember) -> Decimal:
    return Decimal((await budget(owner))["spent_usd"])


def verdict_id_of(jobs: RecordingJobPublisher) -> str:
    (job,) = {job.identifier for job in jobs.sent if job.task == JUDGE}
    return job


# A lost job is sent again once


async def test_a_live_verdict_whose_job_never_reached_the_queue_is_judged_after_its_threshold(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    jobs: RecordingJobPublisher,
    judge: Judge,
    exporter: InMemorySpanExporter,
) -> None:
    agent = await sampled(app, owner)
    jobs.lose_next()
    events = await reply(visitor, agent)
    assert await status_of(owner, agent, events) == "pending"

    clock.advance(THRESHOLD - timedelta(seconds=1))
    assert await sweep(clock) == 0
    clock.advance(timedelta(seconds=1))
    assert await sweep(clock) == 1

    assert await status_of(owner, agent, events) == "judged"
    assert judge.calls == 1
    assert jobs.tasks().count(JUDGE) == 2
    assert recovered(exporter) == [(JUDGE, verdict_id_of(jobs), "pending too long")]
    assert (await live_score(owner, agent, **DAY))["n"] == 1


async def test_a_live_verdict_whose_worker_died_while_it_was_judged_is_judged_once_more(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    jobs: RecordingJobPublisher,
    judge: Judge,
) -> None:
    agent = await sampled(app, owner)
    judge.kill_next = True
    events = await reply(visitor, agent)
    assert len(jobs.killed) == 1
    assert await status_of(owner, agent, events) == "pending"

    clock.advance(THRESHOLD)
    assert await sweep(clock) == 1

    assert await status_of(owner, agent, events) == "judged"
    # The killed call was paid for and not recorded; the one more try is recorded once.
    assert judge.calls == 2
    cost = await judged_cost(owner, agent, message_id(events))
    assert await spent(owner) == cost > 0


async def test_a_live_verdict_still_pending_after_its_resend_is_an_error_left_out_of_the_score(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    jobs: RecordingJobPublisher,
    judge: Judge,
) -> None:
    agent = await sampled(app, owner)
    jobs.lose_next()
    events = await reply(visitor, agent)
    clock.advance(THRESHOLD)
    jobs.lose_next()
    assert await sweep(clock) == 1
    assert await status_of(owner, agent, events) == "pending"

    # The threshold restarts with the resend.
    clock.advance(THRESHOLD - timedelta(seconds=1))
    assert await sweep(clock) == 0
    clock.advance(timedelta(seconds=1))
    assert await sweep(clock) == 1

    verdict = await live_verdict(owner, agent, events)
    assert verdict is not None
    assert (verdict["status"], verdict["error_reason"]) == ("error", LOST)
    assert judge.calls == 0
    assert (await live_score(owner, agent, **DAY))["n"] == 0
    # Nothing is tried again after that.
    clock.advance(THRESHOLD * 3)
    assert await sweep(clock) == 0
    assert judge.calls == 0


# Judged once


async def test_a_resent_live_verdict_whose_first_job_is_still_running_is_judged_and_charged_once(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    jobs: RecordingJobPublisher,
    judge: Judge,
) -> None:
    agent = await sampled(app, owner)
    jobs.hold_next()
    events = await reply(visitor, agent)
    judge.hold_next = True
    first = asyncio.create_task(jobs.release_held())
    assert await asyncio.to_thread(judge.holding.wait, 30)

    # The first copy is somehow still asking the judge when the sweeper gives up on it.
    clock.advance(THRESHOLD)
    assert await sweep(clock) == 1
    resent = await live_verdict(owner, agent, events)
    assert resent is not None
    assert resent["status"] == "judged"
    once = await spent(owner)
    judge.release.set()
    await first

    assert await live_verdict(owner, agent, events) == resent
    assert await spent(owner) == once == Decimal(resent["cost_usd"]) > 0


async def test_a_resent_live_verdict_the_first_job_finished_meanwhile_is_not_judged_again(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    jobs: RecordingJobPublisher,
    judge: Judge,
) -> None:
    agent = await sampled(app, owner)
    jobs.hold_next()
    events = await reply(visitor, agent)
    clock.advance(THRESHOLD)
    jobs.hold_next()
    assert await sweep(clock) == 1

    # The first message arrives after the sweep, then the resend.
    await jobs.release_held()

    assert await status_of(owner, agent, events) == "judged"
    assert judge.calls == 1
    assert await spent(owner) == await judged_cost(owner, agent, message_id(events))


# Purged before the resend


async def test_a_live_verdict_whose_reply_was_purged_before_the_resend_is_skipped(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    jobs: RecordingJobPublisher,
    judge: Judge,
) -> None:
    agent = await sampled(app, owner)
    jobs.lose_next()
    events = await reply(visitor, agent)
    (row,) = (await listed(owner, agent["project_id"]))["items"]
    deleted = await owner.client.delete(conversations_path(owner, agent["project_id"], row["id"]))
    assert deleted.status_code == 204, deleted.text

    clock.advance(THRESHOLD)
    assert await sweep(clock) == 1

    assert await status_of(owner, agent, events) == "skipped"
    assert judge.calls == 0


# Stuck before this shipped


async def test_live_verdicts_stuck_on_pending_before_this_shipped_are_handled_by_the_first_sweep(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    new_client: ClientFactory,
    clock: ControllableClock,
    jobs: RecordingJobPublisher,
    judge: Judge,
) -> None:
    agent = await sampled(app, owner)
    jobs.lose_next()
    lost = await reply(visitor, agent)
    judge.kill_next = True
    died = await reply(await new_client(), agent)
    # As the migration leaves them: never sent again, no claim recorded.
    async with app.state.sessionmaker() as session, session.begin():
        await session.execute(update(LiveVerdict).values(queued_at=None, claim_id=None))

    clock.advance(timedelta(days=3))
    assert await sweep(clock) == 2

    assert await status_of(owner, agent, lost) == "judged"
    assert await status_of(owner, agent, died) == "judged"


# Settings


async def test_the_threshold_and_the_number_of_resends_are_settings(
    app: FastAPI,
    settings_env: pytest.MonkeyPatch,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    jobs: RecordingJobPublisher,
    judge: Judge,
) -> None:
    defaults = load_settings()
    assert (defaults.live_verdict_pending_seconds, defaults.live_verdict_resends) == (300, 1)
    settings_env.setenv("LIVE_VERDICT_PENDING_SECONDS", "60")
    settings_env.setenv("LIVE_VERDICT_RESENDS", "0")
    agent = await sampled(app, owner)
    jobs.lose_next()
    events = await reply(visitor, agent)

    clock.advance(timedelta(seconds=60))
    assert await sweep(clock) == 1

    assert await status_of(owner, agent, events) == "error"
    assert judge.calls == 0
