"""The Retention Window setting: Owners set how many days Message text and feedback comments
are kept (``app.retention.service``); every Member reads it on ``getOrganisation``."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.auth.api import Db, ErrorResponse
from app.core.clock import Clock, get_clock
from app.retention import service
from app.tenancy.api import ORGANISATION_PREFIX, OrganisationOut, organisation_out
from app.tenancy.policy import MFA_REQUIRED, NOT_FOUND, OWNERS_ONLY, OwnerScope

router = APIRouter(prefix=ORGANISATION_PREFIX, tags=["organisations"])


class RetentionWindowRequest(BaseModel):
    retention_days: int = Field(
        ge=service.MIN_RETENTION_DAYS,
        le=service.MAX_RETENTION_DAYS,
        description="Days Message text and feedback comments are kept before they are purged",
    )


_ERRORS: dict[int | str, dict[str, Any]] = {
    403: {"model": ErrorResponse, "description": f"{MFA_REQUIRED} Or: {OWNERS_ONLY}"},
    404: {"model": ErrorResponse, "description": NOT_FOUND},
}


@router.put("/retention-window", responses=_ERRORS, operation_id="setRetentionWindow")
async def set_retention_window(
    body: RetentionWindowRequest,
    scope: OwnerScope,
    db: Db,
    clock: Annotated[Clock, Depends(get_clock)],
) -> OrganisationOut:
    """Sets the Organisation's Retention Window (Owners only), from 7 to 3650 days. Recorded as
    ``organisation.retention_window_changed``."""
    organisation = await service.set_retention_window(
        db, scope, days=body.retention_days, now=clock.now()
    )
    return organisation_out(organisation, scope)
