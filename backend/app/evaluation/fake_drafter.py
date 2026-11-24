"""The deterministic drafting path of the fake chat model and the Demo model.

Asked to draft Judging guidance (a structured-output call whose output schema is the ``Draft``),
they answer by rule instead of by meaning, so tests, ``docker compose`` and the demo seed are
deterministic and free, and a draft visibly changes the fake judge's Verdicts:

- the reviews where the Editor passed an answer the Evaluation Model failed on
  ``answers_question`` get ``PARTIAL_RULE``, the rule the fake judge follows
  (``app.evaluation.fake_judge``);
- every other review gets ``OTHER_RULE``.

The draft keeps the current guidance and adds each rule it lacks. They read only the lines the
job writes at the top of each review, before its first data block, and the current guidance an
Owner saved: never a Visitor's or an Editor's text, so nothing in a review can change the draft.
"""

import re

from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo

from app.evaluation.drafter import (
    CHECK_LINE,
    EDITOR_LINE,
    GUIDANCE_CLOSE,
    GUIDANCE_OPEN,
    MODEL_LINE,
)
from app.evaluation.fake_judge import request_text

PARTIAL_RULE = "Partial answers that say what they don't cover pass."
OTHER_RULE = "Judge each verdict by its own check alone."

# A review's id and the lines before its first data block.
_REVIEW = re.compile(r"^<<<REVIEW (R\d+)>>>\n(.*?)^<<<", re.S | re.M)
_GUIDANCE = re.compile(re.escape(GUIDANCE_OPEN) + "\n(.*?)\n" + re.escape(GUIDANCE_CLOSE), re.S)
_PARTIAL = f"{CHECK_LINE}answers_question\n{MODEL_LINE}fail\n{EDITOR_LINE}pass\n"


def is_drafting(info: AgentInfo) -> bool:
    """Whether the model is asked to draft guidance: its output schema holds ``explanation``
    and ``guidance``."""
    return any(
        {"explanation", "guidance"} <= tool.parameters_json_schema.get("properties", {}).keys()
        for tool in info.output_tools
    )


def fake_draft(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    """The fake drafter's answer: its structured-output tool called with the draft."""
    request = request_text(messages)
    found = _GUIDANCE.search(request)
    current = found.group(1).strip() if found else ""
    partial: list[str] = []
    other: list[str] = []
    for label, header in _REVIEW.findall(request):
        (partial if header.startswith(_PARTIAL) else other).append(label)
    lines = [current] if current else []
    explanation: list[dict[str, object]] = []
    for rule, labels in ((PARTIAL_RULE, partial), (OTHER_RULE, other)):
        if not labels:
            continue
        if rule not in current:
            lines.append(rule)
        explanation.append({"part": f"Fake drafter: {rule}", "reviews": labels})
    draft = {"guidance": "\n".join(lines), "explanation": explanation}
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, draft)])
