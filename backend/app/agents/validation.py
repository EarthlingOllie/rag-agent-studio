"""The checks on a Draft that need the database, and the credentials a Draft references.

``AgentConfig`` itself checks shapes and ranges. Saving a Draft also checks, against the
capability registry, that each credential it names belongs to the Organisation and offers the
chosen model for the setting's capability, and that its Tags are the Project's. Every problem
is reported at once, located like a request validation error, so the Studio can show each
message beside its field.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.config import AgentConfig, ModelChoice
from app.agents.models import Agent, AgentDraft, AgentVersion
from app.credentials.models import ProviderCredential
from app.credentials.references import CredentialReference
from app.credentials.registry import Capability
from app.gateway.gateway import CapabilityNotGrantedError, ModelUnavailableError, check_offered
from app.projects.models import Project
from app.tags.models import Tag
from app.tenancy.repository import OrganisationScope

UNKNOWN_CREDENTIAL = "Choose a Provider Credential from this Organisation."
UNKNOWN_TAG = "Choose Tags from this Project."


@dataclass(frozen=True)
class CredentialUse:
    """One setting of an AgentConfig that names a credential."""

    loc: tuple[str, str]
    capability: Capability
    label: str


# Every setting that names a credential: where it is, the capability it needs, and how a
# Credential reference describes it.
CREDENTIAL_USES = (
    CredentialUse(("behaviour", "model"), Capability.CHAT, "model"),
    CredentialUse(("retrieval", "reranker"), Capability.RERANK, "reranker"),
    CredentialUse(("guardrails", "classifier"), Capability.CHAT, "Guardrail classifier"),
)


@dataclass(frozen=True)
class DraftProblem:
    loc: tuple[str | int, ...]
    msg: str
    type: str

    def as_error(self) -> dict[str, object]:
        """The problem in the shape of a request validation error."""
        return {"loc": ["body", *self.loc], "msg": self.msg, "type": self.type}


class InvalidDraftError(Exception):
    def __init__(self, problems: list[DraftProblem]) -> None:
        self.problems = problems


def _choice(config: AgentConfig, use: CredentialUse) -> ModelChoice | None:
    group, field = use.loc
    choice: ModelChoice | None = getattr(getattr(config, group), field)
    return choice


async def check_draft(
    session: AsyncSession, scope: OrganisationScope, project: Project, config: AgentConfig
) -> None:
    """Raises ``InvalidDraftError`` listing every problem. The credentials the Draft names are
    share-locked until the transaction ends, so a concurrent delete of one either finishes
    first (and this save is refused) or sees the new reference (and is refused)."""
    problems: list[DraftProblem] = []
    for use in CREDENTIAL_USES:
        choice = _choice(config, use)
        if choice is None:
            continue
        credential = await session.scalar(
            select(ProviderCredential)
            .where(
                ProviderCredential.id == choice.credential_id,
                ProviderCredential.organisation_id == scope.organisation_id,
            )
            .with_for_update(read=True)
        )
        if credential is None:
            problems.append(
                DraftProblem((*use.loc, "credential_id"), UNKNOWN_CREDENTIAL, "unknown_credential")
            )
            continue
        try:
            check_offered(credential, use.capability, choice.model)
        except ModelUnavailableError as error:
            field = "credential_id" if isinstance(error, CapabilityNotGrantedError) else "model"
            problems.append(DraftProblem((*use.loc, field), str(error), "model_unavailable"))
    tag_ids = config.retrieval.tag_ids
    if tag_ids:
        known = set(
            await session.scalars(
                select(Tag.id).where(Tag.project_id == project.id, Tag.id.in_(tag_ids))
            )
        )
        problems.extend(
            DraftProblem(("retrieval", "tag_ids", index), UNKNOWN_TAG, "unknown_tag")
            for index, tag_id in enumerate(tag_ids)
            if tag_id not in known
        )
    if problems:
        raise InvalidDraftError(problems)


async def agent_references(
    session: AsyncSession, scope: OrganisationScope, credential_id: uuid.UUID
) -> list[CredentialReference]:
    """The "who references me" source: each setting that uses the credential in an Agent's
    Draft, or in its Live Version, which Visitors are served."""
    found: list[CredentialReference] = []
    sources: list[tuple[type[AgentDraft] | type[AgentVersion], ColumnElement[bool], str]] = [
        (AgentDraft, AgentDraft.agent_id == Agent.id, ""),
        (AgentVersion, AgentVersion.id == Agent.live_version_id, " Live Version"),
    ]
    for model, join_on, suffix in sources:
        config_column = model.config
        rows = await session.execute(
            select(Agent, config_column)
            .join(model, join_on)
            .where(
                Agent.organisation_id == scope.organisation_id,
                or_(
                    *(
                        config_column[(*use.loc, "credential_id")].astext == str(credential_id)
                        for use in CREDENTIAL_USES
                    )
                ),
            )
        )
        for agent, stored in rows:
            config = AgentConfig.model_validate(stored)
            found.extend(
                CredentialReference("agent", str(agent.id), f"{agent.name}{suffix} ({use.label})")
                for use in CREDENTIAL_USES
                if (choice := _choice(config, use)) is not None
                and choice.credential_id == credential_id
            )
    return found
