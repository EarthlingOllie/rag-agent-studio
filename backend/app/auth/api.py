"""Auth routes: sign up, sign in, sign out and the signed-in Member."""

import re
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import AfterValidator, BaseModel, Field, StringConstraints
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import service
from app.auth.mfa import Mfa
from app.auth.mfa_pending import MFA_PENDING_COOKIE, PendingSignIns
from app.auth.sessions import SESSION_COOKIE, SessionStore
from app.core.clock import Clock, get_clock
from app.core.deps import get_db
from app.core.settings import Settings
from app.tenancy.models import Member, Role
from app.tenancy.repository import list_memberships

router = APIRouter(prefix="/api/auth", tags=["auth"])

SIGN_IN_FAILED = "Email or password is incorrect"
NOT_SIGNED_IN = "Not signed in"

# Deliberately loose: one @, no spaces, a dot in the domain. Delivery is the real check.
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _valid_email(value: str) -> str:
    if not _EMAIL_PATTERN.fullmatch(value):
        raise ValueError("Enter a valid email address")
    return value


Email = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=320), AfterValidator(_valid_email)
]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
# argon2 has no length limit of its own; the cap stops very long inputs costing CPU.
Password = Annotated[str, StringConstraints(min_length=12, max_length=256)]


class SignUpRequest(BaseModel):
    name: Name
    email: Email
    password: Password
    organisation_name: Name


class SignInRequest(BaseModel):
    email: Annotated[str, StringConstraints(max_length=320)]
    password: Annotated[str, StringConstraints(max_length=256)]


class MemberOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str


class MembershipOut(BaseModel):
    id: uuid.UUID = Field(description="The Organisation's ID")
    name: str
    role: Role


class SessionResponse(BaseModel):
    member: MemberOut
    organisations: list[MembershipOut]


class ErrorResponse(BaseModel):
    detail: str


def get_session_store(request: Request) -> SessionStore:
    settings: Settings = request.app.state.settings
    return SessionStore(request.app.state.redis, settings.session_ttl_seconds)


Db = Annotated[AsyncSession, Depends(get_db)]
Sessions = Annotated[SessionStore, Depends(get_session_store)]
SessionToken = Annotated[str | None, Cookie(alias=SESSION_COOKIE, include_in_schema=False)]


async def current_member(db: Db, sessions: Sessions, token: SessionToken = None) -> Member:
    """The signed-in Member, or 401."""
    member_id = None if token is None else await sessions.member_id(token)
    member = None if member_id is None else await db.get(Member, member_id)
    if member is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, NOT_SIGNED_IN)
    return member


CurrentMember = Annotated[Member, Depends(current_member)]


async def _session_response(db: AsyncSession, member: Member) -> SessionResponse:
    memberships = await list_memberships(db, member)
    return SessionResponse(
        member=MemberOut(id=member.id, name=member.name, email=member.email),
        organisations=[
            MembershipOut(id=m.organisation_id, name=m.organisation_name, role=m.role)
            for m in memberships
        ],
    )


async def _start_session(
    response: Response, request: Request, sessions: SessionStore, member: Member, old: str | None
) -> None:
    """Issues a new session token. Any session the browser already had is ended (rotation)."""
    if old is not None:
        await sessions.delete(old)
    token = await sessions.create(member.id)
    settings: Settings = request.app.state.settings
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_ttl_seconds,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )


@router.post(
    "/sign-up",
    status_code=status.HTTP_201_CREATED,
    responses={409: {"model": ErrorResponse, "description": "The email is already registered"}},
    operation_id="signUp",
)
async def sign_up(
    body: SignUpRequest,
    request: Request,
    response: Response,
    db: Db,
    sessions: Sessions,
    token: SessionToken = None,
) -> SessionResponse:
    """Creates a Member and a new Organisation they own, and signs them in."""
    try:
        member = await service.sign_up(
            db,
            name=body.name,
            email=body.email,
            password=body.password,
            organisation_name=body.organisation_name,
        )
    except service.EmailAlreadyRegisteredError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered") from None
    await _start_session(response, request, sessions, member, token)
    return await _session_response(db, member)


class MfaChallengeResponse(BaseModel):
    mfa_required: Literal[True] = True


def get_pending_sign_ins(request: Request) -> PendingSignIns:
    settings: Settings = request.app.state.settings
    return PendingSignIns(request.app.state.redis, settings.mfa_pending_ttl_seconds)


PendingStore = Annotated[PendingSignIns, Depends(get_pending_sign_ins)]
# Sent only to the MFA routes and to sign-in (which replaces it).
MFA_PENDING_COOKIE_PATH = "/api/auth"


@router.post(
    "/sign-in",
    responses={
        202: {
            "model": MfaChallengeResponse,
            "description": "The password is right and the Member uses MFA: send a code to "
            "`/api/auth/mfa/verify` to finish signing in",
        },
        401: {"model": ErrorResponse, "description": SIGN_IN_FAILED},
    },
    response_model=SessionResponse,
    operation_id="signIn",
)
async def sign_in(
    body: SignInRequest,
    request: Request,
    response: Response,
    db: Db,
    sessions: Sessions,
    pending: PendingStore,
    clock: Annotated[Clock, Depends(get_clock)],
    token: SessionToken = None,
) -> SessionResponse | JSONResponse:
    member = await service.authenticate(db, email=body.email, password=body.password)
    if member is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, SIGN_IN_FAILED)
    if await Mfa(db, request.app.state.envelope, clock).is_enabled(member.id):
        challenge = JSONResponse(
            MfaChallengeResponse().model_dump(), status_code=status.HTTP_202_ACCEPTED
        )
        if token is not None:
            await sessions.delete(token)
            challenge.delete_cookie(
                SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="lax"
            )
        settings: Settings = request.app.state.settings
        challenge.set_cookie(
            MFA_PENDING_COOKIE,
            await pending.create(member.id),
            max_age=settings.mfa_pending_ttl_seconds,
            path=MFA_PENDING_COOKIE_PATH,
            secure=True,
            httponly=True,
            samesite="lax",
        )
        return challenge
    await _start_session(response, request, sessions, member, token)
    return await _session_response(db, member)


async def finish_mfa_sign_in(
    response: Response,
    request: Request,
    db: AsyncSession,
    sessions: SessionStore,
    member: Member,
    old_session: str | None,
) -> SessionResponse:
    """Turns a verified MFA-pending sign-in into a full session."""
    response.delete_cookie(
        MFA_PENDING_COOKIE, path=MFA_PENDING_COOKIE_PATH, secure=True, httponly=True, samesite="lax"
    )
    await _start_session(response, request, sessions, member, old_session)
    return await _session_response(db, member)


@router.post("/sign-out", status_code=status.HTTP_204_NO_CONTENT, operation_id="signOut")
async def sign_out(response: Response, sessions: Sessions, token: SessionToken = None) -> None:
    """Ends the session on the server and clears the cookie. Signed out already is fine."""
    if token is not None:
        await sessions.delete(token)
    response.delete_cookie(SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="lax")


@router.get(
    "/me",
    responses={401: {"model": ErrorResponse, "description": NOT_SIGNED_IN}},
    operation_id="getMe",
)
async def me(member: CurrentMember, db: Db) -> SessionResponse:
    return await _session_response(db, member)
