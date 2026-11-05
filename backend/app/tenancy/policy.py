"""The policy dependency every Organisation-scoped route uses.

The active Organisation is in the request path (``/api/organisations/{organisation_id}/…``).
A Member who doesn't belong to it gets 404, the same as for an Organisation that doesn't
exist, so the API never reveals what exists in another tenant.
"""

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status

from app.auth.api import CurrentMember, Db
from app.tenancy.models import Role
from app.tenancy.repository import OrganisationScope, resolve_scope

NOT_FOUND = "Not found"
OWNERS_ONLY = "Only Owners can do this"


async def organisation_scope(
    organisation_id: uuid.UUID, member: CurrentMember, db: Db
) -> OrganisationScope:
    scope = await resolve_scope(db, member_id=member.id, organisation_id=organisation_id)
    if scope is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return scope


Scope = Annotated[OrganisationScope, Depends(organisation_scope)]


async def owner_scope(scope: Scope) -> OrganisationScope:
    """The scope of an Owner. An Editor gets 403: they can know the route exists."""
    if scope.role is not Role.OWNER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, OWNERS_ONLY)
    return scope


OwnerScope = Annotated[OrganisationScope, Depends(owner_scope)]
