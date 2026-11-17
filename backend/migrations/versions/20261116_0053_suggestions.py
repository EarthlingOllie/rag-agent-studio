"""Suggestions (spec 16): Suggestion runs, their suggested changes and their evidence.

Revision ID: 0053_suggestions
Revises: 0052_usage_live_verdicts
Create Date: 2026-11-16
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0053_suggestions"
down_revision: str | None = "0052_usage_live_verdicts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _owned(table: str, parent: str, parent_table: str) -> list[sa.Column[Any] | sa.Constraint]:
    """The ID, creation time, Organisation and owner columns every table here has."""
    return [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column(parent, sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f(f"fk_{table}_organisation_id_organisations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            [parent],
            [f"{parent_table}.id"],
            name=op.f(f"fk_{table}_{parent}_{parent_table}"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}")),
    ]


def upgrade() -> None:
    op.create_table(
        "suggestions",
        *_owned("suggestions", "agent_id", "agents"),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_by", sa.Uuid(), nullable=True),
        sa.Column("range_start", sa.Date(), nullable=False),
        sa.Column("range_end", sa.Date(), nullable=False),
        sa.Column("base_version_id", sa.Uuid(), nullable=False),
        sa.Column("base_config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("model_credential_id", sa.Uuid(), nullable=True),
        sa.Column("model_provider", sa.String(length=50), nullable=False),
        sa.Column("model_name", sa.String(length=200), nullable=False),
        sa.Column("evidence_total", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(length=20), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["started_by"],
            ["members.id"],
            name=op.f("fk_suggestions_started_by_members"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["base_version_id"],
            ["agent_versions.id"],
            name=op.f("fk_suggestions_base_version_id_agent_versions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["model_credential_id"],
            ["provider_credentials.id"],
            name=op.f("fk_suggestions_model_credential_id_provider_credentials"),
            ondelete="SET NULL",
        ),
    )
    for column in ("organisation_id", "agent_id", "base_version_id", "model_credential_id"):
        op.create_index(op.f(f"ix_suggestions_{column}"), "suggestions", [column])

    op.create_table(
        "suggested_changes",
        *_owned("suggested_changes", "suggestion_id", "suggestions"),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("path", sa.String(length=100), nullable=False),
        sa.Column("base_value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("suggested_value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    )
    for column in ("organisation_id", "suggestion_id"):
        op.create_index(op.f(f"ix_suggested_changes_{column}"), "suggested_changes", [column])

    op.create_table(
        "suggestion_evidence",
        *_owned("suggestion_evidence", "suggestion_id", "suggestions"),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            name=op.f("fk_suggestion_evidence_message_id_messages"),
            ondelete="CASCADE",
        ),
    )
    for column in ("organisation_id", "suggestion_id", "message_id"):
        op.create_index(op.f(f"ix_suggestion_evidence_{column}"), "suggestion_evidence", [column])


def downgrade() -> None:
    op.drop_table("suggestion_evidence")
    op.drop_table("suggested_changes")
    op.drop_table("suggestions")
