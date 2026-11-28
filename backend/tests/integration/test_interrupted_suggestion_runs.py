"""API seam plus task seam for Suggestion runs that are cut short (spec 21, ADR-0020): a worker
killed while gathering, proposing or checking, a run that never reached the queue, a run's job
delivered twice, a long run that is still alive, a check Run cancelled directly, and runs stuck
before this shipped.

A kill comes from the scripted chat model raising ``JobKilled`` as the run builds its nth model
(the proposer's, or a check answer's), which stops the job without running its error handling;
gathering reads no model, so a kill there comes from reading its evidence. A lost message comes from
the Job publisher fake. The sweeper is called directly as a task, as Beat would call it, with the
controllable clock moved past each threshold. Outcomes are read through the API, and every test
counts the proposing calls the fake chat model answered."""

import asyncio
from collections.abc import AsyncIterator
from datetime import timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models import Model
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlalchemy import update

from app.credentials.registry import Provider
from app.evaluation.fake_judge import fake_judgement, is_judging
from app.gateway.fakes import FakeModelAdapters
from app.jobs.faults import JobKilled
from app.main import create_app
from app.suggestions.fake_proposer import CITE_LINE, fake_proposal
from app.suggestions.models import Suggestion, SuggestionStatus
from app.suggestions.tasks import run_suggestion_task
from tests.conftest import ClientFactory, SignedUpMember
from tests.fakes.clock import ControllableClock
from tests.fakes.jobs import RecordingJobPublisher
from tests.integration.test_evaluation import add_case, evaluation_path
from tests.integration.test_evaluation_settings import set_repeats
from tests.integration.test_suggestion_check import CITED, REFERENCE, UNCITED
from tests.integration.test_suggestions import (
    everything,
    live_agent,
    replied,
    start,
    suggestions_path,
)
from tests.jobs import settle_jobs_in_flight

SUGGESTION = "suggestions.run"
RUN = "evaluation.run"


@pytest.fixture
def exporter() -> InMemorySpanExporter:
    return InMemorySpanExporter()


@pytest.fixture
async def app(
    settings_env: pytest.MonkeyPatch, database_schema: None, exporter: InMemorySpanExporter
) -> AsyncIterator[FastAPI]:
    """The app, with its spans also captured in memory, so tests can read the traces."""
    application = create_app(extra_span_processors=[SimpleSpanProcessor(exporter)])
    async with LifespanManager(application):
        yield application


@pytest.fixture(autouse=True)
async def no_jobs_left_by_earlier_tests(app: FastAPI) -> None:
    """Earlier tests on this database may have left jobs in flight; each test here starts with
    them settled, so every sweep sees only the test's own rows."""
    await settle_jobs_in_flight(app)


@pytest.fixture
async def visitor(new_client: ClientFactory) -> httpx.AsyncClient:
    """A browser on someone's website: no Studio session."""
    return await new_client()


async def sweep(clock: ControllableClock) -> int | None:
    """Runs the sweeper task as Beat would, as of the controllable clock's time."""
    from app.jobs.tasks import sweep_jobs

    result = await asyncio.to_thread(sweep_jobs.apply, kwargs={"at": clock.now().isoformat()})
    swept: int | None = result.get(disable_sync_subtasks=False)
    return swept


async def deliver_again(suggestion_id: str) -> None:
    """A second delivery of the Suggestion run's job, straight to the worker."""
    await asyncio.to_thread(run_suggestion_task.apply, (suggestion_id,))


def recovered(exporter: InMemorySpanExporter) -> list[tuple[Any, ...]]:
    """The recoveries the sweeper recorded in the traces: job, identifier and reason."""
    template = "Sweeper recovered {job} {job_id}: {reason}"
    return [
        (attributes["job"], attributes["job_id"], attributes["reason"])
        for span in exporter.get_finished_spans()
        if (attributes := span.attributes or {}).get("logfire.msg_template") == template
    ]


class Held:
    """Holds the first call made after it is armed until the test releases it, without blocking
    the job's event loop, so the run's heartbeat keeps being written meanwhile."""

    def __init__(self) -> None:
        self.armed = False
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self._loop = asyncio.get_running_loop()

    async def hold(self) -> None:
        if not self.armed:
            return
        self.armed = False
        self._loop.call_soon_threadsafe(self.started.set)
        released = asyncio.run_coroutine_threadsafe(self.release.wait(), self._loop)
        await asyncio.wait_for(asyncio.wrap_future(released), timeout=10)

    async def wait_until_started(self) -> None:
        await asyncio.wait_for(self.started.wait(), timeout=10)


class Models:
    """The chat models the app builds: Visitor replies and check answers stream ``CITED`` when the
    system prompt holds the fake proposer's citation line (else ``UNCITED``), judging is the fake
    judge's and proposing the fake proposer's. Counts the proposing calls answered.
    ``kill_at(n)`` kills the job as it builds its nth model from now: the worker died. ``held``
    holds the next proposing call (``hold_proposing``) or check answer (``hold_checking``)."""

    def __init__(self, app: FastAPI) -> None:
        self.built = 0
        self.proposed = 0
        self.held_proposing = Held()
        self.held_checking = Held()
        self._kill_at: int | None = None
        app.state.model_gateway.adapters = FakeModelAdapters(chat=self._chat)

    def kill_at(self, build: int) -> None:
        self._kill_at = self.built + build

    def _chat(self, provider: Provider, secret: str, model: str) -> Model:
        self.built += 1
        if self.built == self._kill_at:
            raise JobKilled("chat")
        return FunctionModel(
            self._complete,
            stream_function=self._stream,
            model_name=model,
            profile={"supports_json_schema_output": False},
        )

    async def _complete(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if is_judging(info):
            return fake_judgement(messages, info)
        await self.held_proposing.hold()
        self.proposed += 1
        return fake_proposal(messages, info)

    async def _stream(self, messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
        given = everything(messages)
        if "Leave question" not in given:
            # A Visitor's question: the reply cites nothing, so its Live Verdict fails.
            yield UNCITED
            return
        await self.held_checking.hold()
        yield CITED if CITE_LINE in given else UNCITED


async def live_agent_with_evidence(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    *,
    cases: int = 1,
) -> tuple[dict[str, Any], Models]:
    """A live Agent with one failed Visitor reply as evidence and ``cases`` Evaluation Cases (so
    a configuration change is checked; none, and it isn't)."""
    models = Models(app)
    agent = await live_agent(app, owner)
    await set_repeats(owner, 1)
    for number in range(cases):
        await add_case(
            owner, agent["project_id"], agent["id"], f"Leave question {number}?", REFERENCE
        )
    await replied(visitor, agent)
    return agent, models


async def read(member: SignedUpMember, agent: dict[str, Any], suggestion_id: str) -> Any:
    response = await member.client.get(suggestions_path(member, agent, suggestion_id))
    assert response.status_code == 200, response.text
    return response.json()


async def check_run(member: SignedUpMember, agent: dict[str, Any], run_id: str) -> Any:
    response = await member.client.get(
        evaluation_path(member, agent["project_id"], agent["id"], "runs", run_id)
    )
    assert response.status_code == 200, response.text
    return response.json()


async def started(member: SignedUpMember, agent: dict[str, Any]) -> Any:
    response = await start(member, agent)
    assert response.status_code == 202, response.text
    return response.json()


def kept(suggestion: dict[str, Any]) -> tuple[Any, ...]:
    """How much a run stored: its evidence, changes and Knowledge Base gaps."""
    return len(suggestion["evidence"]), len(suggestion["changes"]), len(suggestion["gaps"])


# --- A second delivery ----------------------------------------------------------------------


async def test_a_finished_runs_job_delivered_again_changes_nothing_and_proposes_nothing(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, jobs: RecordingJobPublisher
) -> None:
    agent, models = await live_agent_with_evidence(app, owner, visitor)
    suggestion = await started(owner, agent)
    assert (suggestion["status"], suggestion["outcome"]) == ("completed", "changes")
    assert models.proposed == 1
    before = await read(owner, agent, suggestion["id"])
    assert kept(before) == (1, 1, 1)

    await deliver_again(suggestion["id"])

    assert models.proposed == 1
    assert await read(owner, agent, suggestion["id"]) == before


# --- A worker killed in each phase ----------------------------------------------------------


async def test_a_run_killed_while_gathering_fails_as_interrupted_and_frees_the_agent(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    jobs: RecordingJobPublisher,
    exporter: InMemorySpanExporter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent, models = await live_agent_with_evidence(app, owner, visitor, cases=0)

    async def worker_dies(*args: Any) -> None:
        raise JobKilled("gathering")

    with monkeypatch.context() as patched:
        patched.setattr("app.suggestions.service._gather", worker_dies)
        suggestion = await started(owner, agent)
    assert suggestion["status"] == "gathering"
    assert len(jobs.killed) == 1

    # Another copy of its job, while the dead one still holds the run, does nothing.
    await deliver_again(suggestion["id"])
    assert (await read(owner, agent, suggestion["id"]))["status"] == "gathering"
    clock.advance(timedelta(minutes=4, seconds=59))
    assert await sweep(clock) == 0
    clock.advance(timedelta(seconds=2))
    assert await sweep(clock) == 1

    failed = await read(owner, agent, suggestion["id"])
    assert (failed["status"], failed["failure_reason"]) == ("failed", "interrupted")
    assert failed["finished_at"] is not None
    assert failed["evidence"] == []
    assert models.proposed == 0
    assert recovered(exporter) == [(SUGGESTION, suggestion["id"], "no heartbeat")]
    # The Agent is free for a new run, which completes.
    assert (await started(owner, agent))["status"] == "completed"


async def test_a_run_killed_while_proposing_fails_as_interrupted_and_its_job_proposes_nothing(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    jobs: RecordingJobPublisher,
) -> None:
    agent, models = await live_agent_with_evidence(app, owner, visitor)
    # The proposer's model is the first the run builds.
    models.kill_at(1)

    suggestion = await started(owner, agent)

    assert suggestion["status"] == "proposing"
    clock.advance(timedelta(minutes=6))
    assert await sweep(clock) == 1
    failed = await read(owner, agent, suggestion["id"])
    assert (failed["status"], failed["failure_reason"]) == ("failed", "interrupted")
    assert failed["changes"] == []
    assert failed["check"] is None
    # Its evidence, gathered before it died, is kept; nothing is added again.
    assert len(failed["evidence"]) == 1
    await deliver_again(suggestion["id"])
    assert models.proposed == 0
    assert await read(owner, agent, suggestion["id"]) == failed


async def test_a_run_killed_while_checking_keeps_its_proposal_not_checked(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    jobs: RecordingJobPublisher,
    exporter: InMemorySpanExporter,
) -> None:
    agent, models = await live_agent_with_evidence(app, owner, visitor, cases=2)
    # Built: the proposer (1), the first case's answer on the Live Version (2) and its judge (3),
    # then the Suggestion's answer.
    models.kill_at(4)

    suggestion = await started(owner, agent)

    assert suggestion["status"] == "checking"
    assert models.proposed == 1
    clock.advance(timedelta(minutes=6))
    # The check Run and the Suggestion run both stopped writing heartbeats.
    assert await sweep(clock) == 2

    settled = await read(owner, agent, suggestion["id"])
    assert (settled["status"], settled["outcome"]) == ("completed", "changes")
    assert settled["failure_reason"] is None
    assert settled["check"]["state"] == "not_checked"
    run_id = settled["check"]["evaluation_run_id"]
    assert (await check_run(owner, agent, run_id))["status"] == "interrupted"
    # The proposing Cost is kept, and what the check spent is frozen.
    assert Decimal(settled["cost"]["proposing_usd"]) > 0
    assert Decimal(settled["cost"]["checking_usd"]) > 0
    assert sorted(recovered(exporter)) == sorted(
        [(RUN, run_id, "no heartbeat"), (SUGGESTION, suggestion["id"], "no heartbeat")]
    )
    # A second delivery changes nothing and pays for no proposal.
    await deliver_again(suggestion["id"])
    assert models.proposed == 1
    assert await read(owner, agent, suggestion["id"]) == settled
    # The Agent is free for a new run.
    assert (await started(owner, agent))["status"] == "completed"


# --- A run that is alive ----------------------------------------------------------------------


@pytest.mark.parametrize("phase", ["proposing", "checking"])
async def test_a_long_run_keeps_writing_heartbeats_and_a_second_delivery_does_nothing(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    jobs: RecordingJobPublisher,
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
) -> None:
    """However long proposing or the check takes, a run whose worker is alive is never
    interrupted, and another copy of its job proposes nothing."""
    monkeypatch.setenv("JOB_HEARTBEAT_SECONDS", "0.05")
    agent, models = await live_agent_with_evidence(app, owner, visitor)
    held = models.held_proposing if phase == "proposing" else models.held_checking
    held.armed = True
    starting = asyncio.create_task(started(owner, agent))
    await held.wait_until_started()
    (listed,) = (await owner.client.get(suggestions_path(owner, agent))).json()

    clock.advance(timedelta(minutes=10))
    # A few heartbeats go by (in real time) after the clock moved.
    await asyncio.sleep(0.5)
    swept = await sweep(clock)
    await deliver_again(listed["id"])

    assert swept == 0
    assert (await read(owner, agent, listed["id"]))["status"] == phase
    held.release.set()
    finished = await starting
    assert (finished["status"], finished["check"]["state"]) == ("completed", "clear")
    assert models.proposed == 1


# --- A run that never reached the queue -------------------------------------------------------


async def test_a_run_that_never_reached_the_queue_is_sent_again_after_fifteen_minutes(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    jobs: RecordingJobPublisher,
    exporter: InMemorySpanExporter,
) -> None:
    agent, models = await live_agent_with_evidence(app, owner, visitor, cases=0)
    jobs.lose_next()

    suggestion = await started(owner, agent)

    assert suggestion["status"] == "queued"
    clock.advance(timedelta(minutes=14))
    assert await sweep(clock) == 0
    clock.advance(timedelta(minutes=1, seconds=1))
    assert await sweep(clock) == 1
    assert (await read(owner, agent, suggestion["id"]))["status"] == "completed"
    assert models.proposed == 1
    assert recovered(exporter) == [(SUGGESTION, suggestion["id"], "queued too long")]


# --- Cancelling the check Run directly --------------------------------------------------------


async def test_cancelling_a_suggestions_check_run_settles_it_as_not_checked(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    jobs: RecordingJobPublisher,
) -> None:
    """The check's worker died, so nothing else would move the Suggestion on: cancelling its
    Run from the Run history settles it at once."""
    agent, models = await live_agent_with_evidence(app, owner, visitor, cases=2)
    models.kill_at(4)
    suggestion = await started(owner, agent)
    run_id = (await read(owner, agent, suggestion["id"]))["check"]["evaluation_run_id"]

    cancelled = await owner.client.post(
        evaluation_path(owner, agent["project_id"], agent["id"], "runs", run_id, "cancel")
    )

    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"
    settled = await read(owner, agent, suggestion["id"])
    assert (settled["status"], settled["check"]["state"]) == ("completed", "not_checked")
    assert settled["check"]["evaluation_run_id"] == run_id
    assert Decimal(settled["cost"]["checking_usd"]) > 0
    assert models.proposed == 1
    assert (await started(owner, agent))["status"] == "completed"


async def test_a_check_run_cancelled_while_its_job_is_alive_settles_as_not_checked(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    jobs: RecordingJobPublisher,
) -> None:
    agent, models = await live_agent_with_evidence(app, owner, visitor)
    models.held_checking.armed = True
    starting = asyncio.create_task(started(owner, agent))
    await models.held_checking.wait_until_started()
    (listed,) = (await owner.client.get(suggestions_path(owner, agent))).json()
    run_id = listed["check"]["evaluation_run_id"]

    cancelled = await owner.client.post(
        evaluation_path(owner, agent["project_id"], agent["id"], "runs", run_id, "cancel")
    )
    models.held_checking.release.set()
    await starting

    assert cancelled.status_code == 200, cancelled.text
    settled = await read(owner, agent, listed["id"])
    assert (settled["status"], settled["check"]["state"]) == ("completed", "not_checked")
    assert (await check_run(owner, agent, run_id))["status"] == "cancelled"


# --- Runs stuck before this shipped -----------------------------------------------------------


@pytest.mark.parametrize("stuck_on", [SuggestionStatus.GATHERING, SuggestionStatus.PROPOSING])
async def test_runs_stuck_in_progress_before_this_shipped_are_settled_on_the_first_sweep(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    jobs: RecordingJobPublisher,
    stuck_on: SuggestionStatus,
) -> None:
    """A run left in progress by the code before this, as the migration leaves it: no claim and
    no heartbeat. The first sweep settles it, however recently it started."""
    agent, _ = await live_agent_with_evidence(app, owner, visitor, cases=0)
    jobs.lose_next()
    suggestion = await started(owner, agent)
    async with app.state.sessionmaker() as session, session.begin():
        await session.execute(
            update(Suggestion)
            .where(Suggestion.id == suggestion["id"])
            .values(status=stuck_on, claim_id=None, heartbeat_at=None)
        )

    assert await sweep(clock) == 1

    settled = await read(owner, agent, suggestion["id"])
    assert (settled["status"], settled["failure_reason"]) == ("failed", "interrupted")
