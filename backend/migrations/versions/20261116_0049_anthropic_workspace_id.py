"""Anthropic credentials name a workspace: the ``anthropic-workspace-id`` an identity-backed key
(a personal or service account key not scoped to one workspace) must send on every request.

Revision ID: 0049_anthropic_workspace_id
Revises: 0048_evaluation_run_kind
Create Date: 2026-11-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0049_anthropic_workspace_id"
down_revision: str | None = "0048_evaluation_run_kind"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "provider_credentials", sa.Column("workspace_id", sa.String(length=64), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("provider_credentials", "workspace_id")
