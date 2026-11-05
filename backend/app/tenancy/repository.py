"""Tenant-scoped data access.

Anything below the platform level is read through functions that require an
``OrganisationScope``. Routes get a scope only from ``resolve_scope`` (through the
``organisation_scope`` dependency), which returns one only when the Member belongs to the
Organisation, so there is no unscoped path to tenant data.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.tenancy.models import Member, Membership, Organisation, Role


@dataclass(frozen=True)
class OrganisationScope:
    """Proof that ``member_id`` is a Member of ``organisation_id`` with ``role``."""

    organisation_id: uuid.UUID
    member_id: uuid.UUID
    role: Role


async def resolve_scope(
    session: AsyncSession, *, member_id: uuid.UUID, organisation_id: uuid.UUID
) -> OrganisationScope | None:
    """The Member's scope in the Organisation, or None if they don't belong to it."""
    role = await session.scalar(
        select(Membership.role).where(
            Membership.member_id == member_id, Membership.organisation_id == organisation_id
        )
    )
    if role is None:
        return None
    return OrganisationScope(organisation_id, member_id, role)


async def get_organisation(session: AsyncSession, scope: OrganisationScope) -> Organisation:
    organisation = await session.get_one(Organisation, scope.organisation_id)
    return organisation


@dataclass(frozen=True)
class MembershipSummary:
    organisation_id: uuid.UUID
    organisation_name: str
    role: Role
    require_mfa: bool


async def list_memberships(session: AsyncSession, member: Member) -> list[MembershipSummary]:
    """The Organisations a Member belongs to (platform level: it is the Member's own view)."""
    rows = await session.execute(
        select(Organisation.id, Organisation.name, Membership.role, Organisation.require_mfa)
        .join(Membership, Membership.organisation_id == Organisation.id)
        .where(Membership.member_id == member.id)
        .order_by(Membership.created_at, Organisation.name)
    )
    return [MembershipSummary(*row) for row in rows]


async def create_organisation_with_new_owner(
    session: AsyncSession, *, organisation_name: str, owner: Member
) -> Organisation:
    """Adds a new Organisation, its first Member and their Owner membership to the transaction.

    The Organisation is written first, so a failure adding the Member (a taken email) must
    roll it back with everything else.
    """
    organisation = Organisation(name=organisation_name)
    session.add(organisation)
    await session.flush()
    session.add(owner)
    await session.flush()
    session.add(Membership(organisation_id=organisation.id, member_id=owner.id, role=Role.OWNER))
    await session.flush()
    return organisation
