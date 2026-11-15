"""Rollout evaluation (spec 14): a Run's kind, ``agent`` (started from the Agent) or ``rollout``
(started by Rollout evaluation, its second side the Live configuration answering with the new
Instructions Version).

Revision ID: 0048_evaluation_run_kind
Revises: 0047_evaluation_run_cost
Create Date: 2026-11-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0048_evaluation_run_kind"
down_revision: str | None = "0047_evaluation_run_cost"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "evaluation_runs",
        sa.Column("kind", sa.String(length=20), server_default="agent", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("evaluation_runs", "kind")
