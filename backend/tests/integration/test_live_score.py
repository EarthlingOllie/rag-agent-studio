"""API seam and task seam: the Live score (spec 15). Visitors chat through the widget API with the
Agent's Live sample rate at 100%, so every reply gets a Live Verdict, judged eagerly in the
background by a scripted judge; the ``usage_daily`` rollup and the purge Beat tasks are called
directly as tasks; Editors read each Version's Live score from the Version metrics, the Version
comparison (and its CSV) and the Time series.

The scripted judge decides by the Visitor's question: a question with ``WRONG`` in it fails the
grounding check, one with ``OUTAGE`` in it can't be judged (an error), and any other passes.
Assertions are on HTTP responses only; Wilson intervals are checked against reference values."""

import asyncio
import csv
import io
from datetime import timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo

from app.evaluation.tasks import judge_live_verdict_task
from tests.conftest import ClientFactory, SignedUpMember
from tests.fakes.clock import ControllableClock
from tests.integration.test_conversations import playground_chat
from tests.integration.test_live_verdicts import (
    PASSED,
    judged,
    sampling,
    scripted,
)
from tests.integration.test_live_verdicts import live_agent as served_agent
from tests.integration.test_live_verdicts import reply as ask
from tests.integration.test_retention import purge, set_window
from tests.integration.test_version_comparison import comparison, get_comparison, rows
from tests.integration.test_version_metrics import metrics, publish_next, roll_up, version_kpis

DAY = {"start": "2026-11-05", "end": "2026-11-05"}
FAILED = {"passed": False, "reason": "Claims a figure no excerpt gives."}
NONE = {"n": 0, "passed": 0, "rate": None, "low": None, "high": None, "low_confidence": True}


@pytest.fixture
async def visitor(new_client: ClientFactory) -> httpx.AsyncClient:
    """A browser on someone's website: no Studio session."""
    return await new_client()


def _asked(messages: list[ModelMessage]) -> str:
    return "\n".join(
        str(part.content)
        for message in messages
        for part in message.parts
        if hasattr(part, "content")
    )


def by_question(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    """Fails grounding for a ``WRONG`` question, can't judge an ``OUTAGE`` one, passes others."""
    asked = _asked(messages)
    if "OUTAGE" in asked:
        raise ModelHTTPError(status_code=503, model_name="gpt-4.1-mini")
    return judged(FAILED if "WRONG" in asked else PASSED, PASSED)(messages, info)


async def judged_agent(app: FastAPI, owner: SignedUpMember) -> dict[str, Any]:
    """A live Automatic Agent (v1) over the leave policy whose every Visitor reply is judged by
    ``by_question``."""
    scripted(app, judgement=by_question)
    agent = await served_agent(app, owner)
    await sampling(owner, agent, 100)
    agent["v1"] = agent["version"]
    return agent


async def chat(
    visitor: httpx.AsyncClient, clock: ControllableClock, agent: dict[str, Any], *questions: str
) -> None:
    """Each question in a new Visitor Conversation, a few seconds apart (under the rate limits)."""
    for question in questions:
        clock.advance(timedelta(seconds=7))
        await ask(visitor, agent, f"How much annual leave? {question}")


async def live_score(member: SignedUpMember, agent: dict[str, Any], **params: Any) -> Any:
    return (await version_kpis(member, agent, agent["v1"], **params))["live_score"]


# The KPI


async def test_a_versions_live_score_is_the_share_of_its_judged_replies_that_passed(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent = await judged_agent(app, owner)
    await chat(visitor, clock, agent, "one", "two", "three", "WRONG", "OUTAGE")

    score = await live_score(owner, agent, **DAY)

    # Three of four judged replies passed; the error is left out. Wilson 95% reference values.
    assert score | {"low": None, "high": None} == {
        "n": 4,
        "passed": 3,
        "rate": pytest.approx(0.75),
        "low": None,
        "high": None,
        "low_confidence": True,
    }
    assert score["low"] == pytest.approx(0.3006418, abs=1e-6)
    assert score["high"] == pytest.approx(0.9544127, abs=1e-6)


async def test_a_version_with_no_judged_reply_has_no_live_score(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent = await judged_agent(app, owner)
    await chat(visitor, clock, agent, "OUTAGE")
    await sampling(owner, agent, 0)
    await chat(visitor, clock, agent, "not sampled")

    assert await live_score(owner, agent, **DAY) == NONE


async def test_the_same_live_score_comes_from_the_rollups_once_the_day_is_final(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent = await judged_agent(app, owner)
    await chat(visitor, clock, agent, "one", "WRONG", "OUTAGE")
    live_day = await version_kpis(owner, agent, agent["v1"], **DAY)

    clock.advance(timedelta(days=1))
    await roll_up(clock.now())
    final_day = await version_kpis(owner, agent, agent["v1"], **DAY)

    assert final_day == live_day
    assert (final_day["live_score"]["n"], final_day["live_score"]["passed"]) == (2, 1)


async def test_the_live_partial_day_is_added_to_the_rolled_up_days(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent = await judged_agent(app, owner)
    await chat(visitor, clock, agent, "one")
    clock.advance(timedelta(days=1))
    await roll_up(clock.now())
    await chat(visitor, clock, agent, "WRONG", "two")

    both = await live_score(owner, agent, start="2026-11-05", end="2026-11-06")
    today = await live_score(owner, agent, start="2026-11-06", end="2026-11-06")

    assert (both["n"], both["passed"]) == (3, 2)
    assert (today["n"], today["passed"]) == (2, 1)


@pytest.fixture
def held(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Holds back the judging of chosen replies, as a busy worker would: the Live Verdicts stay
    pending until the test runs their tasks."""
    queued: list[str] = []

    async def hold(verdict_id: Any) -> None:
        queued.append(str(verdict_id))

    monkeypatch.setattr("app.embed.api.enqueue_live_verdict", hold)
    return queued


async def judge_held(queued: list[str]) -> None:
    for verdict_id in queued:
        result = await asyncio.to_thread(judge_live_verdict_task.apply, args=(verdict_id,))
        # See ``roll_up``: the "inside a task" guard is process-wide.
        result.get(disable_sync_subtasks=False)
    queued.clear()


async def test_a_live_verdict_counts_on_the_day_of_its_reply(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    held: list[str],
) -> None:
    agent = await judged_agent(app, owner)
    clock.advance(timedelta(hours=14, minutes=50))  # 23:50
    await chat(visitor, clock, agent, "one")
    clock.advance(timedelta(minutes=20))  # 00:10 the next day: judged, not yet finalised
    await judge_held(held)
    clock.advance(timedelta(minutes=20))

    await roll_up(clock.now())

    assert (await live_score(owner, agent, **DAY))["n"] == 1
    assert (await live_score(owner, agent, start="2026-11-06", end="2026-11-06"))["n"] == 0


async def test_a_live_verdict_judged_after_its_day_is_final_does_not_move_that_day(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    held: list[str],
) -> None:
    agent = await judged_agent(app, owner)
    await chat(visitor, clock, agent, "one")
    pending = await live_score(owner, agent, **DAY)
    clock.advance(timedelta(days=1))
    await roll_up(clock.now())

    await judge_held(held)
    await roll_up(clock.now() + timedelta(hours=1))

    assert pending == NONE
    assert await live_score(owner, agent, **DAY) == NONE
    assert await live_score(owner, agent, start="2026-11-06", end="2026-11-06") == NONE


async def test_thirty_judged_replies_are_no_longer_a_small_sample(
    app: FastAPI, owner: SignedUpMember, new_client: ClientFactory, clock: ControllableClock
) -> None:
    agent = await judged_agent(app, owner)
    visitor = await new_client()
    await chat(visitor, clock, agent, *["WRONG"] * 9, *["fine"] * 20)

    small = await live_score(owner, agent, **DAY)
    await chat(visitor, clock, agent, "fine")
    enough = await live_score(owner, agent, **DAY)

    assert (small["n"], small["low_confidence"]) == (29, True)
    assert (enough["n"], enough["passed"], enough["low_confidence"]) == (30, 21, False)
    assert enough["rate"] == pytest.approx(0.7)
    assert enough["low"] == pytest.approx(0.5212421, abs=1e-6)
    assert enough["high"] == pytest.approx(0.8333525, abs=1e-6)


async def test_the_live_score_reads_the_same_before_and_after_the_purge(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent = await judged_agent(app, owner)
    assert (await set_window(owner, 7)).status_code == 200
    await chat(visitor, clock, agent, "one", "WRONG", "two")
    clock.advance(timedelta(days=8))
    await roll_up(clock.now())
    before = await metrics(owner, agent, start="2026-11-05", end="2026-11-13")

    await purge(clock.now())

    assert await metrics(owner, agent, start="2026-11-05", end="2026-11-13") == before
    (kpis,) = before["versions"]
    assert (kpis["live_score"]["n"], kpis["live_score"]["passed"]) == (3, 2)


async def test_only_visitor_replies_count(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent = await judged_agent(app, owner)
    await chat(visitor, clock, agent, "one")
    await playground_chat(owner, agent["project_id"], agent["id"], "How much annual leave? WRONG")

    assert (await live_score(owner, agent, **DAY))["n"] == 1


# The Version comparison


async def two_judged_versions(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """v1 with three of four replies passed; v2 (Live) with one of two."""
    agent = await judged_agent(app, owner)
    await chat(visitor, clock, agent, "one", "two", "three", "WRONG")
    v2 = await publish_next(owner, agent, "Answer in one sentence.")
    await chat(visitor, clock, agent, "four", "WRONG")
    return agent, agent["v1"], v2


async def test_the_comparison_has_a_live_score_row_where_higher_is_better(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent, v1, v2 = await two_judged_versions(app, owner, visitor, clock)

    body = await comparison(owner, agent, v1, v2, **DAY)

    assert rows(body)["live_score"] == {
        "metric": "live_score",
        "label": "Live score",
        "unit": "rate",
        "a": pytest.approx(0.75),
        "b": pytest.approx(0.5),
        "difference": pytest.approx(-0.25),
        "changed": True,
        "better": "a",
        "low_confidence": True,
    }
    assert (body["a"]["live_score"]["n"], body["b"]["live_score"]["n"]) == (4, 2)
    reversed_body = await comparison(owner, agent, v2, v1, **DAY)
    assert rows(reversed_body)["live_score"]["better"] == "b"


async def test_the_live_score_is_exported_in_the_comparison_csv(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent, v1, v2 = await two_judged_versions(app, owner, visitor, clock)

    response = await get_comparison(owner, agent, csv=True, a=v1["id"], b=v2["id"], **DAY)

    assert response.status_code == 200, response.text
    found = {row[0]: row for row in csv.reader(io.StringIO(response.text))}
    assert found["Live score"] == ["Live score", "0.7500", "0.5000", "-0.2500", "v1"]


# The Time series


async def test_the_time_series_has_the_live_score_with_gaps_and_live_history_markers(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent = await judged_agent(app, owner)
    await chat(visitor, clock, agent, "one", "WRONG")
    clock.advance(timedelta(days=1))  # 6 November: no reply judged
    await chat(visitor, clock, agent, "OUTAGE")
    clock.advance(timedelta(days=1))
    await roll_up(clock.now())
    await publish_next(owner, agent, "Be brief.")
    await chat(visitor, clock, agent, "two")  # today, the live partial day

    response = await owner.client.get(
        f"/api/organisations/{owner.organisation_id}/projects/{agent['project_id']}"
        f"/agents/{agent['id']}/time-series",
        params={"metric": "live_score", "start": "2026-11-05", "end": "2026-11-07"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert [(p["start"], p["value"], p["n"]) for p in body["points"]] == [
        ("2026-11-05", pytest.approx(0.5), 2),
        ("2026-11-06", None, 0),
        ("2026-11-07", pytest.approx(1.0), 1),
    ]
    assert [(m["day"], m["to_version"]["number"]) for m in body["markers"]] == [
        ("2026-11-05", 1),
        ("2026-11-07", 2),
    ]
