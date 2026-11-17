"""Suggestion runs (spec 16): starting one, the background job that gathers its evidence and has
the Evaluation Model propose the Suggestion, and reading an Agent's Suggestions.

Starting a run reads the Agent's Live Version as its base, copying its AgentConfig, and the
Evaluation Model (or else the Default Model) as it is now; it is refused for an archived Agent,
one never Published, or an Organisation with neither model. The job then gathers the evidence:
the base Version's Visitor replies in the range of UTC days that failed their Live Verdict, have
a thumbs-down or are in a Conversation whose current Conversation Rating is 1 or 2 (each reply
once, with all its reasons; Purged ones left out), and the Evaluation Cases that failed on a side
running the base Version in the latest finished Evaluation Run with such a side. The most recent
``EVIDENCE_MAX`` pieces are used and the count before the cap is stored. Each reply goes to the
model with its Remembered turns, its Live Verdict reasons or Feedback, and a compact Trace; each
case with its question, expectations, Verdicts' reasons and Trace. One proposing call
(``app.suggestions.proposer``) then gives the changes and Knowledge Base gaps; with no evidence
it proposes nothing and asks no model. A model error, a timeout or invalid output makes the run
``failed`` with why. The outcome is ``changes``, else ``gaps_only`` when it found only gaps, else
``no_change``.

Evidence points at its Message, or at the Evaluation Case as its Run copied it, and never copies
text (ADR-0017); reading a Suggestion resolves each piece to its date, kinds and Live Verdict
outcome and to where it opens, saying "Text purged" once the Purge has cleared a reply and "Case
deleted" once a case is gone.
"""

import functools
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.models import AgentVersion
from app.agents.resolution import NoDefaultModelError, ProviderCredentialGoneError
from app.agents.service import AgentWithDraft, active_agent, get_agent
from app.conversations.models import Message
from app.conversations.service import TracedChunk, searches_of, traced_chunks
from app.core.clock import Clock
from app.credentials.models import ProviderCredential
from app.default_model.service import CurrentDefault
from app.evaluation.estimate import NANO
from app.evaluation.failed_cases import FailedCase, failed_cases, run_cases_of
from app.evaluation.from_message import question_of
from app.evaluation.live import remembered_turns
from app.evaluation.live_reads import failed_replies, live_verdicts_of
from app.evaluation.models import (
    EvaluationRun,
    EvaluationRunCase,
    LiveStatus,
    LiveVerdict,
    SideKind,
    VerdictKind,
)
from app.evaluation.ports import EvaluationPorts
from app.evaluation.service import EmptySetError, SideChoice, plan_run, run_in_progress
from app.evaluation.settings import judge_model
from app.feedback.service import low_rated_replies, thumbs_down_replies
from app.gateway.gateway import ModelGateway
from app.pricing.service import credential_pricing, price_table
from app.pricing.table import TokenUsage, cost
from app.projects.service import active_project
from app.retrieval.service import ExcludedReason
from app.suggestions.models import (
    IN_PROGRESS,
    EvidenceKind,
    KnowledgeBaseGap,
    SuggestedChange,
    Suggestion,
    SuggestionEvidence,
    SuggestionOutcome,
    SuggestionStatus,
)
from app.suggestions.proposer import Block, EvidenceItem, ProposeError, propose
from app.suggestions.reads import suggestion_in_progress
from app.tenancy.repository import OrganisationScope

# The most evidence one run reads: the most recent pieces.
EVIDENCE_MAX = 50
# How much of a Chunk's text the model is given in a Trace line.
CHUNK_EXCERPT_MAX = 300
# Below this much evidence the run dialog warns that a Suggestion is likely to be noise.
FEW_EVIDENCE = 10
# The tokens proposing is estimated to use: a fixed allowance in per piece of evidence (its
# question, reply, reasons and compact Trace), and a fixed allowance out for the Suggestion.
EVIDENCE_ALLOWANCE = TokenUsage(input_tokens=1_500, output_tokens=0)
PROPOSING_OUTPUT_ALLOWANCE = TokenUsage(input_tokens=0, output_tokens=1_000)

NO_EVIDENCE = "There was no evidence in the range, so nothing was proposed."
CREDENTIAL_GONE = (
    "The Evaluation Model's Provider Credential no longer exists, so nothing was proposed."
)


class NeverPublishedError(Exception):
    """The Agent has never been Published, so it has no Live Version to read."""


class NoEvaluationModelError(Exception):
    """The Organisation has neither an Evaluation Model nor a Default Model."""


class SuggestionNotFoundError(Exception):
    """No Suggestion of the Agent with that ID."""


class SuggestionInProgressError(Exception):
    """The Agent already has a Suggestion run in progress."""


class EvaluationRunInProgressError(Exception):
    """The Agent has an Evaluation Run in progress: it runs one Run of either kind at a time."""


class SuggestionFinishedError(Exception):
    """Only a Suggestion run in progress can be cancelled."""


def day_start(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=UTC)


@dataclass(frozen=True)
class EvidenceCount:
    """How much evidence a range holds, before the cap: every piece once, and how many qualify
    as each kind (a reply can qualify as several)."""

    total: int
    by_kind: dict[EvidenceKind, int]

    @property
    def likely_noise(self) -> bool:
        """Too little evidence for a Suggestion to be more than noise; a warning, never a
        block."""
        return self.total < FEW_EVIDENCE


@dataclass(frozen=True)
class SuggestionEstimate:
    """A Suggestion run's estimated Cost before it starts, in US dollars."""

    evidence: EvidenceCount
    # How many pieces the run would read: at most ``EVIDENCE_MAX``.
    evidence_used: int
    # None when the Evaluation Model's price is unknown.
    proposing_usd: Decimal | None
    has_evaluation_set: bool
    # The check, which runs only with an Evaluation Set (and a configuration change); None
    # without a set, or when a price it needs is unknown.
    checking_usd: Decimal | None

    @property
    def total_usd(self) -> Decimal | None:
        if self.proposing_usd is None or (self.has_evaluation_set and self.checking_usd is None):
            return None
        return self.proposing_usd + (self.checking_usd or Decimal(0))


@dataclass(frozen=True)
class _Plan:
    agent: AgentWithDraft
    version: AgentVersion
    model: CurrentDefault
    estimate: SuggestionEstimate


async def _checking_usd(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    version_id: uuid.UUID,
    now: datetime,
) -> tuple[bool, Decimal | None]:
    """Whether the Agent has an Evaluation Set, and what checking a Suggestion against it would
    cost: spec 14's estimate for two sides, the Live Version and the Suggestion, which answers
    with the Live Version's model, so it is priced as the Live Version is."""
    try:
        plan = await plan_run(
            session,
            scope,
            project_id,
            agent_id,
            sides=[SideChoice(SideKind.VERSION, version_id)],
            instructions_version_id=None,
            instructions_draft=False,
            starting=False,
            now=now,
        )
    except EmptySetError:
        return False, None
    except (NoDefaultModelError, ProviderCredentialGoneError):
        # The Live Version's model can't be resolved: the check can't be priced.
        return True, None
    one_side = plan.estimate.total_usd
    return True, None if one_side is None else one_side * 2


async def _proposing_usd(
    session: AsyncSession, model: CurrentDefault, pieces: int, now: datetime
) -> Decimal | None:
    if pieces == 0:
        # With no evidence no model is asked.
        return Decimal(0)
    usage = TokenUsage(
        input_tokens=pieces * EVIDENCE_ALLOWANCE.input_tokens,
        output_tokens=PROPOSING_OUTPUT_ALLOWANCE.output_tokens,
    )
    spent = cost(
        await credential_pricing(session, model.credential),
        model.model,
        usage,
        now,
        await price_table(session),
    )
    return None if spent is None else spent.quantize(NANO)


async def _plan(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    *,
    range_start: date,
    range_end: date,
    now: datetime,
    starting: bool,
) -> _Plan:
    """What a Suggestion run of the range would read and cost, refused as ``start_suggestion``
    says. When ``starting``, the Agent's row is locked and a run of either kind in progress is
    refused."""
    await active_project(session, scope, project_id)
    found = await active_agent(session, scope, project_id, agent_id, lock=starting)
    if found.live_version is None:
        raise NeverPublishedError
    if starting and await suggestion_in_progress(session, found.agent.id):
        raise SuggestionInProgressError
    if starting and await run_in_progress(session, found.agent.id):
        raise EvaluationRunInProgressError
    chosen = await judge_model(session, scope.organisation_id)
    if chosen is None:
        raise NoEvaluationModelError
    version = await session.get_one(AgentVersion, found.live_version.id)
    pieces = await _pieces(session, found.agent.id, version.id, range_start, range_end)
    counted = EvidenceCount(
        len(pieces),
        {kind: sum(kind in piece.kinds for piece in pieces) for kind in EvidenceKind},
    )
    used = min(counted.total, EVIDENCE_MAX)
    has_set, checking = await _checking_usd(
        session, scope, project_id, found.agent.id, version.id, now
    )
    return _Plan(
        found,
        version,
        chosen,
        SuggestionEstimate(
            counted, used, await _proposing_usd(session, chosen, used, now), has_set, checking
        ),
    )


async def estimate_suggestion(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    *,
    range_start: date,
    range_end: date,
    now: datetime,
) -> SuggestionEstimate:
    """How much evidence a Suggestion run of the range would read, by kind, and its estimated
    Cost, for the run dialog. Refused as starting would be, except while a run is in
    progress."""
    plan = await _plan(
        session,
        scope,
        project_id,
        agent_id,
        range_start=range_start,
        range_end=range_end,
        now=now,
        starting=False,
    )
    return plan.estimate


async def start_suggestion(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    *,
    range_start: date,
    range_end: date,
    now: datetime,
) -> uuid.UUID:
    """Saves a queued Suggestion run of the Agent's Live Version over the range of UTC days,
    with its estimated Cost, and returns its ID, for the caller to send its task with once
    committed.

    Refused for an archived Agent or Project, one never Published (``NeverPublishedError``), an
    Organisation with neither an Evaluation Model nor a Default Model
    (``NoEvaluationModelError``), and while the Agent has a Suggestion run
    (``SuggestionInProgressError``) or an Evaluation Run (``EvaluationRunInProgressError``) in
    progress, checked together under the Agent's row lock."""
    plan = await _plan(
        session,
        scope,
        project_id,
        agent_id,
        range_start=range_start,
        range_end=range_end,
        now=now,
        starting=True,
    )
    suggestion = Suggestion(
        organisation_id=scope.organisation_id,
        agent_id=plan.agent.agent.id,
        status=SuggestionStatus.QUEUED,
        started_by=scope.member_id,
        range_start=range_start,
        range_end=range_end,
        base_version_id=plan.version.id,
        base_config=plan.version.config,
        model_credential_id=plan.model.credential.id,
        model_provider=plan.model.credential.provider,
        model_name=plan.model.model,
        evidence_total=0,
        estimated_proposing_cost_usd=plan.estimate.proposing_usd,
        estimated_checking_cost_usd=plan.estimate.checking_usd,
        created_at=now,
    )
    session.add(suggestion)
    await session.commit()
    return suggestion.id


async def cancel_suggestion(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    suggestion_id: uuid.UUID,
    *,
    now: datetime,
) -> None:
    """Cancels a Suggestion run in progress (``SuggestionFinishedError`` otherwise), also for an
    archived Agent. Its job stops before its next phase; what it spent so far is kept."""
    found = await get_agent(session, scope, project_id, agent_id)
    suggestion = await session.scalar(
        select(Suggestion)
        .where(Suggestion.id == suggestion_id, Suggestion.agent_id == found.agent.id)
        .with_for_update()
    )
    if suggestion is None:
        raise SuggestionNotFoundError
    if suggestion.status not in IN_PROGRESS:
        raise SuggestionFinishedError
    suggestion.status = SuggestionStatus.CANCELLED
    suggestion.finished_at = now
    await session.commit()


def _outcome(verdict: LiveVerdict) -> str:
    return "pass" if verdict.passed else "fail"


# What the model is told each kind of evidence is.
KIND_LINES = {
    EvidenceKind.LIVE_VERDICT: "Kind: failed Live Verdict",
    EvidenceKind.THUMBS_DOWN: "Kind: thumbs-down",
    EvidenceKind.LOW_RATING: "Kind: in a Conversation rated {score} of 5",
    EvidenceKind.EVALUATION_CASE: "Kind: failed Evaluation Case",
}
VERDICT_NAMES = {
    VerdictKind.EXPECTED_SOURCE: "Expected source",
    VerdictKind.FALLBACK: "Expect Fallback Text",
    VerdictKind.REFERENCE_ANSWER: "Reference answer",
    VerdictKind.GROUNDING: "Grounding",
}
PURGED_TEXT = "[Text purged]"
BELOW_MIN_SCORE: ExcludedReason = "below_min_score"


@dataclass
class _Piece:
    """One piece of evidence while it is gathered: a reply with every reason it qualifies, or
    a failed Evaluation Case."""

    at: datetime
    # Orders pieces given at the same time: the later reply, or the earlier case, first.
    order: int
    kinds: list[EvidenceKind] = field(default_factory=list)
    reply: Message | None = None
    verdict: LiveVerdict | None = None
    comment: str | None = None
    rating: int | None = None
    case: FailedCase | None = None


@dataclass(frozen=True)
class _TracedChunk:
    rank: int | None
    cited: bool
    excluded_reason: str | None
    relevance: float
    document_name: str | None
    text: str | None


def _chunk_line(chunk: _TracedChunk) -> str:
    if chunk.rank is None:
        state = f"excluded ({chunk.excluded_reason})"
    else:
        state = f"[C{chunk.rank}] {'cited' if chunk.cited else 'not cited'}"
    excerpt = " ".join((chunk.text or "").split())[:CHUNK_EXCERPT_MAX]
    name = chunk.document_name or "Deleted Document"
    return f"{state}, relevance {chunk.relevance:.2f}, {name}: {excerpt}"


def _trace_lines(
    chunks: list[_TracedChunk], searches: list[tuple[str, list[_TracedChunk]]]
) -> tuple[list[str], list[str]]:
    """The run's own lines about a Trace (how many Chunks were cited, and the closest excluded
    below the Minimum Score), and the Trace's lines: its Chunks, then each Search with its."""
    lines = [_chunk_line(chunk) for chunk in chunks]
    for order, (query, found) in enumerate(searches, start=1):
        lines.append(f"Search {order}: {' '.join(query.split())}")
        lines.extend(_chunk_line(chunk) for chunk in found)
    every = chunks + [chunk for _, found in searches for chunk in found]
    header = [f"Chunks cited: {sum(chunk.cited for chunk in every)}"]
    below = [c.relevance for c in every if c.excluded_reason == BELOW_MIN_SCORE]
    if below:
        header.append(f"Closest Chunk below the Minimum Score: relevance {max(below):.2f}")
    return header, lines


def _traced(chunk: TracedChunk) -> _TracedChunk:
    retrieval = chunk.retrieval
    return _TracedChunk(
        retrieval.rank,
        retrieval.cited,
        retrieval.excluded_reason,
        retrieval.relevance,
        chunk.document_name,
        chunk.text,
    )


def _text(message: Message) -> str:
    return PURGED_TEXT if message.purged_at is not None else message.content


async def _reply_item(session: AsyncSession, label: str, piece: _Piece) -> EvidenceItem:
    reply = cast(Message, piece.reply)
    question = await question_of(session, reply)
    turns = await remembered_turns(session, reply, question)
    traced = await traced_chunks(session, reply)
    searches = [
        (search.query, [_traced(c) for c in traced if c.retrieval.search_id == search.id])
        for search in await searches_of(session, reply)
    ]
    header, trace = _trace_lines(
        [_traced(c) for c in traced if c.retrieval.search_id is None], searches
    )
    reasons = [KIND_LINES[kind].format(score=piece.rating) for kind in piece.kinds]
    verdict = piece.verdict
    if verdict is not None and verdict.status == LiveStatus.JUDGED:
        reasons += [
            f"Grounding: {verdict.grounded}. {verdict.grounded_reason}",
            f"Answers the question: {verdict.answers_question}. {verdict.answers_question_reason}",
        ]
    blocks = []
    if turns:
        remembered = [
            f"Visitor: {_text(asked)}\nAssistant: {_text(answer)}" for asked, answer in turns
        ]
        blocks.append(Block("REMEMBERED_TURNS", "\n".join(remembered)))
    blocks += [Block("VISITOR_QUESTION", _text(question)), Block("REPLY", reply.content)]
    if piece.comment:
        blocks.append(Block("VISITOR_COMMENT", piece.comment))
    blocks.append(Block("TRACE", "\n".join(trace)))
    return EvidenceItem(label=label, reasons=reasons + header, blocks=blocks)


def _expectations(run_case: EvaluationRunCase) -> str:
    lines = []
    if run_case.reference_answer:
        lines.append(f"Reference answer: {run_case.reference_answer}")
    if run_case.expect_fallback:
        lines.append("Expects the Fallback Text.")
    for source in run_case.expected_sources:
        lines.append(f"Expected source, {source['document_name']}: {source['passage']}")
    return "\n".join(lines)


def _json_chunk(chunk: dict[str, Any]) -> _TracedChunk:
    return _TracedChunk(
        chunk["rank"],
        chunk["cited"],
        chunk["excluded_reason"],
        chunk["relevance"],
        chunk["document_name"],
        chunk["text"],
    )


def _case_item(label: str, case: FailedCase) -> EvidenceItem:
    # The first repeat that failed: the one the model is shown.
    shown = next(repeat for repeat in case.repeats if repeat.answered and not repeat.passed)
    trace = shown.result.trace or {}
    header, lines = _trace_lines(
        [_json_chunk(c) for c in trace.get("chunks", [])],
        [
            (search["query"], [_json_chunk(c) for c in search["chunks"]])
            for search in trace.get("searches", [])
        ],
    )
    reasons = [
        KIND_LINES[EvidenceKind.EVALUATION_CASE],
        f"Repeats passed: {case.result.passed} of {case.result.answered} answered",
        *(
            f"{VERDICT_NAMES[VerdictKind(v.kind)]}: {v.outcome}. {v.reason or ''}".rstrip()
            for v in shown.verdicts
        ),
        *header,
    ]
    return EvidenceItem(
        label=label,
        reasons=reasons,
        blocks=[
            Block("CASE_QUESTION", case.run_case.question),
            Block("EXPECTATIONS", _expectations(case.run_case)),
            Block("REPLY", shown.result.answer or ""),
            Block("TRACE", "\n".join(lines)),
        ],
    )


def _label(position: int) -> str:
    return f"E{position}"


async def _set_status(
    sessionmaker: async_sessionmaker[AsyncSession], suggestion_id: uuid.UUID, status: str
) -> bool:
    """Moves the run on to its next phase, unless it has been cancelled; whether it moved."""
    async with sessionmaker() as session:
        moved = await session.scalar(
            update(Suggestion)
            .where(Suggestion.id == suggestion_id, Suggestion.status.in_(IN_PROGRESS))
            .values(status=status)
            .returning(Suggestion.id)
        )
        await session.commit()
        return moved is not None


async def _pieces(
    session: AsyncSession,
    agent_id: uuid.UUID,
    version_id: uuid.UUID,
    range_start: date,
    range_end: date,
) -> list[_Piece]:
    """Every piece of evidence in the range of UTC days, the most recent first: the Version's
    Visitor replies that failed their Live Verdict, have a thumbs-down or are in a Conversation
    rated 1 or 2, each once with all its reasons, and the Evaluation Cases that failed on it in
    the latest finished Run with a side running it."""
    start = day_start(range_start)
    end = day_start(range_end + timedelta(days=1))
    replies: dict[uuid.UUID, _Piece] = {}

    def piece(reply: Message, kind: EvidenceKind) -> _Piece:
        found = replies.setdefault(reply.id, _Piece(reply.created_at, reply.seq, reply=reply))
        found.kinds.append(kind)
        return found

    for reply, verdict in (await failed_replies(session, version_id, start, end)).replies:
        piece(reply, EvidenceKind.LIVE_VERDICT).verdict = verdict
    for reply, comment in await thumbs_down_replies(session, version_id, start, end):
        piece(reply, EvidenceKind.THUMBS_DOWN).comment = comment
    for reply, score in await low_rated_replies(session, version_id, start, end):
        piece(reply, EvidenceKind.LOW_RATING).rating = score
    verdicts = await live_verdicts_of(
        session, [p.reply.id for p in replies.values() if p.verdict is None and p.reply]
    )
    for each in replies.values():
        if each.verdict is None and each.reply is not None:
            each.verdict = verdicts.get(each.reply.id)
    cases = [
        _Piece(
            cast(datetime, case.run.finished_at),
            -case.run_case.position,
            [EvidenceKind.EVALUATION_CASE],
            case=case,
        )
        for case in await failed_cases(session, agent_id, version_id)
    ]
    return sorted([*replies.values(), *cases], key=lambda p: (p.at, p.order), reverse=True)


async def _gather(
    sessionmaker: async_sessionmaker[AsyncSession], suggestion_id: uuid.UUID
) -> list[EvidenceItem]:
    """Stores the run's evidence and returns it as the model is given it."""
    async with sessionmaker() as session:
        suggestion = await session.get_one(Suggestion, suggestion_id)
        pieces = await _pieces(
            session,
            suggestion.agent_id,
            suggestion.base_version_id,
            suggestion.range_start,
            suggestion.range_end,
        )
        suggestion.evidence_total = len(pieces)
        items: list[EvidenceItem] = []
        for position, piece in enumerate(pieces[:EVIDENCE_MAX], start=1):
            session.add(
                SuggestionEvidence(
                    organisation_id=suggestion.organisation_id,
                    suggestion_id=suggestion.id,
                    position=position,
                    kind=piece.kinds[0],
                    kinds=list(piece.kinds),
                    message_id=None if piece.reply is None else piece.reply.id,
                    run_case_id=None if piece.case is None else piece.case.run_case.id,
                )
            )
            label = _label(position)
            items.append(
                _case_item(label, piece.case)
                if piece.case is not None
                else await _reply_item(session, label, piece)
            )
        await session.commit()
        return items


async def _finish(
    sessionmaker: async_sessionmaker[AsyncSession],
    suggestion_id: uuid.UUID,
    now: datetime,
    *,
    error: str | None = None,
    explanation: str | None = None,
    changes: Sequence[SuggestedChange] = (),
    gaps: Sequence[KnowledgeBaseGap] = (),
) -> None:
    async with sessionmaker() as session:
        suggestion = await session.get_one(Suggestion, suggestion_id, with_for_update=True)
        if suggestion.status not in IN_PROGRESS:
            # Cancelled meanwhile: what it found is not kept.
            return
        suggestion.finished_at = now
        if error is not None:
            suggestion.status = SuggestionStatus.FAILED
            suggestion.error_message = error
        else:
            suggestion.status = SuggestionStatus.COMPLETED
            suggestion.explanation = explanation
            suggestion.outcome = (
                SuggestionOutcome.CHANGES
                if changes
                else SuggestionOutcome.GAPS_ONLY
                if gaps
                else SuggestionOutcome.NO_CHANGE
            )
            session.add_all(changes)
            session.add_all(gaps)
        await session.commit()


async def _spent(
    sessionmaker: async_sessionmaker[AsyncSession],
    suggestion_id: uuid.UUID,
    credential: ProviderCredential,
    usage: TokenUsage,
    now: datetime,
) -> None:
    """Freezes what the proposing call cost at the prices in force now, even for a run cancelled
    while it was made."""
    async with sessionmaker() as session:
        suggestion = await session.get_one(Suggestion, suggestion_id)
        suggestion.proposing_cost_usd = cost(
            await credential_pricing(session, credential),
            suggestion.model_name,
            usage,
            now,
            await price_table(session),
        )
        suggestion.proposed_at = now
        await session.commit()


async def run_suggestion(
    sessionmaker: async_sessionmaker[AsyncSession],
    ports: EvaluationPorts,
    gateway: ModelGateway,
    suggestion_id: uuid.UUID,
    clock: Clock,
) -> None:
    """Gathers the queued Suggestion run's evidence and proposes its Suggestion. A run cancelled
    meanwhile stops before its next phase, keeping what it spent."""
    if not await _set_status(sessionmaker, suggestion_id, SuggestionStatus.GATHERING):
        return
    evidence = await _gather(sessionmaker, suggestion_id)
    if not evidence:
        await _finish(sessionmaker, suggestion_id, clock.now(), explanation=NO_EVIDENCE)
        return
    if not await _set_status(sessionmaker, suggestion_id, SuggestionStatus.PROPOSING):
        return
    async with sessionmaker() as session:
        suggestion = await session.get_one(Suggestion, suggestion_id)
        credential_id = suggestion.model_credential_id
        credential = (
            None if credential_id is None else await session.get(ProviderCredential, credential_id)
        )
    # A chosen model's credential is a Credential reference, so it can't be deleted while it
    # is chosen; only one deleted since it was replaced can be gone.
    if credential is None:  # pragma: no cover - deleted between starting and proposing
        await _finish(sessionmaker, suggestion_id, clock.now(), error=CREDENTIAL_GONE)
        return
    try:
        proposing = await propose(
            functools.partial(gateway.chat_model, credential, suggestion.model_name),
            suggestion.model_name,
            suggestion.base_config,
            evidence,
            timeout_s=ports.suggestion_timeout_s,
        )
    except ProposeError as error:
        await _finish(sessionmaker, suggestion_id, clock.now(), error=error.message)
        return
    await _spent(sessionmaker, suggestion_id, credential, proposing.usage, clock.now())
    positions = {item.label: int(item.label[1:]) for item in evidence}
    changes = [
        SuggestedChange(
            organisation_id=suggestion.organisation_id,
            suggestion_id=suggestion_id,
            position=position,
            path=change.path,
            base_value=change.base_value,
            suggested_value=change.suggested_value,
            explanation=change.explanation,
            evidence=[positions[label] for label in change.evidence],
        )
        for position, change in enumerate(proposing.changes, start=1)
    ]
    gaps = [
        KnowledgeBaseGap(
            organisation_id=suggestion.organisation_id,
            suggestion_id=suggestion_id,
            position=position,
            topic=gap.topic,
            explanation=gap.explanation,
            evidence=[positions[label] for label in gap.evidence],
        )
        for position, gap in enumerate(proposing.gaps, start=1)
    ]
    await _finish(
        sessionmaker,
        suggestion_id,
        clock.now(),
        explanation=proposing.explanation,
        changes=changes,
        gaps=gaps,
    )


# Reading


@dataclass(frozen=True)
class EvidenceRead:
    evidence: SuggestionEvidence
    # The reply, for a reply.
    message: Message | None
    # The reply's Live Verdict outcome, ``pass`` or ``fail``; None when it has none.
    live_verdict: str | None
    # The case as its Run copied it, and the Run, for an Evaluation Case.
    run_case: EvaluationRunCase | None = None
    run: EvaluationRun | None = None

    @property
    def text_purged(self) -> bool:
        return self.message is not None and self.message.purged_at is not None

    @property
    def case_deleted(self) -> bool:
        return self.run_case is not None and self.run_case.case_id is None

    @property
    def occurred_at(self) -> datetime:
        """When the reply was given, or the Run that failed the case finished."""
        if self.message is not None:
            return self.message.created_at
        return cast(datetime, cast(EvaluationRun, self.run).finished_at)


@dataclass(frozen=True)
class SuggestionRead:
    suggestion: Suggestion
    base_version_number: int
    changes: list[SuggestedChange]
    evidence: list[EvidenceRead]
    gaps: list[KnowledgeBaseGap] = field(default_factory=list)


async def list_suggestions(
    session: AsyncSession, scope: OrganisationScope, project_id: uuid.UUID, agent_id: uuid.UUID
) -> list[tuple[Suggestion, int]]:
    """The Agent's Suggestions, newest first, each with its base Version's number."""
    found = await get_agent(session, scope, project_id, agent_id)
    rows = await session.execute(
        select(Suggestion, AgentVersion.number)
        .join(AgentVersion, AgentVersion.id == Suggestion.base_version_id)
        .where(Suggestion.agent_id == found.agent.id)
        .order_by(Suggestion.created_at.desc(), Suggestion.id)
    )
    return [(suggestion, number) for suggestion, number in rows.all()]


async def get_suggestion(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    suggestion_id: uuid.UUID,
) -> SuggestionRead:
    """The Agent's Suggestion with its changes and its evidence resolved."""
    found = await get_agent(session, scope, project_id, agent_id)
    suggestion = await session.scalar(
        select(Suggestion).where(
            Suggestion.id == suggestion_id, Suggestion.agent_id == found.agent.id
        )
    )
    if suggestion is None:
        raise SuggestionNotFoundError
    version = await session.get_one(AgentVersion, suggestion.base_version_id)
    changes = list(
        await session.scalars(
            select(SuggestedChange)
            .where(SuggestedChange.suggestion_id == suggestion.id)
            .order_by(SuggestedChange.position)
        )
    )
    evidence = list(
        await session.scalars(
            select(SuggestionEvidence)
            .where(SuggestionEvidence.suggestion_id == suggestion.id)
            .order_by(SuggestionEvidence.position)
        )
    )
    gaps = list(
        await session.scalars(
            select(KnowledgeBaseGap)
            .where(KnowledgeBaseGap.suggestion_id == suggestion.id)
            .order_by(KnowledgeBaseGap.position)
        )
    )
    message_ids = [each.message_id for each in evidence if each.message_id is not None]
    messages = {
        message.id: message
        for message in await session.scalars(select(Message).where(Message.id.in_(message_ids)))
    }
    outcomes = {
        message_id: _outcome(verdict)
        for message_id, verdict in (await live_verdicts_of(session, message_ids)).items()
        if verdict.status == LiveStatus.JUDGED
    }
    cases = await run_cases_of(
        session, [each.run_case_id for each in evidence if each.run_case_id is not None]
    )

    def read(each: SuggestionEvidence) -> EvidenceRead:
        if each.run_case_id is not None:
            run_case, run = cases[each.run_case_id]
            return EvidenceRead(each, None, None, run_case, run)
        message_id = cast(uuid.UUID, each.message_id)
        return EvidenceRead(each, messages[message_id], outcomes.get(message_id))

    return SuggestionRead(
        suggestion, version.number, changes, [read(each) for each in evidence], gaps
    )
