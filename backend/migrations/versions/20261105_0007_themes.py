"""The Organisation's Theme.

Revision ID: 0007_themes
Revises: 0007_projects
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_themes"
down_revision: str | None = "0007_projects"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "themes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "organisation_id",
            sa.Uuid(),
            sa.ForeignKey(
                "organisations.id",
                ondelete="CASCADE",
                name="fk_themes_organisation_id_organisations",
            ),
            nullable=False,
        ),
        sa.Column("colours", postgresql.JSONB(), nullable=False),
        sa.Column("radius", sa.Integer(), nullable=False),
        sa.Column("font", sa.String(100), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("launcher_type", sa.String(20), nullable=False),
        sa.Column("launcher_position", sa.String(20), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_themes"),
        sa.UniqueConstraint("organisation_id", name="uq_themes_organisation_id"),
    )


def downgrade() -> None:
    op.drop_table("themes")
