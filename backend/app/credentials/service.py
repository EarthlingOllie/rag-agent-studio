"""Provider Credential operations: list, add, re-check, rotate and delete.

Every secret is checked with the credential verifier before it is stored, sealed with the
envelope-encryption module, and never returned: callers see only the masked suffix. Each
change is recorded as an Audit Event in the same transaction, without the secret.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import AuditTarget, record
from app.core.clock import Clock
from app.credentials.models import ProviderCredential
from app.credentials.references import CredentialReference, ReferenceRegistry
from app.credentials.registry import PROVIDERS, AuthKind, Capability, Provider
from app.credentials.verifier import CheckFailure, CheckResult, CredentialVerifier
from app.crypto.envelope import EnvelopeEncryption
from app.tenancy.repository import OrganisationScope

SUFFIX_LENGTH = 4
PASSED, FAILED = "passed", "failed"


class CredentialNotFoundError(Exception):
    pass


class DuplicateNameError(Exception):
    pass


class UnsupportedCapabilityError(Exception):
    def __init__(self, provider: Provider, capabilities: Sequence[Capability]) -> None:
        self.provider = provider
        self.capabilities = capabilities


class CheckFailedError(Exception):
    def __init__(self, failure: CheckFailure) -> None:
        self.failure = failure


class CredentialInUseError(Exception):
    def __init__(self, references: list[CredentialReference]) -> None:
        self.references = references


def _context(organisation_id: uuid.UUID, credential_id: uuid.UUID) -> bytes:
    return f"provider-credential:{organisation_id}:{credential_id}".encode()


def seal_secret(
    envelope: EnvelopeEncryption, organisation_id: uuid.UUID, credential_id: uuid.UUID, secret: str
) -> bytes:
    """Seals a credential's secret, bound to the credential and its Organisation."""
    return envelope.seal(secret.encode(), context=_context(organisation_id, credential_id))


def open_secret(envelope: EnvelopeEncryption, credential: ProviderCredential) -> str:
    """The credential's secret in plain text. Only the model gateway and checks need it."""
    context = _context(credential.organisation_id, credential.id)
    return envelope.open(credential.secret_sealed, context=context).decode()


def _suffix(secret: str) -> str:
    return secret[-SUFFIX_LENGTH:]


def _summary(credential: ProviderCredential) -> dict[str, Any]:
    return {
        "name": credential.name,
        "provider": credential.provider,
        "auth_kind": credential.auth_kind,
        "capabilities": list(credential.capabilities),
        "masked_suffix": credential.masked_suffix,
    }


def _target(credential_id: uuid.UUID | None) -> AuditTarget:
    return AuditTarget("provider_credential", credential_id)


@dataclass(frozen=True)
class NewCredential:
    name: str
    provider: Provider
    api_key: str
    capabilities: Sequence[Capability] | None = None


class Credentials:
    """The credential operations for one request."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        envelope: EnvelopeEncryption,
        verifier: CredentialVerifier,
        references: ReferenceRegistry,
        clock: Clock,
    ) -> None:
        self._session = session
        self._envelope = envelope
        self._verifier = verifier
        self._references = references
        self._clock = clock

    async def list(self, scope: OrganisationScope) -> list[ProviderCredential]:
        rows = await self._session.scalars(
            select(ProviderCredential)
            .where(ProviderCredential.organisation_id == scope.organisation_id)
            .order_by(ProviderCredential.name)
        )
        return list(rows)

    async def get(
        self, scope: OrganisationScope, credential_id: uuid.UUID, *, for_update: bool = False
    ) -> ProviderCredential:
        query = select(ProviderCredential).where(
            ProviderCredential.id == credential_id,
            ProviderCredential.organisation_id == scope.organisation_id,
        )
        credential = await self._session.scalar(query.with_for_update() if for_update else query)
        if credential is None:
            raise CredentialNotFoundError
        return credential

    async def _record(
        self,
        scope: OrganisationScope,
        action: str,
        credential_id: uuid.UUID | None,
        *,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> None:
        await record(
            self._session,
            organisation_id=scope.organisation_id,
            actor_id=scope.member_id,
            action=action,
            target=_target(credential_id),
            before=before,
            after=after,
            occurred_at=self._clock.now(),
        )

    async def _check_failed(
        self,
        scope: OrganisationScope,
        credential_id: uuid.UUID | None,
        details: dict[str, Any],
        failure: CheckFailure,
    ) -> CheckFailedError:
        """Records the failed check, commits it, and returns the error to raise."""
        await self._record(
            scope, "credential.check_failed", credential_id, after=details | {"reason": failure}
        )
        await self._session.commit()
        return CheckFailedError(failure)

    async def create(self, scope: OrganisationScope, new: NewCredential) -> ProviderCredential:
        """Checks the key, then stores the credential. A failed check stores nothing."""
        spec = PROVIDERS[new.provider]
        capabilities = list(spec.capabilities if new.capabilities is None else new.capabilities)
        unsupported = [c for c in capabilities if c not in spec.capabilities]
        if unsupported:
            raise UnsupportedCapabilityError(new.provider, unsupported)
        capabilities = [c for c in spec.capabilities if c in capabilities]
        if await self._name_taken(scope, new.name):
            raise DuplicateNameError
        result = await self._verifier.check(new.provider, new.api_key)
        if result.failure is not None:
            details = {
                "name": new.name,
                "provider": new.provider,
                "masked_suffix": _suffix(new.api_key),
            }
            raise await self._check_failed(scope, None, details, result.failure)
        now = self._clock.now()
        credential_id = uuid.uuid4()
        credential = ProviderCredential(
            id=credential_id,
            organisation_id=scope.organisation_id,
            name=new.name,
            provider=new.provider,
            auth_kind=AuthKind.API_KEY,
            secret_sealed=seal_secret(
                self._envelope, scope.organisation_id, credential_id, new.api_key
            ),
            masked_suffix=_suffix(new.api_key),
            capabilities=[str(c) for c in capabilities],
            check_status=PASSED,
            check_failure=None,
            last_checked_at=now,
            secret_set_at=now,
        )
        self._session.add(credential)
        try:
            await self._session.flush()
        except IntegrityError:
            # Another request took the name between the check above and this insert.
            await self._session.rollback()
            raise DuplicateNameError from None
        await self._record(scope, "credential.created", credential_id, after=_summary(credential))
        await self._session.commit()
        return credential

    async def _name_taken(self, scope: OrganisationScope, name: str) -> bool:
        existing = await self._session.scalar(
            select(ProviderCredential.id).where(
                ProviderCredential.organisation_id == scope.organisation_id,
                ProviderCredential.name == name,
            )
        )
        return existing is not None

    async def recheck(
        self, scope: OrganisationScope, credential_id: uuid.UUID
    ) -> ProviderCredential:
        """Checks the stored secret again and records the outcome on the credential."""
        credential = await self.get(scope, credential_id, for_update=True)
        result = await self._verifier.check(
            Provider(credential.provider), open_secret(self._envelope, credential)
        )
        self._apply(credential, result)
        if result.failure is None:
            await self._record(scope, "credential.checked", credential.id, after={"status": PASSED})
        else:
            await self._record(
                scope,
                "credential.check_failed",
                credential.id,
                after=_summary(credential) | {"reason": result.failure},
            )
        await self._session.commit()
        return credential

    def _apply(self, credential: ProviderCredential, result: CheckResult) -> None:
        credential.check_status = PASSED if result.passed else FAILED
        credential.check_failure = None if result.failure is None else str(result.failure)
        credential.last_checked_at = self._clock.now()

    async def rotate(
        self, scope: OrganisationScope, credential_id: uuid.UUID, api_key: str
    ) -> ProviderCredential:
        """Replaces the secret, keeping the credential's ID. A failed check keeps the old one."""
        credential = await self.get(scope, credential_id, for_update=True)
        result = await self._verifier.check(Provider(credential.provider), api_key)
        if result.failure is not None:
            details = _summary(credential) | {"attempted_suffix": _suffix(api_key)}
            raise await self._check_failed(scope, credential.id, details, result.failure)
        before = {"masked_suffix": credential.masked_suffix}
        credential.secret_sealed = seal_secret(
            self._envelope, credential.organisation_id, credential.id, api_key
        )
        credential.masked_suffix = _suffix(api_key)
        credential.secret_set_at = self._clock.now()
        self._apply(credential, result)
        await self._record(
            scope,
            "credential.rotated",
            credential.id,
            before=before,
            after={"masked_suffix": credential.masked_suffix},
        )
        await self._session.commit()
        return credential

    async def delete(self, scope: OrganisationScope, credential_id: uuid.UUID) -> None:
        """Deletes the credential, unless something still references it."""
        credential = await self.get(scope, credential_id, for_update=True)
        references = await self._references.references_to(self._session, scope, credential.id)
        if references:
            raise CredentialInUseError(references)
        before = _summary(credential)
        await self._session.delete(credential)
        await self._record(scope, "credential.deleted", credential.id, before=before)
        await self._session.commit()
