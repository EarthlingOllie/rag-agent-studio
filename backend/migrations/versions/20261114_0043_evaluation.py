"""Evaluation (spec 14): an Agent's Evaluation Cases, and Evaluation Runs with their sides, the
cases they copied when they started, their case results and Verdicts. Every row goes with its
Agent (``ON DELETE CASCADE``); none references a Conversation or a Message (ADR-0016).

Revision ID: 0043_evaluation
Revises: 0042_usage_searches
Create Date: 2026-11-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0043_evaluation"
down_revision: str | None = "0042_usage_searches"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evaluation_cases",
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("reference_answer", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["agents.id"],
            name=op.f("fk_evaluation_cases_agent_id_agents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["members.id"],
            name=op.f("fk_evaluation_cases_created_by_members"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_evaluation_cases_organisation_id_organisations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluation_cases")),
    )
    op.create_index(
        op.f("ix_evaluation_cases_agent_id"), "evaluation_cases", ["agent_id"], unique=False
    )
    op.create_index(
        op.f("ix_evaluation_cases_organisation_id"),
        "evaluation_cases",
        ["organisation_id"],
        unique=False,
    )
    op.create_table(
        "evaluation_runs",
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_by", sa.Uuid(), nullable=True),
        sa.Column("judge_credential_id", sa.Uuid(), nullable=True),
        sa.Column("judge_provider", sa.String(length=50), nullable=False),
        sa.Column("judge_model", sa.String(length=200), nullable=False),
        sa.Column("answers_done", sa.Integer(), nullable=False),
        sa.Column("answers_total", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["agents.id"],
            name=op.f("fk_evaluation_runs_agent_id_agents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["judge_credential_id"],
            ["provider_credentials.id"],
            name=op.f("fk_evaluation_runs_judge_credential_id_provider_credentials"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_evaluation_runs_organisation_id_organisations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["started_by"],
            ["members.id"],
            name=op.f("fk_evaluation_runs_started_by_members"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluation_runs")),
    )
    op.create_index(
        op.f("ix_evaluation_runs_agent_id"), "evaluation_runs", ["agent_id"], unique=False
    )
    op.create_index(
        op.f("ix_evaluation_runs_judge_credential_id"),
        "evaluation_runs",
        ["judge_credential_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_evaluation_runs_organisation_id"),
        "evaluation_runs",
        ["organisation_id"],
        unique=False,
    )
    op.create_table(
        "evaluation_run_cases",
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("reference_answer", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["evaluation_cases.id"],
            name=op.f("fk_evaluation_run_cases_case_id_evaluation_cases"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_evaluation_run_cases_organisation_id_organisations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["evaluation_runs.id"],
            name=op.f("fk_evaluation_run_cases_run_id_evaluation_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluation_run_cases")),
    )
    op.create_index(
        op.f("ix_evaluation_run_cases_case_id"), "evaluation_run_cases", ["case_id"], unique=False
    )
    op.create_index(
        op.f("ix_evaluation_run_cases_organisation_id"),
        "evaluation_run_cases",
        ["organisation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_evaluation_run_cases_run_id"), "evaluation_run_cases", ["run_id"], unique=False
    )
    op.create_table(
        "evaluation_run_sides",
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.String(length=10), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("agent_version_id", sa.Uuid(), nullable=True),
        sa.Column("draft_revision", sa.Integer(), nullable=True),
        sa.Column("instructions_version_id", sa.Uuid(), nullable=True),
        sa.Column(
            "instructions_draft", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("chat_provider", sa.String(length=50), nullable=False),
        sa.Column("chat_model", sa.String(length=200), nullable=False),
        sa.Column(
            "automatic_fallback", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["agent_version_id"],
            ["agent_versions.id"],
            name=op.f("fk_evaluation_run_sides_agent_version_id_agent_versions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["instructions_version_id"],
            ["project_instructions_versions.id"],
            name=op.f(
                "fk_evaluation_run_sides_instructions_version_id_project_instructions_versions"
            ),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_evaluation_run_sides_organisation_id_organisations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["evaluation_runs.id"],
            name=op.f("fk_evaluation_run_sides_run_id_evaluation_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluation_run_sides")),
    )
    op.create_index(
        op.f("ix_evaluation_run_sides_agent_version_id"),
        "evaluation_run_sides",
        ["agent_version_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_evaluation_run_sides_instructions_version_id"),
        "evaluation_run_sides",
        ["instructions_version_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_evaluation_run_sides_organisation_id"),
        "evaluation_run_sides",
        ["organisation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_evaluation_run_sides_run_id"), "evaluation_run_sides", ["run_id"], unique=False
    )
    op.create_table(
        "evaluation_case_results",
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("side_id", sa.Uuid(), nullable=False),
        sa.Column("run_case_id", sa.Uuid(), nullable=False),
        sa.Column("repeat", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_reason", sa.Text(), nullable=True),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("trace", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("cost_usd", sa.Numeric(precision=18, scale=9), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_evaluation_case_results_organisation_id_organisations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_case_id"],
            ["evaluation_run_cases.id"],
            name=op.f("fk_evaluation_case_results_run_case_id_evaluation_run_cases"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["evaluation_runs.id"],
            name=op.f("fk_evaluation_case_results_run_id_evaluation_runs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["side_id"],
            ["evaluation_run_sides.id"],
            name=op.f("fk_evaluation_case_results_side_id_evaluation_run_sides"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluation_case_results")),
    )
    op.create_index(
        op.f("ix_evaluation_case_results_organisation_id"),
        "evaluation_case_results",
        ["organisation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_evaluation_case_results_run_case_id"),
        "evaluation_case_results",
        ["run_case_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_evaluation_case_results_run_id"),
        "evaluation_case_results",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_evaluation_case_results_side_id"),
        "evaluation_case_results",
        ["side_id"],
        unique=False,
    )
    op.create_table(
        "evaluation_verdicts",
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("result_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("outcome", sa.String(length=10), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_evaluation_verdicts_organisation_id_organisations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["result_id"],
            ["evaluation_case_results.id"],
            name=op.f("fk_evaluation_verdicts_result_id_evaluation_case_results"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluation_verdicts")),
    )
    op.create_index(
        op.f("ix_evaluation_verdicts_organisation_id"),
        "evaluation_verdicts",
        ["organisation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_evaluation_verdicts_result_id"), "evaluation_verdicts", ["result_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_evaluation_verdicts_result_id"), table_name="evaluation_verdicts")
    op.drop_index(op.f("ix_evaluation_verdicts_organisation_id"), table_name="evaluation_verdicts")
    op.drop_table("evaluation_verdicts")
    op.drop_index(op.f("ix_evaluation_case_results_side_id"), table_name="evaluation_case_results")
    op.drop_index(op.f("ix_evaluation_case_results_run_id"), table_name="evaluation_case_results")
    op.drop_index(
        op.f("ix_evaluation_case_results_run_case_id"), table_name="evaluation_case_results"
    )
    op.drop_index(
        op.f("ix_evaluation_case_results_organisation_id"), table_name="evaluation_case_results"
    )
    op.drop_table("evaluation_case_results")
    op.drop_index(op.f("ix_evaluation_run_sides_run_id"), table_name="evaluation_run_sides")
    op.drop_index(
        op.f("ix_evaluation_run_sides_organisation_id"), table_name="evaluation_run_sides"
    )
    op.drop_index(
        op.f("ix_evaluation_run_sides_instructions_version_id"), table_name="evaluation_run_sides"
    )
    op.drop_index(
        op.f("ix_evaluation_run_sides_agent_version_id"), table_name="evaluation_run_sides"
    )
    op.drop_table("evaluation_run_sides")
    op.drop_index(op.f("ix_evaluation_run_cases_run_id"), table_name="evaluation_run_cases")
    op.drop_index(
        op.f("ix_evaluation_run_cases_organisation_id"), table_name="evaluation_run_cases"
    )
    op.drop_index(op.f("ix_evaluation_run_cases_case_id"), table_name="evaluation_run_cases")
    op.drop_table("evaluation_run_cases")
    op.drop_index(op.f("ix_evaluation_runs_organisation_id"), table_name="evaluation_runs")
    op.drop_index(op.f("ix_evaluation_runs_judge_credential_id"), table_name="evaluation_runs")
    op.drop_index(op.f("ix_evaluation_runs_agent_id"), table_name="evaluation_runs")
    op.drop_table("evaluation_runs")
    op.drop_index(op.f("ix_evaluation_cases_organisation_id"), table_name="evaluation_cases")
    op.drop_index(op.f("ix_evaluation_cases_agent_id"), table_name="evaluation_cases")
    op.drop_table("evaluation_cases")
