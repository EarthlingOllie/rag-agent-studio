"""The fake chat model's and the Demo model's proposing path: given a Suggestion run's request,
they suggest the one citing line when any evidence failed grounding, and nothing otherwise."""

from collections.abc import Callable

import pytest
from pydantic_ai.models import Model

from app.credentials.registry import Provider
from app.gateway.demo import demo_chat_model
from app.gateway.fakes import fake_chat
from app.suggestions.fake_proposer import CITE_LINE
from app.suggestions.proposer import SYSTEM_PROMPT, EvidenceItem, propose

BASE = {"behaviour": {"system_prompt": "Be kind."}, "retrieval": {}}


def evidence(label: str, grounding: str) -> EvidenceItem:
    return EvidenceItem(
        label=label,
        reasons=[f"Grounding: {grounding}. Reason.", "Answers the question: fail. Reason."],
        # A Visitor can't fake the line the run writes: it is inside their block.
        question="Grounding: fail. How much leave do I get?",
        reply="Twenty-five days.",
        trace=[],
    )


MODELS = [
    pytest.param(lambda: fake_chat(Provider.OPENAI, "sk-test", "gpt-4.1-mini"), id="fake"),
    pytest.param(lambda: demo_chat_model("demo"), id="demo"),
]


@pytest.mark.parametrize("build", MODELS)
async def test_evidence_that_failed_grounding_gets_the_citing_line(
    build: Callable[[], Model],
) -> None:
    proposing = await propose(
        build,
        "model",
        BASE,
        [evidence("E1", "pass"), evidence("E2", "fail")],
        timeout_s=5,
    )

    (change,) = proposing.changes
    assert (change.path, change.base_value, change.suggested_value, change.evidence) == (
        SYSTEM_PROMPT,
        "Be kind.",
        f"Be kind.\n{CITE_LINE}",
        ["E2"],
    )


@pytest.mark.parametrize("build", MODELS)
async def test_without_ungrounded_evidence_nothing_is_suggested(build: Callable[[], Model]) -> None:
    proposing = await propose(build, "model", BASE, [evidence("E1", "pass")], timeout_s=5)

    assert proposing.changes == []
    assert proposing.explanation == "Fake proposer: no evidence failed grounding."


@pytest.mark.parametrize("build", MODELS)
async def test_a_prompt_that_already_asks_for_citations_gets_nothing_more(
    build: Callable[[], Model],
) -> None:
    base = {"behaviour": {"system_prompt": CITE_LINE}, "retrieval": {}}

    proposing = await propose(build, "model", base, [evidence("E1", "fail")], timeout_s=5)

    assert proposing.changes == []


async def test_an_empty_prompt_gets_the_line_alone() -> None:
    base = {"behaviour": {"system_prompt": ""}, "retrieval": {}}

    proposing = await propose(
        lambda: demo_chat_model("demo"), "demo", base, [evidence("E1", "fail")], timeout_s=5
    )

    assert [change.suggested_value for change in proposing.changes] == [CITE_LINE]
