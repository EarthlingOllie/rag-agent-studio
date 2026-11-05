"""Organisations, Members and memberships.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

role = postgresql.ENUM("owner", "editor", name="role", create_type=False)


def _id_and_created_at() -> list[sa.Column[object]]:
    return [
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    role.create(op.get_bind())
    op.create_table(
        "organisations",
        *_id_and_created_at(),
        sa.Column("name", sa.String(200), nullable=False),
    )
    op.create_table(
        "members",
        *_id_and_created_at(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.UniqueConstraint("email", name="uq_members_email"),
    )
    op.create_table(
        "memberships",
        *_id_and_created_at(),
        sa.Column(
            "organisation_id",
            sa.Uuid(),
            sa.ForeignKey(
                "organisations.id",
                ondelete="CASCADE",
                name="fk_memberships_organisation_id_organisations",
            ),
            nullable=False,
        ),
        sa.Column(
            "member_id",
            sa.Uuid(),
            sa.ForeignKey(
                "members.id", ondelete="CASCADE", name="fk_memberships_member_id_members"
            ),
            nullable=False,
        ),
        sa.Column("role", role, nullable=False),
        sa.UniqueConstraint("organisation_id", "member_id", name="uq_memberships_organisation_id"),
    )
    op.create_index("ix_memberships_organisation_id", "memberships", ["organisation_id"])
    op.create_index("ix_memberships_member_id", "memberships", ["member_id"])


def downgrade() -> None:
    op.drop_table("memberships")
    op.drop_table("members")
    op.drop_table("organisations")
    role.drop(op.get_bind())
