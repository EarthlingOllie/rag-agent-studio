"""Suggestion runs (spec 16): starting one, the background job that gathers its evidence and has
the Evaluation Model propose the Suggestion, and reading an Agent's Suggestions.

Starting a run reads the Agent's Live Version as its base, copying its AgentConfig, and the
Evaluation Model (or else the Default Model) as it is now; it is refused for an archived Agent,
one never Published, or an Organisation with neither model. The job then gathers the base
Version's Visitor replies in the range of UTC days whose Live Verdict failed, Purged ones left
out, the most recent ``EVIDENCE_MAX`` of them, and makes one proposing call
(``app.suggestions.proposer``). With no evidence it proposes nothing and asks no model. A model
error, a timeout or invalid output makes the run ``failed`` with why.

Evidence points at its Message and never copies its text (ADR-0017); reading a Suggestion
resolves each piece to its reply's date, Conversation and Live Verdict outcome, or to "Text
purged" once the Purge has cleared it.
"""

import functools
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.models import AgentVersion
from app.agents.service import active_agent, get_agent
from app.conversations.models import Message
from app.conversations.service import traced_chunks
from app.core.clock import Clock
from app.credentials.models import ProviderCredential
from app.evaluation.from_message import question_of
from app.evaluation.live_reads import failed_replies, live_verdicts_of
from app.evaluation.models import LiveVerdict
from app.evaluation.ports import EvaluationPorts
from app.evaluation.settings import judge_model
from app.gateway.gateway import ModelGateway
from app.projects.service import active_project
from app.suggestions.models import (
    EvidenceKind,
    SuggestedChange,
    Suggestion,
    SuggestionEvidence,
    SuggestionOutcome,
    SuggestionStatus,
)
from app.suggestions.proposer import EvidenceItem, ProposeError, propose
from app.tenancy.repository import OrganisationScope

# The most evidence one run reads: the most recent pieces.
EVIDENCE_MAX = 50
# How much of a Chunk's text the model is given in a Trace line.
CHUNK_EXCERPT_MAX = 300

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


def day_start(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=UTC)


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
    """Saves a queued Suggestion run of the Agent's Live Version over the range of UTC days and
    returns its ID, for the caller to send its task with once committed."""
    await active_project(session, scope, project_id)
    found = await active_agent(session, scope, project_id, agent_id, lock=True)
    if found.live_version is None:
        raise NeverPublishedError
    chosen = await judge_model(session, scope.organisation_id)
    if chosen is None:
        raise NoEvaluationModelError
    version = await session.get_one(AgentVersion, found.live_version.id)
    suggestion = Suggestion(
        organisation_id=scope.organisation_id,
        agent_id=found.agent.id,
        status=SuggestionStatus.QUEUED,
        started_by=scope.member_id,
        range_start=range_start,
        range_end=range_end,
        base_version_id=version.id,
        base_config=version.config,
        model_credential_id=chosen.credential.id,
        model_provider=chosen.credential.provider,
        model_name=chosen.model,
        evidence_total=0,
        created_at=now,
    )
    session.add(suggestion)
    await session.commit()
    return suggestion.id


def _outcome(verdict: LiveVerdict) -> str:
    return "pass" if verdict.passed else "fail"


async def _evidence_item(
    session: AsyncSession, label: str, reply: Message, verdict: LiveVerdict
) -> EvidenceItem:
    question = await question_of(session, reply)
    trace: list[str] = []
    for chunk in await traced_chunks(session, reply):
        retrieval = chunk.retrieval
        if retrieval.rank is None:
            state = f"excluded ({retrieval.excluded_reason})"
        else:
            state = f"[C{retrieval.rank}] {'cited' if retrieval.cited else 'not cited'}"
        excerpt = " ".join((chunk.text or "").split())[:CHUNK_EXCERPT_MAX]
        name = chunk.document_name or "Deleted Document"
        trace.append(f"{state}, relevance {retrieval.relevance:.2f}, {name}: {excerpt}")
    return EvidenceItem(
        label=label,
        reasons=[
            "Kind: failed Live Verdict",
            f"Grounding: {verdict.grounded}. {verdict.grounded_reason}",
            f"Answers the question: {verdict.answers_question}. {verdict.answers_question_reason}",
        ],
        question=question.content,
        reply=reply.content,
        trace=trace,
    )


def _label(position: int) -> str:
    return f"E{position}"


async def _set_status(
    sessionmaker: async_sessionmaker[AsyncSession], suggestion_id: uuid.UUID, status: str
) -> None:
    async with sessionmaker() as session:
        suggestion = await session.get_one(Suggestion, suggestion_id)
        suggestion.status = status
        await session.commit()


async def _gather(
    sessionmaker: async_sessionmaker[AsyncSession], suggestion_id: uuid.UUID
) -> list[EvidenceItem]:
    """Stores the run's evidence and returns it as the model is given it."""
    async with sessionmaker() as session:
        suggestion = await session.get_one(Suggestion, suggestion_id)
        found = await failed_replies(
            session,
            suggestion.base_version_id,
            day_start(suggestion.range_start),
            day_start(suggestion.range_end + timedelta(days=1)),
            limit=EVIDENCE_MAX,
        )
        suggestion.evidence_total = found.total
        items: list[EvidenceItem] = []
        for position, (reply, verdict) in enumerate(found.replies, start=1):
            session.add(
                SuggestionEvidence(
                    organisation_id=suggestion.organisation_id,
                    suggestion_id=suggestion.id,
                    position=position,
                    kind=EvidenceKind.LIVE_VERDICT,
                    message_id=reply.id,
                )
            )
            items.append(await _evidence_item(session, _label(position), reply, verdict))
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
) -> None:
    async with sessionmaker() as session:
        suggestion = await session.get_one(Suggestion, suggestion_id)
        suggestion.finished_at = now
        if error is not None:
            suggestion.status = SuggestionStatus.FAILED
            suggestion.error_message = error
        else:
            suggestion.status = SuggestionStatus.COMPLETED
            suggestion.explanation = explanation
            suggestion.outcome = (
                SuggestionOutcome.CHANGES if changes else SuggestionOutcome.NO_CHANGE
            )
            session.add_all(changes)
        await session.commit()


async def run_suggestion(
    sessionmaker: async_sessionmaker[AsyncSession],
    ports: EvaluationPorts,
    gateway: ModelGateway,
    suggestion_id: uuid.UUID,
    clock: Clock,
) -> None:
    """Gathers the queued Suggestion run's evidence and proposes its Suggestion."""
    await _set_status(sessionmaker, suggestion_id, SuggestionStatus.GATHERING)
    evidence = await _gather(sessionmaker, suggestion_id)
    if not evidence:
        await _finish(sessionmaker, suggestion_id, clock.now(), explanation=NO_EVIDENCE)
        return
    await _set_status(sessionmaker, suggestion_id, SuggestionStatus.PROPOSING)
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
    await _finish(
        sessionmaker,
        suggestion_id,
        clock.now(),
        explanation=proposing.explanation,
        changes=changes,
    )


# Reading


@dataclass(frozen=True)
class EvidenceRead:
    evidence: SuggestionEvidence
    message: Message
    # The reply's Live Verdict outcome, ``pass`` or ``fail``; None when it has none.
    live_verdict: str | None

    @property
    def text_purged(self) -> bool:
        return self.message.purged_at is not None


@dataclass(frozen=True)
class SuggestionRead:
    suggestion: Suggestion
    base_version_number: int
    changes: list[SuggestedChange]
    evidence: list[EvidenceRead]


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
    message_ids = [each.message_id for each in evidence]
    messages = {
        message.id: message
        for message in await session.scalars(select(Message).where(Message.id.in_(message_ids)))
    }
    outcomes = {
        message_id: _outcome(verdict)
        for message_id, verdict in (await live_verdicts_of(session, message_ids)).items()
    }
    return SuggestionRead(
        suggestion,
        version.number,
        changes,
        [
            EvidenceRead(each, messages[each.message_id], outcomes.get(each.message_id))
            for each in evidence
        ],
    )
