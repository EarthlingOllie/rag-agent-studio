"""Judging setup on Verdict reviews and Review sample skips (spec 19, ticket 19-03): the Judging
guidance version beside the judge model they already copy, so agreement and the Review sample
work per Judging setup. Existing reviews take their target's version; existing skips stay None.

Revision ID: 0063_judging_setup_reviews
Revises: 0062_review_sample_skips
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0063_judging_setup_reviews"
down_revision: str | None = "0062_review_sample_skips"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("verdict_reviews", "review_sample_skips")


def _fk(table: str) -> str:
    return f"fk_{table}_judging_guidance_version"


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(table, sa.Column("judging_guidance_version", sa.Integer(), nullable=True))
        # The version is always the row's own Organisation's.
        op.create_foreign_key(
            _fk(table),
            table,
            "judging_guidance_versions",
            ["organisation_id", "judging_guidance_version"],
            ["organisation_id", "version"],
        )
    op.execute(
        """
        UPDATE verdict_reviews r SET judging_guidance_version = run.judging_guidance_version
        FROM evaluation_verdicts v
        JOIN evaluation_case_results res ON res.id = v.result_id
        JOIN evaluation_runs run ON run.id = res.run_id
        WHERE v.id = r.verdict_id
        """
    )
    op.execute(
        """
        UPDATE verdict_reviews r SET judging_guidance_version = lv.judging_guidance_version
        FROM live_verdicts lv
        WHERE lv.id = r.live_verdict_id
        """
    )


def downgrade() -> None:
    for table in _TABLES:
        op.drop_constraint(_fk(table), table, type_="foreignkey")
        op.drop_column(table, "judging_guidance_version")
