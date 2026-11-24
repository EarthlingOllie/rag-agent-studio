"""Verdict reviews (spec 18): an Editor's own pass or fail on a judged Verdict.

One row per reviewed target, here an Evaluation Run Verdict (Reference answer or grounding);
reviewing it again replaces the row. The Evaluation Model's outcome, the check and the Evaluation
Model that judged are copied when it is reviewed, so Evaluation Model agreement is counted from
this table alone. A review never changes the Verdict, or anything counted from Verdicts
(ADR-0018). It goes with its Verdict, and so with its Run and its Agent (``ON DELETE CASCADE``).
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.agents.models import Agent
from app.core.db import Base, IdMixin
from app.evaluation.models import EvaluationVerdict
from app.tenancy.models import Member, Organisation

# The longest reason an Editor may give.
REVIEW_REASON_MAX = 1000


class VerdictReview(IdMixin, Base):
    __tablename__ = "verdict_reviews"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Organisation.id, ondelete="CASCADE"), index=True
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Agent.id, ondelete="CASCADE"), index=True
    )
    # The target: one review per Verdict.
    verdict_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(EvaluationVerdict.id, ondelete="CASCADE"), unique=True
    )
    # The Editor's ``VerdictOutcome``: pass or fail.
    outcome: Mapped[str] = mapped_column(String(10))
    # The Evaluation Model's outcome and the check (a ``VerdictKind``), copied.
    evaluation_model_outcome: Mapped[str] = mapped_column(String(10))
    check: Mapped[str] = mapped_column(String(30))
    # The Evaluation Model that judged (or the Default Model, when none was chosen), copied.
    judge_provider: Mapped[str] = mapped_column(String(50))
    judge_model: Mapped[str] = mapped_column(String(200))
    # Given on the Review sample, blind: only these count towards agreement.
    from_sample: Mapped[bool] = mapped_column(Boolean)
    reason: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(Member.id, ondelete="SET NULL"), index=True
    )
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
