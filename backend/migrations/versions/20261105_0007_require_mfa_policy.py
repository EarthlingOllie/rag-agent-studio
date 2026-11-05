"""The Require MFA policy: an Organisation can require MFA of every Member.

Revision ID: 0007_require_mfa_policy
Revises: 0006_invites
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_require_mfa_policy"
down_revision: str | None = "0006_invites"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organisations",
        sa.Column("require_mfa", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("organisations", "require_mfa")
