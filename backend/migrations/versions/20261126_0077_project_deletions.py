"""Deleting a Project (spec 21, ADR-0020): the deleting mark on a Project, and who asked, set in
the request's transaction, so the sweeper finishes a deletion whose job was lost.

Revision ID: 0077_project_deletions
Revises: 0076_suggestion_run_claims
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0077_project_deletions"
down_revision: str | None = "0076_suggestion_run_claims"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "projects", sa.Column("deletion_requested_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("projects", sa.Column("deletion_requested_by", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_projects_deletion_requested_by_members"),
        "projects",
        "members",
        ["deletion_requested_by"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_projects_deletion_requested_by_members"), "projects", type_="foreignkey"
    )
    op.drop_column("projects", "deletion_requested_by")
    op.drop_column("projects", "deletion_requested_at")
