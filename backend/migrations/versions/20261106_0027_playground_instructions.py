"""Playground Instructions picker: each answer records the Project Instructions it ran with.

``messages.instructions_source`` is ``draft`` (the Instructions Draft) or ``version``, with
``messages.instructions_version_id`` naming the Version. Every answer saved before this in
the Playground ran with the Instructions Draft, so existing Draft answers get the Draft marker;
answers served by an Agent Version (``config_source`` ``version``) keep none, as their pinned
Instructions are named by the Version.

Revision ID: 0027_playground_instructions
Revises: 0026_agent_versions
Create Date: 2026-11-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027_playground_instructions"
down_revision: str | None = "0026_agent_versions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("instructions_source", sa.String(20), nullable=True))
    op.add_column("messages", sa.Column("instructions_version_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_messages_instructions_version",
        "messages",
        "project_instructions_versions",
        ["instructions_version_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.execute(
        "UPDATE messages SET instructions_source = 'draft'"
        " WHERE role = 'assistant' AND config_source = 'draft'"
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_messages_instructions_version",
        "messages",
        type_="foreignkey",
    )
    op.drop_column("messages", "instructions_version_id")
    op.drop_column("messages", "instructions_source")
