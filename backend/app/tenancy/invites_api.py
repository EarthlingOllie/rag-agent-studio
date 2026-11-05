"""Invite routes.

Owners manage an Organisation's Invites under ``/api/organisations/{organisation_id}/invites``.
The invited person looks an Invite up and accepts it under ``/api/invites``, by the token from
the link. Tokens travel in request bodies, never in paths, so they don't appear in access logs.
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, StringConstraints

from app.auth.api import (
    CurrentMember,
    Db,
    Email,
    ErrorResponse,
    Name,
    Password,
    SessionResponse,
    Sessions,
    SessionToken,
    session_response,
    start_session,
)
from app.auth.service import EmailAlreadyRegisteredError
from app.core.clock import Clock, get_clock
from app.core.settings import Settings
from app.mail import templates
from app.mail.port import Mailer
from app.tenancy import invites
from app.tenancy.api import ORGANISATION_PREFIX
from app.tenancy.models import Invite, Member, Role
from app.tenancy.policy import NOT_FOUND, OWNERS_ONLY, OwnerScope
from app.tenancy.repository import OrganisationScope, get_organisation

logger = logging.getLogger(__name__)

owner_router = APIRouter(prefix=f"{ORGANISATION_PREFIX}/invites", tags=["invites"])
router = APIRouter(prefix="/api/invites", tags=["invites"])

ALREADY_A_MEMBER = "That person is already a Member of this Organisation"
PENDING_INVITE_EXISTS = "That email already has a pending invite. Copy a new link or revoke it."
INVALID_INVITE = "This invite link is invalid or has expired."
ACCOUNT_EXISTS = "An account with this email already exists. Sign in to accept the invite."

ClockDep = Annotated[Clock, Depends(get_clock)]
InviteToken = Annotated[str, StringConstraints(min_length=1, max_length=256)]

_OWNER_ROUTE_ERRORS: dict[int | str, dict[str, Any]] = {
    403: {"model": ErrorResponse, "description": OWNERS_ONLY},
    404: {"model": ErrorResponse, "description": NOT_FOUND},
}


class InviterOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str


class InviteOut(BaseModel):
    id: uuid.UUID
    email: str
    role: Role
    created_at: datetime
    expires_at: datetime
    expired: bool
    invited_by: InviterOut


class IssuedInviteOut(BaseModel):
    invite: InviteOut
    link: str
    email_sent: bool


class CreateInviteRequest(BaseModel):
    email: Email
    role: Role
    send_email: bool = True


class RenewInviteRequest(BaseModel):
    send_email: bool = False


def _invite_out(invite: Invite, inviter: Member, now: datetime) -> InviteOut:
    return InviteOut(
        id=invite.id,
        email=invite.email,
        role=invite.role,
        created_at=invite.created_at,
        expires_at=invite.expires_at,
        expired=invite.expires_at <= now,
        invited_by=InviterOut(id=inviter.id, name=inviter.name, email=inviter.email),
    )


def _valid_for(request: Request) -> timedelta:
    settings: Settings = request.app.state.settings
    return timedelta(seconds=settings.invite_ttl_seconds)


async def _issued(
    request: Request,
    db: Db,
    scope: OrganisationScope,
    member: Member,
    issued: invites.IssuedInvite,
    *,
    send_email: bool,
    now: datetime,
) -> IssuedInviteOut:
    """The Invite and its link; emails the link first if asked. A failed email is reported."""
    settings: Settings = request.app.state.settings
    link = templates.invite_link(str(settings.studio_url), issued.token)
    email_sent = False
    if send_email:
        organisation = await get_organisation(db, scope)
        mailer: Mailer = request.app.state.mailer
        try:
            await mailer.send(
                templates.invite(
                    to=issued.invite.email,
                    organisation_name=organisation.name,
                    inviter_name=member.name,
                    role=issued.invite.role.value,
                    link=link,
                    valid_for=_valid_for(request),
                )
            )
            email_sent = True
        except Exception:
            logger.exception("Sending an invite email failed")
    return IssuedInviteOut(
        invite=_invite_out(issued.invite, member, now), link=link, email_sent=email_sent
    )


@owner_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses={
        **_OWNER_ROUTE_ERRORS,
        409: {
            "model": ErrorResponse,
            "description": f"{ALREADY_A_MEMBER}, or {PENDING_INVITE_EXISTS}",
        },
    },
    operation_id="createInvite",
)
async def create_invite(
    body: CreateInviteRequest,
    scope: OwnerScope,
    member: CurrentMember,
    request: Request,
    db: Db,
    clock: ClockDep,
) -> IssuedInviteOut:
    """Invites someone with a role. The answer holds a link to copy, emailed too if asked."""
    now = clock.now()
    try:
        issued = await invites.create_invite(
            db, scope, email=body.email, role=body.role, now=now, valid_for=_valid_for(request)
        )
    except invites.AlreadyAMemberError:
        raise HTTPException(status.HTTP_409_CONFLICT, ALREADY_A_MEMBER) from None
    except invites.PendingInviteExistsError:
        raise HTTPException(status.HTTP_409_CONFLICT, PENDING_INVITE_EXISTS) from None
    return await _issued(request, db, scope, member, issued, send_email=body.send_email, now=now)


@owner_router.get("", responses=_OWNER_ROUTE_ERRORS, operation_id="listInvites")
async def list_invites(scope: OwnerScope, db: Db, clock: ClockDep) -> list[InviteOut]:
    """Pending Invites (not accepted or revoked), newest first, including expired ones."""
    now = clock.now()
    return [_invite_out(p.invite, p.invited_by, now) for p in await invites.list_pending(db, scope)]


@owner_router.delete(
    "/{invite_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_OWNER_ROUTE_ERRORS,
    operation_id="revokeInvite",
)
async def revoke_invite(invite_id: uuid.UUID, scope: OwnerScope, db: Db, clock: ClockDep) -> None:
    """Revokes a pending Invite; its link stops working."""
    try:
        await invites.revoke_invite(db, scope, invite_id, now=clock.now())
    except invites.InviteNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None


@owner_router.post("/{invite_id}/renew", responses=_OWNER_ROUTE_ERRORS, operation_id="renewInvite")
async def renew_invite(
    invite_id: uuid.UUID,
    body: RenewInviteRequest,
    scope: OwnerScope,
    member: CurrentMember,
    request: Request,
    db: Db,
    clock: ClockDep,
) -> IssuedInviteOut:
    """A new link (and expiry) for a pending Invite; the previous link stops working."""
    now = clock.now()
    try:
        issued = await invites.renew_invite(
            db, scope, invite_id, now=now, valid_for=_valid_for(request)
        )
    except invites.InviteNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    return await _issued(request, db, scope, member, issued, send_email=body.send_email, now=now)


class InviteLookupRequest(BaseModel):
    token: InviteToken


class InvitePreviewOut(BaseModel):
    organisation_id: uuid.UUID
    organisation_name: str
    email: str
    role: Role
    invited_by_name: str
    account_exists: bool


@router.post(
    "/lookup",
    responses={404: {"model": ErrorResponse, "description": INVALID_INVITE}},
    operation_id="lookUpInvite",
)
async def look_up_invite(body: InviteLookupRequest, db: Db, clock: ClockDep) -> InvitePreviewOut:
    """What an invite link offers, for the accept screen. Needs no session."""
    try:
        preview = await invites.preview_invite(db, token=body.token, now=clock.now())
    except invites.InvalidInviteError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, INVALID_INVITE) from None
    return InvitePreviewOut(
        organisation_id=preview.organisation_id,
        organisation_name=preview.organisation_name,
        email=preview.email,
        role=preview.role,
        invited_by_name=preview.invited_by_name,
        account_exists=preview.account_exists,
    )


class AcceptInviteRequest(BaseModel):
    token: InviteToken


@router.post(
    "/accept",
    responses={
        400: {"model": ErrorResponse, "description": INVALID_INVITE},
        401: {"model": ErrorResponse, "description": "Not signed in"},
        403: {"model": ErrorResponse, "description": "The invite is for another email address"},
    },
    operation_id="acceptInvite",
)
async def accept_invite(
    body: AcceptInviteRequest,
    member: CurrentMember,
    request: Request,
    response: Response,
    db: Db,
    sessions: Sessions,
    clock: ClockDep,
    token: SessionToken = None,
) -> SessionResponse:
    """Adds the signed-in Member to the Organisation. The session is rotated (new privileges)."""
    try:
        await invites.accept_invite(db, member, token=body.token, now=clock.now())
    except invites.InvalidInviteError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, INVALID_INVITE) from None
    except invites.InviteForAnotherEmailError as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"This invite is for {exc.invited_email}. Sign in with that email to accept it.",
        ) from None
    await start_session(response, request, sessions, member, token)
    return await session_response(db, member)


class InviteSignUpRequest(BaseModel):
    token: InviteToken
    name: Name
    password: Password


@router.post(
    "/sign-up",
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse, "description": INVALID_INVITE},
        409: {"model": ErrorResponse, "description": ACCOUNT_EXISTS},
    },
    operation_id="signUpWithInvite",
)
async def sign_up_with_invite(
    body: InviteSignUpRequest,
    request: Request,
    response: Response,
    db: Db,
    sessions: Sessions,
    clock: ClockDep,
    token: SessionToken = None,
) -> SessionResponse:
    """Creates an account for the invited email, joins the Organisation and signs in."""
    try:
        member = await invites.accept_invite_as_new_member(
            db, token=body.token, name=body.name, password=body.password, now=clock.now()
        )
    except invites.InvalidInviteError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, INVALID_INVITE) from None
    except EmailAlreadyRegisteredError:
        raise HTTPException(status.HTTP_409_CONFLICT, ACCOUNT_EXISTS) from None
    await start_session(response, request, sessions, member, token)
    return await session_response(db, member)
