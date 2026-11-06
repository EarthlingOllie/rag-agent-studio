"""Project Instructions Versions: immutable, numbered Versions and the Current Version pointer.

The existing ``projects.instructions`` field becomes the Draft. A Project whose Instructions
weren't empty gets a v1 holding them, which becomes its Current Version, so what Agents follow
doesn't change.

Revision ID: 0021_instructions_versions
Revises: 0020_chunk_guardrail_flags
Create Date: 2026-11-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021_instructions_versions"
down_revision: str | None = "0020_chunk_guardrail_flags"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MIGRATED_NOTE = "The Instructions as they were when Versions were introduced."


def upgrade() -> None:
    op.create_table(
        "project_instructions_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "organisation_id",
            sa.Uuid(),
            sa.ForeignKey(
                "organisations.id",
                name="fk_project_instructions_versions_organisation_id_organisations",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey(
                "projects.id",
                name="fk_project_instructions_versions_project_id_projects",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column(
            "author_id",
            sa.Uuid(),
            sa.ForeignKey("members.id", name="fk_project_instructions_versions_author_id_members"),
            nullable=True,
        ),
        sa.Column(
            "previous_version_id",
            sa.Uuid(),
            sa.ForeignKey(
                "project_instructions_versions.id",
                name="fk_project_instructions_versions_previous",
            ),
            nullable=True,
        ),
        sa.UniqueConstraint(
            "project_id", "number", name="uq_project_instructions_versions_project_id"
        ),
    )
    op.create_index(
        "ix_project_instructions_versions_organisation_id",
        "project_instructions_versions",
        ["organisation_id"],
    )
    # Versions are immutable: a row can be added, and goes with its Project, but never changes.
    op.execute(
        """
        CREATE FUNCTION project_instructions_versions_immutable() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'project_instructions_versions are immutable: % is not allowed', TG_OP
                USING ERRCODE = 'insufficient_privilege';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER project_instructions_versions_immutable
        BEFORE UPDATE ON project_instructions_versions
        FOR EACH ROW EXECUTE FUNCTION project_instructions_versions_immutable()
        """
    )
    op.add_column(
        "projects", sa.Column("current_instructions_version_id", sa.Uuid(), nullable=True)
    )
    op.create_foreign_key(
        "fk_projects_current_instructions_version",
        "projects",
        "project_instructions_versions",
        ["current_instructions_version_id"],
        ["id"],
    )
    # The Instructions field is now the Draft; non-empty Instructions become v1, the Current
    # Version.
    op.execute(
        sa.text(
            """
            INSERT INTO project_instructions_versions
                (id, organisation_id, project_id, number, markdown, note)
            SELECT gen_random_uuid(), organisation_id, id, 1, instructions, :note
            FROM projects WHERE instructions <> ''
            """
        ).bindparams(note=MIGRATED_NOTE)
    )
    op.execute(
        """
        UPDATE projects SET current_instructions_version_id = v.id
        FROM project_instructions_versions v WHERE v.project_id = projects.id
        """
    )


def downgrade() -> None:
    # The Draft stays in ``projects.instructions``; the Versions go.
    op.drop_constraint("fk_projects_current_instructions_version", "projects", type_="foreignkey")
    op.drop_column("projects", "current_instructions_version_id")
    op.drop_table("project_instructions_versions")
    op.execute("DROP FUNCTION project_instructions_versions_immutable()")
