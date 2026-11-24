"""Verdict reviews (spec 18): an Editor's own pass or fail on a judged Verdict.

One row per reviewed target: an Evaluation Run Verdict (Reference answer or grounding), or a Live
Verdict plus its check (grounding or answers the question); reviewing it again replaces the row.
The Evaluation Model's outcome, the check and the Evaluation Model that judged are copied when it
is reviewed, so Evaluation Model agreement is counted from this table alone. A review never
changes the Verdict, or anything counted from Verdicts (ADR-0018). It goes with its Verdict or
Live Verdict, and so with its Run or Message and its Agent (``ON DELETE CASCADE``). The Purge of
a Live Verdict's reply clears the reason on its reviews, which can quote the Visitor, and stamps
them purged-at; their outcomes stay.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.agents.models import Agent
from app.core.db import Base, IdMixin
from app.evaluation.models import EvaluationVerdict, LiveVerdict
from app.tenancy.models import Member, Organisation

# The longest reason an Editor may give.
REVIEW_REASON_MAX = 1000


class VerdictReview(IdMixin, Base):
    __tablename__ = "verdict_reviews"
    __table_args__ = (
        # A Live Verdict has one review per check.
        UniqueConstraint("live_verdict_id", "check"),
        CheckConstraint("(verdict_id IS NULL) <> (live_verdict_id IS NULL)", name="one_target"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Organisation.id, ondelete="CASCADE"), index=True
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Agent.id, ondelete="CASCADE"), index=True
    )
    # The target: a Run Verdict (one review each), or a Live Verdict and the ``check``.
    verdict_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(EvaluationVerdict.id, ondelete="CASCADE"), unique=True
    )
    live_verdict_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(LiveVerdict.id, ondelete="CASCADE")
    )
    # The Editor's ``VerdictOutcome``: pass or fail.
    outcome: Mapped[str] = mapped_column(String(10))
    # The Evaluation Model's outcome and the check (a ``VerdictKind``: ``grounding`` or
    # ``answers_question`` for a Live Verdict), copied.
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
    # When the Purge of a Live Verdict's reply cleared the reason (``app.retention``).
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
