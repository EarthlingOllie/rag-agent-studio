"""A reply talked over before it was saved (spec 20): the open Call records the Visitor's turn
whose reply was interrupted, and that reply is marked when it is saved.

Revision ID: 0066_interrupted_turn
Revises: 0065_interrupted
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0066_interrupted_turn"
down_revision: str | None = "0065_interrupted"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("calls", sa.Column("interrupted_turn_id", sa.Uuid(), nullable=True))


def downgrade() -> None:
    op.drop_column("calls", "interrupted_turn_id")
