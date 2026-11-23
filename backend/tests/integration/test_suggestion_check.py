"""API and task seams: the check against the Evaluation Set (spec 16, ticket 16-05).

When a Suggestion changes the configuration and the Agent has an Evaluation Set, the Suggestion
run starts a spec 14 Evaluation Run of kind ``suggestion``: its first side is the Live Version
and its second a ``suggestion`` side, the Live Version's AgentConfig with the suggested changes,
answering with the Live Version's pinned Instructions. The Suggestion links the Run and shows
both Evaluation scores and each Regression with its Verdicts' reasons; a failed check is only a
warning. Its checking Cost is frozen beside its proposing Cost. Without an Evaluation Set the
Suggestion is "Not checked"; a gaps-only or no-change Suggestion is never checked. The check Run
is in the Agent's Run history, never in the Evaluation summary, and cancelling the Suggestion
cancels it.

Visitor replies cite nothing, so the fake judge fails their Live Verdicts and the fake proposer
suggests adding its citation line to the system prompt. Answering the Evaluation Set, the
scripted model cites a Chunk or not depending on whether the system prompt it was given holds
that line, so each side's answers show which configuration it answered with.
"""

import uuid
from collections.abc import AsyncIterator, Callable
from decimal import Decimal
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo

from app.evaluation import service as evaluation_service
from app.evaluation.job import run_evaluation
from app.suggestions import service
from app.suggestions.fake_proposer import CITE_LINE
from tests.conftest import ClientFactory, SignedUpMember
from tests.fakes.clock import ControllableClock
from tests.integration.test_evaluation import add_case, evaluation_path
from tests.integration.test_evaluation_publish import summary
from tests.integration.test_evaluation_settings import set_repeats
from tests.integration.test_organisation_cost import org_cost
from tests.integration.test_suggestion_apply import apply, diffed
from tests.integration.test_suggestion_runs import in_new_session, scope_of
from tests.integration.test_suggestions import (
    BASE_PROMPT,
    everything,
    live_agent,
    proposal,
    replied,
    scripted,
    started,
    suggestions_path,
)

UNCITED = "Everyone gets twenty-five days of annual leave a year."
CITED = "Everyone gets twenty-five days of annual leave a year, see [C1]."
REFERENCE = 'You get "twenty-five days".'
NOV_5 = "2026-11-05"


@pytest.fixture
async def visitor(new_client: ClientFactory) -> httpx.AsyncClient:
    """A browser on someone's website: no Studio session."""
    return await new_client()


def answering(
    *, with_line: str, without_line: str
) -> tuple[Callable[[list[ModelMessage], AgentInfo], AsyncIterator[str]], list[str]]:
    """A stream answering an Evaluation Case ``with_line`` when the system prompt it was given
    holds the fake proposer's citation line, else ``without_line``; Visitor replies are always
    uncited. Returns it with every text it was given answering a case."""
    seen: list[str] = []

    async def stream(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
        given = everything(messages)
        if "Leave question" not in given:
            # A Visitor's question.
            yield UNCITED
            return
        seen.append(given)
        yield with_line if CITE_LINE in given else without_line

    return stream, seen


async def visitor_replies_then(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    *,
    with_line: str,
    without_line: str,
    cases: int = 1,
) -> tuple[dict[str, Any], list[str]]:
    """A live Agent with ``cases`` Evaluation Cases and one failed (uncited) Visitor reply."""
    stream, seen = answering(with_line=with_line, without_line=without_line)

    scripted(app, stream)
    agent = await live_agent(app, owner)
    await set_repeats(owner, 1)
    for number in range(cases):
        await add_case(
            owner, agent["project_id"], agent["id"], f"Leave question {number}?", REFERENCE
        )
    await replied(visitor, agent)
    return agent, seen


async def runs(member: SignedUpMember, agent: dict[str, Any]) -> list[dict[str, Any]]:
    response = await member.client.get(
        evaluation_path(member, agent["project_id"], agent["id"], "runs")
    )
    assert response.status_code == 200, response.text
    found: list[dict[str, Any]] = response.json()
    return found


async def run_results(member: SignedUpMember, agent: dict[str, Any], run_id: str) -> dict[str, Any]:
    response = await member.client.get(
        evaluation_path(member, agent["project_id"], agent["id"], "runs", run_id, "results")
    )
    assert response.status_code == 200, response.text
    found: dict[str, Any] = response.json()
    return found


async def read(member: SignedUpMember, agent: dict[str, Any], suggestion_id: str) -> dict[str, Any]:
    response = await member.client.get(suggestions_path(member, agent, suggestion_id))
    assert response.status_code == 200, response.text
    found: dict[str, Any] = response.json()
    return found


# The check


async def test_a_change_is_checked_against_the_live_version_on_the_evaluation_set(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    # The Live Version's answers cite nothing and fail grounding; the Suggestion's cite.
    agent, _ = await visitor_replies_then(
        app, owner, visitor, with_line=CITED, without_line=UNCITED
    )
    assert await runs(owner, agent) == []

    suggestion = await started(owner, agent)

    assert (suggestion["status"], suggestion["outcome"]) == ("completed", "changes")
    check = suggestion["check"]
    assert check["state"] == "clear"
    (run,) = await runs(owner, agent)
    assert check["evaluation_run_id"] == run["id"]
    # The check is a Run of kind ``suggestion``: the Live Version, then the Suggestion.
    assert (run["kind"], run["status"]) == ("suggestion", "completed")
    first, second = run["sides"]
    assert (first["kind"], first["version_number"]) == ("version", 1)
    assert (second["kind"], second["version_number"]) == ("suggestion", 1)
    # The Suggestion answers with the Live Version's pinned Instructions (none here).
    assert second["instructions_version_number"] == first["instructions_version_number"]
    assert second["instructions_draft"] is False
    # Both Evaluation scores are on the Suggestion.
    assert (check["live_score"], check["suggestion_score"]) == (0.0, 1.0)
    assert (first["score"], second["score"]) == (0.0, 1.0)
    assert check["regressions"] == []
    # Each side answered with its own configuration: only the Suggestion's held the new line.
    results = await run_results(owner, agent, run["id"])
    (case,) = results["cases"]
    answers = {r["position"]: r["answer"] for r in case["results"]}
    assert answers == {"first": UNCITED, "second": CITED}
    assert case["change"] == "improvement"
    # The actual checking Cost is frozen beside the proposing Cost: the Run's own Cost.
    cost = suggestion["cost"]
    assert Decimal(cost["checking_usd"]) == Decimal(run["cost"]["total_usd"])
    assert Decimal(cost["checking_usd"]) > 0
    assert cost["proposing_usd"] is not None
    # The list shows the check's result too.
    (listed,) = (await owner.client.get(suggestions_path(owner, agent))).json()
    assert listed["check"] == {k: v for k, v in check.items() if k != "regressions"}
    assert listed["cost"] == cost


async def test_regressions_show_with_their_reasons_and_a_failed_check_still_applies(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    # The other way round: the Live Version's answers cite, and the Suggestion's don't.
    agent, _ = await visitor_replies_then(
        app, owner, visitor, with_line=UNCITED, without_line=CITED, cases=2
    )
    case_ids = [
        c["id"]
        for c in (
            await owner.client.get(
                evaluation_path(owner, agent["project_id"], agent["id"], "cases")
            )
        ).json()
    ]

    suggestion = await started(owner, agent)

    check = suggestion["check"]
    assert check["state"] == "regressions"
    assert (check["live_score"], check["suggestion_score"]) == (1.0, 0.0)
    regressions = check["regressions"]
    assert sorted(r["case_id"] for r in regressions) == sorted(case_ids)
    assert {r["question"] for r in regressions} == {"Leave question 0?", "Leave question 1?"}
    for regression in regressions:
        assert [reason["kind"] for reason in regression["reasons"]] == ["grounding"]
        assert all(reason["reason"] for reason in regression["reasons"])
    # A warning, never a block: the Suggestion still applies to the Draft.
    found = await diffed(owner, agent, suggestion["id"])
    response = await apply(owner, agent, suggestion["id"], found["draft_revision"])
    assert response.status_code == 200, response.text
    # Reading it again shows the same check.
    assert (await read(owner, agent, suggestion["id"]))["check"] == check


async def test_a_check_where_every_answer_errors_has_failed_and_the_suggestion_completes(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    async def stream(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
        if CITE_LINE in everything(messages) or "Leave question" in everything(messages):
            raise ModelHTTPError(503, "gpt-4.1-mini", "Overloaded")
        yield UNCITED

    scripted(app, stream)
    agent = await live_agent(app, owner)
    await set_repeats(owner, 1)
    await add_case(owner, agent["project_id"], agent["id"], "Leave question?", REFERENCE)
    await replied(visitor, agent)

    suggestion = await started(owner, agent)

    assert suggestion["status"] == "completed"
    check = suggestion["check"]
    assert check["state"] == "failed"
    assert (check["live_score"], check["suggestion_score"]) == (None, None)
    (run,) = await runs(owner, agent)
    assert (run["id"], run["status"]) == (check["evaluation_run_id"], "failed")


async def test_without_an_evaluation_set_a_change_is_not_checked(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    scripted(app)
    agent = await live_agent(app, owner)
    await replied(visitor, agent)

    suggestion = await started(owner, agent)

    assert (suggestion["status"], suggestion["outcome"]) == ("completed", "changes")
    assert suggestion["check"] == {
        "state": "not_checked",
        "evaluation_run_id": None,
        "live_score": None,
        "suggestion_score": None,
        "regressions": [],
    }
    assert suggestion["cost"]["checking_usd"] is None
    assert await runs(owner, agent) == []


@pytest.mark.parametrize(
    ("changes", "outcome"),
    [
        ([], "no_change"),
        ([{"path": "unknown.setting", "value": 1, "explanation": "x"}], "no_change"),
    ],
)
async def test_no_configuration_change_is_never_checked(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    changes: list[dict[str, Any]],
    outcome: str,
) -> None:
    scripted(app, proposer=proposal(changes))
    agent = await live_agent(app, owner)
    await set_repeats(owner, 1)
    await add_case(owner, agent["project_id"], agent["id"], "Leave question?", REFERENCE)
    await replied(visitor, agent)

    suggestion = await started(owner, agent)

    assert (suggestion["status"], suggestion["outcome"]) == ("completed", outcome)
    assert suggestion["check"] is None
    assert suggestion["cost"]["checking_usd"] is None
    assert await runs(owner, agent) == []


async def test_a_gaps_only_suggestion_is_never_checked(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    def gaps_only(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        output = {
            "changes": [],
            "gaps": [
                {"topic": "Parental leave", "explanation": "Nothing on it.", "evidence": ["E1"]}
            ],
            "overall_explanation": "Only a gap.",
        }
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    scripted(app, proposer=gaps_only)
    agent = await live_agent(app, owner)
    await add_case(owner, agent["project_id"], agent["id"], "Leave question?", REFERENCE)
    await replied(visitor, agent)

    suggestion = await started(owner, agent)

    assert (suggestion["outcome"], suggestion["check"]) == ("gaps_only", None)
    assert await runs(owner, agent) == []


# Run history and the Evaluation summary


async def test_the_check_is_in_run_history_and_never_counts_in_the_evaluation_summary(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent, _ = await visitor_replies_then(
        app, owner, visitor, with_line=CITED, without_line=UNCITED
    )
    before = await summary(owner, agent["project_id"], agent["id"])
    assert before["state"] == "no_run"

    suggestion = await started(owner, agent)

    (run,) = await runs(owner, agent)
    assert (run["id"], run["kind"]) == (suggestion["check"]["evaluation_run_id"], "suggestion")
    after = await summary(owner, agent["project_id"], agent["id"])
    assert (after["state"], after["run"]) == ("no_run", None)
    # The check is not a Rollout evaluation either, nor evidence that a Draft was evaluated.
    assert run["sides"][1]["draft_revision"] is None


async def test_the_general_run_api_cannot_create_a_suggestion_side(
    app: FastAPI, owner: SignedUpMember
) -> None:
    scripted(app)
    agent = await live_agent(app, owner)
    await add_case(owner, agent["project_id"], agent["id"], "Leave question?", REFERENCE)

    response = await owner.client.post(
        evaluation_path(owner, agent["project_id"], agent["id"], "runs"),
        json={
            "sides": [
                {"kind": "version", "version_id": agent["version"]["id"]},
                {"kind": "suggestion"},
            ]
        },
    )

    assert response.status_code == 422, response.text
    assert await runs(owner, agent) == []


async def test_checking_cost_is_counted_in_organisation_costs_evaluation_column(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent, _ = await visitor_replies_then(
        app, owner, visitor, with_line=CITED, without_line=UNCITED
    )
    before = await org_cost(owner, start=NOV_5, end=NOV_5, group_by="agent")
    (line,) = before["rows"]

    suggestion = await started(owner, agent)

    (counted,) = (await org_cost(owner, start=NOV_5, end=NOV_5, group_by="agent"))["rows"]
    spent = Decimal(suggestion["cost"]["proposing_usd"]) + Decimal(
        suggestion["cost"]["checking_usd"]
    )
    assert Decimal(counted["evaluation_usd"]) == Decimal(line["evaluation_usd"]) + spent


# Cancelling, and the one-Run-at-a-time rule


async def test_cancelling_the_suggestion_while_it_checks_cancels_its_run(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent, _ = await visitor_replies_then(
        app, owner, visitor, with_line=CITED, without_line=UNCITED
    )
    scope = scope_of(owner)
    project_id, agent_id = uuid.UUID(agent["project_id"]), uuid.UUID(agent["id"])
    seen: dict[str, Any] = {}
    real = run_evaluation

    async def editor_cancels_first(
        sessionmaker: Any, ports: Any, gateway: Any, run_id: uuid.UUID, clock: Any
    ) -> None:
        async def meanwhile(session: Any) -> None:
            (listed,) = await service.list_suggestions(session, scope, project_id, agent_id)
            seen["status"] = listed.suggestion.status
            suggestion_id = listed.suggestion.id
            read = await service.get_suggestion(session, scope, project_id, agent_id, suggestion_id)
            seen["check"] = None if read.check is None else read.check.state
            # Evaluate is refused while the check runs.
            try:
                await evaluation_service.start_run(
                    session, scope, project_id, agent_id, now=clock.now()
                )
            except evaluation_service.SuggestionInProgressError:
                seen["evaluate"] = "refused"
            await session.rollback()
            await service.cancel_suggestion(
                session, scope, project_id, agent_id, suggestion_id, now=clock.now()
            )

        await in_new_session(meanwhile)
        await real(sessionmaker, ports, gateway, run_id, clock)

    monkeypatch.setattr("app.suggestions.service.run_evaluation", editor_cancels_first)

    suggestion = await started(owner, agent)

    assert seen == {"status": "checking", "check": "running", "evaluate": "refused"}
    assert suggestion["status"] == "cancelled"
    (run,) = await runs(owner, agent)
    assert (run["id"], run["status"]) == (suggestion["check"]["evaluation_run_id"], "cancelled")
    assert run["progress"]["done"] == 0
    assert suggestion["check"]["state"] == "cancelled"
    # What the check spent before it stopped (nothing) is frozen.
    assert Decimal(suggestion["cost"]["checking_usd"]) == 0
    # Evaluate is allowed again.
    response = await owner.client.post(
        evaluation_path(owner, agent["project_id"], agent["id"], "runs")
    )
    assert response.status_code == 202, response.text


async def test_cancelling_once_the_check_has_finished_keeps_its_run(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent, _ = await visitor_replies_then(
        app, owner, visitor, with_line=CITED, without_line=UNCITED
    )
    scope = scope_of(owner)
    project_id, agent_id = uuid.UUID(agent["project_id"]), uuid.UUID(agent["id"])
    real = run_evaluation

    async def editor_cancels_after(
        sessionmaker: Any, ports: Any, gateway: Any, run_id: uuid.UUID, clock: Any
    ) -> None:
        await real(sessionmaker, ports, gateway, run_id, clock)

        async def cancel_it(session: Any) -> None:
            ((found, *_),) = await service.list_suggestions(session, scope, project_id, agent_id)
            await service.cancel_suggestion(
                session, scope, project_id, agent_id, found.id, now=clock.now()
            )

        await in_new_session(cancel_it)

    monkeypatch.setattr("app.suggestions.service.run_evaluation", editor_cancels_after)

    suggestion = await started(owner, agent)

    # The Suggestion is cancelled, but the check had already finished: it stays completed.
    assert suggestion["status"] == "cancelled"
    assert suggestion["check"]["state"] == "clear"
    (run,) = await runs(owner, agent)
    assert run["status"] == "completed"
    assert Decimal(suggestion["cost"]["checking_usd"]) == Decimal(run["cost"]["total_usd"])


async def test_the_live_versions_base_prompt_is_what_the_first_side_answers_with(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent, seen = await visitor_replies_then(
        app, owner, visitor, with_line=CITED, without_line=UNCITED
    )
    seen.clear()

    await started(owner, agent)

    # One answer per side: the Live Version's prompt, then the Suggestion's.
    live, suggested = seen
    assert BASE_PROMPT in live
    assert CITE_LINE not in live
    assert f"{BASE_PROMPT}\n{CITE_LINE}" in suggested
