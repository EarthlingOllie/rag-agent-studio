"""Organisation-scoped routes. Every one takes ``Scope``; see ``app.tenancy.policy``."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth.api import Db, ErrorResponse
from app.core.clock import Clock, get_clock
from app.tenancy import mfa_policy
from app.tenancy.models import Organisation, Role
from app.tenancy.policy import MFA_REQUIRED, NOT_FOUND, OWNERS_ONLY, OwnerScope, Scope
from app.tenancy.repository import OrganisationScope, get_organisation

ORGANISATION_PREFIX = "/api/organisations/{organisation_id}"
OWNER_WITHOUT_MFA = "Turn on MFA for your own account before requiring it."

router = APIRouter(prefix=ORGANISATION_PREFIX, tags=["organisations"])


class OrganisationOut(BaseModel):
    id: uuid.UUID
    name: str
    role: Role
    require_mfa: bool = Field(description="Whether every Member must have MFA turned on")


class MfaPolicyRequest(BaseModel):
    require_mfa: bool


def _out(organisation: Organisation, scope: OrganisationScope) -> OrganisationOut:
    return OrganisationOut(
        id=organisation.id,
        name=organisation.name,
        role=scope.role,
        require_mfa=organisation.require_mfa,
    )


_MFA_REQUIRED_OR_OWNERS_ONLY = f"{MFA_REQUIRED} Or, on an Owner-only route: {OWNERS_ONLY}"


@router.get(
    "",
    responses={
        403: {"model": ErrorResponse, "description": MFA_REQUIRED},
        404: {"model": ErrorResponse, "description": NOT_FOUND},
    },
    operation_id="getOrganisation",
)
async def read_organisation(scope: Scope, db: Db) -> OrganisationOut:
    """The Organisation, as the signed-in Member sees it."""
    return _out(await get_organisation(db, scope), scope)


_POLICY_ERRORS: dict[int | str, dict[str, Any]] = {
    403: {"model": ErrorResponse, "description": _MFA_REQUIRED_OR_OWNERS_ONLY},
    404: {"model": ErrorResponse, "description": NOT_FOUND},
    409: {"model": ErrorResponse, "description": OWNER_WITHOUT_MFA},
}


@router.put("/mfa-policy", responses=_POLICY_ERRORS, operation_id="setMfaPolicy")
async def set_mfa_policy(
    body: MfaPolicyRequest,
    scope: OwnerScope,
    db: Db,
    clock: Annotated[Clock, Depends(get_clock)],
) -> OrganisationOut:
    """Requires MFA of every Member, or stops requiring it (Owners only).

    The Owner must have MFA themselves to turn the policy on.
    """
    try:
        organisation = await mfa_policy.set_require_mfa(
            db, scope, require_mfa=body.require_mfa, now=clock.now()
        )
    except mfa_policy.OwnerWithoutMfaError:
        raise HTTPException(status.HTTP_409_CONFLICT, OWNER_WITHOUT_MFA) from None
    return _out(organisation, scope)
