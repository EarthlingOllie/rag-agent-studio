"""The deterministic judging path of the fake chat model and the Demo model.

Asked to judge an answer (a structured-output call whose output schema is the ``Judgement``),
they answer by rule instead of by meaning, so tests, ``docker compose`` and the demo seed are
deterministic and free, yet the judge can fail:

- the Reference answer passes when the answer contains its key phrase: the first phrase in
  double quotes in the Reference answer, or else the whole Reference answer (letter case and
  spacing aside);
- grounding passes when the answer cited at least one Chunk;
- answers_question (a Live Verdict's) passes when the answer shares a key phrase with the
  question: the phrases in double quotes in the question, or else its words of five letters or
  more (letter case and spacing aside);
- with Judging guidance holding ``PARTIAL_ANSWERS_PASS`` (letter case and spacing aside), an
  answer that fails ``answers_question`` by key phrase passes when it says what it doesn't cover
  (spec 19's one guidance rule, so a guidance change can visibly change Verdicts).
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
    GUIDANCE_HEADING,
    JUDGE_LINE,
    QUESTION_CLOSE,
    QUESTION_OPEN,
    REFERENCE_CLOSE,
    REFERENCE_OPEN,
)

# The scripted phrase: guidance holding it lets partial answers pass ``answers_question``.
PARTIAL_ANSWERS_PASS = "partial answers that say what they don't cover pass"  # noqa: S105
# An answer saying what it doesn't cover.
_SAYS_UNCOVERED = re.compile(r"\b(?:doesn't|does not|don't|do not|can't|cannot) cover\b")

_QUOTED = re.compile(r"[\"“]([^\"”]+)[\"”]")
# A word of the question long enough to be one of its key phrases.
_KEY_WORD = re.compile(r"[^\W\d_]{5,}")


def is_judging(info: AgentInfo) -> bool:
    """Whether the model is asked to judge an answer: its output schema holds ``grounding``."""
    return any(
        "grounding" in tool.parameters_json_schema.get("properties", {})
        for tool in info.output_tools
    )


def request_text(messages: list[ModelMessage]) -> str:
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


def question_phrases(question: str) -> list[str]:
    """The phrases an answer must share one of for the fake judge to pass ``answers_question``."""
    quoted = _QUOTED.findall(question)
    if quoted:
        return [_normal(phrase) for phrase in quoted]
    return [word.lower() for word in _KEY_WORD.findall(question)]


def _answers_question(question: str, answer: str, guidance: str) -> dict[str, object]:
    shared = next((p for p in question_phrases(question) if p in answer), None)
    if shared is None and PARTIAL_ANSWERS_PASS in guidance and _SAYS_UNCOVERED.search(answer):
        return {
            "passed": True,
            "reason": (
                "Fake judge: a partial answer that says what it doesn't cover passes, "
                "as the guidance says."
            ),
        }
    if shared is None:
        return {
            "passed": False,
            "reason": "Fake judge: the answer shares no key phrase with the question.",
        }
    return {
        "passed": True,
        "reason": f"Fake judge: the answer shares “{shared}” with the question.",
    }


def fake_judgement(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    """The fake judge's answer: its structured-output tool called with the Verdicts asked."""
    request = request_text(messages)
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
    if "answers_question" in asked:
        question = _block(request, QUESTION_OPEN, QUESTION_CLOSE) or ""
        instructions = info.instructions or ""
        guidance = instructions.partition(GUIDANCE_HEADING)[2]
        judgement["answers_question"] = _answers_question(question, answer, _normal(guidance))
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, judgement)])
