"""The authentication module: sign up and check credentials.

Session handling (start, resolve, end) lives in ``app.auth.sessions``; the HTTP layer in
``app.auth.api`` puts the two together.
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.auth.passwords import hash_password, verify_password
from app.tenancy.models import Member
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
