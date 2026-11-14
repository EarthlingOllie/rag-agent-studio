"""Evaluation settings routes (Organisation settings, Models): every Member reads the
Evaluation Model and the Evaluation repeats; Owners set them."""

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator

from app.auth.api import Db, ErrorResponse
from app.core.clock import Clock, get_clock
from app.credentials.registry import Provider
from app.default_model.api import NOT_FOR_CHAT, NOT_IN_ORGANISATION
from app.default_model.service import CredentialNotInOrganisationError
from app.evaluation import settings
from app.gateway.gateway import CapabilityNotGrantedError, ModelNotOfferedError
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
