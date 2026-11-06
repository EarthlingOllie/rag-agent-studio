"""Re-embed jobs: a Project's pending Embedding Model and the job moving its Chunks to it.

Revision ID: 0024_re_embed_jobs
Revises: 0023_erase_organisation
Create Date: 2026-11-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024_re_embed_jobs"
down_revision: str | None = "0023_erase_organisation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "re_embed_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "organisation_id",
            sa.Uuid(),
            sa.ForeignKey(
                "organisations.id",
                name="fk_re_embed_jobs_organisation_id_organisations",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey(
                "projects.id", name="fk_re_embed_jobs_project_id_projects", ondelete="CASCADE"
            ),
            nullable=False,
        ),
        sa.Column("from_model_id", sa.String(100), nullable=False),
        sa.Column("model_id", sa.String(100), nullable=False),
        sa.Column(
            "credential_id",
            sa.Uuid(),
            sa.ForeignKey(
                "provider_credentials.id",
                name="fk_re_embed_jobs_credential_id_provider_credentials",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("embedded_chunks", sa.Integer(), nullable=False),
        sa.Column("total_chunks", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "started_by",
            sa.Uuid(),
            sa.ForeignKey(
                "members.id", name="fk_re_embed_jobs_started_by_members", ondelete="SET NULL"
            ),
            nullable=True,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_re_embed_jobs_organisation_id", "re_embed_jobs", ["organisation_id"])
    op.create_index("ix_re_embed_jobs_project_id", "re_embed_jobs", ["project_id"])
    op.create_index("ix_re_embed_jobs_credential_id", "re_embed_jobs", ["credential_id"])
    op.create_index(
        "uq_re_embed_jobs_running_project",
        "re_embed_jobs",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )


def downgrade() -> None:
    op.drop_table("re_embed_jobs")
