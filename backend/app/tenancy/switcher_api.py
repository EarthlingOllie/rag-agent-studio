"""The Organisation switcher: a Member of several Organisations chooses the active one."""

import uuid

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from app.auth.api import (
    NOT_SIGNED_IN,
    CurrentMember,
    Db,
    ErrorResponse,
    SessionResponse,
    session_response,
)
from app.tenancy.active import ActiveOrganisations
from app.tenancy.policy import NOT_FOUND
from app.tenancy.repository import resolve_scope

router = APIRouter(prefix="/api/auth/me", tags=["organisations"])


class SwitchOrganisationRequest(BaseModel):
    organisation_id: uuid.UUID


@router.put(
    "/active-organisation",
    responses={
        401: {"model": ErrorResponse, "description": NOT_SIGNED_IN},
        404: {"model": ErrorResponse, "description": NOT_FOUND},
    },
    operation_id="switchOrganisation",
)
async def switch_organisation(
    body: SwitchOrganisationRequest, member: CurrentMember, request: Request, db: Db
) -> SessionResponse:
    """Makes one of the Member's Organisations the active one, remembered across sign-ins.

    An Organisation the Member doesn't belong to is 404, the same as one that doesn't exist.
    """
    scope = await resolve_scope(db, member_id=member.id, organisation_id=body.organisation_id)
    if scope is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    await ActiveOrganisations(request.app.state.redis).remember(member.id, scope.organisation_id)
    return await session_response(request, db, member)
