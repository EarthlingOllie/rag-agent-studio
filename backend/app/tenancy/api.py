"""Organisation-scoped routes. Every one takes ``Scope``; see ``app.tenancy.policy``."""

import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from app.auth.api import Db, ErrorResponse
from app.tenancy.models import Role
from app.tenancy.policy import NOT_FOUND, Scope
from app.tenancy.repository import get_organisation

ORGANISATION_PREFIX = "/api/organisations/{organisation_id}"

router = APIRouter(prefix=ORGANISATION_PREFIX, tags=["organisations"])


class OrganisationOut(BaseModel):
    id: uuid.UUID
    name: str
    role: Role


@router.get(
    "",
    responses={404: {"model": ErrorResponse, "description": NOT_FOUND}},
    operation_id="getOrganisation",
)
async def read_organisation(scope: Scope, db: Db) -> OrganisationOut:
    """The Organisation, as the signed-in Member sees it."""
    organisation = await get_organisation(db, scope)
    return OrganisationOut(id=organisation.id, name=organisation.name, role=scope.role)
