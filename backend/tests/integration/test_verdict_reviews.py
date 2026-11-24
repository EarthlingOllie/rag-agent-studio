"""API seam: the Review sample (spec 18, ticket 18-02). An Editor is served a judged Run Verdict
blind, gives their own pass or fail, and is shown the Evaluation Model's; Evaluation Model
agreement counts how many of those reviews agreed (its full figures are in
``test_evaluation_agreement``).

Verdicts come from spec 14's flow: the Draft answers through the real Guardrails and retrieval
with a scripted ``FunctionModel``, judged by the fake judge, and the Run's task runs eagerly.
The draw is seeded through test settings (``REVIEW_SAMPLE_SEED``).
"""

from typing import Any

import httpx
from fastapi import FastAPI

from app.agents.config import DEFAULT_FALLBACK_TEXT
from tests.agents import create_automatic_agent
from tests.conftest import MemberFactory, SignedUpMember, TenantFactory
from tests.documents import create_project
from tests.integration.test_evaluation import (
    FAILING,
    PASSING,
    RATE_LIMITED,
    REFERENCE,
    add_case,
    evaluated,
    evaluation_path,
    judge_with,
    scripted,
)
from tests.integration.test_evaluation_expectations import add_case as add_expectations
from tests.integration.test_evaluation_expectations import leave_document, source
from tests.integration.test_evaluation_publish import summary
from tests.integration.test_evaluation_settings import set_evaluation_model, set_repeats
from tests.integration.test_playground import ANSWER, LEAVE, ready_agent, three_tokens
from tests.integration.test_provider_credentials import ANTHROPIC_KEY, added

QUESTION = "How much leave do I get?"
REFERENCE_PASSED = "Fake judge: the answer contains “twenty-five days”."
REFERENCE_FAILED = "Fake judge: the answer lacks “twenty-five days”."
CITED = "Fake judge: the answer cites the knowledge base."
UNCITED = "Fake judge: the answer cites nothing to support it."
REASON_MAX = 1000


def sample_path(member: SignedUpMember, *rest: str) -> str:
    return "/".join([f"/api/organisations/{member.organisation_id}/review-sample", *rest])


async def next_item(member: SignedUpMember) -> dict[str, Any]:
    response = await member.client.get(sample_path(member, "next"))
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def review(
    member: SignedUpMember, verdict_id: str, outcome: str, reason: str | None = None
) -> httpx.Response:
    return await member.client.post(
        sample_path(member, "reviews"),
        json={"verdict_id": verdict_id, "outcome": outcome, "reason": reason},
    )


async def reviewed(
    member: SignedUpMember, verdict_id: str, outcome: str, reason: str | None = None
) -> dict[str, Any]:
    response = await review(member, verdict_id, outcome, reason)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def agreement(member: SignedUpMember) -> dict[str, Any]:
    response = await member.client.get(
        f"/api/organisations/{member.organisation_id}/evaluation-agreement"
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def drained(member: SignedUpMember) -> list[dict[str, Any]]:
    """Every item the sample serves, each reviewed as passing so the next one is served."""
    served: list[dict[str, Any]] = []
    while (item := (await next_item(member))["item"]) is not None:
        served.append(item)
        await reviewed(member, item["verdict_id"], "pass")
    return served


async def judged_once(
    app: FastAPI, owner: SignedUpMember, *answers: str | int
) -> tuple[str, str, dict[str, Any]]:
    """A ready Agent with one Reference answer case, evaluated once (one answer per case)."""
    judge_with(app, scripted(*answers) if answers else three_tokens)
    _, project_id, agent_id = await ready_agent(app, owner)
    await add_case(owner, project_id, agent_id, QUESTION)
    await set_repeats(owner, 1)
    return project_id, agent_id, await evaluated(owner, project_id, agent_id)


def verdicts_in(results: dict[str, Any]) -> list[dict[str, Any]]:
    return [v for case in results["cases"] for r in case["results"] for v in r["verdicts"]]


def without_reviews(results: dict[str, Any]) -> dict[str, Any]:
    """The results with every Verdict's review left out."""
    for verdict in verdicts_in(results):
        verdict.pop("review")
    return results


def results_path(member: SignedUpMember, project_id: str, agent_id: str, run_id: str) -> str:
    return evaluation_path(member, project_id, agent_id, "runs", run_id, "results")


# The Review sample


async def test_an_editor_reviews_a_judged_verdict_blind_and_then_sees_the_judges(
    app: FastAPI, owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    await judged_once(app, owner)

    first = await next_item(editor)

    item = first["item"]
    assert item["check"] in ("reference_answer", "grounding")
    assert item["question"] == QUESTION
    assert item["answer"] == ANSWER
    assert item["agent_name"]
    assert item["chunks"] == [
        {"label": "C1", "document_name": "leave.txt", "text": LEAVE, "cited": True}
    ]
    assert item["reference_answer"] == (REFERENCE if item["check"] == "reference_answer" else None)
    # Blind: nothing of the Evaluation Model's outcome or reason is served.
    assert "outcome" not in item
    assert "Fake judge" not in str(first)
    assert (first["reviewed"], first["reviewed_by_you"]) == (0, 0)

    reveal = await reviewed(editor, item["verdict_id"], "fail", "It never says a year.")

    assert reveal["outcome"] == "fail"
    assert reveal["evaluation_model_outcome"] == "pass"
    assert reveal["evaluation_model_reason"] in (REFERENCE_PASSED, CITED)
    assert reveal["agreed"] is False
    # The other judged Verdict of the answer is served next, and then there is nothing left.
    second = await next_item(editor)
    assert second["item"]["check"] != item["check"]
    assert (second["reviewed"], second["reviewed_by_you"]) == (1, 1)
    await reviewed(editor, second["item"]["verdict_id"], "pass")
    empty = await next_item(owner)
    assert empty == {"item": None, "reviewed": 2, "reviewed_by_you": 0}


async def test_skipping_stores_nothing_and_the_item_stays_in_the_sample(
    app: FastAPI, owner: SignedUpMember
) -> None:
    await judged_once(app, owner)

    served = {(await next_item(owner))["item"]["verdict_id"] for _ in range(12)}

    # Both judged Verdicts stay in the sample, drawn at random, until one is reviewed.
    assert len(served) == 2
    assert (await next_item(owner))["reviewed"] == 0
    assert (await agreement(owner))["current"]["reviews"] == 0


async def test_only_judged_reference_answer_and_grounding_verdicts_are_served(
    app: FastAPI, owner: SignedUpMember
) -> None:
    judge_with(app, three_tokens)
    _, project_id, agent_id = await ready_agent(app, owner)
    await set_repeats(owner, 1)
    document = await leave_document(owner, project_id)
    # An Expected source and a Reference answer; Expect Fallback Text; and an answer that is
    # the Fallback Text, which isn't asked about grounding.
    await add_expectations(
        owner,
        project_id,
        agent_id,
        reference_answer=REFERENCE,
        expected_sources=[source(document["id"], LEAVE)],
    )
    await add_expectations(owner, project_id, agent_id, question="Fallback?", expect_fallback=True)
    # A Project without Documents: its Agent answers with the Fallback Text.
    empty_project = await create_project(owner)
    automatic = await create_automatic_agent(owner, empty_project)
    await add_case(owner, empty_project, automatic["id"], "What is the canteen menu?", '"know"')
    await evaluated(owner, project_id, agent_id)
    fallback = await evaluated(owner, empty_project, automatic["id"])
    assert fallback["cases"][0]["results"][0]["answer"] == DEFAULT_FALLBACK_TEXT

    served = await drained(owner)

    # The Expect Fallback Text case's answer wasn't the Fallback Text, so it was asked about
    # grounding; its Expect Fallback Text Verdict, like the Expected source's, isn't served.
    assert sorted((i["question"], i["check"]) for i in served) == [
        ("Fallback?", "grounding"),
        (QUESTION, "grounding"),
        (QUESTION, "reference_answer"),
        ("What is the canteen menu?", "reference_answer"),
    ]


async def test_an_errored_answer_is_never_served(app: FastAPI, owner: SignedUpMember) -> None:
    await judged_once(app, owner, RATE_LIMITED)

    assert (await next_item(owner))["item"] is None


async def test_only_the_current_evaluation_models_verdicts_are_served(
    app: FastAPI, owner: SignedUpMember
) -> None:
    await judged_once(app, owner)
    (item,) = [(await next_item(owner))["item"]]
    await reviewed(owner, item["verdict_id"], "pass")
    claude = await added(owner, provider="anthropic", api_key=ANTHROPIC_KEY, name="Claude")

    changed = await set_evaluation_model(owner, claude["id"], "claude-haiku-4-5")

    assert changed.status_code == 200, changed.text
    # The Default Model judged the Run: nothing is left for the new Evaluation Model.
    assert (await next_item(owner))["item"] is None
    current = (await agreement(owner))["current"]
    assert (current["provider"], current["model"]) == ("anthropic", "claude-haiku-4-5")
    assert (current["reviews"], current["agreed"]) == (0, 0)
    await set_evaluation_model(owner, None, None)
    assert (await next_item(owner))["item"] is not None
    assert (await agreement(owner))["current"]["reviews"] == 1


async def test_an_organisation_without_a_model_to_judge_with_has_an_empty_sample(
    owner: SignedUpMember,
) -> None:
    assert await next_item(owner) == {"item": None, "reviewed": 0, "reviewed_by_you": 0}
    assert (await agreement(owner))["current"] is None


# Reviews and agreement


async def test_agreement_counts_sample_reviews_that_agreed_with_the_evaluation_model(
    app: FastAPI, owner: SignedUpMember
) -> None:
    # The answer is wrong and uncited: the Evaluation Model failed both Verdicts.
    await judged_once(app, owner, FAILING)
    first = (await next_item(owner))["item"]
    revealed = await reviewed(owner, first["verdict_id"], "fail")
    assert (revealed["evaluation_model_outcome"], revealed["agreed"]) == ("fail", True)
    assert revealed["evaluation_model_reason"] in (REFERENCE_FAILED, UNCITED)
    second = (await next_item(owner))["item"]
    await reviewed(owner, second["verdict_id"], "pass")

    found = await agreement(owner)

    current = found["current"]
    assert (current["provider"], current["model"]) == ("openai", "gpt-4.1-mini")
    assert (current["reviews"], current["agreed"]) == (2, 1)


async def test_reviewing_the_same_verdict_again_replaces_the_review(
    app: FastAPI, owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    await judged_once(app, owner, PASSING)
    item = (await next_item(owner))["item"]
    await reviewed(owner, item["verdict_id"], "fail")

    replaced = await reviewed(editor, item["verdict_id"], "pass", None)

    assert replaced["agreed"] is True
    assert (await agreement(owner))["current"]["reviews"] == 1
    assert (await agreement(owner))["current"]["agreed"] == 1
    # Now the Editor's review, not the Owner's.
    assert (await next_item(editor))["reviewed_by_you"] == 1
    assert (await next_item(owner))["reviewed_by_you"] == 0


async def test_a_reason_is_up_to_a_thousand_characters(app: FastAPI, owner: SignedUpMember) -> None:
    await judged_once(app, owner)
    item = (await next_item(owner))["item"]

    too_long = await review(owner, item["verdict_id"], "fail", "x" * (REASON_MAX + 1))
    not_an_outcome = await review(owner, item["verdict_id"], "stale")

    assert too_long.status_code == 422
    assert not_an_outcome.status_code == 422
    assert (await reviewed(owner, item["verdict_id"], "fail", "x" * REASON_MAX))["agreed"] is False


async def test_a_verdict_outside_the_sample_cannot_be_reviewed(
    app: FastAPI, owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    judge_with(app, three_tokens)
    _, project_id, agent_id = await ready_agent(app, owner)
    await set_repeats(owner, 1)
    document = await leave_document(owner, project_id)
    await add_expectations(
        owner, project_id, agent_id, expected_sources=[source(document["id"], LEAVE)]
    )
    await add_case(owner, project_id, agent_id, QUESTION)
    results = await evaluated(owner, project_id, agent_id)
    (expected,) = [v["id"] for v in verdicts_in(results) if v["kind"] == "expected_source"]
    item = (await next_item(owner))["item"]
    other = await tenant_factory()

    assert (await review(owner, expected, "pass")).status_code == 404
    assert (await review(other, item["verdict_id"], "pass")).status_code == 404
    assert (await next_item(other))["item"] is None
    assert (await agreement(other))["current"] is None
    assert (await next_item(owner))["reviewed"] == 0


async def test_reviews_never_change_a_verdict_a_score_regressions_or_the_publish_summary(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id, agent_id, results = await judged_once(app, owner, FAILING)
    run_id = results["run"]["id"]
    before = await summary(owner, project_id, agent_id)
    path = results_path(owner, project_id, agent_id, run_id)

    for item in await drained(owner):
        # The Editor disagrees with every failed Verdict.
        assert item["verdict_id"]

    assert (await agreement(owner))["current"]["agreed"] == 0
    after = (await owner.client.get(path)).json()
    # The Verdicts now show their reviews, and are otherwise just as they were.
    assert [v["review"]["outcome"] for v in verdicts_in(after)] == ["pass", "pass"]
    assert without_reviews(after) == without_reviews(results)
    assert await summary(owner, project_id, agent_id) == before
