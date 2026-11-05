"""The credential-verifier port: one check per provider, answering success or a typed reason.

Adapters: ``HttpCredentialVerifier`` makes a minimal live call to the provider;
``FakeCredentialVerifier`` (``docker compose`` and tests) answers from the key itself.
"""

import enum
from dataclasses import dataclass
from typing import Protocol

from fastapi import Request

from app.credentials.registry import Provider


class CheckFailure(enum.StrEnum):
    """Why a credential check failed, in terms an Owner can act on."""

    INVALID_KEY = "invalid_key"
    MISSING_MODEL_ACCESS = "missing_model_access"
    QUOTA_EXCEEDED = "quota_exceeded"
    PROVIDER_UNREACHABLE = "provider_unreachable"


@dataclass(frozen=True)
class CheckResult:
    """``failure`` is None when the check passed."""

    failure: CheckFailure | None = None

    @property
    def passed(self) -> bool:
        return self.failure is None


PASSED = CheckResult()


class CredentialVerifier(Protocol):
    async def check(self, provider: Provider, api_key: str) -> CheckResult: ...


FAKE_FAILURE_PREFIX = "fake-fail-"


class FakeCredentialVerifier:
    """Passes every key, except one starting ``fake-fail-<reason>``, which fails with that reason.

    Tests and the ``docker compose`` stack choose the outcome through the key they save.
    """

    async def check(self, provider: Provider, api_key: str) -> CheckResult:
        if not api_key.startswith(FAKE_FAILURE_PREFIX):
            return PASSED
        reason = api_key.removeprefix(FAKE_FAILURE_PREFIX)
        for failure in CheckFailure:
            if reason.startswith(failure.value):
                return CheckResult(failure)
        return CheckResult(CheckFailure.INVALID_KEY)


def get_verifier(request: Request) -> CredentialVerifier:
    verifier: CredentialVerifier = request.app.state.credential_verifier
    return verifier
