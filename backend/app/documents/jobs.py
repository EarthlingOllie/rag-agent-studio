"""Ingestion as a job type of the job reliability module (``app.jobs.reliability``, ADR-0020).

Its rows are Documents and staged editions: Queued is queued, Processing is in progress. An
edition whose ingestion stopped writing heartbeats goes back to Queued and its job is sent again;
the restarted ingestion claims it, and a staged edition's Document keeps serving its current
edition meanwhile. Both kinds of row are keyed by the Document's ID, which is what the job is
sent with.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents.models import Document, DocumentStatus, StagedEdition
from app.jobs.reliability import JobTable, queued_values
from app.worker.celery_app import INGEST_TASK
from app.worker.publisher import current_publisher

DOCUMENT_ROWS = JobTable(
    Document, Document.id, queued=DocumentStatus.QUEUED, in_progress=DocumentStatus.PROCESSING
)
STAGED_ROWS = JobTable(
    StagedEdition,
    StagedEdition.document_id,
    queued=DocumentStatus.QUEUED,
    in_progress=DocumentStatus.PROCESSING,
)


class IngestionPolicy:
    """What the sweeper does with ingestion's rows."""

    job = INGEST_TASK
    tables: Sequence[JobTable] = (DOCUMENT_ROWS, STAGED_ROWS)

    async def recover(
        self, session: AsyncSession, table: JobTable, row_id: uuid.UUID, now: datetime
    ) -> None:
        """An interrupted ingestion: the edition goes back to Queued, to be ingested again."""
        await session.execute(
            update(table.model)
            .where(table.key == row_id)
            .values(status=DocumentStatus.QUEUED, updated_at=func.now(), **queued_values(now))
            .execution_options(synchronize_session=False)
        )

    async def resend(self, row_id: uuid.UUID) -> None:
        await current_publisher().ingest_document(row_id)


INGESTION = IngestionPolicy()
