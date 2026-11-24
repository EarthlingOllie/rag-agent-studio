"""Evaluation settings routes (Organisation settings, Models): every Member reads the
Evaluation Model, the Evaluation repeats, the Evaluation budget with this month's spend and the
Judging guidance with its versions; Owners set them."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator

from app.auth.api import Db, ErrorResponse
from app.core.clock import Clock, get_clock
from app.credentials.registry import Provider
from app.default_model.api import NOT_FOR_CHAT, NOT_IN_ORGANISATION
from app.default_model.service import CredentialNotInOrganisationError
from app.evaluation import budget, guidance, settings
from app.evaluation.models import GUIDANCE_MAX
from app.gateway.gateway import CapabilityNotGrantedError, ModelNotOfferedError
from app.playground.api import Dollars
from app.tenancy.api import ORGANISATION_PREFIX
from app.tenancy.policy import NOT_FOUND, OWNERS_ONLY, OwnerScope, Scope

router = APIRouter(prefix=ORGANISATION_PREFIX, tags=["models"])

_NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": NOT_FOUND}
}
_OWNERS: dict[int | str, dict[str, Any]] = {
    403: {"model": ErrorResponse, "description": OWNERS_ONLY},
    **_NOT_FOUND,
}

ClockDep = Annotated[Clock, Depends(get_clock)]


class EvaluationModelOut(BaseModel):
    credential_id: uuid.UUID
    credential_name: str
    provider: Provider
    # The model's ID, as the provider knows it, and its display name.
    model: str
    model_name: str


class EvaluationSettingsOut(BaseModel):
    # The model that judges every Evaluation Run; null while the Default Model does.
    evaluation_model: EvaluationModelOut | None
    # How many times each side of a Run answers every case: 1, 3, 5, 7 or 9.
    repeats: int


class SetEvaluationModelRequest(BaseModel):
    """A chat-capable credential and one of its chat models, or both null to judge with the
    Default Model."""

    credential_id: uuid.UUID | None
    model: Annotated[str, Field(min_length=1, max_length=200)] | None

    @model_validator(mode="after")
    def _both_or_neither(self) -> "SetEvaluationModelRequest":
        if (self.credential_id is None) != (self.model is None):
            raise ValueError("Choose a credential and a model, or neither for the Default Model.")
        return self


class SetEvaluationRepeatsRequest(BaseModel):
    repeats: Literal[1, 3, 5, 7, 9]


def _out(current: settings.EvaluationSettings) -> EvaluationSettingsOut:
    chosen = current.evaluation_model
    return EvaluationSettingsOut(
        evaluation_model=None
        if chosen is None
        else EvaluationModelOut(
            credential_id=chosen.credential.id,
            credential_name=chosen.credential.name,
            provider=Provider(chosen.credential.provider),
            model=chosen.model,
            model_name=chosen.model_name,
        ),
        repeats=current.repeats,
    )


@router.get("/evaluation-settings", responses=_NOT_FOUND, operation_id="getEvaluationSettings")
async def get_evaluation_settings(scope: Scope, db: Db) -> EvaluationSettingsOut:
    """The Evaluation Model (null while the Default Model judges) and the Evaluation repeats.
    Open to every Member."""
    return _out(await settings.read_settings(db, scope.organisation_id))


@router.put(
    "/evaluation-model",
    responses={
        **_OWNERS,
        422: {"model": ErrorResponse, "description": "Not a chat model of this Organisation"},
    },
    operation_id="setEvaluationModel",
)
async def set_evaluation_model(
    body: SetEvaluationModelRequest, scope: OwnerScope, db: Db, clock: ClockDep
) -> EvaluationSettingsOut:
    """Sets the Evaluation Model to one of a chat-capable credential's chat models, or with both
    fields null goes back to the Default Model (Owners only). Recorded as
    ``organisation.evaluation_model_changed``."""
    choice = (
        None
        if body.credential_id is None or body.model is None
        else (body.credential_id, body.model)
    )
    try:
        current = await settings.set_evaluation_model(db, scope, choice, now=clock.now())
    except CredentialNotInOrganisationError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, NOT_IN_ORGANISATION) from None
    except CapabilityNotGrantedError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, NOT_FOR_CHAT) from None
    except ModelNotOfferedError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    return _out(current)


@router.put(
    "/evaluation-repeats",
    responses={**_OWNERS, 422: {"description": "Not 1, 3, 5, 7 or 9"}},
    operation_id="setEvaluationRepeats",
)
async def set_evaluation_repeats(
    body: SetEvaluationRepeatsRequest, scope: OwnerScope, db: Db, clock: ClockDep
) -> EvaluationSettingsOut:
    """Sets the Evaluation repeats to 1, 3, 5, 7 or 9 (Owners only). Recorded as
    ``organisation.evaluation_repeats_changed``."""
    return _out(await settings.set_repeats(db, scope, body.repeats, now=clock.now()))


# The largest Evaluation budget, in US dollars.
EVALUATION_BUDGET_MAX = Decimal(1_000_000)


class EvaluationBudgetOut(BaseModel):
    # The most Live Verdicts may spend per calendar month (UTC), in US dollars; null while
    # there is none, and then no reply is sampled.
    evaluation_budget_usd: Dollars | None
    # The first day of the month counted: this one.
    month: date
    # What this month's Live Verdicts have spent, in US dollars. Judgements already under way
    # when the budget is reached still finish, so it can pass the budget slightly.
    spent_usd: Dollars
    # Whether the month's spend has reached the budget, so sampling is paused.
    exhausted: bool
    # Midnight UTC on the 1st of next month, when a new month's spend starts.
    resets_at: datetime


class SetEvaluationBudgetRequest(BaseModel):
    """US dollars and cents above zero, or null for no budget (which stops all sampling)."""

    evaluation_budget_usd: (
        Annotated[Decimal, Field(gt=0, le=EVALUATION_BUDGET_MAX, decimal_places=2)] | None
    )


def _budget_out(found: budget.EvaluationBudget) -> EvaluationBudgetOut:
    return EvaluationBudgetOut(
        evaluation_budget_usd=found.budget_usd,
        month=found.month,
        spent_usd=found.spent_usd.normalize() if found.spent_usd else Decimal(0),
        exhausted=found.exhausted,
        resets_at=found.resets_at,
    )


@router.get("/evaluation-budget", responses=_NOT_FOUND, operation_id="getEvaluationBudget")
async def get_evaluation_budget(scope: Scope, db: Db, clock: ClockDep) -> EvaluationBudgetOut:
    """The Evaluation budget (null while there is none) and this month's spend against it, for
    the meter. Open to every Member."""
    return _budget_out(await budget.read_budget(db, scope.organisation_id, clock.now()))


@router.put(
    "/evaluation-budget",
    responses={**_OWNERS, 422: {"description": "Not dollars and cents above zero"}},
    operation_id="setEvaluationBudget",
)
async def set_evaluation_budget(
    body: SetEvaluationBudgetRequest, scope: OwnerScope, db: Db, clock: ClockDep
) -> EvaluationBudgetOut:
    """Sets the monthly Evaluation budget in US dollars, or with null removes it, which stops
    all sampling while keeping each Agent's Live sample rate (Owners only). Raising it resumes
    sampling at the next reply. Recorded as ``organisation.evaluation_budget_changed``."""
    return _budget_out(
        await budget.set_budget(db, scope, body.evaluation_budget_usd, now=clock.now())
    )


class GuidanceVersionOut(BaseModel):
    # Numbered from 1 in the Organisation.
    version: int
    # Empty when this version removed guidance.
    text: str
    # ``written`` by an Owner, or ``drafted`` by the Evaluation Model and saved by an Owner.
    source: Literal["written", "drafted"]
    # The Member who saved it; null once they are deleted.
    saved_by: str | None
    saved_at: datetime


class JudgingGuidanceOut(BaseModel):
    # The version every new judgement uses; null until guidance is first saved.
    current: GuidanceVersionOut | None
    # Every version, newest first.
    versions: list[GuidanceVersionOut]


class SaveJudgingGuidanceRequest(BaseModel):
    """The new guidance, up to 2,000 characters; empty (or only spaces) removes it."""

    text: Annotated[str, Field(max_length=GUIDANCE_MAX)]


def _version_out(saved: guidance.SavedVersion) -> GuidanceVersionOut:
    version = saved.version
    return GuidanceVersionOut(
        version=version.version,
        text=version.text,
        source=cast(Literal["written", "drafted"], version.source),
        saved_by=saved.saved_by_name,
        saved_at=version.saved_at,
    )


def _guidance_out(found: guidance.Guidance) -> JudgingGuidanceOut:
    return JudgingGuidanceOut(
        current=None if found.current is None else _version_out(found.current),
        versions=[_version_out(saved) for saved in found.versions],
    )


@router.get("/judging-guidance", responses=_NOT_FOUND, operation_id="getJudgingGuidance")
async def get_judging_guidance(scope: Scope, db: Db) -> JudgingGuidanceOut:
    """The Judging guidance every new judgement uses (null until first saved) and its versions,
    newest first. Open to every Member."""
    return _guidance_out(await guidance.read_guidance(db, scope.organisation_id))


@router.put(
    "/judging-guidance",
    responses={**_OWNERS, 422: {"description": "Longer than 2,000 characters"}},
    operation_id="saveJudgingGuidance",
)
async def save_judging_guidance(
    body: SaveJudgingGuidanceRequest, scope: OwnerScope, db: Db, clock: ClockDep
) -> JudgingGuidanceOut:
    """Saves the Judging guidance as a new current version, which new Evaluation Runs and Live
    Verdicts are judged with; empty text removes it (Owners only). Saving the current text again
    changes nothing. Recorded as ``organisation.judging_guidance_changed``."""
    return _guidance_out(await guidance.save_guidance(db, scope, body.text, now=clock.now()))
