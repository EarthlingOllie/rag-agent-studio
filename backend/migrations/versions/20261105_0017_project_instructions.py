"""Project Instructions: one markdown Draft per Project.

Revision ID: 0017_project_instructions
Revises: 0016_project_ocr
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_project_instructions"
down_revision: str | None = "0016_project_ocr"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "projects", sa.Column("instructions", sa.Text(), server_default="", nullable=False)
    )


def downgrade() -> None:
    op.drop_column("projects", "instructions")
