"""What the Evaluation Model is given to judge, rebuilt from what was stored.

``judge_input`` is the one place a judge request is built: Run judging builds it from the case
result it has just stored, Live judging from the Live Verdict it is about to judge, and anything
later (a Verdict review, a guidance check) rebuilds the same request from the same rows.

- A Run's case result (or one of its Verdicts) is judged on the Run's copy of the case (question
  and Reference answer), the result's stored answer, and the Chunks its stored Trace says the
  answer cited; grounding isn't asked of the Fallback Text.
- A Live Verdict is judged on its reply, the question it answered, the reply's Remembered turns
  (as its Agent Version remembered them) and the Chunks the reply was given, split into those it
  cited and the rest; it asks for ``grounding`` and ``answers_question``.

Chunks are labelled by their rank and listed in Trace order, a Chunk found again by a later
Search keeping its first label. There is no request (None) when the text it needs is gone: a
case result whose answering errored, or a Live Verdict whose reply, question or a Remembered turn
has been Purged, so nothing is shown or judged without its text. Run rows are never Purged.
"""

import itertools
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.config import AgentConfig
from app.agents.models import AgentVersion
from app.conversations.models import Message, MessageRole
from app.conversations.service import traced_chunks
from app.evaluation.from_message import question_of
from app.evaluation.judge import CitedExcerpt, JudgeRequest
from app.evaluation.models import (
    EvaluationCaseResult,
    EvaluationRunCase,
    EvaluationVerdict,
    LiveVerdict,
)
from app.guardrails.outcomes import blocked
from app.playground.api import TraceOut
from app.runtime.prompt import Turn

DELETED_DOCUMENT = "Deleted Document"

# A Chunk as traced: its rank (None when it wasn't given to the model), whether the answer
# cited it, its Document's name and its text.
_Traced = tuple[int | None, bool, str | None, str | None]


def _given(chunks: Iterable[_Traced]) -> tuple[list[CitedExcerpt], list[CitedExcerpt]]:
    """The Chunks given to the model, labelled by rank: those cited, then the rest."""
    given: dict[int, tuple[bool, CitedExcerpt]] = {}
    for rank, cited, document_name, text in chunks:
        # Those left out (with no rank) weren't given to the model.
        if rank is None:
            continue
        excerpt = CitedExcerpt(f"C{rank}", document_name or DELETED_DOCUMENT, text or "")
        # A Chunk found again by a later Search keeps its first label.
        given.setdefault(rank, (cited, excerpt))
    return (
        [excerpt for cited, excerpt in given.values() if cited],
        [excerpt for cited, excerpt in given.values() if not cited],
    )


async def remembered_turns(
    session: AsyncSession, reply: Message, question: Message
) -> list[tuple[Message, Message]]:
    """The reply's Remembered turns, oldest first, as its Agent Version remembered them: the
    last of the earlier exchanges, leaving out those the input Guardrail blocked and those
    already Purged when the reply was given (neither was sent to the model)."""
    version = await session.get_one(AgentVersion, reply.agent_version_id)
    count = AgentConfig.model_validate(version.config).behaviour.remembered_turns
    earlier = await session.scalars(
        select(Message)
        .where(Message.conversation_id == reply.conversation_id, Message.seq < question.seq)
        .order_by(Message.seq)
    )
    turns = [
        (asked, answer)
        for asked, answer in itertools.pairwise(earlier)
        if (asked.role, answer.role) == (MessageRole.USER, MessageRole.ASSISTANT)
        and not blocked(answer.guardrail_outcomes)
        and all(m.purged_at is None or m.purged_at > reply.created_at for m in (asked, answer))
    ]
    return turns[-count:] if count else []


async def _live(session: AsyncSession, verdict: LiveVerdict) -> JudgeRequest | None:
    reply = await session.get_one(Message, verdict.message_id)
    question = await question_of(session, reply)
    turns = await remembered_turns(session, reply, question)
    texts = [reply, question, *(m for turn in turns for m in turn)]
    if any(m.purged_at is not None for m in texts):
        return None
    cited, uncited = _given(
        (c.retrieval.rank, c.retrieval.cited, c.document_name, c.text)
        for c in await traced_chunks(session, reply)
    )
    return JudgeRequest(
        question=question.content,
        answer=reply.content,
        cited=cited,
        reference_answer=None,
        grounding=True,
        answers_question=True,
        given=uncited,
        earlier_turns=[Turn(asked.content, answer.content) for asked, answer in turns],
    )


async def _run(session: AsyncSession, result: EvaluationCaseResult) -> JudgeRequest | None:
    if result.answer is None:
        # Answering errored: there is no answer to judge.
        return None
    case = await session.get_one(EvaluationRunCase, result.run_case_id)
    # An answered result always has its Trace.
    trace = TraceOut.model_validate(result.trace)
    chunks = [*trace.chunks, *(c for search in trace.searches for c in search.chunks)]
    cited, _ = _given((c.rank, c.cited, c.document_name, c.text) for c in chunks)
    return JudgeRequest(
        question=case.question,
        answer=result.answer,
        cited=cited,
        reference_answer=case.reference_answer,
        grounding=not trace.fallback,
    )


async def judge_input(
    session: AsyncSession, target: EvaluationCaseResult | EvaluationVerdict | LiveVerdict
) -> JudgeRequest | None:
    """The request the Evaluation Model judges ``target`` with (a Run's case result or one of its
    Verdicts, or a Live Verdict), rebuilt from what was stored; None when its text is gone."""
    if isinstance(target, LiveVerdict):
        return await _live(session, target)
    if isinstance(target, EvaluationVerdict):
        target = await session.get_one(EvaluationCaseResult, target.result_id)
    return await _run(session, target)
