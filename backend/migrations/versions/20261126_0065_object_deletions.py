"""Deleted files are really deleted (spec 21, ADR-0020): the deletions table, holding the object
keys or prefixes to delete, and the flag on a Document whose new edition still needs its Expected
sources matched again.

Revision ID: 0065_object_deletions
Revises: 0064_re_embed_claims
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0065_object_deletions"
down_revision: str | None = "0064_re_embed_claims"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "object_deletions",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("prefix", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_object_deletions")),
    )
    op.add_column(
        "documents",
        sa.Column("recheck_due", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("documents", "recheck_due")
    op.drop_table("object_deletions")
