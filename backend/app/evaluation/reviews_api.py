"""Review sample and Evaluation Model agreement routes (spec 18). Every Member (Owners and
Editors) uses the Review sample and reads agreement; another Organisation's are not found."""

import uuid
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, status
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
