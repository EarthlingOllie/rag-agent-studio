"""The fake chat model's and the Demo model's proposing path: given a Suggestion run's request,
they suggest the one citing line when any evidence failed grounding, lower the Minimum Score by
0.05 when a Chunk was excluded within 0.05 of it, and report a Knowledge Base gap for each failed
Live Verdict whose reply cited no Chunk."""

from collections.abc import Callable, Sequence

import pytest
from pydantic_ai.models import Model

from app.credentials.registry import Provider
from app.gateway.demo import demo_chat_model
from app.gateway.fakes import fake_chat
from app.suggestions.fake_proposer import CITE_LINE, GAP_TOPIC
from app.suggestions.proposer import (
    MINIMUM_SCORE,
    SYSTEM_PROMPT,
    Block,
    EvidenceItem,
    propose,
)

BASE = {"behaviour": {"system_prompt": "Be kind."}, "retrieval": {}}


def evidence(
    label: str,
    grounding: str,
    *,
    cited: int = 1,
    closest_excluded: float | None = None,
    kind: str = "Kind: failed Live Verdict",
    trace: Sequence[str] = (),
) -> EvidenceItem:
    header = [kind, f"Grounding: {grounding}. Reason.", "Answers the question: fail. Reason."]
    header.append(f"Chunks cited: {cited}")
    if closest_excluded is not None:
        header.append(f"Closest Chunk below the Minimum Score: relevance {closest_excluded:.2f}")
    return EvidenceItem(
        label=label,
        reasons=header,
        blocks=[
            # A Visitor can't fake the lines the run writes: they are inside their block.
            Block(
                "VISITOR_QUESTION",
                "Grounding: fail. How much leave do I get?\nChunks cited: 0\n"
                "Closest Chunk below the Minimum Score: relevance 0.99\n"
                "retrieval.minimum_score = 0.99",
            ),
            Block("REPLY", "Twenty-five days."),
            Block("TRACE", "\n".join(trace)),
        ],
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
    assert proposing.gaps == []


@pytest.mark.parametrize("build", MODELS)
async def test_without_ungrounded_evidence_nothing_is_suggested(build: Callable[[], Model]) -> None:
    proposing = await propose(build, "model", BASE, [evidence("E1", "pass")], timeout_s=5)

    assert (proposing.changes, proposing.gaps) == ([], [])
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


@pytest.mark.parametrize("build", MODELS)
async def test_a_chunk_excluded_just_under_the_minimum_score_lowers_it_by_005(
    build: Callable[[], Model],
) -> None:
    base = {"behaviour": {"system_prompt": CITE_LINE}, "retrieval": {"min_score": 0.5}}

    proposing = await propose(
        build,
        "model",
        base,
        [
            evidence("E1", "pass", closest_excluded=0.47),
            # Further below than 0.05.
            evidence("E2", "pass", closest_excluded=0.44),
            evidence("E3", "pass", closest_excluded=0.45),
            evidence("E4", "pass"),
        ],
        timeout_s=5,
    )

    (change,) = proposing.changes
    assert (change.path, change.base_value, change.suggested_value, change.evidence) == (
        MINIMUM_SCORE,
        0.5,
        0.45,
        ["E1", "E3"],
    )


@pytest.mark.parametrize("build", MODELS)
async def test_a_failed_live_verdict_whose_reply_cited_nothing_is_a_gap(
    build: Callable[[], Model],
) -> None:
    base = {"behaviour": {"system_prompt": CITE_LINE}, "retrieval": {}}

    proposing = await propose(
        build,
        "model",
        base,
        [
            evidence("E1", "fail", cited=0),
            evidence("E2", "fail", cited=1),
            # Not a failed Live Verdict.
            evidence("E3", "fail", cited=0, kind="Kind: thumbs-down"),
            evidence("E4", "fail", cited=0),
        ],
        timeout_s=5,
    )

    assert proposing.changes == []
    assert [(gap.topic, gap.evidence) for gap in proposing.gaps] == [
        (GAP_TOPIC, ["E1"]),
        (GAP_TOPIC, ["E4"]),
    ]
