"""Lost Live Verdicts (spec 21, ADR-0020): a Live Verdict records when the sweeper last sent its
judging job again, how many times it has, and the claim of the copy of the job judging it.

Live Verdicts already Pending keep no send time and no claim, so the first sweep takes them as
Pending since they were created and sends them again by the same rules as any other.

Revision ID: 0072_live_verdict_claims
Revises: 0071_evaluation_run_claims
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0072_live_verdict_claims"
down_revision: str | None = "0071_evaluation_run_claims"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "live_verdicts", sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "live_verdicts",
        sa.Column("resends", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("live_verdicts", sa.Column("claim_id", sa.Uuid(), nullable=True))


def downgrade() -> None:
    op.drop_column("live_verdicts", "claim_id")
    op.drop_column("live_verdicts", "resends")
    op.drop_column("live_verdicts", "queued_at")
