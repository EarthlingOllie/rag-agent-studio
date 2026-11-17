"""What other modules read of an Agent's Suggestion runs: whether one is in progress (Evaluate
is refused while it is) and what proposing has cost (Organisation cost's Evaluation column).

Kept apart from ``app.suggestions.service`` so that ``evaluation`` and ``analytics`` can read it
without importing the Suggestion run job."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.suggestions.models import IN_PROGRESS, Suggestion


async def suggestion_in_progress(session: AsyncSession, agent_id: uuid.UUID) -> bool:
    """Whether the Agent has a Suggestion run queued, gathering, proposing or checking. The
    caller holds the Agent's row lock when it is about to start a run of either kind."""
    found = await session.scalar(
        select(Suggestion.id).where(
            Suggestion.agent_id == agent_id, Suggestion.status.in_(IN_PROGRESS)
        )
    )
    return found is not None


async def proposing_cost(
    session: AsyncSession, organisation_id: uuid.UUID, start: datetime, before: datetime
) -> dict[uuid.UUID, Decimal]:
    """What each Agent's Suggestion runs spent proposing from ``start`` until ``before``, by when
    each proposing call was made, at the prices frozen then. A check's Cost is its Evaluation
    Run's, counted with the Agent's Runs."""
    rows = await session.execute(
        select(Suggestion.agent_id, func.sum(Suggestion.proposing_cost_usd))
        .where(
            Suggestion.organisation_id == organisation_id,
            Suggestion.proposing_cost_usd.is_not(None),
            Suggestion.proposed_at >= start,
            Suggestion.proposed_at < before,
        )
        .group_by(Suggestion.agent_id)
    )
    return {agent_id: Decimal(total or 0) for agent_id, total in rows}
