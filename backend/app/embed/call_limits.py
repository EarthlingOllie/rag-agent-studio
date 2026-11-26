"""Call limits (spec 20): what keeps a Call's per-minute bill bounded and an open line from being
abused.

- **Admission.** After the checks a message passes, starting a Call is refused while the
  Conversation has a Call open, while the Visitor's IP address holds ``CALLS_PER_IP`` open
  Calls with the Agent (counted per Agent, as the IP rate limit is), and once the Agent's Call
  minutes for the UTC date, with the minutes so far of its open Calls (at least one each),
  have reached its Call minutes budget. Starts are serialized per Agent, so concurrent starts
  can't all take the budget's last minute. The first refusal of a day for the budget raises
  the Agent's Call minutes alert and emails its Owners, once.
- **Ending.** However a Call ends (the Visitor, the Maximum Call length, silence, the
  Conversation ending, a turn the Agent couldn't answer), ``finish`` records when and why, and
  its minutes: the time from its start, by the platform's clock, rounded up to whole minutes.
  Those minutes go on the Agent's counter for the UTC date the Call ended, unless the Call was
  held in the Playground.
- **The reaper.** A Beat task (``end_idle_calls``) ends Calls that have reached the Maximum Call
  length they started with (changing it applies to the next Call), and Calls with no turn for
  ``SILENCE`` (which also closes Calls whose browser vanished without ending them).
  Such a Call ends when its limit passed, not when Beat noticed; a turn that arrives after
  the limit passed and before Beat ran ends it too (``past_deadline``) and is refused.
"""

import enum
import math
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.models import Agent
from app.agents.service import get_agent
from app.conversations.models import Call, CallMinutesUsed, Conversation
from app.embed.admission import utc_date
from app.mail import templates
from app.mail.port import Mailer
from app.tenancy.models import Member, Membership, Role
from app.tenancy.repository import OrganisationScope

# The platform's cap of Calls one IP address may hold open at once with one Agent.
CALLS_PER_IP = 2
# A Call with no turn for this long is ended.
SILENCE = timedelta(seconds=60)


class CallEnd(enum.StrEnum):
    """Why a Call ended."""

    VISITOR = "visitor"
    MAX_LENGTH = "max_length"
    SILENCE = "silence"
    CONVERSATION_ENDED = "conversation_ended"
    # The Agent couldn't answer a turn (rate limits, Token Budget, provider failure, no model,
    # retired): the Visitor heard the Unavailable text and returns to messaging.
    UNAVAILABLE = "unavailable"


class CallRefusal(enum.StrEnum):
    """Why starting a Call was refused, after the message checks passed."""

    CALL_OPEN = "call_open"
    TOO_MANY_CALLS = "too_many_calls"
    MINUTES_SPENT = "call_minutes_exhausted"


def call_minutes(started_at: datetime, ended_at: datetime) -> int:
    """A Call's minutes: its length rounded up to whole minutes."""
    return math.ceil(max((ended_at - started_at).total_seconds(), 0) / 60)


def deadline(call: Call) -> tuple[datetime, CallEnd]:
    """When an open Call is to be ended by the platform, and why: the Maximum Call length it
    started with, from its start, or ``SILENCE`` after its last turn (or its start), whichever
    comes first."""
    longest = call.started_at + timedelta(minutes=call.max_call_minutes)
    silent = (call.last_turn_at or call.started_at) + SILENCE
    return (silent, CallEnd.SILENCE) if silent < longest else (longest, CallEnd.MAX_LENGTH)


async def past_deadline(
    session: AsyncSession, call: Call, conversation: Conversation, *, now: datetime
) -> bool:
    """Whether the open ``call`` (locked by the caller) has passed its deadline by ``now``;
    if so it is ended then, as Beat would have ended it, in the caller's transaction."""
    at, reason = deadline(call)
    if at > now:
        return False
    await finish(session, call, conversation, ended_at=at, reason=reason)
    return True


async def finish(
    session: AsyncSession,
    call: Call,
    conversation: Conversation,
    *,
    ended_at: datetime,
    reason: CallEnd,
) -> None:
    """Ends the open ``call`` (locked by the caller) in the caller's transaction, adding its
    minutes to its Agent's counter for the UTC date unless it was a Playground Call."""
    call.ended_at = ended_at
    call.minutes = call_minutes(call.started_at, ended_at)
    call.end_reason = reason
    if conversation.is_playground:
        return
    added = insert(CallMinutesUsed).values(
        agent_id=conversation.agent_id,
        day=utc_date(ended_at),
        organisation_id=conversation.organisation_id,
        minutes=call.minutes,
    )
    await session.execute(
        added.on_conflict_do_update(
            index_elements=[CallMinutesUsed.agent_id, CallMinutesUsed.day],
            set_={"minutes": CallMinutesUsed.minutes + added.excluded.minutes},
        )
    )


async def end_open_call(
    session: AsyncSession, conversation: Conversation, *, now: datetime, reason: CallEnd
) -> None:
    """Ends the Conversation's open Call, if it has one, in the caller's transaction."""
    call = await session.scalar(
        select(Call)
        .where(Call.conversation_id == conversation.id, Call.ended_at.is_(None))
        .with_for_update()
    )
    if call is not None:
        await finish(session, call, conversation, ended_at=now, reason=reason)


async def minutes_used(session: AsyncSession, agent_id: uuid.UUID, day: date) -> int:
    """The minutes of the Agent's Visitors' Calls that ended on that UTC date."""
    used = await session.scalar(
        select(CallMinutesUsed.minutes).where(
            CallMinutesUsed.agent_id == agent_id, CallMinutesUsed.day == day
        )
    )
    return used or 0


async def open_minutes(session: AsyncSession, agent_id: uuid.UUID, *, now: datetime) -> int:
    """The minutes, so far, of the Agent's Visitors' Calls still open, at least one each (a
    Call just started will cost its first minute): admission and the Studio's meter count
    them with the day's ended Calls. (A Call that started yesterday counts whole: its minutes
    go on the day it ends.)"""
    starts = await session.scalars(
        select(Call.started_at)
        .join(Conversation, Conversation.id == Call.conversation_id)
        .where(
            Conversation.agent_id == agent_id,
            Conversation.is_playground.is_(False),
            Call.ended_at.is_(None),
        )
    )
    return sum(max(call_minutes(started_at, now), 1) for started_at in starts)


async def minutes_so_far(session: AsyncSession, agent_id: uuid.UUID, *, now: datetime) -> int:
    """Today's (UTC) Call minutes as the budget counts them: the Calls that ended today and the
    minutes so far of those still open."""
    ended = await minutes_used(session, agent_id, utc_date(now))
    return ended + await open_minutes(session, agent_id, now=now)


async def refusal(
    session: AsyncSession, agent: Agent, conversation: Conversation, ip: str, *, now: datetime
) -> CallRefusal | None:
    """Why a Call may not start in the Conversation now, or None. Run it in the transaction
    that records the Call: it locks the Conversation and then the Agent's Call starts, so two
    starts can't both take the last place in the Conversation, for the IP address or in the
    budget."""
    await session.execute(
        select(Conversation.id).where(Conversation.id == conversation.id).with_for_update()
    )
    await session.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"calls:{agent.id}"))))
    open_here = await session.scalar(
        select(Call.id).where(Call.conversation_id == conversation.id, Call.ended_at.is_(None))
    )
    if open_here is not None:
        return CallRefusal.CALL_OPEN
    open_for_ip = await session.scalar(
        select(func.count())
        .select_from(Call)
        .join(Conversation, Conversation.id == Call.conversation_id)
        .where(Call.ip == ip, Call.ended_at.is_(None), Conversation.agent_id == agent.id)
    )
    if (open_for_ip or 0) >= CALLS_PER_IP:
        return CallRefusal.TOO_MANY_CALLS
    if await minutes_so_far(session, agent.id, now=now) >= agent.call_minutes_budget:
        return CallRefusal.MINUTES_SPENT
    return None


def _start_of_day(now: datetime) -> datetime:
    return datetime.combine(utc_date(now), time(), tzinfo=UTC)


async def budget_spent(
    session: AsyncSession,
    agent_id: uuid.UUID,
    *,
    mailer: Mailer,
    studio_url: str,
    now: datetime,
) -> None:
    """Raises the Agent's Call minutes alert for today and emails every Owner of its
    Organisation, once per Agent per UTC date: only the refusal that raises today's flag sends.
    A flag left from an earlier day counts as no flag."""
    raised = await session.scalar(
        update(Agent)
        .where(
            Agent.id == agent_id,
            or_(
                Agent.call_budget_exhausted_at.is_(None),
                Agent.call_budget_exhausted_at < _start_of_day(now),
            ),
        )
        .values(call_budget_exhausted_at=now)
        .returning(Agent.id)
    )
    await session.commit()
    if raised is None:
        return
    agent = await session.get_one(Agent, agent_id)
    owners = await session.execute(
        select(Member.name, Member.email)
        .join(Membership, Membership.member_id == Member.id)
        .where(Membership.organisation_id == agent.organisation_id, Membership.role == Role.OWNER)
        .order_by(Member.email)
    )
    link = templates.agent_link(
        studio_url, str(agent.organisation_id), str(agent.project_id), str(agent.id)
    )
    for name, email in owners:
        await mailer.send(
            templates.call_minutes_budget_spent(
                to=email,
                name=name,
                agent_name=agent.name,
                budget=agent.call_minutes_budget,
                link=link,
            )
        )


async def end_idle_calls(session: AsyncSession, *, now: datetime) -> int:
    """Ends every open Call past its Maximum Call length or silent for ``SILENCE``, for Beat;
    returns how many it ended. A Call another transaction holds (being ended, or locked by a
    turn, which then finds it open) is left for the next run."""
    rows = await session.execute(
        select(Call, Conversation)
        .join(Conversation, Conversation.id == Call.conversation_id)
        .where(Call.ended_at.is_(None))
        .with_for_update(of=Call, skip_locked=True)
    )
    ended = 0
    for call, conversation in rows:
        if await past_deadline(session, call, conversation, now=now):
            ended += 1
    await session.commit()
    return ended


@dataclass(frozen=True)
class CallMinutes:
    # The UTC date counted, today's.
    date: date
    # The Calls that ended today and the minutes so far of those still open, as admission
    # counts them.
    minutes_used: int
    call_minutes_budget: int
    exhausted: bool
    # Midnight UTC, when the next day's counter starts.
    resets_at: datetime


async def usage(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    *,
    now: datetime,
) -> CallMinutes:
    """Today's (UTC) Call minutes against the Agent's Call minutes budget, counted as admission
    counts them: spent once Calls are refused."""
    agent = (await get_agent(session, scope, project_id, agent_id)).agent
    today = utc_date(now)
    used = await minutes_so_far(session, agent.id, now=now)
    return CallMinutes(
        date=today,
        minutes_used=used,
        call_minutes_budget=agent.call_minutes_budget,
        exhausted=used >= agent.call_minutes_budget,
        resets_at=_start_of_day(now) + timedelta(days=1),
    )
