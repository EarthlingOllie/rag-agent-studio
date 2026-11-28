"""Calls (spec 20): an Agent's Call settings, its remote agent in the voice layer and the
per-Agent secret the remote agent presents to the turn endpoint.

Revision ID: 0059_call_settings
Revises: 0058_suggestion_check
Create Date: 2026-11-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0059_call_settings"
down_revision: str | None = "0058_suggestion_check"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("calls_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column("agents", sa.Column("call_credential_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_agents_call_credential_id_provider_credentials"),
        "agents",
        "provider_credentials",
        ["call_credential_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_agents_call_credential_id"), "agents", ["call_credential_id"])
    op.add_column("agents", sa.Column("call_voice_id", sa.String(64), nullable=True))
    op.add_column(
        "agents",
        sa.Column("spoken_greeting", sa.String(500), server_default=sa.text("''"), nullable=False),
    )
    op.add_column("agents", sa.Column("remote_agent_id", sa.String(128), nullable=True))
    op.add_column("agents", sa.Column("call_secret_sealed", sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    op.drop_column("agents", "call_secret_sealed")
    op.drop_column("agents", "remote_agent_id")
    op.drop_column("agents", "spoken_greeting")
    op.drop_column("agents", "call_voice_id")
    op.drop_index(op.f("ix_agents_call_credential_id"), table_name="agents")
    op.drop_constraint(
        op.f("fk_agents_call_credential_id_provider_credentials"), "agents", type_="foreignkey"
    )
    op.drop_column("agents", "call_credential_id")
    op.drop_column("agents", "calls_enabled")
