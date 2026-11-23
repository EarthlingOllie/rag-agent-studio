"""The Evaluation budget (spec 15): the most an Organisation's Live Verdicts may spend in US
dollars per calendar month (UTC), set by Owners in Organisation settings (Models).

There is none by default, and without one no reply is sampled; an Agent's Live sample rate can't
be raised above 0% either (``app.embed.service``). Each month has its own spend record, created by
the month's first judgement, so a new month starts from nothing without a job. A judgement adds
its frozen Cost to the record with one atomic update; the judgement that takes the spend to or
past the budget marks the record, in the same update that finds it unmarked, and its Owners are
emailed once for the month. Sampling reads the record: once the spend reaches the budget, no
reply is chosen until the budget is raised or the month ends. Judgements already pending still
finish, so the spend can pass the budget by at most the judgements in flight.

Only Live Verdicts count. Evaluation Runs are never capped by the budget and don't add to it.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.evaluation.models import EvaluationSpend
from app.mail import templates
from app.mail.port import Mailer
from app.tenancy.models import Member, Membership, Organisation, Role
from app.tenancy.repository import OrganisationScope

EVALUATION_BUDGET_CHANGED = "organisation.evaluation_budget_changed"


def month_of(moment: datetime) -> date:
    """The first day of the calendar month (UTC) the moment falls in."""
    return moment.astimezone(UTC).date().replace(day=1)


def _next_month(month: date) -> date:
    return (
        month.replace(year=month.year + 1, month=1)
        if month.month == 12
        else month.replace(month=month.month + 1)
    )


@dataclass(frozen=True)
class EvaluationBudget:
    """The Organisation's Evaluation budget (None: none) and this month's spend against it."""

    budget_usd: Decimal | None
    month: date
    spent_usd: Decimal

    @property
    def exhausted(self) -> bool:
        """Whether the month's spend has reached the budget, so sampling is paused."""
        return self.budget_usd is not None and self.spent_usd >= self.budget_usd

    @property
    def allows_sampling(self) -> bool:
        return self.budget_usd is not None and not self.exhausted

    @property
    def resets_at(self) -> datetime:
        """Midnight UTC on the 1st of the next month, when a new month's spend starts."""
        return datetime.combine(_next_month(self.month), time(), tzinfo=UTC)


async def read_budget(
    session: AsyncSession, organisation_id: uuid.UUID, now: datetime
) -> EvaluationBudget:
    """The budget and the spend of the month ``now`` falls in."""
    month = month_of(now)
    budget_usd = await session.scalar(
        select(Organisation.evaluation_budget_usd).where(Organisation.id == organisation_id)
    )
    spent = await session.scalar(
        select(EvaluationSpend.spent_usd).where(
            EvaluationSpend.organisation_id == organisation_id, EvaluationSpend.month == month
        )
    )
    return EvaluationBudget(budget_usd, month, Decimal(0) if spent is None else spent)


def _dollars(amount: Decimal | None) -> str | None:
    return None if amount is None else format(amount, ".2f")


async def set_budget(
    session: AsyncSession, scope: OrganisationScope, budget_usd: Decimal | None, *, now: datetime
) -> EvaluationBudget:
    """Sets the Evaluation budget, or with None removes it, which stops all sampling (the Live
    sample rates stay as they are). Raising it resumes sampling at the next reply. A change is
    recorded as ``organisation.evaluation_budget_changed`` with before and after; setting the
    budget in force records nothing. Only Owners set it, which the route enforces."""
    organisation = (
        await session.scalars(
            select(Organisation).where(Organisation.id == scope.organisation_id).with_for_update()
        )
    ).one()
    before = organisation.evaluation_budget_usd
    if before != budget_usd:
        organisation.evaluation_budget_usd = budget_usd
        await audit.record(
            session,
            organisation_id=scope.organisation_id,
            actor_id=scope.member_id,
            action=EVALUATION_BUDGET_CHANGED,
            target=audit.AuditTarget("organisation", scope.organisation_id),
            before={"evaluation_budget_usd": _dollars(before)},
            after={"evaluation_budget_usd": _dollars(budget_usd)},
            occurred_at=now,
        )
        await session.commit()
    return await read_budget(session, scope.organisation_id, now)


async def has_budget(session: AsyncSession, organisation_id: uuid.UUID) -> bool:
    budget_usd = await session.scalar(
        select(Organisation.evaluation_budget_usd).where(Organisation.id == organisation_id)
    )
    return budget_usd is not None


async def add_spend(
    session: AsyncSession, organisation_id: uuid.UUID, cost_usd: Decimal, now: datetime
) -> bool:
    """Adds a judgement's Cost to the month's spend, atomically, in the caller's transaction.
    True when this judgement took the spend to or past the budget first this month: its
    Owners are to be emailed (``email_owners``) once the transaction commits."""
    month = month_of(now)
    spent = await session.scalar(
        insert(EvaluationSpend)
        .values(id=uuid.uuid4(), organisation_id=organisation_id, month=month, spent_usd=cost_usd)
        .on_conflict_do_update(
            index_elements=[EvaluationSpend.organisation_id, EvaluationSpend.month],
            set_={"spent_usd": EvaluationSpend.spent_usd + cost_usd},
        )
        .returning(EvaluationSpend.spent_usd)
    )
    budget_usd = await session.scalar(
        select(Organisation.evaluation_budget_usd).where(Organisation.id == organisation_id)
    )
    if budget_usd is None or spent is None or spent < budget_usd:
        return False
    # Only the first judgement to find the record unmarked emails.
    marked = await session.scalar(
        update(EvaluationSpend)
        .where(
            EvaluationSpend.organisation_id == organisation_id,
            EvaluationSpend.month == month,
            EvaluationSpend.budget_spent_emailed_at.is_(None),
        )
        .values(budget_spent_emailed_at=now)
        .returning(EvaluationSpend.id)
    )
    return marked is not None


async def email_owners(
    session: AsyncSession,
    organisation_id: uuid.UUID,
    now: datetime,
    *,
    mailer: Mailer,
    studio_url: str,
) -> None:
    """Emails every Owner that the month's Evaluation budget is spent and sampling has paused."""
    found = await read_budget(session, organisation_id, now)
    owners = await session.execute(
        select(Member.name, Member.email)
        .join(Membership, Membership.member_id == Member.id)
        .where(Membership.organisation_id == organisation_id, Membership.role == Role.OWNER)
        .order_by(Member.email)
    )
    link = templates.models_settings_link(studio_url, str(organisation_id))
    for name, email in owners:
        await mailer.send(
            templates.evaluation_budget_spent(
                to=email,
                name=name,
                budget=f"${_dollars(found.budget_usd)}",
                resets_on=found.resets_at.date(),
                link=link,
            )
        )
