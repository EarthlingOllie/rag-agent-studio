"""Each Project's OCR flag, off by default (ticket 03-08).

Revision ID: 0012_project_ocr
Revises: 0011_documents
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_project_ocr"
down_revision: str | None = "0011_documents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("ocr_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("projects", "ocr_enabled")
