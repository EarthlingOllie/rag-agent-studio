"""Judging guidance (spec 19): its versions, the Organisation's current one, and the version
each Evaluation Run and Live Verdict was judged under (with its judge model, its Judging setup).

Revision ID: 0059_judging_guidance
Revises: 0058_suggestion_check
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0059_judging_guidance"
down_revision: str | None = "0058_suggestion_check"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JUDGED = ("evaluation_runs", "live_verdicts", "organisations")


def _fk(table: str) -> str:
    return f"fk_{table}_judging_guidance_version"


def upgrade() -> None:
    op.create_table(
        "judging_guidance_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("text", sa.String(2000), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("saved_by", sa.Uuid(), nullable=True),
        sa.Column("saved_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_judging_guidance_versions_organisation_id_organisations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["saved_by"],
            ["members.id"],
            name=op.f("fk_judging_guidance_versions_saved_by_members"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_judging_guidance_versions")),
        sa.UniqueConstraint(
            "organisation_id", "version", name=op.f("uq_judging_guidance_versions_organisation_id")
        ),
    )
    for table in _JUDGED:
        op.add_column(table, sa.Column("judging_guidance_version", sa.Integer(), nullable=True))
        # The version is always the row's own Organisation's.
        op.create_foreign_key(
            _fk(table),
            table,
            "judging_guidance_versions",
            ["id" if table == "organisations" else "organisation_id", "judging_guidance_version"],
            ["organisation_id", "version"],
        )


def downgrade() -> None:
    for table in _JUDGED:
        op.drop_constraint(_fk(table), table, type_="foreignkey")
        op.drop_column(table, "judging_guidance_version")
    op.drop_table("judging_guidance_versions")
