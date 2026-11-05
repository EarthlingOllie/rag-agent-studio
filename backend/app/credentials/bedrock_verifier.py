"""The live Bedrock verifier, and the cache of assumed-role sessions.

A role credential is checked in two steps:
1. the platform's own AWS identity assumes the Owner's role through STS, passing the
   Organisation's external ID;
2. with the assumed session, Bedrock's ``GetFoundationModelAvailability`` (no tokens, no cost)
   says whether the model is offered in the credential's region and whether the account may
   use it.

Access keys are checked the same way, with STS ``GetCallerIdentity`` as the first step.

Assumed-role sessions are cached per role and external ID, and reused until shortly before
they expire, so checks (and, later, model calls) don't assume the role every time. A cached
session is still a valid AWS session: changing a role's trust policy doesn't revoke sessions
already issued, so a check that reuses one reports what the platform can actually do.

boto3 is synchronous, so checks run in a worker thread.
"""

import asyncio
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, cast

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError, EndpointConnectionError

from app.core.clock import Clock
from app.credentials.verifier import PASSED, BedrockAccess, CheckFailure, CheckResult

SESSION_NAME = "rag-agent-studio"
SESSION_SECONDS = 60 * 60


@dataclass(frozen=True)
class AwsKeys:
    """AWS credentials: an IAM user's access keys, or an assumed-role session."""

    access_key_id: str
    secret_access_key: str = field(repr=False)
    session_token: str | None = field(default=None, repr=False)
    expires_at: datetime | None = None


# Builds a boto3 client for (service, region), signing with ``keys``, or with the platform's
# own identity when ``keys`` is None.
ClientFactory = Callable[[str, str, AwsKeys | None], Any]


def boto3_client(
    service: str, region: str, keys: AwsKeys | None, *, timeout_seconds: float = 10.0
) -> Any:
    """A boto3 client with short timeouts and no retries, so a check answers promptly."""
    config = Config(
        connect_timeout=timeout_seconds,
        read_timeout=timeout_seconds,
        retries={"total_max_attempts": 1},
    )
    signing: dict[str, Any] = {}
    if keys is not None:
        signing = {
            "aws_access_key_id": keys.access_key_id,
            "aws_secret_access_key": keys.secret_access_key,
            "aws_session_token": keys.session_token,
        }
    return boto3.client(service, region_name=region, config=config, **signing)  # type: ignore[call-overload]


class AssumedRoleSessions:
    """Assumes Owners' roles with the platform's STS client, caching each session until
    ``refresh_before`` its expiry."""

    def __init__(self, sts: Any, clock: Clock, *, refresh_before: timedelta) -> None:
        self.sts = sts
        self.refresh_before = refresh_before
        self._clock = clock
        self._cache: dict[tuple[str, str], AwsKeys] = {}
        self._lock = threading.Lock()

    def keys_for(self, role_arn: str, external_id: str) -> AwsKeys:
        """A session for the role, from the cache while it has long enough left to run.

        Raises botocore's ``ClientError`` when STS refuses, and ``BotoCoreError`` when STS
        can't be reached; neither is cached."""
        key = (role_arn, external_id)
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None and self._clock.now() < self._renew_at(cached):
                return cached
            answer = self.sts.assume_role(
                RoleArn=role_arn,
                RoleSessionName=SESSION_NAME,
                ExternalId=external_id,
                DurationSeconds=SESSION_SECONDS,
            )["Credentials"]
            keys = AwsKeys(
                answer["AccessKeyId"],
                answer["SecretAccessKey"],
                answer["SessionToken"],
                answer["Expiration"],
            )
            self._cache[key] = keys
            return keys

    def _renew_at(self, keys: AwsKeys) -> datetime:
        # Assumed-role sessions always carry their expiry.
        return cast(datetime, keys.expires_at) - self.refresh_before


_BEDROCK_ERRORS = {
    "AccessDeniedException": CheckFailure.MISSING_MODEL_ACCESS,
    "ResourceNotFoundException": CheckFailure.WRONG_REGION,
    "ValidationException": CheckFailure.WRONG_REGION,
    "ThrottlingException": CheckFailure.QUOTA_EXCEEDED,
    "UnrecognizedClientException": CheckFailure.INVALID_KEY,
}


def _code(error: ClientError) -> str:
    return str(error.response.get("Error", {}).get("Code", ""))


class BedrockVerifier:
    def __init__(
        self, sessions: AssumedRoleSessions, clients: ClientFactory, *, sts_region: str
    ) -> None:
        self.sessions = sessions
        self._clients = clients
        self._sts_region = sts_region

    async def check(self, access: BedrockAccess) -> CheckResult:
        return await asyncio.to_thread(self._check, access)

    def _check(self, access: BedrockAccess) -> CheckResult:
        keys = self._role_keys(access) if access.role_arn else self._access_keys(access)
        if isinstance(keys, CheckResult):
            return keys
        return self._model_access(access, keys)

    def _role_keys(self, access: BedrockAccess) -> AwsKeys | CheckResult:
        try:
            return self.sessions.keys_for(str(access.role_arn), str(access.external_id))
        except ClientError:
            return CheckResult(CheckFailure.ROLE_NOT_ASSUMABLE)
        except BotoCoreError:
            return CheckResult(CheckFailure.PROVIDER_UNREACHABLE)

    def _access_keys(self, access: BedrockAccess) -> AwsKeys | CheckResult:
        keys = AwsKeys(str(access.access_key_id), str(access.secret_access_key))
        try:
            self._clients("sts", self._sts_region, keys).get_caller_identity()
        except ClientError:
            return CheckResult(CheckFailure.INVALID_KEY)
        except BotoCoreError:
            return CheckResult(CheckFailure.PROVIDER_UNREACHABLE)
        return keys

    def _model_access(self, access: BedrockAccess, keys: AwsKeys) -> CheckResult:
        bedrock = self._clients("bedrock", access.region, keys)
        try:
            answer = bedrock.get_foundation_model_availability(modelId=access.model_id)
        except EndpointConnectionError:
            # The identity is fine (STS answered), but there is no Bedrock in this region.
            return CheckResult(CheckFailure.WRONG_REGION)
        except ClientError as error:
            return CheckResult(_BEDROCK_ERRORS.get(_code(error), CheckFailure.PROVIDER_UNREACHABLE))
        except BotoCoreError:
            return CheckResult(CheckFailure.PROVIDER_UNREACHABLE)
        if answer["regionAvailability"] != "AVAILABLE":
            return CheckResult(CheckFailure.WRONG_REGION)
        if (
            answer["authorizationStatus"] != "AUTHORIZED"
            or answer["entitlementAvailability"] != "AVAILABLE"
        ):
            return CheckResult(CheckFailure.MISSING_MODEL_ACCESS)
        return PASSED
