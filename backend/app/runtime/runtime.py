"""``run_turn``: one turn of a Conversation, as an async stream of events.

It knows nothing about HTTP, the Playground or the widget: callers give it the Conversation's
turns (it keeps the last ``remembered_turns`` of them), the AgentConfig, the Instructions text,
the Visitor input, the chat model (from the model gateway) and a ``retrieve`` function bound to
the Project. When retrieval finds no Chunk at or above the minimum score, the turn is the Agent's
fallback text and the model isn't asked. In Automatic Retrieval Mode the Pydantic AI agent it
builds registers no tools (ADR-0007).

In Agentic Retrieval Mode (ADR-0015) nothing is retrieved up front. The agent registers exactly
one tool, Knowledge Search, whose only argument is the query: it runs ``retrieve`` with the
Agent's Retrieval settings and returns the Chunks it found as a spotlighted, labelled data block
(``app.runtime.prompt.search_results``). A ``SearchEvent`` is streamed as each Search starts, and
the ``DoneEvent`` lists the reply's Searches (``Searched``). Searches run one at a time, even
when the model asks for several at once. Tool calls finish before the answer streams: the text
of each model response is held until the response ends, so text a model writes before calling
the tool is never sent. Token use is summed over every model call of the reply.

A reply makes at most the Agent's Search limit of Searches: a call beyond it searches nothing,
streams no ``SearchEvent`` and tells the model "search limit reached; answer from what you
have"; it is recorded as a ``Searched`` with ``limit_refused``, so the Trace shows the limit was
hit. If the model searched and no Search found a Chunk reaching the minimum score, the model's
answer is discarded before any of it streams, and the reply is the Agent's fallback text with
``fallback`` true. A reply that made no Search (a greeting) is never a fallback.

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
encoded canary, which is logged and flagged but can't be un-sent. In Agentic mode each search
query is checked for the canary (in any form) before it runs: a query carrying it is never run
or recorded, and the reply ends as a canary leak, with the fallback text and a ``replaced``
Guardrail outcome.

With ``cautioned`` (the input Guardrail's warn mode flagged the message), the prompt carries a
caution block after the system prompt (``app.runtime.prompt.CAUTION``).
"""

import asyncio
import dataclasses
import itertools
import logging
import time
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable, Sequence
from contextlib import aclosing, suppress
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError
from pydantic_ai import Agent, NativeOutput, Tool
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models import Model
from pydantic_ai.result import AgentStream
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import RunUsage

from app.agents.config import AgentConfig, Retrieval, RetrievalMode
from app.guardrails.canary import CanaryFilter, carries_canary, encoded_leak, new_canary
from app.guardrails.outcomes import GuardrailOutcome
from app.retrieval.service import Candidate, Excluded, RetrievalResult
from app.runtime.citations import CitedAnswer, labels_in, resolve
from app.runtime.errors import PROVIDER_ERRORS, ErrorEvent, provider_error
from app.runtime.prompt import (
    KNOWLEDGE_SEARCH,
    KNOWLEDGE_SEARCH_DESCRIPTION,
    SEARCH_LIMIT_REACHED,
    GivenChunks,
    Turn,
    data_blocks,
    history,
    search_results,
    visitor_block,
)

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
class SearchEvent:
    """A Knowledge Search starts: the reply's ``order``-th (from 1), for the model's ``query``."""

    query: str
    order: int


@dataclass(frozen=True)
class Searched:
    """One Knowledge Search the reply made: its query, how long it took, the Chunks it found
    (each ranked by the number in its Chunk label, which continues across the reply) and the
    Chunks it left out. ``limit_refused`` marks a call refused by the Search limit."""

    order: int
    query: str
    latency_ms: int
    candidates: list[Candidate]
    excluded: list[Excluded]
    limit_refused: bool = False


@dataclass(frozen=True)
class DoneEvent:
    """The end of the turn: the full answer, token usage, the Chunks the model was given and
    the Chunks retrieval left out. ``fallback`` is true when no Chunk reached the minimum score,
    so the answer is the fallback text: in Automatic Retrieval Mode the model wasn't asked; in
    Agentic mode it searched, found nothing, and its answer was discarded unsent.
    ``guardrail_outcomes`` holds what the Guardrails decided (a canary leak replaced or
    flagged, a question blocked)."""

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
    # In Agentic Retrieval Mode, the reply's Searches in order; ``retrieved`` is then every Chunk
    # given to the model, in label order, and ``excluded`` every Chunk the Searches left out.
    searches: list[Searched] = field(default_factory=list)

    @property
    def search_count(self) -> int:
        """How many Searches the reply ran: a call the Search limit refused searched nothing."""
        return sum(not search.limit_refused for search in self.searches)


TurnEvent = TokenEvent | ReplaceEvent | CitationEvent | SearchEvent | DoneEvent | ErrorEvent

CANARY_REPLACED = "The reply contained the canary token, so it was cut off and replaced."
CANARY_ENCODED = "The reply contained the canary token, encoded ({encoding})"
CANARY_IN_QUERY = "A search query contained the canary token, so the reply was replaced."


class _CanaryInQueryError(Exception):
    """The model wrote the Canary token into a Knowledge Search query: the reply ends."""


@dataclass
class _Streamed:
    """What a model call streamed, filled in as it streams."""

    text: str = ""
    labels: list[str] = field(default_factory=list)
    usage: RunUsage = field(default_factory=RunUsage)


async def _response_text(response: AgentStream[None, str]) -> AsyncGenerator[tuple[str, None]]:
    """A plain text model response's text, as it arrives."""
    async for text in response.stream_text(delta=True, debounce_by=None):
        yield text, None


async def _response_structured(
    response: AgentStream[None, CitedAnswer],
) -> AsyncGenerator[tuple[str, list[str] | None]]:
    """A structured model response's answer text as its JSON arrives, with the labels it cites
    so far. A response that calls a tool is no answer: its text isn't parsed."""
    answer = ""
    async for snapshot in response.stream_response(debounce_by=None):
        if snapshot.tool_calls or not snapshot.text:
            continue
        try:
            partial = await response.validate_response_output(snapshot, allow_partial=True)
        except (ValidationError, UnexpectedModelBehavior):
            # Not yet JSON, or the text part has only just started.
            continue
        # A partly streamed JSON string only ever grows, so the new text is its tail.
        yield partial.answer[len(answer) :], partial.citations
        answer = partial.answer
    if not response.response.tool_calls:
        final = await response.validate_response_output(response.response)
        yield final.answer[len(answer) :], final.citations


async def _stream_answer(
    model: Model,
    question: str,
    messages: list[ModelMessage],
    settings: ModelSettings,
    streamed: _Streamed,
    tools: list[Tool[None]],
    *,
    structured: bool,
) -> AsyncGenerator[str]:
    """The answer's text as it arrives, over every model call of the reply (each tool call is
    run, and the model called again, until it answers). A model that supports structured
    output is asked for a ``CitedAnswer``; any other model answers in text.

    With tools, the text of a model response is held until the response ends: a response that
    calls a tool is not the answer, so any text written before the call is never sent."""
    output = NativeOutput(CitedAnswer) if structured else str
    agent: Agent[None, Any] = Agent(model, output_type=output, tools=tools)
    async with agent.iter(question, message_history=messages, model_settings=settings) as run:
        nodes = aiter(run)
        while True:  # a run only ends with an answer, which returns below
            node = await anext(nodes)
            if Agent.is_model_request_node(node):
                async with node.stream(run.ctx) as response:
                    pieces = (
                        _response_structured(response) if structured else _response_text(response)
                    )
                    held: list[tuple[str, list[str] | None]] = []
                    async with aclosing(pieces) as response_pieces:
                        async for piece in response_pieces:
                            streamed.usage = response.usage
                            if tools:
                                held.append(piece)
                                continue
                            _take(streamed, piece)
                            if piece[0]:
                                yield piece[0]
                    streamed.usage = response.usage
                    if not response.response.tool_calls:
                        # The first response that calls no tool is the answer, as with
                        # ``run_stream``: the run isn't driven further (an empty answer stays
                        # empty rather than being retried).
                        for piece in held:
                            _take(streamed, piece)
                            if piece[0]:
                                yield piece[0]
                        if not structured:
                            streamed.labels = labels_in(streamed.text)
                        return


def _take(streamed: _Streamed, piece: tuple[str, list[str] | None]) -> None:
    text, labels = piece
    streamed.text += text
    if labels is not None:
        streamed.labels = labels


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def _knowledge_search(
    retrieve: Retrieve,
    settings: Retrieval,
    given: GivenChunks,
    searches: list[Searched],
    started: Callable[[SearchEvent], None],
    canary: str,
) -> Tool[None]:
    """Knowledge Search for one reply: the model writes the query; everything else comes from
    the Agent's Retrieval settings. Each Search is reported to ``started`` as it starts and
    recorded in ``searches`` once it ends. Once ``settings.search_limit`` Searches have run, a
    further call is refused: it searches nothing, and is recorded as refused.

    A query is model output, so it is checked for the reply's Canary token first: one that
    carries it is never run, reported or recorded (it would reach the Trace and the logs), and
    the reply ends (``_CanaryInQueryError``)."""

    # Numbered as they start: the model may ask for several Searches at once.
    orders = itertools.count(1)

    async def knowledge_search(query: str) -> str:
        if carries_canary(query, canary):
            raise _CanaryInQueryError
        order = next(orders)
        if order > settings.search_limit:
            searches.append(Searched(order, query, 0, [], [], limit_refused=True))
            return SEARCH_LIMIT_REACHED
        started(SearchEvent(query, order))
        began = time.perf_counter()
        found = await retrieve(query, settings)
        results = search_results(found.candidates, given)
        searches.append(
            Searched(
                order=order,
                query=query,
                latency_ms=_elapsed_ms(began),
                candidates=[
                    dataclasses.replace(chunk, rank=given.entry(chunk).number)
                    for chunk in found.candidates
                ],
                excluded=found.excluded,
            )
        )
        searches.sort(key=lambda search: search.order)
        return results

    return Tool(
        knowledge_search,
        name=KNOWLEDGE_SEARCH,
        description=KNOWLEDGE_SEARCH_DESCRIPTION,
        takes_ctx=False,
        # One Search at a time, even when the model asks for several at once: ``retrieve`` may
        # share one database session, which can't run two queries concurrently.
        sequential=True,
    )


def _found_nothing(given: GivenChunks, searches: list[Searched]) -> bool:
    """Whether the reply searched and no Search gave the model a Chunk: no Chunk reached the
    minimum score."""
    return bool(searches) and not given.entries()


def _searched_result(given: GivenChunks, searches: list[Searched]) -> RetrievalResult:
    """What the reply's Searches found, together: every Chunk given to the model, in label
    order, and every Chunk left out that no Search gave, once each."""
    candidates = [dataclasses.replace(entry.chunk, rank=entry.number) for entry in given.entries()]
    seen = {chunk.chunk_id for chunk in candidates}
    excluded: list[Excluded] = []
    for chunk in (chunk for search in searches for chunk in search.excluded):
        if chunk.chunk_id not in seen:
            seen.add(chunk.chunk_id)
            excluded.append(chunk)
    return RetrievalResult(candidates, excluded)


@dataclass(frozen=True)
class _Failed:
    error: Exception


async def _with_searches(
    texts: AsyncGenerator[str], queue: "asyncio.Queue[str | SearchEvent | _Failed | None]"
) -> AsyncGenerator[str | SearchEvent]:
    """The answer's text with the ``SearchEvent``s Knowledge Search puts on ``queue`` as they
    happen: the model is streamed in a task of its own, so a Search is reported when it starts,
    not when the answer does. Closing this stops the model."""

    async def pump() -> None:
        try:
            async with aclosing(texts):
                async for text in texts:
                    queue.put_nowait(text)
        except Exception as error:  # re-raised below, in the reply's own task
            queue.put_nowait(_Failed(error))
        else:
            queue.put_nowait(None)

    task = asyncio.create_task(pump())
    try:
        while (item := await queue.get()) is not None:
            if isinstance(item, _Failed):
                raise item.error
            yield item
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


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
    agentic = config.retrieval.mode is RetrievalMode.AGENTIC
    # The reply's record of the Chunks given to the model: it labels them and resolves Citations.
    given = GivenChunks()
    searches: list[Searched] = []
    queue: asyncio.Queue[str | SearchEvent | _Failed | None] = asyncio.Queue()
    canary = new_canary()
    if agentic:
        # No upfront search: the model searches with Knowledge Search, its one tool.
        retrieved = RetrievalResult([])
        search = _knowledge_search(
            retrieve, config.retrieval, given, searches, queue.put_nowait, canary
        )
        tools = [search]
        question = visitor_block(visitor_input)
    else:
        retrieved = await retrieve(visitor_input, config.retrieval)
        tools = []
        question = data_blocks(retrieved.candidates, visitor_input, given)
    if not agentic and not retrieved.candidates:
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
    messages = history(
        instructions,
        behaviour.system_prompt,
        remembered,
        canary=canary,
        cautioned=cautioned,
        agentic=agentic,
    )
    settings = ModelSettings(
        temperature=behaviour.temperature, max_tokens=behaviour.max_output_tokens
    )
    structured = model.profile.get("supports_json_schema_output", False)
    streamed = _Streamed()
    canary_filter = CanaryFilter(canary)
    texts = _stream_answer(
        model, question, messages, settings, streamed, tools, structured=structured
    )
    items = _with_searches(texts, queue) if agentic else texts
    query_leaked = False
    try:
        async with aclosing(items) as stream_items:
            async for text in stream_items:
                if isinstance(text, SearchEvent):
                    yield text
                    continue
                if _found_nothing(given, searches):
                    # The answer only streams once every Search has run, so it is discarded
                    # before any of it is sent. Leaving the loop stops the model.
                    break
                safe = canary_filter.feed(text)
                if canary_filter.leaked:
                    # Leaving the loop closes the stream, which stops the model.
                    break
                if safe:
                    yield TokenEvent(safe)
    except _CanaryInQueryError:
        # The run stopped at the query. No answer text streams before a Search, so nothing is
        # replaced: the Visitor gets the Fallback Text alone.
        query_leaked = True
    if agentic:
        retrieved = _searched_result(given, searches)
    if query_leaked:
        yield TokenEvent(behaviour.fallback_text)
        yield DoneEvent(
            answer=behaviour.fallback_text,
            input_tokens=streamed.usage.input_tokens,
            output_tokens=streamed.usage.output_tokens,
            retrieved=retrieved.candidates,
            excluded=retrieved.excluded,
            guardrail_outcomes=[GuardrailOutcome("canary", "leak", "replaced", CANARY_IN_QUERY)],
            searches=searches,
        )
        return
    if _found_nothing(given, searches):
        # Searched, and nothing relevant was found: the Agent's words, not the model's guess.
        yield TokenEvent(behaviour.fallback_text)
        yield DoneEvent(
            answer=behaviour.fallback_text,
            input_tokens=streamed.usage.input_tokens,
            output_tokens=streamed.usage.output_tokens,
            retrieved=[],
            excluded=retrieved.excluded,
            fallback=True,
            searches=searches,
        )
        return
    if canary_filter.leaked:
        yield ReplaceEvent(behaviour.fallback_text)
        yield DoneEvent(
            answer=behaviour.fallback_text,
            input_tokens=streamed.usage.input_tokens,
            output_tokens=streamed.usage.output_tokens,
            retrieved=retrieved.candidates,
            excluded=retrieved.excluded,
            guardrail_outcomes=[GuardrailOutcome("canary", "leak", "replaced", CANARY_REPLACED)],
            searches=searches,
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
        searches=searches,
    )
