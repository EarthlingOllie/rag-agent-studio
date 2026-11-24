"""Verdict reviews, the Review sample and Evaluation Model agreement (spec 18).

The Review sample's pool is every judged Reference answer and grounding Verdict of an answered
Run result (outcome pass or fail) in the Organisation, judged by its current Evaluation Model
(or the Default Model, when none is chosen), with no review. Expected source and Expect Fallback
Text Verdicts aren't judged by the Evaluation Model, Stale ones are neither pass nor fail, and an
errored answer has no Verdicts, so none of them is ever in it.

``next_item`` draws one uniformly at random from the pool, from the one module-level random
source seeded with ``Settings.review_sample_seed`` (tests set it), and returns what the
Evaluation Model was given (``app.evaluation.judge_input``), never its outcome or reason.
Submitting stores the review with ``from_sample`` true, replacing any earlier review of the
Verdict, and returns the Evaluation Model's outcome and reason for the reveal. Skipping stores
nothing.

Agreement is counted when read, over the sample reviews of a given Evaluation Model, from the
outcomes copied onto each review. Nothing that counts Verdicts reads reviews (ADR-0018).
"""

import random
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from sqlalchemy import ColumnElement, Select, case, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.models import Agent
from app.evaluation.judge import CitedExcerpt, JudgeRequest
from app.evaluation.judge_input import judge_input
from app.evaluation.models import (
    EvaluationCaseResult,
    EvaluationRun,
    EvaluationVerdict,
    VerdictKind,
    VerdictOutcome,
)
from app.evaluation.review_models import VerdictReview
from app.evaluation.settings import judge_model
from app.tenancy.repository import OrganisationScope

# The Verdicts the Evaluation Model judges, and so the ones that can be reviewed.
REVIEWED_KINDS = (VerdictKind.REFERENCE_ANSWER, VerdictKind.GROUNDING)
JUDGED = (VerdictOutcome.PASS, VerdictOutcome.FAIL)

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
class SampleItem:
    verdict_id: uuid.UUID
    check: str
    agent_id: uuid.UUID
    agent_name: str
    question: str
    # Only when the check is the Reference answer.
    reference_answer: str | None
    answer: str
    chunks: list[ReviewChunk]


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
class Agreement:
    judge: Judge
    reviews: int
    agreed: int


class NotReviewableError(Exception):
    """No judged Reference answer or grounding Verdict of the Organisation has that ID."""


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


async def next_item(session: AsyncSession, scope: OrganisationScope) -> SampleNext:
    """One item drawn at random from the pool, or None when it is empty, with review counts."""
    judge = await current_judge(session, scope.organisation_id)
    if judge is None:
        return SampleNext(None, 0, 0)
    pool = (
        _reviewable(scope.organisation_id)
        .outerjoin(VerdictReview, VerdictReview.verdict_id == EvaluationVerdict.id)
        .where(
            EvaluationRun.judge_provider == judge.provider,
            EvaluationRun.judge_model == judge.model,
            VerdictReview.id.is_(None),
        )
    )
    size = await session.scalar(select(func.count()).select_from(pool.subquery())) or 0
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
    verdict, run = (
        await session.execute(
            pool.order_by(EvaluationVerdict.id).offset(_draws.randrange(size)).limit(1)
        )
    ).one()
    return SampleNext(await _item(session, verdict, run), reviewed, reviewed_by_you)


async def _item(
    session: AsyncSession, verdict: EvaluationVerdict, run: EvaluationRun
) -> SampleItem:
    # Only answered results are in the pool, and their input is always rebuilt.
    request = cast(JudgeRequest, await judge_input(session, verdict))
    agent = await session.get_one(Agent, run.agent_id)
    return SampleItem(
        verdict_id=verdict.id,
        check=verdict.kind,
        agent_id=agent.id,
        agent_name=agent.name,
        question=request.question,
        reference_answer=(
            request.reference_answer if verdict.kind == VerdictKind.REFERENCE_ANSWER else None
        ),
        answer=request.answer,
        chunks=[ReviewChunk(c, True) for c in request.cited]
        + [ReviewChunk(c, False) for c in request.given],
    )


async def submit_sample_review(
    session: AsyncSession,
    scope: OrganisationScope,
    verdict_id: uuid.UUID,
    outcome: VerdictOutcome,
    reason: str | None,
    *,
    now: datetime,
) -> Reveal:
    """Stores the Editor's review of a Review sample item, replacing any earlier review of the
    Verdict, and returns the Evaluation Model's outcome and reason. Raises
    ``NotReviewableError``."""
    found = (
        await session.execute(
            _reviewable(scope.organisation_id).where(EvaluationVerdict.id == verdict_id)
        )
    ).one_or_none()
    if found is None:
        raise NotReviewableError
    verdict, run = found
    values = {
        "outcome": outcome.value,
        "evaluation_model_outcome": verdict.outcome,
        "check": verdict.kind,
        "judge_provider": run.judge_provider,
        "judge_model": run.judge_model,
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
            agent_id=run.agent_id,
            verdict_id=verdict.id,
            **values,
        )
        .on_conflict_do_update(index_elements=[VerdictReview.verdict_id], set_=values)
    )
    await session.commit()
    return Reveal(outcome.value, verdict.outcome, verdict.reason)


async def read_agreement(session: AsyncSession, organisation_id: uuid.UUID) -> Agreement | None:
    """How many sample reviews of the current Evaluation Model agreed with it; None when the
    Organisation has no model to judge with."""
    judge = await current_judge(session, organisation_id)
    if judge is None:
        return None
    agreed = case((VerdictReview.outcome == VerdictReview.evaluation_model_outcome, 1), else_=0)
    reviews, agreeing = (
        await session.execute(
            select(func.count(), func.coalesce(func.sum(agreed), 0)).where(
                *_of(judge, organisation_id)
            )
        )
    ).one()
    return Agreement(judge, reviews, agreeing)
