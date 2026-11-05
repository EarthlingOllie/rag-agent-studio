"""A Project's Embedding Model: the choices an Organisation has, choosing one, and the
credential reference a provider model registers.

- The local model needs no credential and is every new Project's default.
- A provider model (Voyage, OpenAI or Bedrock) is chosen together with one of the
  Organisation's Provider Credentials that offers it for ``embeddings``.
- Until re-embedding exists (ticket 03-10), the model can only change while the Project has no
  Documents, so every Chunk of a Project is embedded with its current model.
- The chosen credential is a "who references me" source: it can't be deleted while a Project
  (archived or not) embeds with it. The credential's row is share-locked while the choice is
  written, so a concurrent delete either finishes first (and the choice is refused) or sees
  the new reference (and is refused).
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.credentials.models import ProviderCredential
from app.credentials.references import CredentialReference
from app.credentials.registry import Capability, Provider, models_for
from app.documents.models import Document
from app.embeddings.registry import EMBEDDING_MODELS, LOCAL_MODEL, EmbeddingModel
from app.gateway.gateway import ModelUnavailableError, check_offered
from app.projects.models import Project
from app.projects.service import active_project
from app.tenancy.repository import OrganisationScope

CHANGED = "project.embedding_model_changed"


class EmbeddingChoiceError(Exception):
    """The model and credential don't make a usable Embedding Model; the message says why."""


class ProjectHasDocumentsError(Exception):
    """The Project has Documents, so its Embedding Model can't change (until ticket 03-10)."""


@dataclass(frozen=True)
class EmbeddingChoice:
    """An Embedding Model the Organisation can use, with the credential it is called through."""

    model: EmbeddingModel
    credential: ProviderCredential | None


async def embedding_choices(
    session: AsyncSession, scope: OrganisationScope
) -> list[EmbeddingChoice]:
    """The local model, then each embedding-capable credential's models, by credential name."""
    credentials = await session.scalars(
        select(ProviderCredential)
        .where(ProviderCredential.organisation_id == scope.organisation_id)
        .order_by(func.lower(ProviderCredential.name), ProviderCredential.created_at)
    )
    choices = [EmbeddingChoice(LOCAL_MODEL, None)]
    for credential in credentials:
        offered = models_for(
            Provider(credential.provider), credential.capabilities, Capability.EMBEDDINGS
        )
        choices.extend(EmbeddingChoice(EMBEDDING_MODELS[m.id], credential) for m in offered)
    return choices


async def _credential(
    session: AsyncSession, scope: OrganisationScope, model: EmbeddingModel, credential_id: uuid.UUID
) -> ProviderCredential:
    credential = await session.scalar(
        select(ProviderCredential)
        .where(
            ProviderCredential.id == credential_id,
            ProviderCredential.organisation_id == scope.organisation_id,
        )
        .with_for_update(read=True)
    )
    if credential is None:
        raise EmbeddingChoiceError("There is no such Provider Credential in this Organisation.")
    try:
        check_offered(credential, Capability.EMBEDDINGS, model.id)
    except ModelUnavailableError as error:
        raise EmbeddingChoiceError(str(error)) from None
    return credential


async def _validated(
    session: AsyncSession,
    scope: OrganisationScope,
    model_id: str,
    credential_id: uuid.UUID | None,
) -> EmbeddingModel:
    model = EMBEDDING_MODELS.get(model_id)
    if model is None:
        raise EmbeddingChoiceError(f"There is no Embedding Model {model_id}.")
    if model.is_local:
        if credential_id is not None:
            raise EmbeddingChoiceError(
                "The built-in Embedding Model doesn't use a Provider Credential."
            )
    elif credential_id is None:
        raise EmbeddingChoiceError(f"Choose a Provider Credential for {model_id}.")
    else:
        await _credential(session, scope, model, credential_id)
    return model


def _summary(project: Project) -> dict[str, str | None]:
    credential_id = project.embedding_credential_id
    return {
        "model_id": project.embedding_model_id,
        "credential_id": None if credential_id is None else str(credential_id),
    }


async def set_embedding_model(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    *,
    model_id: str,
    credential_id: uuid.UUID | None,
    now: datetime,
) -> Project:
    """Chooses the Project's Embedding Model and records ``project.embedding_model_changed``.

    Choosing the current model again changes nothing. Raises the Project service's errors,
    ``EmbeddingChoiceError`` and ``ProjectHasDocumentsError``."""
    project = await active_project(session, scope, project_id, lock=True)
    model = await _validated(session, scope, model_id, credential_id)
    if (project.embedding_model_id, project.embedding_credential_id) == (model.id, credential_id):
        return project
    if await session.scalar(select(exists().where(Document.project_id == project.id))):
        raise ProjectHasDocumentsError
    before = _summary(project)
    project.embedding_model_id = model.id
    project.embedding_credential_id = credential_id
    await audit.record(
        session,
        organisation_id=scope.organisation_id,
        actor_id=scope.member_id,
        action=CHANGED,
        target=audit.AuditTarget("project", project.id),
        before=before,
        after=_summary(project),
        occurred_at=now,
    )
    await session.commit()
    return project


async def project_credential(session: AsyncSession, project: Project) -> ProviderCredential | None:
    """The credential the Project's Embedding Model is called through; None for the local one."""
    if project.embedding_credential_id is None:
        return None
    return await session.get(ProviderCredential, project.embedding_credential_id)


async def project_embedding_references(
    session: AsyncSession, scope: OrganisationScope, credential_id: uuid.UUID
) -> list[CredentialReference]:
    """The "who references me" source: the Organisation's Projects, archived or not, that
    embed with the credential."""
    projects = await session.scalars(
        select(Project).where(
            Project.organisation_id == scope.organisation_id,
            Project.embedding_credential_id == credential_id,
        )
    )
    return [
        CredentialReference(
            "project",
            str(project.id),
            f"{project.name} (Embedding Model {project.embedding_model_id})",
        )
        for project in projects
    ]
