"""The live Bedrock verifier and the assumed-role session cache, with stubbed AWS clients.

No AWS account is used: STS and Bedrock clients are real boto3 clients wrapped in botocore's
``Stubber``, which checks each request against the service's API model and answers with the
response a test queues. Time comes from the controllable clock.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
import httpx
import pytest
from botocore.awsrequest import AWSResponse, HTTPHeaders
from botocore.config import Config
from botocore.exceptions import EndpointConnectionError
from botocore.stub import Stubber

from app.core.settings import Settings
from app.credentials.adapters import LiveCredentialVerifier, build_verifier
from app.credentials.bedrock_verifier import (
    AssumedRoleSessions,
    AwsKeys,
    BedrockVerifier,
    boto3_client,
)
from app.credentials.http_verifier import HttpCredentialVerifier
from app.credentials.registry import Provider
from app.credentials.verifier import PASSED, BedrockAccess, CheckFailure, CheckResult
from tests.fakes.clock import ControllableClock

ROLE_ARN = "arn:aws:iam::111122223333:role/StudioBedrockAccess"
EXTERNAL_ID = "k2Jd8wQm4Zr7Vt1Xy9Pb3Lc6Ns0Hf5Ga"
MODEL = "anthropic.claude-sonnet-4-5-20250929-v1:0"
START = datetime(2026, 11, 5, 9, 0, tzinfo=UTC)


def _client(service: str, region: str = "eu-west-2") -> Any:
    return boto3.client(  # type: ignore[call-overload]
        service,
        region_name=region,
        aws_access_key_id="testing",
        aws_secret_access_key="testing",  # noqa: S106
        config=Config(retries={"total_max_attempts": 1}),
    )


def _assumed(number: int, expires: datetime) -> dict[str, Any]:
    return {
        "Credentials": {
            "AccessKeyId": f"ASIATESTSESSION{number:05d}",
            "SecretAccessKey": f"session-secret-{number}",
            "SessionToken": f"session-token-{number}",
            "Expiration": expires,
        },
        "AssumedRoleUser": {
            "AssumedRoleId": "AROATESTROLEID:rag-agent-studio",
            "Arn": "arn:aws:sts::111122223333:assumed-role/StudioBedrockAccess/rag-agent-studio",
        },
    }


ASSUME_REQUEST = {
    "RoleArn": ROLE_ARN,
    "RoleSessionName": "rag-agent-studio",
    "ExternalId": EXTERNAL_ID,
    "DurationSeconds": 3600,
}


def _available(**overrides: Any) -> dict[str, Any]:
    return {
        "modelId": MODEL,
        "agreementAvailability": {"status": "AVAILABLE"},
        "authorizationStatus": "AUTHORIZED",
        "entitlementAvailability": "AVAILABLE",
        "regionAvailability": "AVAILABLE",
        **overrides,
    }


class _Clients:
    """A client factory that hands out stubbed clients and records what it was asked for."""

    def __init__(self) -> None:
        self.bedrock = _client("bedrock")
        self.sts = _client("sts", "us-east-1")
        self.made: list[tuple[str, str, AwsKeys | None]] = []

    def __call__(self, service: str, region: str, keys: AwsKeys | None) -> Any:
        self.made.append((service, region, keys))
        return self.bedrock if service == "bedrock" else self.sts


@pytest.fixture
def clock() -> ControllableClock:
    return ControllableClock(START)


@pytest.fixture
def platform_sts() -> Any:
    return _client("sts", "us-east-1")


@pytest.fixture
def sessions(platform_sts: Any, clock: ControllableClock) -> AssumedRoleSessions:
    return AssumedRoleSessions(platform_sts, clock, refresh_before=timedelta(minutes=5))


def _role(region: str = "eu-west-2") -> BedrockAccess:
    return BedrockAccess(region=region, model_id=MODEL, role_arn=ROLE_ARN, external_id=EXTERNAL_ID)


def _keys() -> BedrockAccess:
    return BedrockAccess(
        region="us-east-1",
        model_id=MODEL,
        access_key_id="AKIAIOSFODNN7EXAMPLE",
        secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",  # noqa: S106
    )


# Assumed-role sessions


def test_a_role_is_assumed_with_the_organisations_external_id(
    sessions: AssumedRoleSessions, platform_sts: Any
) -> None:
    with Stubber(platform_sts) as stub:
        stub.add_response("assume_role", _assumed(1, START + timedelta(hours=1)), ASSUME_REQUEST)

        keys = sessions.keys_for(ROLE_ARN, EXTERNAL_ID)

        stub.assert_no_pending_responses()
    assert keys == AwsKeys(
        "ASIATESTSESSION00001",
        "session-secret-1",
        "session-token-1",
        START + timedelta(hours=1),
    )
    assert "session-secret-1" not in repr(keys)


def test_a_session_is_reused_until_shortly_before_it_expires(
    sessions: AssumedRoleSessions, platform_sts: Any, clock: ControllableClock
) -> None:
    expires = START + timedelta(hours=1)
    with Stubber(platform_sts) as stub:
        stub.add_response("assume_role", _assumed(1, expires), ASSUME_REQUEST)
        first = sessions.keys_for(ROLE_ARN, EXTERNAL_ID)

        # 54m59s later: still more than five minutes left, so no new STS call.
        clock.advance(timedelta(minutes=54, seconds=59))
        assert sessions.keys_for(ROLE_ARN, EXTERNAL_ID) == first

        # Five minutes before expiry the session is renewed.
        clock.advance(timedelta(seconds=1))
        stub.add_response("assume_role", _assumed(2, expires + timedelta(hours=1)), ASSUME_REQUEST)
        renewed = sessions.keys_for(ROLE_ARN, EXTERNAL_ID)

        stub.assert_no_pending_responses()
    assert renewed.access_key_id == "ASIATESTSESSION00002"
    # And the renewed one is reused in turn.
    assert sessions.keys_for(ROLE_ARN, EXTERNAL_ID) == renewed


def test_sessions_are_cached_per_role_and_external_id(
    sessions: AssumedRoleSessions, platform_sts: Any
) -> None:
    other_role = "arn:aws:iam::444455556666:role/OtherCustomer"
    expires = START + timedelta(hours=1)
    with Stubber(platform_sts) as stub:
        stub.add_response("assume_role", _assumed(1, expires), ASSUME_REQUEST)
        stub.add_response(
            "assume_role", _assumed(2, expires), {**ASSUME_REQUEST, "RoleArn": other_role}
        )
        stub.add_response(
            "assume_role", _assumed(3, expires), {**ASSUME_REQUEST, "ExternalId": "another-id-0001"}
        )

        mine = sessions.keys_for(ROLE_ARN, EXTERNAL_ID)
        theirs = sessions.keys_for(other_role, EXTERNAL_ID)
        other_org = sessions.keys_for(ROLE_ARN, "another-id-0001")

        stub.assert_no_pending_responses()
    assert [k.access_key_id[-1] for k in (mine, theirs, other_org)] == ["1", "2", "3"]


def test_a_refused_assumption_is_not_cached(
    sessions: AssumedRoleSessions, platform_sts: Any
) -> None:
    with Stubber(platform_sts) as stub:
        stub.add_client_error("assume_role", "AccessDenied", http_status_code=403)
        stub.add_response("assume_role", _assumed(1, START + timedelta(hours=1)), ASSUME_REQUEST)

        with pytest.raises(Exception, match="AccessDenied"):
            sessions.keys_for(ROLE_ARN, EXTERNAL_ID)
        keys = sessions.keys_for(ROLE_ARN, EXTERNAL_ID)

        stub.assert_no_pending_responses()
    assert keys.access_key_id == "ASIATESTSESSION00001"


# The verifier: role assumption, then model access


async def test_a_role_check_assumes_the_role_then_checks_model_access_in_the_region(
    sessions: AssumedRoleSessions, platform_sts: Any
) -> None:
    clients = _Clients()
    verifier = BedrockVerifier(sessions, clients, sts_region="us-east-1")
    with Stubber(platform_sts) as sts, Stubber(clients.bedrock) as bedrock:
        sts.add_response("assume_role", _assumed(1, START + timedelta(hours=1)), ASSUME_REQUEST)
        bedrock.add_response("get_foundation_model_availability", _available(), {"modelId": MODEL})

        result = await verifier.check(_role())

        sts.assert_no_pending_responses()
        bedrock.assert_no_pending_responses()
    assert result == PASSED
    # Bedrock is reached in the credential's region with the assumed session's keys.
    ((service, region, keys),) = clients.made
    assert (service, region) == ("bedrock", "eu-west-2")
    assert keys is not None
    assert keys.session_token == "session-token-1"


async def test_checking_a_role_again_reuses_its_cached_session(
    sessions: AssumedRoleSessions, platform_sts: Any
) -> None:
    clients = _Clients()
    verifier = BedrockVerifier(sessions, clients, sts_region="us-east-1")
    with Stubber(platform_sts) as sts, Stubber(clients.bedrock) as bedrock:
        sts.add_response("assume_role", _assumed(1, START + timedelta(hours=1)), ASSUME_REQUEST)
        for _ in range(2):
            bedrock.add_response(
                "get_foundation_model_availability", _available(), {"modelId": MODEL}
            )

        assert await verifier.check(_role()) == PASSED
        assert await verifier.check(_role()) == PASSED

        sts.assert_no_pending_responses()
        bedrock.assert_no_pending_responses()


@pytest.mark.parametrize(
    "code", ["AccessDenied", "InvalidParameterValue", "RegionDisabledException"]
)
async def test_a_role_that_cannot_be_assumed_says_so(
    code: str, sessions: AssumedRoleSessions, platform_sts: Any
) -> None:
    clients = _Clients()
    verifier = BedrockVerifier(sessions, clients, sts_region="us-east-1")
    with Stubber(platform_sts) as sts:
        sts.add_client_error("assume_role", code, http_status_code=403)

        result = await verifier.check(_role())

    assert result == CheckResult(CheckFailure.ROLE_NOT_ASSUMABLE)
    # Bedrock was never called.
    assert clients.made == []


async def test_sts_being_unreachable_is_not_blamed_on_the_role(
    clock: ControllableClock,
) -> None:
    sts = _client("sts", "us-east-1")
    sts.meta.events.register("before-send.sts.AssumeRole", _unreachable)
    verifier = BedrockVerifier(
        AssumedRoleSessions(sts, clock, refresh_before=timedelta(minutes=5)),
        _Clients(),
        sts_region="us-east-1",
    )

    assert await verifier.check(_role()) == CheckResult(CheckFailure.PROVIDER_UNREACHABLE)


def _unreachable(**_: Any) -> None:
    raise EndpointConnectionError(endpoint_url="https://sts.amazonaws.com")


@pytest.mark.parametrize(
    ("answer", "failure"),
    [
        (_available(authorizationStatus="NOT_AUTHORIZED"), CheckFailure.MISSING_MODEL_ACCESS),
        (_available(entitlementAvailability="NOT_AVAILABLE"), CheckFailure.MISSING_MODEL_ACCESS),
        (_available(regionAvailability="NOT_AVAILABLE"), CheckFailure.WRONG_REGION),
        (
            _available(regionAvailability="NOT_AVAILABLE", authorizationStatus="NOT_AUTHORIZED"),
            CheckFailure.WRONG_REGION,
        ),
    ],
)
async def test_model_availability_gives_the_reason(
    answer: dict[str, Any],
    failure: CheckFailure,
    sessions: AssumedRoleSessions,
    platform_sts: Any,
) -> None:
    clients = _Clients()
    verifier = BedrockVerifier(sessions, clients, sts_region="us-east-1")
    with Stubber(platform_sts) as sts, Stubber(clients.bedrock) as bedrock:
        sts.add_response("assume_role", _assumed(1, START + timedelta(hours=1)), ASSUME_REQUEST)
        bedrock.add_response("get_foundation_model_availability", answer, {"modelId": MODEL})

        assert await verifier.check(_role()) == CheckResult(failure)


@pytest.mark.parametrize(
    ("code", "failure"),
    [
        ("AccessDeniedException", CheckFailure.MISSING_MODEL_ACCESS),
        ("ResourceNotFoundException", CheckFailure.WRONG_REGION),
        ("ValidationException", CheckFailure.WRONG_REGION),
        ("ThrottlingException", CheckFailure.QUOTA_EXCEEDED),
        ("UnrecognizedClientException", CheckFailure.INVALID_KEY),
        ("InternalServerException", CheckFailure.PROVIDER_UNREACHABLE),
    ],
)
async def test_bedrock_errors_give_the_reason(
    code: str, failure: CheckFailure, sessions: AssumedRoleSessions, platform_sts: Any
) -> None:
    clients = _Clients()
    verifier = BedrockVerifier(sessions, clients, sts_region="us-east-1")
    with Stubber(platform_sts) as sts, Stubber(clients.bedrock) as bedrock:
        sts.add_response("assume_role", _assumed(1, START + timedelta(hours=1)), ASSUME_REQUEST)
        bedrock.add_client_error("get_foundation_model_availability", code, http_status_code=400)

        assert await verifier.check(_role()) == CheckResult(failure)


async def test_a_region_without_a_bedrock_endpoint_is_the_wrong_region(
    sessions: AssumedRoleSessions, platform_sts: Any
) -> None:
    clients = _Clients()
    clients.bedrock = _client("bedrock", "eu-moon-1")
    clients.bedrock.meta.events.register(
        "before-send.bedrock.GetFoundationModelAvailability", _unreachable
    )
    verifier = BedrockVerifier(sessions, clients, sts_region="us-east-1")
    with Stubber(platform_sts) as sts:
        sts.add_response("assume_role", _assumed(1, START + timedelta(hours=1)), ASSUME_REQUEST)

        assert await verifier.check(_role("eu-moon-1")) == CheckResult(CheckFailure.WRONG_REGION)


async def test_other_bedrock_client_failures_mean_aws_was_unreachable(
    sessions: AssumedRoleSessions, platform_sts: Any
) -> None:
    clients = _Clients()
    clients.bedrock.meta.events.register(
        "before-send.bedrock.GetFoundationModelAvailability", _read_timeout
    )
    verifier = BedrockVerifier(sessions, clients, sts_region="us-east-1")
    with Stubber(platform_sts) as sts:
        sts.add_response("assume_role", _assumed(1, START + timedelta(hours=1)), ASSUME_REQUEST)

        result = await verifier.check(_role())

    assert result == CheckResult(CheckFailure.PROVIDER_UNREACHABLE)


def _read_timeout(**_: Any) -> None:
    from botocore.exceptions import ReadTimeoutError

    raise ReadTimeoutError(endpoint_url="https://bedrock.eu-west-2.amazonaws.com")


# The verifier: access keys


async def test_access_keys_are_checked_with_sts_then_model_access(
    sessions: AssumedRoleSessions, platform_sts: Any
) -> None:
    clients = _Clients()
    verifier = BedrockVerifier(sessions, clients, sts_region="us-east-1")
    with Stubber(clients.sts) as sts, Stubber(clients.bedrock) as bedrock:
        sts.add_response(
            "get_caller_identity",
            {"UserId": "AIDATEST", "Account": "111122223333", "Arn": "arn:aws:iam::1:user/x"},
            {},
        )
        bedrock.add_response("get_foundation_model_availability", _available(), {"modelId": MODEL})

        assert await verifier.check(_keys()) == PASSED

    keys = AwsKeys("AKIAIOSFODNN7EXAMPLE", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY")
    assert clients.made == [("sts", "us-east-1", keys), ("bedrock", "us-east-1", keys)]


@pytest.mark.parametrize("code", ["InvalidClientTokenId", "SignatureDoesNotMatch", "AccessDenied"])
async def test_rejected_access_keys_are_an_invalid_key(
    code: str, sessions: AssumedRoleSessions
) -> None:
    clients = _Clients()
    verifier = BedrockVerifier(sessions, clients, sts_region="us-east-1")
    with Stubber(clients.sts) as sts:
        sts.add_client_error("get_caller_identity", code, http_status_code=403)

        assert await verifier.check(_keys()) == CheckResult(CheckFailure.INVALID_KEY)
    assert [service for service, _, _ in clients.made] == ["sts"]


async def test_sts_unreachable_while_checking_access_keys(
    sessions: AssumedRoleSessions,
) -> None:
    clients = _Clients()
    clients.sts.meta.events.register("before-send.sts.GetCallerIdentity", _unreachable)
    verifier = BedrockVerifier(sessions, clients, sts_region="us-east-1")

    assert await verifier.check(_keys()) == CheckResult(CheckFailure.PROVIDER_UNREACHABLE)


# Building real clients


def _capture(seen: list[dict[str, str]]) -> Any:
    def handler(request: Any, **_: Any) -> AWSResponse:
        headers = {k: v.decode() if isinstance(v, bytes) else v for k, v in request.headers.items()}
        seen.append(headers | {"url": request.url})
        body = (
            b"<GetCallerIdentityResponse><GetCallerIdentityResult><UserId>u</UserId>"
            b"<Account>111122223333</Account><Arn>arn:aws:iam::111122223333:user/u</Arn>"
            b"</GetCallerIdentityResult></GetCallerIdentityResponse>"
        )
        return AWSResponse(request.url, 200, HTTPHeaders(), _Raw(body))

    return handler


class _Raw:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def stream(self, **_: Any) -> Any:
        yield self._body


def test_clients_are_built_for_the_region_with_the_given_keys() -> None:
    keys = AwsKeys("ASIAEXAMPLESESSION09", "session-secret-9", "session-token-9")
    client = boto3_client("sts", "eu-west-2", keys, timeout_seconds=7)
    seen: list[dict[str, str]] = []
    client.meta.events.register("before-send.sts.GetCallerIdentity", _capture(seen))

    client.get_caller_identity()

    (headers,) = seen
    assert headers["url"] == "https://sts.eu-west-2.amazonaws.com/"
    assert "Credential=ASIAEXAMPLESESSION09/" in headers["Authorization"]
    assert headers["X-Amz-Security-Token"] == "session-token-9"
    assert client.meta.config.connect_timeout == 7
    assert client.meta.config.read_timeout == 7
    assert client.meta.config.retries["total_max_attempts"] == 1


def test_the_platform_client_uses_the_platform_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAEXAMPLEPLATFORM1")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "platform-secret")
    # boto3 resolves its default session's credentials once; start from a fresh one.
    monkeypatch.setattr(boto3, "DEFAULT_SESSION", None)
    client = boto3_client("sts", "us-east-1", None, timeout_seconds=3)
    seen: list[dict[str, str]] = []
    client.meta.events.register("before-send.sts.GetCallerIdentity", _capture(seen))

    client.get_caller_identity()

    assert "Credential=AKIAEXAMPLEPLATFORM1/" in seen[0]["Authorization"]


async def test_the_live_verifier_sends_bedrock_to_sts_and_the_rest_over_http(
    settings_env: pytest.MonkeyPatch,
) -> None:
    settings_env.setenv("CREDENTIAL_VERIFIER", "live")
    settings_env.setenv("BEDROCK_STS_REGION", "eu-central-1")
    settings_env.setenv("BEDROCK_SESSION_REFRESH_SECONDS", "120")
    settings = Settings()

    verifier = build_verifier(settings, httpx.AsyncClient(), ControllableClock(START))

    assert isinstance(verifier, LiveCredentialVerifier)
    assert isinstance(verifier.api_keys, HttpCredentialVerifier)
    assert verifier.bedrock.sessions.refresh_before == timedelta(seconds=120)
    assert verifier.bedrock.sessions.sts.meta.region_name == "eu-central-1"


class _Answers:
    def __init__(self, answer: CheckResult) -> None:
        self.answer = answer
        self.asked: list[object] = []

    async def check(self, *args: object) -> CheckResult:
        self.asked.append(args)
        return self.answer


async def test_the_live_verifier_routes_each_check() -> None:
    api_keys, bedrock = _Answers(PASSED), _Answers(CheckResult(CheckFailure.WRONG_REGION))
    verifier = LiveCredentialVerifier(api_keys, bedrock)  # type: ignore[arg-type]

    assert await verifier.check(Provider.OPENAI, "sk-test-key-0000") == PASSED
    assert await verifier.check_bedrock(_role()) == CheckResult(CheckFailure.WRONG_REGION)
    assert api_keys.asked == [(Provider.OPENAI, "sk-test-key-0000")]
    assert bedrock.asked == [(_role(),)]
