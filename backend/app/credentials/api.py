"""Provider Credential routes, and the capability registry.

Members (Owners and Editors) can list and read credentials; adding, re-checking, rotating
and deleting are Owner-only. No response model has a field that carries a secret: a
credential is shown by its masked suffix only.
"""

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
from app.credentials.registry import PROVIDERS, AuthKind, Capability, Provider
from app.credentials.service import (
    CheckFailedError,
    CredentialInUseError,
    CredentialNotFoundError,
    Credentials,
    DuplicateNameError,
    NewCredential,
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

CredentialName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
ApiKeyProvider = Literal[Provider.ANTHROPIC, Provider.OPENAI, Provider.VOYAGE]


class CreateCredentialRequest(BaseModel):
    name: CredentialName
    provider: ApiKeyProvider
    # Write-only: checked, sealed and never returned.
    api_key: SecretStr
    # What the credential may be used for; defaults to everything the provider offers.
    capabilities: Annotated[list[Capability], Field(min_length=1)] | None = None


class RotateCredentialRequest(BaseModel):
    api_key: SecretStr


class CredentialOut(BaseModel):
    id: uuid.UUID
    name: str
    provider: Provider
    auth_kind: AuthKind
    # The last characters of the secret; the rest is never returned.
    masked_suffix: str
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


def _check_failed(error: CheckFailedError) -> JSONResponse:
    body = CheckFailedResponse(detail=FAILURE_MESSAGES[error.failure], reason=error.failure)
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
        names = ", ".join(error.capabilities)
        detail = f"{PROVIDERS[error.provider].name} credentials don't offer {names}."
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail) from None
    except DuplicateNameError:
        raise HTTPException(status.HTTP_409_CONFLICT, NAME_TAKEN) from None
    except CheckFailedError as error:
        return _check_failed(error)
    return _out(credential)


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
                    models=[ModelOut(id=m.id, name=m.name) for m in models],
                )
                for capability, models in spec.models.items()
            ],
        )
        for spec in PROVIDERS.values()
    ]
