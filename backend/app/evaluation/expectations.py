"""The checks that need no model: Expected sources and Expect Fallback Text.

An Expected source's passage is matched, after normalising case and whitespace, against the text
of its Document's current-Edition Chunks. It is a Stale expectation when the Document is gone
(``document_deleted``) or no Chunk holds the passage (``passage_missing``): its Verdict is
``stale``, neither pass nor fail. Otherwise it passes when the answer cited a Chunk holding the
passage, and fails when it didn't, the reason saying whether such a Chunk was retrieved but left
uncited or never retrieved at all.

Expect Fallback Text passes when the answer was the Fallback Text (its ``fallback`` flag is set,
or its text is the Agent's Fallback Text) or the Refusal text, and fails otherwise.

``refresh_stale`` sets each Expected source's Stale flag and reason from the Knowledge Base as it
is now, for the case editor and the Runs to keep the Evaluation Set's flags current;
``recheck_document`` does it for every Expected source on a Document once a new Edition of it is
swapped in, so cases whose passage has gone are flagged at once.
"""

import uuid
from collections.abc import Collection, Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.config import AgentConfig
from app.documents.service import CurrentChunks, current_chunks
from app.evaluation.models import EvaluationExpectedSource, StaleReason, VerdictOutcome


def normalised(text: str) -> str:
    """The text in one case with its whitespace runs collapsed to single spaces."""
    return " ".join(text.split()).casefold()


@dataclass(frozen=True)
class Check:
    outcome: VerdictOutcome
    reason: str
    # Why it is a Stale expectation; None when it isn't.
    stale_reason: StaleReason | None = None


def matching_chunks(passage: str, current: CurrentChunks) -> set[uuid.UUID]:
    """The current-Edition Chunks that hold the passage."""
    wanted = normalised(passage)
    return {chunk_id for chunk_id, text in current.chunks if wanted in normalised(text)}


def _matched(passage: str, current: CurrentChunks | None) -> StaleReason | set[uuid.UUID]:
    """The Chunks holding the passage, or why there are none."""
    if current is None:
        return StaleReason.DOCUMENT_DELETED
    return matching_chunks(passage, current) or StaleReason.PASSAGE_MISSING


def staleness(passage: str, current: CurrentChunks | None) -> StaleReason | None:
    """Why the passage is a Stale expectation, given its Document's current Chunks (None for a
    Document that is gone); None when a Chunk holds it."""
    found = _matched(passage, current)
    return found if isinstance(found, StaleReason) else None


_STALE = {
    StaleReason.DOCUMENT_DELETED: "{name} has been deleted, so this was skipped.",
    StaleReason.PASSAGE_MISSING: (
        "No Chunk of {name}'s current Edition holds the passage, so this was skipped."
    ),
}


def check_expected_source(
    document_name: str,
    passage: str,
    current: CurrentChunks | None,
    *,
    cited: Collection[uuid.UUID],
    retrieved: Collection[uuid.UUID],
) -> Check:
    """The ``expected_source`` Verdict for an answer that cited ``cited`` and was given
    ``retrieved``."""
    matching = _matched(passage, current)
    if isinstance(matching, StaleReason):
        reason = _STALE[matching].format(name=document_name)
        return Check(VerdictOutcome.STALE, reason, matching)
    if matching & set(cited):
        return Check(VerdictOutcome.PASS, f"The answer cited the passage of {document_name}.")
    if matching & set(retrieved):
        return Check(
            VerdictOutcome.FAIL,
            f"The passage of {document_name} was retrieved but the answer didn't cite it.",
        )
    return Check(
        VerdictOutcome.FAIL,
        f"The passage of {document_name} wasn't retrieved, so the answer didn't cite it.",
    )


def check_fallback(answer: str, *, fallback: bool, refused: bool, config: AgentConfig) -> Check:
    """The ``fallback`` Verdict for an answer, given whether it was a fallback reply or a
    refusal and the AgentConfig it answered with."""
    if fallback or answer == config.behaviour.fallback_text:
        return Check(VerdictOutcome.PASS, "The answer was the Fallback Text.")
    if refused or answer == config.guardrails.refusal_text:
        return Check(VerdictOutcome.PASS, "The answer was the Refusal text.")
    return Check(VerdictOutcome.FAIL, "The answer wasn't the Fallback Text or the Refusal text.")


async def refresh_stale(session: AsyncSession, sources: Sequence[EvaluationExpectedSource]) -> None:
    """Sets each Expected source's Stale flag and reason from its Document's current Chunks."""
    current = await current_chunks(
        session, [s.document_id for s in sources if s.document_id is not None]
    )
    for expected in sources:
        found = None if expected.document_id is None else current.get(expected.document_id)
        reason = staleness(expected.passage, found)
        expected.stale = reason is not None
        expected.stale_reason = reason


async def recheck_document(
    sessionmaker: async_sessionmaker[AsyncSession], document_id: uuid.UUID
) -> None:
    """Matches every Expected source on the Document against its current Edition again, after a
    new one is swapped in: surviving passages stay valid, missing ones become Stale expectations
    and earlier Stale ones whose passage is back are cleared."""
    async with sessionmaker() as session, session.begin():
        sources = await session.scalars(
            select(EvaluationExpectedSource)
            .where(EvaluationExpectedSource.document_id == document_id)
            .with_for_update()
        )
        await refresh_stale(session, list(sources))
