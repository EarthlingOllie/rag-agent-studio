"""Guardrail outcomes on Messages: what each Guardrail layer decided about an answer.

Revision ID: 0018_message_guardrail_outcomes
Revises: 0017_message_retrievals
Create Date: 2026-11-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018_message_guardrail_outcomes"
down_revision: str | None = "0017_message_retrievals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column(
            "guardrail_outcomes",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("messages", "guardrail_outcomes")
