"""Playground Calls (spec 20): a Call held in the Playground answers with the Draft, so it names
no Agent Version, and records the Project Instructions it answers with (an Instructions Version,
or none for the Instructions Draft).

Revision ID: 0063_playground_calls
Revises: 0062_voice_cost
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0063_playground_calls"
down_revision: str | None = "0062_voice_cost"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("calls", "agent_version_id", existing_type=sa.Uuid(), nullable=True)
    op.add_column("calls", sa.Column("instructions_version_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_calls_instructions_version",
        "calls",
        "project_instructions_versions",
        ["instructions_version_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    # Playground Calls name no Agent Version, so they go with the column's nullability.
    op.execute("DELETE FROM calls WHERE agent_version_id IS NULL")
    op.drop_constraint("fk_calls_instructions_version", "calls", type_="foreignkey")
    op.drop_column("calls", "instructions_version_id")
    op.alter_column("calls", "agent_version_id", existing_type=sa.Uuid(), nullable=False)
