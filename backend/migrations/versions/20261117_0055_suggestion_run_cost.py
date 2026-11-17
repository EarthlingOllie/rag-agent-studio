"""Suggestions (spec 16): a run's estimated and actual Cost, and one run in progress per Agent.

A Suggestion stores its estimated proposing and checking Cost, and the proposing call's actual
Cost with when it was spent. A partial unique index backs up the rule that an Agent has at most
one Suggestion run in progress.

Revision ID: 0055_suggestion_run_cost
Revises: 0054_suggestion_gaps
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0055_suggestion_run_cost"
down_revision: str | None = "0054_suggestion_gaps"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_IN_PROGRESS = "('queued', 'gathering', 'proposing', 'checking')"
_SUPERSEDED = "A later Suggestion run of this Agent started while this one was in progress."
_COSTS = ("estimated_proposing_cost_usd", "estimated_checking_cost_usd", "proposing_cost_usd")


def upgrade() -> None:
    for column in _COSTS:
        op.add_column(
            "suggestions", sa.Column(column, sa.Numeric(precision=18, scale=9), nullable=True)
        )
    op.add_column(
        "suggestions", sa.Column("proposed_at", sa.DateTime(timezone=True), nullable=True)
    )
    # Before the index, an Agent could have several runs in progress: all but its newest fail.
    op.execute(
        sa.text(
            """
            UPDATE suggestions SET status = 'failed', error_message = :superseded,
                finished_at = now()
            WHERE status IN ('queued', 'gathering', 'proposing', 'checking') AND id NOT IN (
                SELECT DISTINCT ON (agent_id) id FROM suggestions
                WHERE status IN ('queued', 'gathering', 'proposing', 'checking')
                ORDER BY agent_id, created_at DESC, id
            )
            """
        ).bindparams(superseded=_SUPERSEDED)
    )
    op.create_index(
        "uq_suggestions_in_progress_agent",
        "suggestions",
        ["agent_id"],
        unique=True,
        postgresql_where=sa.text(f"status IN {_IN_PROGRESS}"),
    )


def downgrade() -> None:
    op.drop_index("uq_suggestions_in_progress_agent", table_name="suggestions")
    op.drop_column("suggestions", "proposed_at")
    for column in reversed(_COSTS):
        op.drop_column("suggestions", column)
