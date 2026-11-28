"""Helpers for the tests of the job sweeper (ADR-0020)."""

from fastapi import FastAPI
from sqlalchemy import update

from app.alert_emails.models import AlertEmail
from app.documents.models import Document, DocumentStatus, StagedEdition
from app.evaluation.models import EvaluationRun, LiveStatus, LiveVerdict, RunStatus
from app.projects.models import Project
from app.re_embedding.models import ReEmbedJob, ReEmbedStatus
from app.suggestions.models import IN_PROGRESS as SUGGESTIONS_IN_PROGRESS
from app.suggestions.models import Suggestion, SuggestionStatus


async def settle_jobs_in_flight(app: FastAPI) -> None:
    """Settles every job row earlier tests on this database left in flight, so a sweep then sees
    only the calling test's own rows: Documents and replacements Queued or Processing as Failed,
    Evaluation Runs Queued or Running as cancelled, Suggestion runs in progress as cancelled,
    Live Verdicts Pending as Errors, running Re-embeds as Failed, alert emails not yet sent as
    sent, and Projects Deleting as no longer asked to be deleted (they stay archived)."""
    in_flight = (DocumentStatus.QUEUED, DocumentStatus.PROCESSING)
    async with app.state.sessionmaker() as session, session.begin():
        for model in (Document, StagedEdition):
            await session.execute(
                update(model)
                .where(model.status.in_(in_flight))
                .values(status=DocumentStatus.FAILED, claim_id=None, heartbeat_at=None)
            )
        await session.execute(
            update(EvaluationRun)
            .where(EvaluationRun.status.in_([RunStatus.QUEUED, RunStatus.RUNNING]))
            .values(status=RunStatus.CANCELLED, claim_id=None, heartbeat_at=None)
        )
        await session.execute(
            update(Suggestion)
            .where(Suggestion.status.in_(SUGGESTIONS_IN_PROGRESS))
            .values(status=SuggestionStatus.CANCELLED, claim_id=None, heartbeat_at=None)
        )
        await session.execute(
            update(LiveVerdict)
            .where(LiveVerdict.status == LiveStatus.PENDING)
            .values(status=LiveStatus.ERROR)
        )
        await session.execute(
            update(ReEmbedJob)
            .where(ReEmbedJob.status == ReEmbedStatus.RUNNING)
            .values(status=ReEmbedStatus.FAILED, claim_id=None, heartbeat_at=None)
        )
        await session.execute(
            update(AlertEmail)
            .where(AlertEmail.sent_at.is_(None))
            .values(sent_at=AlertEmail.raised_at)
        )
        await session.execute(
            update(Project)
            .where(Project.deletion_requested_at.is_not(None))
            .values(deletion_requested_at=None, deletion_requested_by=None)
        )
