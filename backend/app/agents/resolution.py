"""Resolving an AgentConfig to the models that run it: its chat model (the Model override, or
else the Organisation's Default Model), its Reranker and the LLM classifier of its Guardrails.

The Playground (a Draft), serving the Live Version (an Agent Version) and evaluation all resolve
a configuration through ``resolve_models``, so they answer with the same models a Visitor reply
would. A configuration is refused with a typed error when it has no chat model
(``NoDefaultModelError``) or names a Provider Credential that no longer exists
(``ProviderCredentialGoneError``).

An Agentic configuration whose chat model can't use tools is resolved as Automatic (the
Automatic fallback): saving the Draft checked its model supports tools, but the Default Model
may have changed since, and such an Agent answers as Automatic rather than not at all.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.config import AgentConfig, ModelChoice, RetrievalMode
from app.credentials.models import ProviderCredential
from app.credentials.registry import Provider, supports_tools
from app.default_model.service import read_default


class NoDefaultModelError(Exception):
    """The configuration has no Model override and the Organisation has no Default Model."""


class ProviderCredentialGoneError(Exception):
    """The configuration names a Provider Credential that no longer exists."""


@dataclass(frozen=True)
class ChosenModel:
    """A credential and one of its models: the chat model, the Reranker or the LLM
    classifier."""

    credential: ProviderCredential
    model: str


@dataclass(frozen=True)
class ResolvedModels:
    """The models an AgentConfig runs with. ``config`` is the configuration to answer with: the
    one resolved, or its Automatic fallback when ``automatic_fallback``."""

    config: AgentConfig
    chat: ChosenModel
    reranker: ChosenModel | None
    classifier: ChosenModel | None
    # The configuration is Agentic but its chat model can't use tools, so ``config`` is
    # Automatic.
    automatic_fallback: bool


async def _credentials(
    session: AsyncSession, organisation_id: uuid.UUID, choices: list[ModelChoice]
) -> dict[uuid.UUID, ProviderCredential]:
    if not choices:
        return {}
    found = await session.scalars(
        select(ProviderCredential).where(
            ProviderCredential.id.in_({choice.credential_id for choice in choices}),
            ProviderCredential.organisation_id == organisation_id,
        )
    )
    return {credential.id: credential for credential in found}


async def resolve_models(
    session: AsyncSession, organisation_id: uuid.UUID, config: AgentConfig
) -> ResolvedModels:
    """The chat model, Reranker and LLM classifier ``config`` names, in the Organisation.
    Raises ``NoDefaultModelError`` or ``ProviderCredentialGoneError``."""
    override = config.behaviour.model
    reranker = config.retrieval.reranker
    classifier = config.guardrails.classifier
    named = [choice for choice in (override, reranker, classifier) if choice is not None]
    credentials = await _credentials(session, organisation_id, named)
    if any(choice.credential_id not in credentials for choice in named):
        raise ProviderCredentialGoneError

    def chosen(choice: ModelChoice | None) -> ChosenModel | None:
        if choice is None:
            return None
        return ChosenModel(credentials[choice.credential_id], choice.model)

    chat = chosen(override)
    if chat is None:
        default = await read_default(session, organisation_id)
        if default is None:
            raise NoDefaultModelError
        chat = ChosenModel(default.credential, default.model)
    automatic_fallback = config.retrieval.mode is RetrievalMode.AGENTIC and not supports_tools(
        Provider(chat.credential.provider), chat.model
    )
    if automatic_fallback:
        retrieval = config.retrieval.model_copy(update={"mode": RetrievalMode.AUTOMATIC})
        config = config.model_copy(update={"retrieval": retrieval})
    return ResolvedModels(
        config=config,
        chat=chat,
        reranker=chosen(reranker),
        classifier=chosen(classifier),
        automatic_fallback=automatic_fallback,
    )
