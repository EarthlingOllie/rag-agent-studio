"""Invites: Owners invite people to their Organisation, and the invited person joins.

An Invite is addressed to one email, with a role. Its link carries a random token, of which
only the SHA-256 is stored. The link works once (accepting uses it up), until it expires, and
not after an Owner revokes the Invite. Renewing a pending Invite replaces its token, so an
Owner can always copy a working link even though the old one can't be shown again.
"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.auth.passwords import hash_password
from app.auth.service import EmailAlreadyRegisteredError, normalise_email
from app.tenancy.models import Invite, Member, Membership, Organisation, Role
from app.tenancy.repository import OrganisationScope


class AlreadyAMemberError(Exception):
    """The email already belongs to a Member of the Organisation."""


class PendingInviteExistsError(Exception):
    """The email already has a pending Invite to the Organisation."""


class InviteNotFoundError(Exception):
    """No pending Invite with that ID in the Organisation."""


class InvalidInviteError(Exception):
    """The invite token is unknown, already used, revoked or expired."""


class InviteForAnotherEmailError(Exception):
    """The signed-in Member's email isn't the one the Invite is addressed to."""

    def __init__(self, invited_email: str) -> None:
        super().__init__(invited_email)
        self.invited_email = invited_email


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _new_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    return token, _token_hash(token)


def _invite_values(invite: Invite) -> dict[str, str]:
    return {"email": invite.email, "role": invite.role.value}


@dataclass(frozen=True)
class IssuedInvite:
    """A pending Invite and the token of its link, which is never stored."""

    invite: Invite
    token: str


async def create_invite(
    session: AsyncSession,
    scope: OrganisationScope,
    *,
    email: str,
    role: Role,
    now: datetime,
    valid_for: timedelta,
) -> IssuedInvite:
    """Creates a pending Invite and records ``invite.created``. The caller sends the email."""
    email = normalise_email(email)
    already_member = await session.scalar(
        select(Membership.id)
        .join(Member, Member.id == Membership.member_id)
        .where(Membership.organisation_id == scope.organisation_id, Member.email == email)
    )
    if already_member is not None:
        raise AlreadyAMemberError
    token, token_hash = _new_token()
    invite = Invite(
        organisation_id=scope.organisation_id,
        email=email,
        role=role,
        token_hash=token_hash,
        invited_by_id=scope.member_id,
        expires_at=now + valid_for,
    )
    session.add(invite)
    try:
        await session.flush()
    except IntegrityError as exc:
        # The only constraint a new Invite can break is one pending Invite per email.
        raise PendingInviteExistsError from exc
    await audit.record(
        session,
        organisation_id=scope.organisation_id,
        actor_id=scope.member_id,
        action="invite.created",
        target=audit.AuditTarget("invite", invite.id),
        after=_invite_values(invite),
        occurred_at=now,
    )
    await session.commit()
    return IssuedInvite(invite, token)


@dataclass(frozen=True)
class PendingInvite:
    invite: Invite
    invited_by: Member


async def list_pending(session: AsyncSession, scope: OrganisationScope) -> list[PendingInvite]:
    """The Organisation's Invites that are neither accepted nor revoked, newest first.

    Expired ones are included, so an Owner can renew or revoke them.
    """
    rows = await session.execute(
        select(Invite, Member)
        .join(Member, Member.id == Invite.invited_by_id)
        .where(
            Invite.organisation_id == scope.organisation_id,
            Invite.accepted_at.is_(None),
            Invite.revoked_at.is_(None),
        )
        .order_by(Invite.created_at.desc(), Invite.email)
    )
    return [PendingInvite(invite, member) for invite, member in rows]


async def _pending_for_update(
    session: AsyncSession, scope: OrganisationScope, invite_id: uuid.UUID
) -> Invite:
    invite = await session.scalar(
        select(Invite)
        .where(
            Invite.id == invite_id,
            Invite.organisation_id == scope.organisation_id,
            Invite.accepted_at.is_(None),
            Invite.revoked_at.is_(None),
        )
        .with_for_update()
    )
    if invite is None:
        raise InviteNotFoundError
    return invite


async def revoke_invite(
    session: AsyncSession, scope: OrganisationScope, invite_id: uuid.UUID, *, now: datetime
) -> None:
    """Revokes a pending Invite, so its link stops working, and records ``invite.revoked``."""
    invite = await _pending_for_update(session, scope, invite_id)
    invite.revoked_at = now
    await audit.record(
        session,
        organisation_id=scope.organisation_id,
        actor_id=scope.member_id,
        action="invite.revoked",
        target=audit.AuditTarget("invite", invite.id),
        before=_invite_values(invite),
        occurred_at=now,
    )
    await session.commit()


async def renew_invite(
    session: AsyncSession,
    scope: OrganisationScope,
    invite_id: uuid.UUID,
    *,
    now: datetime,
    valid_for: timedelta,
) -> IssuedInvite:
    """Gives a pending Invite a new link and expiry; the previous link stops working."""
    invite = await _pending_for_update(session, scope, invite_id)
    token, invite.token_hash = _new_token()
    invite.expires_at = now + valid_for
    await audit.record(
        session,
        organisation_id=scope.organisation_id,
        actor_id=scope.member_id,
        action="invite.renewed",
        target=audit.AuditTarget("invite", invite.id),
        after=_invite_values(invite),
        occurred_at=now,
    )
    await session.commit()
    return IssuedInvite(invite, token)


@dataclass(frozen=True)
class InvitePreview:
    """What the invited person sees before accepting."""

    organisation_id: uuid.UUID
    organisation_name: str
    email: str
    role: Role
    invited_by_name: str
    account_exists: bool


async def _usable_invite(
    session: AsyncSession, token: str, now: datetime, *, lock: bool = False
) -> Invite:
    query = select(Invite).where(
        Invite.token_hash == _token_hash(token),
        Invite.accepted_at.is_(None),
        Invite.revoked_at.is_(None),
        Invite.expires_at > now,
    )
    invite = await session.scalar(query.with_for_update() if lock else query)
    if invite is None:
        raise InvalidInviteError
    return invite


async def preview_invite(session: AsyncSession, *, token: str, now: datetime) -> InvitePreview:
    invite = await _usable_invite(session, token, now)
    organisation = await session.get_one(Organisation, invite.organisation_id)
    inviter = await session.get_one(Member, invite.invited_by_id)
    account = await session.scalar(select(Member.id).where(Member.email == invite.email))
    return InvitePreview(
        organisation_id=organisation.id,
        organisation_name=organisation.name,
        email=invite.email,
        role=invite.role,
        invited_by_name=inviter.name,
        account_exists=account is not None,
    )


async def _join(session: AsyncSession, invite: Invite, member: Member, now: datetime) -> None:
    """Uses up the Invite, adds the membership and records ``invite.accepted``."""
    invite.accepted_at = now
    invite.accepted_by_id = member.id
    session.add(
        Membership(organisation_id=invite.organisation_id, member_id=member.id, role=invite.role)
    )
    await session.flush()
    await audit.record(
        session,
        organisation_id=invite.organisation_id,
        actor_id=member.id,
        action="invite.accepted",
        target=audit.AuditTarget("invite", invite.id),
        after={**_invite_values(invite), "member_id": str(member.id)},
        occurred_at=now,
    )


async def accept_invite(
    session: AsyncSession, member: Member, *, token: str, now: datetime
) -> uuid.UUID:
    """Adds the signed-in Member to the invite's Organisation; returns the Organisation's ID."""
    invite = await _usable_invite(session, token, now, lock=True)
    if invite.email != member.email:
        raise InviteForAnotherEmailError(invite.email)
    # The Member can't belong already: an Invite is refused for a Member's email, and only
    # one Invite per email is pending.
    await _join(session, invite, member, now)
    organisation_id = invite.organisation_id
    await session.commit()
    return organisation_id


async def accept_invite_as_new_member(
    session: AsyncSession, *, token: str, name: str, password: str, now: datetime
) -> Member:
    """Creates an account for the invited email and adds it to the Organisation, in one go."""
    password_hash = hash_password(password)
    invite = await _usable_invite(session, token, now, lock=True)
    member = Member(name=name, email=invite.email, password_hash=password_hash)
    session.add(member)
    try:
        await session.flush()
    except IntegrityError as exc:
        # The only constraint a new Member can break is the unique email.
        raise EmailAlreadyRegisteredError from exc
    await _join(session, invite, member, now)
    await session.commit()
    return member
