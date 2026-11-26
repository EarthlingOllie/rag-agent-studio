"""API seam and task seam: no job stays in progress after an error (spec 21, ticket 21-02).

A sampled reply's Live Verdict is judged and charged once however often its job runs: a second
run after the first finished makes no judge call and records no spend, and a second copy while
the first is judging finds it claimed and makes no judge call (ticket 21-07); the spend is stored
in the one conditional update that stores the verdict.
An Evaluation Run, Suggestion run or Live Verdict whose job raises an unexpected error ends in a
state a person can see: a Failed Run with a reason that frees the Agent, a Failed Suggestion run
whose check Run is ended too, and a Live Verdict that is an Error and left out of the Live score.

Models are the scripted fake chat model, whose judge calls are counted; an unexpected error is a
``RuntimeError`` raised where no handler expects one. Spend is read back through the Evaluation
budget API. Held-back jobs are run as the worker would, in a thread with an event loop of its own.
"""

import asyncio
import threading
import uuid
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo

from app.evaluation.fake_judge import fake_judgement, is_judging
from app.evaluation.job import run_evaluation
from app.suggestions import service
from app.suggestions.tasks import run_suggestion_task
from tests.conftest import ClientFactory, SignedUpMember
from tests.fakes.clock import ControllableClock
from tests.integration.test_evaluation import add_case, evaluation_path, judge_with
from tests.integration.test_evaluation_budget import budget, judged_cost
from tests.integration.test_evaluation_cost import started as run_started
from tests.integration.test_evaluation_settings import set_repeats
from tests.integration.test_live_score import DAY, live_score
from tests.integration.test_live_verdict_context import held_back as held_back
from tests.integration.test_live_verdict_context import judge_now
from tests.integration.test_live_verdicts import (
    Judgement,
    live_agent,
    live_verdict,
    message_id,
    reply,
    sampling,
    scripted,
)
from tests.integration.test_playground import ready_agent, three_tokens
from tests.integration.test_suggestion_check import (
    CITED,
    UNCITED,
    read,
    runs,
    visitor_replies_then,
)
from tests.integration.test_suggestion_runs import in_new_session, scope_of
from tests.integration.test_suggestion_runs import unsent as unsent
from tests.integration.test_suggestions import live_agent as suggesting_agent
from tests.integration.test_suggestions import replied
from tests.integration.test_suggestions import scripted as suggesting
from tests.integration.test_suggestions import started as suggestion_started

BROKEN = "The judge's client was handed a closed connection."


class Killed(BaseException):
    """The worker died here: no error handling of the job's runs."""


@pytest.fixture
async def visitor(new_client: ClientFactory) -> httpx.AsyncClient:
    """A browser on someone's website: no Studio session."""
    return await new_client()


def counting(calls: list[str]) -> Judgement:
    """A judge as the fake chat model judges, recording each judge call."""

    def judgement(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        assert is_judging(info)
        calls.append("judge")
        return fake_judgement(messages, info)

    return judgement


async def spent(owner: SignedUpMember) -> Decimal:
    return Decimal((await budget(owner))["spent_usd"])


# A Live Verdict is judged and charged once


async def test_a_second_run_of_a_live_verdicts_job_makes_no_judge_call_and_records_no_spend(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    held_back: list[uuid.UUID],
) -> None:
    calls: list[str] = []
    scripted(app, judgement=counting(calls))
    agent = await live_agent(app, owner)
    await sampling(owner, agent, 100)
    events = await reply(visitor, agent)
    (verdict_id,) = held_back

    await judge_now(verdict_id)
    first = await live_verdict(owner, agent, events)
    once = await spent(owner)
    await judge_now(verdict_id)

    assert calls == ["judge"]
    assert await live_verdict(owner, agent, events) == first
    assert await spent(owner) == once == (await judged_cost(owner, agent, message_id(events)))


async def test_a_second_copy_of_a_live_verdicts_job_while_the_first_judges_makes_no_judge_call(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    held_back: list[uuid.UUID],
) -> None:
    calls: list[str] = []
    # The first copy is asking the judge, holding no lock on the Live Verdict, when the second
    # copy starts: the first copy's claim makes the second exit (ticket 21-07).
    asking = threading.Event()
    answer = threading.Event()
    judging = counting(calls)

    def judgement(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        asking.set()
        assert answer.wait(timeout=30)
        return judging(messages, info)

    scripted(app, judgement=judgement)
    agent = await live_agent(app, owner)
    await sampling(owner, agent, 100)
    events = await reply(visitor, agent)
    (verdict_id,) = held_back

    first = asyncio.create_task(judge_now(verdict_id))
    assert await asyncio.to_thread(asking.wait, 30)
    await judge_now(verdict_id)
    assert (await live_verdict(owner, agent, events) or {})["status"] == "pending"
    answer.set()
    await first

    assert calls == ["judge"]
    cost = await judged_cost(owner, agent, message_id(events))
    assert cost > 0
    assert await spent(owner) == cost


# An unexpected error ends the job in a state a person can see


async def test_a_live_verdict_whose_job_raises_unexpectedly_is_an_error_left_out_of_the_score(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    new_client: ClientFactory,
    clock: ControllableClock,
) -> None:
    def judgement(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if "BROKEN" in str(messages):
            raise RuntimeError(BROKEN)
        return fake_judgement(messages, info)

    scripted(app, judgement=judgement)
    agent = await live_agent(app, owner)
    agent["v1"] = agent["version"]
    await sampling(owner, agent, 100)

    judged = await reply(visitor, agent)
    broken = await reply(await new_client(), agent, "How much annual leave? BROKEN")

    verdict = await live_verdict(owner, agent, broken)
    assert verdict is not None
    assert verdict["status"] == "error"
    assert verdict["error_reason"] == (
        "Judging stopped on an unexpected error; this reply is left out of the Live score."
    )
    assert (await live_verdict(owner, agent, judged) or {})["status"] == "judged"
    # Only the judged reply counts in the Live score.
    assert (await live_score(owner, agent, **DAY))["n"] == 1


async def test_an_evaluation_run_whose_job_raises_unexpectedly_fails_and_frees_the_agent(
    app: FastAPI, owner: SignedUpMember
) -> None:
    raised: list[str] = []

    async def answer_then_break(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str]:
        if raised:
            raise RuntimeError(BROKEN)
        raised.append("once")
        async for token in three_tokens(messages, info):
            yield token

    judge_with(app, answer_then_break)
    _, project_id, agent_id = await ready_agent(app, owner)
    await set_repeats(owner, 1)
    for question in ("First?", "Second?"):
        await add_case(owner, project_id, agent_id, question)

    run = await run_started(owner, project_id, agent_id)

    response = await owner.client.get(
        evaluation_path(owner, project_id, agent_id, "runs", run["id"], "results")
    )
    finished = response.json()["run"]
    assert finished["status"] == "failed"
    assert finished["error_message"] == (
        "The Run stopped on an unexpected error. What it answered is kept; run it again."
    )
    assert finished["finished_at"] is not None
    # What it answered before the error is kept.
    assert finished["progress"]["done"] == 1
    # The Agent is free for another Run.
    again = await owner.client.post(evaluation_path(owner, project_id, agent_id, "runs"))
    assert again.status_code == 202, again.text


SUGGESTION_UNEXPECTED = "The Suggestion run stopped on an unexpected error. Start a new one."


async def test_a_suggestion_run_whose_job_raises_unexpectedly_fails(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    def broken(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        raise RuntimeError(BROKEN)

    suggesting(app, proposer=broken)
    agent = await suggesting_agent(app, owner)
    await replied(visitor, agent)

    suggestion = await suggestion_started(owner, agent)

    assert (suggestion["status"], suggestion["error_message"]) == ("failed", SUGGESTION_UNEXPECTED)
    assert suggestion["finished_at"] is not None
    assert suggestion["check"] is None


async def test_a_suggestion_run_cancelled_before_an_unexpected_error_stays_cancelled(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent: dict[str, Any] = {}

    async def cancel_then_break(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        async def cancel_it(session: Any) -> None:
            scope = scope_of(owner)
            project_id, agent_id = uuid.UUID(agent["project_id"]), uuid.UUID(agent["id"])
            ((found, *_),) = await service.list_suggestions(session, scope, project_id, agent_id)
            await service.cancel_suggestion(
                session, scope, project_id, agent_id, found.id, now=clock.now()
            )

        await in_new_session(cancel_it)
        raise RuntimeError(BROKEN)

    suggesting(app, proposer=cancel_then_break)
    agent.update(await suggesting_agent(app, owner))
    await replied(visitor, agent)

    suggestion = await suggestion_started(owner, agent)

    assert (suggestion["status"], suggestion["error_message"]) == ("cancelled", None)


async def test_a_suggestion_run_that_raises_after_its_check_finished_keeps_the_check(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent, _ = await visitor_replies_then(
        app, owner, visitor, with_line=CITED, without_line=UNCITED
    )

    async def check_then_break(
        sessionmaker: Any, ports: Any, gateway: Any, run_id: uuid.UUID, clock: Any
    ) -> None:
        await run_evaluation(sessionmaker, ports, gateway, run_id, clock)
        raise RuntimeError(BROKEN)

    monkeypatch.setattr("app.suggestions.service.run_evaluation", check_then_break)

    suggestion = await suggestion_started(owner, agent)

    assert (suggestion["status"], suggestion["error_message"]) == ("failed", SUGGESTION_UNEXPECTED)
    (run,) = await runs(owner, agent)
    assert (run["id"], run["status"]) == (suggestion["check"]["evaluation_run_id"], "completed")


async def test_a_suggestion_run_that_finds_its_check_run_in_progress_fails_and_ends_it(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    unsent: list[uuid.UUID],
) -> None:
    agent, _ = await visitor_replies_then(
        app, owner, visitor, with_line=CITED, without_line=UNCITED
    )
    suggestion = await suggestion_started(owner, agent)
    (suggestion_id,) = unsent

    async def dies(*args: Any) -> None:
        raise Killed

    # The first copy's worker dies once the check Run is started: the Suggestion is Checking and
    # its check Run is left in progress.
    monkeypatch.setattr("app.suggestions.service.run_evaluation", dies)
    with pytest.raises(Killed):
        await asyncio.to_thread(run_suggestion_task.run, str(suggestion_id))
    assert (await read(owner, agent, suggestion["id"]))["status"] == "checking"
    (stranded,) = await runs(owner, agent)
    assert stranded["status"] == "queued"

    # The job is delivered again.
    monkeypatch.setattr("app.suggestions.service.run_evaluation", run_evaluation)
    await asyncio.to_thread(run_suggestion_task.run, str(suggestion_id))

    settled = await read(owner, agent, suggestion["id"])
    assert (settled["status"], settled["error_message"]) == ("failed", SUGGESTION_UNEXPECTED)
    (run,) = await runs(owner, agent)
    assert (run["id"], run["status"]) == (stranded["id"], "failed")
    assert run["error_message"] == SUGGESTION_UNEXPECTED
    # The Agent is free for another Run.
    again = await owner.client.post(
        evaluation_path(owner, agent["project_id"], agent["id"], "runs")
    )
    assert again.status_code == 202, again.text
