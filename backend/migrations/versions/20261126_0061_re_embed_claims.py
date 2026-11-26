"""A Re-embed survives interruption (spec 21, ADR-0020): a re-embed job records when it was last
put on queued, the claim of the copy working on it and its last heartbeat, and how many times in
a row it was interrupted with no new Chunks embedded in between.

Running jobs take their start as the time they were queued, with no claim, so the first sweep
sends again every Re-embed left running (and stuck) before this shipped for longer than the
queued-too-long time; it resumes from the Chunks it had not yet done.

Revision ID: 0061_re_embed_claims
Revises: 0060_ingestion_claims
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0061_re_embed_claims"
down_revision: str | None = "0060_ingestion_claims"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("re_embed_jobs", sa.Column("queued_at", sa.DateTime(timezone=True)))
    op.add_column("re_embed_jobs", sa.Column("claim_id", sa.Uuid()))
    op.add_column("re_embed_jobs", sa.Column("heartbeat_at", sa.DateTime(timezone=True)))
    op.add_column(
        "re_embed_jobs",
        sa.Column("interruptions", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("re_embed_jobs", sa.Column("chunks_at_interruption", sa.Integer()))
    op.execute("UPDATE re_embed_jobs SET queued_at = created_at WHERE status = 'running'")


def downgrade() -> None:
    for column in ("chunks_at_interruption", "interruptions", "heartbeat_at", "claim_id"):
        op.drop_column("re_embed_jobs", column)
    op.drop_column("re_embed_jobs", "queued_at")
