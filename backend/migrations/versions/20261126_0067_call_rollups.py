"""Calls and Call minutes in the daily rollups (spec 20): each Agent Version's Visitor Calls that
ended on the UTC day, and their minutes. Rollups already made are filled in from the Calls.

Revision ID: 0067_call_rollups
Revises: 0066_interrupted_turn
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0067_call_rollups"
down_revision: str | None = "0066_interrupted_turn"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for column in ("calls", "call_minutes"):
        op.add_column(
            "usage_daily",
            sa.Column(column, sa.Integer(), server_default=sa.text("0"), nullable=False),
        )
    op.execute(
        """
        UPDATE usage_daily AS u
        SET calls = c.calls, call_minutes = c.call_minutes
        FROM (
            SELECT calls.agent_version_id,
                   (calls.ended_at AT TIME ZONE 'UTC')::date AS day,
                   count(*) AS calls,
                   coalesce(sum(calls.minutes), 0) AS call_minutes
            FROM calls
            JOIN conversations ON conversations.id = calls.conversation_id
            WHERE calls.ended_at IS NOT NULL AND NOT conversations.is_playground
            GROUP BY 1, 2
        ) AS c
        WHERE u.agent_version_id = c.agent_version_id AND u.day = c.day
        """
    )


def downgrade() -> None:
    op.drop_column("usage_daily", "call_minutes")
    op.drop_column("usage_daily", "calls")
