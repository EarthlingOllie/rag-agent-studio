"""Guidance job routes (Organisation settings, Models): Owners start a check of guidance text on
the held-out half of the Review sample reviews (spec 19, ticket 19-04), read whether drafting is
offered and start a draft from disagreements (ticket 19-05), read a job's progress and result,
and cancel it."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.api import Db, ErrorResponse
from app.evaluation import guidance_check, guidance_draft
from app.evaluation.models import GUIDANCE_MAX, GuidanceJob
from app.evaluation.settings_api import ClockDep
from app.evaluation.tasks import enqueue_guidance_job
from app.playground.api import Dollars
from app.tenancy.api import ORGANISATION_PREFIX
from app.tenancy.models import Member
from app.tenancy.policy import NOT_FOUND, OWNERS_ONLY, OwnerScope

router = APIRouter(prefix=ORGANISATION_PREFIX, tags=["models"])

IN_PROGRESS = "A draft or check is already in progress in the Organisation."
NOT_IN_PROGRESS = "Only a draft or check in progress can be cancelled."

_OWNERS: dict[int | str, dict[str, Any]] = {
    403: {"model": ErrorResponse, "description": OWNERS_ONLY},
    404: {"model": ErrorResponse, "description": NOT_FOUND},
}


class DraftPartOut(BaseModel):
    """A part of a draft's explanation: a rule in a short sentence, and the reviews it answers."""

    part: str
    # The IDs of the disagreeing reviews it answers.
    reviews: list[uuid.UUID]


class GuidanceDraftOut(BaseModel):
    """What a completed draft proposes: guidance text, up to 2,000 characters, and its
    explanation."""

    text: str
    explanation: list[DraftPartOut]


class GuidanceJobOut(BaseModel):
    id: uuid.UUID
    # ``check``: re-judging held-out reviews with some guidance text; ``draft``: drafting guidance
    # from the disagreeing reviews outside the held-out half.
    kind: Literal["check", "draft"]
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    # The guidance text checked; a draft's, the current guidance it revises.
    text: str
    # Review sample reviews held out: the check's whole set.
    held_out: int
    # Held-out reviews re-judged so far, and those left out because their text was Purged.
    judged: int
    left_out: int
    # Over the reviews judged, with the text: agreed with the Editor, false passes (it passed,
    # the Editor said fail) and false fails; and how many the current Judging setup agreed on.
    agreed: int
    false_passes: int
    false_fails: int
    agreed_before: int
    # Fewer than 30 reviews judged.
    low_sample: bool
    # A draft's: the disagreeing reviews it gave the Evaluation Model, and, once completed, the
    # guidance it drafted (null until then, and for a check).
    reviews_read: int
    draft: GuidanceDraftOut | None
    # What its Evaluation Model calls cost, in US dollars, at the prices frozen when each was made.
    cost_usd: Dollars
    # Why it failed; null unless it did.
    error_reason: str | None
    # The Owner who started it; null once they are deleted.
    requested_by: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class StartCheckRequest(BaseModel):
    """The guidance text to check, up to 2,000 characters; it needn't be saved."""

    text: Annotated[str, Field(max_length=GUIDANCE_MAX)]


async def _out(session: AsyncSession, job: GuidanceJob) -> GuidanceJobOut:
    requested_by = (
        None
        if job.requested_by is None
        else await session.scalar(select(Member.name).where(Member.id == job.requested_by))
    )
    spent: Decimal = await guidance_check.job_cost(session, job.id)
    return GuidanceJobOut(
        id=job.id,
        kind=cast(Literal["check", "draft"], job.kind),
        status=cast(Any, job.status),
        text=job.text,
        held_out=len(job.held_out),
        judged=job.judged,
        left_out=job.left_out,
        agreed=job.agreed,
        false_passes=job.false_passes,
        false_fails=job.false_fails,
        agreed_before=job.agreed_before,
        low_sample=guidance_check.low_sample(job),
        reviews_read=job.reviews_read,
        draft=None
        if job.draft_text is None
        else GuidanceDraftOut(
            text=job.draft_text,
            explanation=[
                DraftPartOut(part=p["part"], reviews=[uuid.UUID(r) for r in p["reviews"]])
                for p in job.draft_explanation or []
            ],
        ),
        cost_usd=spent.normalize(),
        error_reason=job.error_reason,
        requested_by=requested_by,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


@router.post(
    "/judging-guidance/checks",
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        **_OWNERS,
        409: {"model": ErrorResponse, "description": IN_PROGRESS},
        422: {
            "model": ErrorResponse,
            "description": "No model to judge with, too few reviews, or too long",
        },
    },
    operation_id="startGuidanceCheck",
)
async def start_guidance_check(
    body: StartCheckRequest, scope: OwnerScope, db: Db, clock: ClockDep
) -> GuidanceJobOut:
    """Starts checking guidance text: the Evaluation Model re-judges the held-out half of the
    current Judging setup's Review sample reviews with it, in the background (Owners only). At
    most one draft or check is in progress per Organisation. Its Cost counts in Organisation
    cost, never against the Evaluation budget."""
    try:
        job = await guidance_check.start_check(db, scope, body.text, now=clock.now())
    except guidance_check.GuidanceJobInProgressError:
        raise HTTPException(status.HTTP_409_CONFLICT, IN_PROGRESS) from None
    except guidance_check.NothingToCheckError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, error.message) from None
    await enqueue_guidance_job(job.id)
    await db.refresh(job)
    return await _out(db, job)


class DraftingOut(BaseModel):
    """Whether drafting guidance is offered under the current Judging setup, and its estimate."""

    # Reviews under the current Judging setup whose Editor's outcome differs from the Evaluation
    # Model's, and Review sample reviews; drafting needs ``needs_disagreements`` and
    # ``needs_sample_reviews`` of them.
    disagreements: int
    sample_reviews: int
    needs_disagreements: int
    needs_sample_reviews: int
    # Whether an Owner can draft now; if not, ``missing`` says what is missing.
    offered: bool
    missing: str | None
    # About how many disagreeing reviews a draft would read (those outside the held-out half),
    # and its estimated Cost in US dollars: the Evaluation Model's prices for a fixed allowance
    # per review read. Null when the model has no known price.
    reviews_read: int
    estimated_cost_usd: Dollars | None


@router.get(
    "/judging-guidance/drafting",
    responses={
        **_OWNERS,
        422: {"model": ErrorResponse, "description": "No model to judge with"},
    },
    operation_id="getGuidanceDrafting",
)
async def get_guidance_drafting(scope: OwnerScope, db: Db, clock: ClockDep) -> DraftingOut:
    """Whether drafting guidance from Editors' disagreements is offered under the current
    Judging setup, what is missing if not, and the estimated Cost (Owners only)."""
    try:
        found = await guidance_draft.read_drafting(db, scope.organisation_id, now=clock.now())
    except guidance_check.NothingToCheckError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, error.message) from None
    return DraftingOut(
        disagreements=found.disagreements,
        sample_reviews=found.sample_reviews,
        needs_disagreements=guidance_draft.DRAFT_DISAGREEMENTS,
        needs_sample_reviews=guidance_draft.DRAFT_SAMPLE_REVIEWS,
        offered=found.missing is None,
        missing=found.missing,
        reviews_read=found.reviews_read,
        estimated_cost_usd=None
        if found.estimated_cost_usd is None
        else found.estimated_cost_usd.normalize(),
    )


@router.post(
    "/judging-guidance/drafts",
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        **_OWNERS,
        409: {"model": ErrorResponse, "description": IN_PROGRESS},
        422: {
            "model": ErrorResponse,
            "description": "No model to judge with, or drafting isn't offered yet",
        },
    },
    operation_id="startGuidanceDraft",
)
async def start_guidance_draft(scope: OwnerScope, db: Db, clock: ClockDep) -> GuidanceJobOut:
    """Starts drafting guidance: the Evaluation Model reads the current Judging setup's
    disagreeing reviews outside the held-out half and the current guidance, in the background,
    and proposes guidance with an explanation (Owners only). At most one draft or check is in
    progress per Organisation. Its Cost counts in Organisation cost, never against the
    Evaluation budget."""
    try:
        job = await guidance_draft.start_draft(db, scope, now=clock.now())
    except guidance_check.GuidanceJobInProgressError:
        raise HTTPException(status.HTTP_409_CONFLICT, IN_PROGRESS) from None
    except (guidance_check.NothingToCheckError, guidance_draft.NotOfferedError) as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, error.message) from None
    await enqueue_guidance_job(job.id)
    await db.refresh(job)
    return await _out(db, job)


@router.get("/guidance-jobs/latest", responses=_OWNERS, operation_id="getLatestGuidanceJob")
async def get_latest_guidance_job(scope: OwnerScope, db: Db) -> GuidanceJobOut | None:
    """The most recently started draft or check, with its progress and result; null before the
    first (Owners only)."""
    job = await guidance_check.latest_job(db, scope.organisation_id)
    return None if job is None else await _out(db, job)


@router.get("/guidance-jobs/{job_id}", responses=_OWNERS, operation_id="getGuidanceJob")
async def get_guidance_job(job_id: uuid.UUID, scope: OwnerScope, db: Db) -> GuidanceJobOut:
    """A draft or check, with its progress and result (Owners only)."""
    try:
        job = await guidance_check.read_job(db, scope.organisation_id, job_id)
    except guidance_check.GuidanceJobNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    return await _out(db, job)


@router.post(
    "/guidance-jobs/{job_id}/cancel",
    responses={**_OWNERS, 409: {"model": ErrorResponse, "description": NOT_IN_PROGRESS}},
    operation_id="cancelGuidanceJob",
)
async def cancel_guidance_job(
    job_id: uuid.UUID, scope: OwnerScope, db: Db, clock: ClockDep
) -> GuidanceJobOut:
    """Cancels a draft or check in progress, keeping what it counted and spent (Owners only)."""
    try:
        job = await guidance_check.cancel_job(db, scope, job_id, now=clock.now())
    except guidance_check.GuidanceJobNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    except guidance_check.NotInProgressError:
        raise HTTPException(status.HTTP_409_CONFLICT, NOT_IN_PROGRESS) from None
    return await _out(db, job)
