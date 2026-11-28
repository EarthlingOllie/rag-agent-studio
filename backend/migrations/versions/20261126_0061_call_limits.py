"""Call limits (spec 20): an Agent's Maximum Call length, Call minutes budget and its alert; a
Call's Maximum Call length (the Agent's when it started), last turn, minutes and why it ended;
and each Agent's Call minutes counter per UTC date.

Revision ID: 0061_call_limits
Revises: 0060_calls
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0061_call_limits"
down_revision: str | None = "0060_calls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("max_call_minutes", sa.Integer(), server_default=sa.text("10"), nullable=False),
    )
    op.add_column(
        "agents",
        sa.Column(
            "call_minutes_budget", sa.Integer(), server_default=sa.text("60"), nullable=False
        ),
    )
    op.add_column(
        "agents", sa.Column("call_budget_exhausted_at", sa.DateTime(timezone=True), nullable=True)
    )
    # Calls open during the upgrade get the default Maximum Call length; new ones are given theirs.
    op.add_column(
        "calls",
        sa.Column("max_call_minutes", sa.Integer(), server_default=sa.text("10"), nullable=False),
    )
    op.alter_column("calls", "max_call_minutes", server_default=None)
    op.add_column("calls", sa.Column("last_turn_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("calls", sa.Column("minutes", sa.Integer(), nullable=True))
    op.add_column("calls", sa.Column("end_reason", sa.String(32), nullable=True))
    op.create_index(
        "ix_calls_open_ip", "calls", ["ip"], postgresql_where=sa.text("ended_at IS NULL")
    )
    op.create_table(
        "call_minutes_used",
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("minutes", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["agents.id"],
            name=op.f("fk_call_minutes_used_agent_id_agents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_call_minutes_used_organisation_id_organisations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("agent_id", "day", name=op.f("pk_call_minutes_used")),
    )
    op.create_index(
        op.f("ix_call_minutes_used_organisation_id"), "call_minutes_used", ["organisation_id"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_call_minutes_used_organisation_id"), table_name="call_minutes_used")
    op.drop_table("call_minutes_used")
    op.drop_index("ix_calls_open_ip", table_name="calls")
    op.drop_column("calls", "end_reason")
    op.drop_column("calls", "minutes")
    op.drop_column("calls", "last_turn_at")
    op.drop_column("calls", "max_call_minutes")
    op.drop_column("agents", "call_budget_exhausted_at")
    op.drop_column("agents", "call_minutes_budget")
    op.drop_column("agents", "max_call_minutes")
