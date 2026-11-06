"""Draft revisions, for Agent Drafts and the Project Instructions Draft: the optimistic
concurrency token a Draft change carries, so a save made on a Draft someone has since changed
is refused instead of overwriting their edits.

Revision ID: 0027_draft_revisions
Revises: 0026_agent_versions
Create Date: 2026-11-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027_draft_revisions"
down_revision: str | None = "0026_agent_versions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_drafts",
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )
    op.add_column(
        "projects",
        sa.Column(
            "instructions_revision", sa.Integer(), server_default=sa.text("1"), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_column("projects", "instructions_revision")
    op.drop_column("agent_drafts", "revision")
