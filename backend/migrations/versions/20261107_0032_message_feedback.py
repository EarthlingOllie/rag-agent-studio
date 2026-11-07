"""Message Feedback: a Visitor's thumbs up or down, with an optional comment, on an Agent reply;
one per Message, attributed to the Message's Agent Version when written.

Revision ID: 0031_message_feedback
Revises: 0030_agent_theme_override
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031_message_feedback"
down_revision: str | None = "0030_agent_theme_override"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "message_feedback",
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
                name="fk_message_feedback_organisation_id_organisations",
            ),
            nullable=False,
        ),
        sa.Column(
            "message_id",
            sa.Uuid(),
            sa.ForeignKey(
                "messages.id", ondelete="CASCADE", name="fk_message_feedback_message_id_messages"
            ),
            nullable=False,
        ),
        sa.Column(
            "agent_version_id",
            sa.Uuid(),
            sa.ForeignKey(
                "agent_versions.id", name="fk_message_feedback_agent_version_id_agent_versions"
            ),
            nullable=True,
        ),
        sa.Column("rating", sa.String(10), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("message_id", name="uq_message_feedback_message_id"),
    )
    op.create_index("ix_message_feedback_organisation_id", "message_feedback", ["organisation_id"])
    op.create_index(
        "ix_message_feedback_agent_version_id", "message_feedback", ["agent_version_id"]
    )


def downgrade() -> None:
    op.drop_table("message_feedback")
