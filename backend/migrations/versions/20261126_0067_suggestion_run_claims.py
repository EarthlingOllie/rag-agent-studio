"""Interrupted Suggestion runs (spec 21, ADR-0020): a Suggestion records when it was last put on
Queued, and, while its job gathers, proposes or checks, that job's claim and its last heartbeat. A
failed run records why when its worker stopped before its proposal existed (``failure_reason``,
``interrupted``).

Runs already Queued take their creation as their queued time. Runs already gathering, proposing
or checking get no heartbeat, so the first sweep settles them by the same rule as any other.
Downgrading drops the columns: an interrupted run stays Failed, which the code before this reads
the same way.

Revision ID: 0067_suggestion_run_claims
Revises: 0066_alert_emails
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0067_suggestion_run_claims"
down_revision: str | None = "0066_alert_emails"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("suggestions", sa.Column("failure_reason", sa.String(20), nullable=True))
    op.add_column("suggestions", sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("suggestions", sa.Column("claim_id", sa.Uuid(), nullable=True))
    op.add_column(
        "suggestions", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.execute("UPDATE suggestions SET queued_at = created_at WHERE status = 'queued'")


def downgrade() -> None:
    op.drop_column("suggestions", "heartbeat_at")
    op.drop_column("suggestions", "claim_id")
    op.drop_column("suggestions", "queued_at")
    op.drop_column("suggestions", "failure_reason")
