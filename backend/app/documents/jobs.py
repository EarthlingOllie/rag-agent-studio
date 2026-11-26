"""Ingestion as a job type of the job reliability module (``app.jobs.reliability``, ADR-0020).

Its rows are Documents and staged editions: Queued is queued, Processing is in progress. An
edition whose ingestion stopped writing heartbeats goes back to Queued and its job is sent again;
the restarted ingestion claims it, and a staged edition's Document keeps serving its current
edition meanwhile. Interruptions are counted apart from the automatic retries: the one that
reaches the cap (``INGESTION_MAX_INTERRUPTIONS``) sets the edition Failed with the Failure category
``interrupted`` instead (a Document then loses any Chunks it had; a staged edition's Document keeps
its current edition). A row Queued for an automatic retry records when it is due, so the sweeper
sends it if its message was lost. Both kinds of row are keyed by the Document's ID, which is
what the job is sent with.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import load_settings
from app.documents.limits import interrupted_message
from app.documents.models import Chunk, Document, DocumentStatus, FailureCategory, StagedEdition
from app.jobs.reliability import JobTable, queued_values, released
from app.worker.celery_app import INGEST_TASK
from app.worker.publisher import current_publisher

DOCUMENT_ROWS = JobTable(
    Document,
    Document.id,
    queued=DocumentStatus.QUEUED,
    in_progress=DocumentStatus.PROCESSING,
    retry_at=Document.retry_at,
)
STAGED_ROWS = JobTable(
    StagedEdition,
    StagedEdition.document_id,
    queued=DocumentStatus.QUEUED,
    in_progress=DocumentStatus.PROCESSING,
    retry_at=StagedEdition.retry_at,
)


class IngestionPolicy:
    """What the sweeper does with ingestion's rows."""

    job = INGEST_TASK
    tables: Sequence[JobTable] = (DOCUMENT_ROWS, STAGED_ROWS)

    async def recover(
        self, session: AsyncSession, table: JobTable, row_id: uuid.UUID, now: datetime
    ) -> None:
        """An interrupted ingestion: the edition goes back to Queued, to be ingested again, or,
        at the interruption cap, is Failed as interrupted. The interrupted run doesn't count as
        one of the automatic attempts."""
        cap = load_settings().ingestion_max_interruptions
        row: Document | StagedEdition = await session.get_one(
            table.model, row_id, populate_existing=True
        )
        row.interruption_count += 1
        row.attempt_count = max(row.attempt_count - 1, 0)
        row.updated_at = func.now()
        if row.interruption_count < cap:
            row.status = DocumentStatus.QUEUED
            for column, value in queued_values(now).items():
                setattr(row, column, value)
            return
        row.status = DocumentStatus.FAILED
        row.error_category = FailureCategory.INTERRUPTED
        row.error_message = interrupted_message(row.interruption_count)
        released(row)
        if table is DOCUMENT_ROWS:
            # A Document reprocessed from Ready that fails no longer serves its old Chunks.
            await session.execute(delete(Chunk).where(Chunk.document_id == row_id))

    async def resend(self, row_id: uuid.UUID) -> None:
        await current_publisher().ingest_document(row_id)


INGESTION = IngestionPolicy()
