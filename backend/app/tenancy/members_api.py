"""Member routes: the Members list, role changes and removal (Owners), and leaving (anyone)."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.auth.api import Db, ErrorResponse
from app.core.clock import Clock, get_clock
from app.tenancy import members
from app.tenancy.api import ORGANISATION_PREFIX
from app.tenancy.models import Role
from app.tenancy.policy import NOT_FOUND, OWNERS_ONLY, OwnerScope, Scope

router = APIRouter(prefix=ORGANISATION_PREFIX, tags=["members"])

LAST_OWNER = "An Organisation needs at least one Owner. Make someone else an Owner first."

ClockDep = Annotated[Clock, Depends(get_clock)]

_NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": NOT_FOUND}
}
_OWNER_ROUTE_ERRORS: dict[int | str, dict[str, Any]] = {
    403: {"model": ErrorResponse, "description": OWNERS_ONLY},
    **_NOT_FOUND,
}
_LAST_OWNER: dict[int | str, dict[str, Any]] = {
    409: {"model": ErrorResponse, "description": LAST_OWNER}
}


class OrganisationMemberOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    role: Role
    joined_at: datetime


class ChangeRoleRequest(BaseModel):
    role: Role


def _out(entry: members.OrganisationMember) -> OrganisationMemberOut:
    return OrganisationMemberOut(
        id=entry.member.id,
        name=entry.member.name,
        email=entry.member.email,
        role=entry.role,
        joined_at=entry.joined_at,
    )


@router.get("/members", responses=_OWNER_ROUTE_ERRORS, operation_id="listMembers")
async def list_members(scope: OwnerScope, db: Db) -> list[OrganisationMemberOut]:
    """Every Member of the Organisation with their role, in the order they joined."""
    return [_out(entry) for entry in await members.list_members(db, scope)]


@router.patch(
    "/members/{member_id}",
    responses={**_OWNER_ROUTE_ERRORS, **_LAST_OWNER},
    operation_id="changeMemberRole",
)
async def change_member_role(
    member_id: uuid.UUID, body: ChangeRoleRequest, scope: OwnerScope, db: Db, clock: ClockDep
) -> OrganisationMemberOut:
    """Makes the Member an Owner or an Editor. The last Owner can't be demoted."""
    try:
        entry = await members.change_role(db, scope, member_id, role=body.role, now=clock.now())
    except members.MemberNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    except members.LastOwnerError:
        raise HTTPException(status.HTTP_409_CONFLICT, LAST_OWNER) from None
    return _out(entry)


@router.delete(
    "/members/{member_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**_OWNER_ROUTE_ERRORS, **_LAST_OWNER},
    operation_id="removeMember",
)
async def remove_member(member_id: uuid.UUID, scope: OwnerScope, db: Db, clock: ClockDep) -> None:
    """Removes the Member; their access to the Organisation ends at once."""
    try:
        await members.remove_member(db, scope, member_id, now=clock.now())
    except members.MemberNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    except members.LastOwnerError:
        raise HTTPException(status.HTTP_409_CONFLICT, LAST_OWNER) from None


@router.post(
    "/leave",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**_NOT_FOUND, **_LAST_OWNER},
    operation_id="leaveOrganisation",
)
async def leave_organisation(scope: Scope, db: Db, clock: ClockDep) -> None:
    """The signed-in Member leaves the Organisation. Its last Owner can't."""
    try:
        await members.leave(db, scope, now=clock.now())
    except members.LastOwnerError:
        raise HTTPException(status.HTTP_409_CONFLICT, LAST_OWNER) from None
