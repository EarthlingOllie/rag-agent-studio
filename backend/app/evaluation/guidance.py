"""Judging guidance (spec 19): the Organisation's own instructions to the Evaluation Model, added
to every judgement as an "Organisation guidance" section (``app.evaluation.judge``).

Each save is a new ``JudgingGuidanceVersion``, numbered from 1, made current on the Organisation
and recorded as ``organisation.judging_guidance_changed`` with before and after, in the same
transaction. Removing guidance saves an empty version. Saving the text already current changes
and records nothing. Saving locks the Organisation's row, so two saves can't take one number.
Only Owners save, which the routes enforce; every Member reads.

A judgement records the version current when it starts, beside its judge model: its Judging
setup. ``guidance_text`` reads a recorded version's text back for judging.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.evaluation.models import GuidanceSource, JudgingGuidanceVersion
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
