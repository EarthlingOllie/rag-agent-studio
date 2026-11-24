"""API seam: Evaluation Model agreement (spec 18, ticket 18-05). Agreement is counted when read
over the Review sample reviews of an Evaluation Model: reviews, agreed, false passes (it passed,
the Editor said fail) and false fails, overall and per check, with the rate's Wilson interval and
Low sample under 30 reviews. The current Evaluation Model's figures come with the earlier ones
that have reviews, and with how many sample reviews the Organisation and the reader gave and how
many items were skipped.

Run Verdicts come from spec 14's flow and Live Verdicts from spec 15's, as in the Review sample's
own tests.
"""

from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from tests.conftest import ClientFactory, MemberFactory, SignedUpMember, TenantFactory
from tests.integration.test_evaluation import FAILING, add_case, evaluated, judge_with
from tests.integration.test_evaluation_settings import set_evaluation_model, set_repeats
from tests.integration.test_live_verdict_context import conversation
from tests.integration.test_live_verdict_reviews import remembering, reviewed_item
from tests.integration.test_playground import ready_agent, three_tokens
from tests.integration.test_provider_credentials import ANTHROPIC_KEY, added
from tests.integration.test_verdict_reviews import (
    QUESTION,
    agreement,
    judged_once,
    next_item,
    sample_path,
)


@pytest.fixture
async def visitor(new_client: ClientFactory) -> httpx.AsyncClient:
    return await new_client()


def figures(
    reviews: int, agreed: int, false_passes: int, false_fails: int, low: float, high: float
) -> dict[str, Any]:
    """Expected figures; the interval bounds are worked out by hand from Wilson's formula."""
    return {
        "reviews": reviews,
        "agreed": agreed,
        "false_passes": false_passes,
        "false_fails": false_fails,
        "rate": pytest.approx(agreed / reviews),
        "low": pytest.approx(low, abs=5e-4),
        "high": pytest.approx(high, abs=5e-4),
        "low_sample": reviews < 30,
    }


async def skip(member: SignedUpMember) -> httpx.Response:
    return await member.client.post(sample_path(member, "skips"))


async def review_all(member: SignedUpMember, outcome_for: dict[str, str]) -> None:
    """Reviews every item served, with the outcome given for its check."""
    while (item := (await next_item(member))["item"]) is not None:
        await reviewed_item(member, item, outcome_for[item["check"]])


async def test_agreement_counts_false_fails_per_check_with_the_wilson_interval(
    app: FastAPI, owner: SignedUpMember
) -> None:
    # The answer is wrong and uncited: the Evaluation Model failed both Verdicts.
    await judged_once(app, owner, FAILING)
    await review_all(owner, {"reference_answer": "pass", "grounding": "fail"})

    current = (await agreement(owner))["current"]

    # 1 of 2: Wilson's 95% interval is 0.0945 to 0.9055.
    assert current == {
        "provider": "openai",
        "model": "gpt-4.1-mini",
        **figures(2, 1, 0, 1, 0.0945, 0.9055),
        "checks": [
            {"check": "grounding", **figures(1, 1, 0, 0, 0.2065, 1.0)},
            {"check": "reference_answer", **figures(1, 0, 0, 1, 0.0, 0.7935)},
        ],
    }


async def test_a_live_verdict_the_editor_failed_after_it_passed_is_a_false_pass(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    # Grounded passed; answers the question failed.
    agent = await remembering(app, owner, 0)
    await conversation(visitor, agent, "What about part-timers?")
    await review_all(owner, {"grounding": "fail", "answers_question": "fail"})

    current = (await agreement(owner))["current"]

    assert (current["false_passes"], current["false_fails"], current["agreed"]) == (1, 0, 1)
    assert [(c["check"], c["false_passes"], c["agreed"]) for c in current["checks"]] == [
        ("grounding", 1, 0),
        ("answers_question", 0, 1),
    ]


async def test_agreement_is_a_low_sample_under_thirty_reviews(
    app: FastAPI, owner: SignedUpMember
) -> None:
    judge_with(app, three_tokens)
    _, project_id, agent_id = await ready_agent(app, owner)
    for n in range(3):
        await add_case(owner, project_id, agent_id, f"{QUESTION} ({n})")
    await set_repeats(owner, 5)
    # Three cases answered five times: thirty judged Verdicts, all passed.
    await evaluated(owner, project_id, agent_id)
    for _ in range(29):
        await reviewed_item(owner, (await next_item(owner))["item"], "pass")
    assert (await agreement(owner))["current"]["low_sample"] is True

    await reviewed_item(owner, (await next_item(owner))["item"], "pass")

    current = (await agreement(owner))["current"]
    # 30 of 30: Wilson's 95% interval is 0.8865 to 1.
    assert current == {
        "provider": "openai",
        "model": "gpt-4.1-mini",
        **figures(30, 30, 0, 0, 0.8865, 1.0),
        "checks": [
            {"check": "grounding", **figures(15, 15, 0, 0, 0.7961, 1.0)},
            {"check": "reference_answer", **figures(15, 15, 0, 0, 0.7961, 1.0)},
        ],
    }


async def test_changing_the_evaluation_model_starts_new_figures_and_lists_the_old_ones(
    app: FastAPI, owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    await judged_once(app, owner, FAILING)
    await review_all(owner, {"reference_answer": "pass", "grounding": "fail"})
    assert (await skip(owner)).status_code == 204
    claude = await added(owner, provider="anthropic", api_key=ANTHROPIC_KEY, name="Claude")

    await set_evaluation_model(owner, claude["id"], "claude-haiku-4-5")

    # Every Member reads it.
    found = await agreement(editor)
    assert found["current"] == {
        "provider": "anthropic",
        "model": "claude-haiku-4-5",
        "reviews": 0,
        "agreed": 0,
        "false_passes": 0,
        "false_fails": 0,
        "rate": None,
        "low": None,
        "high": None,
        "low_sample": True,
        "checks": [],
    }
    (earlier,) = found["earlier"]
    assert (earlier["provider"], earlier["model"], earlier["reviews"]) == (
        "openai",
        "gpt-4.1-mini",
        2,
    )
    assert earlier["false_fails"] == 1
    assert [c["check"] for c in earlier["checks"]] == ["grounding", "reference_answer"]
    assert (found["reviewed"], found["reviewed_by_you"], found["skipped"]) == (0, 0, 0)
    # Back to the Default Model: its figures are current again, and the Claude model, which
    # has no reviews, isn't listed.
    await set_evaluation_model(owner, None, None)
    back = await agreement(owner)
    assert back["current"]["reviews"] == 2
    assert back["earlier"] == []
    assert (back["reviewed"], back["reviewed_by_you"], back["skipped"]) == (2, 2, 1)


async def test_the_card_counts_the_organisations_and_your_sample_reviews_and_the_skips(
    app: FastAPI, owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    await judged_once(app, owner)
    await reviewed_item(owner, (await next_item(owner))["item"], "pass")

    for _ in range(2):
        assert (await skip(editor)).status_code == 204

    # A skip stores no review: the item is still served.
    assert (await next_item(editor))["item"] is not None
    for member, by_you in ((editor, 0), (owner, 1)):
        found = await agreement(member)
        assert (found["reviewed"], found["reviewed_by_you"], found["skipped"]) == (1, by_you, 2)
        assert found["current"]["reviews"] == 1


async def test_without_a_model_to_judge_with_nothing_can_be_skipped(
    owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    assert (await skip(owner)).status_code == 404
    assert await agreement(owner) == {
        "current": None,
        "earlier": [],
        "reviewed": 0,
        "reviewed_by_you": 0,
        "skipped": 0,
    }


async def test_another_organisations_agreement_and_skips_are_never_shown(
    app: FastAPI, owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    await judged_once(app, owner)
    await reviewed_item(owner, (await next_item(owner))["item"], "pass")
    await skip(owner)
    other = await tenant_factory()

    found = await agreement(other)

    assert found["current"] is None
    assert (found["earlier"], found["reviewed"], found["skipped"]) == ([], 0, 0)
