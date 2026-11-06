"""The Theme's logo and default Agent avatar.

Revision ID: 0016_theme_images
Revises: 0015_provider_embedding_models
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016_theme_images"
down_revision: str | None = "0015_provider_embedding_models"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("themes", sa.Column("logo", postgresql.JSONB(), nullable=True))
    op.add_column("themes", sa.Column("avatar", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("themes", "avatar")
    op.drop_column("themes", "logo")
