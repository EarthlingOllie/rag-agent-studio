"""Chunk labels come from the reply's record of the Chunks given to the model, in the order they
were first given, not from each Chunk's rank; Citations resolve through the same record."""

import uuid
from collections.abc import AsyncIterator

from pydantic_ai.messages import ModelMessage, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.profiles import ModelProfile

from app.agents.config import AgentConfig, Retrieval, RetrievalMode
from app.retrieval.service import Candidate, RetrievalResult
from app.runtime.runtime import CitationEvent, DoneEvent, TurnEvent, run_turn

TEXT_ONLY: ModelProfile = {"supports_json_schema_output": False}


def candidate(rank: int, name: str) -> Candidate:
    return Candidate(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_name=name,
        text=f"Text of {name}.",
        heading_path=[],
        score=1 / rank,
        relevance=1 / rank,
        semantic_score=1 / rank,
        keyword_score=None,
        rank=rank,
    )


def question_of(messages: list[ModelMessage]) -> str:
    part = messages[-1].parts[-1]
    assert isinstance(part, UserPromptPart)
    return str(part.content)


# The labels of Chunks retrieved up front: Automatic Retrieval Mode.
AUTOMATIC = AgentConfig(retrieval=Retrieval(mode=RetrievalMode.AUTOMATIC))


async def turn(chunks: list[Candidate], model: FunctionModel) -> list[TurnEvent]:
    async def retrieve(query: str, settings: Retrieval) -> RetrievalResult:
        return RetrievalResult(chunks)

    return [
        event
        async for event in run_turn([], AUTOMATIC, "", "Leave?", model=model, retrieve=retrieve)
    ]


async def test_labels_follow_the_order_chunks_are_given_not_their_rank() -> None:
    seen: list[str] = []
    later, earlier = candidate(7, "later.md"), candidate(3, "earlier.md")

    async def cites_the_second(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
        seen.append(question_of(messages))
        yield "See [C2] and [C9]."

    events = await turn(
        [later, earlier], FunctionModel(stream_function=cites_the_second, profile=TEXT_ONLY)
    )

    assert "[C1] later.md\n" in seen[0]
    assert "[C2] earlier.md\n" in seen[0]
    *_, citation, done = events
    assert citation == CitationEvent("C2", earlier)
    assert isinstance(done, DoneEvent)
    assert done.cited == [earlier]


async def test_a_chunk_given_twice_keeps_its_first_label() -> None:
    seen: list[str] = []
    first, second = candidate(1, "first.md"), candidate(2, "second.md")

    async def structured(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
        seen.append(question_of(messages))
        yield '{"answer": "Both.", "citations": ["c2", "[C1]", "C3"]}'

    events = await turn([first, second, first], FunctionModel(stream_function=structured))

    assert seen[0].count("Text of first.md.") == 1
    assert "[C2] second.md\n" in seen[0]
    assert "[C3]" not in seen[0]
    citations = [event for event in events if isinstance(event, CitationEvent)]
    assert citations == [CitationEvent("C2", second), CitationEvent("C1", first)]
