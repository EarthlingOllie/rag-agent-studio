"""Provider Credential operations: list, add, re-check, rotate and delete.

Every secret is checked with the credential verifier before it is stored, sealed with the
envelope-encryption module, and never returned: callers see only the masked suffix. Each
change is recorded as an Audit Event in the same transaction, without the secret.

Bedrock credentials are either an IAM role in the Owner's AWS account, which the platform
assumes with the Organisation's external ID (no secret is stored), or AWS access keys.
"""

import json
import secrets
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import AuditTarget, record
from app.core.clock import Clock
from app.credentials.models import AwsExternalId, ProviderCredential
from app.credentials.references import CredentialReference, ReferenceRegistry
from app.credentials.registry import PROVIDERS, AuthKind, Capability, Provider
from app.credentials.verifier import BedrockAccess, CheckFailure, CheckResult, CredentialVerifier
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


class NotRotatableError(Exception):
    """Only API-key credentials are rotated with a new key."""


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
    """The credential's secret in plain text. Only the model gateway and checks need it, and
    only for credentials with a secret: a Bedrock IAM role has none."""
    context = _context(credential.organisation_id, credential.id)
    sealed = cast(bytes, credential.secret_sealed)
    return envelope.open(sealed, context=context).decode()


def _suffix(secret: str) -> str:
    return secret[-SUFFIX_LENGTH:]


def _summary(credential: ProviderCredential) -> dict[str, Any]:
    summary = {
        "name": credential.name,
        "provider": credential.provider,
        "auth_kind": credential.auth_kind,
        "capabilities": list(credential.capabilities),
        "masked_suffix": credential.masked_suffix,
    }
    if credential.provider == Provider.BEDROCK:
        summary |= {"role_arn": credential.role_arn, "region": credential.region}
    return summary


def _check_model(capabilities: Sequence[Capability]) -> str:
    """The Bedrock model whose access is checked: the first of the first capability's."""
    return PROVIDERS[Provider.BEDROCK].models[capabilities[0]][0].id


def _target(credential_id: uuid.UUID | None) -> AuditTarget:
    return AuditTarget("provider_credential", credential_id)


@dataclass(frozen=True)
class NewCredential:
    name: str
    provider: Provider
    api_key: str
    capabilities: Sequence[Capability] | None = None


@dataclass(frozen=True)
class NewBedrockCredential:
    """A Bedrock credential: ``role_arn``, or ``access_key_id`` and ``secret_access_key``."""

    name: str
    region: str
    role_arn: str | None = None
    access_key_id: str | None = None
    secret_access_key: str | None = None
    capabilities: Sequence[Capability] | None = None

    @property
    def auth_kind(self) -> AuthKind:
        return AuthKind.AWS_ROLE if self.role_arn is not None else AuthKind.AWS_ACCESS_KEYS


EXTERNAL_ID_BYTES = 24


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

    async def _capabilities(
        self,
        scope: OrganisationScope,
        provider: Provider,
        name: str,
        chosen: Sequence[Capability] | None,
    ) -> tuple[Capability, ...]:
        """The capabilities to store, in the registry's order, once the name is known free."""
        spec = PROVIDERS[provider]
        capabilities = list(spec.capabilities if chosen is None else chosen)
        unsupported = [c for c in capabilities if c not in spec.capabilities]
        if unsupported:
            raise UnsupportedCapabilityError(provider, unsupported)
        if await self._name_taken(scope, name):
            raise DuplicateNameError
        return tuple(c for c in spec.capabilities if c in capabilities)

    async def create(self, scope: OrganisationScope, new: NewCredential) -> ProviderCredential:
        """Checks the key, then stores the credential. A failed check stores nothing."""
        capabilities = await self._capabilities(scope, new.provider, new.name, new.capabilities)
        result = await self._verifier.check(new.provider, new.api_key)
        if result.failure is not None:
            # Nothing of the rejected key is recorded, not even its last characters.
            details = {"name": new.name, "provider": new.provider}
            raise await self._check_failed(scope, None, details, result.failure)
        credential = ProviderCredential(
            name=new.name,
            provider=new.provider,
            auth_kind=AuthKind.API_KEY,
            masked_suffix=_suffix(new.api_key),
        )
        return await self._store(scope, credential, capabilities, new.api_key)

    async def create_bedrock(
        self, scope: OrganisationScope, new: NewBedrockCredential
    ) -> ProviderCredential:
        """Checks role assumption (or the access keys), then model access, then stores the
        credential. A failed check stores nothing."""
        capabilities = await self._capabilities(scope, Provider.BEDROCK, new.name, new.capabilities)
        if new.role_arn is not None:
            access = BedrockAccess(
                region=new.region,
                model_id=_check_model(capabilities),
                role_arn=new.role_arn,
                external_id=await self._external_id(scope),
            )
            secret, suffix = None, None
            shown: dict[str, Any] = {"role_arn": new.role_arn}
        else:
            access = BedrockAccess(
                region=new.region,
                model_id=_check_model(capabilities),
                access_key_id=new.access_key_id,
                secret_access_key=new.secret_access_key,
            )
            secret = json.dumps(
                {"access_key_id": new.access_key_id, "secret_access_key": new.secret_access_key}
            )
            # The end of the access key ID, which the Owner can match in the IAM console.
            suffix = _suffix(str(new.access_key_id))
            shown = {"masked_suffix": suffix}
        result = await self._verifier.check_bedrock(access)
        if result.failure is not None:
            details = {
                "name": new.name,
                "provider": Provider.BEDROCK,
                "auth_kind": new.auth_kind,
                **shown,
                "region": new.region,
            }
            raise await self._check_failed(scope, None, details, result.failure)
        credential = ProviderCredential(
            name=new.name,
            provider=Provider.BEDROCK,
            auth_kind=new.auth_kind,
            masked_suffix=suffix,
            region=new.region,
            role_arn=new.role_arn,
        )
        return await self._store(scope, credential, capabilities, secret)

    async def _store(
        self,
        scope: OrganisationScope,
        credential: ProviderCredential,
        capabilities: Sequence[Capability],
        secret: str | None,
    ) -> ProviderCredential:
        """Seals the secret (if any) and stores a credential that has just passed its check."""
        now = self._clock.now()
        credential_id = uuid.uuid4()
        credential.id = credential_id
        credential.organisation_id = scope.organisation_id
        credential.secret_sealed = (
            None
            if secret is None
            else seal_secret(self._envelope, scope.organisation_id, credential_id, secret)
        )
        credential.capabilities = [str(c) for c in capabilities]
        credential.check_status = PASSED
        credential.check_failure = None
        credential.last_checked_at = now
        credential.secret_set_at = now
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

    async def bedrock_external_id(self, scope: OrganisationScope) -> str:
        """The Organisation's external ID for Bedrock role trust policies."""
        external_id = await self._external_id(scope)
        await self._session.commit()
        return external_id

    async def _external_id(self, scope: OrganisationScope) -> str:
        """The Organisation's external ID, generated the first time it is asked for. Concurrent
        first requests agree on one: the losing insert does nothing."""
        await self._session.execute(
            insert(AwsExternalId)
            .values(
                organisation_id=scope.organisation_id,
                external_id=secrets.token_urlsafe(EXTERNAL_ID_BYTES),
                created_at=self._clock.now(),
            )
            .on_conflict_do_nothing(index_elements=["organisation_id"])
        )
        external_id = await self._session.scalar(
            select(AwsExternalId.external_id).where(
                AwsExternalId.organisation_id == scope.organisation_id
            )
        )
        return str(external_id)

    async def _verify_stored(
        self, scope: OrganisationScope, credential: ProviderCredential
    ) -> CheckResult:
        """Checks a stored credential again, however it authenticates."""
        if credential.auth_kind == AuthKind.API_KEY:
            return await self._verifier.check(
                Provider(credential.provider), open_secret(self._envelope, credential)
            )
        capabilities = [Capability(c) for c in credential.capabilities]
        region = str(credential.region)
        if credential.auth_kind == AuthKind.AWS_ROLE:
            access = BedrockAccess(
                region=region,
                model_id=_check_model(capabilities),
                role_arn=credential.role_arn,
                external_id=await self._external_id(scope),
            )
        else:
            keys = json.loads(open_secret(self._envelope, credential))
            access = BedrockAccess(
                region=region,
                model_id=_check_model(capabilities),
                access_key_id=keys["access_key_id"],
                secret_access_key=keys["secret_access_key"],
            )
        return await self._verifier.check_bedrock(access)

    async def recheck(
        self, scope: OrganisationScope, credential_id: uuid.UUID
    ) -> ProviderCredential:
        """Checks the stored secret again and records the outcome on the credential."""
        credential = await self.get(scope, credential_id, for_update=True)
        result = await self._verify_stored(scope, credential)
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
        if credential.auth_kind != AuthKind.API_KEY:
            raise NotRotatableError
        result = await self._verifier.check(Provider(credential.provider), api_key)
        if result.failure is not None:
            # The summary shows the old (accepted) key's suffix, never the rejected key's.
            details = _summary(credential)
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
