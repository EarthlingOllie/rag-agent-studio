"""Retention: the Organisation's Retention Window, the daily purge of Message text and feedback
comments older than it, and Conversations an Owner deletes on request.

Purging clears a Message's ``content``, the reasons in its Guardrail outcomes and the comment of
any Message Feedback on it, and sets ``purged_at``; every number and attribution (tokens, cost,
latency, Agent Version, thumbs, ratings, retrievals, verdicts) stays, so the metrics are the same
before and after. The daily purge and a
deletion go through the same ``purge_messages``.

Rollups come first: the daily purge clears a Visitor reply only once the ``usage_daily`` rollup
of its day is final (``app.analytics.rollup``), so no metric is ever worked out from a purged
day that wasn't already counted."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import ColumnElement, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import audit
from app.agents.models import Agent
from app.analytics.rollup import pending_days
from app.analytics.usage import day_bounds
from app.conversations.models import Conversation, Message
from app.conversations.service import ConversationNotFoundError
from app.feedback.models import MessageFeedback
from app.projects.service import get_project
from app.tenancy.models import Organisation
from app.tenancy.repository import OrganisationScope

MIN_RETENTION_DAYS = 7
MAX_RETENTION_DAYS = 3650
RETENTION_WINDOW_CHANGED = "organisation.retention_window_changed"
CONVERSATION_DELETED = "conversation.deleted"


async def purge_messages(
    session: AsyncSession, *conditions: ColumnElement[bool], now: datetime
) -> int:
    """Purges the Messages matching ``conditions`` that aren't purged yet: their text, their
    Guardrail outcomes' reasons and the comments of their feedback are cleared, and
    ``purged_at`` set to ``now``. Returns how many Messages were purged."""
    found = select(Message.id).where(Message.purged_at.is_(None), *conditions)
    await session.execute(
        update(MessageFeedback)
        .where(MessageFeedback.message_id.in_(found), MessageFeedback.comment.is_not(None))
        .values(comment=None)
    )
    # A Guardrail's reason can quote or paraphrase the message; its verdict and action stay.
    outcome = func.jsonb_array_elements(Message.guardrail_outcomes).table_valued("value")
    without_reasons = (
        select(
            func.coalesce(
                func.jsonb_agg(outcome.c.value.op("||")(text("""'{"reason": ""}'::jsonb"""))),
                text("'[]'::jsonb"),
            )
        )
        .select_from(outcome)
        .scalar_subquery()
    )
    purged = await session.execute(
        update(Message)
        .where(Message.id.in_(found))
        .values(content="", purged_at=now, guardrail_outcomes=without_reasons)
    )
    return int(purged.rowcount)  # type: ignore[attr-defined]


async def purge_expired(sessionmaker: async_sessionmaker[AsyncSession], at: datetime) -> int:
    """Purges, in every Organisation, the Messages older than its Retention Window as of
    ``at``, those of archived Agents and Projects included. A Visitor reply on a day whose
    rollup isn't final yet waits for a later run. Returns how many Messages were purged."""
    purged = 0
    async with sessionmaker() as session, session.begin():
        windows = list(await session.execute(select(Organisation.id, Organisation.retention_days)))
        for organisation_id, days in windows:
            cutoff = at - timedelta(days=days)
            conditions = [Message.organisation_id == organisation_id, Message.created_at < cutoff]
            # The first day up to the cutoff's whose rollup isn't final, if any: Visitor
            # Messages from then on wait. Playground Messages never go into the rollups. Rollup
            # days are UTC days, whatever offset ``at`` is written in.
            last_day = cutoff.astimezone(UTC).date()
            first_open = (await pending_days(session, last_day + timedelta(days=1))).get(
                organisation_id
            )
            if first_open is not None:
                playground = select(Conversation.id).where(Conversation.is_playground.is_(True))
                conditions.append(
                    or_(
                        Message.created_at < day_bounds(first_open)[0],
                        Message.conversation_id.in_(playground),
                    )
                )
            purged += await purge_messages(session, *conditions, now=at)
    return purged


async def set_retention_window(
    session: AsyncSession, scope: OrganisationScope, *, days: int, now: datetime
) -> Organisation:
    """Sets the Organisation's Retention Window and records
    ``organisation.retention_window_changed``. Setting the value it already has changes and
    records nothing. The range (``MIN_RETENTION_DAYS`` to ``MAX_RETENTION_DAYS``) is checked
    by the route."""
    organisation = (
        await session.scalars(
            select(Organisation).where(Organisation.id == scope.organisation_id).with_for_update()
        )
    ).one()
    before = organisation.retention_days
    if before != days:
        organisation.retention_days = days
        await audit.record(
            session,
            organisation_id=scope.organisation_id,
            actor_id=scope.member_id,
            action=RETENTION_WINDOW_CHANGED,
            target=audit.AuditTarget("organisation", scope.organisation_id),
            before={"retention_days": before},
            after={"retention_days": days},
            occurred_at=now,
        )
    await session.commit()
    return organisation


async def delete_conversation(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
    *,
    now: datetime,
) -> None:
    """Deletes the Project's Conversation on request: its Messages' text and feedback comments
    are purged at once, its Conversation token stops working, and ``conversation.deleted`` is
    recorded. Its numbers stay for the metrics. Deleting it again changes and records
    nothing."""
    project = await get_project(session, scope, project_id)
    conversation = await session.scalar(
        select(Conversation)
        .join(Agent, Agent.id == Conversation.agent_id)
        .where(
            Conversation.id == conversation_id,
            Conversation.organisation_id == scope.organisation_id,
            Agent.project_id == project.id,
        )
        .with_for_update(of=Conversation)
    )
    if conversation is None:
        raise ConversationNotFoundError
    if conversation.deleted_at is None:
        purged = await purge_messages(session, Message.conversation_id == conversation.id, now=now)
        conversation.deleted_at = now
        conversation.token_hash = None
        await audit.record(
            session,
            organisation_id=scope.organisation_id,
            actor_id=scope.member_id,
            action=CONVERSATION_DELETED,
            target=audit.AuditTarget("conversation", conversation.id),
            before={
                "project_id": str(project.id),
                "agent_id": str(conversation.agent_id),
                "is_playground": conversation.is_playground,
            },
            after={"purged_messages": purged},
            occurred_at=now,
        )
    await session.commit()
