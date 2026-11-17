"""The deterministic proposing path of the fake chat model and the Demo model.

Asked to propose a Suggestion (a structured-output call whose output schema is the
``Proposal``), they answer by rule instead of by meaning, so tests, ``docker compose`` and the
demo seed are deterministic and free: when any piece of evidence failed grounding, they suggest
adding one line to the system prompt, ``CITE_LINE``, citing those pieces; otherwise they suggest
no change. They read only the lines the run itself writes at the top of each evidence block,
never the Visitor's text, so nothing a Visitor writes can change what they propose.
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
    EVIDENCE_CLOSE,
    QUESTION_OPEN,
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_CLOSE,
    SYSTEM_PROMPT_OPEN,
)

CITE_LINE = "Always cite the passage you used."
# What the run writes at the top of the evidence of a reply that failed grounding.
GROUNDING_FAILED = "Grounding: fail"

_EVIDENCE = re.compile(
    r"<<<EVIDENCE (E\d+)>>>\n(.*?)" + re.escape(QUESTION_OPEN) + ".*?" + re.escape(EVIDENCE_CLOSE),
    re.S,
)
_SYSTEM_PROMPT = re.compile(
    re.escape(SYSTEM_PROMPT_OPEN) + "\n(.*?)\n" + re.escape(SYSTEM_PROMPT_CLOSE), re.S
)


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


def fake_proposal(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    """The fake proposer's answer: its structured-output tool called with the Proposal."""
    request = _request(messages)
    found = _SYSTEM_PROMPT.search(request)
    system_prompt = found.group(1) if found else ""
    ungrounded = [
        label
        for label, header in _EVIDENCE.findall(request)
        if any(line.startswith(GROUNDING_FAILED) for line in header.splitlines())
    ]
    if not ungrounded or CITE_LINE in system_prompt:
        proposal: dict[str, object] = {
            "changes": [],
            "overall_explanation": "Fake proposer: no evidence failed grounding.",
        }
    else:
        suggested = f"{system_prompt.rstrip()}\n{CITE_LINE}".lstrip("\n")
        proposal = {
            "changes": [
                {
                    "path": SYSTEM_PROMPT,
                    "value": suggested,
                    "explanation": "Fake proposer: replies failed grounding, so ask for citations.",
                    "evidence": ungrounded,
                }
            ],
            "overall_explanation": f"Fake proposer: {len(ungrounded)} replies failed grounding.",
        }
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, proposal)])
