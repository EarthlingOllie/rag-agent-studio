"""The authentication module: sign up, check credentials, reset and change passwords.

Session handling (start, resolve, end) lives in ``app.auth.sessions``; the HTTP layer in
``app.auth.api`` puts the two together.
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.auth.models import PasswordResetToken
from app.auth.passwords import hash_password, verify_password
from app.mail import templates
from app.mail.port import Mailer
from app.tenancy.models import Member, Membership
from app.tenancy.repository import create_organisation_with_new_owner


class EmailAlreadyRegisteredError(Exception):
    """Sign-up used an email that already belongs to a Member."""


def normalise_email(email: str) -> str:
    return email.strip().lower()


async def sign_up(
    session: AsyncSession, *, name: str, email: str, password: str, organisation_name: str
) -> Member:
    """Creates the Member, the Organisation, the Owner membership and the Audit Event of the
    Organisation being created, in one transaction."""
    member = Member(name=name, email=normalise_email(email), password_hash=hash_password(password))
    async with session.begin():
        # Only the Member's insert can clash with a taken email; any other failure, such as
        # the Audit Event's insert, propagates as itself and still rolls everything back.
        try:
            organisation = await create_organisation_with_new_owner(
                session, organisation_name=organisation_name, owner=member
            )
        except IntegrityError as exc:
            raise EmailAlreadyRegisteredError from exc
        await audit.record(
            session,
            organisation_id=organisation.id,
            actor_id=member.id,
            action="organisation.created",
            target=audit.AuditTarget("organisation", organisation.id),
            after={"name": organisation.name},
        )
    return member


async def authenticate(session: AsyncSession, *, email: str, password: str) -> Member | None:
    """The Member these credentials belong to, or None. Unknown emails cost the same time."""
    member = await session.scalar(select(Member).where(Member.email == normalise_email(email)))
    password_hash = None if member is None else member.password_hash
    if not verify_password(password_hash, password):
        return None
    return member


class InvalidResetTokenError(Exception):
    """The reset token is unknown, already used or expired."""


class WrongPasswordError(Exception):
    """The current password given to change it was wrong."""


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def request_password_reset(
    session: AsyncSession,
    mailer: Mailer,
    *,
    email: str,
    now: datetime,
    valid_for: timedelta,
    studio_url: str,
) -> None:
    """Emails a single-use reset link if the email is registered; otherwise does nothing."""
    member = await session.scalar(select(Member).where(Member.email == normalise_email(email)))
    if member is None:
        return
    token = secrets.token_urlsafe(32)
    session.add(
        PasswordResetToken(
            member_id=member.id, token_hash=_token_hash(token), expires_at=now + valid_for
        )
    )
    await session.commit()
    await mailer.send(
        templates.password_reset(
            to=member.email,
            name=member.name,
            studio_url=studio_url,
            token=token,
            valid_for=valid_for,
        )
    )


async def complete_password_reset(
    session: AsyncSession, *, token: str, password: str, now: datetime
) -> Member:
    """Sets a new password with a reset token, using it up along with the Member's other links.

    The caller ends the Member's sessions once this returns.
    """
    async with session.begin():
        member_id = await session.scalar(
            update(PasswordResetToken)
            .where(
                PasswordResetToken.token_hash == _token_hash(token),
                PasswordResetToken.used_at.is_(None),
                PasswordResetToken.expires_at > now,
            )
            .values(used_at=now)
            .returning(PasswordResetToken.member_id)
        )
        if member_id is None:
            raise InvalidResetTokenError
        await _use_up_reset_links(session, member_id, now)
        member = await session.get_one(Member, member_id)
        member.password_hash = hash_password(password)
        await _record_security_event(session, member, "member.password_reset", now)
    return member


async def _record_security_event(
    session: AsyncSession, member: Member, action: str, now: datetime
) -> None:
    """Records an Audit Event about the Member in every Organisation they belong to."""
    organisation_ids = await session.scalars(
        select(Membership.organisation_id).where(Membership.member_id == member.id)
    )
    for organisation_id in organisation_ids:
        await audit.record(
            session,
            organisation_id=organisation_id,
            actor_id=member.id,
            action=action,
            target=audit.AuditTarget("member", member.id),
            occurred_at=now,
        )


async def _use_up_reset_links(session: AsyncSession, member_id: uuid.UUID, now: datetime) -> None:
    await session.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.member_id == member_id, PasswordResetToken.used_at.is_(None))
        .values(used_at=now)
    )


async def change_password(
    session: AsyncSession,
    member: Member,
    *,
    current_password: str,
    new_password: str,
    now: datetime,
) -> None:
    """Replaces the password after checking the current one. Outstanding reset links stop working.

    The caller ends the Member's other sessions once this returns.
    """
    if not verify_password(member.password_hash, current_password):
        raise WrongPasswordError
    member.password_hash = hash_password(new_password)
    await _use_up_reset_links(session, member.id, now)
    await _record_security_event(session, member, "member.password_changed", now)
    await session.commit()


async def rename(session: AsyncSession, member: Member, *, name: str) -> None:
    member.name = name
    await session.commit()
