"""``run_turn``: one turn of a Conversation, as an async stream of events.

It knows nothing about HTTP, the Playground or the widget: callers give it the Conversation's
remembered turns, the AgentConfig, the Instructions text, the Visitor input, the chat model
(from the model gateway) and a ``retrieve`` function bound to the Project. When retrieval finds
no Chunk at or above the minimum score, the turn is the Agent's fallback text and the model
isn't asked. The Pydantic AI agent it builds registers no tools (ADR-0007).

The turn streams ``TokenEvent``s as the answer arrives, then a ``CitationEvent`` for each Chunk
the answer cites (``app.runtime.citations``), then one ``DoneEvent``. A model that supports
structured output is asked for a ``CitedAnswer`` through the provider's native JSON schema
output (not an output tool), and its answer text is streamed as the JSON arrives; any other
model answers in text, and its citations are the labels written in it.
"""

from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass, field

from pydantic_ai import Agent, NativeOutput
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models import Model
from pydantic_ai.usage import RunUsage

from app.agents.config import AgentConfig, Retrieval
from app.retrieval.service import Candidate, Excluded, RetrievalResult
from app.runtime.citations import CitedAnswer, labels_in, resolve
from app.runtime.prompt import Turn, chunk_label, data_blocks, history

Retrieve = Callable[[str, Retrieval], Awaitable[RetrievalResult]]


@dataclass(frozen=True)
class TokenEvent:
    text: str


@dataclass(frozen=True)
class CitationEvent:
    """The answer cites ``chunk``, which the model was given labelled ``label``."""

    label: str
    chunk: Candidate


@dataclass(frozen=True)
class DoneEvent:
    """The end of the turn: the full answer, token usage, the Chunks the model was given and
    the Chunks retrieval left out. ``fallback`` is true when no Chunk reached the minimum score,
    so the answer is the fallback text and the model wasn't asked."""

    answer: str
    input_tokens: int
    output_tokens: int
    retrieved: list[Candidate]
    excluded: list[Excluded]
    fallback: bool = False
    cited: list[Candidate] = field(default_factory=list)


TurnEvent = TokenEvent | CitationEvent | DoneEvent


@dataclass
class _Streamed:
    """What a model call streamed, filled in as it streams."""

    text: str = ""
    labels: list[str] = field(default_factory=list)
    usage: RunUsage = field(default_factory=RunUsage)


async def _stream_text(
    model: Model, question: str, messages: list[ModelMessage], streamed: _Streamed
) -> AsyncIterator[str]:
    async with Agent(model).run_stream(question, message_history=messages) as result:
        async for text in result.stream_text(delta=True, debounce_by=None):
            streamed.text += text
            yield text
        streamed.usage = result.usage
    streamed.labels = labels_in(streamed.text)


async def _stream_structured(
    model: Model, question: str, messages: list[ModelMessage], streamed: _Streamed
) -> AsyncIterator[str]:
    agent = Agent(model, output_type=NativeOutput(CitedAnswer))
    async with agent.run_stream(question, message_history=messages) as result:
        async for partial in result.stream_output(debounce_by=None):
            # A partly streamed JSON string only ever grows, so the new text is its tail.
            delta = partial.answer[len(streamed.text) :]
            if delta:
                streamed.text += delta
                yield delta
            streamed.labels = partial.citations
        streamed.usage = result.usage


async def run_turn(
    turns: Sequence[Turn],
    config: AgentConfig,
    instructions: str,
    visitor_input: str,
    *,
    model: Model,
    retrieve: Retrieve,
) -> AsyncIterator[TurnEvent]:
    retrieved = await retrieve(visitor_input, config.retrieval)
    if not retrieved.candidates:
        # Nothing relevant was found: say so in the Agent's words instead of letting it guess.
        fallback_text = config.behaviour.fallback_text
        yield TokenEvent(fallback_text)
        yield DoneEvent(
            answer=fallback_text,
            input_tokens=0,
            output_tokens=0,
            retrieved=[],
            excluded=retrieved.excluded,
            fallback=True,
        )
        return
    messages = history(instructions, config.behaviour.system_prompt, turns)
    question = data_blocks(retrieved.candidates, visitor_input)
    structured = model.profile.get("supports_json_schema_output", False)
    stream = _stream_structured if structured else _stream_text
    streamed = _Streamed()
    async for text in stream(model, question, messages, streamed):
        yield TokenEvent(text)
    cited = resolve(streamed.labels, retrieved.candidates)
    for chunk in cited:
        yield CitationEvent(chunk_label(chunk.rank), chunk)
    yield DoneEvent(
        answer=streamed.text,
        input_tokens=streamed.usage.input_tokens,
        output_tokens=streamed.usage.output_tokens,
        retrieved=retrieved.candidates,
        excluded=retrieved.excluded,
        cited=cited,
    )
