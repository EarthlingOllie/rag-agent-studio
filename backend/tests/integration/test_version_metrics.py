"""API seam and task seam: Version KPIs. Visitors chat through the widget API (answers from a
``FunctionModel``), give Message Feedback and Conversation Ratings; the ``usage_daily`` rollup
Beat task is called directly as a task; Editors read each Agent Version's KPIs from the
Version metrics endpoint: volume, mean and p95 tokens per reply, cost per Conversation,
thumbs-up rate with its Wilson 95% interval and sample size, mean rating with its count,
fallback rate and p95 latency, with small samples flagged as low confidence.

Assertions are on HTTP responses only. The exact values the KPIs are checked against come from
the Conversations viewer (each reply's own tokens, latency and frozen cost), not from the
rollups."""

import asyncio
import math
import re
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic_ai.messages import ModelMessage, UserPromptPart
from pydantic_ai.models.function import AgentInfo

from app.analytics.tasks import roll_up_usage
from app.worker.celery_app import ROLL_UP_TASK, celery_app
from tests.agents import answer_with, create_agent, save_draft, use_default_model
from tests.conftest import ClientFactory, MemberFactory, SignedUpMember
from tests.documents import create_project, project_path, upload
from tests.fakes.clock import ControllableClock
from tests.integration.test_agent_versions import published
from tests.integration.test_conversations import listed, opened, playground_chat
from tests.integration.test_embed import conversation_token
from tests.integration.test_message_feedback import bearer, give, reply
from tests.integration.test_playground import LEAVE
from tests.integration.test_prices import override

NOV_5 = date(2026, 11, 5)


@pytest.fixture
async def visitor(new_client: ClientFactory) -> httpx.AsyncClient:
    """A browser on someone's website: no Studio session."""
    return await new_client()


_WORDS = re.compile(r"words:(\d+)")


async def wordy(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
    """Answers with as many words as the question asks for (``words:N``; 5 otherwise), so
    replies differ in their token counts."""
    question = " ".join(
        str(part.content) for part in messages[-1].parts if isinstance(part, UserPromptPart)
    )
    found = _WORDS.findall(question)
    count = int(found[-1]) if found else 5
    yield " ".join(["leave"] * count)


async def live_agent(app: FastAPI, owner: SignedUpMember) -> dict[str, Any]:
    """A live Agent (v1) in a Project holding the leave policy, answered by ``wordy`` through
    an OpenAI credential; with its ``project_id`` and ``credential_id``."""
    answer_with(app, wordy)
    credential_id = await use_default_model(owner)
    project_id = await create_project(owner)
    await upload(app, owner, project_id, "leave.txt", LEAVE.encode())
    agent: dict[str, Any] = await create_agent(owner, project_id)
    agent["project_id"] = project_id
    agent["credential_id"] = credential_id
    agent["v1"] = await published(owner, project_id, agent["id"])
    return agent


async def publish_next(owner: SignedUpMember, agent: dict[str, Any], prompt: str) -> Any:
    saved = await save_draft(
        owner, agent["project_id"], agent["id"], {"behaviour": {"system_prompt": prompt}}
    )
    assert saved.status_code == 200, saved.text
    return await published(owner, agent["project_id"], agent["id"])


def metrics_path(member: SignedUpMember, agent: dict[str, Any]) -> str:
    return f"{project_path(member, agent['project_id'])}/agents/{agent['id']}/metrics"


async def get_metrics(
    member: SignedUpMember, agent: dict[str, Any], **params: Any
) -> httpx.Response:
    return await member.client.get(metrics_path(member, agent), params=params)


async def metrics(member: SignedUpMember, agent: dict[str, Any], **params: Any) -> dict[str, Any]:
    response = await get_metrics(member, agent, **params)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def version_kpis(
    member: SignedUpMember, agent: dict[str, Any], version: dict[str, Any], **params: Any
) -> dict[str, Any]:
    (kpis,) = (await metrics(member, agent, version=version["id"], **params))["versions"]
    return dict(kpis)


async def roll_up(at: datetime) -> None:
    """Runs the rollup Beat task as Beat would at ``at`` (in a thread: the task runs its own
    event loop)."""
    result = await asyncio.to_thread(roll_up_usage.apply, kwargs={"at": at.isoformat()})
    # disable_sync_subtasks=False: this test isn't inside a task, but Celery's "inside a task" guard
    # is a process-wide flag that eager tasks run concurrently in other threads (by earlier tests
    # in the same xdist worker) can leave set.
    result.get(disable_sync_subtasks=False)


async def chat(
    visitor: httpx.AsyncClient, agent: dict[str, Any], *questions: str
) -> tuple[str, list[str]]:
    """A new Visitor Conversation asking each question; its token and the replies' IDs."""
    token = await conversation_token(visitor, agent["public_id"])
    replies = [await reply(visitor, agent["public_id"], token, q) for q in questions]
    return token, replies


async def rate(visitor: httpx.AsyncClient, agent: dict[str, Any], token: str, score: int) -> None:
    response = await visitor.put(
        f"/api/widget/agents/{agent['public_id']}/conversation/rating",
        json={"score": score},
        headers=bearer(token),
    )
    assert response.status_code == 200, response.text


async def thumb(
    visitor: httpx.AsyncClient, agent: dict[str, Any], token: str, message_id: str, rating: str
) -> None:
    response = await give(visitor, agent["public_id"], token, message_id, rating=rating)
    assert response.status_code == 200, response.text


async def visitor_replies(owner: SignedUpMember, agent: dict[str, Any]) -> list[dict[str, Any]]:
    """Every Visitor reply of the Agent, read back from the Conversations viewer."""
    page = await listed(owner, agent["project_id"], playground="false", page_size=100)
    found: list[dict[str, Any]] = []
    for row in page["items"]:
        detail = await opened(owner, agent["project_id"], row["id"])
        found.extend(m for m in detail["messages"] if m["role"] == "assistant")
    return found


def nearest_rank(values: list[int], p: float) -> int:
    ordered = sorted(values)
    return ordered[max(math.ceil(p * len(ordered)) - 1, 0)]


def within_ten_percent(estimate: float, exact: int) -> bool:
    # A histogram bucket is 10% wide; tiny latencies sit in the [0, 1) ms bucket.
    return abs(estimate - exact) <= max(0.10 * exact, 1)


# The KPIs


async def test_a_versions_kpis_count_visitor_conversations_feedback_and_ratings(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    agent = await live_agent(app, owner)
    first, (a1, a2) = await chat(visitor, agent, "Leave? words:12", "And sick days? words:40")
    await thumb(visitor, agent, first, a1, "up")
    await thumb(visitor, agent, first, a2, "up")
    await rate(visitor, agent, first, 5)
    second, (b1,) = await chat(visitor, agent, "Parental leave? words:3")
    await thumb(visitor, agent, second, b1, "down")
    await rate(visitor, agent, second, 2)
    await chat(visitor, agent, "Holidays? words:90")
    # Playground use of the same Agent never counts.
    await playground_chat(owner, agent["project_id"], agent["id"], "Testing words:500")

    kpis = await version_kpis(owner, agent, agent["v1"], start="2026-11-05", end="2026-11-05")

    replies = await visitor_replies(owner, agent)
    assert len(replies) == 4
    tokens = [m["input_tokens"] + m["output_tokens"] for m in replies]
    latencies = [m["latency_ms"] for m in replies]
    first_tokens = [m["first_token_ms"] for m in replies]
    cost = sum(Decimal(m["cost_usd"]) for m in replies)
    assert cost > 0
    assert kpis["version_id"] == agent["v1"]["id"]
    assert kpis["number"] == 1
    assert kpis["is_live"] is True
    assert (kpis["conversations"], kpis["messages"]) == (3, 4)
    assert kpis["tokens"]["n"] == 4
    assert kpis["tokens"]["mean"] == pytest.approx(sum(tokens) / 4)
    assert within_ten_percent(kpis["tokens"]["p95"], nearest_rank(tokens, 0.95))
    assert Decimal(kpis["cost"]["total_usd"]) == cost
    assert Decimal(kpis["cost"]["per_conversation_usd"]) == pytest.approx(cost / 3)
    # Two thumbs up out of three: Wilson 95% interval (statsmodels reference values).
    assert kpis["thumbs_up"] | {"low": None, "high": None} == {
        "up": 2,
        "down": 1,
        "n": 3,
        "rate": pytest.approx(2 / 3),
        "low": None,
        "high": None,
        "low_confidence": True,
    }
    assert kpis["thumbs_up"]["low"] == pytest.approx(0.2076596, abs=1e-6)
    assert kpis["thumbs_up"]["high"] == pytest.approx(0.9385081, abs=1e-6)
    assert kpis["rating"] == {"n": 2, "mean": 3.5, "low_confidence": True}
    assert kpis["fallback"] == {"count": 0, "rate": 0.0}
    assert kpis["latency"]["n"] == 4
    assert within_ten_percent(kpis["latency"]["total_p95_ms"], nearest_rank(latencies, 0.95))
    assert within_ten_percent(
        kpis["latency"]["first_token_p95_ms"], nearest_rank(first_tokens, 0.95)
    )
    assert kpis["low_confidence"] is True


async def test_the_same_numbers_come_from_the_rollups_once_the_day_is_final(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    agent = await live_agent(app, owner)
    token, (r1, _r2) = await chat(visitor, agent, "Leave? words:8", "More words:70")
    await thumb(visitor, agent, token, r1, "up")
    await rate(visitor, agent, token, 4)
    await chat(visitor, agent, "Other words:20")
    live_day = await version_kpis(owner, agent, agent["v1"], start="2026-11-05", end="2026-11-05")

    clock.advance(timedelta(days=1))
    await roll_up(clock.now())
    final_day = await version_kpis(owner, agent, agent["v1"], start="2026-11-05", end="2026-11-05")

    assert final_day == live_day
    assert (final_day["conversations"], final_day["messages"]) == (2, 3)
    assert final_day["rating"] == {"n": 1, "mean": 4.0, "low_confidence": True}


async def test_the_live_partial_day_is_included(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    agent = await live_agent(app, owner)
    await chat(visitor, agent, "Monday words:5")
    clock.advance(timedelta(days=1))
    await roll_up(clock.now())
    # Tuesday: no rollup has run since these replies.
    await chat(visitor, agent, "Tuesday words:5", "Again words:5")

    both = await version_kpis(owner, agent, agent["v1"], start="2026-11-05", end="2026-11-06")
    tuesday = await version_kpis(owner, agent, agent["v1"], start="2026-11-06", end="2026-11-06")

    assert (both["conversations"], both["messages"]) == (2, 3)
    assert (tuesday["conversations"], tuesday["messages"]) == (1, 2)


async def test_past_days_are_read_from_their_rollups_which_are_final_once_the_day_is_over(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    agent = await live_agent(app, owner)
    await chat(visitor, agent, "Morning words:5")  # 09:00
    clock.advance(timedelta(hours=1))
    await roll_up(clock.now())  # the hourly run for the current day
    clock.advance(timedelta(hours=5))
    token, (afternoon,) = await chat(visitor, agent, "Afternoon words:5")  # 15:00
    clock.advance(timedelta(hours=9, minutes=30))
    # 00:30 the next day: the first day is over, but its rollup hasn't been finalised yet.
    before = await version_kpis(owner, agent, agent["v1"], start="2026-11-05", end="2026-11-05")

    await roll_up(clock.now())
    finalised = await version_kpis(owner, agent, agent["v1"], start="2026-11-05", end="2026-11-05")
    # Feedback given after the day was finalised doesn't change it.
    await thumb(visitor, agent, token, afternoon, "down")
    await roll_up(clock.now() + timedelta(hours=1))
    later = await version_kpis(owner, agent, agent["v1"], start="2026-11-05", end="2026-11-05")

    assert before["conversations"] == 1  # only the hourly run's morning
    assert (finalised["conversations"], finalised["messages"]) == (2, 2)
    assert later == finalised
    assert later["thumbs_up"]["n"] == 0


async def test_rollups_are_idempotent(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    agent = await live_agent(app, owner)
    token, (r1,) = await chat(visitor, agent, "Leave words:30")
    await thumb(visitor, agent, token, r1, "up")
    await rate(visitor, agent, token, 3)
    clock.advance(timedelta(days=1))
    await chat(visitor, agent, "Next day words:9")

    await roll_up(clock.now())
    once = await metrics(owner, agent, start="2026-11-05", end="2026-11-06")
    await roll_up(clock.now())
    await roll_up(clock.now() + timedelta(minutes=30))
    again = await metrics(owner, agent, start="2026-11-05", end="2026-11-06")

    assert again == once
    (kpis,) = once["versions"]
    assert (kpis["conversations"], kpis["messages"], kpis["thumbs_up"]["n"]) == (2, 2, 1)


async def test_days_missed_by_the_task_are_caught_up(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    agent = await live_agent(app, owner)
    await roll_up(clock.now() - timedelta(days=3))  # an earlier run: nothing to roll up
    for _ in range(3):
        await chat(visitor, agent, "Daily words:4")
        clock.advance(timedelta(days=1))

    # The task didn't run for three days; the next run finalises each of them.
    await roll_up(clock.now())

    for day in ("2026-11-05", "2026-11-06", "2026-11-07"):
        kpis = await version_kpis(owner, agent, agent["v1"], start=day, end=day)
        assert (kpis["conversations"], kpis["messages"]) == (1, 1)


async def test_the_beat_schedule_runs_the_rollup_hourly(app: FastAPI) -> None:
    (entry,) = [e for e in celery_app.conf.beat_schedule.values() if e["task"] == ROLL_UP_TASK]
    assert entry["schedule"].minute == {5}
    assert entry["schedule"].hour == set(range(24))


async def test_without_a_time_the_task_rolls_up_now(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await live_agent(app, owner)
    await chat(visitor, agent, "Now words:4")

    result = await asyncio.to_thread(roll_up_usage.apply)
    # disable_sync_subtasks=False: this test isn't inside a task, but Celery's "inside a task" guard
    # is a process-wide flag that eager tasks run concurrently in other threads (by earlier tests
    # in the same xdist worker) can leave set.
    result.get(disable_sync_subtasks=False)

    today = datetime.now(UTC).date().isoformat()
    kpis = await version_kpis(owner, agent, agent["v1"], start=today, end=today)
    assert kpis["messages"] == 1


# Versions, attribution and exclusions


async def test_each_version_has_its_own_kpis_and_a_conversation_counts_for_each_that_replied(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    agent = await live_agent(app, owner)
    token, (old,) = await chat(visitor, agent, "Before words:5")
    await thumb(visitor, agent, token, old, "up")
    v2 = await publish_next(owner, agent, "Be brief.")
    # The same Conversation goes on with v2; the rating goes to v2, the last reply's Version.
    new = await reply(visitor, agent["public_id"], token, "After words:5")
    await thumb(visitor, agent, token, new, "down")
    await rate(visitor, agent, token, 1)

    body = await metrics(owner, agent, start="2026-11-05", end="2026-11-05")

    v1_kpis, v2_kpis = body["versions"]
    assert [v1_kpis["number"], v2_kpis["number"]] == [1, 2]
    assert [v1_kpis["is_live"], v2_kpis["is_live"]] == [False, True]
    assert (v1_kpis["conversations"], v1_kpis["messages"]) == (1, 1)
    assert (v2_kpis["conversations"], v2_kpis["messages"]) == (1, 1)
    assert (v1_kpis["thumbs_up"]["up"], v1_kpis["thumbs_up"]["down"]) == (1, 0)
    assert (v2_kpis["thumbs_up"]["up"], v2_kpis["thumbs_up"]["down"]) == (0, 1)
    assert v1_kpis["rating"] == {"n": 0, "mean": None, "low_confidence": True}
    assert v2_kpis["rating"] == {"n": 1, "mean": 1.0, "low_confidence": True}
    assert body["agent_id"] == agent["id"]
    assert (body["start"], body["end"]) == ("2026-11-05", "2026-11-05")
    only_v2 = await metrics(owner, agent, version=v2["id"], start="2026-11-05", end="2026-11-05")
    assert only_v2["versions"] == [v2_kpis]


async def test_a_version_with_no_visitor_use_has_empty_kpis(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock
) -> None:
    agent = await live_agent(app, owner)
    await playground_chat(owner, agent["project_id"], agent["id"], "Only testing words:5")

    kpis = await version_kpis(owner, agent, agent["v1"], start="2026-11-05", end="2026-11-05")

    assert kpis == {
        "version_id": agent["v1"]["id"],
        "number": 1,
        "is_live": True,
        "retrieval_mode": "automatic",
        "conversations": 0,
        "messages": 0,
        "low_confidence": True,
        "tokens": {"n": 0, "mean": None, "p95": None},
        "cost": {"total_usd": "0.000000000", "per_conversation_usd": None},
        "thumbs_up": {
            "up": 0,
            "down": 0,
            "n": 0,
            "rate": None,
            "low": None,
            "high": None,
            "low_confidence": True,
        },
        "rating": {"n": 0, "mean": None, "low_confidence": True},
        "fallback": {"count": 0, "rate": None},
        "guardrail_blocks": {"count": 0, "rate": None},
        "searches": {"total": 0, "mean_per_reply": None},
        "latency": {"n": 0, "first_token_p95_ms": None, "total_p95_ms": None},
    }


async def test_fallback_replies_count_in_the_fallback_rate_but_not_in_tokens(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    agent = await live_agent(app, owner)
    await chat(visitor, agent, "Leave words:6")
    clock.advance(timedelta(days=1))
    # v2 needs a relevance no Chunk reaches, so it always replies with its fallback text.
    saved = await save_draft(
        owner, agent["project_id"], agent["id"], {"retrieval": {"min_score": 1}}
    )
    assert saved.status_code == 200, saved.text
    v2 = await published(owner, agent["project_id"], agent["id"])
    await chat(visitor, agent, "Leave words:6", "Pay words:6", "Sick words:6")
    await roll_up(clock.now() + timedelta(days=1))

    kpis = await version_kpis(owner, agent, v2, start="2026-11-05", end="2026-11-06")

    assert kpis["fallback"] == {"count": 3, "rate": 1.0}
    assert kpis["messages"] == 3
    assert kpis["tokens"] == {"n": 0, "mean": None, "p95": None}
    assert kpis["latency"]["n"] == 3


async def test_cost_per_conversation_uses_the_costs_frozen_when_each_reply_was_made(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    agent = await live_agent(app, owner)
    await chat(visitor, agent, "Cheap words:50")
    changed = await override(
        owner, agent["credential_id"], model="gpt-4.1-mini", input="100", output="400"
    )
    assert changed.status_code == 200, changed.text
    await chat(visitor, agent, "Dear words:50")

    replies = await visitor_replies(owner, agent)
    kpis = await version_kpis(owner, agent, agent["v1"], start="2026-11-05", end="2026-11-05")

    cheap, dear = sorted(Decimal(m["cost_usd"]) for m in replies)
    assert dear > 10 * cheap  # the override applies from the second reply on, not before
    assert Decimal(kpis["cost"]["total_usd"]) == cheap + dear
    assert Decimal(kpis["cost"]["per_conversation_usd"]) == pytest.approx((cheap + dear) / 2)


async def test_thirty_votes_are_no_longer_a_small_sample(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    agent = await live_agent(app, owner)
    token = await conversation_token(visitor, agent["public_id"])
    for number in range(30):
        # Stay under the per-Conversation rate limit (10 messages a minute).
        clock.advance(timedelta(seconds=7))
        message_id = await reply(visitor, agent["public_id"], token, f"Question {number}")
        if number < 29:
            await thumb(visitor, agent, token, message_id, "up" if number < 23 else "down")

    small = await version_kpis(owner, agent, agent["v1"], start="2026-11-05", end="2026-11-05")
    await thumb(visitor, agent, token, message_id, "up")
    enough = await version_kpis(owner, agent, agent["v1"], start="2026-11-05", end="2026-11-05")

    assert (small["thumbs_up"]["n"], small["thumbs_up"]["low_confidence"]) == (29, True)
    assert enough["thumbs_up"] | {"low": None, "high": None} == {
        "up": 24,
        "down": 6,
        "n": 30,
        "rate": pytest.approx(0.8),
        "low": None,
        "high": None,
        "low_confidence": False,
    }
    assert enough["thumbs_up"]["low"] == pytest.approx(0.6269430, abs=1e-6)
    assert enough["thumbs_up"]["high"] == pytest.approx(0.9049489, abs=1e-6)


# The query


async def test_by_default_every_version_and_the_last_30_days_are_shown(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    agent = await live_agent(app, owner)
    await chat(visitor, agent, "Old words:5")  # 2026-11-05
    await publish_next(owner, agent, "Two.")
    clock.advance(timedelta(days=30))
    await chat(visitor, agent, "New words:5")  # 2026-12-05

    body = await metrics(owner, agent)

    assert (body["start"], body["end"]) == ("2026-11-06", "2026-12-05")
    assert [(v["number"], v["messages"]) for v in body["versions"]] == [(1, 0), (2, 1)]


async def test_days_after_today_hold_nothing(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    agent = await live_agent(app, owner)
    await chat(visitor, agent, "Today words:5")

    kpis = await version_kpis(owner, agent, agent["v1"], start="2026-11-06", end="2026-11-30")

    assert kpis["messages"] == 0


@pytest.mark.parametrize(
    "params",
    [
        {"start": "2026-11-06", "end": "2026-11-05"},
        {"start": "2025-01-01", "end": "2026-11-05"},
        {"start": "yesterday"},
        {"version": "not-a-uuid"},
    ],
)
async def test_bad_queries_are_refused(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock, params: dict[str, str]
) -> None:
    agent = await live_agent(app, owner)

    response = await get_metrics(owner, agent, **params)

    assert response.status_code == 422, response.text


async def test_another_agents_version_or_an_unknown_agent_is_not_found(
    app: FastAPI, owner: SignedUpMember, tenant_factory: Any, clock: ControllableClock
) -> None:
    agent = await live_agent(app, owner)
    other = await create_agent(owner, agent["project_id"], "Other")
    other_version = await published(owner, agent["project_id"], other["id"])
    stranger = await tenant_factory()

    wrong_version = await get_metrics(owner, agent, version=other_version["id"])
    unknown_agent = await get_metrics(owner, agent | {"id": other_version["id"]})
    other_tenant = await stranger.client.get(
        metrics_path(owner, agent).replace(owner.organisation_id, stranger.organisation_id)
    )

    assert wrong_version.status_code == 404, wrong_version.text
    assert unknown_agent.status_code == 404, unknown_agent.text
    assert other_tenant.status_code == 404, other_tenant.text


async def test_editors_read_metrics(
    app: FastAPI,
    owner: SignedUpMember,
    member_factory: MemberFactory,
    clock: ControllableClock,
) -> None:
    agent = await live_agent(app, owner)
    editor = await member_factory(owner, "editor")

    response = await get_metrics(editor, agent)

    assert response.status_code == 200, response.text
