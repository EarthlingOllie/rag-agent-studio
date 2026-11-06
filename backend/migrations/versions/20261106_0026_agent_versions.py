"""Agent Versions: immutable, numbered snapshots of an Agent's Draft, each pinning a Project
Instructions Version; the Agent's Live Version pointer; the append-only Live History; and the
Agent Version each Message was answered by.

Revision ID: 0026_agent_versions
Revises: 0025_instructions_versions
Create Date: 2026-11-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026_agent_versions"
down_revision: str | None = "0025_instructions_versions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

IMMUTABLE_TABLES = ("agent_versions", "agent_live_history")


def upgrade() -> None:
    op.create_table(
        "agent_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "organisation_id",
            sa.Uuid(),
            sa.ForeignKey(
                "organisations.id",
                name="fk_agent_versions_organisation_id_organisations",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            sa.Uuid(),
            sa.ForeignKey(
                "agents.id", name="fk_agent_versions_agent_id_agents", ondelete="CASCADE"
            ),
            nullable=False,
        ),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("config", postgresql.JSONB(), nullable=False),
        sa.Column(
            "instructions_version_id",
            sa.Uuid(),
            sa.ForeignKey(
                "project_instructions_versions.id",
                name="fk_agent_versions_instructions_version",
            ),
            nullable=True,
        ),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column(
            "author_id",
            sa.Uuid(),
            sa.ForeignKey("members.id", name="fk_agent_versions_author_id_members"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_agent_versions"),
        sa.UniqueConstraint("agent_id", "number", name="uq_agent_versions_agent_id"),
    )
    op.create_index("ix_agent_versions_organisation_id", "agent_versions", ["organisation_id"])
    op.create_table(
        "agent_live_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "organisation_id",
            sa.Uuid(),
            sa.ForeignKey(
                "organisations.id",
                name="fk_agent_live_history_organisation_id_organisations",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            sa.Uuid(),
            sa.ForeignKey(
                "agents.id", name="fk_agent_live_history_agent_id_agents", ondelete="CASCADE"
            ),
            nullable=False,
        ),
        sa.Column("seq", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column(
            "from_version_id",
            sa.Uuid(),
            sa.ForeignKey(
                "agent_versions.id", name="fk_agent_live_history_from_version_id_agent_versions"
            ),
            nullable=True,
        ),
        sa.Column(
            "to_version_id",
            sa.Uuid(),
            sa.ForeignKey(
                "agent_versions.id", name="fk_agent_live_history_to_version_id_agent_versions"
            ),
            nullable=False,
        ),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column(
            "actor_id",
            sa.Uuid(),
            sa.ForeignKey("members.id", name="fk_agent_live_history_actor_id_members"),
            nullable=False,
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bulk_operation_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_agent_live_history"),
        sa.UniqueConstraint("seq", name="uq_agent_live_history_seq"),
    )
    op.create_index(
        "ix_agent_live_history_organisation_id", "agent_live_history", ["organisation_id"]
    )
    op.create_index("ix_agent_live_history_agent_id", "agent_live_history", ["agent_id"])
    # Versions and Live History entries are immutable: rows are added, and go with their Agent,
    # but never change.
    op.execute(
        """
        CREATE FUNCTION agent_versions_immutable() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION '% are immutable: % is not allowed', TG_TABLE_NAME, TG_OP
                USING ERRCODE = 'insufficient_privilege';
        END;
        $$
        """
    )
    for table in IMMUTABLE_TABLES:
        op.execute(
            f"""
            CREATE TRIGGER {table}_immutable
            BEFORE UPDATE ON {table}
            FOR EACH ROW EXECUTE FUNCTION agent_versions_immutable()
            """
        )
    op.add_column("agents", sa.Column("live_version_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_agents_live_version", "agents", "agent_versions", ["live_version_id"], ["id"]
    )
    op.add_column("messages", sa.Column("agent_version_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_messages_agent_version_id_agent_versions",
        "messages",
        "agent_versions",
        ["agent_version_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_messages_agent_version_id_agent_versions", "messages", type_="foreignkey"
    )
    op.drop_column("messages", "agent_version_id")
    op.drop_constraint("fk_agents_live_version", "agents", type_="foreignkey")
    op.drop_column("agents", "live_version_id")
    op.drop_table("agent_live_history")
    op.drop_table("agent_versions")
    op.execute("DROP FUNCTION agent_versions_immutable()")
