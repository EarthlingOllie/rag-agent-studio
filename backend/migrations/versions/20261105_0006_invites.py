"""Invites to join an Organisation.

Revision ID: 0006_invites
Revises: 0005_totp_mfa
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_invites"
down_revision: str | None = "0005_totp_mfa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "invites",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "organisation_id",
            sa.Uuid(),
            sa.ForeignKey(
                "organisations.id",
                ondelete="CASCADE",
                name="fk_invites_organisation_id_organisations",
            ),
            nullable=False,
        ),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column(
            "role",
            postgresql.ENUM("owner", "editor", name="role", create_type=False),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column(
            "invited_by_id",
            sa.Uuid(),
            sa.ForeignKey(
                "members.id", ondelete="CASCADE", name="fk_invites_invited_by_id_members"
            ),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "accepted_by_id",
            sa.Uuid(),
            sa.ForeignKey(
                "members.id", ondelete="SET NULL", name="fk_invites_accepted_by_id_members"
            ),
            nullable=True,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("token_hash", name="uq_invites_token_hash"),
    )
    op.create_index("ix_invites_organisation_id", "invites", ["organisation_id"])
    op.create_index(
        "uq_invites_pending_email",
        "invites",
        ["organisation_id", "email"],
        unique=True,
        postgresql_where=sa.text("accepted_at IS NULL AND revoked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_table("invites")
