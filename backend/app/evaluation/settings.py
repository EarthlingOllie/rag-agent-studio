"""The Organisation's evaluation settings: the Evaluation Model and the Evaluation repeats.

The Evaluation Model is a chat-capable credential and one of its chat models, or none, and then
the Default Model judges (``judge_model``). Its credential is a Credential reference
(``evaluation_model_references``), share-locked while it is chosen, as the Default Model's is.
The Evaluation repeats is one of 1, 3, 5, 7 or 9 on the Organisation.

Changing either records ``organisation.evaluation_model_changed`` or
``organisation.evaluation_repeats_changed`` with before and after values, in the same
transaction; setting what is already in force changes and records nothing. Only Owners change
them, which the routes enforce.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.credentials.models import ProviderCredential
from app.credentials.references import CredentialReference
from app.credentials.registry import Capability
from app.default_model.service import (
    CredentialNotInOrganisationError,
    CurrentDefault,
    read_default,
)
from app.evaluation.models import EvaluationModel
from app.gateway.gateway import check_offered
from app.tenancy.models import Organisation
from app.tenancy.repository import OrganisationScope

EVALUATION_MODEL_CHANGED = "organisation.evaluation_model_changed"
EVALUATION_REPEATS_CHANGED = "organisation.evaluation_repeats_changed"


@dataclass(frozen=True)
class EvaluationSettings:
    # None: the Default Model judges.
    evaluation_model: CurrentDefault | None
    repeats: int


async def read_evaluation_model(
    session: AsyncSession, organisation_id: uuid.UUID
) -> CurrentDefault | None:
    """The chosen Evaluation Model (a chat model, in the Default Model's shape), or None."""
    row = await session.execute(
        select(EvaluationModel, ProviderCredential)
        .join(ProviderCredential, ProviderCredential.id == EvaluationModel.credential_id)
        .where(EvaluationModel.organisation_id == organisation_id)
    )
    found = row.one_or_none()
    if found is None:
        return None
    chosen, credential = found
    return CurrentDefault(credential, chosen.model, chosen.updated_at)


async def read_settings(session: AsyncSession, organisation_id: uuid.UUID) -> EvaluationSettings:
    organisation = await session.get_one(Organisation, organisation_id)
    return EvaluationSettings(
        await read_evaluation_model(session, organisation_id), organisation.evaluation_repeats
    )


async def judge_model(session: AsyncSession, organisation_id: uuid.UUID) -> CurrentDefault | None:
    """The model that judges a Run started now: the Evaluation Model, or else the Default
    Model; None when the Organisation has neither."""
    chosen = await read_evaluation_model(session, organisation_id)
    return chosen if chosen is not None else await read_default(session, organisation_id)


async def set_evaluation_model(
    session: AsyncSession,
    scope: OrganisationScope,
    choice: tuple[uuid.UUID, str] | None,
    *,
    now: datetime,
) -> EvaluationSettings:
    """Makes ``choice`` (a credential and one of its chat models) the Evaluation Model, or with
    None goes back to the Default Model. Raises ``CredentialNotInOrganisationError`` or the
    gateway's ``ModelUnavailableError``."""
    before = await read_evaluation_model(session, scope.organisation_id)
    after: CurrentDefault | None = None
    if choice is not None:
        credential_id, model = choice
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
        after = CurrentDefault(credential, model, now)
    if _same(before, after):
        return await read_settings(session, scope.organisation_id)
    if after is None:
        await session.execute(
            delete(EvaluationModel).where(EvaluationModel.organisation_id == scope.organisation_id)
        )
    else:
        await session.execute(
            insert(EvaluationModel)
            .values(
                id=uuid.uuid4(),
                organisation_id=scope.organisation_id,
                credential_id=after.credential.id,
                model=after.model,
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=[EvaluationModel.organisation_id],
                set_={
                    "credential_id": after.credential.id,
                    "model": after.model,
                    "updated_at": now,
                },
            )
        )
    await audit.record(
        session,
        organisation_id=scope.organisation_id,
        actor_id=scope.member_id,
        action=EVALUATION_MODEL_CHANGED,
        target=audit.AuditTarget("organisation", scope.organisation_id),
        before=None if before is None else before.summary(),
        after=None if after is None else after.summary(),
        occurred_at=now,
    )
    await session.commit()
    return await read_settings(session, scope.organisation_id)


def _same(before: CurrentDefault | None, after: CurrentDefault | None) -> bool:
    if before is None or after is None:
        return before is after
    return (before.credential.id, before.model) == (after.credential.id, after.model)


async def set_repeats(
    session: AsyncSession, scope: OrganisationScope, repeats: int, *, now: datetime
) -> EvaluationSettings:
    """Sets the Evaluation repeats; the route checks it is 1, 3, 5, 7 or 9 (odd, so a
    majority always decides)."""
    organisation = (
        await session.scalars(
            select(Organisation).where(Organisation.id == scope.organisation_id).with_for_update()
        )
    ).one()
    before = organisation.evaluation_repeats
    if before != repeats:
        organisation.evaluation_repeats = repeats
        await audit.record(
            session,
            organisation_id=scope.organisation_id,
            actor_id=scope.member_id,
            action=EVALUATION_REPEATS_CHANGED,
            target=audit.AuditTarget("organisation", scope.organisation_id),
            before={"repeats": before},
            after={"repeats": repeats},
            occurred_at=now,
        )
        await session.commit()
    return await read_settings(session, scope.organisation_id)


async def evaluation_model_references(
    session: AsyncSession, scope: OrganisationScope, credential_id: uuid.UUID
) -> list[CredentialReference]:
    """The "who references me" source: the Organisation's Evaluation Model, if it uses the
    credential."""
    chosen = await read_evaluation_model(session, scope.organisation_id)
    if chosen is None or chosen.credential.id != credential_id:
        return []
    name = f"Evaluation Model ({chosen.model_name})"
    return [CredentialReference("evaluation_model", str(scope.organisation_id), name)]
