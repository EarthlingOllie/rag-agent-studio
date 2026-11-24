"""Verdict review routes (spec 18): the Review sample, reviews given where Verdicts are shown (Run
results and the Trace) and Evaluation Model agreement. Every Member (Owners and Editors) reviews
and reads agreement; another Organisation's are not found."""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, model_validator

from app.auth.api import Db, ErrorResponse
from app.core.clock import Clock, get_clock
from app.evaluation import reviews
from app.evaluation.models import VerdictOutcome
from app.evaluation.review_models import REVIEW_REASON_MAX
from app.tenancy.api import ORGANISATION_PREFIX
from app.tenancy.policy import NOT_FOUND, Scope

router = APIRouter(prefix=ORGANISATION_PREFIX, tags=["evaluation"])

_NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": NOT_FOUND}
}

ClockDep = Annotated[Clock, Depends(get_clock)]

Outcome = Literal["pass", "fail"]
Check = Literal["reference_answer", "grounding", "answers_question"]
LiveCheck = Literal["grounding", "answers_question"]


class ReviewChunkOut(BaseModel):
    # The Chunk's label as the Evaluation Model saw it ([C1], [C2] …).
    label: str
    document_name: str
    text: str
    # Whether the answer cited it.
    cited: bool


class RememberedTurnOut(BaseModel):
    question: str
    answer: str


class ReviewSampleItemOut(BaseModel):
    """A judged Verdict or Live Verdict check, as the Evaluation Model was given it, without its
    outcome or reason. Exactly one of ``verdict_id`` and ``live_verdict_id`` is set."""

    # A Run Verdict's ID, or null for a Live Verdict check.
    verdict_id: uuid.UUID | None
    # A Live Verdict's ID, with ``check`` naming which of its checks; null for a Run Verdict.
    live_verdict_id: uuid.UUID | None
    # What is being checked.
    check: Check
    agent_id: uuid.UUID
    agent_name: str
    question: str
    # Only when the check is the Reference answer.
    reference_answer: str | None
    answer: str
    chunks: list[ReviewChunkOut]
    # A Live Verdict's reply's Remembered turns, oldest first, as the Evaluation Model was given
    # them; empty for a Run Verdict.
    remembered_turns: list[RememberedTurnOut]


class ReviewSampleNextOut(BaseModel):
    # Null when there is nothing left to review.
    item: ReviewSampleItemOut | None
    # Review sample reviews of the current Evaluation Model: the Organisation's and yours.
    reviewed: int
    reviewed_by_you: int


class SampleReviewRequest(BaseModel):
    """A review of a Run Verdict (``verdict_id``) or of one check of a Live Verdict
    (``live_verdict_id`` and ``check``): exactly one of the two IDs."""

    verdict_id: uuid.UUID | None = None
    live_verdict_id: uuid.UUID | None = None
    # Which check of the Live Verdict; ignored for a Run Verdict.
    check: Check | None = None
    outcome: Outcome
    # Why the Editor differs from the Evaluation Model, when they do.
    reason: Annotated[str, Field(max_length=REVIEW_REASON_MAX)] | None = None

    @model_validator(mode="after")
    def _one_target(self) -> "SampleReviewRequest":
        if (self.verdict_id is None) == (self.live_verdict_id is None):
            raise ValueError("Give exactly one of verdict_id and live_verdict_id")
        if self.live_verdict_id is not None and self.check not in reviews.LIVE_CHECKS:
            raise ValueError("A Live Verdict's check is grounding or answers_question")
        return self

    def target(self) -> reviews.RunTarget | reviews.LiveTarget:
        if self.verdict_id is not None:
            return reviews.RunTarget(self.verdict_id)
        return reviews.LiveTarget(cast(uuid.UUID, self.live_verdict_id), cast(str, self.check))


class SampleReviewOut(BaseModel):
    """The reveal: the Editor's outcome beside the Evaluation Model's, and its reason."""

    outcome: Outcome
    evaluation_model_outcome: Outcome
    evaluation_model_reason: str | None
    agreed: bool


class AgreementFiguresOut(BaseModel):
    # Review sample reviews, how many agreed with the Evaluation Model, false passes (it passed,
    # the Editor said fail) and false fails.
    reviews: int
    agreed: int
    false_passes: int
    false_fails: int
    # The share that agreed and its Wilson 95% interval; null without a review.
    rate: float | None
    low: float | None
    high: float | None
    # Fewer than 30 reviews: Low sample.
    low_sample: bool


class CheckAgreementOut(AgreementFiguresOut):
    check: Check


class AgreementOut(AgreementFiguresOut):
    """One Evaluation Model's agreement: overall, then per check that has reviews (grounding,
    answers the question, Reference answer)."""

    # The Evaluation Model (or the Default Model, while none is chosen).
    provider: str
    model: str
    checks: list[CheckAgreementOut]


class EvaluationAgreementOut(BaseModel):
    # The current Evaluation Model's; null while the Organisation has no model to judge with.
    current: AgreementOut | None
    # Earlier Evaluation Models that have Review sample reviews, most recently reviewed first.
    earlier: list[AgreementOut]
    # The current Evaluation Model's Review sample reviews: the Organisation's and yours; and
    # the items skipped on the Review sample while it judged.
    reviewed: int
    reviewed_by_you: int
    skipped: int


def _figures(figures: reviews.Figures) -> dict[str, Any]:
    interval = figures.interval
    return {
        "reviews": figures.reviews,
        "agreed": figures.agreed,
        "false_passes": figures.false_passes,
        "false_fails": figures.false_fails,
        "rate": None if interval is None else figures.agreed / figures.reviews,
        "low": None if interval is None else interval.low,
        "high": None if interval is None else interval.high,
        "low_sample": figures.low_sample,
    }


def _agreement(found: reviews.JudgeAgreement) -> AgreementOut:
    return AgreementOut(
        provider=found.judge.provider,
        model=found.judge.model,
        **_figures(found.overall),
        checks=[
            CheckAgreementOut(check=cast(Check, check), **_figures(figures))
            for check, figures in found.checks
        ],
    )


def _item(item: reviews.SampleItem) -> ReviewSampleItemOut:
    target = item.target
    return ReviewSampleItemOut(
        verdict_id=target.verdict_id if isinstance(target, reviews.RunTarget) else None,
        live_verdict_id=target.live_verdict_id if isinstance(target, reviews.LiveTarget) else None,
        check=cast(Check, item.check),
        agent_id=item.agent_id,
        agent_name=item.agent_name,
        question=item.question,
        reference_answer=item.reference_answer,
        answer=item.answer,
        chunks=[
            ReviewChunkOut(
                label=c.excerpt.label,
                document_name=c.excerpt.document_name,
                text=c.excerpt.text,
                cited=c.cited,
            )
            for c in item.chunks
        ],
        remembered_turns=[
            RememberedTurnOut(question=t.question, answer=t.answer) for t in item.remembered_turns
        ],
    )


@router.get("/review-sample/next", responses=_NOT_FOUND, operation_id="getReviewSampleItem")
async def get_review_sample_item(scope: Scope, db: Db) -> ReviewSampleNextOut:
    """One judged Verdict or Live Verdict check drawn at random from those of the current
    Evaluation Model not yet reviewed whose text is still there (null when there are none),
    without the Evaluation Model's outcome or reason, and how many Review sample reviews the
    Organisation and you have given."""
    found = await reviews.next_item(db, scope)
    return ReviewSampleNextOut(
        item=None if found.item is None else _item(found.item),
        reviewed=found.reviewed,
        reviewed_by_you=found.reviewed_by_you,
    )


@router.post(
    "/review-sample/reviews",
    responses={
        **_NOT_FOUND,
        422: {
            "description": "Not pass or fail, a reason over 1,000 characters, or not exactly one "
            "target (a Live Verdict needs its check)"
        },
    },
    operation_id="submitSampleReview",
)
async def submit_sample_review(
    body: SampleReviewRequest, scope: Scope, db: Db, clock: ClockDep
) -> SampleReviewOut:
    """Stores your pass or fail on a Review sample item, replacing any earlier review of it,
    and reveals the Evaluation Model's outcome and reason. A Verdict that isn't a judged
    Reference answer or grounding Verdict of this Organisation, or a Live Verdict that isn't
    judged or whose text is gone, is not found."""
    try:
        reveal = await reviews.submit_sample_review(
            db, scope, body.target(), VerdictOutcome(body.outcome), body.reason, now=clock.now()
        )
    except reviews.NotReviewableError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    return SampleReviewOut(
        outcome=body.outcome,
        evaluation_model_outcome=cast(Outcome, reveal.evaluation_model_outcome),
        evaluation_model_reason=reveal.evaluation_model_reason,
        agreed=reveal.outcome == reveal.evaluation_model_outcome,
    )


@router.post(
    "/review-sample/skips",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": ErrorResponse, "description": "No model to judge with"}},
    operation_id="skipReviewSampleItem",
)
async def skip_review_sample_item(scope: Scope, db: Db, clock: ClockDep) -> None:
    """Counts an item you skipped on the Review sample against the current Evaluation Model.
    No review is stored, so the item stays in the sample. Not found while the Organisation has
    no model to judge with."""
    try:
        await reviews.skip_sample_item(db, scope, now=clock.now())
    except reviews.NotReviewableError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None


@router.get("/evaluation-agreement", responses=_NOT_FOUND, operation_id="getEvaluationAgreement")
async def get_evaluation_agreement(scope: Scope, db: Db) -> EvaluationAgreementOut:
    """Evaluation Model agreement over Review sample reviews: the current Evaluation Model's
    figures (rate with its Wilson interval, Low sample, false passes and false fails, overall
    and per check), the earlier Evaluation Models that have reviews, and how many sample reviews
    the Organisation and you have given and items were skipped."""
    found = await reviews.read_agreement(db, scope)
    current = None if found.current is None else _agreement(found.current)
    return EvaluationAgreementOut(
        current=current,
        earlier=[_agreement(e) for e in found.earlier],
        reviewed=0 if current is None else current.reviews,
        reviewed_by_you=found.reviewed_by_you,
        skipped=found.skipped,
    )


class VerdictReviewOut(BaseModel):
    """An Editor's review of a judged Verdict or Live Verdict check, as shown on it."""

    outcome: Outcome
    # Why the Editor differs, when they said; null without one, or once the Purge cleared it
    # with the Live Verdict's reply ("Text purged", with ``purged_at``).
    reason: str | None
    # The name of the Member who gave it; null once they are deleted.
    reviewed_by: str | None
    reviewed_at: datetime
    # Given blind on the Review sample: only these count towards agreement.
    from_sample: bool
    purged_at: datetime | None


def review_out(found: reviews.ShownReview | None) -> VerdictReviewOut | None:
    if found is None:
        return None
    return VerdictReviewOut(
        outcome=cast(Outcome, found.outcome),
        reason=found.reason,
        reviewed_by=found.reviewed_by,
        reviewed_at=found.reviewed_at,
        from_sample=found.from_sample,
        purged_at=found.purged_at,
    )


class ReviewRequest(BaseModel):
    """An Editor's agree or disagree with the shown pass or fail, as their own pass or fail."""

    outcome: Outcome
    # Why the Editor differs from the Evaluation Model, when they do.
    reason: Annotated[str, Field(max_length=REVIEW_REASON_MAX)] | None = None


_PUT_RESPONSES: dict[int | str, dict[str, Any]] = {
    **_NOT_FOUND,
    422: {"description": "Not pass or fail, or a reason over 1,000 characters"},
}


async def _put(
    target: reviews.RunTarget | reviews.LiveTarget,
    body: ReviewRequest,
    scope: Scope,
    db: Db,
    clock: Clock,
) -> VerdictReviewOut:
    try:
        found = await reviews.put_review(
            db, scope, target, VerdictOutcome(body.outcome), body.reason, now=clock.now()
        )
    except reviews.NotReviewableError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    return cast(VerdictReviewOut, review_out(found))


async def _delete(target: reviews.RunTarget | reviews.LiveTarget, scope: Scope, db: Db) -> Response:
    try:
        await reviews.delete_review(db, scope, target)
    except reviews.NotReviewableError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/verdicts/{verdict_id}/review", responses=_PUT_RESPONSES, operation_id="putVerdictReview"
)
async def put_verdict_review(
    verdict_id: uuid.UUID, body: ReviewRequest, scope: Scope, db: Db, clock: ClockDep
) -> VerdictReviewOut:
    """Stores your review of a judged Reference answer or grounding Verdict in Run results,
    replacing any earlier review of it (one from the Review sample then stops counting towards
    agreement). It takes the Verdict out of the Review sample and never changes the Verdict.
    Any other Verdict, or another Organisation's, is not found."""
    return await _put(reviews.RunTarget(verdict_id), body, scope, db, clock)


@router.delete(
    "/verdicts/{verdict_id}/review",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_NOT_FOUND,
    operation_id="deleteVerdictReview",
)
async def delete_verdict_review(verdict_id: uuid.UUID, scope: Scope, db: Db) -> Response:
    """Removes the Verdict's review, which puts it back in the Review sample. Not found when it
    has none."""
    return await _delete(reviews.RunTarget(verdict_id), scope, db)


@router.put(
    "/live-verdicts/{live_verdict_id}/checks/{check}/review",
    responses=_PUT_RESPONSES,
    operation_id="putLiveVerdictReview",
)
async def put_live_verdict_review(
    live_verdict_id: uuid.UUID,
    check: LiveCheck,
    body: ReviewRequest,
    scope: Scope,
    db: Db,
    clock: ClockDep,
) -> VerdictReviewOut:
    """Stores your review of one check of a judged Live Verdict in the Trace, replacing any
    earlier review of it (one from the Review sample then stops counting towards agreement).
    It takes the check out of the Review sample and never changes the Live Verdict. A Live
    Verdict that isn't judged or whose text is gone, or another Organisation's, is not
    found."""
    return await _put(reviews.LiveTarget(live_verdict_id, check), body, scope, db, clock)


@router.delete(
    "/live-verdicts/{live_verdict_id}/checks/{check}/review",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_NOT_FOUND,
    operation_id="deleteLiveVerdictReview",
)
async def delete_live_verdict_review(
    live_verdict_id: uuid.UUID, check: LiveCheck, scope: Scope, db: Db
) -> Response:
    """Removes the review of the Live Verdict's check, which puts it back in the Review sample
    while its text is still there. Not found when it has none."""
    return await _delete(reviews.LiveTarget(live_verdict_id, check), scope, db)
