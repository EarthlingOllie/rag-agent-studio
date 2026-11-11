"""Provider Credential routes, and the capability registry.

Members (Owners and Editors) can list and read credentials; adding, re-checking, rotating
and deleting are Owner-only. No response model has a field that carries a secret: a
credential is shown by its masked suffix only.
"""

import json
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, SecretStr, StringConstraints

from app.auth.api import CurrentMember, Db, ErrorResponse
from app.core.clock import Clock, get_clock
from app.credentials.models import ProviderCredential
from app.credentials.references import ReferenceRegistry
from app.credentials.registry import PROVIDERS, AuthKind, Capability, Provider, models_for
from app.credentials.service import (
    CheckFailedError,
    CredentialInUseError,
    CredentialNotFoundError,
    Credentials,
    DuplicateNameError,
    NewBedrockCredential,
    NewCredential,
    NotRotatableError,
    UnsupportedCapabilityError,
)
from app.credentials.verifier import CheckFailure, CredentialVerifier, get_verifier
from app.tenancy.api import ORGANISATION_PREFIX
from app.tenancy.policy import NOT_FOUND, OWNERS_ONLY, OwnerScope, Scope

router = APIRouter(prefix=ORGANISATION_PREFIX, tags=["credentials"])
providers_router = APIRouter(prefix="/api/providers", tags=["credentials"])

API_KEY_MIN, API_KEY_MAX = 8, 512
INVALID_API_KEY = (
    f"An API key is {API_KEY_MIN} to {API_KEY_MAX} characters, with no spaces or line breaks."
)
NAME_TAKEN = "Another credential in this Organisation already has that name."
IN_USE = "This credential is still in use. Move these items to another credential first."
FAILURE_MESSAGES = {
    CheckFailure.INVALID_KEY: "The provider rejected this API key. Check it was copied in full.",
    CheckFailure.MISSING_MODEL_ACCESS: (
        "The key works, but it can't use this provider's models. "
        "Check the key's permissions in your provider account."
    ),
    CheckFailure.QUOTA_EXCEEDED: (
        "The provider says this key is over its rate limit or quota. "
        "Try again later, or check your plan."
    ),
    CheckFailure.PROVIDER_UNREACHABLE: (
        "We couldn't reach the provider to check the key. Try again in a few minutes."
    ),
}
BEDROCK_FAILURE_MESSAGES = {
    CheckFailure.INVALID_KEY: (
        "AWS rejected this access key. Check the access key ID and secret access key were "
        "copied in full."
    ),
    CheckFailure.ROLE_NOT_ASSUMABLE: (
        "We couldn't assume this role. Check the role ARN, and that the role's trust policy "
        "is exactly the one shown, with your external ID."
    ),
    CheckFailure.MISSING_MODEL_ACCESS: (
        "The role works, but it can't use the model. Enable model access in the Bedrock "
        "console for this region, and check the role's permissions policy."
    ),
    CheckFailure.WRONG_REGION: (
        "Bedrock, or this model, isn't available in that region. Choose the region where "
        "you enabled model access."
    ),
    CheckFailure.QUOTA_EXCEEDED: (
        "AWS says this account is over its Bedrock rate limit or quota. Try again later."
    ),
    CheckFailure.PROVIDER_UNREACHABLE: (
        "We couldn't reach AWS to check the credential. Try again in a few minutes."
    ),
}
NOT_ROTATABLE = (
    "Bedrock credentials can't be rotated with an API key. "
    "Add a new Bedrock credential, then delete this one."
)
# The Bedrock actions the Owner's role (or access keys) must allow.
BEDROCK_ACTIONS = (
    "bedrock:InvokeModel",
    "bedrock:InvokeModelWithResponseStream",
    "bedrock:GetFoundationModelAvailability",
)

CredentialName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
ApiKeyProvider = Literal[Provider.ANTHROPIC, Provider.OPENAI, Provider.VOYAGE, Provider.DEMO]


class CreateCredentialRequest(BaseModel):
    name: CredentialName
    provider: ApiKeyProvider
    # Write-only: checked, sealed and never returned.
    api_key: SecretStr
    # What the credential may be used for; defaults to everything the provider offers.
    capabilities: Annotated[list[Capability], Field(min_length=1)] | None = None


# An IAM role in any AWS partition, possibly with a path: arn:aws:iam::123456789012:role/Name
RoleArn = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        max_length=2048,
        pattern=r"^arn:aws(-[a-z]+)*:iam::[0-9]{12}:role/[A-Za-z0-9_+=,.@/-]+$",
    ),
]
# An AWS region code, such as us-east-1 or us-gov-west-1.
AwsRegion = Annotated[
    str, StringConstraints(strip_whitespace=True, pattern=r"^[a-z]{2}(-[a-z]+)+-[0-9]{1,2}$")
]
AccessKeyId = Annotated[
    str, StringConstraints(strip_whitespace=True, pattern=r"^[A-Z0-9]{16,128}$")
]
SECRET_ACCESS_KEY_MIN, SECRET_ACCESS_KEY_MAX = 16, 128
INVALID_SECRET_ACCESS_KEY = (
    f"A secret access key is {SECRET_ACCESS_KEY_MIN} to {SECRET_ACCESS_KEY_MAX} characters, "
    "with no spaces or line breaks."
)
Capabilities = Annotated[list[Capability], Field(min_length=1)] | None


class CreateBedrockRoleRequest(BaseModel):
    """A Bedrock credential the platform reaches by assuming an IAM role (recommended)."""

    auth_kind: Literal[AuthKind.AWS_ROLE]
    name: CredentialName
    role_arn: RoleArn
    region: AwsRegion
    capabilities: Capabilities = None


class CreateBedrockAccessKeysRequest(BaseModel):
    """A Bedrock credential reached with an IAM user's access keys (the fallback)."""

    auth_kind: Literal[AuthKind.AWS_ACCESS_KEYS]
    name: CredentialName
    access_key_id: AccessKeyId
    # Write-only: checked, sealed and never returned.
    secret_access_key: SecretStr
    region: AwsRegion
    capabilities: Capabilities = None


CreateBedrockRequest = Annotated[
    CreateBedrockRoleRequest | CreateBedrockAccessKeysRequest, Field(discriminator="auth_kind")
]


class BedrockSetupOut(BaseModel):
    """What an Owner pastes into AWS to let the platform assume their role."""

    external_id: str
    platform_principal: str
    trust_policy: str
    permissions_policy: str


class RotateCredentialRequest(BaseModel):
    api_key: SecretStr


class CredentialOut(BaseModel):
    id: uuid.UUID
    name: str
    provider: Provider
    auth_kind: AuthKind
    # The last characters of the secret (or of the AWS access key ID); the rest is never
    # returned. None for a Bedrock IAM role, which has no secret.
    masked_suffix: str | None
    # The Owner's IAM role, for Bedrock role credentials.
    role_arn: str | None
    # The AWS region, for Bedrock.
    region: str | None
    capabilities: list[Capability]
    check_status: Literal["passed", "failed"]
    check_failure: CheckFailure | None
    last_checked_at: datetime
    created_at: datetime


class CheckFailedResponse(BaseModel):
    detail: str
    reason: CheckFailure


class CredentialReferenceOut(BaseModel):
    kind: str
    id: str
    name: str


class CredentialInUseResponse(BaseModel):
    detail: str
    references: list[CredentialReferenceOut]


class ModelOut(BaseModel):
    id: str
    name: str
    # Whether the model can call tools, as Agentic Retrieval Mode needs; false for every
    # embedding and rerank model.
    supports_tools: bool


class CapabilityModelsOut(BaseModel):
    capability: Capability
    models: list[ModelOut]


class ProviderOut(BaseModel):
    id: Provider
    name: str
    auth_kinds: list[AuthKind]
    capabilities: list[CapabilityModelsOut]


def get_credentials(
    request: Request,
    db: Db,
    clock: Annotated[Clock, Depends(get_clock)],
    verifier: Annotated[CredentialVerifier, Depends(get_verifier)],
) -> Credentials:
    references: ReferenceRegistry = request.app.state.credential_references
    return Credentials(
        db,
        envelope=request.app.state.envelope,
        verifier=verifier,
        references=references,
        clock=clock,
    )


CredentialsService = Annotated[Credentials, Depends(get_credentials)]

_Responses = dict[int | str, dict[str, Any]]
_NOT_FOUND: _Responses = {404: {"model": ErrorResponse, "description": NOT_FOUND}}
_OWNER_ONLY: _Responses = {403: {"model": ErrorResponse, "description": OWNERS_ONLY}, **_NOT_FOUND}
_CHECK_FAILED: _Responses = {
    400: {"model": CheckFailedResponse, "description": "The provider check failed"}
}


def _out(credential: ProviderCredential) -> CredentialOut:
    return CredentialOut(
        id=credential.id,
        name=credential.name,
        provider=Provider(credential.provider),
        auth_kind=AuthKind(credential.auth_kind),
        masked_suffix=credential.masked_suffix,
        role_arn=credential.role_arn,
        region=credential.region,
        capabilities=[Capability(c) for c in credential.capabilities],
        check_status="passed" if credential.check_status == "passed" else "failed",
        check_failure=None
        if credential.check_failure is None
        else CheckFailure(credential.check_failure),
        last_checked_at=credential.last_checked_at,
        created_at=credential.created_at,
    )


def _api_key(secret: SecretStr) -> str:
    """The key without surrounding whitespace; refused (without echoing it) if malformed."""
    key = secret.get_secret_value().strip()
    if not API_KEY_MIN <= len(key) <= API_KEY_MAX or any(c.isspace() for c in key):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, INVALID_API_KEY)
    return key


def _check_failed(error: CheckFailedError, *, bedrock: bool = False) -> JSONResponse:
    messages = BEDROCK_FAILURE_MESSAGES if bedrock else FAILURE_MESSAGES
    body = CheckFailedResponse(detail=messages[error.failure], reason=error.failure)
    return JSONResponse(body.model_dump(mode="json"), status_code=status.HTTP_400_BAD_REQUEST)


def _not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)


@router.get("/credentials", responses=_NOT_FOUND, operation_id="listCredentials")
async def list_credentials(scope: Scope, credentials: CredentialsService) -> list[CredentialOut]:
    """The Organisation's Provider Credentials, by name. Open to every Member."""
    return [_out(credential) for credential in await credentials.list(scope)]


@router.post(
    "/credentials",
    status_code=status.HTTP_201_CREATED,
    responses={
        **_OWNER_ONLY,
        **_CHECK_FAILED,
        409: {"model": ErrorResponse, "description": NAME_TAKEN},
    },
    response_model=CredentialOut,
    operation_id="createCredential",
)
async def create_credential(
    body: CreateCredentialRequest, scope: OwnerScope, credentials: CredentialsService
) -> CredentialOut | JSONResponse:
    """Checks the key with the provider, then stores it encrypted. A failed check stores nothing."""
    new = NewCredential(body.name, body.provider, _api_key(body.api_key), body.capabilities)
    try:
        credential = await credentials.create(scope, new)
    except UnsupportedCapabilityError as error:
        raise _unsupported(error) from None
    except DuplicateNameError:
        raise HTTPException(status.HTTP_409_CONFLICT, NAME_TAKEN) from None
    except CheckFailedError as error:
        return _check_failed(error)
    return _out(credential)


def _unsupported(error: UnsupportedCapabilityError) -> HTTPException:
    names = ", ".join(error.capabilities)
    detail = f"{PROVIDERS[error.provider].name} credentials don't offer {names}."
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail)


@router.post(
    "/credentials/bedrock",
    status_code=status.HTTP_201_CREATED,
    responses={
        **_OWNER_ONLY,
        **_CHECK_FAILED,
        409: {"model": ErrorResponse, "description": NAME_TAKEN},
    },
    response_model=CredentialOut,
    operation_id="createBedrockCredential",
)
async def create_bedrock_credential(
    body: CreateBedrockRequest, scope: OwnerScope, credentials: CredentialsService
) -> CredentialOut | JSONResponse:
    """Adds a Bedrock credential: an IAM role the platform assumes with the Organisation's
    external ID (recommended: no secret is stored), or access keys. The platform checks role
    assumption (or the keys), then model access, before storing anything."""
    if isinstance(body, CreateBedrockRoleRequest):
        new = NewBedrockCredential(
            body.name, body.region, role_arn=body.role_arn, capabilities=body.capabilities
        )
    else:
        secret = body.secret_access_key.get_secret_value().strip()
        if not SECRET_ACCESS_KEY_MIN <= len(secret) <= SECRET_ACCESS_KEY_MAX or any(
            c.isspace() for c in secret
        ):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, INVALID_SECRET_ACCESS_KEY)
        new = NewBedrockCredential(
            body.name,
            body.region,
            access_key_id=body.access_key_id,
            secret_access_key=secret,
            capabilities=body.capabilities,
        )
    try:
        # Bedrock offers every capability, so no choice of them is unsupported.
        credential = await credentials.create_bedrock(scope, new)
    except DuplicateNameError:
        raise HTTPException(status.HTTP_409_CONFLICT, NAME_TAKEN) from None
    except CheckFailedError as error:
        return _check_failed(error, bedrock=True)
    return _out(credential)


def _policy(statement: dict[str, Any]) -> str:
    return json.dumps({"Version": "2012-10-17", "Statement": [statement]}, indent=2)


@router.get("/bedrock-setup", responses=_OWNER_ONLY, operation_id="getBedrockSetup")
async def get_bedrock_setup(
    request: Request, scope: OwnerScope, credentials: CredentialsService
) -> BedrockSetupOut:
    """The Organisation's external ID, and the trust and permissions policies to paste into
    the IAM role the platform will assume."""
    external_id = await credentials.bedrock_external_id(scope)
    principal: str = request.app.state.settings.bedrock_platform_principal
    trust = {
        "Effect": "Allow",
        "Principal": {"AWS": principal},
        "Action": "sts:AssumeRole",
        "Condition": {"StringEquals": {"sts:ExternalId": external_id}},
    }
    permissions = {"Effect": "Allow", "Action": list(BEDROCK_ACTIONS), "Resource": "*"}
    return BedrockSetupOut(
        external_id=external_id,
        platform_principal=principal,
        trust_policy=_policy(trust),
        permissions_policy=_policy(permissions),
    )


@router.get("/credentials/{credential_id}", responses=_NOT_FOUND, operation_id="getCredential")
async def get_credential(
    credential_id: uuid.UUID, scope: Scope, credentials: CredentialsService
) -> CredentialOut:
    try:
        return _out(await credentials.get(scope, credential_id))
    except CredentialNotFoundError:
        raise _not_found() from None


@router.post(
    "/credentials/{credential_id}/check", responses=_OWNER_ONLY, operation_id="checkCredential"
)
async def check_credential(
    credential_id: uuid.UUID, scope: OwnerScope, credentials: CredentialsService
) -> CredentialOut:
    """Checks the stored key with the provider again; the outcome is on the credential."""
    try:
        return _out(await credentials.recheck(scope, credential_id))
    except CredentialNotFoundError:
        raise _not_found() from None


@router.post(
    "/credentials/{credential_id}/rotate",
    responses={**_OWNER_ONLY, **_CHECK_FAILED},
    response_model=CredentialOut,
    operation_id="rotateCredential",
)
async def rotate_credential(
    credential_id: uuid.UUID,
    body: RotateCredentialRequest,
    scope: OwnerScope,
    credentials: CredentialsService,
) -> CredentialOut | JSONResponse:
    """Replaces the key, keeping the credential's identity. A failed check keeps the old key."""
    api_key = _api_key(body.api_key)
    try:
        return _out(await credentials.rotate(scope, credential_id, api_key))
    except CredentialNotFoundError:
        raise _not_found() from None
    except NotRotatableError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, NOT_ROTATABLE) from None
    except CheckFailedError as error:
        return _check_failed(error)


@router.delete(
    "/credentials/{credential_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**_OWNER_ONLY, 409: {"model": CredentialInUseResponse, "description": IN_USE}},
    response_model=None,
    operation_id="deleteCredential",
)
async def delete_credential(
    credential_id: uuid.UUID, scope: OwnerScope, credentials: CredentialsService
) -> JSONResponse | None:
    """Deletes the credential, unless something still references it (409 lists what does)."""
    try:
        await credentials.delete(scope, credential_id)
    except CredentialNotFoundError:
        raise _not_found() from None
    except CredentialInUseError as error:
        body = CredentialInUseResponse(
            detail=IN_USE,
            references=[
                CredentialReferenceOut(kind=r.kind, id=r.id, name=r.name) for r in error.references
            ],
        )
        return JSONResponse(body.model_dump(mode="json"), status_code=status.HTTP_409_CONFLICT)
    return None


@router.get(
    "/credentials/{credential_id}/models/{capability}",
    responses=_NOT_FOUND,
    operation_id="listCredentialModels",
)
async def list_credential_models(
    credential_id: uuid.UUID, capability: Capability, scope: Scope, credentials: CredentialsService
) -> list[ModelOut]:
    """The models this credential offers for a capability: empty unless the credential was
    given that capability. Open to every Member, for model pickers."""
    try:
        credential = await credentials.get(scope, credential_id)
    except CredentialNotFoundError:
        raise _not_found() from None
    offered = models_for(Provider(credential.provider), credential.capabilities, capability)
    return [ModelOut(id=m.id, name=m.name, supports_tools=m.supports_tools) for m in offered]


@providers_router.get(
    "",
    responses={401: {"model": ErrorResponse, "description": "Not signed in"}},
    operation_id="listProviders",
)
async def list_providers(member: CurrentMember) -> list[ProviderOut]:
    """The capability registry: each provider, its auth kinds, and its models per capability."""
    return [
        ProviderOut(
            id=spec.provider,
            name=spec.name,
            auth_kinds=list(spec.auth_kinds),
            capabilities=[
                CapabilityModelsOut(
                    capability=capability,
                    models=[
                        ModelOut(id=m.id, name=m.name, supports_tools=m.supports_tools)
                        for m in models
                    ],
                )
                for capability, models in spec.models.items()
            ],
        )
        for spec in PROVIDERS.values()
    ]
