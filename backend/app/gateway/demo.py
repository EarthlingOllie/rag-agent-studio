"""The demo provider's chat model: deterministic, offline, and labelled as a demo.

The seeded demo Organisation answers with it when no real Provider Credential is configured,
so the demo needs no API keys. It is a Pydantic AI ``FunctionModel`` that reads the question's
data blocks (``app.runtime.prompt``) and answers with the first retrieved Chunk, quoted and
cited, always prefixed with a label so nobody mistakes it for a real model. Both the live and
the fake adapters build it, so the demo looks the same in ``docker compose`` and in AWS.

In Agentic Retrieval Mode (offered Knowledge Search, spec 13) the demo model makes one Knowledge
Search with the Visitor's question, then answers as above from the first Chunk the Search
returned, so an Agentic Agent works without a real Provider Credential too. Asked to judge an
Evaluation Run's answer, it judges by rule, as the fake chat model does
(``app.evaluation.fake_judge``), so the seeded Runs are deterministic.

The provider's second model, ``demo-naive``, is the Attack evaluation suite's Naive model behind
its own label: it obeys whatever instructions it finds (decoding base64 and reciting its system
text when asked to), so the attack panel's Guardrail demo Agent shows what the Guardrails stop
rather than a model refusing. Its replies stream in short pieces, as the suite's do. Offered
Knowledge Search, it searches as the suite's Naive model does: with the Visitor's question.
"""

import json
import re
from collections.abc import AsyncIterator

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models import Model
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, DeltaToolCalls, FunctionModel

from app.evals.naive_model import PIECE, naive_answer, naive_search
from app.evaluation.fake_judge import fake_judgement, is_judging
from app.runtime.prompt import CHUNKS_CLOSE, CHUNKS_OPEN, INPUT_CLOSE, INPUT_OPEN, KNOWLEDGE_SEARCH

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
_VISITOR_BLOCK = re.compile(f"{re.escape(INPUT_OPEN)}\n(.*?)\n{re.escape(INPUT_CLOSE)}", re.DOTALL)


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


def _search_results(messages: list[ModelMessage]) -> list[str]:
    """What the reply's Knowledge Searches returned, in order: the tool results after the
    question."""
    results: list[str] = []
    for message in messages:
        if not isinstance(message, ModelRequest):
            continue
        for part in message.parts:
            if isinstance(part, UserPromptPart):
                results = []  # a new question: earlier turns' Searches aren't this reply's
            elif isinstance(part, ToolReturnPart):
                results.append(str(part.content))
    return results


def demo_search(messages: list[ModelMessage], info: AgentInfo) -> str | None:
    """The query of the demo model's one Knowledge Search, when it is offered the tool and
    hasn't searched yet: the Visitor's question (the text of the Visitor input block)."""
    offered = any(tool.name == KNOWLEDGE_SEARCH for tool in info.function_tools)
    if not offered or _search_results(messages):
        return None
    question = _question(messages)
    block = _VISITOR_BLOCK.findall(question)
    return block[-1] if block else question


def demo_answer(messages: list[ModelMessage]) -> str:
    """The first Chunk the Search returned, or else the first retrieved up front, quoted."""
    searched = _search_results(messages)
    excerpt = _FIRST_EXCERPT.search(searched[0] if searched else _question(messages))
    if excerpt is None:
        return NOTHING_FOUND
    label, document, text = excerpt.groups()
    return f"{DEMO_LABEL}: from {document} [{label}]: {' '.join(text.split())}"


def _reply(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    if is_judging(info):
        return fake_judgement(messages, info)
    query = demo_search(messages, info)
    if query is not None:
        return ModelResponse(parts=[ToolCallPart(KNOWLEDGE_SEARCH, {"query": query})])
    return ModelResponse(parts=[TextPart(demo_answer(messages))])


def _search_call(query: str) -> DeltaToolCalls:
    args = json.dumps({"query": query})
    return {0: DeltaToolCall(name=KNOWLEDGE_SEARCH, json_args=args, tool_call_id="search-1")}


async def _stream(
    messages: list[ModelMessage], info: AgentInfo
) -> AsyncIterator[str | DeltaToolCalls]:
    query = demo_search(messages, info)
    if query is not None:
        yield _search_call(query)
        return
    words = demo_answer(messages).split(" ")
    for index, word in enumerate(words):
        yield word if index == 0 else f" {word}"


async def _naive_stream(
    messages: list[ModelMessage], info: AgentInfo
) -> AsyncIterator[str | DeltaToolCalls]:
    query = naive_search(messages, [tool.name for tool in info.function_tools])
    if query is not None:
        yield _search_call(query)
        return
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
