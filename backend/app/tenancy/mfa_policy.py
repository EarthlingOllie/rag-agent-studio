"""The Require MFA policy: an Owner requires MFA of every Member of their Organisation.

The policy is enforced by ``app.tenancy.policy.RequireRole`` on every Organisation-scoped
route, and by ``app.auth.mfa.Mfa.disable``, which refuses while any of the Member's
Organisations requires MFA. Turning it on needs the Owner to have MFA themselves, so the
change can't lock out the Owner making it.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.auth.mfa import mfa_enabled
from app.tenancy.models import Organisation
from app.tenancy.repository import OrganisationScope

MFA_POLICY_CHANGED = "organisation.mfa_policy_changed"


class OwnerWithoutMfaError(Exception):
    """The Owner asked to require MFA without having turned it on for themselves."""


async def set_require_mfa(
    session: AsyncSession, scope: OrganisationScope, *, require_mfa: bool, now: datetime
) -> Organisation:
    """Turns the policy on or off and records ``organisation.mfa_policy_changed``.

    Setting the value it already has changes and records nothing.
    """
    organisation = (
        await session.scalars(
            select(Organisation).where(Organisation.id == scope.organisation_id).with_for_update()
        )
    ).one()
    if organisation.require_mfa is require_mfa:
        await session.commit()
        return organisation
    if require_mfa and not await mfa_enabled(session, scope.member_id):
        raise OwnerWithoutMfaError
    organisation.require_mfa = require_mfa
    await audit.record(
        session,
        organisation_id=scope.organisation_id,
        actor_id=scope.member_id,
        action=MFA_POLICY_CHANGED,
        target=audit.AuditTarget("organisation", scope.organisation_id),
        before={"require_mfa": not require_mfa},
        after={"require_mfa": require_mfa},
        occurred_at=now,
    )
    await session.commit()
    return organisation
