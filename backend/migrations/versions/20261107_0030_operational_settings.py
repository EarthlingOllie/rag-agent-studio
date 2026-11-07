"""Operational Settings: an Agent's unavailable text, what Visitors are told when it can't
answer (null means the platform's default).

Revision ID: 0030_operational_settings
Revises: 0029_embed
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030_operational_settings"
down_revision: str | None = "0029_embed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("unavailable_text", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("agents", "unavailable_text")
