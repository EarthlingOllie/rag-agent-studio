"""Reading and setting the Default Model, and building its chat model through the gateway.

Setting it records ``default_model.changed`` in the same transaction; setting the same
model again changes nothing. The chosen credential's row is share-locked while the Default
Model is written, so a concurrent delete of that credential either finishes first (and the
choice is refused) or sees the new reference (and is refused).
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic_ai.models import Model
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.credentials.models import ProviderCredential
from app.credentials.references import CredentialReference
from app.credentials.registry import Capability, Provider, models_for
from app.default_model.models import DefaultModel
from app.gateway.gateway import ModelGateway, check_offered
from app.tenancy.repository import OrganisationScope

CHANGED = "default_model.changed"


class CredentialNotInOrganisationError(Exception):
    pass


@dataclass(frozen=True)
class CurrentDefault:
    credential: ProviderCredential
    model: str
    updated_at: datetime

    @property
    def model_name(self) -> str:
        offered = models_for(
            Provider(self.credential.provider), self.credential.capabilities, Capability.CHAT
        )
        # A model since dropped from the registry is shown by its ID.
        return {m.id: m.name for m in offered}.get(self.model, self.model)

    def summary(self) -> dict[str, Any]:
        return {
            "credential_id": str(self.credential.id),
            "credential_name": self.credential.name,
            "provider": self.credential.provider,
            "model": self.model,
        }


async def read_default(session: AsyncSession, organisation_id: uuid.UUID) -> CurrentDefault | None:
    row = await session.execute(
        select(DefaultModel, ProviderCredential)
        .join(ProviderCredential, ProviderCredential.id == DefaultModel.credential_id)
        .where(DefaultModel.organisation_id == organisation_id)
    )
    found = row.one_or_none()
    if found is None:
        return None
    default, credential = found
    return CurrentDefault(credential, default.model, default.updated_at)


async def set_default(
    session: AsyncSession,
    scope: OrganisationScope,
    credential_id: uuid.UUID,
    model: str,
    *,
    now: datetime,
) -> CurrentDefault:
    """Makes ``model`` of the credential the Default Model. Raises
    ``CredentialNotInOrganisationError`` or the gateway's ``ModelUnavailableError``."""
    credential = await session.scalar(
        select(ProviderCredential)
        .where(
            ProviderCredential.id == credential_id,
            ProviderCredential.organisation_id == scope.organisation_id,
        )
        .with_for_update(read=True)
    )
    if credential is None:
        raise CredentialNotInOrganisationError
    check_offered(credential, Capability.CHAT, model)
    before = await read_default(session, scope.organisation_id)
    if before is not None and (before.credential.id, before.model) == (credential.id, model):
        return before
    await session.execute(
        insert(DefaultModel)
        .values(
            id=uuid.uuid4(),
            organisation_id=scope.organisation_id,
            credential_id=credential.id,
            model=model,
            updated_at=now,
        )
        .on_conflict_do_update(
            index_elements=[DefaultModel.organisation_id],
            set_={"credential_id": credential.id, "model": model, "updated_at": now},
        )
    )
    after = CurrentDefault(credential, model, now)
    await audit.record(
        session,
        organisation_id=scope.organisation_id,
        actor_id=scope.member_id,
        action=CHANGED,
        target=audit.AuditTarget("organisation", scope.organisation_id),
        before=None if before is None else before.summary(),
        after=after.summary(),
        occurred_at=now,
    )
    await session.commit()
    return after


async def default_chat_model(
    session: AsyncSession, gateway: ModelGateway, organisation_id: uuid.UUID
) -> Model | None:
    """The Organisation's Default Model as a Pydantic AI model, or None when none is set."""
    current = await read_default(session, organisation_id)
    if current is None:
        return None
    return gateway.chat_model(current.credential, current.model)


async def default_model_references(
    session: AsyncSession, scope: OrganisationScope, credential_id: uuid.UUID
) -> list[CredentialReference]:
    """The "who references me" source: the Organisation's Default Model, if it uses the
    credential."""
    current = await read_default(session, scope.organisation_id)
    if current is None or current.credential.id != credential_id:
        return []
    name = f"Default Model ({current.model_name})"
    return [CredentialReference("default_model", str(scope.organisation_id), name)]
