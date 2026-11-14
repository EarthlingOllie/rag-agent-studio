"""The deterministic judging path of the fake chat model and the Demo model.

Asked to judge an answer (a structured-output call whose output schema is the ``Judgement``),
they answer by rule instead of by meaning, so tests, ``docker compose`` and the demo seed are
deterministic and free, yet the judge can fail:

- the Reference answer passes when the answer contains its key phrase: the first phrase in
  double quotes in the Reference answer, or else the whole Reference answer (letter case and
  spacing aside);
- grounding passes when the answer cited at least one Chunk.
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

from app.evaluation.judge import (
    ANSWER_CLOSE,
    ANSWER_OPEN,
    CITED_CLOSE,
    CITED_OPEN,
    JUDGE_LINE,
    REFERENCE_CLOSE,
    REFERENCE_OPEN,
)

_QUOTED = re.compile(r"[\"“]([^\"”]+)[\"”]")


def is_judging(info: AgentInfo) -> bool:
    """Whether the model is asked to judge an answer: its output schema holds ``grounding``."""
    return any(
        "grounding" in tool.parameters_json_schema.get("properties", {})
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


def _block(text: str, opening: str, closing: str) -> str | None:
    found = re.search(f"{re.escape(opening)}\n(.*?)\n?{re.escape(closing)}", text, re.S)
    return None if found is None else found.group(1)


def _normal(text: str) -> str:
    return " ".join(text.lower().split())


def key_phrase(reference_answer: str) -> str:
    """The phrase an answer must contain for the fake judge to pass its Reference answer."""
    quoted = _QUOTED.search(reference_answer)
    return _normal(quoted.group(1) if quoted else reference_answer)


def fake_judgement(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    """The fake judge's answer: its structured-output tool called with the Verdicts asked."""
    request = _request(messages)
    answer = _normal(_block(request, ANSWER_OPEN, ANSWER_CLOSE) or "")
    asked = request.rsplit(JUDGE_LINE, 1)[-1]
    judgement: dict[str, dict[str, object]] = {}
    reference = _block(request, REFERENCE_OPEN, REFERENCE_CLOSE)
    if reference is not None:
        phrase = key_phrase(reference)
        passed = phrase in answer
        judgement["reference_answer"] = {
            "passed": passed,
            "reason": f"Fake judge: the answer {'contains' if passed else 'lacks'} “{phrase}”.",
        }
    if "grounding" in asked:
        cited = "[C" in (_block(request, CITED_OPEN, CITED_CLOSE) or "")
        judgement["grounding"] = {
            "passed": cited,
            "reason": (
                "Fake judge: the answer cites the knowledge base."
                if cited
                else "Fake judge: the answer cites nothing to support it."
            ),
        }
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, judgement)])
