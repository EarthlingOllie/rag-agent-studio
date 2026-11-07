"""Conversation Rating: a Visitor Conversation's current 1-5 rating and rating-prompt dismissal,
and the append-only change log of ratings; each attributed to the Agent Version of the last
reply before it when written.

Revision ID: 0033_conversation_ratings
Revises: 0032_message_feedback
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033_conversation_ratings"
down_revision: str | None = "0032_message_feedback"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _common(table: str) -> list[sa.Column[object]]:
    return [
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
                name=f"fk_{table}_organisation_id_organisations",
            ),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            sa.Uuid(),
            sa.ForeignKey(
                "conversations.id",
                ondelete="CASCADE",
                name=f"fk_{table}_conversation_id_conversations",
            ),
            nullable=False,
        ),
    ]


def _agent_version(table: str) -> sa.Column[object]:
    return sa.Column(
        "agent_version_id",
        sa.Uuid(),
        sa.ForeignKey("agent_versions.id", name=f"fk_{table}_agent_version_id_agent_versions"),
        nullable=True,
    )


def upgrade() -> None:
    op.create_table(
        "conversation_ratings",
        *_common("conversation_ratings"),
        sa.Column("score", sa.SmallInteger(), nullable=True),
        _agent_version("conversation_ratings"),
        sa.Column("rated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("prompt_dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("conversation_id", name="uq_conversation_ratings_conversation_id"),
        sa.CheckConstraint(
            "score BETWEEN 1 AND 5", name="ck_conversation_ratings_score_from_1_to_5"
        ),
    )
    for column in ("organisation_id", "score", "agent_version_id"):
        op.create_index(f"ix_conversation_ratings_{column}", "conversation_ratings", [column])
    op.create_table(
        "conversation_rating_changes",
        *_common("conversation_rating_changes"),
        sa.Column("seq", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("score", sa.SmallInteger(), nullable=False),
        sa.Column("previous_score", sa.SmallInteger(), nullable=True),
        _agent_version("conversation_rating_changes"),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("seq", name="uq_conversation_rating_changes_seq"),
    )
    for column in ("organisation_id", "conversation_id", "agent_version_id"):
        op.create_index(
            f"ix_conversation_rating_changes_{column}", "conversation_rating_changes", [column]
        )


def downgrade() -> None:
    op.drop_table("conversation_rating_changes")
    op.drop_table("conversation_ratings")
