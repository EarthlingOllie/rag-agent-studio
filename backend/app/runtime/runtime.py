"""``run_turn``: one turn of a Conversation, as an async stream of events.

It knows nothing about HTTP, the Playground or the widget: callers give it the Conversation's
turns (it keeps the last ``remembered_turns`` of them), the AgentConfig, the Instructions text,
the Visitor input, the chat model (from the model gateway) and a ``retrieve`` function bound to
the Project. When retrieval finds no Chunk at or above the minimum score, the turn is the Agent's
fallback text and the model isn't asked. The Pydantic AI agent it builds registers no tools
(ADR-0007).

The turn streams ``TokenEvent``s as the answer arrives, then a ``CitationEvent`` for each Chunk
the answer cites (``app.runtime.citations``), then one ``DoneEvent``. The reply keeps one record
of the Chunks given to the model (``app.runtime.prompt.GivenChunks``), which assigns their Chunk
labels and resolves the Citations. If the model's provider
fails (or the Embedding Model's, retrieving), the turn ends instead with an ``ErrorEvent`` saying
why (``app.runtime.errors``), whatever was streamed before it. A model that supports
structured output is asked for a ``CitedAnswer`` through the provider's native JSON schema
output (not an output tool), and its answer text is streamed as the JSON arrives; any other
model answers in text, and its citations are the labels written in it.

Every model call carries a fresh Canary token in its preamble, and the answer streams through a
``CanaryFilter``. If the canary starts to appear, the model stream is stopped, nothing more of
the answer is sent, and a ``ReplaceEvent`` carrying the fallback text replaces what was sent; the
``DoneEvent``'s answer is then the fallback text. A completed answer is checked again for an
encoded canary, which is logged and flagged but can't be un-sent.

With ``cautioned`` (the input Guardrail's warn mode flagged the message), the prompt carries a
caution block after the system prompt (``app.runtime.prompt.CAUTION``).
"""

import logging
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable, Sequence
from contextlib import aclosing
from dataclasses import dataclass, field

from pydantic_ai import Agent, NativeOutput
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import RunUsage

from app.agents.config import AgentConfig, Retrieval
from app.guardrails.canary import CanaryFilter, encoded_leak, new_canary
from app.guardrails.outcomes import GuardrailOutcome
from app.retrieval.service import Candidate, Excluded, RetrievalResult
from app.runtime.citations import CitedAnswer, labels_in, resolve
from app.runtime.errors import PROVIDER_ERRORS, ErrorEvent, provider_error
from app.runtime.prompt import GivenChunks, Turn, data_blocks, history

logger = logging.getLogger(__name__)

Retrieve = Callable[[str, Retrieval], Awaitable[RetrievalResult]]


@dataclass(frozen=True)
class TokenEvent:
    text: str


@dataclass(frozen=True)
class ReplaceEvent:
    """The answer leaked the Canary token: what was sent so far is replaced by ``text``."""

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
    so the answer is the fallback text and the model wasn't asked. ``guardrail_outcomes`` holds
    what the Guardrails decided (a canary leak replaced or flagged, a question blocked)."""

    answer: str
    input_tokens: int
    output_tokens: int
    retrieved: list[Candidate]
    excluded: list[Excluded]
    fallback: bool = False
    cited: list[Candidate] = field(default_factory=list)
    # True when the input Guardrail blocked the question (``app.guardrails.pipeline``): the
    # answer is the refusal text, and nothing was retrieved and no model was asked.
    refused: bool = False
    guardrail_outcomes: list[GuardrailOutcome] = field(default_factory=list)


TurnEvent = TokenEvent | ReplaceEvent | CitationEvent | DoneEvent | ErrorEvent

CANARY_REPLACED = "The reply contained the canary token, so it was cut off and replaced."
CANARY_ENCODED = "The reply contained the canary token, encoded ({encoding})"


@dataclass
class _Streamed:
    """What a model call streamed, filled in as it streams."""

    text: str = ""
    labels: list[str] = field(default_factory=list)
    usage: RunUsage = field(default_factory=RunUsage)


async def _stream_text(
    model: Model,
    question: str,
    messages: list[ModelMessage],
    settings: ModelSettings,
    streamed: _Streamed,
) -> AsyncGenerator[str]:
    async with Agent(model).run_stream(
        question, message_history=messages, model_settings=settings
    ) as result:
        async for text in result.stream_text(delta=True, debounce_by=None):
            streamed.text += text
            streamed.usage = result.usage
            yield text
        streamed.usage = result.usage
    streamed.labels = labels_in(streamed.text)


async def _stream_structured(
    model: Model,
    question: str,
    messages: list[ModelMessage],
    settings: ModelSettings,
    streamed: _Streamed,
) -> AsyncGenerator[str]:
    agent = Agent(model, output_type=NativeOutput(CitedAnswer))
    async with agent.run_stream(
        question, message_history=messages, model_settings=settings
    ) as result:
        async for partial in result.stream_output(debounce_by=None):
            # A partly streamed JSON string only ever grows, so the new text is its tail.
            delta = partial.answer[len(streamed.text) :]
            streamed.labels = partial.citations
            if delta:
                streamed.text += delta
                streamed.usage = result.usage
                yield delta
        streamed.usage = result.usage


async def run_turn(
    turns: Sequence[Turn],
    config: AgentConfig,
    instructions: str,
    visitor_input: str,
    *,
    model: Model,
    retrieve: Retrieve,
    cautioned: bool = False,
) -> AsyncIterator[TurnEvent]:
    try:
        async with aclosing(
            _turn(
                turns,
                config,
                instructions,
                visitor_input,
                model=model,
                retrieve=retrieve,
                cautioned=cautioned,
            )
        ) as events:
            async for event in events:
                yield event
    except PROVIDER_ERRORS as error:
        # The provider failed (retrieving or answering): end the turn with why, and no answer.
        yield provider_error(error, model.model_name)


async def _turn(
    turns: Sequence[Turn],
    config: AgentConfig,
    instructions: str,
    visitor_input: str,
    *,
    model: Model,
    retrieve: Retrieve,
    cautioned: bool,
) -> AsyncGenerator[TurnEvent]:
    behaviour = config.behaviour
    retrieved = await retrieve(visitor_input, config.retrieval)
    if not retrieved.candidates:
        # Nothing relevant was found: say so in the Agent's words instead of letting it guess.
        fallback_text = behaviour.fallback_text
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
    remembered = list(turns)[-behaviour.remembered_turns :] if behaviour.remembered_turns else []
    canary = new_canary()
    messages = history(
        instructions, behaviour.system_prompt, remembered, canary=canary, cautioned=cautioned
    )
    # The reply's record of the Chunks given to the model: it labels them and resolves Citations.
    given = GivenChunks()
    question = data_blocks(retrieved.candidates, visitor_input, given)
    settings = ModelSettings(
        temperature=behaviour.temperature, max_tokens=behaviour.max_output_tokens
    )
    structured = model.profile.get("supports_json_schema_output", False)
    stream = _stream_structured if structured else _stream_text
    streamed = _Streamed()
    canary_filter = CanaryFilter(canary)
    async with aclosing(stream(model, question, messages, settings, streamed)) as texts:
        async for text in texts:
            safe = canary_filter.feed(text)
            if canary_filter.leaked:
                # Leaving the loop closes the stream, which stops the model.
                break
            if safe:
                yield TokenEvent(safe)
    if canary_filter.leaked:
        yield ReplaceEvent(behaviour.fallback_text)
        yield DoneEvent(
            answer=behaviour.fallback_text,
            input_tokens=streamed.usage.input_tokens,
            output_tokens=streamed.usage.output_tokens,
            retrieved=retrieved.candidates,
            excluded=retrieved.excluded,
            guardrail_outcomes=[GuardrailOutcome("canary", "leak", "replaced", CANARY_REPLACED)],
        )
        return
    rest = canary_filter.finish()
    if rest:
        yield TokenEvent(rest)
    outcomes = []
    encoding = encoded_leak(streamed.text, canary)
    if encoding is not None:
        reason = CANARY_ENCODED.format(encoding=encoding)
        logger.warning(reason)
        outcomes.append(GuardrailOutcome("canary", "leak", "flagged", f"{reason}."))
    cited = resolve(streamed.labels, given)
    for entry in cited:
        yield CitationEvent(entry.label, entry.chunk)
    yield DoneEvent(
        answer=streamed.text,
        input_tokens=streamed.usage.input_tokens,
        output_tokens=streamed.usage.output_tokens,
        retrieved=retrieved.candidates,
        excluded=retrieved.excluded,
        cited=[entry.chunk for entry in cited],
        guardrail_outcomes=outcomes,
    )
