"""The policy dependency every Organisation-scoped route uses.

The active Organisation is in the request path (``/api/organisations/{organisation_id}/…``).
A Member who doesn't belong to it gets 404, the same as for an Organisation that doesn't
exist, so the API never reveals what exists in another tenant.
"""

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status

from app.auth.api import CurrentMember, Db
from app.tenancy.repository import OrganisationScope, resolve_scope

NOT_FOUND = "Not found"


async def organisation_scope(
    organisation_id: uuid.UUID, member: CurrentMember, db: Db
) -> OrganisationScope:
    scope = await resolve_scope(db, member_id=member.id, organisation_id=organisation_id)
    if scope is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return scope


Scope = Annotated[OrganisationScope, Depends(organisation_scope)]
