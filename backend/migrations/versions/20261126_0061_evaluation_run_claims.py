"""Interrupted Evaluation Runs (spec 21, ADR-0020): an Evaluation Run records when it was last put
on Queued, and, while Running, the claim of the job answering it and its last heartbeat. A Run
whose heartbeat stops ends ``interrupted``, a new finished status (``status`` is a plain string,
so the status needs no schema change).

Runs already Queued take their creation as their queued time. Runs already Running get no
heartbeat, so the first sweep ends them Interrupted by the same rule as any other. Downgrading
turns Interrupted Runs into Cancelled ones, which the code before this reads the same way.

Revision ID: 0061_evaluation_run_claims
Revises: 0060_ingestion_claims
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0061_evaluation_run_claims"
down_revision: str | None = "0060_ingestion_claims"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "evaluation_runs", sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("evaluation_runs", sa.Column("claim_id", sa.Uuid(), nullable=True))
    op.add_column(
        "evaluation_runs", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.execute("UPDATE evaluation_runs SET queued_at = created_at WHERE status = 'queued'")


def downgrade() -> None:
    op.execute("UPDATE evaluation_runs SET status = 'cancelled' WHERE status = 'interrupted'")
    op.drop_column("evaluation_runs", "heartbeat_at")
    op.drop_column("evaluation_runs", "claim_id")
    op.drop_column("evaluation_runs", "queued_at")
