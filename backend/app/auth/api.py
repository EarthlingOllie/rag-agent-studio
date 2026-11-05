"""Auth routes: sign up, sign in, sign out and the signed-in Member."""

import re
import uuid
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import AfterValidator, BaseModel, Field, StringConstraints
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import Address

from app.auth import service
from app.auth.sessions import SESSION_COOKIE, SessionStore
from app.auth.throttle import SignInThrottle
from app.core.deps import get_db
from app.core.settings import Settings
from app.tenancy.models import Member, Role
from app.tenancy.repository import list_memberships

router = APIRouter(prefix="/api/auth", tags=["auth"])

SIGN_IN_FAILED = "Email or password is incorrect"
SIGN_IN_THROTTLED = "Too many failed sign-in attempts"
# ASGI servers may leave the client unset (a Unix socket, for example); they share one counter.
_UNKNOWN_CLIENT = Address("unknown", 0)
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


class ThrottledResponse(BaseModel):
    detail: str
    locked: bool = Field(description="True for a lockout; false for a short delay between attempts")
    retry_after_seconds: int = Field(description="Seconds until sign-in can be tried again")


def get_session_store(request: Request) -> SessionStore:
    settings: Settings = request.app.state.settings
    return SessionStore(request.app.state.redis, settings.session_ttl_seconds)


def get_sign_in_throttle(request: Request) -> SignInThrottle:
    return SignInThrottle(
        request.app.state.redis, request.app.state.clock, request.app.state.settings
    )


Db = Annotated[AsyncSession, Depends(get_db)]
Sessions = Annotated[SessionStore, Depends(get_session_store)]
Throttle = Annotated[SignInThrottle, Depends(get_sign_in_throttle)]
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


@router.post(
    "/sign-in",
    responses={
        401: {"model": ErrorResponse, "description": SIGN_IN_FAILED},
        429: {"model": ThrottledResponse, "description": SIGN_IN_THROTTLED},
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
    throttle: Throttle,
    token: SessionToken = None,
) -> SessionResponse | JSONResponse:
    """Signs a Member in. Repeated failures per account or IP are delayed, then locked out."""
    try:
        member = await service.sign_in(
            db,
            throttle,
            request.app.state.clock,
            email=body.email,
            password=body.password,
            ip=(request.client or _UNKNOWN_CLIENT).host,
        )
    except service.SignInThrottledError as throttled:
        refusal = throttled.refusal
        content = ThrottledResponse(
            detail=SIGN_IN_THROTTLED,
            locked=refusal.locked,
            retry_after_seconds=refusal.retry_after_seconds,
        )
        return JSONResponse(
            content.model_dump(),
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={"Retry-After": str(refusal.retry_after_seconds)},
        )
    if member is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, SIGN_IN_FAILED)
    await _start_session(response, request, sessions, member, token)
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
