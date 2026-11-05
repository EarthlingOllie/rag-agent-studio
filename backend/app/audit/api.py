"""The Owner-only Audit Event list."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import AwareDatetime, BaseModel

from app.audit.service import AuditFilter, list_events, list_facets
from app.auth.api import Db, ErrorResponse
from app.tenancy.api import ORGANISATION_PREFIX
from app.tenancy.models import Member
from app.tenancy.policy import NOT_FOUND, OWNERS_ONLY, OwnerScope

router = APIRouter(prefix=f"{ORGANISATION_PREFIX}/audit-events", tags=["audit"])

MAX_PAGE_SIZE = 100


class AuditActorOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str


class AuditTargetOut(BaseModel):
    type: str
    id: str | None


class AuditEventOut(BaseModel):
    id: uuid.UUID
    occurred_at: datetime
    actor: AuditActorOut | None
    action: str
    target: AuditTargetOut
    before: dict[str, Any] | None
    after: dict[str, Any] | None


def _actor(member: Member) -> AuditActorOut:
    return AuditActorOut(id=member.id, name=member.name, email=member.email)


class AuditEventPage(BaseModel):
    items: list[AuditEventOut]
    page: int
    page_size: int
    total: int


_OWNER_ROUTE_ERRORS: dict[int | str, dict[str, Any]] = {
    403: {"model": ErrorResponse, "description": OWNERS_ONLY},
    404: {"model": ErrorResponse, "description": NOT_FOUND},
}


@router.get("", responses=_OWNER_ROUTE_ERRORS, operation_id="listAuditEvents")
async def list_audit_events(
    scope: OwnerScope,
    db: Db,
    actor_id: uuid.UUID | None = None,
    action: Annotated[str | None, Query(max_length=100)] = None,
    start: Annotated[
        AwareDatetime | None, Query(description="Only events at or after this time")
    ] = None,
    end: Annotated[AwareDatetime | None, Query(description="Only events before this time")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 25,
) -> AuditEventPage:
    """The Organisation's Audit Events, newest first, filtered by actor, action and time."""
    where = AuditFilter(actor_id=actor_id, action=action, start=start, end=end)
    result = await list_events(db, scope, where, page=page, size=page_size)
    return AuditEventPage(
        items=[
            AuditEventOut(
                id=row.event.id,
                occurred_at=row.event.occurred_at,
                actor=None if row.actor is None else _actor(row.actor),
                action=row.event.action,
                target=AuditTargetOut(type=row.event.target_type, id=row.event.target_id),
                before=row.event.before,
                after=row.event.after,
            )
            for row in result.rows
        ],
        page=page,
        page_size=page_size,
        total=result.total,
    )


class AuditFacetsOut(BaseModel):
    actors: list[AuditActorOut]
    actions: list[str]


@router.get("/facets", responses=_OWNER_ROUTE_ERRORS, operation_id="getAuditFacets")
async def get_audit_facets(scope: OwnerScope, db: Db) -> AuditFacetsOut:
    """The actors and actions that appear in the Organisation's Audit Events, for filtering."""
    facets = await list_facets(db, scope)
    return AuditFacetsOut(actors=[_actor(m) for m in facets.actors], actions=facets.actions)
