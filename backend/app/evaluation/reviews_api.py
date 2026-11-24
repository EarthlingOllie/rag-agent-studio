"""Review sample and Evaluation Model agreement routes (spec 18). Every Member (Owners and
Editors) uses the Review sample and reads agreement; another Organisation's are not found."""

import uuid
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

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
Check = Literal["reference_answer", "grounding"]


class ReviewChunkOut(BaseModel):
    # The Chunk's label as the Evaluation Model saw it ([C1], [C2] …).
    label: str
    document_name: str
    text: str
    # Whether the answer cited it.
    cited: bool


class ReviewSampleItemOut(BaseModel):
    """A judged Verdict, as the Evaluation Model was given it, without its outcome or reason."""

    verdict_id: uuid.UUID
    # What is being checked.
    check: Check
    agent_id: uuid.UUID
    agent_name: str
    question: str
    # Only when the check is the Reference answer.
    reference_answer: str | None
    answer: str
    chunks: list[ReviewChunkOut]


class ReviewSampleNextOut(BaseModel):
    # Null when there is nothing left to review.
    item: ReviewSampleItemOut | None
    # Review sample reviews of the current Evaluation Model: the Organisation's and yours.
    reviewed: int
    reviewed_by_you: int


class SampleReviewRequest(BaseModel):
    verdict_id: uuid.UUID
    outcome: Outcome
    # Why the Editor differs from the Evaluation Model, when they do.
    reason: Annotated[str, Field(max_length=REVIEW_REASON_MAX)] | None = None


class SampleReviewOut(BaseModel):
    """The reveal: the Editor's outcome beside the Evaluation Model's, and its reason."""

    outcome: Outcome
    evaluation_model_outcome: Outcome
    evaluation_model_reason: str | None
    agreed: bool


class AgreementOut(BaseModel):
    # The Evaluation Model (or the Default Model, while none is chosen).
    provider: str
    model: str
    # Its Review sample reviews, and how many agreed with it.
    reviews: int
    agreed: int


class EvaluationAgreementOut(BaseModel):
    # Null while the Organisation has no model to judge with.
    current: AgreementOut | None


def _item(item: reviews.SampleItem) -> ReviewSampleItemOut:
    return ReviewSampleItemOut(
        verdict_id=item.verdict_id,
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
    )


@router.get("/review-sample/next", responses=_NOT_FOUND, operation_id="getReviewSampleItem")
async def get_review_sample_item(scope: Scope, db: Db) -> ReviewSampleNextOut:
    """One judged Verdict drawn at random from those of the current Evaluation Model not yet
    reviewed (null when there are none), without the Evaluation Model's outcome or reason, and
    how many Review sample reviews the Organisation and you have given."""
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
        422: {"description": "Not pass or fail, or a reason over 1,000 characters"},
    },
    operation_id="submitSampleReview",
)
async def submit_sample_review(
    body: SampleReviewRequest, scope: Scope, db: Db, clock: ClockDep
) -> SampleReviewOut:
    """Stores your pass or fail on a Review sample item, replacing any earlier review of the
    Verdict, and reveals the Evaluation Model's outcome and reason. A Verdict that isn't a judged
    Reference answer or grounding Verdict of this Organisation is not found."""
    try:
        reveal = await reviews.submit_sample_review(
            db, scope, body.verdict_id, VerdictOutcome(body.outcome), body.reason, now=clock.now()
        )
    except reviews.NotReviewableError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    return SampleReviewOut(
        outcome=body.outcome,
        evaluation_model_outcome=cast(Outcome, reveal.evaluation_model_outcome),
        evaluation_model_reason=reveal.evaluation_model_reason,
        agreed=reveal.outcome == reveal.evaluation_model_outcome,
    )


@router.get("/evaluation-agreement", responses=_NOT_FOUND, operation_id="getEvaluationAgreement")
async def get_evaluation_agreement(scope: Scope, db: Db) -> EvaluationAgreementOut:
    """How many Review sample reviews of the current Evaluation Model agreed with it."""
    found = await reviews.read_agreement(db, scope.organisation_id)
    return EvaluationAgreementOut(
        current=None
        if found is None
        else AgreementOut(
            provider=found.judge.provider,
            model=found.judge.model,
            reviews=found.reviews,
            agreed=found.agreed,
        )
    )
