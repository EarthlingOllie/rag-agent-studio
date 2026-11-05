"""MFA routes: status, enrolment, the sign-in challenge, recovery codes and disabling."""

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, StringConstraints

from app.auth.api import (
    CurrentMember,
    Db,
    ErrorResponse,
    PendingStore,
    SessionResponse,
    Sessions,
    SessionToken,
    finish_mfa_sign_in,
)
from app.auth.mfa import (
    CodeIncorrectError,
    Mfa,
    MfaAlreadyEnabledError,
    MfaNotEnabledError,
    MfaRequiredByOrganisationError,
    NoPendingEnrolmentError,
)
from app.auth.mfa_pending import MFA_PENDING_COOKIE
from app.core.clock import Clock, get_clock
from app.tenancy.models import Member

router = APIRouter(prefix="/api/auth/mfa", tags=["mfa"])

CODE_INCORRECT = "Code is incorrect"
SIGN_IN_AGAIN = "Sign in again"
ALREADY_ENABLED = "MFA is already enabled"
NOT_ENABLED = "MFA is not enabled"
PASSWORD_OR_CODE_INCORRECT = "Password or code is incorrect"  # noqa: S105 (a message)

# A six-digit authenticator code or a recovery code (dashes and spaces are ignored).
Code = Annotated[str, StringConstraints(min_length=1, max_length=64)]


def get_mfa(request: Request, db: Db, clock: Annotated[Clock, Depends(get_clock)]) -> Mfa:
    return Mfa(db, request.app.state.envelope, clock)


MfaService = Annotated[Mfa, Depends(get_mfa)]
PendingToken = Annotated[str | None, Cookie(alias=MFA_PENDING_COOKIE, include_in_schema=False)]


class MfaStatusResponse(BaseModel):
    enabled: bool
    recovery_codes_remaining: int


class EnrolmentResponse(BaseModel):
    secret: str
    otpauth_uri: str
    qr_code: str


class CodeRequest(BaseModel):
    code: Code


class DisableRequest(BaseModel):
    password: Annotated[str, StringConstraints(max_length=256)]
    code: Code


class RecoveryCodesResponse(BaseModel):
    recovery_codes: list[str]


def required_by_organisations_message(names: list[str]) -> str:
    """ "MFA can't be turned off while A requires it." or "… while A, B and C require it." """
    if len(names) == 1:
        return f"MFA can't be turned off while {names[0]} requires it."
    return f"MFA can't be turned off while {', '.join(names[:-1])} and {names[-1]} require it."


def _error(status_code: int, detail: str) -> dict[int | str, dict[str, object]]:
    return {status_code: {"model": ErrorResponse, "description": detail}}


@router.get("", operation_id="getMfaStatus", responses=_error(401, "Not signed in"))
async def get_status(member: CurrentMember, mfa: MfaService) -> MfaStatusResponse:
    status_ = await mfa.status(member.id)
    return MfaStatusResponse(
        enabled=status_.enabled, recovery_codes_remaining=status_.recovery_codes_remaining
    )


@router.post(
    "/enrolment",
    status_code=status.HTTP_201_CREATED,
    operation_id="startMfaEnrolment",
    responses=_error(409, ALREADY_ENABLED),
)
async def start_enrolment(member: CurrentMember, mfa: MfaService) -> EnrolmentResponse:
    """A new secret for an authenticator app, as a QR code and as text. Starting again
    replaces an unconfirmed secret."""
    try:
        enrolment = await mfa.start_enrolment(member)
    except MfaAlreadyEnabledError:
        raise HTTPException(status.HTTP_409_CONFLICT, ALREADY_ENABLED) from None
    return EnrolmentResponse(
        secret=enrolment.secret, otpauth_uri=enrolment.otpauth_uri, qr_code=enrolment.qr_code
    )


@router.post(
    "/enrolment/confirm",
    operation_id="confirmMfaEnrolment",
    responses=_error(400, CODE_INCORRECT) | _error(409, "Start enrolment first, or already on"),
)
async def confirm_enrolment(
    body: CodeRequest, member: CurrentMember, mfa: MfaService
) -> RecoveryCodesResponse:
    """Turns MFA on. The ten recovery codes in the response are never shown again."""
    try:
        codes = await mfa.confirm_enrolment(member, body.code)
    except NoPendingEnrolmentError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Start enrolment first") from None
    except MfaAlreadyEnabledError:
        raise HTTPException(status.HTTP_409_CONFLICT, ALREADY_ENABLED) from None
    except CodeIncorrectError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, CODE_INCORRECT) from None
    return RecoveryCodesResponse(recovery_codes=codes)


@router.post(
    "/verify",
    operation_id="verifyMfa",
    responses=_error(400, CODE_INCORRECT) | _error(401, SIGN_IN_AGAIN),
)
async def verify(
    body: CodeRequest,
    request: Request,
    response: Response,
    db: Db,
    sessions: Sessions,
    pending: PendingStore,
    mfa: MfaService,
    pending_token: PendingToken = None,
    session_token: SessionToken = None,
) -> SessionResponse:
    """Finishes an MFA-pending sign-in with an authenticator or recovery code."""
    member_id = None if pending_token is None else await pending.member_id(pending_token)
    if pending_token is None or member_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, SIGN_IN_AGAIN)
    try:
        accepted = await mfa.verify(member_id, body.code)
    except MfaNotEnabledError:
        # MFA was turned off between the password and the code: sign in again.
        await pending.delete(pending_token)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, SIGN_IN_AGAIN) from None
    if not accepted:
        await pending.record_failure(pending_token)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, CODE_INCORRECT)
    await pending.delete(pending_token)
    member = await db.get_one(Member, member_id)
    return await finish_mfa_sign_in(response, request, db, sessions, member, session_token)


@router.post(
    "/recovery-codes",
    operation_id="replaceRecoveryCodes",
    responses=_error(400, CODE_INCORRECT) | _error(409, NOT_ENABLED),
)
async def replace_recovery_codes(
    body: CodeRequest, member: CurrentMember, mfa: MfaService
) -> RecoveryCodesResponse:
    """New recovery codes for a code; the old ones stop working."""
    try:
        codes = await mfa.replace_recovery_codes(member, body.code)
    except MfaNotEnabledError:
        raise HTTPException(status.HTTP_409_CONFLICT, NOT_ENABLED) from None
    except CodeIncorrectError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, CODE_INCORRECT) from None
    return RecoveryCodesResponse(recovery_codes=codes)


@router.post(
    "/disable",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="disableMfa",
    responses=_error(400, PASSWORD_OR_CODE_INCORRECT)
    | _error(409, "MFA is not enabled, or an Organisation of the Member requires it"),
)
async def disable(body: DisableRequest, member: CurrentMember, mfa: MfaService) -> None:
    """Turns MFA off with the password and a code, unless an Organisation requires it."""
    try:
        await mfa.disable(member, password=body.password, code=body.code)
    except MfaNotEnabledError:
        raise HTTPException(status.HTTP_409_CONFLICT, NOT_ENABLED) from None
    except MfaRequiredByOrganisationError as required:
        message = required_by_organisations_message(required.organisation_names)
        raise HTTPException(status.HTTP_409_CONFLICT, message) from None
    except CodeIncorrectError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, PASSWORD_OR_CODE_INCORRECT) from None
