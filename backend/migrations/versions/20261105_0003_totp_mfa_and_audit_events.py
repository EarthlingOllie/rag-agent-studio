"""TOTP MFA factors, recovery codes and the Audit Event table.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _created_at() -> sa.Column[object]:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "mfa_factors",
        sa.Column(
            "member_id",
            sa.Uuid(),
            sa.ForeignKey(
                "members.id", ondelete="CASCADE", name="fk_mfa_factors_member_id_members"
            ),
            primary_key=True,
        ),
        sa.Column("secret_sealed", sa.LargeBinary(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_step", sa.BigInteger(), nullable=True),
        _created_at(),
    )
    op.create_table(
        "mfa_recovery_codes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _created_at(),
        sa.Column(
            "member_id",
            sa.Uuid(),
            sa.ForeignKey(
                "members.id", ondelete="CASCADE", name="fk_mfa_recovery_codes_member_id_members"
            ),
            nullable=False,
        ),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("member_id", "code_hash", name="uq_mfa_recovery_codes_member_id"),
    )
    op.create_index("ix_mfa_recovery_codes_member_id", "mfa_recovery_codes", ["member_id"])
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _created_at(),
        sa.Column(
            "organisation_id",
            sa.Uuid(),
            sa.ForeignKey(
                "organisations.id",
                ondelete="CASCADE",
                name="fk_audit_events_organisation_id_organisations",
            ),
            nullable=False,
        ),
        sa.Column(
            "actor_member_id",
            sa.Uuid(),
            sa.ForeignKey(
                "members.id", ondelete="SET NULL", name="fk_audit_events_actor_member_id_members"
            ),
            nullable=True,
        ),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("target_type", sa.String(50), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=True),
        sa.Column("before", postgresql.JSONB(), nullable=True),
        sa.Column("after", postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_audit_events_organisation_id", "audit_events", ["organisation_id"])
    op.create_index("ix_audit_events_actor_member_id", "audit_events", ["actor_member_id"])


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("mfa_recovery_codes")
    op.drop_table("mfa_factors")
