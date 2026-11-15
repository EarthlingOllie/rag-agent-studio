"""Rollout evaluation routes, under a Project Instructions Version: start a Rollout evaluation of
the selected Agents, and read each Agent's state for the rollout dialog. Editors and Owners may
use them; another Organisation's Projects are not found.

Starting runs, for each selected Agent with an Evaluation Set, the Live Version as it is against
its Live configuration answering with the Instructions Version; the others are skipped. The
Runs appear in each Agent's Run history. The read says, per Agent, ``regressions`` (listed with
their Verdicts' reasons), ``not_evaluated``, ``running`` or ``clear``. It is advisory: Bulk
publish is unchanged and never blocked.
"""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.agents.api import NOT_FOUND_RESPONSE, archived, not_found
from app.agents.bulk_api import BULK_MAX
from app.agents.resolution import NoDefaultModelError
from app.auth.api import Db, ErrorResponse
from app.evaluation import rollout
from app.evaluation.api import ClockDep, RunOut, SummaryRegressionOut, _reasons, _run_out
from app.evaluation.tasks import enqueue_run
from app.playground.api import NO_DEFAULT_MODEL
from app.projects.instructions import InstructionsVersionNotFoundError
from app.projects.service import ProjectArchivedError, ProjectNotFoundError
from app.tenancy.api import ORGANISATION_PREFIX
from app.tenancy.policy import Scope

router = APIRouter(
    prefix=ORGANISATION_PREFIX
    + "/projects/{project_id}/instructions/versions/{instructions_version_id}/evaluation",
    tags=["evaluation"],
)


def rollout_in_progress(name: str) -> str:
    return (
        f"{name} already has an Evaluation Run in progress. Wait for it to finish, or cancel it, "
        "then evaluate the rollout again."
    )


def rollout_credential_gone(name: str) -> str:
    return (
        f"{name}'s Live Version uses a Provider Credential that no longer exists, so it can't be "
        "evaluated. Leave it out of the Rollout evaluation."
    )


class RolloutEvaluationIn(BaseModel):
    # The Agents selected in the rollout dialog.
    agent_ids: Annotated[list[uuid.UUID], Field(min_length=1, max_length=BULK_MAX)]


class RolloutAgentEvaluationOut(BaseModel):
    agent_id: uuid.UUID
    name: str
    # ``regressions``, ``clear``, ``running``, or ``not_evaluated``: no Evaluation Set, never
    # published, or no Rollout evaluation of its Live Version with these Instructions.
    state: Literal["not_evaluated", "running", "regressions", "clear"]
    # Whether it has an Evaluation Set.
    has_set: bool
    # The Rollout evaluation the state comes from, with its progress and scores; null while
    # not evaluated.
    run: RunOut | None
    # Its Regressions (pass with the Live Version, fail with the new Instructions), in set
    # order, with why each failed.
    regressions: list[SummaryRegressionOut]


class RolloutEvaluationOut(BaseModel):
    """Each Agent's Rollout evaluation of the Instructions Version. Advisory: Bulk publish never
    depends on it."""

    instructions_version_number: int
    # The Project's active Agents asked about, oldest first.
    agents: list[RolloutAgentEvaluationOut]


def _out(found: rollout.Rollout) -> RolloutEvaluationOut:
    agents: list[RolloutAgentEvaluationOut] = []
    for each in found.agents:
        run = each.run
        agents.append(
            RolloutAgentEvaluationOut(
                agent_id=each.agent.id,
                name=each.agent.name,
                state=each.state,
                has_set=each.has_set,
                run=None if run is None else _run_out(run),
                regressions=[]
                if run is None
                else [
                    SummaryRegressionOut(
                        case_id=case.case.case_id,
                        question=case.case.question,
                        reasons=_reasons(case, run.sides[-1].id),
                    )
                    for case in each.regressions
                ],
            )
        )
    return RolloutEvaluationOut(
        instructions_version_number=found.instructions.number, agents=agents
    )


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="startRolloutEvaluation",
    responses={
        **NOT_FOUND_RESPONSE,
        409: {
            "model": ErrorResponse,
            "description": (
                "The Project is archived, a selected Agent already has a Run in progress or its "
                "Live Version names a Provider Credential that no longer exists (then nothing "
                "is started), or there is no Default Model."
            ),
        },
    },
)
async def start_rollout_evaluation(
    project_id: uuid.UUID,
    instructions_version_id: uuid.UUID,
    body: RolloutEvaluationIn,
    scope: Scope,
    db: Db,
    clock: ClockDep,
) -> RolloutEvaluationOut:
    """Starts a Rollout evaluation of each selected Agent with an Evaluation Set, skipping the
    others, and returns the selected Agents' states. Poll the read until none is running."""
    try:
        run_ids = await rollout.start_rollout(
            db, scope, project_id, instructions_version_id, body.agent_ids, now=clock.now()
        )
    except (ProjectNotFoundError, InstructionsVersionNotFoundError):
        raise not_found() from None
    except ProjectArchivedError:
        raise archived() from None
    except rollout.RolloutInProgressError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, rollout_in_progress(error.name)) from None
    except rollout.RolloutCredentialGoneError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, rollout_credential_gone(error.name)) from None
    except NoDefaultModelError:
        raise HTTPException(status.HTTP_409_CONFLICT, NO_DEFAULT_MODEL) from None
    for run_id in run_ids:
        await enqueue_run(run_id)
    # When tasks run eagerly the Runs have moved on in other sessions: read them afresh.
    db.expire_all()
    return _out(
        await rollout.rollout(db, scope, project_id, instructions_version_id, body.agent_ids)
    )


@router.get("", operation_id="getRolloutEvaluation", responses=NOT_FOUND_RESPONSE)
async def get_rollout_evaluation(
    project_id: uuid.UUID,
    instructions_version_id: uuid.UUID,
    scope: Scope,
    db: Db,
    agent_id: Annotated[list[uuid.UUID] | None, Query(max_length=BULK_MAX)] = None,
) -> RolloutEvaluationOut:
    """Each named Agent's (every active Agent's when none is named) Rollout evaluation state
    for the Instructions Version: ``regressions``, ``not_evaluated``, ``running`` or
    ``clear``."""
    try:
        found = await rollout.rollout(db, scope, project_id, instructions_version_id, agent_id)
    except (ProjectNotFoundError, InstructionsVersionNotFoundError):
        raise not_found() from None
    return _out(found)
