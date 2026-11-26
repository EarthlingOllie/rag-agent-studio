"""The permanent-deletion cascade, a Celery task. An Owner's request marks the archived Project
Deleting and sends it; the sweeper runs the same cascade for a Project still Deleting, so a lost
message or a dead worker never leaves it half deleted (spec 21, ADR-0020)."""

import asyncio
import uuid

from app.core.db import create_engine, create_sessionmaker
from app.core.settings import load_settings
from app.documents.ports import current_ports
from app.jobs import deletions
from app.projects import service
from app.worker.celery_app import DELETE_PROJECT_TASK, celery_app
from app.worker.publisher import current_publisher


async def _delete(project_id: uuid.UUID) -> None:
    engine = create_engine(load_settings())
    sessionmaker = create_sessionmaker(engine)
    try:
        async with sessionmaker() as session:
            await service.delete_project(session, project_id)
        await deletions.drain(sessionmaker, current_ports().object_store)
    finally:
        await engine.dispose()


@celery_app.task(name=DELETE_PROJECT_TASK, ignore_result=True)
def delete_project(project_id: str, *sent_before: str) -> None:
    """Permanently deletes a Deleting Project: in one transaction, its rows (Documents, Chunks,
    Tags, Agents, Conversations...) with the ``project.deleted`` Audit Event, and its storage
    prefix written to the deletions table; then drains the deletions table, removing every
    object stored under the prefix (originals, converted markdown, unconfirmed uploads).

    The message carries only the Project: who asked, and when, are on its row.
    ``sent_before`` takes the requester and time that messages sent before the row held them
    carry; they are ignored. Running it again is safe: a deleted Project is simply not found."""
    del sent_before
    asyncio.run(_delete(uuid.UUID(project_id)))


async def enqueue_deletion(project_id: uuid.UUID) -> None:
    """Sends the Project deletion job through the Job publisher, once the deleting mark is
    committed."""
    await current_publisher().delete_project(project_id)
