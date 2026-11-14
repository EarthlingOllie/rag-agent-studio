"""API seam: the Evaluation summary for Publish. Given the Instructions Version the Publish dialog
has chosen, it says whether the Draft has been evaluated against the current Live Version with
those Instructions, and warns about Regressions or a lower Evaluation score. It never blocks
Publishing: the Publish endpoint is unchanged, and Publishing succeeds in every state.

As in ``test_evaluation_sides``, the sides answer through the real Guardrails and retrieval with
a scripted ``FunctionModel`` and the fake judge, and the Run's task runs eagerly.
"""

import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo

from app.evaluation import api as evaluation_api
from tests.agents import StreamFunction
from tests.conftest import SignedUpMember, TenantFactory
from tests.integration.test_agent_versions import published
from tests.integration.test_evaluation import (
    FAILING,
    PASSING,
    add_case,
    evaluation_path,
    judge_with,
)
from tests.integration.test_evaluation_settings import set_repeats
from tests.integration.test_evaluation_sides import (
    DRAFT,
    LIVE,
    answering,
    cancel,
    evaluated,
    live_and_draft,
    prompted,
    start,
    unsent,
)
from tests.integration.test_playground import ready_agent
from tests.integration.test_project_instructions_versions import published as instructions


async def summary(
    member: SignedUpMember,
    project_id: str,
    agent_id: str,
    instructions_version_id: str | None = None,
) -> dict[str, Any]:
    params = (
        {}
        if instructions_version_id is None
        else {"instructions_version_id": instructions_version_id}
    )
    response = await member.client.get(
        evaluation_path(member, project_id, agent_id, "publish-summary"), params=params
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def publishes(member: SignedUpMember, project_id: str, agent_id: str, **body: Any) -> None:
    """Publishing still succeeds, whatever the summary says."""
    await published(member, project_id, agent_id, **body)


__all__ = ["unsent"]

TABLE = {
    (LIVE, "Same?"): PASSING,
    (DRAFT, "Same?"): PASSING,
    (LIVE, "Broken?"): PASSING,
    (DRAFT, "Broken?"): FAILING,
}


async def test_an_agent_without_a_set_has_no_set_and_still_publishes(
    app: FastAPI, owner: SignedUpMember
) -> None:
    _, project_id, agent_id = await ready_agent(app, owner)

    found = await summary(owner, project_id, agent_id)

    assert found == {
        "state": "no_set",
        "run": None,
        "regressions": [],
        "lower_score": False,
        "evaluated_live_version_number": None,
        "publishing_instructions_version_number": None,
    }
    await publishes(owner, project_id, agent_id)


async def test_a_set_without_a_qualifying_run_has_no_run(
    app: FastAPI, owner: SignedUpMember, unsent: list[uuid.UUID]
) -> None:
    project_id, agent_id, _ = await live_and_draft(app, owner)
    await add_case(owner, project_id, agent_id, "Same?")
    # A Run in progress, or cancelled, doesn't qualify.
    queued = await start(owner, project_id, agent_id)
    assert queued.status_code == 202, queued.text
    assert (await summary(owner, project_id, agent_id))["state"] == "no_run"
    await cancel(owner, project_id, agent_id, queued.json()["id"])

    found = await summary(owner, project_id, agent_id)

    assert (found["state"], found["run"], found["regressions"]) == ("no_run", None, [])
    await publishes(owner, project_id, agent_id)


async def test_runs_that_are_not_live_against_the_draft_do_not_qualify(
    app: FastAPI, owner: SignedUpMember
) -> None:
    judge_with(app, answering(TABLE))
    project_id, agent_id, version = await live_and_draft(app, owner)
    await add_case(owner, project_id, agent_id, "Same?")
    v1 = {"kind": "version", "version_id": version["id"]}
    for sides in ([v1], [{"kind": "draft"}, v1], [{"kind": "draft"}]):
        await evaluated(owner, project_id, agent_id, {"sides": sides})

    assert (await summary(owner, project_id, agent_id))["state"] == "no_run"


async def test_regressions_are_listed_with_their_verdicts_reasons_and_publishing_succeeds(
    app: FastAPI, owner: SignedUpMember
) -> None:
    judge_with(app, answering(TABLE))
    project_id, agent_id, _ = await live_and_draft(app, owner)
    await set_repeats(owner, 3)
    await add_case(owner, project_id, agent_id, "Same?")
    broken = await add_case(owner, project_id, agent_id, "Broken?")
    run = (await evaluated(owner, project_id, agent_id))["run"]

    found = await summary(owner, project_id, agent_id)

    assert found["state"] == "regressions"
    assert found["run"]["id"] == run["id"]
    assert [(s["kind"], s["version_number"], s["score"]) for s in found["run"]["sides"]] == [
        ("version", 1, 1.0),
        ("draft", None, 0.5),
    ]
    assert found["lower_score"] is True
    (regression,) = found["regressions"]
    assert (regression["case_id"], regression["question"]) == (broken["id"], "Broken?")
    assert regression["reasons"]
    assert {reason["kind"] for reason in regression["reasons"]} <= {
        "reference_answer",
        "grounding",
    }
    assert all(reason["reason"] for reason in regression["reasons"])
    # Each repeat failed for the same reasons: each is listed once.
    reasons = [(reason["kind"], reason["reason"]) for reason in regression["reasons"]]
    assert len(reasons) == len(set(reasons))
    await publishes(owner, project_id, agent_id)


def answering_or_failing(table: dict[tuple[str, str], str | int]) -> StreamFunction:
    """As ``answering``, where an ``int`` is an HTTP status the provider fails with."""

    async def stream(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
        given = " ".join(
            str(getattr(part, "content", "")) for message in messages for part in message.parts
        )
        (answer,) = [
            answer
            for (marker, question), answer in table.items()
            if marker in given and question in given
        ]
        if isinstance(answer, int):
            raise ModelHTTPError(status_code=answer, model_name="gpt-4.1-mini")
        yield answer

    return stream


async def test_a_lower_draft_score_warns_even_without_a_regression(
    app: FastAPI, owner: SignedUpMember
) -> None:
    # Live errors on one case, so it is left out of Live's score and can't be a Regression.
    judge_with(
        app,
        answering_or_failing(
            {
                (LIVE, "Same?"): PASSING,
                (DRAFT, "Same?"): PASSING,
                (LIVE, "Errored?"): 503,
                (DRAFT, "Errored?"): FAILING,
            }
        ),
    )
    project_id, agent_id, _ = await live_and_draft(app, owner)
    await add_case(owner, project_id, agent_id, "Same?")
    await add_case(owner, project_id, agent_id, "Errored?")
    await evaluated(owner, project_id, agent_id)

    found = await summary(owner, project_id, agent_id)

    assert (found["state"], found["regressions"], found["lower_score"]) == (
        "regressions",
        [],
        True,
    )
    await publishes(owner, project_id, agent_id)


async def test_a_run_with_no_regression_and_no_lower_score_is_clear(
    app: FastAPI, owner: SignedUpMember
) -> None:
    judge_with(app, answering(TABLE))
    project_id, agent_id, _ = await live_and_draft(app, owner)
    await add_case(owner, project_id, agent_id, "Same?")
    await evaluated(owner, project_id, agent_id)

    found = await summary(owner, project_id, agent_id)

    assert (found["state"], found["regressions"], found["lower_score"]) == ("clear", [], False)
    await publishes(owner, project_id, agent_id)


async def test_a_never_published_agents_draft_alone_qualifies(
    app: FastAPI, owner: SignedUpMember
) -> None:
    judge_with(app, answering({(DRAFT, "Same?"): PASSING}))
    _, project_id, agent_id = await ready_agent(app, owner)
    await set_repeats(owner, 1)
    await prompted(owner, project_id, agent_id, DRAFT)
    await add_case(owner, project_id, agent_id, "Same?")
    await evaluated(owner, project_id, agent_id)

    found = await summary(owner, project_id, agent_id)

    assert found["state"] == "clear"
    assert [s["kind"] for s in found["run"]["sides"]] == ["draft"]
    assert found["lower_score"] is False
    await publishes(owner, project_id, agent_id)


async def test_a_run_goes_stale_once_the_draft_has_a_newer_revision(
    app: FastAPI, owner: SignedUpMember
) -> None:
    judge_with(app, answering({**TABLE, (DRAFT + " Still.", "Same?"): PASSING}))
    project_id, agent_id, _ = await live_and_draft(app, owner)
    await add_case(owner, project_id, agent_id, "Same?")
    run = (await evaluated(owner, project_id, agent_id))["run"]
    await prompted(owner, project_id, agent_id, DRAFT + " Still.")

    found = await summary(owner, project_id, agent_id)

    assert (found["state"], found["run"]["id"], found["run"]["stale"]) == (
        "stale",
        run["id"],
        True,
    )
    await publishes(owner, project_id, agent_id)


async def test_live_changed_once_the_run_compared_with_a_version_no_longer_live(
    app: FastAPI, owner: SignedUpMember
) -> None:
    judge_with(app, answering(TABLE))
    project_id, agent_id, _ = await live_and_draft(app, owner)
    await add_case(owner, project_id, agent_id, "Same?")
    await evaluated(owner, project_id, agent_id)
    await published(owner, project_id, agent_id)

    found = await summary(owner, project_id, agent_id)

    assert (found["state"], found["run"], found["evaluated_live_version_number"]) == (
        "live_changed",
        None,
        1,
    )
    await publishes(owner, project_id, agent_id)


async def test_a_draft_run_alone_does_not_qualify_once_the_agent_is_live(
    app: FastAPI, owner: SignedUpMember
) -> None:
    judge_with(app, answering({(DRAFT, "Same?"): PASSING}))
    _, project_id, agent_id = await ready_agent(app, owner)
    await set_repeats(owner, 1)
    await prompted(owner, project_id, agent_id, DRAFT)
    await add_case(owner, project_id, agent_id, "Same?")
    await evaluated(owner, project_id, agent_id)
    await published(owner, project_id, agent_id)

    found = await summary(owner, project_id, agent_id)

    assert (found["state"], found["evaluated_live_version_number"]) == ("no_run", None)


async def test_instructions_differ_when_publishing_with_other_instructions(
    app: FastAPI, owner: SignedUpMember
) -> None:
    judge_with(app, answering(TABLE))
    project_id, agent_id, _ = await live_and_draft(app, owner)
    v1 = await instructions(owner, project_id, "Answer briefly.", "Brief")
    v2 = await instructions(owner, project_id, "Answer kindly.", "Kind")
    await add_case(owner, project_id, agent_id, "Same?")
    # The Draft answers with the Current Instructions Version, v2.
    await evaluated(owner, project_id, agent_id)

    current = await summary(owner, project_id, agent_id)
    chosen = await summary(owner, project_id, agent_id, v2["id"])
    other = await summary(owner, project_id, agent_id, v1["id"])

    assert (current["state"], current["publishing_instructions_version_number"]) == ("clear", 2)
    assert chosen["state"] == "clear"
    assert (other["state"], other["publishing_instructions_version_number"]) == (
        "instructions_differ",
        1,
    )
    assert other["run"]["sides"][1]["instructions_version_number"] == 2
    await publishes(owner, project_id, agent_id, instructions_version_id=v1["id"])


async def test_a_run_with_the_instructions_draft_differs_from_any_version(
    app: FastAPI, owner: SignedUpMember
) -> None:
    judge_with(app, answering(TABLE))
    project_id, agent_id, _ = await live_and_draft(app, owner)
    await add_case(owner, project_id, agent_id, "Same?")
    await evaluated(owner, project_id, agent_id, {"instructions_draft": True})

    found = await summary(owner, project_id, agent_id)

    # The Project has no Instructions Version: publishing pins none.
    assert (found["state"], found["publishing_instructions_version_number"]) == (
        "instructions_differ",
        None,
    )


async def test_the_summary_is_refused_for_foreign_instructions_and_other_organisations(
    app: FastAPI, owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    _, project_id, agent_id = await ready_agent(app, owner)
    path = evaluation_path(owner, project_id, agent_id, "publish-summary")

    foreign = await owner.client.get(path, params={"instructions_version_id": str(uuid.uuid4())})

    assert (foreign.status_code, foreign.json()) == (
        422,
        {"detail": evaluation_api.INSTRUCTIONS_NOT_FOUND},
    )
    stranger = await tenant_factory()
    hidden = await stranger.client.get(
        evaluation_path(stranger, project_id, agent_id, "publish-summary")
    )
    assert hidden.status_code == 404
