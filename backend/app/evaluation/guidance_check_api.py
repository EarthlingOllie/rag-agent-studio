"""Guidance job routes (Organisation settings, Models): Owners start a check of guidance text on
the held-out half of the Review sample reviews, read its progress and result, and cancel it
(spec 19, ticket 19-04)."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.api import Db, ErrorResponse
from app.evaluation import guidance_check
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


class GuidanceJobOut(BaseModel):
    id: uuid.UUID
    # Only ``check`` so far: re-judging held-out reviews with some guidance text.
    kind: Literal["check"]
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    # The guidance text checked.
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
        kind=cast(Literal["check"], job.kind),
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
