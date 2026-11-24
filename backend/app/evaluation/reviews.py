"""Verdict reviews, the Review sample and Evaluation Model agreement (spec 18).

The Review sample's pool is, in the Organisation and judged by its current Evaluation Model (or
the Default Model, when none is chosen), with no review:

- every judged Reference answer and grounding Verdict of an answered Run result (outcome pass or
  fail). Expected source and Expect Fallback Text Verdicts aren't judged by the Evaluation Model,
  Stale ones are neither pass nor fail, and an errored answer has no Verdicts, so none of them is
  ever in it;
- both checks (grounding, answers the question) of every judged Live Verdict whose text is all
  still there: not purged, and with no earlier Message of its Conversation purged since the reply
  (a Remembered turn may be gone). Error and skipped Live Verdicts were never judged.

``next_item`` draws one uniformly at random from the pool, from the one module-level random
source seeded with ``Settings.review_sample_seed`` (tests set it), and returns what the
Evaluation Model was given (``app.evaluation.judge_input``), never its outcome or reason.
Submitting stores the review with ``from_sample`` true, replacing any earlier review of the
target, and returns the Evaluation Model's outcome and reason for the reveal. Skipping stores
no review, so the item stays in the pool; it is only counted, against the current Evaluation
Model, so the skip count can be shown beside agreement.

Agreement is counted when read, over the sample reviews of each Evaluation Model, from the
outcomes copied onto each review: agreed, false passes and false fails, overall and per check,
with the rate's Wilson interval. Changing the Evaluation Model starts new figures; the earlier
ones stay listed. Nothing that counts Verdicts reads reviews (ADR-0018).
"""

import random
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from sqlalchemy import ColumnElement, Select, and_, case, exists, func, literal, select, union_all
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute, aliased

from app.agents.models import Agent
from app.analytics.stats import Interval, wilson
from app.conversations.models import Message
from app.evaluation.judge import CitedExcerpt, JudgeRequest
from app.evaluation.judge_input import judge_input
from app.evaluation.models import (
    EvaluationCaseResult,
    EvaluationRun,
    EvaluationVerdict,
    LiveStatus,
    LiveVerdict,
    VerdictKind,
    VerdictOutcome,
)
from app.evaluation.review_models import ReviewSampleSkip, VerdictReview
from app.evaluation.settings import judge_model
from app.runtime.prompt import Turn
from app.tenancy.repository import OrganisationScope

# The Verdicts the Evaluation Model judges, and so the ones that can be reviewed.
REVIEWED_KINDS = (VerdictKind.REFERENCE_ANSWER, VerdictKind.GROUNDING)
JUDGED = (VerdictOutcome.PASS, VerdictOutcome.FAIL)
# A Live Verdict's checks, as reviews name them.
ANSWERS_QUESTION = "answers_question"
LIVE_CHECKS = (VerdictKind.GROUNDING.value, ANSWERS_QUESTION)
# Agreement's checks, in the order they are listed.
CHECK_ORDER = (VerdictKind.GROUNDING.value, ANSWERS_QUESTION, VerdictKind.REFERENCE_ANSWER.value)
# Fewer sample reviews than this are a Low sample, as for the Version KPIs.
LOW_SAMPLE_BELOW = 30

# The one random source the Review sample draws from.
_draws = random.Random()  # noqa: S311 (sampling, not security)


def seed_draws(seed: int | None) -> None:
    """Seeds the draws: the API does at start, with ``Settings.review_sample_seed``."""
    _draws.seed(seed)


@dataclass(frozen=True)
class Judge:
    """An Evaluation Model, as Runs copy it."""

    provider: str
    model: str


@dataclass(frozen=True)
class ReviewChunk:
    excerpt: CitedExcerpt
    cited: bool


@dataclass(frozen=True)
class RunTarget:
    """A Run Verdict."""

    verdict_id: uuid.UUID


@dataclass(frozen=True)
class LiveTarget:
    """One check (one of ``LIVE_CHECKS``) of a Live Verdict."""

    live_verdict_id: uuid.UUID
    check: str


@dataclass(frozen=True)
class SampleItem:
    target: RunTarget | LiveTarget
    check: str
    agent_id: uuid.UUID
    agent_name: str
    question: str
    # Only when the check is the Reference answer.
    reference_answer: str | None
    answer: str
    chunks: list[ReviewChunk]
    # A Live Verdict's reply's Remembered turns, oldest first; empty for a Run Verdict.
    remembered_turns: list[Turn]


@dataclass(frozen=True)
class SampleNext:
    item: SampleItem | None
    # Sample reviews of the current Evaluation Model, in the Organisation and by the Editor.
    reviewed: int
    reviewed_by_you: int


@dataclass(frozen=True)
class Reveal:
    outcome: str
    evaluation_model_outcome: str
    evaluation_model_reason: str | None


@dataclass(frozen=True)
class Figures:
    """Agreement over some sample reviews: how many agreed, false passes (the Evaluation Model
    passed, the Editor said fail) and false fails, and the rate's Wilson interval (None without
    reviews); Low sample under ``LOW_SAMPLE_BELOW`` reviews."""

    reviews: int
    agreed: int
    false_passes: int
    false_fails: int
    interval: Interval | None
    low_sample: bool


@dataclass(frozen=True)
class JudgeAgreement:
    judge: Judge
    overall: Figures
    # Per check that has reviews, in ``CHECK_ORDER``.
    checks: list[tuple[str, Figures]]


@dataclass(frozen=True)
class AgreementRead:
    current: JudgeAgreement | None
    earlier: list[JudgeAgreement]
    # The current Evaluation Model's sample reviews by the reader, and items skipped.
    reviewed_by_you: int
    skipped: int


@dataclass(frozen=True)
class _CheckRow:
    check: str
    reviews: int
    agreed: int
    false_passes: int
    false_fails: int


class NotReviewableError(Exception):
    """No judged Reference answer or grounding Verdict, or judged Live Verdict whose text is
    still there, of the Organisation has that ID."""


async def current_judge(session: AsyncSession, organisation_id: uuid.UUID) -> Judge | None:
    """The model judging now: the Evaluation Model, or else the Default Model."""
    chosen = await judge_model(session, organisation_id)
    return None if chosen is None else Judge(chosen.credential.provider, chosen.model)


def _reviewable(organisation_id: uuid.UUID) -> Select[EvaluationVerdict, EvaluationRun]:
    return (
        select(EvaluationVerdict, EvaluationRun)
        .join(EvaluationCaseResult, EvaluationCaseResult.id == EvaluationVerdict.result_id)
        .join(EvaluationRun, EvaluationRun.id == EvaluationCaseResult.run_id)
        .where(
            EvaluationVerdict.organisation_id == organisation_id,
            EvaluationVerdict.kind.in_(REVIEWED_KINDS),
            EvaluationVerdict.outcome.in_(JUDGED),
            EvaluationCaseResult.answer.is_not(None),
        )
    )


def _of(judge: Judge, organisation_id: uuid.UUID) -> list[ColumnElement[bool]]:
    """The Organisation's Review sample reviews of ``judge``."""
    return [
        VerdictReview.organisation_id == organisation_id,
        VerdictReview.from_sample.is_(True),
        VerdictReview.judge_provider == judge.provider,
        VerdictReview.judge_model == judge.model,
    ]


def _live_reviewable(organisation_id: uuid.UUID) -> Select[LiveVerdict]:
    reply, earlier = aliased(Message), aliased(Message)
    # A Remembered turn purged after the reply was given: it can't be shown as it was judged.
    turn_gone = exists().where(
        earlier.conversation_id == reply.conversation_id,
        earlier.seq < reply.seq,
        earlier.purged_at > reply.created_at,
    )
    return (
        select(LiveVerdict)
        .join(reply, reply.id == LiveVerdict.message_id)
        .where(
            LiveVerdict.organisation_id == organisation_id,
            LiveVerdict.status == LiveStatus.JUDGED,
            LiveVerdict.purged_at.is_(None),
            ~turn_gone,
        )
    )


async def next_item(session: AsyncSession, scope: OrganisationScope) -> SampleNext:
    """One item drawn at random from the pool, or None when it is empty, with review counts."""
    judge = await current_judge(session, scope.organisation_id)
    if judge is None:
        return SampleNext(None, 0, 0)
    runs = (
        _reviewable(scope.organisation_id)
        .outerjoin(VerdictReview, VerdictReview.verdict_id == EvaluationVerdict.id)
        .where(
            EvaluationRun.judge_provider == judge.provider,
            EvaluationRun.judge_model == judge.model,
            VerdictReview.id.is_(None),
        )
        .with_only_columns(
            literal("run").label("target"),
            EvaluationVerdict.id.label("id"),
            EvaluationVerdict.kind.label("check"),
        )
    )
    lives = [
        _live_reviewable(scope.organisation_id)
        .outerjoin(
            VerdictReview,
            and_(VerdictReview.live_verdict_id == LiveVerdict.id, VerdictReview.check == check),
        )
        .where(
            LiveVerdict.judge_provider == judge.provider,
            LiveVerdict.judge_model == judge.model,
            VerdictReview.id.is_(None),
        )
        .with_only_columns(
            literal("live").label("target"), LiveVerdict.id.label("id"), literal(check)
        )
        for check in LIVE_CHECKS
    ]
    pool = union_all(runs, *lives).subquery()
    size = await session.scalar(select(func.count()).select_from(pool)) or 0
    by_you = case((VerdictReview.reviewed_by == scope.member_id, 1), else_=0)
    reviewed, reviewed_by_you = (
        await session.execute(
            select(func.count(), func.coalesce(func.sum(by_you), 0)).where(
                *_of(judge, scope.organisation_id)
            )
        )
    ).one()
    if size == 0:
        return SampleNext(None, reviewed, reviewed_by_you)
    target, target_id, check = (
        await session.execute(
            select(pool).order_by(*pool.c).offset(_draws.randrange(size)).limit(1)
        )
    ).one()
    if target == "run":
        item = await _run_item(session, await session.get_one(EvaluationVerdict, target_id))
    else:
        item = await _live_item(session, await session.get_one(LiveVerdict, target_id), check)
    return SampleNext(item, reviewed, reviewed_by_you)


def _chunks(request: JudgeRequest) -> list[ReviewChunk]:
    return [ReviewChunk(c, True) for c in request.cited] + [
        ReviewChunk(c, False) for c in request.given
    ]


async def _run_item(session: AsyncSession, verdict: EvaluationVerdict) -> SampleItem:
    # Only answered results are in the pool, and their input is always rebuilt.
    request = cast(JudgeRequest, await judge_input(session, verdict))
    result = await session.get_one(EvaluationCaseResult, verdict.result_id)
    run = await session.get_one(EvaluationRun, result.run_id)
    agent = await session.get_one(Agent, run.agent_id)
    return SampleItem(
        target=RunTarget(verdict.id),
        check=verdict.kind,
        agent_id=agent.id,
        agent_name=agent.name,
        question=request.question,
        reference_answer=(
            request.reference_answer if verdict.kind == VerdictKind.REFERENCE_ANSWER else None
        ),
        answer=request.answer,
        chunks=_chunks(request),
        remembered_turns=[],
    )


async def _live_item(session: AsyncSession, verdict: LiveVerdict, check: str) -> SampleItem:
    # Only Live Verdicts whose text is all still there are in the pool.
    request = cast(JudgeRequest, await judge_input(session, verdict))
    agent = await session.get_one(Agent, verdict.agent_id)
    return SampleItem(
        target=LiveTarget(verdict.id, check),
        check=check,
        agent_id=agent.id,
        agent_name=agent.name,
        question=request.question,
        reference_answer=None,
        answer=request.answer,
        chunks=_chunks(request),
        remembered_turns=list(request.earlier_turns),
    )


@dataclass(frozen=True)
class _Reviewed:
    """What a review copies from its target, and the reason revealed with it."""

    agent_id: uuid.UUID
    check: str
    evaluation_model_outcome: str
    evaluation_model_reason: str | None
    judge: Judge


async def _run_target(
    session: AsyncSession, organisation_id: uuid.UUID, target: RunTarget
) -> _Reviewed:
    found = (
        await session.execute(
            _reviewable(organisation_id).where(EvaluationVerdict.id == target.verdict_id)
        )
    ).one_or_none()
    if found is None:
        raise NotReviewableError
    verdict, run = found
    return _Reviewed(
        run.agent_id,
        verdict.kind,
        verdict.outcome,
        verdict.reason,
        Judge(run.judge_provider, run.judge_model),
    )


async def _live_target(
    session: AsyncSession, organisation_id: uuid.UUID, target: LiveTarget
) -> _Reviewed:
    verdict = await session.scalar(
        _live_reviewable(organisation_id).where(LiveVerdict.id == target.live_verdict_id)
    )
    if verdict is None:
        raise NotReviewableError
    grounding = target.check == VerdictKind.GROUNDING
    # A judged Live Verdict has both outcomes and its judge.
    return _Reviewed(
        verdict.agent_id,
        target.check,
        cast(str, verdict.grounded if grounding else verdict.answers_question),
        verdict.grounded_reason if grounding else verdict.answers_question_reason,
        Judge(cast(str, verdict.judge_provider), cast(str, verdict.judge_model)),
    )


async def submit_sample_review(
    session: AsyncSession,
    scope: OrganisationScope,
    target: RunTarget | LiveTarget,
    outcome: VerdictOutcome,
    reason: str | None,
    *,
    now: datetime,
) -> Reveal:
    """Stores the Editor's review of a Review sample item, replacing any earlier review of the
    target, and returns the Evaluation Model's outcome and reason. Raises
    ``NotReviewableError``."""
    if isinstance(target, RunTarget):
        found = await _run_target(session, scope.organisation_id, target)
        keys = {"verdict_id": target.verdict_id}
        conflict: list[InstrumentedAttribute[Any]] = [VerdictReview.verdict_id]
    else:
        found = await _live_target(session, scope.organisation_id, target)
        keys = {"live_verdict_id": target.live_verdict_id}
        conflict = [VerdictReview.live_verdict_id, VerdictReview.check]
    values = {
        "outcome": outcome.value,
        "evaluation_model_outcome": found.evaluation_model_outcome,
        "check": found.check,
        "judge_provider": found.judge.provider,
        "judge_model": found.judge.model,
        "from_sample": True,
        "reason": reason,
        "reviewed_by": scope.member_id,
        "reviewed_at": now,
    }
    await session.execute(
        insert(VerdictReview)
        .values(
            id=uuid.uuid4(),
            organisation_id=scope.organisation_id,
            agent_id=found.agent_id,
            **keys,
            **values,
        )
        .on_conflict_do_update(index_elements=conflict, set_=values)
    )
    await session.commit()
    return Reveal(outcome.value, found.evaluation_model_outcome, found.evaluation_model_reason)


async def skip_sample_item(
    session: AsyncSession, scope: OrganisationScope, *, now: datetime
) -> None:
    """Counts a skipped Review sample item against the current Evaluation Model; stores no
    review, so the item stays in the pool. Raises ``NotReviewableError`` when the Organisation
    has no model to judge with, and so nothing to skip."""
    judge = await current_judge(session, scope.organisation_id)
    if judge is None:
        raise NotReviewableError
    session.add(
        ReviewSampleSkip(
            organisation_id=scope.organisation_id,
            judge_provider=judge.provider,
            judge_model=judge.model,
            skipped_by=scope.member_id,
            skipped_at=now,
        )
    )
    await session.commit()


def _figures(rows: list[_CheckRow]) -> Figures:
    reviews = sum(r.reviews for r in rows)
    agreed = sum(r.agreed for r in rows)
    return Figures(
        reviews=reviews,
        agreed=agreed,
        false_passes=sum(r.false_passes for r in rows),
        false_fails=sum(r.false_fails for r in rows),
        interval=wilson(agreed, reviews),
        low_sample=reviews < LOW_SAMPLE_BELOW,
    )


def _judge_agreement(judge: Judge, rows: list[_CheckRow]) -> JudgeAgreement:
    by_check = sorted(rows, key=lambda r: CHECK_ORDER.index(r.check))
    return JudgeAgreement(
        judge=judge,
        overall=_figures(rows),
        checks=[(r.check, _figures([r])) for r in by_check],
    )


async def read_agreement(session: AsyncSession, scope: OrganisationScope) -> AgreementRead:
    """Evaluation Model agreement, counted now over the Organisation's Review sample reviews:
    the current Evaluation Model's figures (None when there is no model to judge with), each
    earlier one that has reviews (most recently reviewed first), and the current one's review
    counts in the Organisation and by the reader, and its skips."""
    judge = await current_judge(session, scope.organisation_id)
    editor, model = VerdictReview.outcome, VerdictReview.evaluation_model_outcome
    pass_, fail = VerdictOutcome.PASS.value, VerdictOutcome.FAIL.value

    def counted(condition: ColumnElement[bool]) -> ColumnElement[int]:
        return func.coalesce(func.sum(case((condition, 1), else_=0)), 0)

    found = await session.execute(
        select(
            VerdictReview.judge_provider,
            VerdictReview.judge_model,
            VerdictReview.check,
            func.count(),
            counted(editor == model),
            counted(and_(model == pass_, editor == fail)),
            counted(and_(model == fail, editor == pass_)),
            counted(VerdictReview.reviewed_by == scope.member_id),
            func.max(VerdictReview.reviewed_at),
        )
        .where(
            VerdictReview.organisation_id == scope.organisation_id,
            VerdictReview.from_sample.is_(True),
        )
        .group_by(VerdictReview.judge_provider, VerdictReview.judge_model, VerdictReview.check)
    )
    rows: dict[Judge, list[_CheckRow]] = {}
    latest: dict[Judge, datetime] = {}
    by_you = 0
    for provider, model_name, check, *counts, yours, last in found.all():
        key = Judge(provider, model_name)
        rows.setdefault(key, []).append(_CheckRow(check, *counts))
        latest[key] = max(latest.get(key, last), last)
        if key == judge:
            by_you += yours
    earlier = sorted((j for j in rows if j != judge), key=lambda j: latest[j], reverse=True)
    skipped = 0
    if judge is not None:
        skipped = (
            await session.scalar(
                select(func.count()).where(
                    ReviewSampleSkip.organisation_id == scope.organisation_id,
                    ReviewSampleSkip.judge_provider == judge.provider,
                    ReviewSampleSkip.judge_model == judge.model,
                )
            )
            or 0
        )
    current = None if judge is None else _judge_agreement(judge, rows.get(judge, []))
    return AgreementRead(
        current=current,
        earlier=[_judge_agreement(j, rows[j]) for j in earlier],
        reviewed_by_you=by_you,
        skipped=skipped,
    )
