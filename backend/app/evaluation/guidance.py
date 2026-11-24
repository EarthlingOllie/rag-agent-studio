"""Judging guidance (spec 19): the Organisation's own instructions to the Evaluation Model, added
to every judgement as an "Organisation guidance" section (``app.evaluation.judge``).

Each save is a new ``JudgingGuidanceVersion``, numbered from 1, made current on the Organisation
and recorded as ``organisation.judging_guidance_changed`` with before and after, in the same
transaction. Removing guidance saves an empty version. Saving the text already current changes
and records nothing. Saving locks the Organisation's row, so two saves can't take one number.
Only Owners save, which the routes enforce; every Member reads.

A judgement records the version current when it starts, beside its judge model: its Judging
setup. ``guidance_text`` reads a recorded version's text back for judging; ``current_setup`` is
the Judging setup a judgement started now would record, which comparisons (the Live score drop
alert, the Publish summary) hold earlier judgements against. ``judging_setup_changes`` lists
when the Organisation's Judging setup changed (guidance saved or removed, the Evaluation Model
chosen or dropped) and ``mixed_judging_setups`` whether an Agent's Live Verdicts in a range were
judged under more than one, for the Version comparison and the Time series.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.audit.models import AuditEvent
from app.conversations.models import Message
from app.evaluation.models import GuidanceSource, JudgingGuidanceVersion, LiveStatus, LiveVerdict
from app.evaluation.settings import EVALUATION_MODEL_CHANGED, judge_model
from app.tenancy.models import Member, Organisation
from app.tenancy.repository import OrganisationScope

JUDGING_GUIDANCE_CHANGED = "organisation.judging_guidance_changed"


@dataclass(frozen=True)
class SavedVersion:
    version: JudgingGuidanceVersion
    # The name of the Member who saved it; None once they are deleted.
    saved_by_name: str | None


@dataclass(frozen=True)
class Guidance:
    # None until guidance is first saved.
    current: SavedVersion | None
    # Newest first.
    versions: list[SavedVersion]


async def read_guidance(session: AsyncSession, organisation_id: uuid.UUID) -> Guidance:
    """The current Judging guidance version and every version, newest first."""
    current = await current_version(session, organisation_id)
    rows = await session.execute(
        select(JudgingGuidanceVersion, Member.name)
        .outerjoin(Member, Member.id == JudgingGuidanceVersion.saved_by)
        .where(JudgingGuidanceVersion.organisation_id == organisation_id)
        .order_by(JudgingGuidanceVersion.version.desc())
    )
    versions = [SavedVersion(version, name) for version, name in rows]
    return Guidance(
        next((v for v in versions if v.version.version == current), None),
        versions,
    )


async def current_version(session: AsyncSession, organisation_id: uuid.UUID) -> int | None:
    """The number of the Organisation's current Judging guidance version, for a judgement to
    record; None until guidance is first saved."""
    return await session.scalar(
        select(Organisation.judging_guidance_version).where(Organisation.id == organisation_id)
    )


async def guidance_text(
    session: AsyncSession, organisation_id: uuid.UUID, version: int | None
) -> str:
    """The text of the Organisation's guidance version ``version``; empty for none."""
    if version is None:
        return ""
    text = await session.scalar(
        select(JudgingGuidanceVersion.text).where(
            JudgingGuidanceVersion.organisation_id == organisation_id,
            JudgingGuidanceVersion.version == version,
        )
    )
    return text or ""


@dataclass(frozen=True)
class JudgingSetup:
    """The Evaluation Model (its provider and model) and the Judging guidance version it judges
    with; None for the version when the Organisation had never saved guidance."""

    judge_provider: str
    judge_model: str
    guidance_version: int | None


async def current_setup(session: AsyncSession, organisation_id: uuid.UUID) -> JudgingSetup | None:
    """The Judging setup a judgement started now would record; None when the Organisation has
    no model to judge with."""
    chosen = await judge_model(session, organisation_id)
    version = await current_version(session, organisation_id)
    return (
        None if chosen is None else JudgingSetup(chosen.credential.provider, chosen.model, version)
    )


@dataclass(frozen=True)
class JudgingSetupChange:
    """One change of the Organisation's Judging setup: guidance saved (``guidance_version``, or
    removed), or the Evaluation Model chosen (``evaluation_model``, the model's ID) or dropped
    for the Default Model (None)."""

    occurred_at: datetime
    kind: Literal["guidance", "evaluation_model"]
    guidance_version: int | None
    guidance_removed: bool
    evaluation_model: str | None


def _change(event: AuditEvent) -> JudgingSetupChange:
    if event.action == JUDGING_GUIDANCE_CHANGED:
        # A guidance save always has an after: removing saves an empty version.
        saved: dict[str, Any] = event.after or {}
        return JudgingSetupChange(
            event.occurred_at, "guidance", saved["version"], saved["text"] == "", None
        )
    model = None if event.after is None else event.after["model"]
    return JudgingSetupChange(event.occurred_at, "evaluation_model", None, False, model)


async def judging_setup_changes(
    session: AsyncSession, organisation_id: uuid.UUID, since: datetime, until: datetime
) -> list[JudgingSetupChange]:
    """The Organisation's Judging setup changes from ``since`` until before ``until``, oldest
    first, read from their Audit Events."""
    events = await session.scalars(
        select(AuditEvent)
        .where(
            AuditEvent.organisation_id == organisation_id,
            AuditEvent.action.in_([JUDGING_GUIDANCE_CHANGED, EVALUATION_MODEL_CHANGED]),
            AuditEvent.occurred_at >= since,
            AuditEvent.occurred_at < until,
        )
        .order_by(AuditEvent.occurred_at, AuditEvent.sequence)
    )
    return [_change(event) for event in events]


async def mixed_judging_setups(
    session: AsyncSession,
    agent_id: uuid.UUID,
    version_ids: Sequence[uuid.UUID] | None,
    since: datetime,
    until: datetime,
) -> bool:
    """Whether the Agent's judged Live Verdicts on replies from ``since`` until before
    ``until`` (of ``version_ids`` only, when given) were judged under more than one Judging
    setup."""
    query = (
        select(
            LiveVerdict.judge_provider,
            LiveVerdict.judge_model,
            LiveVerdict.judging_guidance_version,
        )
        .join(Message, Message.id == LiveVerdict.message_id)
        .where(
            LiveVerdict.agent_id == agent_id,
            LiveVerdict.status == LiveStatus.JUDGED,
            Message.created_at >= since,
            Message.created_at < until,
        )
        .distinct()
    )
    if version_ids is not None:
        query = query.where(LiveVerdict.agent_version_id.in_(version_ids))
    setups = await session.scalar(select(func.count()).select_from(query.subquery()))
    return (setups or 0) > 1


def _summary(version: JudgingGuidanceVersion | None) -> dict[str, object] | None:
    return None if version is None else {"version": version.version, "text": version.text}


async def save_guidance(
    session: AsyncSession, scope: OrganisationScope, text: str, *, now: datetime
) -> Guidance:
    """Saves ``text`` (trimmed; empty removes guidance) as the Organisation's new current
    version, unless it is the current text already."""
    text = text.strip()
    organisation = (
        await session.scalars(
            select(Organisation).where(Organisation.id == scope.organisation_id).with_for_update()
        )
    ).one()
    before = await session.scalar(
        select(JudgingGuidanceVersion).where(
            JudgingGuidanceVersion.organisation_id == scope.organisation_id,
            JudgingGuidanceVersion.version == organisation.judging_guidance_version,
        )
    )
    if (before.text if before is not None else "") != text:
        after = JudgingGuidanceVersion(
            organisation_id=scope.organisation_id,
            version=(organisation.judging_guidance_version or 0) + 1,
            text=text,
            source=GuidanceSource.WRITTEN,
            saved_by=scope.member_id,
            saved_at=now,
        )
        session.add(after)
        await session.flush()
        organisation.judging_guidance_version = after.version
        await audit.record(
            session,
            organisation_id=scope.organisation_id,
            actor_id=scope.member_id,
            action=JUDGING_GUIDANCE_CHANGED,
            target=audit.AuditTarget("organisation", scope.organisation_id),
            before=_summary(before),
            after=_summary(after),
            occurred_at=now,
        )
        await session.commit()
    return await read_guidance(session, scope.organisation_id)
