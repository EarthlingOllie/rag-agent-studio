"""Account routes: forgotten-password reset, and the signed-in Member's Profile."""

import logging
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, StringConstraints
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth import service
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
from app.core.clock import Clock, get_clock
from app.core.settings import Settings
from app.mail.port import Mailer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

RESET_ACCEPTED = "If that email is registered, a reset link is on its way."
INVALID_RESET_LINK = "This reset link is invalid or has expired."
WRONG_CURRENT_PASSWORD = "Current password is incorrect"  # noqa: S105 (a message)

ClockDep = Annotated[Clock, Depends(get_clock)]


class PasswordResetRequest(BaseModel):
    email: Email


class PasswordResetAccepted(BaseModel):
    detail: str


class CompletePasswordResetRequest(BaseModel):
    token: Annotated[str, StringConstraints(min_length=1, max_length=256)]
    password: Password


class UpdateProfileRequest(BaseModel):
    name: Name


class ChangePasswordRequest(BaseModel):
    current_password: Annotated[str, StringConstraints(max_length=256)]
    new_password: Password


async def _send_reset_link(
    sessionmaker: async_sessionmaker[AsyncSession],
    mailer: Mailer,
    clock: Clock,
    settings: Settings,
    email: str,
) -> None:
    """Runs after the response is sent, so the answer can't hint whether the email exists."""
    try:
        async with sessionmaker() as session:
            await service.request_password_reset(
                session,
                mailer,
                email=email,
                now=clock.now(),
                valid_for=timedelta(seconds=settings.password_reset_ttl_seconds),
                studio_url=str(settings.studio_url),
            )
    except Exception:
        logger.exception("Sending a password reset email failed")


@router.post(
    "/password-reset",
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="requestPasswordReset",
)
async def request_password_reset(
    body: PasswordResetRequest, request: Request, background: BackgroundTasks, clock: ClockDep
) -> PasswordResetAccepted:
    """Emails a reset link if the email is registered. The answer is the same either way."""
    state = request.app.state
    background.add_task(
        _send_reset_link, state.sessionmaker, state.mailer, clock, state.settings, body.email
    )
    return PasswordResetAccepted(detail=RESET_ACCEPTED)


@router.post(
    "/password-reset/complete",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={400: {"model": ErrorResponse, "description": INVALID_RESET_LINK}},
    operation_id="completePasswordReset",
)
async def complete_password_reset(
    body: CompletePasswordResetRequest, db: Db, sessions: Sessions, clock: ClockDep
) -> None:
    """Sets a new password from an emailed link, and signs the Member out everywhere."""
    try:
        member = await service.complete_password_reset(
            db, token=body.token, password=body.password, now=clock.now()
        )
    except service.InvalidResetTokenError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, INVALID_RESET_LINK) from None
    await sessions.delete_all(member.id)


@router.patch("/me", operation_id="updateProfile")
async def update_profile(
    body: UpdateProfileRequest, member: CurrentMember, request: Request, db: Db
) -> SessionResponse:
    """Edits the signed-in Member's Profile."""
    await service.rename(db, member, name=body.name)
    return await session_response(request, db, member)


@router.post(
    "/me/password",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={400: {"model": ErrorResponse, "description": WRONG_CURRENT_PASSWORD}},
    operation_id="changePassword",
)
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    response: Response,
    member: CurrentMember,
    db: Db,
    sessions: Sessions,
    clock: ClockDep,
    token: SessionToken = None,
) -> None:
    """Changes the password. Other sessions end; this one continues under a new token."""
    try:
        await service.change_password(
            db,
            member,
            current_password=body.current_password,
            new_password=body.new_password,
            now=clock.now(),
        )
    except service.WrongPasswordError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, WRONG_CURRENT_PASSWORD) from None
    await sessions.delete_all(member.id)
    await start_session(response, request, sessions, member, token)
