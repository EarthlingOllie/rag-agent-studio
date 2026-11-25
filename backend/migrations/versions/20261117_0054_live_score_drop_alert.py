"""Live score drop alert (spec 15): each Agent's alert flag, beside the Budget alert and Block
rate alert flags, and the Live Version it was raised against.

Revision ID: 0054_live_score_drop_alert
Revises: 0053_suggestions
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0054_live_score_drop_alert"
down_revision: str | None = "0053_suggestions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agents", sa.Column("live_score_drop_alert_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("agents", sa.Column("live_score_drop_version_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_agents_live_score_drop_version",
        "agents",
        "agent_versions",
        ["live_score_drop_version_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_agents_live_score_drop_version", "agents", type_="foreignkey")
    op.drop_column("agents", "live_score_drop_version_id")
    op.drop_column("agents", "live_score_drop_alert_at")
