"""API seam plus task seam for Evaluation Runs that are cut short (spec 21, ADR-0020): a worker
killed mid-Run, a Run that never reached the queue (also from a Rollout evaluation), a Run's job
delivered twice, a long Run that is still alive, and Runs stuck on Running before this shipped.

A kill comes from the scripted chat model raising ``JobKilled`` when the Run builds its nth model,
which stops the job without running its error handling. A lost message comes from the Job
publisher fake. The sweeper is called directly as a task, as Beat would call it, with the
controllable clock moved past each threshold. Outcomes are read through the API, as an Editor
would see them, and the traces."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models import Model
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlalchemy import update

from app.credentials.registry import Provider
from app.evaluation import rollout_api
from app.evaluation.models import EvaluationRun, RunStatus
from app.evaluation.tasks import enqueue_run, run_evaluation_task
from app.gateway.fakes import FakeModelAdapters, fake_chat
from app.jobs.faults import JobKilled
from app.main import create_app
from tests.agents import StreamFunction
from tests.conftest import SignedUpMember
from tests.fakes.clock import ControllableClock
from tests.fakes.jobs import RecordingJobPublisher
from tests.integration.test_evaluation import add_case, evaluation_path
from tests.integration.test_evaluation_publish import summary
from tests.integration.test_evaluation_rollout import (
    TABLE as ROLLOUT_TABLE,
)
from tests.integration.test_evaluation_rollout import (
    answering as rollout_answering,
)
from tests.integration.test_evaluation_rollout import (
    live_agent,
    rolled_out,
    rollout,
    start_rollout,
    states,
)
from tests.integration.test_evaluation_settings import set_repeats
from tests.integration.test_evaluation_sides import results_of, start
from tests.integration.test_playground import ready_agent, three_tokens
from tests.jobs import settle_jobs_in_flight

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
    """The test database is shared by the tests a worker runs, one after another, so earlier
    tests may have left Runs or Documents in flight (a Run left queued on purpose, a kill). The
    sweeper would recover those too, so each test here starts with them settled: every sweep then
    sees only the test's own rows."""
    await settle_jobs_in_flight(app)


async def sweep(clock: ControllableClock) -> int | None:
    """Runs the sweeper task as Beat would, as of the controllable clock's time."""
    from app.jobs.tasks import sweep_jobs

    result = await asyncio.to_thread(sweep_jobs.apply, kwargs={"at": clock.now().isoformat()})
    swept: int | None = result.get(disable_sync_subtasks=False)
    return swept


async def deliver_again(run_id: str) -> None:
    """A second delivery of the Run's job, straight to the worker."""
    await asyncio.to_thread(run_evaluation_task.apply, (run_id,))


def recovered(exporter: InMemorySpanExporter) -> list[tuple[Any, ...]]:
    """The recoveries the sweeper recorded in the traces: job, identifier and reason."""
    template = "Sweeper recovered {job} {job_id}: {reason}"
    return [
        (attributes["job"], attributes["job_id"], attributes["reason"])
        for span in exporter.get_finished_spans()
        if (attributes := span.attributes or {}).get("logfire.msg_template") == template
    ]


class Models:
    """The chat models the Runs build (to answer and to judge), answering by streaming
    ``stream`` and judging as the fake chat model. ``kill_at(n)`` kills the job as it builds its
    nth model from now: the worker died."""

    def __init__(self, app: FastAPI, stream: StreamFunction) -> None:
        self.built = 0
        self._kill_at: int | None = None
        self._stream = stream
        app.state.model_gateway.adapters = FakeModelAdapters(chat=self._chat)

    def kill_at(self, build: int) -> None:
        self._kill_at = self.built + build

    def _chat(self, provider: Provider, secret: str, model: str) -> Model:
        self.built += 1
        if self.built == self._kill_at:
            raise JobKilled("chat")
        fake = fake_chat(provider, secret, model)
        assert isinstance(fake, FunctionModel)
        assert fake.function is not None
        return FunctionModel(
            fake.function,
            stream_function=self._stream,
            model_name=model,
            profile={"supports_json_schema_output": False},
        )


class HeldStream:
    """Streams the answer, holding its first answer until the test releases it (so the Run stays
    Running while the test acts). It waits without blocking the job's event loop, so the Run's
    heartbeat keeps being written meanwhile."""

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.answers = 0
        self._loop = asyncio.get_running_loop()

    async def __call__(self, messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
        self.answers += 1
        if self.answers == 1:
            self._loop.call_soon_threadsafe(self.started.set)
            released = asyncio.run_coroutine_threadsafe(self.release.wait(), self._loop)
            await asyncio.wait_for(asyncio.wrap_future(released), timeout=10)
        async for token in three_tokens(messages, info):
            yield token

    async def wait_until_started(self) -> None:
        await asyncio.wait_for(self.started.wait(), timeout=10)


async def run_of(member: SignedUpMember, project_id: str, agent_id: str, run_id: str) -> Any:
    response = await member.client.get(
        evaluation_path(member, project_id, agent_id, "runs", run_id)
    )
    assert response.status_code == 200, response.text
    return response.json()


async def killed_run(
    app: FastAPI, owner: SignedUpMember, jobs: RecordingJobPublisher
) -> tuple[str, str, dict[str, Any], Models]:
    """A Run of one case, three repeats, whose worker died answering its second repeat (the
    first answer and its judging were done)."""
    models = Models(app, three_tokens)
    _, project_id, agent_id = await ready_agent(app, owner)
    await add_case(owner, project_id, agent_id)
    # Built: the first answer's model (1), its judge (2), then the second answer's model.
    models.kill_at(3)
    started = await start(owner, project_id, agent_id)
    assert started.status_code == 202, started.text
    assert len(jobs.killed) == 1
    return project_id, agent_id, started.json(), models


# --- A worker killed mid-Run ----------------------------------------------------------------


async def test_a_run_whose_worker_died_becomes_interrupted_keeping_what_it_answered_and_spent(
    app: FastAPI,
    owner: SignedUpMember,
    clock: ControllableClock,
    jobs: RecordingJobPublisher,
    exporter: InMemorySpanExporter,
) -> None:
    project_id, agent_id, run, _ = await killed_run(app, owner, jobs)
    assert (run["status"], run["progress"]) == ("running", {"done": 1, "total": 3})

    # Still within the dead-after time: the sweeper leaves it alone.
    clock.advance(timedelta(minutes=4, seconds=59))
    assert await sweep(clock) == 0
    assert (await run_of(owner, project_id, agent_id, run["id"]))["status"] == "running"

    clock.advance(timedelta(seconds=2))
    assert await sweep(clock) == 1

    interrupted = await run_of(owner, project_id, agent_id, run["id"])
    assert interrupted["status"] == "interrupted"
    assert interrupted["finished_at"] is not None
    assert interrupted["error_message"] is None
    assert interrupted["progress"] == {"done": 1, "total": 3}
    # Its Cost so far is what the first answer and its judging cost.
    assert float(interrupted["cost"]["answers_usd"]) > 0
    assert float(interrupted["cost"]["judging_usd"]) > 0
    results = await results_of(owner, project_id, agent_id, run["id"])
    (case,) = results["cases"]
    (answer,) = case["results"]
    assert (answer["repeat"], answer["status"], answer["passed"]) == (1, "answered", True)
    assert [v["kind"] for v in answer["verdicts"]] == ["reference_answer", "grounding"]
    assert recovered(exporter) == [(RUN, run["id"], "no heartbeat")]


async def test_an_interrupted_run_frees_the_agent_for_another_run(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock, jobs: RecordingJobPublisher
) -> None:
    project_id, agent_id, _, _ = await killed_run(app, owner, jobs)
    refused = await start(owner, project_id, agent_id)
    assert refused.status_code == 409
    clock.advance(timedelta(minutes=6))
    assert await sweep(clock) == 1

    again = await start(owner, project_id, agent_id)

    assert again.status_code == 202, again.text
    assert again.json()["status"] == "completed"


async def test_an_interrupted_run_cannot_be_cancelled_and_its_job_delivered_again_does_nothing(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock, jobs: RecordingJobPublisher
) -> None:
    project_id, agent_id, run, models = await killed_run(app, owner, jobs)
    clock.advance(timedelta(minutes=6))
    await sweep(clock)
    interrupted = await results_of(owner, project_id, agent_id, run["id"])
    built = models.built

    await deliver_again(run["id"])
    cancelled = await owner.client.post(
        evaluation_path(owner, project_id, agent_id, "runs", run["id"], "cancel")
    )

    assert cancelled.status_code == 409
    assert models.built == built
    assert await results_of(owner, project_id, agent_id, run["id"]) == interrupted


async def test_interrupted_runs_count_as_cancelled_ones_for_latest_results_and_publish(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock, jobs: RecordingJobPublisher
) -> None:
    """Reads that mean "latest result" (the set, failed cases a Suggestion takes as evidence) and
    the Evaluation summary for Publish leave an Interrupted Run out."""
    models = Models(app, three_tokens)
    _, project_id, agent_id = await ready_agent(app, owner)
    await set_repeats(owner, 1)
    case = await add_case(owner, project_id, agent_id)
    finished = (await start(owner, project_id, agent_id)).json()
    assert finished["status"] == "completed"
    before = await summary(owner, project_id, agent_id)
    second = await add_case(owner, project_id, agent_id, "Where do visitors park?", "North.")
    # The first case is answered and judged (two models), then the worker dies.
    models.kill_at(3)
    killed = (await start(owner, project_id, agent_id)).json()
    clock.advance(timedelta(minutes=6))
    assert await sweep(clock) == 1
    assert (await run_of(owner, project_id, agent_id, killed["id"]))["status"] == "interrupted"

    cases = (await owner.client.get(evaluation_path(owner, project_id, agent_id, "cases"))).json()

    latest = {c["id"]: c["latest_result"] for c in cases}
    assert latest[case["id"]]["run_id"] == finished["id"]
    assert latest[second["id"]] is None
    assert await summary(owner, project_id, agent_id) == before


# --- A Run that is alive, and a second delivery ---------------------------------------------


async def test_a_long_run_keeps_writing_heartbeats_and_a_second_delivery_does_nothing(
    app: FastAPI,
    owner: SignedUpMember,
    clock: ControllableClock,
    jobs: RecordingJobPublisher,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """However long an answer takes, a Run whose worker is alive is never interrupted, and
    another copy of its job pays for no answer."""
    monkeypatch.setenv("JOB_HEARTBEAT_SECONDS", "0.05")
    held = HeldStream()
    models = Models(app, held)
    _, project_id, agent_id = await ready_agent(app, owner)
    await set_repeats(owner, 1)
    await add_case(owner, project_id, agent_id)
    starting = asyncio.create_task(start(owner, project_id, agent_id))
    await held.wait_until_started()
    (listed,) = (
        await owner.client.get(evaluation_path(owner, project_id, agent_id, "runs"))
    ).json()

    clock.advance(timedelta(minutes=10))
    # A few heartbeats go by (in real time) after the clock moved.
    await asyncio.sleep(0.5)
    swept = await sweep(clock)
    built = models.built
    await deliver_again(listed["id"])

    assert swept == 0
    assert models.built == built
    assert (await run_of(owner, project_id, agent_id, listed["id"]))["status"] == "running"
    held.release.set()
    started = await starting
    assert started.json()["status"] == "completed"
    assert held.answers == 1


# --- A Run that never reached the queue ------------------------------------------------------


async def test_a_run_that_never_reached_the_queue_is_sent_again_after_fifteen_minutes(
    app: FastAPI,
    owner: SignedUpMember,
    clock: ControllableClock,
    jobs: RecordingJobPublisher,
    exporter: InMemorySpanExporter,
) -> None:
    Models(app, three_tokens)
    _, project_id, agent_id = await ready_agent(app, owner)
    await add_case(owner, project_id, agent_id)
    jobs.lose_next()

    run = (await start(owner, project_id, agent_id)).json()

    assert run["status"] == "queued"
    clock.advance(timedelta(minutes=14))
    assert await sweep(clock) == 0
    clock.advance(timedelta(minutes=1, seconds=1))
    assert await sweep(clock) == 1
    assert (await run_of(owner, project_id, agent_id, run["id"]))["status"] == "completed"
    assert recovered(exporter) == [(RUN, run["id"], "queued too long")]


async def test_rollout_runs_never_queued_because_the_api_died_partway_are_sent_again(
    app: FastAPI,
    owner: SignedUpMember,
    clock: ControllableClock,
    jobs: RecordingJobPublisher,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    Models(app, rollout_answering(ROLLOUT_TABLE))
    project_id, first_id, second_id, _, v2 = await rolled_out(app, owner)
    await add_case(owner, project_id, second_id, "Same?")
    third_id = await live_agent(owner, project_id, "IT helper", "Same?")
    sent = 0

    async def dying_after_the_first(run_id: uuid.UUID) -> None:
        """The first Agent's Run is sent; the API dies before sending the others."""
        nonlocal sent
        sent += 1
        if sent > 1:
            jobs.lose_next()
        await enqueue_run(run_id)

    monkeypatch.setattr(rollout_api, "enqueue_run", dying_after_the_first)

    started = await start_rollout(owner, project_id, v2["id"], [first_id, second_id, third_id])

    # One Agent's Run finished; the other two wait on Queued.
    assert sorted(states(started.json()).values()).count("running") == 2
    clock.advance(timedelta(minutes=16))
    assert await sweep(clock) == 2
    assert states(await rollout(owner, project_id, v2["id"])) == {
        "HR helper": "regressions",
        "Payroll helper": "clear",
        "IT helper": "clear",
    }


# --- Runs stuck before this shipped ---------------------------------------------------------


async def test_runs_stuck_on_running_before_this_shipped_become_interrupted_on_the_first_sweep(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock, jobs: RecordingJobPublisher
) -> None:
    """A Run left Running by the code before this, as the migration leaves it: no claim and no
    heartbeat. It becomes Interrupted on the first sweep, however recently it started."""
    Models(app, three_tokens)
    _, project_id, agent_id = await ready_agent(app, owner)
    await add_case(owner, project_id, agent_id)
    jobs.lose_next()
    run = (await start(owner, project_id, agent_id)).json()
    async with app.state.sessionmaker() as session, session.begin():
        await session.execute(
            update(EvaluationRun)
            .where(EvaluationRun.id == run["id"])
            .values(status=RunStatus.RUNNING, claim_id=None, heartbeat_at=None)
        )

    assert await sweep(clock) == 1

    assert (await run_of(owner, project_id, agent_id, run["id"]))["status"] == "interrupted"
