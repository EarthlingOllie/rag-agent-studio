"""The Calls failing alert (spec 20): when the voice layer couldn't start one of the Agent's
Calls. Saving its Call settings, or the next Call that starts, clears it.

Revision ID: 0064_calls_failing
Revises: 0063_playground_calls
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0064_calls_failing"
down_revision: str | None = "0063_playground_calls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agents", sa.Column("calls_failing_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("agents", "calls_failing_at")
