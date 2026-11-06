"""Erasing a whole Organisation: every row it owns, its Audit Events and its stored files.

Only ``make seed-reset`` erases an Organisation (the demo one); the Studio has no way to
delete Organisations. Tenant tables cascade from ``organisations``. Audit Events are
append-only, so the transaction first sets ``app.erasing_organisation``, the one exception
their trigger allows (migration ``0023_erase_organisation``).
"""

import secrets
import uuid

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEvent
from app.auth.passwords import hash_password
from app.documents.models import Document, StagedEdition
from app.documents.pipeline import stored_keys
from app.storage.port import ObjectStore
from app.tenancy.models import Member, Organisation


async def erase_organisation(
    session: AsyncSession, store: ObjectStore, organisation_id: uuid.UUID
) -> None:
    """Deletes the Organisation and everything it owns, then its Documents' stored files."""
    keys = [
        key
        for model in (Document, StagedEdition)
        for object_key in await session.scalars(
            select(model.object_key).where(model.organisation_id == organisation_id)
        )
        for key in stored_keys(object_key)
    ]
    await session.execute(
        text("SELECT set_config('app.erasing_organisation', :id, true)"),
        {"id": str(organisation_id)},
    )
    await session.execute(delete(AuditEvent).where(AuditEvent.organisation_id == organisation_id))
    await session.execute(delete(Organisation).where(Organisation.id == organisation_id))
    await session.commit()
    for key in keys:
        await store.delete(key)


async def erase_member(session: AsyncSession, member_id: uuid.UUID) -> None:
    """Removes an account that belongs to no Organisation any more: their sessions stop working
    and their email can sign up again.

    An account that other Organisations' Audit Events name as the actor can't be deleted (those
    events are kept), so it is retired instead: its email becomes an unusable placeholder and
    its password a random one nobody knows."""
    named = await session.scalar(
        select(AuditEvent.id).where(AuditEvent.actor_id == member_id).limit(1)
    )
    if named is None:
        await session.execute(delete(Member).where(Member.id == member_id))
    else:
        member = await session.get_one(Member, member_id)
        member.email = f"retired-{member_id}@retired.invalid"
        member.password_hash = hash_password(secrets.token_urlsafe(32))
    await session.commit()
