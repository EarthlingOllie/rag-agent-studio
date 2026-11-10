"""Default Model routes: every Member reads it; Owners set it."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth.api import Db, ErrorResponse
from app.core.clock import Clock, get_clock
from app.credentials.registry import Provider
from app.default_model import service
from app.gateway.gateway import CapabilityNotGrantedError, ModelNotOfferedError
from app.tenancy.api import ORGANISATION_PREFIX
from app.tenancy.policy import NOT_FOUND, OWNERS_ONLY, OwnerScope, Scope

router = APIRouter(prefix=ORGANISATION_PREFIX, tags=["models"])

NOT_IN_ORGANISATION = "Choose one of this Organisation's credentials."
NOT_FOR_CHAT = "That credential can't be used for chat. Choose a chat-capable credential."

_NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": NOT_FOUND}
}


class SetDefaultModelRequest(BaseModel):
    credential_id: uuid.UUID
    model: Annotated[str, Field(min_length=1, max_length=200)]


class DefaultModelOut(BaseModel):
    credential_id: uuid.UUID
    credential_name: str
    provider: Provider
    # The model's ID, as the provider knows it, and its display name.
    model: str
    model_name: str
    # Whether the model can call tools, as Agentic Retrieval Mode needs.
    supports_tools: bool
    updated_at: datetime


def _out(current: service.CurrentDefault) -> DefaultModelOut:
    return DefaultModelOut(
        credential_id=current.credential.id,
        credential_name=current.credential.name,
        provider=Provider(current.credential.provider),
        model=current.model,
        model_name=current.model_name,
        supports_tools=current.supports_tools,
        updated_at=current.updated_at,
    )


@router.get("/default-model", responses=_NOT_FOUND, operation_id="getDefaultModel")
async def get_default_model(scope: Scope, db: Db) -> DefaultModelOut | None:
    """The Organisation's Default Model, or null until an Owner sets one. Open to every Member."""
    current = await service.read_default(db, scope.organisation_id)
    return None if current is None else _out(current)


@router.put(
    "/default-model",
    responses={
        403: {"model": ErrorResponse, "description": OWNERS_ONLY},
        422: {"model": ErrorResponse, "description": "Not a chat model of this Organisation"},
        **_NOT_FOUND,
    },
    operation_id="setDefaultModel",
)
async def set_default_model(
    body: SetDefaultModelRequest,
    scope: OwnerScope,
    db: Db,
    clock: Annotated[Clock, Depends(get_clock)],
) -> DefaultModelOut:
    """Sets the Default Model to one of a chat-capable credential's chat models."""
    try:
        current = await service.set_default(
            db, scope, body.credential_id, body.model, now=clock.now()
        )
    except service.CredentialNotInOrganisationError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, NOT_IN_ORGANISATION) from None
    except CapabilityNotGrantedError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, NOT_FOR_CHAT) from None
    except ModelNotOfferedError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    return _out(current)
