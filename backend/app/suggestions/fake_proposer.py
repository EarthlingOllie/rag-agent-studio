"""The deterministic proposing path of the fake chat model and the Demo model.

Asked to propose a Suggestion (a structured-output call whose output schema is the
``Proposal``), they answer by rule instead of by meaning, so tests, ``docker compose`` and the
demo seed are deterministic and free:

- when any piece of evidence failed grounding, they suggest adding one line to the system
  prompt, ``CITE_LINE``, citing those pieces;
- when any piece had a Chunk excluded below the Minimum Score but within 0.05 of it, they
  suggest lowering the Minimum Score by 0.05, citing those pieces;
- they report a Knowledge Base gap for each failed Live Verdict whose reply cited no Chunk.

They read only the lines the run itself writes: the retrieval settings, and the lines at the top
of each evidence block, before its first data block. Never the Visitor's text, so nothing a
Visitor writes can change what they propose.
"""

import re

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo

from app.suggestions.proposer import (
    MINIMUM_SCORE,
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_CLOSE,
    SYSTEM_PROMPT_OPEN,
)

CITE_LINE = "Always cite the passage you used."
GAP_TOPIC = "Fake proposer: a question no Chunk covered"
# How far below the Minimum Score an excluded Chunk may be for it to be lowered, and by how much.
MINIMUM_SCORE_STEP = 0.05
# What the run writes at the top of a piece of evidence.
GROUNDING_FAILED = "Grounding: fail"
FAILED_LIVE_VERDICT = "Kind: failed Live Verdict"
NOTHING_CITED = "Chunks cited: 0"
CLOSEST_EXCLUDED = "Closest Chunk below the Minimum Score: relevance "

# A piece of evidence's id and the lines before its first data block.
_EVIDENCE = re.compile(r"^<<<EVIDENCE (E\d+)>>>\n(.*?)^<<<", re.S | re.M)
_SYSTEM_PROMPT = re.compile(
    re.escape(SYSTEM_PROMPT_OPEN) + "\n(.*?)\n" + re.escape(SYSTEM_PROMPT_CLOSE), re.S
)
_MINIMUM_SCORE = re.compile(rf"^{re.escape(MINIMUM_SCORE)} = ([\d.]+) ", re.M)


def is_proposing(info: AgentInfo) -> bool:
    """Whether the model is asked to propose a Suggestion: its output schema holds
    ``overall_explanation``."""
    return any(
        "overall_explanation" in tool.parameters_json_schema.get("properties", {})
        for tool in info.output_tools
    )


def _request(messages: list[ModelMessage]) -> str:
    return "\n".join(
        str(part.content)
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, UserPromptPart)
    )


def _closest_excluded(header: list[str]) -> float | None:
    for line in header:
        if line.startswith(CLOSEST_EXCLUDED):
            return float(line.removeprefix(CLOSEST_EXCLUDED))
    return None


def fake_proposal(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    """The fake proposer's answer: its structured-output tool called with the Proposal."""
    request = _request(messages)
    found = _SYSTEM_PROMPT.search(request)
    system_prompt = found.group(1) if found else ""
    # The run writes the settings before any evidence, so the first match is its own.
    setting = _MINIMUM_SCORE.search(request)
    minimum_score = float(setting.group(1)) if setting else 0.0
    headers = [(label, header.splitlines()) for label, header in _EVIDENCE.findall(request)]
    ungrounded = [
        label
        for label, header in headers
        if any(line.startswith(GROUNDING_FAILED) for line in header)
    ]
    near_misses = [
        label
        for label, header in headers
        if (closest := _closest_excluded(header)) is not None
        and minimum_score - closest <= MINIMUM_SCORE_STEP + 1e-9
    ]
    changes: list[dict[str, object]] = []
    if ungrounded and CITE_LINE not in system_prompt:
        changes.append(
            {
                "path": SYSTEM_PROMPT,
                "value": f"{system_prompt.rstrip()}\n{CITE_LINE}".lstrip("\n"),
                "explanation": "Fake proposer: replies failed grounding, so ask for citations.",
                "evidence": ungrounded,
            }
        )
    if near_misses:
        changes.append(
            {
                "path": MINIMUM_SCORE,
                "value": round(max(minimum_score - MINIMUM_SCORE_STEP, 0), 2),
                "explanation": (
                    "Fake proposer: Chunks were excluded just under the Minimum Score, so lower it."
                ),
                "evidence": near_misses,
            }
        )
    gaps = [
        {
            "topic": GAP_TOPIC,
            "explanation": "Fake proposer: the reply failed its Live Verdict and cited no Chunk.",
            "evidence": [label],
        }
        for label, header in headers
        if FAILED_LIVE_VERDICT in header and NOTHING_CITED in header
    ]
    explanation = (
        f"Fake proposer: {len(ungrounded)} replies failed grounding."
        if ungrounded
        else "Fake proposer: no evidence failed grounding."
    )
    proposal = {"changes": changes, "gaps": gaps, "overall_explanation": explanation}
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, proposal)])
