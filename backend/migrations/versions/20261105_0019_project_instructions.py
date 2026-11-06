"""Project Instructions: one markdown Draft per Project.

Revision ID: 0019_project_instructions
Revises: 0018_document_failures
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_project_instructions"
down_revision: str | None = "0018_document_failures"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "projects", sa.Column("instructions", sa.Text(), server_default="", nullable=False)
    )


def downgrade() -> None:
    op.drop_column("projects", "instructions")
