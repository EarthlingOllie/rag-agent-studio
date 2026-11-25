"""API and task seams: a Suggestion run's dialog reads, Cost and lifecycle (spec 16, ticket 16-04).

Before starting, the run dialog reads how much evidence a range holds, by kind and without the
cap, with a warning below 10 pieces, and the estimated Cost: proposing at the Evaluation Model's
prices for a fixed allowance per piece of evidence plus an output allowance, and, when the Agent
has an Evaluation Set, checking from spec 14's estimator for two sides. Both are stored on the
Suggestion, and the actual proposing Cost is frozen as it is spent and counted in Organisation
cost's Evaluation column; the Evaluation budget never applies.

A run moves through ``queued``, ``gathering``, ``proposing`` (and ``checking``) to
``completed``; an Editor can cancel it, and it stops between phases keeping what it spent. An
Agent has at most one Suggestion run in progress, and Suggestion runs and Evaluation Runs never
overlap, each refused with a typed conflict.

Expected amounts are hand-worked from the repo's price table: ``gpt-4.1-mini`` is $0.40 in and
$1.60 out per million tokens.
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo
from pydantic_ai.usage import RequestUsage
from sqlalchemy import func, select

from app.core.db import create_engine, create_sessionmaker
from app.core.settings import load_settings
from app.evaluation import api as evaluation_api
from app.evaluation.failed_cases import failed_cases
from app.suggestions import api as suggestions_api
from app.suggestions import service
from app.suggestions.models import Suggestion
from app.suggestions.tasks import enqueue_suggestion
from app.tenancy.models import Role
from app.tenancy.repository import OrganisationScope
from tests.agents import AUTOMATIC, save_draft
from tests.conftest import ClientFactory, MemberFactory, SignedUpMember
from tests.fakes.clock import ControllableClock
from tests.integration.test_agent_archive import archive, delete_permanently
from tests.integration.test_evaluation import add_case, evaluation_path
from tests.integration.test_evaluation_budget import budget
from tests.integration.test_evaluation_cost import PriceTable
from tests.integration.test_evaluation_cost import price_table as price_table
from tests.integration.test_evaluation_settings import set_repeats
from tests.integration.test_live_verdicts import served
from tests.integration.test_organisation_cost import org_cost
from tests.integration.test_playground import delete_credential_row, ready_agent, three_tokens
from tests.integration.test_provider_credentials import ANTHROPIC_KEY, added
from tests.integration.test_suggestion_evidence import Chat
from tests.integration.test_suggestions import (
    live_agent,
    replied,
    scripted,
    start,
    started,
    suggestions_path,
)

ZERO = Decimal(0)
NOV_5 = "2026-11-05"


@pytest.fixture
async def visitor(new_client: ClientFactory) -> httpx.AsyncClient:
    """A browser on someone's website: no Studio session."""
    return await new_client()


@pytest.fixture
def unsent(monkeypatch: pytest.MonkeyPatch) -> list[uuid.UUID]:
    """Suggestion runs stay queued: their task isn't sent. Yields the runs that would have
    been."""
    sent: list[uuid.UUID] = []

    async def enqueue(suggestion_id: uuid.UUID) -> None:
        sent.append(suggestion_id)

    monkeypatch.setattr(suggestions_api, "enqueue_suggestion", enqueue)
    return sent


async def evidence_count(
    member: SignedUpMember, agent: dict[str, Any], **params: str
) -> httpx.Response:
    return await member.client.get(suggestions_path(member, agent, "evidence"), params=params)


async def estimate(member: SignedUpMember, agent: dict[str, Any], **body: str) -> httpx.Response:
    return await member.client.post(suggestions_path(member, agent, "estimate"), json=body)


async def cancel(
    member: SignedUpMember, agent: dict[str, Any], suggestion_id: str
) -> httpx.Response:
    return await member.client.post(suggestions_path(member, agent, suggestion_id, "cancel"))


async def read(member: SignedUpMember, agent: dict[str, Any], suggestion_id: str) -> dict[str, Any]:
    response = await member.client.get(suggestions_path(member, agent, suggestion_id))
    assert response.status_code == 200, response.text
    found: dict[str, Any] = response.json()
    return found


def dollars(value: str | None) -> Decimal | None:
    return None if value is None else Decimal(value)


def with_usage(
    changes: list[dict[str, Any]], input_tokens: int, output_tokens: int
) -> Callable[[list[ModelMessage], AgentInfo], ModelResponse]:
    """A proposer giving ``changes`` and reporting exactly the tokens it used."""

    def propose(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        output = {"changes": changes, "overall_explanation": "Scripted."}
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, output)],
            usage=RequestUsage(input_tokens=input_tokens, output_tokens=output_tokens),
        )

    return propose


PROMPT_CHANGE = {
    "path": "behaviour.system_prompt",
    "value": "Answer HR questions kindly. Always cite the passage you used.",
    "explanation": "Replies cited nothing.",
    "evidence": ["E1"],
}


def scope_of(member: SignedUpMember) -> OrganisationScope:
    return OrganisationScope(
        uuid.UUID(member.organisation_id), uuid.UUID(member.member_id), Role.EDITOR
    )


async def in_new_session(work: Callable[[Any], Awaitable[Any]]) -> Any:
    """Runs ``work`` with a session of its own, as another request or the job would."""
    engine = create_engine(load_settings())
    try:
        async with create_sessionmaker(engine)() as session:
            return await work(session)
    finally:
        await engine.dispose()


# The run dialog: evidence counts and the estimate


async def test_the_evidence_count_is_by_kind_without_the_cap_and_warns_below_ten(
    app: FastAPI,
    owner: SignedUpMember,
    member_factory: MemberFactory,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    scripted(app)
    agent = await live_agent(app, owner)
    # Fails its Live Verdict and has a thumbs-down: one piece of two kinds.
    chat = await Chat.opened(visitor, agent)
    await chat.thumbs(await chat.ask("How much annual leave do I get?"), "down")
    await chat.rate(2)
    clock.advance(timedelta(minutes=1))
    await replied(visitor, agent)
    editor = await member_factory(owner, "editor")

    response = await evidence_count(editor, agent)

    assert response.status_code == 200, response.text
    today = clock.now().date()
    assert response.json() == {
        "range_start": str(today - timedelta(days=13)),
        "range_end": str(today),
        "total": 2,
        "live_verdict": 2,
        "thumbs_down": 1,
        "low_rating": 1,
        "evaluation_case": 0,
        "likely_noise": True,
    }
    # A range that holds none of it.
    earlier = await evidence_count(owner, agent, range_start="2026-10-01", range_end="2026-10-02")
    assert earlier.json()["total"] == 0


async def test_ten_pieces_of_evidence_or_more_are_not_noise_and_the_count_is_not_capped(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(service, "EVIDENCE_MAX", 3)
    scripted(app)
    agent = await live_agent(app, owner)
    for _ in range(10):
        clock.advance(timedelta(minutes=1))
        await replied(visitor, agent)

    counted = (await evidence_count(owner, agent)).json()
    estimated = (await estimate(owner, agent)).json()

    assert (counted["total"], counted["live_verdict"], counted["likely_noise"]) == (10, 10, False)
    # The estimate prices only the evidence a run would use.
    assert estimated["evidence"]["total"] == 10
    assert estimated["evidence_used"] == 3


async def test_the_estimate_prices_proposing_per_piece_of_evidence_and_checking_for_two_sides(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    scripted(app)
    agent = await live_agent(app, owner)
    await replied(visitor, agent)
    clock.advance(timedelta(minutes=1))
    await replied(visitor, agent)

    without_set = await estimate(owner, agent)

    assert without_set.status_code == 200, without_set.text
    body = without_set.json()
    # 2 pieces x 1,500 tokens in, and 1,000 out: 3,000 x $0.40 / 1M + 1,000 x $1.60 / 1M.
    assert dollars(body["proposing_usd"]) == Decimal("0.0028")
    # No Evaluation Set: no check, so nothing to price.
    assert (body["has_evaluation_set"], body["checking_usd"]) == (False, None)
    assert dollars(body["total_usd"]) == Decimal("0.0028")

    await set_repeats(owner, 1)
    await add_case(owner, agent["project_id"], agent["id"], "How much leave?")
    with_set = (await estimate(owner, agent)).json()

    # One case, one repeat, two sides of the Live Version's model with no history, each answer
    # and judgement at spec 14's allowance of 2,000 in and 200 out ($0.00112).
    assert with_set["has_evaluation_set"] is True
    assert dollars(with_set["checking_usd"]) == Decimal("0.00448")
    assert dollars(with_set["total_usd"]) == Decimal("0.00728")

    # Both are stored on the Suggestion.
    suggestion = await started(owner, agent)
    assert dollars(suggestion["cost"]["estimated_proposing_usd"]) == Decimal("0.0028")
    assert dollars(suggestion["cost"]["estimated_checking_usd"]) == Decimal("0.00448")
    listed = (await owner.client.get(suggestions_path(owner, agent))).json()
    assert listed[0]["cost"] == suggestion["cost"]


async def test_with_no_evidence_proposing_is_estimated_at_nothing(
    app: FastAPI, owner: SignedUpMember
) -> None:
    scripted(app)
    agent = await live_agent(app, owner)

    body = (await estimate(owner, agent)).json()

    assert (body["evidence"]["total"], body["evidence_used"]) == (0, 0)
    assert dollars(body["proposing_usd"]) == ZERO


async def test_with_unknown_prices_the_estimate_and_the_spend_are_unknown(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, price_table: PriceTable
) -> None:
    scripted(app, proposer=with_usage([PROMPT_CHANGE], 1_000, 100))
    agent = await live_agent(app, owner)
    await replied(visitor, agent)
    await add_case(owner, agent["project_id"], agent["id"], "How much leave?")
    await price_table([])

    body = (await estimate(owner, agent)).json()

    assert dollars(body["proposing_usd"]) is None
    assert (body["has_evaluation_set"], body["checking_usd"], body["total_usd"]) == (
        True,
        None,
        None,
    )
    suggestion = await started(owner, agent)
    assert suggestion["status"] == "completed"
    assert suggestion["cost"] == {
        "estimated_proposing_usd": None,
        "estimated_checking_usd": None,
        "proposing_usd": None,
        # The check ran, but no price it needed was known.
        "checking_usd": None,
    }


async def test_a_check_whose_model_is_gone_cannot_be_priced(
    app: FastAPI, owner: SignedUpMember
) -> None:
    scripted(app)
    _, project_id, agent_id = await ready_agent(app, owner)
    credential = await added(owner, provider="anthropic", api_key=ANTHROPIC_KEY, name="Claude")
    override = {"credential_id": credential["id"], "model": "claude-haiku-4-5"}
    draft = {"retrieval": AUTOMATIC, "behaviour": {"model": override}}
    assert (await save_draft(owner, project_id, agent_id, draft)).status_code == 200
    agent = await served(owner, project_id, agent_id)
    await add_case(owner, project_id, agent_id, "How much leave?")
    # The Live Version's own Provider Credential is gone, so its answers can't be priced.
    await delete_credential_row(app, credential["id"])

    body = (await estimate(owner, agent)).json()

    assert dollars(body["proposing_usd"]) == ZERO
    assert (body["has_evaluation_set"], body["checking_usd"], body["total_usd"]) == (
        True,
        None,
        None,
    )


async def test_the_dialog_reads_are_refused_as_starting_is(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    scripted(app)
    _, project_id, agent_id = await ready_agent(app, owner)
    unpublished = {"project_id": project_id, "id": agent_id}
    backwards = {"range_start": "2026-11-05", "range_end": "2026-11-04"}

    for response in (await evidence_count(owner, unpublished), await estimate(owner, unpublished)):
        assert response.status_code == 409, response.text
        assert "never been Published" in response.json()["detail"]
    agent = await live_agent(app, owner)
    assert (await evidence_count(owner, agent, **backwards)).status_code == 422
    assert (await estimate(owner, agent, **backwards)).status_code == 422
    unknown = {**agent, "id": "00000000-0000-4000-8000-000000000000"}
    assert (await evidence_count(owner, unknown)).status_code == 404
    assert (await estimate(owner, unknown)).status_code == 404
    assert (await archive(owner, agent["project_id"], agent["id"])).status_code == 200
    assert (await evidence_count(owner, agent)).status_code == 409
    assert (await estimate(owner, agent)).status_code == 409


# Actual Cost


async def test_proposing_cost_is_frozen_on_the_suggestion_and_counted_in_organisation_cost(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    scripted(app, proposer=with_usage([PROMPT_CHANGE], 1_000, 100))
    agent = await live_agent(app, owner)
    await replied(visitor, agent)
    # Live Verdicts are judged as replies are given; their Cost is the Evaluation column's
    # already, and the budget's spend.
    before = await org_cost(owner, start=NOV_5, end=NOV_5, group_by="agent")
    (line,) = before["rows"]
    spent_before = (await budget(owner))["spent_usd"]

    suggestion = await started(owner, agent)

    # 1,000 x $0.40 / 1M + 100 x $1.60 / 1M.
    proposing = Decimal("0.00056")
    assert dollars(suggestion["cost"]["proposing_usd"]) == proposing
    after = await org_cost(owner, start=NOV_5, end=NOV_5, group_by="agent")
    (counted,) = after["rows"]
    assert Decimal(counted["evaluation_usd"]) == Decimal(line["evaluation_usd"]) + proposing
    assert Decimal(counted["total_usd"]) == Decimal(line["total_usd"]) + proposing
    # Another day's cost holds none of it.
    assert (await org_cost(owner, start="2026-11-04", end="2026-11-04"))["rows"] == []
    # The Evaluation budget never applies: its spend is the Live Verdicts' alone.
    assert (await budget(owner))["spent_usd"] == spent_before


async def test_a_run_starts_with_the_evaluation_budget_spent(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    scripted(app, proposer=with_usage([PROMPT_CHANGE], 1_000, 100))
    agent = await live_agent(app, owner)
    await replied(visitor, agent)
    # A budget of a cent, which the Live Verdict's judging has taken.
    response = await owner.client.put(
        f"/api/organisations/{owner.organisation_id}/evaluation-budget",
        json={"evaluation_budget_usd": "0.01"},
    )
    assert response.status_code == 200, response.text

    suggestion = await started(owner, agent)

    assert (suggestion["status"], suggestion["outcome"]) == ("completed", "changes")


async def test_a_failed_proposing_call_costs_nothing(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    def broken(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"nonsense": 1})])

    scripted(app, proposer=broken)
    agent = await live_agent(app, owner)
    await replied(visitor, agent)

    suggestion = await started(owner, agent)

    assert suggestion["status"] == "failed"
    assert suggestion["cost"]["proposing_usd"] is None


# Status and cancelling


async def test_a_run_is_queued_then_gathers_proposes_and_completes(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, unsent: list[uuid.UUID]
) -> None:
    seen: list[str] = []
    agent: dict[str, Any] = {}

    async def watching(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        async def status(session: Any) -> str:
            found = await service.list_suggestions(
                session, scope_of(owner), uuid.UUID(agent["project_id"]), uuid.UUID(agent["id"])
            )
            return found[0][0].status

        seen.append(await in_new_session(status))
        return with_usage([PROMPT_CHANGE], 10, 10)(messages, info)

    scripted(app, proposer=watching)
    agent.update(await live_agent(app, owner))
    await replied(visitor, agent)

    queued = await started(owner, agent)

    assert queued["status"] == "queued"
    (suggestion_id,) = unsent
    await enqueue_suggestion(suggestion_id)
    assert seen == ["proposing"]
    assert (await read(owner, agent, queued["id"]))["status"] == "completed"


async def test_a_queued_run_cancelled_never_gathers_or_proposes(
    app: FastAPI,
    owner: SignedUpMember,
    member_factory: MemberFactory,
    visitor: httpx.AsyncClient,
    unsent: list[uuid.UUID],
) -> None:
    proposing = scripted(app)
    agent = await live_agent(app, owner)
    await replied(visitor, agent)
    queued = await started(owner, agent)
    editor = await member_factory(owner, "editor")

    cancelled = await cancel(editor, agent, queued["id"])

    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["finished_at"] is not None
    # Its task, sent before it was cancelled, does nothing.
    await enqueue_suggestion(unsent[0])
    found = await read(owner, agent, queued["id"])
    assert (found["status"], found["evidence"], found["outcome"]) == ("cancelled", [], None)
    assert proposing == []
    # Cancelled, it is no longer in progress: another run can start.
    assert (await start(owner, agent)).status_code == 202


async def test_a_run_cancelled_while_proposing_stops_and_keeps_what_it_spent(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent: dict[str, Any] = {}

    async def cancelling(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        async def cancel_it(session: Any) -> None:
            scope = scope_of(owner)
            project_id, agent_id = uuid.UUID(agent["project_id"]), uuid.UUID(agent["id"])
            ((found, *_),) = await service.list_suggestions(session, scope, project_id, agent_id)
            await service.cancel_suggestion(
                session, scope, project_id, agent_id, found.id, now=clock.now()
            )

        await in_new_session(cancel_it)
        return with_usage([PROMPT_CHANGE], 1_000, 100)(messages, info)

    scripted(app, proposer=cancelling)
    agent.update(await live_agent(app, owner))
    await replied(visitor, agent)

    suggestion = await started(owner, agent)

    assert suggestion["status"] == "cancelled"
    # What it proposed is not kept, but what it spent is.
    assert (suggestion["changes"], suggestion["outcome"]) == ([], None)
    assert dollars(suggestion["cost"]["proposing_usd"]) == Decimal("0.00056")
    assert len(suggestion["evidence"]) == 1
    (line,) = (await org_cost(owner, start=NOV_5, end=NOV_5, group_by="agent"))["rows"]
    assert Decimal(line["evaluation_usd"]) >= Decimal("0.00056")


async def test_a_run_cancelled_while_proposing_stays_cancelled_when_the_call_then_fails(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent: dict[str, Any] = {}

    async def cancelling(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        async def cancel_it(session: Any) -> None:
            scope = scope_of(owner)
            project_id, agent_id = uuid.UUID(agent["project_id"]), uuid.UUID(agent["id"])
            ((found, *_),) = await service.list_suggestions(session, scope, project_id, agent_id)
            await service.cancel_suggestion(
                session, scope, project_id, agent_id, found.id, now=clock.now()
            )

        # The invalid output is retried: only the first call cancels.
        if not agent.get("cancelled"):
            agent["cancelled"] = True
            await in_new_session(cancel_it)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"nonsense": 1})])

    scripted(app, proposer=cancelling)
    agent.update(await live_agent(app, owner))
    await replied(visitor, agent)

    suggestion = await started(owner, agent)

    assert (suggestion["status"], suggestion["error_message"]) == ("cancelled", None)


async def test_a_run_cancelled_while_gathering_never_proposes(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    clock: ControllableClock,
) -> None:
    proposing = scripted(app)
    agent = await live_agent(app, owner)
    await replied(visitor, agent)
    gather = failed_cases

    async def cancelling(*args: Any) -> Any:
        async def cancel_it(session: Any) -> None:
            scope = scope_of(owner)
            project_id, agent_id = uuid.UUID(agent["project_id"]), uuid.UUID(agent["id"])
            listed = await service.list_suggestions(session, scope, project_id, agent_id)
            # Starting reads the evidence too, to estimate; only the job's gathering cancels.
            for found, *_ in listed:
                await service.cancel_suggestion(
                    session, scope, project_id, agent_id, found.id, now=clock.now()
                )

        found = await gather(*args)
        await in_new_session(cancel_it)
        return found

    monkeypatch.setattr("app.suggestions.service.failed_cases", cancelling)

    suggestion = await started(owner, agent)

    assert (suggestion["status"], suggestion["outcome"]) == ("cancelled", None)
    assert proposing == []
    assert suggestion["cost"]["proposing_usd"] is None


async def test_a_finished_or_unknown_run_cannot_be_cancelled(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    scripted(app)
    agent = await live_agent(app, owner)
    await replied(visitor, agent)
    suggestion = await started(owner, agent)

    refused = await cancel(owner, agent, suggestion["id"])

    assert (refused.status_code, refused.json()) == (
        409,
        {"detail": suggestions_api.SUGGESTION_FINISHED},
    )
    assert (await cancel(owner, agent, str(uuid.uuid4()))).status_code == 404


# One run at a time


async def test_an_agent_has_one_suggestion_run_in_progress_with_a_typed_conflict(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, unsent: list[uuid.UUID]
) -> None:
    scripted(app)
    agent = await live_agent(app, owner)
    await replied(visitor, agent)
    await started(owner, agent)

    again = await start(owner, agent)

    assert (again.status_code, again.json()) == (
        409,
        {
            "detail": suggestions_api.SUGGESTION_IN_PROGRESS,
            "conflict": "suggestion_run_in_progress",
        },
    )
    # The dialog's reads still answer.
    assert (await evidence_count(owner, agent)).status_code == 200
    assert (await estimate(owner, agent)).status_code == 200
    # Another Agent's runs are its own.
    other = await live_agent(app, owner)
    assert (await start(owner, other)).status_code == 202


async def test_evaluate_is_refused_while_a_suggestion_run_is_in_progress(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, unsent: list[uuid.UUID]
) -> None:
    scripted(app, three_tokens)
    agent = await live_agent(app, owner)
    await add_case(owner, agent["project_id"], agent["id"], "How much leave?")
    queued = await started(owner, agent)

    refused = await owner.client.post(
        evaluation_path(owner, agent["project_id"], agent["id"], "runs")
    )

    assert (refused.status_code, refused.json()) == (
        409,
        {
            "detail": evaluation_api.SUGGESTION_RUN_IN_PROGRESS,
            "conflict": "suggestion_run_in_progress",
        },
    )
    assert (await cancel(owner, agent, queued["id"])).status_code == 200
    allowed = await owner.client.post(
        evaluation_path(owner, agent["project_id"], agent["id"], "runs")
    )
    assert allowed.status_code == 202, allowed.text


async def test_a_suggestion_run_is_refused_while_an_evaluation_run_is_in_progress(
    app: FastAPI, owner: SignedUpMember, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def enqueue(run_id: uuid.UUID) -> None:
        """Evaluation Runs stay queued."""

    monkeypatch.setattr(evaluation_api, "enqueue_run", enqueue)
    scripted(app, three_tokens)
    agent = await live_agent(app, owner)
    await add_case(owner, agent["project_id"], agent["id"], "How much leave?")
    run = await owner.client.post(evaluation_path(owner, agent["project_id"], agent["id"], "runs"))
    assert run.status_code == 202, run.text
    # Evaluation Runs keep their plain conflict with each other.
    again = await owner.client.post(
        evaluation_path(owner, agent["project_id"], agent["id"], "runs")
    )
    assert again.json() == {
        "detail": evaluation_api.RUN_IN_PROGRESS,
        "conflict": "evaluation_run_in_progress",
    }

    refused = await start(owner, agent)

    assert (refused.status_code, refused.json()) == (
        409,
        {
            "detail": suggestions_api.EVALUATION_RUN_IN_PROGRESS,
            "conflict": "evaluation_run_in_progress",
        },
    )
    assert (await owner.client.get(suggestions_path(owner, agent))).json() == []


# Archived and deleted Agents


async def test_permanent_deletion_of_an_agent_removes_its_suggestions(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    scripted(app)
    agent = await live_agent(app, owner)
    await replied(visitor, agent)
    suggestion = await started(owner, agent)
    assert suggestion["evidence"]
    name = (
        await owner.client.get(
            f"/api/organisations/{owner.organisation_id}/projects/{agent['project_id']}"
            f"/agents/{agent['id']}"
        )
    ).json()["name"]
    assert (await archive(owner, agent["project_id"], agent["id"])).status_code == 200

    deleted = await delete_permanently(owner, agent["project_id"], agent["id"], name)

    assert deleted.status_code == 204, deleted.text
    assert (await owner.client.get(suggestions_path(owner, agent))).status_code == 404

    async def remaining(session: Any) -> int:
        return int(
            await session.scalar(
                select(func.count())
                .select_from(Suggestion)
                .where(Suggestion.agent_id == uuid.UUID(agent["id"]))
            )
        )

    assert await in_new_session(remaining) == 0


async def test_an_archived_agents_run_cannot_be_cancelled_once_finished_but_reads(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, unsent: list[uuid.UUID]
) -> None:
    scripted(app)
    agent = await live_agent(app, owner)
    await replied(visitor, agent)
    queued = await started(owner, agent)
    assert (await archive(owner, agent["project_id"], agent["id"])).status_code == 200

    # A run in progress when its Agent is archived can still be stopped.
    cancelled = await cancel(owner, agent, queued["id"])

    assert cancelled.status_code == 200, cancelled.text
    assert (await read(owner, agent, queued["id"]))["status"] == "cancelled"
