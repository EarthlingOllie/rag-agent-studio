"""Price routes: every Member reads a credential's prices; Owners override them.

Prices are US dollars per million tokens, returned as decimal strings ("3", "0.075") so no
amount is rounded through a float.
"""

import uuid
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth.api import Db, ErrorResponse
from app.core.clock import Clock, get_clock
from app.credentials.api import CredentialsService
from app.credentials.registry import Capability
from app.credentials.service import CredentialNotFoundError
from app.pricing import service
from app.pricing.table import Override
from app.tenancy.api import ORGANISATION_PREFIX
from app.tenancy.policy import NOT_FOUND, OWNERS_ONLY, OwnerScope, Scope

router = APIRouter(prefix=ORGANISATION_PREFIX, tags=["prices"])

_NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": NOT_FOUND}
}

# Up to $999,999.999999 per million tokens, to a millionth of a dollar, never negative.
PriceIn = Annotated[
    Decimal, Field(ge=0, max_digits=12, decimal_places=6, allow_inf_nan=False, strict=False)
]


class OverridePricesRequest(BaseModel):
    """A model's prices for this credential. A price left out (or null) keeps the platform's;
    leaving all three out clears the override."""

    model: Annotated[str, Field(min_length=1, max_length=200)]
    input: PriceIn | None = None
    output: PriceIn | None = None
    cached_input: PriceIn | None = None


class PricesOut(BaseModel):
    input: str
    output: str
    cached_input: str


class OptionalPricesOut(BaseModel):
    input: str | None
    output: str | None
    cached_input: str | None


class ModelPricesOut(BaseModel):
    model: str
    model_name: str
    capability: Capability
    # The platform price table's price in effect now, or null when it has none.
    platform: PricesOut | None
    # This credential's override, or null; a null price in it keeps the platform's.
    override: OptionalPricesOut | None
    # What this credential pays: each override, else the platform price.
    effective: OptionalPricesOut


class CredentialPricesOut(BaseModel):
    credential_id: uuid.UUID
    currency: Literal["USD"] = "USD"
    unit: Literal["per million tokens"] = "per million tokens"
    models: list[ModelPricesOut]


def _amount(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _optional(value: Decimal | None) -> str | None:
    return None if value is None else _amount(value)


def _out(pricing: service.ModelPricing) -> ModelPricesOut:
    platform, override, effective = pricing.platform, pricing.override, pricing.effective
    return ModelPricesOut(
        model=pricing.model.id,
        model_name=pricing.model.name,
        capability=pricing.capability,
        platform=None
        if platform is None
        else PricesOut(
            input=_amount(platform.input),
            output=_amount(platform.output),
            cached_input=_amount(platform.cached_input),
        ),
        override=None
        if override is None
        else OptionalPricesOut(
            input=_optional(override.input),
            output=_optional(override.output),
            cached_input=_optional(override.cached_input),
        ),
        effective=OptionalPricesOut(
            input=_optional(effective.input),
            output=_optional(effective.output),
            cached_input=_optional(effective.cached_input),
        ),
    )


@router.get(
    "/credentials/{credential_id}/prices", responses=_NOT_FOUND, operation_id="listCredentialPrices"
)
async def list_credential_prices(
    credential_id: uuid.UUID,
    scope: Scope,
    db: Db,
    credentials: CredentialsService,
    clock: Annotated[Clock, Depends(get_clock)],
) -> CredentialPricesOut:
    """The prices of every model the credential offers: the platform price in effect now, the
    credential's override, and the price that applies. Open to every Member."""
    try:
        credential = await credentials.get(scope, credential_id)
    except CredentialNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    listed = await service.credential_prices(db, credential, clock.now())
    return CredentialPricesOut(credential_id=credential.id, models=[_out(p) for p in listed])


@router.put(
    "/credentials/{credential_id}/prices",
    responses={
        403: {"model": ErrorResponse, "description": OWNERS_ONLY},
        422: {"model": ErrorResponse, "description": "Not a model this credential offers"},
        **_NOT_FOUND,
    },
    operation_id="overrideCredentialPrices",
)
async def override_credential_prices(
    credential_id: uuid.UUID,
    body: OverridePricesRequest,
    scope: OwnerScope,
    db: Db,
    credentials: CredentialsService,
    clock: Annotated[Clock, Depends(get_clock)],
) -> ModelPricesOut:
    """Overrides the credential's prices for one model, for negotiated rates. Owners only."""
    try:
        credential = await credentials.get(scope, credential_id, for_update=True)
    except CredentialNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    override = Override(body.input, body.output, body.cached_input)
    try:
        pricing = await service.set_override(
            db, scope, credential, body.model, override, now=clock.now()
        )
    except service.ModelNotOfferedError:
        detail = f"This credential doesn't offer {body.model}."
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail) from None
    return _out(pricing)
