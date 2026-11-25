"""Live Verdicts are Purged with their Message (spec 15): the purged-at stamp of a Live Verdict
whose reasons the Purge cleared.

Revision ID: 0050_live_verdicts_purged_at
Revises: 0049_live_verdicts
Create Date: 2026-11-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0050_live_verdicts_purged_at"
down_revision: str | None = "0049_live_verdicts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "live_verdicts", sa.Column("purged_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("live_verdicts", "purged_at")
