"""Interrupted replies (spec 20): an Agent Message the Visitor talked over in a Call. It keeps
its whole text.

Revision ID: 0065_interrupted
Revises: 0064_calls_failing
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0065_interrupted"
down_revision: str | None = "0064_calls_failing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("interrupted", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("messages", "interrupted")
