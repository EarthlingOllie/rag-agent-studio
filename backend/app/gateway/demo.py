"""The demo provider's chat model: deterministic, offline, and labelled as a demo.

The seeded demo Organisation answers with it when no real Provider Credential is configured,
so the demo needs no API keys. It is a Pydantic AI ``FunctionModel`` that reads the question's
data blocks (``app.runtime.prompt``) and answers with the first retrieved Chunk, quoted and
cited, always prefixed with a label so nobody mistakes it for a real model. Both the live and
the fake adapters build it, so the demo looks the same in ``docker compose`` and in AWS.

The provider's second model, ``demo-naive``, is the Attack evaluation suite's Naive model behind
its own label: it obeys whatever instructions it finds (decoding base64 and reciting its system
text when asked to), so the attack panel's Guardrail demo Agent shows what the Guardrails stop
rather than a model refusing. Its replies stream in short pieces, as the suite's do.
"""

import re
from collections.abc import AsyncIterator

from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models import Model
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.evals.naive_model import PIECE, naive_answer
from app.runtime.prompt import CHUNKS_CLOSE, CHUNKS_OPEN

DEMO_LABEL = "Demo model (canned answer, not AI)"
NAIVE_MODEL = "demo-naive"
NAIVE_LABEL = "Naive demo model (obeys injected instructions, not AI)"
NOTHING_FOUND = f"{DEMO_LABEL}: the Knowledge Base has nothing on that."
# The first excerpt of the Chunks block: "[C1] <document name>" on one line, then its text.
_FIRST_EXCERPT = re.compile(
    re.escape(CHUNKS_OPEN)
    + r"\n\[(C\d+)\] ([^\n]+)\n(.+?)(?:\n\n\[C\d+\] |\n"
    + re.escape(CHUNKS_CLOSE)
    + ")",
    re.DOTALL,
)


def _question(messages: list[ModelMessage]) -> str:
    """The text of the last user prompt: the question with its data blocks."""
    prompts = [
        part.content
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, UserPromptPart) and isinstance(part.content, str)
    ]
    return prompts[-1] if prompts else ""


def demo_answer(messages: list[ModelMessage]) -> str:
    excerpt = _FIRST_EXCERPT.search(_question(messages))
    if excerpt is None:
        return NOTHING_FOUND
    label, document, text = excerpt.groups()
    return f"{DEMO_LABEL}: from {document} [{label}]: {' '.join(text.split())}"


def _reply(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    return ModelResponse(parts=[TextPart(demo_answer(messages))])


async def _stream(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
    words = demo_answer(messages).split(" ")
    for index, word in enumerate(words):
        yield word if index == 0 else f" {word}"


async def _naive_stream(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
    answer = f"{NAIVE_LABEL}: {naive_answer(messages)}"
    for start in range(0, len(answer), PIECE):
        yield answer[start : start + PIECE]


def demo_chat_model(model: str) -> Model:
    if model == NAIVE_MODEL:
        # The runtime always streams, so the naive model has only a streaming function.
        return FunctionModel(
            stream_function=_naive_stream,
            model_name=model,
            profile={"supports_json_schema_output": False},
        )
    # Plain text, not structured output: the runtime reads the [C1] citation from the text.
    return FunctionModel(
        _reply,
        stream_function=_stream,
        model_name=model,
        profile={"supports_json_schema_output": False},
    )
