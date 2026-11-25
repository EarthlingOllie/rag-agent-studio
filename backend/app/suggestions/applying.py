"""Applying a Suggestion to the Draft, its Diff against the Draft, and deleting a Suggestion
(spec 16).

Each suggested change is compared with the Draft's current value of its setting: a Draft still
holding the change's base value takes the suggested value (``clean``), one already holding the
suggested value is left (``applied``), and anything else is a ``clash``. Applying is whole: any
clash refuses it (``SuggestionClashError``) and nothing is written; otherwise the merged
configuration is written in one ``replace_draft`` on the Draft revision the Editor reviewed, so
a Draft someone has changed since is the usual ``StaleDraftError``. Applying never Publishes;
the Draft moves to its next revision like any edit, so its Evaluation summary asks for a new Run.

A Suggestion made from a Version that is no longer Live is stale: its check was against the old
Live. It still applies. Applying records ``agent.suggestion_applied`` with the Suggestion and the
paths written (never their text) and stamps who applied it and when; deleting records
``agent.suggestion_deleted``. Both are refused for an archived Agent or Project; the Diff, a
read, is not.
"""

import enum
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.agents.config import AgentConfig
from app.agents.models import AgentDraft, AgentVersion
from app.agents.service import (
    AgentWithDraft,
    StaleDraftError,
    active_agent,
    get_agent,
    replace_draft,
    with_draft,
)
from app.projects.service import active_project
from app.suggestions.models import (
    IN_PROGRESS,
    SuggestedChange,
    Suggestion,
    SuggestionOutcome,
    SuggestionStatus,
)
from app.suggestions.proposer import setting_value, with_setting
from app.suggestions.service import SuggestionNotFoundError
from app.tenancy.repository import OrganisationScope

APPLIED = "agent.suggestion_applied"
DELETED = "agent.suggestion_deleted"


class ChangeState(enum.StrEnum):
    # The Draft still has the base value: applying writes the suggested value.
    CLEAN = "clean"
    # The Draft already has the suggested value: nothing to write.
    APPLIED = "applied"
    # The Draft has changed the setting some other way: the Editor resolves it by hand.
    CLASH = "clash"


class NothingToApplyError(Exception):
    """Only a completed Suggestion with a configuration change can be applied."""


class SuggestionRunningError(Exception):
    """A Suggestion run in progress can't be deleted; cancel it first."""


@dataclass(frozen=True)
class DiffRow:
    change: SuggestedChange
    # The Draft's current value of the setting.
    draft_value: Any
    state: ChangeState


class SuggestionClashError(Exception):
    """The Draft has changed a setting the Suggestion changes, some other way."""

    def __init__(self, clashes: list[DiffRow]) -> None:
        self.clashes = clashes


@dataclass(frozen=True)
class SuggestionDiff:
    suggestion: Suggestion
    base_version_number: int
    # The Draft revision the Diff was read on; send it back to apply.
    draft_revision: int
    # The base Version is no longer Live.
    stale: bool
    rows: list[DiffRow]


@dataclass(frozen=True)
class AppliedSuggestion:
    agent: AgentWithDraft
    # The setting paths written, in the Suggestion's order.
    paths: list[str]
    base_version_number: int
    stale: bool


def _rows(changes: list[SuggestedChange], draft: AgentConfig) -> list[DiffRow]:
    rows = []
    for change in changes:
        value = setting_value(draft, change.path)
        if value == change.base_value:
            state = ChangeState.CLEAN
        elif value == change.suggested_value:
            state = ChangeState.APPLIED
        else:
            state = ChangeState.CLASH
        rows.append(DiffRow(change, value, state))
    return rows


async def _suggestion(
    session: AsyncSession, found: AgentWithDraft, suggestion_id: uuid.UUID, *, lock: bool = False
) -> Suggestion:
    query = select(Suggestion).where(
        Suggestion.id == suggestion_id, Suggestion.agent_id == found.agent.id
    )
    suggestion = await session.scalar(query.with_for_update() if lock else query)
    if suggestion is None:
        raise SuggestionNotFoundError
    return suggestion


async def _changes(session: AsyncSession, suggestion: Suggestion) -> list[SuggestedChange]:
    return list(
        await session.scalars(
            select(SuggestedChange)
            .where(SuggestedChange.suggestion_id == suggestion.id)
            .order_by(SuggestedChange.position)
        )
    )


async def _base_number(session: AsyncSession, suggestion: Suggestion) -> int:
    return (await session.get_one(AgentVersion, suggestion.base_version_id)).number


def is_stale(suggestion: Suggestion, found: AgentWithDraft) -> bool:
    """Whether the Version the Suggestion was made from is no longer Live."""
    return found.agent.live_version_id != suggestion.base_version_id


async def diff_suggestion(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    suggestion_id: uuid.UUID,
) -> SuggestionDiff:
    """The Suggestion's changes against the Agent's current Draft, also an archived Agent's."""
    found = await get_agent(session, scope, project_id, agent_id)
    suggestion = await _suggestion(session, found, suggestion_id)
    rows = _rows(await _changes(session, suggestion), found.draft)
    return SuggestionDiff(
        suggestion,
        await _base_number(session, suggestion),
        found.draft_revision,
        is_stale(suggestion, found),
        rows,
    )


async def apply_suggestion(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    suggestion_id: uuid.UUID,
    *,
    base_revision: int,
    now: datetime,
) -> AppliedSuggestion:
    """Writes the Suggestion's clean changes into the Draft in one save on ``base_revision``.

    Refused for an archived Project or Agent, a Suggestion with no configuration change
    (``NothingToApplyError``), a Draft that has moved on from ``base_revision``
    (``StaleDraftError``), any clash (``SuggestionClashError``), and a merged Draft that no
    longer saves (``InvalidDraftError``); nothing is written when refused."""
    project = await active_project(session, scope, project_id)
    found = await active_agent(session, scope, project_id, agent_id)
    suggestion = await _suggestion(session, found, suggestion_id, lock=True)
    if (
        suggestion.status != SuggestionStatus.COMPLETED
        or suggestion.outcome != SuggestionOutcome.CHANGES
    ):
        raise NothingToApplyError
    agent = found.agent
    draft = await session.get_one(AgentDraft, agent.id, with_for_update=True)
    if draft.revision != base_revision:
        raise StaleDraftError(await with_draft(session, agent))
    rows = _rows(await _changes(session, suggestion), AgentConfig.model_validate(draft.config))
    clashes = [row for row in rows if row.state == ChangeState.CLASH]
    if clashes:
        raise SuggestionClashError(clashes)
    merged = draft.config
    paths = []
    for row in rows:
        if row.state == ChangeState.CLEAN:
            merged = with_setting(merged, row.change.path, row.change.suggested_value)
            paths.append(row.change.path)
    await replace_draft(
        session,
        scope,
        project,
        agent,
        AgentConfig.model_validate(merged),
        base_revision=base_revision,
        now=now,
    )
    suggestion.applied_by = scope.member_id
    suggestion.applied_at = now
    await audit.record(
        session,
        organisation_id=scope.organisation_id,
        actor_id=scope.member_id,
        action=APPLIED,
        target=audit.AuditTarget("agent", agent.id),
        after={"suggestion_id": str(suggestion.id), "paths": paths},
        occurred_at=now,
    )
    await session.commit()
    return AppliedSuggestion(
        await with_draft(session, agent),
        paths,
        await _base_number(session, suggestion),
        is_stale(suggestion, found),
    )


async def delete_suggestion(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    suggestion_id: uuid.UUID,
    *,
    now: datetime,
) -> None:
    """Deletes a finished Suggestion with its changes, gaps and evidence, recording
    ``agent.suggestion_deleted``. Refused for an archived Project or Agent, and for a run in
    progress (``SuggestionRunningError``)."""
    await active_project(session, scope, project_id)
    found = await active_agent(session, scope, project_id, agent_id)
    suggestion = await _suggestion(session, found, suggestion_id, lock=True)
    if suggestion.status in IN_PROGRESS:
        raise SuggestionRunningError
    await session.delete(suggestion)
    await audit.record(
        session,
        organisation_id=scope.organisation_id,
        actor_id=scope.member_id,
        action=DELETED,
        target=audit.AuditTarget("agent", found.agent.id),
        before={"suggestion_id": str(suggestion.id)},
        occurred_at=now,
    )
    await session.commit()
