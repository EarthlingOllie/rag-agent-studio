"""Reading prices and overrides from the database, setting overrides, and the cost of a call.

Setting an override records ``credential.price_overridden`` in the same transaction, with the
override before and after; saving the same prices again changes nothing. The credential's row
is locked while its override is written, so concurrent changes apply one after the other.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.credentials.models import ProviderCredential
from app.credentials.registry import PROVIDERS, Capability, Model, Provider, models_for
from app.pricing.models import ModelPrice, PriceOverride
from app.pricing.table import (
    CredentialPricing,
    Override,
    PriceEntry,
    Prices,
    TokenUsage,
    cost,
    platform_price,
    prices,
)
from app.tenancy.repository import OrganisationScope

OVERRIDDEN = "credential.price_overridden"


class ModelNotOfferedError(Exception):
    pass


@dataclass(frozen=True)
class ModelPricing:
    """One model of a credential: its platform price now, its override and what applies."""

    model: Model
    capability: Capability
    platform: PriceEntry | None
    override: Override | None
    effective: Prices


async def price_table(session: AsyncSession) -> tuple[PriceEntry, ...]:
    """The platform price table, as loaded on migrate."""
    rows = await session.scalars(select(ModelPrice))
    return tuple(
        PriceEntry(
            Provider(row.provider),
            row.model,
            row.effective_from,
            row.input,
            row.output,
            row.cached_input,
        )
        for row in rows
    )


async def credential_pricing(
    session: AsyncSession, credential: ProviderCredential
) -> CredentialPricing:
    """The credential's provider and overrides, for ``app.pricing.table.cost``."""
    rows = await session.scalars(
        select(PriceOverride).where(PriceOverride.credential_id == credential.id)
    )
    return CredentialPricing(
        Provider(credential.provider),
        {row.model: Override(row.input, row.output, row.cached_input) for row in rows},
    )


async def credential_cost(
    session: AsyncSession,
    credential: ProviderCredential,
    model: str,
    usage: TokenUsage,
    at: datetime,
) -> Decimal | None:
    """What ``usage`` of ``model`` through ``credential`` cost at ``at``, in US dollars, or
    None when a price is missing. Cost reporting (spec 07) calls this when a Message is
    written; reporting over many Messages can load the table once and call ``cost``."""
    pricing = await credential_pricing(session, credential)
    return cost(pricing, model, usage, at, await price_table(session))


def _offered(credential: ProviderCredential) -> list[tuple[Model, Capability]]:
    provider = Provider(credential.provider)
    return [
        (model, capability)
        for capability in PROVIDERS[provider].capabilities
        for model in models_for(provider, credential.capabilities, capability)
    ]


async def credential_prices(
    session: AsyncSession, credential: ProviderCredential, at: datetime
) -> list[ModelPricing]:
    """Every model the credential offers, by capability, with the prices that apply at ``at``."""
    table = await price_table(session)
    pricing = await credential_pricing(session, credential)
    provider = Provider(credential.provider)
    return [
        ModelPricing(
            model,
            capability,
            platform_price(provider, model.id, at, table),
            pricing.overrides.get(model.id),
            prices(pricing, model.id, at, table),
        )
        for model, capability in _offered(credential)
    ]


def _summary(model: str, override: Override | None) -> dict[str, Any]:
    values = override or Override()
    return {
        "model": model,
        **{
            name: None if value is None else format(value.normalize(), "f")
            for name, value in (
                ("input", values.input),
                ("output", values.output),
                ("cached_input", values.cached_input),
            )
        },
    }


async def set_override(
    session: AsyncSession,
    scope: OrganisationScope,
    credential: ProviderCredential,
    model: str,
    override: Override,
    *,
    now: datetime,
) -> ModelPricing:
    """Sets the credential's prices for ``model``; an override with no price clears it.
    ``credential`` must be locked by the caller. Raises ``ModelNotOfferedError``."""
    if model not in {offered.id for offered, _ in _offered(credential)}:
        raise ModelNotOfferedError
    before = (await credential_pricing(session, credential)).overrides.get(model)
    after = None if override == Override() else override
    if before != after:
        if after is None:
            await session.execute(
                delete(PriceOverride).where(
                    PriceOverride.credential_id == credential.id, PriceOverride.model == model
                )
            )
        else:
            values = {
                "input": after.input,
                "output": after.output,
                "cached_input": after.cached_input,
                "updated_at": now,
            }
            await session.execute(
                insert(PriceOverride)
                .values(
                    id=uuid.uuid4(),
                    organisation_id=scope.organisation_id,
                    credential_id=credential.id,
                    model=model,
                    **values,
                )
                .on_conflict_do_update(
                    index_elements=[PriceOverride.credential_id, PriceOverride.model], set_=values
                )
            )
        await audit.record(
            session,
            organisation_id=scope.organisation_id,
            actor_id=scope.member_id,
            action=OVERRIDDEN,
            target=audit.AuditTarget("provider_credential", credential.id),
            before=_summary(model, before),
            after=_summary(model, after),
            occurred_at=now,
        )
    await session.commit()
    (pricing,) = [
        p for p in await credential_prices(session, credential, now) if p.model.id == model
    ]
    return pricing
