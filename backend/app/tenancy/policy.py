"""The one policy dependency every Organisation-scoped route declares its required role with.

The active Organisation is in the request path (``/api/organisations/{organisation_id}/…``).
A route takes ``Scope`` (any Member, Owner or Editor) or ``OwnerScope`` (Owners only); both
are ``RequireRole``. A Member who doesn't belong to the Organisation gets 404, the same as for
an Organisation that doesn't exist, so the API never reveals what exists in another tenant. A
Member whose role is too low gets 403: they can know the route exists.
"""

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, status

from app.auth.api import CurrentMember, Db
from app.tenancy.models import Role
from app.tenancy.repository import OrganisationScope, resolve_scope

NOT_FOUND = "Not found"
OWNERS_ONLY = "Only Owners can do this"

# An Owner can do everything an Editor can.
_RANK = {Role.EDITOR: 0, Role.OWNER: 1}


@dataclass(frozen=True)
class RequireRole:
    """The policy dependency: the signed-in Member's scope, if their role is at least ``role``."""

    role: Role

    async def __call__(
        self, organisation_id: uuid.UUID, member: CurrentMember, db: Db
    ) -> OrganisationScope:
        scope = await resolve_scope(db, member_id=member.id, organisation_id=organisation_id)
        if scope is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
        if _RANK[scope.role] < _RANK[self.role]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, OWNERS_ONLY)
        return scope


Scope = Annotated[OrganisationScope, Depends(RequireRole(Role.EDITOR))]
"""Any Member of the Organisation."""

OwnerScope = Annotated[OrganisationScope, Depends(RequireRole(Role.OWNER))]
"""Owners only; Editors get 403."""
