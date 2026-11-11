"""The credential-verifier port: one check per provider, answering success or a typed reason.

API-key providers are checked with ``check``; Bedrock, which authenticates with an IAM role
or AWS access keys, with ``check_bedrock``.

Adapters: ``LiveCredentialVerifier`` makes a minimal live call to the provider (HTTP for the
API-key providers, STS then Bedrock for Bedrock); ``FakeCredentialVerifier`` (``docker
compose`` and tests) answers from the key, or the role's name, itself.
"""

import enum
from dataclasses import dataclass, field
from typing import Protocol

from fastapi import Request

from app.credentials.registry import Provider


class CheckFailure(enum.StrEnum):
    """Why a credential check failed, in terms an Owner can act on."""

    INVALID_KEY = "invalid_key"
    MISSING_MODEL_ACCESS = "missing_model_access"
    QUOTA_EXCEEDED = "quota_exceeded"
    PROVIDER_UNREACHABLE = "provider_unreachable"
    # Bedrock: the platform could not assume the Owner's IAM role.
    ROLE_NOT_ASSUMABLE = "role_not_assumable"
    # Bedrock: Bedrock, or the model, is not offered in the credential's region.
    WRONG_REGION = "wrong_region"


@dataclass(frozen=True)
class CheckResult:
    """``failure`` is None when the check passed."""

    failure: CheckFailure | None = None

    @property
    def passed(self) -> bool:
        return self.failure is None


PASSED = CheckResult()


@dataclass(frozen=True)
class BedrockAccess:
    """How to reach Bedrock for one credential: an IAM role (with the Organisation's external
    ID) or access keys, in a region, checked against ``model_id``."""

    region: str
    model_id: str
    role_arn: str | None = None
    external_id: str | None = None
    access_key_id: str | None = None
    secret_access_key: str | None = field(default=None, repr=False)

    @property
    def marker(self) -> str:
        """The part of the access the fake verifier reads its outcome from."""
        if self.role_arn is not None:
            return self.role_arn.rsplit("/", 1)[1]
        return self.secret_access_key or ""


class CredentialVerifier(Protocol):
    async def check(self, provider: Provider, api_key: str) -> CheckResult: ...

    async def check_bedrock(self, access: BedrockAccess) -> CheckResult: ...


FAKE_FAILURE_PREFIX = "fake-fail-"


def _fake_result(value: str, otherwise: CheckFailure) -> CheckResult:
    if not value.startswith(FAKE_FAILURE_PREFIX):
        return PASSED
    reason = value.removeprefix(FAKE_FAILURE_PREFIX)
    for failure in CheckFailure:
        if reason.startswith(failure.value):
            return CheckResult(failure)
    return CheckResult(otherwise)


class FakeCredentialVerifier:
    """Passes every key, except one starting ``fake-fail-<reason>``, which fails with that reason.

    For Bedrock it reads the role's name (``arn:aws:iam::…:role/fake-fail-<reason>``) or the
    secret access key. Tests and the ``docker compose`` stack choose the outcome through what
    they save.
    """

    async def check(self, provider: Provider, api_key: str) -> CheckResult:
        return _fake_result(api_key, CheckFailure.INVALID_KEY)

    async def check_bedrock(self, access: BedrockAccess) -> CheckResult:
        otherwise = CheckFailure.ROLE_NOT_ASSUMABLE if access.role_arn else CheckFailure.INVALID_KEY
        return _fake_result(access.marker, otherwise)


def get_verifier(request: Request) -> CredentialVerifier:
    verifier: CredentialVerifier = request.app.state.credential_verifier
    return verifier
