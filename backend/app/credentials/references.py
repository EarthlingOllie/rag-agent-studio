"""The "who references me" registry.

The credentials module knows nothing about its consumers. Each consumer (a Project's
Embedding Model, an Agent's model override, a reranker, a guardrail classifier) registers a
``ReferenceSource`` when the app is built, and deleting a credential is refused while any
source reports a reference to it.
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.tenancy.repository import OrganisationScope


@dataclass(frozen=True)
class CredentialReference:
    """Something that uses a credential: its kind (``agent``, ``project``…), ID and name."""

    kind: str
    id: str
    name: str


ReferenceSource = Callable[
    [AsyncSession, OrganisationScope, uuid.UUID], Awaitable[list[CredentialReference]]
]
"""Answers which of one consumer's items, in the scope's Organisation, use the credential."""


class ReferenceRegistry:
    def __init__(self) -> None:
        self._sources: list[ReferenceSource] = []

    def register(self, source: ReferenceSource) -> Callable[[], None]:
        """Adds a source; the returned function removes it again."""
        self._sources.append(source)
        return lambda: self._sources.remove(source)

    async def references_to(
        self, session: AsyncSession, scope: OrganisationScope, credential_id: uuid.UUID
    ) -> list[CredentialReference]:
        found: list[CredentialReference] = []
        for source in self._sources:
            found.extend(await source(session, scope, credential_id))
        return sorted(found, key=lambda reference: (reference.kind, reference.name, reference.id))
