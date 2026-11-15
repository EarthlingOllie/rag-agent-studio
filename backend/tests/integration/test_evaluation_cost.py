"""API seam: Run Cost. The Evaluate dialog's estimate before a Run starts, the estimate stored on
the Run, the actual Cost split into answers and judging and frozen at the prices in force when it
ran (a controllable clock and a dated price change), and the Evaluation column in Organisation
cost.

Answers come from a scripted ``FunctionModel`` and judging from the fake chat model's judge, as in
``test_evaluation``. Expected amounts come from independent sources: hand-worked prices from the
repo's price table (``gpt-4.1-mini`` is $0.40 in and $1.60 out per million tokens), the Traces of
the Run's own answers, and the Conversations viewer's frozen cost of each earlier reply.
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.credentials.registry import Provider
from app.pricing.sync import sync_price_table
from app.pricing.table import PriceEntry
from tests.agents import create_automatic_agent
from tests.conftest import ClientFactory, SignedUpMember
from tests.fakes.clock import ControllableClock
from tests.integration.test_agent_versions import published
from tests.integration.test_conversations import playground_chat
from tests.integration.test_evaluation import add_case, evaluation_path, judge_with, start
from tests.integration.test_evaluation_settings import set_evaluation_model, set_repeats
from tests.integration.test_organisation_cost import org_cost, spent
from tests.integration.test_playground import ready_agent, three_tokens
from tests.integration.test_prices import override
from tests.integration.test_provider_credentials import ANTHROPIC_KEY, added
from tests.integration.test_version_metrics import chat, live_agent, roll_up, wordy

ZERO = Decimal(0)
# The fixed allowance of 2,000 tokens in and 200 out, at gpt-4.1-mini's prices:
# 2,000 x $0.40 / 1M + 200 x $1.60 / 1M.
ALLOWANCE_MINI = Decimal("0.00112")
NOV_5 = "2026-11-05"
# Estimates are to the billionth of a dollar.
NANO = Decimal("0.000000001")


@pytest.fixture
async def visitor(new_client: ClientFactory) -> httpx.AsyncClient:
    """A browser on someone's website: no Studio session."""
    return await new_client()


PriceTable = Callable[[list[PriceEntry]], Awaitable[None]]


@pytest.fixture
async def price_table(app: FastAPI) -> AsyncIterator[PriceTable]:
    """Loads a test's own platform price table; the repo's is reloaded afterwards."""

    async def load(entries: list[PriceEntry]) -> None:
        async with app.state.engine.begin() as connection:
            await connection.run_sync(sync_price_table, entries)

    yield load
    async with app.state.engine.begin() as connection:
        await connection.run_sync(sync_price_table)


async def estimated(
    member: SignedUpMember, project_id: str, agent_id: str, body: dict[str, Any] | None = None
) -> dict[str, Any]:
    response = await member.client.post(
        evaluation_path(member, project_id, agent_id, "estimate"), json=body
    )
    assert response.status_code == 200, response.text
    found: dict[str, Any] = response.json()
    return found


async def started(member: SignedUpMember, project_id: str, agent_id: str) -> dict[str, Any]:
    response = await start(member, project_id, agent_id)
    assert response.status_code == 202, response.text
    run: dict[str, Any] = response.json()
    return run


async def results(member: SignedUpMember, project_id: str, agent_id: str, run_id: str) -> Any:
    response = await member.client.get(
        evaluation_path(member, project_id, agent_id, "runs", run_id, "results")
    )
    assert response.status_code == 200, response.text
    return response.json()


def dollars(amounts: dict[str, Any], *keys: str) -> tuple[Decimal | None, ...]:
    return tuple(None if amounts[key] is None else Decimal(amounts[key]) for key in keys)


# The estimate


async def test_with_no_history_the_estimate_prices_the_sides_model_and_judging_by_allowance(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock
) -> None:
    judge_with(app, three_tokens)
    _, project_id, agent_id = await ready_agent(app, owner)
    await add_case(owner, project_id, agent_id)
    await add_case(owner, project_id, agent_id, "Can I carry leave over?")

    estimate = await estimated(owner, project_id, agent_id)

    # The Draft alone: 2 cases x 1 side x 3 repeats, each answer and each judgement at the
    # allowance.
    assert (estimate["cases"], estimate["sides"], estimate["repeats"]) == (2, 1, 3)
    assert dollars(estimate, "answers_usd", "judging_usd", "total_usd") == (
        6 * ALLOWANCE_MINI,
        6 * ALLOWANCE_MINI,
        12 * ALLOWANCE_MINI,
    )


async def test_the_drafts_estimate_is_its_mean_playground_cost_per_reply_over_30_days(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock
) -> None:
    judge_with(app, three_tokens)
    _, project_id, agent_id = await ready_agent(app, owner)
    await add_case(owner, project_id, agent_id)
    await set_repeats(owner, 1)
    await playground_chat(owner, project_id, agent_id, "How much leave?", "And sick days?")
    mean = await spent(owner, project_id, playground=True) / 2
    assert ZERO < mean != ALLOWANCE_MINI

    estimate = await estimated(owner, project_id, agent_id)

    assert dollars(estimate, "answers_usd", "judging_usd") == (mean.quantize(NANO), ALLOWANCE_MINI)

    # 31 days on, those replies are outside the last 30 days: back to the allowance.
    clock.advance(timedelta(days=31))
    later = await estimated(owner, project_id, agent_id)
    assert dollars(later, "answers_usd") == (ALLOWANCE_MINI,)


async def test_a_versions_estimate_is_its_mean_visitor_cost_per_reply_from_the_rollups(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent = await live_agent(app, owner)
    project_id = agent["project_id"]
    await add_case(owner, project_id, agent["id"])
    await chat(visitor, agent, "Leave? words:40", "Sick days? words:80")
    visitor_mean = await spent(owner, project_id, playground=False) / 2
    # Today's replies aren't rolled up yet: the Version has no history.
    today = await estimated(owner, project_id, agent["id"])
    clock.advance(timedelta(days=1))
    await roll_up(clock.now())

    estimate = await estimated(owner, project_id, agent["id"])

    # The Live Version against the Draft, 3 repeats; the Draft has no Playground history.
    assert (estimate["sides"], estimate["repeats"]) == (2, 3)
    assert dollars(today, "answers_usd") == (3 * 2 * ALLOWANCE_MINI,)
    assert ZERO < visitor_mean != ALLOWANCE_MINI
    assert dollars(estimate, "answers_usd", "judging_usd") == (
        (3 * (visitor_mean + ALLOWANCE_MINI)).quantize(NANO),
        3 * 2 * ALLOWANCE_MINI,
    )
    # Choosing the Version alone estimates it alone.
    alone = await estimated(
        owner,
        project_id,
        agent["id"],
        {"sides": [{"kind": "version", "version_id": agent["v1"]["id"]}]},
    )
    assert dollars(alone, "answers_usd") == ((3 * visitor_mean).quantize(NANO),)


async def test_the_estimate_is_unknown_when_a_price_is_and_is_refused_as_starting_is(
    app: FastAPI, owner: SignedUpMember, price_table: PriceTable
) -> None:
    judge_with(app, three_tokens)
    _, project_id, agent_id = await ready_agent(app, owner)
    nothing_to_run = await owner.client.post(
        evaluation_path(owner, project_id, agent_id, "estimate")
    )
    await add_case(owner, project_id, agent_id)
    await price_table([])

    estimate = await estimated(owner, project_id, agent_id)

    assert nothing_to_run.status_code == 409
    assert nothing_to_run.json()["detail"] == "Add an Evaluation Case before evaluating."
    assert dollars(estimate, "answers_usd", "judging_usd", "total_usd") == (None, None, None)
    # A Run of unpriced models spends nothing anyone can price.
    run = await started(owner, project_id, agent_id)
    assert run["cost"] == {
        "estimated_usd": None,
        "answers_usd": "0",
        "judging_usd": "0",
        "total_usd": "0",
    }


# The Run's Cost


async def test_a_run_stores_its_estimate_and_records_answers_and_judging_separately(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock
) -> None:
    judge_with(app, three_tokens)
    _, project_id, agent_id = await ready_agent(app, owner)
    await add_case(owner, project_id, agent_id)
    claude = await added(owner, provider="anthropic", api_key=ANTHROPIC_KEY, name="Claude")
    await set_evaluation_model(owner, claude["id"], "claude-sonnet-4-5")
    estimate = await estimated(owner, project_id, agent_id)

    run = await started(owner, project_id, agent_id)

    found = await results(owner, project_id, agent_id, run["id"])
    traced = sum((Decimal(r["trace"]["cost_usd"]) for r in found["cases"][0]["results"]), ZERO)
    cost = run["cost"]
    assert cost["estimated_usd"] == estimate["total_usd"]
    assert Decimal(cost["answers_usd"]) == traced > ZERO
    assert Decimal(cost["judging_usd"]) > ZERO
    assert Decimal(cost["total_usd"]) == traced + Decimal(cost["judging_usd"])
    # The history list shows each Run's Cost.
    listed = await owner.client.get(evaluation_path(owner, project_id, agent_id, "runs"))
    assert [r["cost"] for r in listed.json()] == [cost]

    # Judging is priced at the Evaluation Model's prices: free judging costs nothing.
    free = await override(owner, claude["id"], model="claude-sonnet-4-5", input=0, output=0)
    assert free.status_code == 200, free.text
    again = await started(owner, project_id, agent_id)
    assert (again["cost"]["answers_usd"], again["cost"]["judging_usd"]) == (
        cost["answers_usd"],
        "0",
    )


async def test_a_later_price_change_does_not_move_a_finished_runs_cost(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock, price_table: PriceTable
) -> None:
    d = Decimal
    rise = datetime(2026, 11, 6, tzinfo=UTC)
    await price_table(
        [
            PriceEntry(
                Provider.OPENAI, "gpt-4.1-mini", rise - timedelta(days=365), d(1), d(1), d(1)
            ),
            PriceEntry(Provider.OPENAI, "gpt-4.1-mini", rise, d(100), d(100), d(100)),
        ]
    )
    judge_with(app, three_tokens)
    _, project_id, agent_id = await ready_agent(app, owner)
    await add_case(owner, project_id, agent_id)
    first = await started(owner, project_id, agent_id)
    cost_before = await org_cost(owner, start=NOV_5, end=NOV_5)

    clock.advance(rise - clock.now() + timedelta(hours=1))
    reread = await owner.client.get(
        evaluation_path(owner, project_id, agent_id, "runs", first["id"])
    )
    cost_after = await org_cost(owner, start=NOV_5, end=NOV_5)

    assert reread.json()["cost"] == first["cost"]
    assert cost_after == cost_before
    # A Run after the rise pays the new price: a hundred times as much.
    second = await started(owner, project_id, agent_id)
    for key in ("answers_usd", "judging_usd"):
        assert Decimal(second["cost"][key]) == 100 * Decimal(first["cost"][key]) > ZERO


# Organisation cost


async def test_organisation_cost_has_an_evaluation_column_per_line_and_in_the_total(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent = await live_agent(app, owner)
    judge_with(app, wordy)
    project_id = agent["project_id"]
    await chat(visitor, agent, "Leave? words:20")
    visitor_usd = await spent(owner, project_id, playground=False)
    await add_case(owner, project_id, agent["id"])
    run = await started(owner, project_id, agent["id"])
    run_usd = Decimal(run["cost"]["total_usd"])
    # Another Agent of the Project that has only been evaluated, never asked.
    tried = (await create_automatic_agent(owner, project_id, "Tried"))["id"]
    await published(owner, project_id, tried)
    await add_case(owner, project_id, tried)
    tried_run = await started(owner, project_id, tried)
    tried_usd = Decimal(tried_run["cost"]["total_usd"])

    by_agent = await org_cost(owner, start=NOV_5, end=NOV_5, group_by="agent")
    by_project = await org_cost(owner, start=NOV_5, end=NOV_5, group_by="project")

    assert ZERO not in (visitor_usd, run_usd, tried_usd)
    lines = {
        row["agent_id"]: dollars(
            row, "visitor_usd", "playground_usd", "evaluation_usd", "total_usd"
        )
        for row in by_agent["rows"]
    }
    assert lines == {
        agent["id"]: (visitor_usd, ZERO, run_usd, visitor_usd + run_usd),
        tried: (ZERO, ZERO, tried_usd, tried_usd),
    }
    (line,) = by_project["rows"]
    everything = (visitor_usd, ZERO, run_usd + tried_usd, visitor_usd + run_usd + tried_usd)
    assert dollars(line, "visitor_usd", "playground_usd", "evaluation_usd", "total_usd") == (
        everything
    )
    assert (
        dollars(by_project["total"], "visitor_usd", "playground_usd", "evaluation_usd", "total_usd")
        == everything
    )
    # Another day's cost holds none of it.
    other_day = await org_cost(owner, start="2026-11-04", end="2026-11-04")
    assert other_day["rows"] == []
