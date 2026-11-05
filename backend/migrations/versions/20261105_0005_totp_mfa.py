"""TOTP MFA factors and recovery codes.

Revision ID: 0005_totp_mfa
Revises: 0004_password_reset
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_totp_mfa"
down_revision: str | None = "0004_password_reset"
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


def downgrade() -> None:
    op.drop_table("mfa_recovery_codes")
    op.drop_table("mfa_factors")
