"""API seam and task seam: the Evaluation budget (spec 15).

An Owner sets the Organisation's monthly Evaluation budget in US dollars in Organisation settings
(Models); every Member reads it with this month's spend. Without one, no Agent's Live sample rate
can be raised above 0%, and removing it stops all sampling. Each Live Verdict's Cost adds to the
month's spend; once the spend reaches the budget no more replies are sampled across the
Organisation, judgements already pending still finish, and every Owner is emailed once. Raising
the budget, or a new month (UTC), resumes sampling. Live Verdict Cost counts in Organisation
cost's Evaluation column, never in the Version KPIs' cost or the Token Budget, and Evaluation
Runs are never capped.

Replies and judging come from the fake chat model through a scripted ``FunctionModel``, as in
``test_live_verdicts``, and are priced from a test price table at $10,000 per million tokens in
and out, so one judgement costs whole dollars. Amounts are read back from each Live Verdict's
frozen Cost in its Trace.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi import FastAPI

from app.credentials.registry import Provider
from app.mail.outbox import OutboxMailer
from app.pricing.table import PriceEntry
from tests.conftest import ClientFactory, MemberFactory, SignedUpMember, TenantFactory
from tests.fakes.clock import ControllableClock
from tests.integration.test_bedrock_credentials import audit_events
from tests.integration.test_embed import settings_path
from tests.integration.test_evaluation import add_case
from tests.integration.test_evaluation_cost import PriceTable, started
from tests.integration.test_evaluation_cost import price_table as price_table
from tests.integration.test_live_verdict_context import held_back as held_back
from tests.integration.test_live_verdict_context import judge_now
from tests.integration.test_live_verdicts import (
    budgeted,
    live_agent,
    live_verdict,
    message_id,
    reply,
    scripted,
    set_rate,
    trace,
)
from tests.integration.test_organisation_cost import org_cost
from tests.integration.test_playground import ANSWER
from tests.integration.test_token_budget import usage
from tests.integration.test_version_metrics import version_kpis

CHANGED = "organisation.evaluation_budget_changed"
ZERO = Decimal(0)
# The ControllableClock starts on 5 November 2026.
NOV_5 = "2026-11-05"


@pytest.fixture(autouse=True)
def _stood_still(clock: ControllableClock) -> None:
    """Every test runs on the ControllableClock, from 5 November 2026."""


def budget_path(member: SignedUpMember) -> str:
    return f"/api/organisations/{member.organisation_id}/evaluation-budget"


async def budget(member: SignedUpMember) -> dict[str, Any]:
    response = await member.client.get(budget_path(member))
    assert response.status_code == 200, response.text
    found: dict[str, Any] = response.json()
    return found


@pytest.fixture
async def dear(price_table: PriceTable) -> None:
    """Prices gpt-4.1-mini at $10,000 per million tokens: a cent a token."""
    since = datetime(2020, 1, 1, tzinfo=UTC)
    d = Decimal(10_000)
    await price_table([PriceEntry(Provider.OPENAI, "gpt-4.1-mini", since, d, d, d)])


async def judged_cost(owner: SignedUpMember, agent: dict[str, Any], replied: str) -> Decimal:
    verdict = (await trace(owner, agent, replied))["live_verdict"]
    assert verdict is not None
    assert verdict["status"] == "judged"
    return Decimal(verdict["cost_usd"])


async def sampled_agent(app: FastAPI, owner: SignedUpMember, limit: str) -> dict[str, Any]:
    """A Live Agent sampling every reply, under an Evaluation budget of ``limit`` dollars."""
    scripted(app)
    agent = await live_agent(app, owner)
    assert (await budgeted(owner, limit)).status_code == 200
    assert (await set_rate(owner, agent, 100)).status_code == 200
    return agent


def emails_about_the_budget(outbox: OutboxMailer) -> list[str]:
    return [e.to for e in outbox.sent if "Evaluation budget" in e.subject]


# Setting it


async def test_there_is_no_budget_by_default_and_every_member_reads_the_meter(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")

    assert await budget(editor) == {
        "evaluation_budget_usd": None,
        "month": "2026-11-01",
        "spent_usd": "0",
        "exhausted": False,
        "resets_at": "2026-12-01T00:00:00Z",
    }


async def test_owners_set_and_remove_the_budget_audited_with_before_and_after(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")

    refused = await budgeted(editor, "50")
    assert refused.status_code == 403, refused.text
    set_to = await budgeted(owner, "50")
    assert set_to.status_code == 200, set_to.text
    assert set_to.json()["evaluation_budget_usd"] == "50.00"
    assert (await budget(editor))["evaluation_budget_usd"] == "50.00"
    # Setting what is already in force records nothing.
    assert (await budgeted(owner, "50.00")).status_code == 200
    removed = await budgeted(owner, None)
    assert removed.status_code == 200, removed.text
    assert removed.json()["evaluation_budget_usd"] is None

    later, earlier = await audit_events(owner, CHANGED)
    assert earlier["actor"]["id"] == owner.member_id
    assert earlier["target"] == {"type": "organisation", "id": owner.organisation_id}
    assert (earlier["before"], earlier["after"]) == (
        {"evaluation_budget_usd": None},
        {"evaluation_budget_usd": "50.00"},
    )
    assert (later["before"], later["after"]) == (
        {"evaluation_budget_usd": "50.00"},
        {"evaluation_budget_usd": None},
    )


@pytest.mark.parametrize("amount", ["0", "-5", "12.345", "half", 1_000_001])
async def test_the_budget_is_dollars_and_cents_above_zero(
    owner: SignedUpMember, amount: Any
) -> None:
    response = await budgeted(owner, amount)

    assert response.status_code == 422, response.text
    assert (await budget(owner))["evaluation_budget_usd"] is None


async def test_another_organisations_budget_is_unreachable(
    owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    await budgeted(owner, "50")
    stranger = await tenant_factory()

    path = budget_path(owner)
    assert (await stranger.client.get(path)).status_code == 404
    put = await stranger.client.put(path, json={"evaluation_budget_usd": "1"})
    assert put.status_code == 404
    assert (await budget(stranger))["evaluation_budget_usd"] is None
    assert (await budget(owner))["evaluation_budget_usd"] == "50.00"


# Without a budget


async def test_a_live_sample_rate_above_zero_is_refused_with_a_typed_error_without_a_budget(
    app: FastAPI, owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    scripted(app)
    agent = await live_agent(app, owner)
    editor = await member_factory(owner, "editor")

    refused = await set_rate(editor, agent, 10)

    assert refused.status_code == 422, refused.text
    (error,) = refused.json()["detail"]
    assert error["type"] == "evaluation_budget_required"
    assert error["loc"] == ["body", "live_sample_rate"]
    assert "Evaluation budget" in error["msg"]
    path = settings_path(owner, agent["project_id"], agent["id"])
    assert (await owner.client.get(path)).json()["live_sample_rate"] == 0
    # Turning sampling off needs no budget.
    assert (await set_rate(editor, agent, 0)).status_code == 200


async def test_removing_the_budget_keeps_rates_but_stops_all_sampling(
    app: FastAPI, owner: SignedUpMember, new_client: ClientFactory
) -> None:
    agent = await sampled_agent(app, owner, "100")
    assert await live_verdict(owner, agent, await reply(await new_client(), agent)) is not None

    assert (await budgeted(owner, None)).status_code == 200
    events = await reply(await new_client(), agent)

    assert await live_verdict(owner, agent, events) is None
    assert "".join(d["text"] for e, d in events if e == "token") == ANSWER
    path = settings_path(owner, agent["project_id"], agent["id"])
    assert (await owner.client.get(path)).json()["live_sample_rate"] == 100


# Spend


@pytest.mark.usefixtures("dear")
async def test_each_live_verdicts_cost_adds_to_the_months_spend(
    app: FastAPI, owner: SignedUpMember, new_client: ClientFactory
) -> None:
    agent = await sampled_agent(app, owner, "1000000")

    first = await reply(await new_client(), agent)
    second = await reply(await new_client(), agent)

    costs = [await judged_cost(owner, agent, message_id(e)) for e in (first, second)]
    meter = await budget(owner)
    assert ZERO not in costs
    assert Decimal(meter["spent_usd"]) == sum(costs, ZERO)
    assert meter["exhausted"] is False


@pytest.mark.usefixtures("dear")
async def test_reaching_the_budget_stops_sampling_and_emails_every_owner_once(
    app: FastAPI,
    owner: SignedUpMember,
    member_factory: MemberFactory,
    new_client: ClientFactory,
    outbox: OutboxMailer,
) -> None:
    second_owner = await member_factory(owner, "owner")
    await member_factory(owner, "editor")
    agent = await sampled_agent(app, owner, "0.01")

    first = await reply(await new_client(), agent)
    after = await reply(await new_client(), agent)

    # The first judgement takes the spend past the budget.
    spend = await judged_cost(owner, agent, message_id(first))
    meter = await budget(owner)
    assert (Decimal(meter["spent_usd"]), meter["exhausted"]) == (spend, True)
    # No reply is sampled once the budget is spent, and the Visitor's reply is unchanged.
    assert await live_verdict(owner, agent, after) is None
    assert "".join(d["text"] for e, d in after if e == "token") == ANSWER
    assert sorted(emails_about_the_budget(outbox)) == sorted([owner.email, second_owner.email])
    (email, *_) = [e for e in outbox.sent if e.to == owner.email and "budget" in e.subject]
    assert "$0.01" in email.text
    assert f"/organisations/{owner.organisation_id}/settings/models" in email.text


@pytest.mark.usefixtures("dear")
async def test_judgements_pending_when_the_budget_is_reached_still_finish_with_one_email(
    app: FastAPI,
    owner: SignedUpMember,
    new_client: ClientFactory,
    outbox: OutboxMailer,
    held_back: list[uuid.UUID],
) -> None:
    agent = await sampled_agent(app, owner, "0.01")
    first = await reply(await new_client(), agent)
    second = await reply(await new_client(), agent)
    assert len(held_back) == 2

    for verdict_id in held_back:
        await judge_now(verdict_id)

    costs = [await judged_cost(owner, agent, message_id(e)) for e in (first, second)]
    # The overshoot is the in-flight judgement's Cost.
    assert Decimal((await budget(owner))["spent_usd"]) == sum(costs, ZERO)
    assert emails_about_the_budget(outbox) == [owner.email]
    third = await reply(await new_client(), agent)
    assert len(held_back) == 2
    assert await live_verdict(owner, agent, third) is None


@pytest.mark.usefixtures("dear")
async def test_raising_the_budget_resumes_sampling_at_the_next_reply(
    app: FastAPI, owner: SignedUpMember, new_client: ClientFactory, outbox: OutboxMailer
) -> None:
    agent = await sampled_agent(app, owner, "0.01")
    await reply(await new_client(), agent)
    assert (await budget(owner))["exhausted"] is True

    assert (await budgeted(owner, "1000000")).status_code == 200
    resumed = await reply(await new_client(), agent)

    assert await live_verdict(owner, agent, resumed) is not None
    assert (await budget(owner))["exhausted"] is False
    assert len(emails_about_the_budget(outbox)) == 1


@pytest.mark.usefixtures("dear")
async def test_a_new_month_starts_a_new_record_so_sampling_resumes_on_the_first(
    app: FastAPI,
    owner: SignedUpMember,
    new_client: ClientFactory,
    outbox: OutboxMailer,
    clock: ControllableClock,
) -> None:
    agent = await sampled_agent(app, owner, "0.01")
    await reply(await new_client(), agent)
    assert await live_verdict(owner, agent, await reply(await new_client(), agent)) is None

    clock.advance(datetime(2026, 12, 1, 0, 0, 1, tzinfo=UTC) - clock.now())
    meter = await budget(owner)
    assert (meter["month"], meter["spent_usd"], meter["exhausted"]) == ("2026-12-01", "0", False)
    december = await reply(await new_client(), agent)

    assert await live_verdict(owner, agent, december) is not None
    assert (await budget(owner))["exhausted"] is True
    # The new month's spend reaching the budget emails the Owner again, once.
    assert emails_about_the_budget(outbox) == [owner.email, owner.email]


# Where the Cost counts


@pytest.mark.usefixtures("dear")
async def test_live_verdict_cost_counts_in_the_evaluation_column_on_the_day_it_was_judged(
    app: FastAPI, owner: SignedUpMember, new_client: ClientFactory
) -> None:
    agent = await sampled_agent(app, owner, "1000000")
    assert (await set_rate(owner, agent, 0)).status_code == 200
    unsampled = await reply(await new_client(), agent)
    tokens_unsampled = (await usage(owner, agent))["tokens_used"]
    kpis_before = await version_kpis(owner, agent, agent["version"])
    assert (await set_rate(owner, agent, 100)).status_code == 200

    sampled = await reply(await new_client(), agent)

    judging = await judged_cost(owner, agent, message_id(sampled))
    replies = sum(
        [
            Decimal((await trace(owner, agent, message_id(e)))["cost_usd"])
            for e in (unsampled, sampled)
        ],
        ZERO,
    )
    by_agent = await org_cost(owner, start=NOV_5, end=NOV_5, group_by="agent")
    (line,) = by_agent["rows"]
    assert Decimal(line["evaluation_usd"]) == judging > ZERO
    assert Decimal(line["visitor_usd"]) == replies
    assert (await org_cost(owner, start="2026-11-04", end="2026-11-04"))["rows"] == []
    # Never in the Token Budget: the sampled reply counts only its own tokens, as the first did.
    assert (await usage(owner, agent))["tokens_used"] == 2 * tokens_unsampled
    # Never in the Version KPIs' cost: it doubles with the second reply, judging aside.
    kpis = await version_kpis(owner, agent, agent["version"])
    assert Decimal(kpis["cost"]["total_usd"]) == replies
    assert Decimal(kpis_before["cost"]["total_usd"]) * 2 == replies


@pytest.mark.usefixtures("dear")
async def test_evaluation_runs_are_never_capped_by_the_budget(
    app: FastAPI, owner: SignedUpMember, new_client: ClientFactory
) -> None:
    agent = await sampled_agent(app, owner, "0.01")
    await reply(await new_client(), agent)
    meter = await budget(owner)
    assert meter["exhausted"] is True
    await add_case(owner, agent["project_id"], agent["id"])

    run = await started(owner, agent["project_id"], agent["id"])

    found = await owner.client.get(
        f"/api/organisations/{owner.organisation_id}/projects/{agent['project_id']}/agents/"
        f"{agent['id']}/evaluation/runs/{run['id']}"
    )
    assert found.status_code == 200, found.text
    assert found.json()["status"] == "completed"
    assert Decimal(found.json()["cost"]["judging_usd"]) > ZERO
    # A Run's Cost doesn't add to the Evaluation budget's spend.
    assert await budget(owner) == meter


async def test_a_judgement_counts_in_the_month_it_was_judged(
    app: FastAPI, owner: SignedUpMember, new_client: ClientFactory, clock: ControllableClock
) -> None:
    agent = await sampled_agent(app, owner, "100")
    clock.advance(datetime(2026, 11, 30, 23, 59, tzinfo=UTC) - clock.now())
    november = await reply(await new_client(), agent)
    spent = await judged_cost(owner, agent, message_id(november))

    assert Decimal((await budget(owner))["spent_usd"]) == spent > ZERO
    clock.advance(timedelta(minutes=2))
    assert (await budget(owner))["spent_usd"] == "0"
