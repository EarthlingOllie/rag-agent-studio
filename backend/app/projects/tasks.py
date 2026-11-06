"""The permanent-deletion cascade, a Celery task. An Owner's request enqueues it once the
Project is archived and its name typed; the task deletes the Project's rows, then its stored
objects."""

import asyncio
import uuid
from datetime import datetime

from app.core.db import create_engine, create_sessionmaker
from app.core.settings import load_settings
from app.documents.ports import current_ports
from app.projects import service
from app.worker.celery_app import celery_app

DELETE_PROJECT_TASK = "projects.delete"


async def _delete(project_id: uuid.UUID, actor_id: uuid.UUID, requested_at: datetime) -> None:
    engine = create_engine(load_settings())
    try:
        async with create_sessionmaker(engine)() as session:
            prefix = await service.delete_project(
                session, project_id, actor_id=actor_id, requested_at=requested_at
            )
    finally:
        await engine.dispose()
    if prefix is not None:
        await current_ports().object_store.delete_prefix(prefix)


@celery_app.task(name=DELETE_PROJECT_TASK)
def delete_project(project_id: str, actor_id: str, requested_at: str) -> None:
    """Permanently deletes an archived Project: first, in one transaction, its rows (Documents,
    Chunks, Tags, Agents, Conversations...) with the ``project.deleted`` Audit Event, so it
    stops existing at once; then every object stored under the Project's prefix (originals,
    converted markdown, unconfirmed uploads). A Project restored in the meantime is left alone.
    Running it again is safe: a deleted Project is simply not found."""
    asyncio.run(
        _delete(uuid.UUID(project_id), uuid.UUID(actor_id), datetime.fromisoformat(requested_at))
    )


async def enqueue_deletion(
    project_id: uuid.UUID, *, actor_id: uuid.UUID, requested_at: datetime
) -> None:
    """Sends the task from a thread: sending blocks on the broker, and in eager mode (tests)
    the task itself runs there, with its own event loop."""
    await asyncio.to_thread(
        delete_project.delay, str(project_id), str(actor_id), requested_at.isoformat()
    )
