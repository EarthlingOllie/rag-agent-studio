"""API seam: Evaluation Model agreement and the Review sample per Judging setup (spec 19, ticket
19-03). A Verdict review records the Judging setup (Evaluation Model and Judging guidance version)
of the judgement it reviews; the Review sample serves only judgements under the current Judging
setup; agreement shows the current Judging setup's figures and lists the earlier ones that have
reviews. Saving guidance and changing the Evaluation Model both start new figures.

Run Verdicts come from spec 14's flow and Live Verdicts from spec 15's, as in spec 18's own
tests; guidance is saved through its route (spec 19, ticket 19-01).
"""

from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from tests.conftest import ClientFactory, SignedUpMember
from tests.integration.test_evaluation import FAILING, evaluated
from tests.integration.test_evaluation_agreement import review_all, skip
from tests.integration.test_evaluation_settings import set_evaluation_model
from tests.integration.test_judging_guidance import saved
from tests.integration.test_live_verdict_context import conversation
from tests.integration.test_live_verdict_reviews import remembering, reviewed_item
from tests.integration.test_provider_credentials import ANTHROPIC_KEY, added
from tests.integration.test_verdict_reviews import agreement, judged_once, next_item

STRICT = "Fail an answer that doesn't cite the leave policy."
LENIENT = "Pass a partial answer that says what it doesn't cover."


@pytest.fixture
async def visitor(new_client: ClientFactory) -> httpx.AsyncClient:
    return await new_client()


def setup(found: dict[str, Any]) -> tuple[str, str, int | None, int]:
    """An agreement's Judging setup and its review count."""
    return (found["provider"], found["model"], found["guidance_version"], found["reviews"])


async def test_saving_guidance_starts_new_figures_and_lists_the_earlier_judging_setup(
    app: FastAPI, owner: SignedUpMember
) -> None:
    # Both Runs' answers are wrong and uncited: the Evaluation Model fails both Verdicts.
    project_id, agent_id, _ = await judged_once(app, owner, FAILING, FAILING)
    await review_all(owner, {"reference_answer": "pass", "grounding": "fail"})

    await saved(owner, STRICT)

    found = await agreement(owner)
    assert setup(found["current"]) == ("openai", "gpt-4.1-mini", 1, 0)
    assert found["current"]["checks"] == []
    (earlier,) = found["earlier"]
    assert setup(earlier) == ("openai", "gpt-4.1-mini", None, 2)
    assert (earlier["agreed"], earlier["false_fails"]) == (1, 1)
    assert (found["reviewed"], found["reviewed_by_you"]) == (0, 0)
    # The Run was judged before the guidance: nothing in the sample is under it yet.
    assert (await next_item(owner))["item"] is None
    # A new Run is judged under the guidance, and its Verdicts are served.
    await evaluated(owner, project_id, agent_id)
    await review_all(owner, {"reference_answer": "fail", "grounding": "fail"})
    found = await agreement(owner)
    assert setup(found["current"]) == ("openai", "gpt-4.1-mini", 1, 2)
    assert found["current"]["agreed"] == 2
    assert [setup(e) for e in found["earlier"]] == [("openai", "gpt-4.1-mini", None, 2)]


async def test_a_review_records_the_judging_setup_of_the_judgement_it_reviews(
    app: FastAPI, owner: SignedUpMember
) -> None:
    await judged_once(app, owner)
    item = (await next_item(owner))["item"]
    # The guidance changes while the item is on screen.
    await saved(owner, STRICT)

    await reviewed_item(owner, item, "pass")

    found = await agreement(owner)
    assert setup(found["current"]) == ("openai", "gpt-4.1-mini", 1, 0)
    assert [setup(e) for e in found["earlier"]] == [("openai", "gpt-4.1-mini", None, 1)]


async def test_live_verdicts_are_served_only_under_the_current_judging_setup(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent = await remembering(app, owner, 0)
    await conversation(visitor, agent, "How much leave do I get?")
    await saved(owner, LENIENT)
    assert (await next_item(owner))["item"] is None

    await conversation(visitor, agent, "What about part-timers?")

    served = []
    while (item := (await next_item(owner))["item"]) is not None:
        served.append(item["check"])
        await reviewed_item(owner, item, "pass")
    assert sorted(served) == ["answers_question", "grounding"]
    found = await agreement(owner)
    assert setup(found["current"]) == ("openai", "gpt-4.1-mini", 1, 2)
    assert found["earlier"] == []


async def test_changing_the_evaluation_model_under_guidance_starts_new_figures(
    app: FastAPI, owner: SignedUpMember
) -> None:
    await saved(owner, STRICT)
    await judged_once(app, owner, FAILING)
    await review_all(owner, {"reference_answer": "pass", "grounding": "fail"})
    claude = await added(owner, provider="anthropic", api_key=ANTHROPIC_KEY, name="Claude")

    await set_evaluation_model(owner, claude["id"], "claude-haiku-4-5")

    found = await agreement(owner)
    assert setup(found["current"]) == ("anthropic", "claude-haiku-4-5", 1, 0)
    assert [setup(e) for e in found["earlier"]] == [("openai", "gpt-4.1-mini", 1, 2)]
    assert (await next_item(owner))["item"] is None


async def test_removing_guidance_starts_new_figures_and_earlier_setups_list_newest_first(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id, agent_id, _ = await judged_once(app, owner)
    await reviewed_item(owner, (await next_item(owner))["item"], "pass")
    await saved(owner, STRICT)
    await evaluated(owner, project_id, agent_id)
    await reviewed_item(owner, (await next_item(owner))["item"], "pass")

    # Removing guidance saves the empty version 2: a Judging setup of its own.
    await saved(owner, "")

    found = await agreement(owner)
    assert setup(found["current"]) == ("openai", "gpt-4.1-mini", 2, 0)
    assert [setup(e) for e in found["earlier"]] == [
        ("openai", "gpt-4.1-mini", 1, 1),
        ("openai", "gpt-4.1-mini", None, 1),
    ]


async def test_skips_are_counted_per_judging_setup(app: FastAPI, owner: SignedUpMember) -> None:
    await judged_once(app, owner)
    assert (await skip(owner)).status_code == 204

    await saved(owner, STRICT)

    assert (await agreement(owner))["skipped"] == 0
    assert (await skip(owner)).status_code == 204
    assert (await agreement(owner))["skipped"] == 1
