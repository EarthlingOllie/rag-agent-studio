"""``run_turn``: one turn of a Conversation, as an async stream of events.

It knows nothing about HTTP, the Playground or the widget: callers give it the Conversation's
turns (it keeps the last ``remembered_turns`` of them), the AgentConfig, the Instructions text,
the Visitor input, the chat model (from the model gateway) and a ``retrieve`` function bound to
the Project. The Pydantic AI agent it builds registers no tools (ADR-0007).
"""

from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass

from pydantic_ai import Agent
from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings

from app.agents.config import AgentConfig, Retrieval
from app.retrieval.service import Candidate, RetrievalResult
from app.runtime.prompt import Turn, data_blocks, history

Retrieve = Callable[[str, Retrieval], Awaitable[RetrievalResult]]


@dataclass(frozen=True)
class TokenEvent:
    text: str


@dataclass(frozen=True)
class DoneEvent:
    """The end of the turn: the full answer, token usage and the Chunks the model was given."""

    answer: str
    input_tokens: int
    output_tokens: int
    retrieved: list[Candidate]


TurnEvent = TokenEvent | DoneEvent


async def run_turn(
    turns: Sequence[Turn],
    config: AgentConfig,
    instructions: str,
    visitor_input: str,
    *,
    model: Model,
    retrieve: Retrieve,
) -> AsyncIterator[TurnEvent]:
    behaviour = config.behaviour
    retrieved = await retrieve(visitor_input, config.retrieval)
    agent = Agent(model)
    remembered = list(turns)[-behaviour.remembered_turns :] if behaviour.remembered_turns else []
    messages = history(instructions, behaviour.system_prompt, remembered)
    question = data_blocks(retrieved.candidates, visitor_input)
    settings = ModelSettings(
        temperature=behaviour.temperature, max_tokens=behaviour.max_output_tokens
    )
    answer: list[str] = []
    async with agent.run_stream(
        question, message_history=messages, model_settings=settings
    ) as result:
        async for text in result.stream_text(delta=True, debounce_by=None):
            answer.append(text)
            yield TokenEvent(text)
        usage = result.usage
    yield DoneEvent(
        answer="".join(answer),
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        retrieved=retrieved.candidates,
    )
