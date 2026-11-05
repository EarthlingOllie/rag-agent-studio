"""API seam: Owners connect Amazon Bedrock with a cross-account IAM role or with access keys.

The credential verifier is the fake one (``CREDENTIAL_VERIFIER=fake``). For Bedrock it passes
unless the role's name, or the secret access key, starts ``fake-fail-<reason>``. Tests that
need to see what the verifier was asked put a recording verifier on ``app.state``.
Everything is observed through the API, including Audit Events.
"""

import json
import re
import uuid
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.credentials.registry import Capability, Provider
from app.credentials.verifier import (
    PASSED,
    BedrockAccess,
    CheckFailure,
    CheckResult,
)
from tests.conftest import MemberFactory, SignedUpMember, TenantFactory
from tests.fakes.clock import ControllableClock

ROLE_ARN = "arn:aws:iam::111122223333:role/StudioBedrockAccess"
ACCESS_KEY_ID = "AKIAIOSFODNN7EXAMPLE"
SECRET_ACCESS_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
PLATFORM_PRINCIPAL = "arn:aws:iam::000000000000:role/rag-agent-studio-local"


def path(organisation_id: str, *rest: str) -> str:
    return "/".join([f"/api/organisations/{organisation_id}", *rest])


async def setup_of(owner: SignedUpMember) -> dict[str, Any]:
    response = await owner.client.get(path(owner.organisation_id, "bedrock-setup"))
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def add_role(
    owner: SignedUpMember,
    *,
    role_arn: str = ROLE_ARN,
    region: str = "eu-west-2",
    name: str | None = None,
    **extra: Any,
) -> httpx.Response:
    body = {
        "name": name or f"Bedrock {uuid.uuid4().hex[:8]}",
        "auth_kind": "aws_role",
        "role_arn": role_arn,
        "region": region,
        **extra,
    }
    return await owner.client.post(path(owner.organisation_id, "credentials", "bedrock"), json=body)


async def add_keys(
    owner: SignedUpMember,
    *,
    access_key_id: str = ACCESS_KEY_ID,
    secret_access_key: str = SECRET_ACCESS_KEY,
    region: str = "us-east-1",
    name: str | None = None,
    **extra: Any,
) -> httpx.Response:
    body = {
        "name": name or f"Bedrock keys {uuid.uuid4().hex[:8]}",
        "auth_kind": "aws_access_keys",
        "access_key_id": access_key_id,
        "secret_access_key": secret_access_key,
        "region": region,
        **extra,
    }
    return await owner.client.post(path(owner.organisation_id, "credentials", "bedrock"), json=body)


def created(response: httpx.Response) -> dict[str, Any]:
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def audit_events(owner: SignedUpMember, action: str) -> list[dict[str, Any]]:
    response = await owner.client.get(
        path(owner.organisation_id, "audit-events"), params={"action": action}
    )
    assert response.status_code == 200, response.text
    items: list[dict[str, Any]] = response.json()["items"]
    return items


class _Recording:
    """A verifier that records each Bedrock check and answers with ``result``."""

    def __init__(self, result: CheckResult = PASSED) -> None:
        self.result = result
        self.bedrock: list[BedrockAccess] = []

    async def check(self, provider: Provider, api_key: str) -> CheckResult:
        raise AssertionError("A Bedrock credential is never checked as an API key")

    async def check_bedrock(self, access: BedrockAccess) -> CheckResult:
        self.bedrock.append(access)
        return self.result


# The setup helper: the external ID and what to paste into AWS


async def test_the_studio_shows_the_external_id_and_the_trust_policy_to_paste(
    owner: SignedUpMember,
) -> None:
    setup = await setup_of(owner)

    external_id = setup["external_id"]
    assert re.fullmatch(r"[A-Za-z0-9_-]{32,}", external_id)
    assert setup["platform_principal"] == PLATFORM_PRINCIPAL
    assert json.loads(setup["trust_policy"]) == {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"AWS": PLATFORM_PRINCIPAL},
                "Action": "sts:AssumeRole",
                "Condition": {"StringEquals": {"sts:ExternalId": external_id}},
            }
        ],
    }
    # Pretty-printed, ready to paste.
    assert setup["trust_policy"].startswith('{\n  "Version": "2012-10-17"')
    permissions = json.loads(setup["permissions_policy"])
    (statement,) = permissions["Statement"]
    assert statement["Effect"] == "Allow"
    assert statement["Resource"] == "*"
    assert set(statement["Action"]) == {
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream",
        "bedrock:GetFoundationModelAvailability",
    }


async def test_the_external_id_is_stable_for_an_organisation_and_differs_between_them(
    owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    other = await tenant_factory()

    first = (await setup_of(owner))["external_id"]
    again = (await setup_of(owner))["external_id"]
    theirs = (await setup_of(other))["external_id"]

    assert first == again
    assert theirs != first


async def test_the_platform_principal_comes_from_settings(
    settings_env: pytest.MonkeyPatch, tenant_factory: TenantFactory, app: FastAPI
) -> None:
    app.state.settings = app.state.settings.model_copy(
        update={"bedrock_platform_principal": "arn:aws:iam::999988887777:role/studio-api-task"}
    )
    owner = await tenant_factory()

    setup = await setup_of(owner)

    assert setup["platform_principal"] == "arn:aws:iam::999988887777:role/studio-api-task"
    policy = json.loads(setup["trust_policy"])
    assert policy["Statement"][0]["Principal"] == {
        "AWS": "arn:aws:iam::999988887777:role/studio-api-task"
    }


async def test_editors_cannot_see_the_bedrock_setup(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")

    response = await editor.client.get(path(owner.organisation_id, "bedrock-setup"))

    assert response.status_code == 403


# Adding a role-based credential


async def test_an_owner_adds_a_bedrock_credential_with_a_role(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock
) -> None:
    verifier = _Recording()
    app.state.credential_verifier = verifier
    external_id = (await setup_of(owner))["external_id"]

    credential = created(await add_role(owner, name="Bedrock (role)", region="eu-west-2"))

    assert credential == {
        "id": credential["id"],
        "name": "Bedrock (role)",
        "provider": "bedrock",
        "auth_kind": "aws_role",
        "masked_suffix": None,
        "role_arn": ROLE_ARN,
        "region": "eu-west-2",
        "capabilities": ["chat", "embeddings", "rerank"],
        "check_status": "passed",
        "check_failure": None,
        "last_checked_at": "2026-11-05T09:00:00Z",
        "created_at": credential["created_at"],
    }
    (access,) = verifier.bedrock
    assert access.role_arn == ROLE_ARN
    assert access.external_id == external_id
    assert access.region == "eu-west-2"
    assert access.access_key_id is None
    assert access.secret_access_key is None
    # Model access is checked on a model of the credential's first capability.
    assert access.model_id == "anthropic.claude-sonnet-4-5-20250929-v1:0"
    (event,) = await audit_events(owner, "credential.created")
    assert event["target"] == {"type": "provider_credential", "id": credential["id"]}
    assert event["after"] == {
        "name": "Bedrock (role)",
        "provider": "bedrock",
        "auth_kind": "aws_role",
        "capabilities": ["chat", "embeddings", "rerank"],
        "masked_suffix": None,
        "role_arn": ROLE_ARN,
        "region": "eu-west-2",
    }


async def test_model_access_is_checked_on_a_model_the_credential_will_be_used_for(
    app: FastAPI, owner: SignedUpMember
) -> None:
    verifier = _Recording()
    app.state.credential_verifier = verifier

    created(await add_role(owner, capabilities=["embeddings"]))
    created(await add_role(owner, capabilities=["rerank", "embeddings"]))

    assert [a.model_id for a in verifier.bedrock] == [
        "amazon.titan-embed-text-v2:0",
        "amazon.titan-embed-text-v2:0",
    ]


@pytest.mark.parametrize(
    ("role_arn", "reason", "message"),
    [
        (
            "arn:aws:iam::111122223333:role/fake-fail-role_not_assumable",
            "role_not_assumable",
            "We couldn't assume this role. Check the role ARN, and that the role's trust policy "
            "is exactly the one shown, with your external ID.",
        ),
        (
            "arn:aws:iam::111122223333:role/fake-fail-missing_model_access",
            "missing_model_access",
            "The role works, but it can't use the model. Enable model access in the Bedrock "
            "console for this region, and check the role's permissions policy.",
        ),
        (
            "arn:aws:iam::111122223333:role/fake-fail-wrong_region",
            "wrong_region",
            "Bedrock, or this model, isn't available in that region. Choose the region where "
            "you enabled model access.",
        ),
    ],
)
async def test_a_failed_role_check_gives_a_clear_reason_and_stores_nothing(
    role_arn: str, reason: str, message: str, owner: SignedUpMember
) -> None:
    response = await add_role(owner, role_arn=role_arn, name="Failing")

    assert response.status_code == 400
    assert response.json() == {"detail": message, "reason": reason}
    listing = await owner.client.get(path(owner.organisation_id, "credentials"))
    assert listing.json() == []
    (event,) = await audit_events(owner, "credential.check_failed")
    assert event["target"] == {"type": "provider_credential", "id": None}
    assert event["after"] == {
        "name": "Failing",
        "provider": "bedrock",
        "auth_kind": "aws_role",
        "role_arn": role_arn,
        "region": "eu-west-2",
        "reason": reason,
    }


@pytest.mark.parametrize(
    "role_arn",
    [
        "StudioBedrockAccess",
        "arn:aws:iam::1111:role/Short",
        "arn:aws:iam::111122223333:user/NotARole",
        "arn:aws:s3:::bucket",
        "arn:aws:iam::111122223333:role/has space",
    ],
)
async def test_a_malformed_role_arn_is_refused_before_any_check(
    app: FastAPI, role_arn: str, owner: SignedUpMember
) -> None:
    verifier = _Recording()
    app.state.credential_verifier = verifier

    response = await add_role(owner, role_arn=role_arn)

    assert response.status_code == 422
    assert verifier.bedrock == []


async def test_role_arns_in_other_aws_partitions_and_paths_are_accepted(
    owner: SignedUpMember,
) -> None:
    china = created(await add_role(owner, role_arn="arn:aws-cn:iam::111122223333:role/a/b/Role"))

    assert china["role_arn"] == "arn:aws-cn:iam::111122223333:role/a/b/Role"


@pytest.mark.parametrize("region", ["", "europe", "EU-WEST-2", "eu-west", "eu_west_2"])
async def test_a_malformed_region_is_refused(region: str, owner: SignedUpMember) -> None:
    response = await add_role(owner, region=region)

    assert response.status_code == 422


async def test_a_bedrock_capability_list_is_checked_against_the_registry(
    owner: SignedUpMember,
) -> None:
    chat_only = created(await add_role(owner, capabilities=["chat"]))
    empty = await add_role(owner, capabilities=[])

    assert chat_only["capabilities"] == ["chat"]
    assert empty.status_code == 422


async def test_bedrock_names_share_the_organisation_namespace(owner: SignedUpMember) -> None:
    created(await add_role(owner, name="Shared name"))

    taken = await add_keys(owner, name="Shared name")

    assert taken.status_code == 409


# Adding an access-key credential (the fallback)


async def test_an_owner_adds_a_bedrock_credential_with_access_keys(
    app: FastAPI, owner: SignedUpMember
) -> None:
    verifier = _Recording()
    app.state.credential_verifier = verifier

    credential = created(await add_keys(owner, name="Bedrock (keys)", region="us-east-1"))

    assert credential == {
        "id": credential["id"],
        "name": "Bedrock (keys)",
        "provider": "bedrock",
        "auth_kind": "aws_access_keys",
        # The end of the access key ID, which Owners can match in the IAM console.
        "masked_suffix": "MPLE",
        "role_arn": None,
        "region": "us-east-1",
        "capabilities": ["chat", "embeddings", "rerank"],
        "check_status": "passed",
        "check_failure": None,
        "last_checked_at": credential["last_checked_at"],
        "created_at": credential["created_at"],
    }
    (access,) = verifier.bedrock
    assert access.access_key_id == ACCESS_KEY_ID
    assert access.secret_access_key == SECRET_ACCESS_KEY
    assert access.role_arn is None
    assert access.external_id is None
    assert SECRET_ACCESS_KEY not in json.dumps(await audit_events(owner, "credential.created"))


@pytest.mark.parametrize(
    ("secret", "reason"),
    [
        ("fake-fail-invalid_key-0000000000000000000000000", "invalid_key"),
        ("fake-fail-missing_model_access-000000000000000", "missing_model_access"),
        ("fake-fail-wrong_region-00000000000000000000000", "wrong_region"),
    ],
)
async def test_a_failed_access_key_check_gives_a_clear_reason(
    secret: str, reason: str, owner: SignedUpMember
) -> None:
    response = await add_keys(owner, secret_access_key=secret)

    assert response.status_code == 400
    assert response.json()["reason"] == reason
    assert secret not in response.text


async def test_access_keys_say_which_key_was_rejected(owner: SignedUpMember) -> None:
    response = await add_keys(
        owner,
        secret_access_key="fake-fail-invalid_key-0000000000000000000000000",  # noqa: S106
    )

    assert response.json()["detail"] == (
        "AWS rejected this access key. Check the access key ID and secret access key were "
        "copied in full."
    )


@pytest.mark.parametrize(
    ("access_key_id", "secret_access_key"),
    [
        ("short", SECRET_ACCESS_KEY),
        ("akiaiosfodnn7example", SECRET_ACCESS_KEY),
        (ACCESS_KEY_ID, "too-short"),
        (ACCESS_KEY_ID, "has a space in it and is long enough....."),
    ],
)
async def test_malformed_access_keys_are_refused_without_echoing_them(
    access_key_id: str, secret_access_key: str, owner: SignedUpMember
) -> None:
    response = await add_keys(
        owner, access_key_id=access_key_id, secret_access_key=secret_access_key
    )

    assert response.status_code == 422
    assert secret_access_key not in response.text


async def test_a_role_request_needs_a_role_arn_and_a_keys_request_needs_keys(
    owner: SignedUpMember,
) -> None:
    no_arn = await owner.client.post(
        path(owner.organisation_id, "credentials", "bedrock"),
        json={"name": "x", "auth_kind": "aws_role", "region": "us-east-1"},
    )
    no_secret = await owner.client.post(
        path(owner.organisation_id, "credentials", "bedrock"),
        json={
            "name": "x",
            "auth_kind": "aws_access_keys",
            "access_key_id": ACCESS_KEY_ID,
            "region": "us-east-1",
        },
    )

    assert no_arn.status_code == 422
    assert no_secret.status_code == 422


async def test_editors_cannot_add_bedrock_credentials(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")

    response = await add_role(editor)

    assert response.status_code == 403


# Re-checking, rotating and deleting


async def test_a_role_credential_is_rechecked_with_the_organisations_external_id(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock
) -> None:
    external_id = (await setup_of(owner))["external_id"]
    credential = created(await add_role(owner, capabilities=["rerank"]))
    verifier = _Recording(CheckResult(CheckFailure.ROLE_NOT_ASSUMABLE))
    app.state.credential_verifier = verifier
    clock.advance(60)

    response = await owner.client.post(
        path(owner.organisation_id, "credentials", credential["id"], "check")
    )

    assert response.status_code == 200
    assert response.json()["check_status"] == "failed"
    assert response.json()["check_failure"] == "role_not_assumable"
    assert response.json()["last_checked_at"] == "2026-11-05T09:01:00Z"
    (access,) = verifier.bedrock
    assert (access.role_arn, access.external_id, access.region, access.model_id) == (
        ROLE_ARN,
        external_id,
        "eu-west-2",
        "cohere.rerank-v3-5:0",
    )


async def test_an_access_key_credential_is_rechecked_with_its_stored_keys(
    app: FastAPI, owner: SignedUpMember
) -> None:
    credential = created(await add_keys(owner, region="ap-northeast-1"))
    verifier = _Recording()
    app.state.credential_verifier = verifier

    response = await owner.client.post(
        path(owner.organisation_id, "credentials", credential["id"], "check")
    )

    assert response.json()["check_status"] == "passed"
    (access,) = verifier.bedrock
    assert (access.access_key_id, access.secret_access_key, access.region) == (
        ACCESS_KEY_ID,
        SECRET_ACCESS_KEY,
        "ap-northeast-1",
    )


async def test_bedrock_credentials_are_not_rotated_with_an_api_key(
    owner: SignedUpMember,
) -> None:
    credential = created(await add_role(owner))

    response = await owner.client.post(
        path(owner.organisation_id, "credentials", credential["id"], "rotate"),
        json={"api_key": "sk-not-for-bedrock-0000"},
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Bedrock credentials can't be rotated with an API key. "
        "Add a new Bedrock credential, then delete this one."
    }


async def test_a_bedrock_credential_is_deleted_like_any_other(owner: SignedUpMember) -> None:
    credential = created(await add_keys(owner))

    response = await owner.client.delete(
        path(owner.organisation_id, "credentials", credential["id"])
    )

    assert response.status_code == 204
    (event,) = await audit_events(owner, "credential.deleted")
    assert event["before"]["region"] == "us-east-1"


async def test_the_registry_recommends_the_role_for_bedrock(owner: SignedUpMember) -> None:
    response = await owner.client.get("/api/providers")

    (bedrock,) = [p for p in response.json() if p["id"] == "bedrock"]
    # The preferred auth kind comes first.
    assert bedrock["auth_kinds"] == ["aws_role", "aws_access_keys"]
    assert [c["capability"] for c in bedrock["capabilities"]] == [
        Capability.CHAT,
        Capability.EMBEDDINGS,
        Capability.RERANK,
    ]
