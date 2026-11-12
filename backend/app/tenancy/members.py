"""Members of an Organisation: listing, role changes, removal and leaving.

The last-Owner invariant lives here: an Organisation always keeps at least one Owner, so
demoting, removing or leaving as its last Owner is refused. Each change locks the
Organisation's row first, so two concurrent changes can't both remove "the other" Owner.
Access is resolved from memberships on every request, so a removed Member loses access to the
Organisation at once. An Owner who is demoted, removed or leaves loses their pending Invites
too (they are revoked), so they can't use one to come back as an Owner.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.tenancy import invites
from app.tenancy.models import Member, Membership, Organisation, Role
from app.tenancy.repository import OrganisationScope


class MemberNotFoundError(Exception):
    """No Member with that ID in the Organisation."""


class LastOwnerError(Exception):
    """The change would leave the Organisation without an Owner."""


@dataclass(frozen=True)
class OrganisationMember:
    member: Member
    role: Role
    joined_at: datetime


async def list_members(session: AsyncSession, scope: OrganisationScope) -> list[OrganisationMember]:
    """Every Member of the Organisation with their role, in the order they joined."""
    rows = await session.execute(
        select(Member, Membership.role, Membership.created_at)
        .join(Membership, Membership.member_id == Member.id)
        .where(Membership.organisation_id == scope.organisation_id)
        .order_by(Membership.created_at, Member.name)
    )
    return [OrganisationMember(member, role, joined_at) for member, role, joined_at in rows]


async def _locked_membership(
    session: AsyncSession, scope: OrganisationScope, member_id: uuid.UUID
) -> tuple[Membership, Member]:
    """The Member's membership, after locking the Organisation against concurrent changes."""
    await session.execute(
        select(Organisation.id).where(Organisation.id == scope.organisation_id).with_for_update()
    )
    row = (
        await session.execute(
            select(Membership, Member)
            .join(Member, Member.id == Membership.member_id)
            .where(
                Membership.organisation_id == scope.organisation_id,
                Membership.member_id == member_id,
            )
        )
    ).one_or_none()
    if row is None:
        raise MemberNotFoundError
    membership, member = row
    return membership, member


async def _refuse_if_last_owner(session: AsyncSession, membership: Membership) -> None:
    if membership.role is not Role.OWNER:
        return
    owners = await session.scalar(
        select(func.count()).where(
            Membership.organisation_id == membership.organisation_id,
            Membership.role == Role.OWNER,
        )
    )
    if owners == 1:
        raise LastOwnerError


async def change_role(
    session: AsyncSession,
    scope: OrganisationScope,
    member_id: uuid.UUID,
    *,
    role: Role,
    now: datetime,
) -> OrganisationMember:
    """Sets the Member's role and records ``member.role_changed``; the same role is a no-op."""
    membership, member = await _locked_membership(session, scope, member_id)
    if membership.role is not role:
        if role is not Role.OWNER:
            await _refuse_if_last_owner(session, membership)
        before = membership.role
        membership.role = role
        if before is Role.OWNER:
            await invites.revoke_invites_from(
                session, scope.organisation_id, member.id, actor_id=scope.member_id, now=now
            )
        await audit.record(
            session,
            organisation_id=scope.organisation_id,
            actor_id=scope.member_id,
            action="member.role_changed",
            target=audit.AuditTarget("member", member.id),
            before={"email": member.email, "role": before.value},
            after={"email": member.email, "role": role.value},
            occurred_at=now,
        )
    joined_at = membership.created_at
    await session.commit()
    return OrganisationMember(member, role, joined_at)


async def _end_membership(
    session: AsyncSession,
    scope: OrganisationScope,
    member_id: uuid.UUID,
    *,
    action: str,
    now: datetime,
) -> None:
    membership, member = await _locked_membership(session, scope, member_id)
    await _refuse_if_last_owner(session, membership)
    await session.delete(membership)
    if membership.role is Role.OWNER:
        await invites.revoke_invites_from(
            session, scope.organisation_id, member.id, actor_id=scope.member_id, now=now
        )
    await audit.record(
        session,
        organisation_id=scope.organisation_id,
        actor_id=scope.member_id,
        action=action,
        target=audit.AuditTarget("member", member.id),
        before={"email": member.email, "name": member.name, "role": membership.role.value},
        occurred_at=now,
    )
    await session.commit()


async def remove_member(
    session: AsyncSession, scope: OrganisationScope, member_id: uuid.UUID, *, now: datetime
) -> None:
    """Removes the Member from the Organisation and records ``member.removed``."""
    await _end_membership(session, scope, member_id, action="member.removed", now=now)


async def leave(session: AsyncSession, scope: OrganisationScope, *, now: datetime) -> None:
    """The signed-in Member leaves the Organisation; records ``member.left``."""
    await _end_membership(session, scope, scope.member_id, action="member.left", now=now)
