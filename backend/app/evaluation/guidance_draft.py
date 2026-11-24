"""Drafting guidance from disagreements (spec 19, ticket 19-05).

Drafting is offered once the current Judging setup has at least ``DRAFT_DISAGREEMENTS``
disagreeing reviews (any review whose Editor's outcome differs from the Evaluation Model's) and
``DRAFT_SAMPLE_REVIEWS`` Review sample reviews; ``read_drafting`` says what is missing and
estimates the Cost: the Evaluation Model's prices for a fixed allowance per review read, and one
for the draft, as Suggestion runs do.

Starting a draft takes the same lock and split as a check (``app.evaluation.guidance_check``),
so at most one draft or check is in progress per Organisation and a draft never reads the
held-out half a check re-judges. Its task gives the Evaluation Model, in one call
(``app.evaluation.drafter``), the current guidance and every disagreeing review under the job's
Judging setup outside the held-out half: those made outside the Review sample and those in the
other half. Each gives its check, both outcomes and both reasons, and the input it judged,
rebuilt from what was stored (``app.evaluation.judge_input``); a review whose text was Purged
gives its outcomes alone. The validated draft is stored on the job, for an Owner to edit, check
and save as a ``drafted`` version. A model error, a timeout or invalid output fails the job;
an Owner can cancel it. The call's Cost is frozen with the cost function and Price table in
force when it is made, split between the Agents of the reviews it read in proportion to how
many each had, and counted in Organisation cost's Evaluation column, never against the
Evaluation budget or the Token Budget.
"""

import functools
import math
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.clock import Clock
from app.default_model.service import CurrentDefault
from app.evaluation import guidance_check
from app.evaluation.drafter import DraftError, DraftReview, draft
from app.evaluation.guidance import current_setup, guidance_text
from app.evaluation.guidance_check import (
    NothingToCheckError,
    finish,
    lock_and_split,
    new_job,
    pick_up,
    under,
)
from app.evaluation.judge_input import judge_input
from app.evaluation.live import NO_EVALUATION_MODEL
from app.evaluation.models import (
    EvaluationVerdict,
    GuidanceJob,
    GuidanceJobKind,
    GuidanceJobStatus,
    GuidanceJudgement,
    LiveVerdict,
    VerdictKind,
)
from app.evaluation.ports import EvaluationPorts
from app.evaluation.review_models import VerdictReview
from app.evaluation.settings import judge_model
from app.gateway.gateway import ModelGateway
from app.pricing.service import credential_pricing, price_table
from app.pricing.table import TokenUsage, cost
from app.tenancy.repository import OrganisationScope

# Drafting is offered from this many disagreeing reviews and Review sample reviews.
DRAFT_DISAGREEMENTS = 10
DRAFT_SAMPLE_REVIEWS = 30
# The tokens drafting is estimated to use: a fixed allowance in per review read (its outcomes,
# reasons and judged input), and a fixed allowance out for the draft.
REVIEW_ALLOWANCE = TokenUsage(input_tokens=1_500, output_tokens=0)
DRAFT_OUTPUT_ALLOWANCE = TokenUsage(input_tokens=0, output_tokens=1_000)
NANO = Decimal("0.000000001")

DRAFT_SETUP_CHANGED = "The Judging setup changed after the draft started. Draft again."


@dataclass(frozen=True)
class DraftingRead:
    """Whether drafting is offered under the current Judging setup: its disagreeing and Review
    sample reviews, what is missing (None when offered), and the reviews a draft would read with
    its estimated Cost (None when the model has no known price)."""

    disagreements: int
    sample_reviews: int
    missing: str | None
    reviews_read: int
    estimated_cost_usd: Decimal | None


def _plural(n: int, one: str, many: str) -> str:
    return f"{n:,} {one if n == 1 else many}"


def _missing(disagreements: int, sample_reviews: int) -> str | None:
    """What drafting still needs, in words; None when it has enough."""
    needs: list[str] = []
    if disagreements < DRAFT_DISAGREEMENTS:
        more = DRAFT_DISAGREEMENTS - disagreements
        needs.append(_plural(more, "more disagreeing review", "more disagreeing reviews"))
    if sample_reviews < DRAFT_SAMPLE_REVIEWS:
        more = DRAFT_SAMPLE_REVIEWS - sample_reviews
        needs.append(_plural(more, "more Review sample review", "more Review sample reviews"))
    if not needs:
        return None
    return (
        f"Drafting needs {DRAFT_DISAGREEMENTS} disagreeing reviews and {DRAFT_SAMPLE_REVIEWS} "
        f"Review sample reviews under the current Judging setup: {' and '.join(needs)}."
    )


def _disagreeing(organisation_id: uuid.UUID) -> list[ColumnElement[bool]]:
    return [
        VerdictReview.organisation_id == organisation_id,
        VerdictReview.outcome != VerdictReview.evaluation_model_outcome,
    ]


async def _estimate(
    session: AsyncSession, chosen: CurrentDefault, reviews: int, now: datetime
) -> Decimal | None:
    usage = TokenUsage(
        input_tokens=reviews * REVIEW_ALLOWANCE.input_tokens,
        output_tokens=DRAFT_OUTPUT_ALLOWANCE.output_tokens,
    )
    pricing = await credential_pricing(session, chosen.credential)
    spent = cost(pricing, chosen.model, usage, now, await price_table(session))
    return None if spent is None else spent.quantize(NANO)


async def read_drafting(
    session: AsyncSession, organisation_id: uuid.UUID, *, now: datetime
) -> DraftingRead:
    """Whether drafting is offered now, and its estimate. Raises ``NothingToCheckError`` when
    there is no model to judge with."""
    setup = await current_setup(session, organisation_id)
    chosen = await judge_model(session, organisation_id)
    if setup is None or chosen is None:
        raise NothingToCheckError(NO_EVALUATION_MODEL)
    rows = (
        await session.execute(
            select(VerdictReview.id, VerdictReview.from_sample).where(
                *_disagreeing(organisation_id), *under(setup)
            )
        )
    ).all()
    sample_reviews = (
        await session.scalar(
            select(func.count()).where(
                VerdictReview.organisation_id == organisation_id,
                VerdictReview.from_sample.is_(True),
                *under(setup),
            )
        )
        or 0
    )
    earlier = await guidance_check.latest_split(session, organisation_id, setup)
    held_out = set(earlier.held_out) if earlier else set()
    other_half = set(earlier.other_half) if earlier else set()
    outside = sum(1 for _, from_sample in rows if not from_sample)
    known = sum(1 for review, from_sample in rows if from_sample and str(review) in other_half)
    unsplit = sum(
        1
        for review, from_sample in rows
        if from_sample and str(review) not in held_out | other_half
    )
    # About half the sample reviews not split yet will be held out.
    reads = outside + known + math.ceil(unsplit / 2)
    return DraftingRead(
        disagreements=len(rows),
        sample_reviews=sample_reviews,
        missing=_missing(len(rows), sample_reviews),
        reviews_read=reads,
        estimated_cost_usd=await _estimate(session, chosen, reads, now),
    )


class NotOfferedError(Exception):
    """Drafting isn't offered yet; ``message`` says what is missing."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


async def start_draft(
    session: AsyncSession, scope: OrganisationScope, *, now: datetime
) -> GuidanceJob:
    """Starts drafting guidance from the current Judging setup's disagreements, for the caller
    to enqueue once committed. Raises ``GuidanceJobInProgressError``, ``NothingToCheckError``
    and ``NotOfferedError``."""
    split = await lock_and_split(session, scope)
    offered = await read_drafting(session, scope.organisation_id, now=now)
    if offered.missing is not None:
        raise NotOfferedError(offered.missing)
    current = await guidance_text(session, scope.organisation_id, split.setup.guidance_version)
    job = new_job(scope, GuidanceJobKind.DRAFT, current, split, now)
    session.add(job)
    await session.commit()
    return job


async def _reviews(session: AsyncSession, job: GuidanceJob) -> list[VerdictReview]:
    """The disagreeing reviews under the job's Judging setup outside its held-out half, in the
    order they were given."""
    held_out = [uuid.UUID(review) for review in job.held_out]
    found = await session.scalars(
        select(VerdictReview)
        .where(
            *_disagreeing(job.organisation_id),
            *under(guidance_check.job_setup(job)),
            VerdictReview.id.not_in(held_out),
        )
        .order_by(VerdictReview.reviewed_at, VerdictReview.id)
    )
    return list(found)


async def _draft_review(session: AsyncSession, label: str, review: VerdictReview) -> DraftReview:
    """A review as the drafting model is given it: its outcomes alone once its text is gone."""
    if review.verdict_id is not None:
        verdict = await session.get_one(EvaluationVerdict, review.verdict_id)
        request = await judge_input(session, verdict)
        model_reason = verdict.reason
    else:
        live = await session.get_one(LiveVerdict, review.live_verdict_id)
        request = await judge_input(session, live)
        grounding = review.check == VerdictKind.GROUNDING
        model_reason = live.grounded_reason if grounding else live.answers_question_reason
    return DraftReview(
        label=label,
        check=review.check,
        evaluation_model_outcome=review.evaluation_model_outcome,
        outcome=review.outcome,
        request=request,
        evaluation_model_reason=None if request is None else model_reason,
        reason=None if request is None else review.reason,
    )


def _shares(total: int | Decimal, weights: list[int]) -> list[Decimal]:
    """``total`` split in proportion to ``weights``, the last share taking what rounding left."""
    whole = sum(weights)
    shares = [(Decimal(total) * w / whole).quantize(NANO) for w in weights[:-1]]
    return [*shares, Decimal(total) - sum(shares, Decimal(0))]


def _spent(
    job: GuidanceJob,
    reviews: list[VerdictReview],
    usage: TokenUsage,
    spent: Decimal | None,
    now: datetime,
) -> list[GuidanceJudgement]:
    """The call's tokens and Cost, split between the Agents of the reviews it read."""
    by_agent = Counter(review.agent_id for review in reviews)
    agents, weights = list(by_agent), list(by_agent.values())
    tokens_in = _shares(usage.input_tokens, weights)
    tokens_out = _shares(usage.output_tokens, weights)
    costs = [None] * len(agents) if spent is None else _shares(spent, weights)
    return [
        GuidanceJudgement(
            organisation_id=job.organisation_id,
            job_id=job.id,
            agent_id=agent_id,
            input_tokens=int(tokens_in[n]),
            output_tokens=int(tokens_out[n]),
            cost_usd=costs[n],
            judged_at=now,
        )
        for n, agent_id in enumerate(agents)
    ]


async def run_draft(
    session: AsyncSession,
    ports: EvaluationPorts,
    gateway: ModelGateway,
    job: GuidanceJob,
    chosen: CurrentDefault,
    clock: Clock,
) -> None:
    """Runs a picked-up draft: one call over the reviews it reads, stored once valid."""
    reviews = await _reviews(session, job)
    given = [await _draft_review(session, f"R{n}", review) for n, review in enumerate(reviews, 1)]
    job.reviews_read = len(given)
    await session.commit()
    build = functools.partial(gateway.chat_model, chosen.credential, chosen.model)
    failure: DraftError | None = None
    try:
        drafting = await draft(
            build, chosen.model, job.text, given, timeout_s=ports.judge_timeout_s
        )
        usage: TokenUsage | None = drafting.usage
    except DraftError as error:
        failure, usage = error, error.usage
    now = clock.now()
    if usage is not None:
        pricing = await credential_pricing(session, chosen.credential)
        spent = cost(pricing, chosen.model, usage, now, await price_table(session))
        session.add_all(_spent(job, reviews, usage, spent, now))
    if failure is not None:
        await finish(session, job, GuidanceJobStatus.FAILED, now, failure.message)
        return
    ids = {review.label: str(reviews[n].id) for n, review in enumerate(given)}
    await session.refresh(job, ["status"], with_for_update=True)
    if job.status != GuidanceJobStatus.CANCELLED:
        job.draft_text = drafting.text
        job.draft_explanation = [
            {"part": part.part, "reviews": [ids[label] for label in part.reviews]}
            for part in drafting.explanation
        ]
    await finish(session, job, GuidanceJobStatus.COMPLETED, now)


async def run_guidance_job(
    sessionmaker: async_sessionmaker[AsyncSession],
    ports: EvaluationPorts,
    gateway: ModelGateway,
    job_id: uuid.UUID,
    clock: Clock,
) -> None:
    """Runs a queued guidance job: a draft here, a check in ``app.evaluation.guidance_check``."""
    async with sessionmaker() as session:
        kind = await session.scalar(select(GuidanceJob.kind).where(GuidanceJob.id == job_id))
    if kind == GuidanceJobKind.CHECK:
        await guidance_check.run_guidance_job(sessionmaker, ports, gateway, job_id, clock)
        return
    async with sessionmaker() as session:
        picked = await pick_up(session, job_id, clock, DRAFT_SETUP_CHANGED)
        if picked is not None:
            job, chosen = picked
            await run_draft(session, ports, gateway, job, chosen, clock)
