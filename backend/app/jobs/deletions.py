"""The deletions table (ADR-0020): stored objects nothing refers to any more, deleted later.

Object deletions have no row of their own, so the transaction that removes the last reference to
some stored objects (a deleted Document, a replaced or discarded edition, a deleted Project) also
writes their keys, or a prefix, here (``schedule``). After it commits, the object-deletion job is
sent; it carries no keys, and drains the table (``drain``), as does every sweep. Each entry is
deleted from storage and only then removed, so a worker that dies in between leaves the entry for
the next drain. Deleting objects that are already gone is not an error, so that is safe twice.
"""

import logging
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.jobs.models import ObjectDeletion
from app.storage.port import ObjectStore

logger = logging.getLogger(__name__)

# How many entries one drain looks at; whatever is left waits for the next drain.
DRAIN_BATCH = 1000


def schedule(session: AsyncSession, keys: Iterable[str], *, prefix: bool = False) -> None:
    """Writes the keys (or, with ``prefix``, key prefixes) to the deletions table, in the
    caller's transaction."""
    session.add_all(ObjectDeletion(key=key, prefix=prefix) for key in keys)


async def drain(sessionmaker: async_sessionmaker[AsyncSession], store: ObjectStore) -> int:
    """Deletes what the deletions table holds, one entry per transaction: the objects, then the
    row. An entry another drain is working on is skipped; one whose delete fails is logged and
    kept for the next drain. Returns how many entries were deleted."""
    async with sessionmaker() as session:
        ids = (
            await session.scalars(
                select(ObjectDeletion.id).order_by(ObjectDeletion.created_at).limit(DRAIN_BATCH)
            )
        ).all()
    deleted = 0
    for deletion_id in ids:
        try:
            async with sessionmaker() as session, session.begin():
                entry = await session.scalar(
                    select(ObjectDeletion)
                    .where(ObjectDeletion.id == deletion_id)
                    .with_for_update(skip_locked=True)
                )
                if entry is None:
                    continue
                if entry.prefix:
                    await store.delete_prefix(entry.key)
                else:
                    await store.delete(entry.key)
                await session.delete(entry)
            deleted += 1
        except Exception:
            logger.exception(
                "Deleting stored objects failed; the entry is kept for the next drain",
                extra={"deletion_id": str(deletion_id)},
            )
    return deleted
