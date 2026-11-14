"""API seam: two-sided Evaluation Runs. An Editor compares the Live Version with the Draft, or any
two of the Draft and the Agent's Versions, reads each side's Evaluation score with Regressions
first, and cancels a Run in progress.

As in ``test_evaluation``, the sides answer through the real Guardrails and retrieval with a
scripted ``FunctionModel`` and the fake judge, and the Run's task runs eagerly. A test that needs
a Run to stay queued stops the task from being sent; a test that cancels a Run while it answers
cancels it from inside the answering model, through the evaluation service, as another request
would.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo

from app.core.db import create_engine, create_sessionmaker
from app.core.settings import load_settings
from app.evaluation import api as evaluation_api
from app.evaluation import service
from app.tenancy.models import Role
from app.tenancy.repository import OrganisationScope
from tests.agents import AUTOMATIC, StreamFunction, agents_path, save_draft, use_default_model
from tests.conftest import SignedUpMember
from tests.documents import create_project, project_path, upload
from tests.integration.test_agent_versions import published
from tests.integration.test_evaluation import (
    FAILING,
    PASSING,
    add_case,
    evaluation_path,
    judge_with,
)
from tests.integration.test_evaluation_settings import set_repeats
from tests.integration.test_playground import LEAVE, delete_credential_row, echo, ready_agent
from tests.integration.test_project_instructions_versions import published as instructions
from tests.integration.test_provider_credentials import ANTHROPIC_KEY, added

LIVE = "You are the Live helper."
DRAFT = "You are the Draft helper."


def answering(table: dict[tuple[str, str], str]) -> StreamFunction:
    """Answers with ``table[(marker, question)]`` for the marker in the model's instructions and
    the question it was asked, whichever order the sides answer in."""

    async def stream(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
        given = " ".join(
            str(getattr(part, "content", "")) for message in messages for part in message.parts
        )
        (answer,) = [
            answer
            for (marker, question), answer in table.items()
            if marker in given and question in given
        ]
        yield answer

    return stream


async def prompted(member: SignedUpMember, project_id: str, agent_id: str, prompt: str) -> None:
    saved = await save_draft(
        member,
        project_id,
        agent_id,
        {"behaviour": {"system_prompt": prompt}, "retrieval": AUTOMATIC},
    )
    assert saved.status_code == 200, saved.text


async def start(
    member: SignedUpMember, project_id: str, agent_id: str, body: dict[str, Any] | None = None
) -> httpx.Response:
    return await member.client.post(
        evaluation_path(member, project_id, agent_id, "runs"), json=body
    )


async def results_of(
    member: SignedUpMember, project_id: str, agent_id: str, run_id: str
) -> dict[str, Any]:
    response = await member.client.get(
        evaluation_path(member, project_id, agent_id, "runs", run_id, "results")
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def evaluated(
    member: SignedUpMember, project_id: str, agent_id: str, body: dict[str, Any] | None = None
) -> dict[str, Any]:
    started = await start(member, project_id, agent_id, body)
    assert started.status_code == 202, started.text
    return await results_of(member, project_id, agent_id, started.json()["id"])


def sides(run: dict[str, Any]) -> list[tuple[str, str, int | None]]:
    return [(s["position"], s["kind"], s["version_number"]) for s in run["sides"]]


async def live_and_draft(app: FastAPI, owner: SignedUpMember) -> tuple[str, str, dict[str, Any]]:
    """A ready Agent whose v1 is Live with the ``LIVE`` prompt and whose Draft has ``DRAFT``."""
    _, project_id, agent_id = await ready_agent(app, owner)
    await set_repeats(owner, 1)
    await prompted(owner, project_id, agent_id, LIVE)
    version = await published(owner, project_id, agent_id)
    await prompted(owner, project_id, agent_id, DRAFT)
    return project_id, agent_id, version


# Sides


async def test_the_live_version_is_compared_with_the_draft_by_default_regressions_first(
    app: FastAPI, owner: SignedUpMember
) -> None:
    judge_with(
        app,
        answering(
            {
                (LIVE, "Same?"): PASSING,
                (DRAFT, "Same?"): PASSING,
                (LIVE, "Fixed?"): FAILING,
                (DRAFT, "Fixed?"): PASSING,
                (LIVE, "Broken?"): PASSING,
                (DRAFT, "Broken?"): FAILING,
                (LIVE, "Never?"): FAILING,
                (DRAFT, "Never?"): FAILING,
            }
        ),
    )
    project_id, agent_id, version = await live_and_draft(app, owner)
    for question in ("Same?", "Fixed?", "Broken?", "Never?"):
        await add_case(owner, project_id, agent_id, question)

    results = await evaluated(owner, project_id, agent_id)

    run = results["run"]
    assert sides(run) == [("first", "version", 1), ("second", "draft", None)]
    first, second = run["sides"]
    assert first["agent_version_id"] == version["id"]
    assert (first["draft_revision"], second["agent_version_id"]) == (None, None)
    assert (first["cases_passed"], first["cases_failed"], first["score"]) == (2, 2, 0.5)
    assert (second["cases_passed"], second["cases_failed"], second["score"]) == (2, 2, 0.5)
    assert run["progress"] == {"done": 8, "total": 8}
    assert run["stale"] is False
    # Regressions (pass on the first side, fail on the second), then improvements, then the rest.
    assert [(c["question"], c["change"]) for c in results["cases"]] == [
        ("Broken?", "regression"),
        ("Fixed?", "improvement"),
        ("Same?", None),
        ("Never?", None),
    ]
    broken = results["cases"][0]
    assert [(s["position"], s["outcome"]) for s in broken["sides"]] == [
        ("first", "pass"),
        ("second", "fail"),
    ]
    assert [(r["position"], r["answer"], r["passed"]) for r in broken["results"]] == [
        ("first", PASSING, True),
        ("second", FAILING, False),
    ]
    live_trace, draft_trace = (r["trace"] for r in broken["results"])
    assert (live_trace["config_source"], live_trace["agent_version_number"]) == ("version", 1)
    assert live_trace["agent_version_id"] == version["id"]
    assert (draft_trace["config_source"], draft_trace["agent_version_number"]) == ("draft", None)


async def test_a_never_published_agent_runs_the_draft_alone(
    app: FastAPI, owner: SignedUpMember
) -> None:
    judge_with(app, answering({(DRAFT, "Alone?"): PASSING}))
    _, project_id, agent_id = await ready_agent(app, owner)
    await prompted(owner, project_id, agent_id, DRAFT)
    await add_case(owner, project_id, agent_id, "Alone?")

    results = await evaluated(owner, project_id, agent_id)

    assert sides(results["run"]) == [("first", "draft", None)]
    assert [c["change"] for c in results["cases"]] == [None]


async def test_any_two_sides_can_be_compared_each_with_its_instructions(
    app: FastAPI, owner: SignedUpMember
) -> None:
    judge_with(app, echo)
    _, project_id, agent_id = await ready_agent(app, owner)
    await set_repeats(owner, 1)
    french = await instructions(owner, project_id, "Answer in French.", "French")
    v1 = await published(owner, project_id, agent_id)
    german = await instructions(owner, project_id, "Answer in German.", "German")
    v2 = await published(owner, project_id, agent_id)
    saved = await owner.client.put(
        f"{project_path(owner, project_id)}/instructions", json={"markdown": "Answer in Latin."}
    )
    assert saved.status_code == 200, saved.text
    await add_case(owner, project_id, agent_id)

    def answer(results: dict[str, Any], position: str) -> str:
        (found,) = [r for r in results["cases"][0]["results"] if r["position"] == position]
        text: str = found["answer"]
        return text

    # Two Versions: each answers with the Instructions it pins.
    versions = await evaluated(
        owner,
        project_id,
        agent_id,
        {
            "sides": [
                {"kind": "version", "version_id": v2["id"]},
                {"kind": "version", "version_id": v1["id"]},
            ]
        },
    )
    assert sides(versions["run"]) == [("first", "version", 2), ("second", "version", 1)]
    assert [s["instructions_version_number"] for s in versions["run"]["sides"]] == [2, 1]
    assert "Answer in German." in answer(versions, "first")
    assert "Answer in French." in answer(versions, "second")

    # The Draft answers with the Current Instructions Version by default…
    current = await evaluated(owner, project_id, agent_id)
    assert sides(current["run"]) == [("first", "version", 2), ("second", "draft", None)]
    assert current["run"]["sides"][1]["instructions_version_number"] == german["number"]
    assert "Answer in German." in answer(current, "second")

    # …or the Instructions Draft…
    draft = await evaluated(
        owner,
        project_id,
        agent_id,
        {
            "sides": [{"kind": "version", "version_id": v1["id"]}, {"kind": "draft"}],
            "instructions_draft": True,
        },
    )
    draft_side = draft["run"]["sides"][1]
    assert (draft_side["instructions_draft"], draft_side["instructions_version_number"]) == (
        True,
        None,
    )
    assert "Answer in Latin." in answer(draft, "second")
    (_, trace) = (r["trace"] for r in draft["cases"][0]["results"])
    assert trace["instructions_source"] == "draft"
    # …which doesn't change the Version side's pinned Instructions.
    assert "Answer in French." in answer(draft, "first")

    # …or any Instructions Version chosen, on a Draft running alone.
    chosen = await evaluated(
        owner,
        project_id,
        agent_id,
        {"sides": [{"kind": "draft"}], "instructions_version_id": french["id"]},
    )
    assert sides(chosen["run"]) == [("first", "draft", None)]
    assert chosen["run"]["sides"][0]["instructions_version_number"] == 1
    assert "Answer in French." in answer(chosen, "first")


async def test_each_side_answers_with_its_own_retrieval_mode_and_models(
    app: FastAPI, owner: SignedUpMember
) -> None:
    await use_default_model(owner)
    await set_repeats(owner, 1)
    project_id = await create_project(owner)
    await upload(app, owner, project_id, "leave.txt", LEAVE.encode())
    response = await owner.client.post(agents_path(owner, project_id), json={"name": "HR"})
    agent_id = response.json()["id"]
    await prompted(owner, project_id, agent_id, LIVE)
    await published(owner, project_id, agent_id)
    claude = await added(owner, provider="anthropic", api_key=ANTHROPIC_KEY, name="Claude")
    override = {"credential_id": claude["id"], "model": "claude-haiku-4-5"}
    saved = await save_draft(
        owner,
        project_id,
        agent_id,
        {"behaviour": {"model": override}, "retrieval": {"mode": "agentic"}},
    )
    assert saved.status_code == 200, saved.text
    await add_case(owner, project_id, agent_id, LEAVE, '"Fake reply"')

    results = await evaluated(owner, project_id, agent_id)

    live, draft = results["run"]["sides"]
    assert (live["model_provider"], live["model_name"]) == ("openai", "gpt-4.1-mini")
    assert (draft["model_provider"], draft["model_name"]) == ("anthropic", "claude-haiku-4-5")
    live_answer, draft_answer = results["cases"][0]["results"]
    # The Live Version is Automatic: it retrieved before answering.
    assert live_answer["trace"]["searches"] == []
    assert live_answer["trace"]["chunks"] != []
    # The Draft is Agentic: its model searched.
    assert [s["query"] for s in draft_answer["trace"]["searches"]] == [LEAVE]
    assert draft_answer["answer"].startswith("Fake reply from anthropic:claude-haiku-4-5.")


async def test_sides_must_be_the_agents_and_different(app: FastAPI, owner: SignedUpMember) -> None:
    project_id, agent_id, version = await live_and_draft(app, owner)
    await add_case(owner, project_id, agent_id)
    other_project = await create_project(owner, "Other")
    stranger = await owner.client.post(agents_path(owner, other_project), json={"name": "Other"})
    theirs = await published(owner, other_project, stranger.json()["id"])

    for body, detail in (
        (
            {"sides": [{"kind": "version", "version_id": str(uuid.uuid4())}]},
            evaluation_api.VERSION_NOT_FOUND,
        ),
        (
            {"sides": [{"kind": "version", "version_id": theirs["id"]}]},
            evaluation_api.VERSION_NOT_FOUND,
        ),
        ({"sides": [{"kind": "version"}]}, evaluation_api.VERSION_NOT_FOUND),
        ({"sides": [{"kind": "draft"}, {"kind": "draft"}]}, evaluation_api.SAME_SIDES),
        (
            {"sides": [{"kind": "version", "version_id": version["id"]}] * 2},
            evaluation_api.SAME_SIDES,
        ),
        ({"instructions_version_id": str(uuid.uuid4())}, evaluation_api.INSTRUCTIONS_NOT_FOUND),
        (
            {"instructions_version_id": str(uuid.uuid4()), "instructions_draft": True},
            evaluation_api.INSTRUCTIONS_NOT_FOUND,
        ),
    ):
        refused = await start(owner, project_id, agent_id, body)
        assert (refused.status_code, refused.json()) == (422, {"detail": detail}), body
    invalid: list[dict[str, Any]] = [
        {"sides": []},
        {"sides": [{"kind": "draft"}] * 3},
        {"sides": [{"kind": "x"}]},
    ]
    for body in invalid:
        assert (await start(owner, project_id, agent_id, body)).status_code == 422
    runs = await owner.client.get(evaluation_path(owner, project_id, agent_id, "runs"))
    assert runs.json() == []


async def test_a_side_whose_credential_is_gone_is_refused_with_the_reason(
    app: FastAPI, owner: SignedUpMember
) -> None:
    _, project_id, agent_id = await ready_agent(app, owner)
    claude = await added(owner, provider="anthropic", api_key=ANTHROPIC_KEY, name="Claude")
    override = {"credential_id": claude["id"], "model": "claude-haiku-4-5"}
    saved = await save_draft(
        owner, project_id, agent_id, {"behaviour": {"model": override}, "retrieval": AUTOMATIC}
    )
    assert saved.status_code == 200, saved.text
    await published(owner, project_id, agent_id)
    await prompted(owner, project_id, agent_id, DRAFT)
    await add_case(owner, project_id, agent_id)
    await delete_credential_row(app, claude["id"])

    refused = await start(owner, project_id, agent_id)

    assert (refused.status_code, refused.json()) == (
        409,
        {
            "detail": "Version 1 uses a Provider Credential that no longer exists, so it can't "
            "be evaluated. Choose another side."
        },
    )
    # The Draft alone, which uses the Default Model, can still be evaluated.
    alone = await start(owner, project_id, agent_id, {"sides": [{"kind": "draft"}]})
    assert alone.status_code == 202, alone.text


# Staleness


async def test_a_run_with_a_draft_side_goes_stale_once_the_draft_moves_on(
    app: FastAPI, owner: SignedUpMember
) -> None:
    judge_with(app, answering({(LIVE, "Q?"): PASSING, (DRAFT, "Q?"): PASSING}))
    project_id, agent_id, version = await live_and_draft(app, owner)
    await add_case(owner, project_id, agent_id, "Q?")
    with_draft = (await evaluated(owner, project_id, agent_id))["run"]
    versions_only = (
        await evaluated(
            owner,
            project_id,
            agent_id,
            {"sides": [{"kind": "version", "version_id": version["id"]}]},
        )
    )["run"]
    assert (with_draft["stale"], versions_only["stale"]) == (False, False)

    await prompted(owner, project_id, agent_id, DRAFT + " Still.")

    listed = await owner.client.get(evaluation_path(owner, project_id, agent_id, "runs"))
    assert [(run["id"], run["stale"]) for run in listed.json()] == [
        (versions_only["id"], False),
        (with_draft["id"], True),
    ]


# One Run at a time, and cancelling


@pytest.fixture
def unsent(monkeypatch: pytest.MonkeyPatch) -> list[uuid.UUID]:
    """Runs stay queued: their task isn't sent. Yields the Runs that would have been."""
    sent: list[uuid.UUID] = []

    async def enqueue(run_id: uuid.UUID) -> None:
        sent.append(run_id)

    monkeypatch.setattr(evaluation_api, "enqueue_run", enqueue)
    return sent


async def cancel(
    member: SignedUpMember, project_id: str, agent_id: str, run_id: str
) -> httpx.Response:
    return await member.client.post(
        evaluation_path(member, project_id, agent_id, "runs", run_id, "cancel")
    )


async def test_an_agent_has_one_run_in_progress_and_a_queued_run_can_be_cancelled(
    app: FastAPI, owner: SignedUpMember, unsent: list[uuid.UUID]
) -> None:
    judge_with(app, answering({(LIVE, "Q?"): PASSING, (DRAFT, "Q?"): PASSING}))
    project_id, agent_id, _ = await live_and_draft(app, owner)
    await add_case(owner, project_id, agent_id, "Q?")
    queued = await start(owner, project_id, agent_id)
    assert queued.json()["status"] == "queued"

    again = await start(owner, project_id, agent_id)

    assert (again.status_code, again.json()) == (409, {"detail": evaluation_api.RUN_IN_PROGRESS})
    cancelled = await cancel(owner, project_id, agent_id, queued.json()["id"])
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["finished_at"] is not None
    assert cancelled.json()["progress"] == {"done": 0, "total": 2}
    # Cancelled, it is no longer in progress: another Run can start.
    after = await start(owner, project_id, agent_id)
    assert after.status_code == 202, after.text
    assert len(unsent) == 2


async def test_a_finished_run_cannot_be_cancelled(app: FastAPI, owner: SignedUpMember) -> None:
    judge_with(app, answering({(DRAFT, "Q?"): PASSING}))
    _, project_id, agent_id = await ready_agent(app, owner)
    await prompted(owner, project_id, agent_id, DRAFT)
    await add_case(owner, project_id, agent_id, "Q?")
    run_id = (await evaluated(owner, project_id, agent_id))["run"]["id"]

    refused = await cancel(owner, project_id, agent_id, run_id)

    assert (refused.status_code, refused.json()) == (
        409,
        {"detail": evaluation_api.RUN_FINISHED},
    )
    missing = await cancel(owner, project_id, agent_id, str(uuid.uuid4()))
    assert missing.status_code == 404


def cancelling_on(answer: int, member: SignedUpMember, where: list[str]) -> StreamFunction:
    """Answers ``PASSING``, and while giving answer number ``answer`` cancels the Run in
    progress of the Agent at ``where`` (its Project and Agent IDs) through the evaluation
    service, as another request would."""
    given: list[int] = []

    async def stream(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
        given.append(answer)
        if len(given) == answer:
            project_id, agent_id = (uuid.UUID(found) for found in where)
            scope = OrganisationScope(
                uuid.UUID(member.organisation_id), uuid.UUID(member.member_id), Role.EDITOR
            )
            engine = create_engine(load_settings())
            try:
                async with create_sessionmaker(engine)() as session:
                    (run,) = await service.list_runs(session, scope, project_id, agent_id)
                    await service.cancel_run(
                        session, scope, project_id, agent_id, run.id, now=datetime.now(UTC)
                    )
            finally:
                await engine.dispose()
        yield PASSING

    return stream


async def test_a_running_run_cancelled_stops_between_answers_and_keeps_what_it_spent(
    app: FastAPI, owner: SignedUpMember
) -> None:
    where: list[str] = []
    judge_with(app, cancelling_on(2, owner, where))
    _, project_id, agent_id = await ready_agent(app, owner)
    where.extend([project_id, agent_id])
    await set_repeats(owner, 1)
    for question in ("First?", "Second?", "Third?"):
        await add_case(owner, project_id, agent_id, question)

    results = await evaluated(owner, project_id, agent_id)

    run = results["run"]
    assert run["status"] == "cancelled"
    # The answer being given when it was cancelled is kept; no more were asked for.
    assert run["progress"] == {"done": 2, "total": 3}
    assert [len(c["results"]) for c in results["cases"]] == [1, 1, 0]
    assert all(c["results"][0]["trace"]["cost_usd"] is not None for c in results["cases"][:2])
    assert run["sides"][0]["cases_passed"] == 2


async def test_a_run_cancelled_during_its_last_answer_stays_cancelled(
    app: FastAPI, owner: SignedUpMember
) -> None:
    where: list[str] = []
    judge_with(app, cancelling_on(1, owner, where))
    _, project_id, agent_id = await ready_agent(app, owner)
    where.extend([project_id, agent_id])
    await set_repeats(owner, 1)
    await add_case(owner, project_id, agent_id)

    results = await evaluated(owner, project_id, agent_id)

    assert results["run"]["status"] == "cancelled"
    assert results["run"]["progress"] == {"done": 1, "total": 1}
