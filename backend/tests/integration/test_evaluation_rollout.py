"""API seam: Rollout evaluation. Before rolling a Project Instructions Version out with Bulk
publish, an Editor starts one Run per selected Agent with an Evaluation Set: the Live Version as
it is against its Live configuration answering with the new Instructions Version. A read gives
each Agent's state for the rollout dialog: Regressions, not evaluated, running or clear. It never
blocks the rollout.

As in ``test_evaluation_sides``, the sides answer through the real Guardrails and retrieval with
a scripted ``FunctionModel`` and the fake judge, and the Runs' tasks run eagerly.
"""

import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo

from app.evaluation import api as evaluation_api
from app.evaluation import rollout_api
from tests.agents import AUTOMATIC, create_automatic_agent, save_draft
from tests.conftest import MemberFactory, SignedUpMember, TenantFactory
from tests.documents import create_project, project_path
from tests.integration.test_agent_archive import archive
from tests.integration.test_agent_versions import agent, published
from tests.integration.test_evaluation import FAILING, PASSING, add_case, judge_with
from tests.integration.test_evaluation_publish import summary
from tests.integration.test_evaluation_settings import set_repeats
from tests.integration.test_evaluation_sides import (
    DRAFT,
    LIVE,
    cancel,
    prompted,
    results_of,
    sides,
    start,
)
from tests.integration.test_playground import delete_credential_row, echo, ready_agent
from tests.integration.test_project_instructions_versions import published as instructions
from tests.integration.test_projects import archive as archive_project
from tests.integration.test_provider_credentials import ANTHROPIC_KEY, added


@pytest.fixture
def unsent(monkeypatch: pytest.MonkeyPatch) -> list[uuid.UUID]:
    """Runs stay queued: their tasks aren't sent. Yields the Runs that would have been."""
    sent: list[uuid.UUID] = []

    async def enqueue(run_id: uuid.UUID) -> None:
        sent.append(run_id)

    monkeypatch.setattr(evaluation_api, "enqueue_run", enqueue)
    monkeypatch.setattr(rollout_api, "enqueue_run", enqueue)
    return sent


BRIEF = "Answer briefly."
KIND = "Answer kindly."


def answering(table: dict[tuple[str, str], str]) -> Any:
    """Answers with ``table[(instructions, question)]``. Rollout evaluation runs the Live
    configuration, so an answer given with the Draft's prompt fails the test."""

    async def stream(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
        given = " ".join(
            str(getattr(part, "content", "")) for message in messages for part in message.parts
        )
        assert LIVE in given
        assert DRAFT not in given
        (answer,) = [
            answer
            for (marker, question), answer in table.items()
            if marker in given and question in given
        ]
        yield answer

    return stream


TABLE = {
    (BRIEF, "Same?"): PASSING,
    (KIND, "Same?"): PASSING,
    (BRIEF, "Broken?"): PASSING,
    (KIND, "Broken?"): FAILING,
}


def rollout_path(member: SignedUpMember, project_id: str, version_id: str) -> str:
    return project_path(member, project_id) + f"/instructions/versions/{version_id}/evaluation"


async def start_rollout(
    member: SignedUpMember, project_id: str, version_id: str, agent_ids: list[str]
) -> httpx.Response:
    return await member.client.post(
        rollout_path(member, project_id, version_id), json={"agent_ids": agent_ids}
    )


async def rollout(
    member: SignedUpMember, project_id: str, version_id: str, agent_ids: list[str] | None = None
) -> dict[str, Any]:
    params = {} if agent_ids is None else {"agent_id": agent_ids}
    response = await member.client.get(rollout_path(member, project_id, version_id), params=params)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def states(found: dict[str, Any]) -> dict[str, str]:
    return {agent["name"]: agent["state"] for agent in found["agents"]}


async def live_agent(member: SignedUpMember, project_id: str, name: str, *questions: str) -> str:
    """An Agent of the Project Live with the ``LIVE`` prompt and the Current Instructions, its
    Draft since changed to ``DRAFT``, with a case per question."""
    agent_id: str = (await create_automatic_agent(member, project_id, name))["id"]
    await prompted(member, project_id, agent_id, LIVE)
    await published(member, project_id, agent_id)
    await prompted(member, project_id, agent_id, DRAFT)
    for question in questions:
        await add_case(member, project_id, agent_id, question)
    return agent_id


async def rolled_out(
    app: FastAPI, owner: SignedUpMember
) -> tuple[str, str, str, dict[str, Any], dict[str, Any]]:
    """A Project whose ``HR helper`` (a Regression ahead) and ``Payroll helper`` (no set) are Live
    with Instructions v1 (``BRIEF``), and its new Instructions v2 (``KIND``)."""
    _, project_id, first_id = await ready_agent(app, owner)
    await set_repeats(owner, 1)
    v1 = await instructions(owner, project_id, BRIEF, "Brief")
    await prompted(owner, project_id, first_id, LIVE)
    await published(owner, project_id, first_id)
    await prompted(owner, project_id, first_id, DRAFT)
    await add_case(owner, project_id, first_id, "Same?")
    await add_case(owner, project_id, first_id, "Broken?")
    second_id = await live_agent(owner, project_id, "Payroll helper")
    v2 = await instructions(owner, project_id, KIND, "Kind")
    return project_id, first_id, second_id, v1, v2


async def test_a_rollout_evaluation_runs_each_agent_with_a_set_against_the_new_instructions(
    app: FastAPI, owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    judge_with(app, answering(TABLE))
    project_id, first_id, second_id, v1, v2 = await rolled_out(app, owner)
    editor = await member_factory(owner, "editor")

    started = await start_rollout(editor, project_id, v2["id"], [first_id, second_id])

    assert started.status_code == 202, started.text
    body = started.json()
    assert body["instructions_version_number"] == 2
    assert states(body) == {"HR helper": "regressions", "Payroll helper": "not_evaluated"}
    hr, payroll = body["agents"]
    assert (hr["agent_id"], hr["has_set"], payroll["has_set"]) == (first_id, True, False)
    assert (payroll["run"], payroll["regressions"]) == (None, [])
    assert [(r["question"], [x["kind"] for x in r["reasons"]]) for r in hr["regressions"]] == [
        ("Broken?", ["reference_answer", "grounding"])
    ]
    run = hr["run"]
    assert run["kind"] == "rollout"
    assert sides(run) == [("first", "version", 1), ("second", "rollout", 1)]
    first, second = run["sides"]
    assert first["agent_version_id"] == second["agent_version_id"]
    assert (first["instructions_version_number"], second["instructions_version_number"]) == (1, 2)
    assert (first["score"], second["score"]) == (1.0, 0.5)
    # The rollout side answers with the Live configuration: its Trace names the Live Version.
    results = await results_of(owner, project_id, first_id, run["id"])
    broken = results["cases"][0]
    assert (broken["question"], broken["change"]) == ("Broken?", "regression")
    rollout_trace = broken["results"][1]["trace"]
    assert (rollout_trace["config_source"], rollout_trace["agent_version_number"]) == (
        "version",
        1,
    )
    assert rollout_trace["instructions_version_number"] == 2
    # The read says the same, and nothing was rolled out.
    assert await rollout(owner, project_id, v2["id"], [first_id, second_id]) == body
    assert v1["number"] == 1


async def test_rollout_runs_appear_in_the_agents_run_history_and_never_count_for_publish(
    app: FastAPI, owner: SignedUpMember
) -> None:
    judge_with(app, answering(TABLE))
    project_id, first_id, _, _, v2 = await rolled_out(app, owner)
    started = await start_rollout(owner, project_id, v2["id"], [first_id])
    assert started.status_code == 202, started.text

    history = await owner.client.get(
        project_path(owner, project_id) + f"/agents/{first_id}/evaluation/runs"
    )

    assert history.status_code == 200, history.text
    assert [(run["kind"], sides(run)) for run in history.json()] == [
        ("rollout", [("first", "version", 1), ("second", "rollout", 1)])
    ]
    # A rollout side isn't the Draft: the Run isn't evidence about publishing the Draft.
    assert (await summary(owner, project_id, first_id))["state"] == "no_run"


async def test_rollout_sides_cannot_be_created_through_the_run_api(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id, first_id, _, _, _ = await rolled_out(app, owner)
    version_id = (await agent(owner, project_id, first_id))["live_version"]["id"]

    refused = await start(
        owner, project_id, first_id, {"sides": [{"kind": "rollout", "version_id": version_id}]}
    )

    assert refused.status_code == 422


async def test_an_agent_starts_as_not_evaluated_and_runs_until_its_run_finishes(
    app: FastAPI, owner: SignedUpMember, unsent: list[uuid.UUID]
) -> None:
    project_id, first_id, second_id, _, v2 = await rolled_out(app, owner)
    # Every active Agent of the Project when none is named.
    assert states(await rollout(owner, project_id, v2["id"])) == {
        "HR helper": "not_evaluated",
        "Payroll helper": "not_evaluated",
    }

    started = await start_rollout(owner, project_id, v2["id"], [first_id, first_id])

    assert started.status_code == 202, started.text
    assert len(unsent) == 1
    (hr,) = started.json()["agents"]
    assert (hr["state"], hr["run"]["status"], hr["run"]["progress"]) == (
        "running",
        "queued",
        {"done": 0, "total": 4},
    )
    # A second start while it runs is refused, naming the Agent; nothing more is started.
    again = await start_rollout(owner, project_id, v2["id"], [second_id, first_id])
    assert (again.status_code, again.json()) == (
        409,
        {"detail": rollout_api.rollout_in_progress("HR helper")},
    )
    assert len(unsent) == 1
    # A cancelled Run doesn't count.
    await cancel(owner, project_id, first_id, hr["run"]["id"])
    assert states(await rollout(owner, project_id, v2["id"], [first_id])) == {
        "HR helper": "not_evaluated"
    }


async def test_only_runs_of_the_current_live_version_with_these_instructions_count(
    app: FastAPI, owner: SignedUpMember
) -> None:
    judge_with(app, answering(TABLE))
    project_id, first_id, _, v1, v2 = await rolled_out(app, owner)
    started = await start_rollout(owner, project_id, v2["id"], [first_id])
    assert started.status_code == 202, started.text
    # A Run of the Agent's own isn't a Rollout evaluation.
    judge_with(app, echo)
    await start(owner, project_id, first_id)

    assert states(await rollout(owner, project_id, v1["id"], [first_id])) == {
        "HR helper": "not_evaluated"
    }
    assert states(await rollout(owner, project_id, v2["id"], [first_id])) == {
        "HR helper": "regressions"
    }
    # Once another Version is Live, the Run describes a Version that is no longer Live.
    await prompted(owner, project_id, first_id, LIVE + " Still.")
    await published(owner, project_id, first_id)
    assert states(await rollout(owner, project_id, v2["id"], [first_id])) == {
        "HR helper": "not_evaluated"
    }


async def test_a_clean_rollout_evaluation_is_clear(app: FastAPI, owner: SignedUpMember) -> None:
    judge_with(app, answering({**TABLE, (KIND, "Broken?"): PASSING}))
    project_id, first_id, _, _, v2 = await rolled_out(app, owner)

    started = await start_rollout(owner, project_id, v2["id"], [first_id])

    assert started.status_code == 202, started.text
    (hr,) = started.json()["agents"]
    assert (hr["state"], hr["regressions"]) == ("clear", [])


async def test_agents_that_cannot_be_evaluated_are_skipped(
    app: FastAPI, owner: SignedUpMember, tenant_factory: TenantFactory, unsent: list[uuid.UUID]
) -> None:
    project_id, first_id, _, _, v2 = await rolled_out(app, owner)
    # Never published, with a set.
    draft_only: str = (await create_automatic_agent(owner, project_id, "Draft helper"))["id"]
    await add_case(owner, project_id, draft_only, "Same?")
    # Archived, with a set.
    archived = await live_agent(owner, project_id, "Old helper", "Same?")
    await archive(owner, project_id, archived)
    # Another Organisation's.
    stranger = await tenant_factory()
    _, _, foreign = await ready_agent(app, stranger)

    started = await start_rollout(
        owner, project_id, v2["id"], [draft_only, archived, foreign, str(uuid.uuid4())]
    )

    assert started.status_code == 202, started.text
    assert states(started.json()) == {"Draft helper": "not_evaluated"}
    assert unsent == []
    assert first_id not in {agent["agent_id"] for agent in started.json()["agents"]}


async def test_a_rollout_evaluation_is_refused_as_starting_a_run_would_be(
    app: FastAPI, owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    project_id, first_id, _, _, v2 = await rolled_out(app, owner)
    unknown = str(uuid.uuid4())

    foreign = await start_rollout(owner, project_id, unknown, [first_id])
    read = await owner.client.get(rollout_path(owner, project_id, unknown))
    empty = await start_rollout(owner, project_id, v2["id"], [])
    stranger = await tenant_factory()
    hidden = await stranger.client.get(rollout_path(stranger, project_id, v2["id"]))

    assert foreign.status_code == read.status_code == hidden.status_code == 404
    assert empty.status_code == 422
    # An Agent whose Live Version's Provider Credential is gone.
    claude = await added(owner, provider="anthropic", api_key=ANTHROPIC_KEY, name="Claude")
    gone_id: str = (await create_automatic_agent(owner, project_id, "Claude helper"))["id"]
    override = {"credential_id": claude["id"], "model": "claude-haiku-4-5"}
    saved = await save_draft(
        owner, project_id, gone_id, {"behaviour": {"model": override}, "retrieval": AUTOMATIC}
    )
    assert saved.status_code == 200, saved.text
    await published(owner, project_id, gone_id)
    await add_case(owner, project_id, gone_id, "Same?")
    await delete_credential_row(app, claude["id"])
    gone = await start_rollout(owner, project_id, v2["id"], [first_id, gone_id])
    assert (gone.status_code, gone.json()) == (
        409,
        {"detail": rollout_api.rollout_credential_gone("Claude helper")},
    )
    # Nothing was started for the other Agent either.
    assert states(await rollout(owner, project_id, v2["id"], [first_id])) == {
        "HR helper": "not_evaluated"
    }
    # An archived Project starts none.
    await archive_project(owner, project_id)
    refused = await start_rollout(owner, project_id, v2["id"], [first_id])
    assert (refused.status_code, refused.json()) == (
        409,
        {"detail": "This Project is archived. An Owner can restore it."},
    )


async def test_a_rollout_evaluation_needs_a_model_to_judge(owner: SignedUpMember) -> None:
    project_id = await create_project(owner)
    credential = await added(owner, provider="anthropic", api_key=ANTHROPIC_KEY, name="Claude")
    agent_id: str = (await create_automatic_agent(owner, project_id))["id"]
    override = {"credential_id": credential["id"], "model": "claude-haiku-4-5"}
    saved = await save_draft(
        owner, project_id, agent_id, {"behaviour": {"model": override}, "retrieval": AUTOMATIC}
    )
    assert saved.status_code == 200, saved.text
    await published(owner, project_id, agent_id)
    await add_case(owner, project_id, agent_id, "Same?")
    version = await instructions(owner, project_id, KIND, "Kind")

    refused = await start_rollout(owner, project_id, version["id"], [agent_id])

    assert refused.status_code == 409
    assert refused.json()["detail"].startswith("This Organisation has no Default Model.")
