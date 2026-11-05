"""The authentication module: sign up and check credentials.

Session handling (start, resolve, end) lives in ``app.auth.sessions`` and sign-in
protection in ``app.auth.throttle``; the HTTP layer in ``app.auth.api`` puts them together.
"""

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit_service
from app.auth.passwords import hash_password, verify_password
from app.auth.throttle import Lockout, Refusal, SignInThrottle
from app.core.clock import Clock
from app.tenancy.models import Member
from app.tenancy.repository import create_organisation_with_new_owner, list_memberships

logger = logging.getLogger(__name__)

SIGN_IN_LOCKED_OUT = "sign_in.locked_out"


class EmailAlreadyRegisteredError(Exception):
    """Sign-up used an email that already belongs to a Member."""


class SignInThrottledError(Exception):
    """Too many sign-ins failed for this account or IP address; the password wasn't checked."""

    def __init__(self, refusal: Refusal) -> None:
        super().__init__(refusal)
        self.refusal = refusal


def normalise_email(email: str) -> str:
    return email.strip().lower()


async def sign_up(
    session: AsyncSession, *, name: str, email: str, password: str, organisation_name: str
) -> Member:
    """Creates the Member, the Organisation and the Owner membership in one transaction."""
    member = Member(name=name, email=normalise_email(email), password_hash=hash_password(password))
    try:
        async with session.begin():
            await create_organisation_with_new_owner(
                session, organisation_name=organisation_name, owner=member
            )
    except IntegrityError as exc:
        raise EmailAlreadyRegisteredError from exc
    return member


async def sign_in(
    session: AsyncSession,
    throttle: SignInThrottle,
    clock: Clock,
    *,
    email: str,
    password: str,
    ip: str,
) -> Member | None:
    """The Member these credentials belong to, or None. Unknown emails cost the same time.

    Raises ``SignInThrottledError`` while too many recent sign-ins have failed. Failures count
    the same whether or not the email is registered, so throttling reveals nothing either.
    """
    email = normalise_email(email)
    refusal = await throttle.check(email, ip)
    if refusal is not None:
        raise SignInThrottledError(refusal)
    member = await session.scalar(select(Member).where(Member.email == email))
    password_hash = None if member is None else member.password_hash
    # The password is always checked, so unknown emails do the same argon2 work.
    if verify_password(password_hash, password) and member is not None:
        await throttle.record_success(email, ip)
        return member
    lockouts = await throttle.record_failure(email, ip)
    for lockout in lockouts:
        await _record_lockout(session, member, ip, lockout, clock.now())
    return None


async def _record_lockout(
    session: AsyncSession, member: Member | None, ip: str, lockout: Lockout, at: datetime
) -> None:
    """Logs the lockout, and records it in the Audit of each Organisation the Member is in."""
    logger.warning(
        "Sign-in locked out",
        extra={"scope": lockout.scope.value, "ip": ip, "known_account": member is not None},
    )
    if member is None:
        return  # no Organisation to audit it in; the log line is the record
    for membership in await list_memberships(session, member):
        audit_service.record(
            session,
            organisation_id=membership.organisation_id,
            actor_member_id=None,
            action=SIGN_IN_LOCKED_OUT,
            target_type="member",
            target_id=str(member.id),
            before=None,
            after={
                "scope": lockout.scope.value,
                "ip": ip,
                "failures": lockout.failures,
                "locked_until": lockout.locked_until.isoformat(),
            },
            at=at,
        )
    await session.commit()
