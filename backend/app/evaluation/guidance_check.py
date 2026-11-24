"""Checking guidance on held-out reviews (spec 19, ticket 19-04).

An Owner checks any guidance text before saving it. Starting a check locks the Organisation's
row, so at most one guidance job (a draft or a check) is in progress per Organisation, and splits
the current Judging setup's Review sample reviews into two halves, stored on the job as review
IDs: the held-out half, which the check re-judges, and the other half (which a draft reads, ticket
19-05). A later job under the same Judging setup keeps the earlier job's halves for the reviews
they hold, and splits only reviews given since, from the one module-level random source seeded
with ``Settings.guidance_split_seed`` (tests set it), so a re-check uses the same halves.

The task re-judges each held-out review's target, rebuilt from what was stored
(``app.evaluation.judge_input``), with the candidate text in place of the guidance it was judged
under, with the current Evaluation Model: one call per target, so a Live Verdict's two checks, or
a Run result's two Verdicts, share it. It counts agreement with the Editor's outcome (agreed,
false passes, false fails), and how many the Judging setup's own outcomes, copied on the reviews,
agreed on. Targets whose text is gone (Purged) are left out. Nothing it does creates or changes a
Verdict or Live Verdict. Each call's Cost is frozen with the cost function and Price table in
force when it is made, and counted in Organisation cost's Evaluation column, never against the
Evaluation budget or the Token Budget. A judge error fails the job; an Owner can cancel it; both
keep what it spent so far. A job started before the Judging setup changed fails, as its reviews
are no longer the current ones.
"""

import dataclasses
import functools
import random
import uuid
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.clock import Clock
from app.evaluation.guidance import JudgingSetup, current_setup
from app.evaluation.judge import Judged, JudgeError, judge
from app.evaluation.judge_input import judge_input
from app.evaluation.live import NO_EVALUATION_MODEL
from app.evaluation.models import (
    GUIDANCE_JOB_IN_PROGRESS,
    EvaluationCaseResult,
    EvaluationVerdict,
    GuidanceJob,
    GuidanceJobKind,
    GuidanceJobStatus,
    GuidanceJudgement,
    LiveVerdict,
    VerdictOutcome,
)
from app.evaluation.ports import EvaluationPorts
from app.evaluation.review_models import VerdictReview
from app.evaluation.reviews import LOW_SAMPLE_BELOW
from app.evaluation.settings import judge_model
from app.gateway.gateway import ModelGateway
from app.pricing.service import credential_pricing, price_table
from app.pricing.table import cost
from app.tenancy.models import Organisation
from app.tenancy.repository import OrganisationScope

TOO_FEW_REVIEWS = "A check needs at least 2 Review sample reviews under the current Judging setup."
SETUP_CHANGED = "The Judging setup changed after the check started. Check again."

# The one random source new reviews are split by.
_draws = random.Random()  # noqa: S311 (sampling, not security)


def seed_draws(seed: int | None) -> None:
    """Seeds the split: the API does at start, with ``Settings.guidance_split_seed``."""
    _draws.seed(seed)


class GuidanceJobInProgressError(Exception):
    """The Organisation already has a draft or check in progress."""


class NothingToCheckError(Exception):
    """There is no model to judge with, or too few reviews to hold half out; ``message`` says
    which."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class GuidanceJobNotFoundError(Exception):
    """No guidance job of the Organisation has that ID."""


class NotInProgressError(Exception):
    """Only a draft or check in progress can be cancelled."""


def low_sample(job: GuidanceJob) -> bool:
    """Whether the check counted fewer held-out reviews than a Low sample allows."""
    return job.judged < LOW_SAMPLE_BELOW


def _setup(job: GuidanceJob) -> JudgingSetup:
    return JudgingSetup(job.judge_provider, job.judge_model, job.judging_guidance_version)


def _split(reviews: list[str], earlier: GuidanceJob | None) -> tuple[list[str], list[str]]:
    """The held-out half and the other half: the earlier job's halves for the reviews they hold,
    and a random split of the rest that keeps the held-out half to half of all of them."""
    present = set(reviews)
    held = [r for r in earlier.held_out if r in present] if earlier else []
    other = [r for r in earlier.other_half if r in present] if earlier else []
    known = {*held, *other}
    new = [r for r in reviews if r not in known]
    _draws.shuffle(new)
    take = min(len(new), max(0, len(reviews) // 2 - len(held)))
    return held + new[:take], other + new[take:]


async def start_check(
    session: AsyncSession, scope: OrganisationScope, text: str, *, now: datetime
) -> GuidanceJob:
    """Starts checking ``text`` (trimmed) on the held-out half of the current Judging setup's
    Review sample reviews, for the caller to enqueue once committed. Raises
    ``GuidanceJobInProgressError`` and ``NothingToCheckError``."""
    await session.execute(
        select(Organisation.id).where(Organisation.id == scope.organisation_id).with_for_update()
    )
    in_progress = await session.scalar(
        select(GuidanceJob.id).where(
            GuidanceJob.organisation_id == scope.organisation_id,
            GuidanceJob.status.in_(GUIDANCE_JOB_IN_PROGRESS),
        )
    )
    if in_progress is not None:
        raise GuidanceJobInProgressError
    setup = await current_setup(session, scope.organisation_id)
    if setup is None:
        raise NothingToCheckError(NO_EVALUATION_MODEL)
    reviews = await session.scalars(
        select(VerdictReview.id)
        .where(
            VerdictReview.organisation_id == scope.organisation_id,
            VerdictReview.from_sample.is_(True),
            VerdictReview.judge_provider == setup.judge_provider,
            VerdictReview.judge_model == setup.judge_model,
            VerdictReview.judging_guidance_version.is_not_distinct_from(setup.guidance_version),
        )
        .order_by(VerdictReview.reviewed_at, VerdictReview.id)
    )
    earlier = await session.scalar(
        select(GuidanceJob)
        .where(
            GuidanceJob.organisation_id == scope.organisation_id,
            GuidanceJob.judge_provider == setup.judge_provider,
            GuidanceJob.judge_model == setup.judge_model,
            GuidanceJob.judging_guidance_version.is_not_distinct_from(setup.guidance_version),
        )
        .order_by(GuidanceJob.created_at.desc())
        .limit(1)
    )
    held_out, other_half = _split([str(r) for r in reviews], earlier)
    if not held_out:
        raise NothingToCheckError(TOO_FEW_REVIEWS)
    job = GuidanceJob(
        organisation_id=scope.organisation_id,
        kind=GuidanceJobKind.CHECK,
        status=GuidanceJobStatus.QUEUED,
        text=text.strip(),
        judge_provider=setup.judge_provider,
        judge_model=setup.judge_model,
        judging_guidance_version=setup.guidance_version,
        held_out=held_out,
        other_half=other_half,
        judged=0,
        left_out=0,
        agreed=0,
        false_passes=0,
        false_fails=0,
        agreed_before=0,
        requested_by=scope.member_id,
        created_at=now,
    )
    session.add(job)
    await session.commit()
    return job


async def read_job(
    session: AsyncSession, organisation_id: uuid.UUID, job_id: uuid.UUID
) -> GuidanceJob:
    """The Organisation's guidance job. Raises ``GuidanceJobNotFoundError``."""
    job = await session.scalar(
        select(GuidanceJob).where(
            GuidanceJob.id == job_id, GuidanceJob.organisation_id == organisation_id
        )
    )
    if job is None:
        raise GuidanceJobNotFoundError
    return job


async def latest_job(session: AsyncSession, organisation_id: uuid.UUID) -> GuidanceJob | None:
    """The Organisation's most recently started guidance job; None before the first."""
    return await session.scalar(
        select(GuidanceJob)
        .where(GuidanceJob.organisation_id == organisation_id)
        .order_by(GuidanceJob.created_at.desc())
        .limit(1)
    )


async def job_cost(session: AsyncSession, job_id: uuid.UUID) -> Decimal:
    """What the job's calls cost, at the prices frozen when each was made."""
    spent = await session.scalar(
        select(func.coalesce(func.sum(GuidanceJudgement.cost_usd), 0)).where(
            GuidanceJudgement.job_id == job_id
        )
    )
    return Decimal(spent or 0)


async def cancel_job(
    session: AsyncSession, scope: OrganisationScope, job_id: uuid.UUID, *, now: datetime
) -> GuidanceJob:
    """Cancels the job in progress: its task stops before its next call, keeping what it
    counted and spent. Raises ``GuidanceJobNotFoundError`` and ``NotInProgressError``."""
    job = await session.scalar(
        select(GuidanceJob)
        .where(GuidanceJob.id == job_id, GuidanceJob.organisation_id == scope.organisation_id)
        .with_for_update()
    )
    if job is None:
        raise GuidanceJobNotFoundError
    if job.status not in GUIDANCE_JOB_IN_PROGRESS:
        raise NotInProgressError
    job.status = GuidanceJobStatus.CANCELLED
    job.finished_at = now
    await session.commit()
    return job


async def _held_out(
    session: AsyncSession, job: GuidanceJob
) -> dict[tuple[str, uuid.UUID], list[VerdictReview]]:
    """The held-out reviews still there, by the target their re-judging rebuilds: a Run's case
    result (for its Verdicts) or a Live Verdict (for its checks)."""
    rows = await session.execute(
        select(VerdictReview, EvaluationVerdict.result_id)
        .outerjoin(EvaluationVerdict, EvaluationVerdict.id == VerdictReview.verdict_id)
        .where(
            VerdictReview.organisation_id == job.organisation_id,
            VerdictReview.id.in_([uuid.UUID(r) for r in job.held_out]),
        )
        .order_by(VerdictReview.reviewed_at, VerdictReview.id)
    )
    targets: defaultdict[tuple[str, uuid.UUID], list[VerdictReview]] = defaultdict(list)
    for review, result_id in rows:
        key = ("live", review.live_verdict_id) if result_id is None else ("run", result_id)
        targets[key].append(review)
    return targets


async def _finish(
    session: AsyncSession,
    job: GuidanceJob,
    status: GuidanceJobStatus,
    now: datetime,
    reason: str | None = None,
) -> None:
    """Finishes the job, unless an Owner cancelled it meanwhile."""
    await session.refresh(job, ["status"], with_for_update=True)
    if job.status != GuidanceJobStatus.CANCELLED:
        job.status = status
        job.error_reason = reason
        job.finished_at = now
    await session.commit()


async def run_guidance_job(
    sessionmaker: async_sessionmaker[AsyncSession],
    ports: EvaluationPorts,
    gateway: ModelGateway,
    job_id: uuid.UUID,
    clock: Clock,
) -> None:
    """Runs a queued check: re-judges each held-out review's target with its text and counts
    the result, until done, failed or cancelled."""
    async with sessionmaker() as session:
        job = await session.get_one(GuidanceJob, job_id, with_for_update=True)
        if job.status != GuidanceJobStatus.QUEUED:
            # Cancelled before its task picked it up.
            await session.commit()
            return
        job.status = GuidanceJobStatus.RUNNING
        job.started_at = clock.now()
        await session.commit()
        chosen = await judge_model(session, job.organisation_id)
        setup = await current_setup(session, job.organisation_id)
        if chosen is None or setup != _setup(job):
            await _finish(session, job, GuidanceJobStatus.FAILED, clock.now(), SETUP_CHANGED)
            return
        pricing = await credential_pricing(session, chosen.credential)
        build = functools.partial(gateway.chat_model, chosen.credential, chosen.model)
        for (kind, target_id), reviews in (await _held_out(session, job)).items():
            await session.refresh(job, ["status"])
            if job.status == GuidanceJobStatus.CANCELLED:
                return
            target: LiveVerdict | EvaluationCaseResult = (
                await session.get_one(LiveVerdict, target_id)
                if kind == "live"
                else await session.get_one(EvaluationCaseResult, target_id)
            )
            request = await judge_input(session, target)
            if request is None:
                # Purged: nothing is re-judged without its text.
                job.left_out += len(reviews)
                await session.commit()
                continue
            try:
                judging = await judge(
                    build,
                    chosen.model,
                    dataclasses.replace(request, guidance=job.text),
                    timeout_s=ports.judge_timeout_s,
                )
            except JudgeError as error:
                await _finish(session, job, GuidanceJobStatus.FAILED, clock.now(), error.message)
                return
            now = clock.now()
            session.add(
                GuidanceJudgement(
                    organisation_id=job.organisation_id,
                    job_id=job.id,
                    agent_id=reviews[0].agent_id,
                    input_tokens=judging.usage.input_tokens,
                    output_tokens=judging.usage.output_tokens,
                    cost_usd=cost(
                        pricing, chosen.model, judging.usage, now, await price_table(session)
                    ),
                    judged_at=now,
                )
            )
            for review in reviews:
                passed = judging.verdicts[cast(Judged, review.check)].passed
                outcome = VerdictOutcome.PASS if passed else VerdictOutcome.FAIL
                job.judged += 1
                job.agreed += outcome == review.outcome
                job.false_passes += outcome == VerdictOutcome.PASS != review.outcome
                job.false_fails += outcome == VerdictOutcome.FAIL != review.outcome
                job.agreed_before += review.evaluation_model_outcome == review.outcome
            await session.commit()
        await _finish(session, job, GuidanceJobStatus.COMPLETED, clock.now())


async def guidance_cost(
    session: AsyncSession, organisation_id: uuid.UUID, start: datetime, before: datetime
) -> dict[uuid.UUID, Decimal]:
    """What guidance jobs' calls cost from ``start`` until ``before``, by the Agent whose target
    each re-judged and by when it was made, at the prices frozen then."""
    rows = await session.execute(
        select(GuidanceJudgement.agent_id, func.sum(GuidanceJudgement.cost_usd))
        .where(
            GuidanceJudgement.organisation_id == organisation_id,
            GuidanceJudgement.cost_usd.is_not(None),
            GuidanceJudgement.judged_at >= start,
            GuidanceJudgement.judged_at < before,
        )
        .group_by(GuidanceJudgement.agent_id)
    )
    # Only calls with a Cost are summed.
    return {agent_id: cast(Decimal, total) for agent_id, total in rows}
