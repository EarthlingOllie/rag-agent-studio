"""API seam: an Editor keeps an Agent's Evaluation Set and evaluates the Draft against it.

The Draft answers through the real Guardrails and retrieval with a scripted Pydantic AI
``FunctionModel``; the judge is the same model's structured-output path, the fake chat model's
deterministic judge (``app.evaluation.fake_judge``) unless a test scripts its own. The Run's task
runs eagerly when it is started through the API, so the Run comes back finished; it is read back
through the API, as the Studio polls it. Once an Agent is deleted, whether its Evaluation rows are
gone has no API surface, so that is read directly.
"""

import asyncio
import uuid
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
from fastapi import FastAPI
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models import Model
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlalchemy import text

from app.agents.config import DEFAULT_FALLBACK_TEXT
from app.credentials.registry import Provider
from app.evaluation.tasks import run_evaluation_task
from app.gateway.fakes import FakeModelAdapters, fake_chat
from tests.agents import (
    AUTOMATIC,
    StreamFunction,
    agents_path,
    create_agent,
    create_automatic_agent,
    save_draft,
    use_default_model,
)
from tests.conftest import MemberFactory, SignedUpMember, TenantFactory
from tests.documents import create_project, project_path, upload
from tests.integration.test_agent_archive import archive, delete_permanently
from tests.integration.test_agent_versions import published
from tests.integration.test_playground import (
    ANSWER,
    LEAVE,
    delete_credential_row,
    echo,
    ready_agent,
    three_tokens,
)
from tests.integration.test_project_instructions_versions import published as instructions
from tests.integration.test_projects import archive as archive_project
from tests.integration.test_provider_credentials import ANTHROPIC_KEY, added
from tests.integration.test_token_budget import usage

REFERENCE = 'Everyone gets "twenty-five days" of annual leave.'
NO_EXPECTATION = "An Evaluation Case needs at least one expectation: write a Reference answer."


def evaluation_path(member: SignedUpMember, project_id: str, agent_id: str, *rest: str) -> str:
    return "/".join([agents_path(member, project_id, agent_id), "evaluation", *rest])


def judge_with(app: FastAPI, stream: StreamFunction) -> None:
    """Every chat model answers by streaming ``stream`` and judges as the fake chat model."""

    def chat(provider: Provider, secret: str, model: str) -> FunctionModel:
        fake = fake_chat(provider, secret, model)
        assert isinstance(fake, FunctionModel)
        assert fake.function is not None
        return FunctionModel(
            fake.function,
            stream_function=stream,
            model_name=model,
            profile={"supports_json_schema_output": False},
        )

    app.state.model_gateway.adapters = FakeModelAdapters(chat=chat)


async def add_case(
    member: SignedUpMember,
    project_id: str,
    agent_id: str,
    question: str = "How much leave do I get?",
    reference_answer: str | None = REFERENCE,
) -> dict[str, Any]:
    response = await member.client.post(
        evaluation_path(member, project_id, agent_id, "cases"),
        json={"question": question, "reference_answer": reference_answer},
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def start(member: SignedUpMember, project_id: str, agent_id: str) -> httpx.Response:
    return await member.client.post(evaluation_path(member, project_id, agent_id, "runs"))


async def evaluated(member: SignedUpMember, project_id: str, agent_id: str) -> dict[str, Any]:
    """Starts a Run, and returns its results once it has finished."""
    started = await start(member, project_id, agent_id)
    assert started.status_code == 202, started.text
    run_id = started.json()["id"]
    response = await member.client.get(
        evaluation_path(member, project_id, agent_id, "runs", run_id, "results")
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def only_result(results: dict[str, Any]) -> dict[str, Any]:
    (case,) = results["cases"]
    (result,) = case["results"]
    found: dict[str, Any] = result
    return found


def outcomes(result: dict[str, Any]) -> list[tuple[str, str]]:
    return [(v["kind"], v["outcome"]) for v in result["verdicts"]]


# The Evaluation Set


async def test_an_editor_writes_reads_edits_and_deletes_cases(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    project_id = await create_project(editor)
    agent = await create_agent(editor, project_id)
    path = evaluation_path(editor, project_id, agent["id"], "cases")
    assert (await editor.client.get(path)).json() == []

    first = await add_case(editor, project_id, agent["id"], "  How much leave?  ", "25 days.")
    second = await add_case(editor, project_id, agent["id"], "Where do visitors park?", "North.")

    assert (first["question"], first["reference_answer"], first["source"]) == (
        "How much leave?",
        "25 days.",
        "written",
    )
    listed = (await editor.client.get(path)).json()
    assert [c["id"] for c in listed] == [first["id"], second["id"]]
    read = await editor.client.get(f"{path}/{first['id']}")
    assert read.json() == first

    edited = await editor.client.put(
        f"{path}/{first['id']}",
        json={"question": "How much annual leave?", "reference_answer": "25"},
    )
    assert edited.status_code == 200, edited.text
    assert (edited.json()["question"], edited.json()["reference_answer"]) == (
        "How much annual leave?",
        "25",
    )

    deleted = await editor.client.delete(f"{path}/{first['id']}")
    assert deleted.status_code == 204
    assert (await editor.client.get(f"{path}/{first['id']}")).status_code == 404
    assert [c["id"] for c in (await editor.client.get(path)).json()] == [second["id"]]


async def test_a_case_without_an_expectation_is_refused(owner: SignedUpMember) -> None:
    project_id = await create_project(owner)
    agent = await create_agent(owner, project_id)
    path = evaluation_path(owner, project_id, agent["id"], "cases")
    case = await add_case(owner, project_id, agent["id"])

    for body in ({"question": "How much leave?"}, {"question": "Q", "reference_answer": "  "}):
        refused = await owner.client.post(path, json=body)
        assert (refused.status_code, refused.json()) == (422, {"detail": NO_EXPECTATION})
    emptied = await owner.client.put(
        f"{path}/{case['id']}", json={"question": "Q", "reference_answer": ""}
    )
    assert (emptied.status_code, emptied.json()) == (422, {"detail": NO_EXPECTATION})
    blank = await owner.client.post(path, json={"question": "  ", "reference_answer": "Yes."})
    assert blank.status_code == 422
    assert (await owner.client.get(path)).json() == [case]


async def test_cases_are_not_found_outside_their_agent_and_organisation(
    owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    project_id = await create_project(owner)
    agent = await create_agent(owner, project_id)
    other = await create_agent(owner, project_id, "Benefits FAQ")
    case = await add_case(owner, project_id, agent["id"])
    stranger = await tenant_factory()

    in_other_agent = evaluation_path(owner, project_id, other["id"], "cases", case["id"])
    assert (await owner.client.get(in_other_agent)).status_code == 404
    body = {"question": "Q", "reference_answer": "A"}
    assert (await owner.client.put(in_other_agent, json=body)).status_code == 404
    assert (await owner.client.delete(in_other_agent)).status_code == 404
    missing = evaluation_path(owner, project_id, str(uuid.uuid4()), "cases")
    assert (await owner.client.get(missing)).status_code == 404
    assert (await owner.client.post(missing, json=body)).status_code == 404
    theirs = evaluation_path(owner, project_id, agent["id"], "cases")
    assert (await stranger.client.get(theirs)).status_code == 404
    assert (await stranger.client.get(f"{theirs}/{case['id']}")).status_code == 404
    assert (await start(stranger, project_id, agent["id"])).status_code == 404


async def test_an_archived_agents_set_is_readable_but_unchangeable_and_starts_no_run(
    app: FastAPI, owner: SignedUpMember
) -> None:
    judge_with(app, three_tokens)
    _, project_id, agent_id = await ready_agent(app, owner)
    case = await add_case(owner, project_id, agent_id)
    results = await evaluated(owner, project_id, agent_id)
    await archive(owner, project_id, agent_id)
    path = evaluation_path(owner, project_id, agent_id, "cases")
    archived = (409, {"detail": "This Agent is archived. An Owner can restore it."})

    body = {"question": "Q", "reference_answer": "A"}
    for response in (
        await owner.client.post(path, json=body),
        await owner.client.put(f"{path}/{case['id']}", json=body),
        await owner.client.delete(f"{path}/{case['id']}"),
        await start(owner, project_id, agent_id),
    ):
        assert (response.status_code, response.json()) == archived
    assert (await owner.client.get(path)).json() == [case]
    runs = await owner.client.get(evaluation_path(owner, project_id, agent_id, "runs"))
    assert [run["id"] for run in runs.json()] == [results["run"]["id"]]


async def test_an_archived_projects_set_is_unchangeable(owner: SignedUpMember) -> None:
    project_id = await create_project(owner)
    agent = await create_agent(owner, project_id)
    case = await add_case(owner, project_id, agent["id"])
    await archive_project(owner, project_id)
    path = evaluation_path(owner, project_id, agent["id"], "cases")
    archived = (409, {"detail": "This Project is archived. An Owner can restore it."})

    for response in (
        await owner.client.post(path, json={"question": "Q", "reference_answer": "A"}),
        await owner.client.delete(f"{path}/{case['id']}"),
        await start(owner, project_id, agent["id"]),
    ):
        assert (response.status_code, response.json()) == archived


# Evaluating the Draft


async def test_an_editor_evaluates_the_draft_and_reads_the_judged_answer(
    app: FastAPI, owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    judge_with(app, three_tokens)
    editor, project_id, agent_id = await ready_agent(
        app, owner, await member_factory(owner, "editor")
    )
    case = await add_case(editor, project_id, agent_id)

    started = await start(editor, project_id, agent_id)

    assert started.status_code == 202, started.text
    run = started.json()
    # The task ran eagerly: the Run is already finished, and its progress counts the answer.
    assert run["status"] == "completed"
    assert run["progress"] == {"done": 1, "total": 1}
    assert run["finished_at"] is not None
    assert (run["judge_provider"], run["judge_model"]) == ("openai", "gpt-4.1-mini")
    agent = (await editor.client.get(agents_path(editor, project_id, agent_id))).json()
    assert run["sides"] == [
        {
            "position": "first",
            "kind": "draft",
            "draft_revision": agent["draft_revision"],
            "instructions_version_number": None,
            "model_provider": "openai",
            "model_name": "gpt-4.1-mini",
        }
    ]
    polled = await editor.client.get(
        evaluation_path(editor, project_id, agent_id, "runs", run["id"])
    )
    assert polled.json() == run
    listed = await editor.client.get(evaluation_path(editor, project_id, agent_id, "runs"))
    assert listed.json() == [run]

    results = (
        await editor.client.get(
            evaluation_path(editor, project_id, agent_id, "runs", run["id"], "results")
        )
    ).json()
    assert results["run"] == run
    (copied,) = results["cases"]
    assert (copied["case_id"], copied["question"], copied["reference_answer"]) == (
        case["id"],
        case["question"],
        REFERENCE,
    )
    result = only_result(results)
    assert (result["position"], result["repeat"], result["status"]) == ("first", 1, "answered")
    assert result["answer"] == ANSWER
    assert result["passed"] is True
    assert result["verdicts"] == [
        {
            "kind": "reference_answer",
            "outcome": "pass",
            "reason": "Fake judge: the answer contains “twenty-five days”.",
        },
        {
            "kind": "grounding",
            "outcome": "pass",
            "reason": "Fake judge: the answer cites the knowledge base.",
        },
    ]
    trace = result["trace"]
    assert trace["config_source"] == "draft"
    assert (trace["model_provider"], trace["model_name"]) == ("openai", "gpt-4.1-mini")
    assert trace["fallback"] is False
    (chunk,) = trace["chunks"]
    assert (chunk["rank"], chunk["cited"], chunk["text"], chunk["document_name"]) == (
        1,
        True,
        LEAVE,
        "leave.txt",
    )


async def wrong_and_uncited(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
    yield "Everyone gets ten days of leave."


async def test_a_wrong_uncited_answer_fails_both_verdicts(
    app: FastAPI, owner: SignedUpMember
) -> None:
    judge_with(app, wrong_and_uncited)
    _, project_id, agent_id = await ready_agent(app, owner)
    await add_case(owner, project_id, agent_id)

    result = only_result(await evaluated(owner, project_id, agent_id))

    assert result["passed"] is False
    assert result["verdicts"] == [
        {
            "kind": "reference_answer",
            "outcome": "fail",
            "reason": "Fake judge: the answer lacks “twenty-five days”.",
        },
        {
            "kind": "grounding",
            "outcome": "fail",
            "reason": "Fake judge: the answer cites nothing to support it.",
        },
    ]


async def test_an_answer_that_is_the_fallback_text_skips_grounding(
    app: FastAPI, owner: SignedUpMember
) -> None:
    await use_default_model(owner)
    project_id = await create_project(owner)
    agent = await create_automatic_agent(owner, project_id)
    await add_case(owner, project_id, agent["id"], "What is the canteen menu?", '"don\'t know"')

    result = only_result(await evaluated(owner, project_id, agent["id"]))

    assert result["answer"] == DEFAULT_FALLBACK_TEXT
    assert result["trace"]["fallback"] is True
    # A fallback reply asked no model.
    assert result["trace"]["model_name"] is None
    assert outcomes(result) == [("reference_answer", "pass")]


async def test_an_agentic_draft_searches_and_its_searches_are_traced(
    app: FastAPI, owner: SignedUpMember
) -> None:
    await use_default_model(owner)
    project_id = await create_project(owner)
    await upload(app, owner, project_id, "leave.txt", LEAVE.encode())
    agent = await create_agent(owner, project_id)
    await add_case(owner, project_id, agent["id"], LEAVE, '"Fake reply"')

    result = only_result(await evaluated(owner, project_id, agent["id"]))

    # The fake chat model searched with the question, then cited what it found.
    assert result["answer"] == "Fake reply from openai:gpt-4.1-mini. [C1]"
    assert result["trace"]["chunks"] == []
    (search,) = result["trace"]["searches"]
    assert search["query"] == LEAVE
    assert [(c["rank"], c["cited"]) for c in search["chunks"]] == [(1, True)]
    assert outcomes(result) == [("reference_answer", "pass"), ("grounding", "pass")]


async def test_the_draft_answers_with_the_current_instructions_version(
    app: FastAPI, owner: SignedUpMember
) -> None:
    judge_with(app, echo)
    _, project_id, agent_id = await ready_agent(app, owner)
    await instructions(owner, project_id, "Answer in French.", "French")
    # The Instructions Draft moves on, unpublished: the Run doesn't answer with it.
    saved = await owner.client.put(
        f"{project_path(owner, project_id)}/instructions", json={"markdown": "Answer in Latin."}
    )
    assert saved.status_code == 200, saved.text
    await add_case(owner, project_id, agent_id)

    results = await evaluated(owner, project_id, agent_id)

    assert results["run"]["sides"][0]["instructions_version_number"] == 1
    trace = only_result(results)["trace"]
    assert (trace["instructions_source"], trace["instructions_version_number"]) == ("version", 1)
    answer = only_result(results)["answer"]
    assert "Answer in French." in answer
    assert "Answer in Latin." not in answer
    # No history: the question is the only turn the model is given.
    assert answer.count("How much leave do I get?") == 1


async def test_a_run_keeps_its_copy_of_each_case(app: FastAPI, owner: SignedUpMember) -> None:
    judge_with(app, three_tokens)
    _, project_id, agent_id = await ready_agent(app, owner)
    kept = await add_case(owner, project_id, agent_id)
    gone = await add_case(owner, project_id, agent_id, "Where do I park?", "North car park.")
    results = await evaluated(owner, project_id, agent_id)
    path = evaluation_path(owner, project_id, agent_id, "cases")

    await owner.client.put(
        f"{path}/{kept['id']}", json={"question": "Edited?", "reference_answer": "Edited."}
    )
    await owner.client.delete(f"{path}/{gone['id']}")

    run_id = results["run"]["id"]
    again = await owner.client.get(
        evaluation_path(owner, project_id, agent_id, "runs", run_id, "results")
    )
    assert [
        (c["case_id"], c["question"], c["reference_answer"]) for c in again.json()["cases"]
    ] == [
        (kept["id"], "How much leave do I get?", REFERENCE),
        (None, "Where do I park?", "North car park."),
    ]


async def test_answering_creates_no_conversation_and_leaves_kpis_and_budget_alone(
    app: FastAPI, owner: SignedUpMember
) -> None:
    judge_with(app, three_tokens)
    _, project_id, agent_id = await ready_agent(app, owner)
    await published(owner, project_id, agent_id)
    await add_case(owner, project_id, agent_id)
    agent = {"project_id": project_id, "id": agent_id}
    metrics_path = f"{project_path(owner, project_id)}/agents/{agent_id}/metrics"
    conversations_path = f"{project_path(owner, project_id)}/conversations"
    cost_path = f"/api/organisations/{owner.organisation_id}/cost"
    before = [
        (await owner.client.get(path)).json()
        for path in (metrics_path, conversations_path, cost_path)
    ]
    budget_before = await usage(owner, agent)

    result = only_result(await evaluated(owner, project_id, agent_id))

    assert result["status"] == "answered"
    after = [
        (await owner.client.get(path)).json()
        for path in (metrics_path, conversations_path, cost_path)
    ]
    assert after == before
    assert before[1]["items"] == []
    assert await usage(owner, agent) == budget_before


# Errors


async def test_a_provider_error_makes_the_case_result_an_error(
    app: FastAPI, owner: SignedUpMember
) -> None:
    _, project_id, agent_id = await ready_agent(app, owner)
    await add_case(owner, project_id, agent_id, "Please simulate a rate limit.")

    results = await evaluated(owner, project_id, agent_id)

    assert results["run"]["status"] == "completed"
    result = only_result(results)
    assert result["status"] == "error"
    assert result["error_reason"].startswith("The provider says this key is over its rate limit")
    assert (result["answer"], result["trace"], result["passed"]) == (None, None, None)
    assert result["verdicts"] == []


def failing_to_build(provider: Provider, secret: str, model: str) -> Model:
    raise ModelHTTPError(status_code=401, model_name=model)


async def test_a_model_that_cannot_be_built_makes_the_case_result_an_error(
    app: FastAPI, owner: SignedUpMember
) -> None:
    app.state.model_gateway.adapters = FakeModelAdapters(chat=failing_to_build)
    _, project_id, agent_id = await ready_agent(app, owner)
    await add_case(owner, project_id, agent_id)

    result = only_result(await evaluated(owner, project_id, agent_id))

    assert result["status"] == "error"
    assert result["error_reason"].startswith("The provider rejected the API key.")


def judge_failing(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    raise ModelHTTPError(status_code=503, model_name="gpt-4.1-mini")


def answering_but_not_judging(
    judge: Callable[[list[ModelMessage], AgentInfo], ModelResponse],
) -> Callable[[Provider, str, str], Model]:
    def chat(provider: Provider, secret: str, model: str) -> Model:
        return FunctionModel(
            judge,
            stream_function=three_tokens,
            model_name=model,
            profile={"supports_json_schema_output": False},
        )

    return chat


async def test_a_judge_error_makes_the_case_result_an_error_keeping_the_answer(
    app: FastAPI, owner: SignedUpMember
) -> None:
    app.state.model_gateway.adapters = FakeModelAdapters(
        chat=answering_but_not_judging(judge_failing)
    )
    _, project_id, agent_id = await ready_agent(app, owner)
    await add_case(owner, project_id, agent_id)

    result = only_result(await evaluated(owner, project_id, agent_id))

    assert result["status"] == "error"
    assert result["error_reason"] == (
        "The Evaluation Model couldn't judge the answer: The provider couldn't answer just now. "
        "Try again in a moment."
    )
    assert result["answer"] == ANSWER
    assert result["trace"] is not None
    assert result["verdicts"] == []


async def test_a_run_needs_cases_a_model_and_its_credentials(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    agent = await create_automatic_agent(owner, project_id)
    empty = await start(owner, project_id, agent["id"])
    assert (empty.status_code, empty.json()) == (
        409,
        {"detail": "Add an Evaluation Case before evaluating."},
    )
    await add_case(owner, project_id, agent["id"])
    no_model = await start(owner, project_id, agent["id"])
    assert no_model.status_code == 409
    assert no_model.json()["detail"].startswith("This Organisation has no Default Model.")

    # A Model override answers, but the Default Model judges, so a Run still needs it.
    credential = await added(owner, provider="anthropic", api_key=ANTHROPIC_KEY, name="Claude")
    override = {"credential_id": credential["id"], "model": "claude-haiku-4-5"}
    saved = await save_draft(
        owner, project_id, agent["id"], {"behaviour": {"model": override}, "retrieval": AUTOMATIC}
    )
    assert saved.status_code == 200, saved.text
    no_judge = await start(owner, project_id, agent["id"])
    assert no_judge.json()["detail"].startswith("This Organisation has no Default Model.")

    await use_default_model(owner)
    await delete_credential_row(app, credential["id"])
    gone = await start(owner, project_id, agent["id"])
    assert gone.status_code == 409
    assert gone.json()["detail"].startswith("This Agent uses a Provider Credential")
    runs = await owner.client.get(evaluation_path(owner, project_id, agent["id"], "runs"))
    assert runs.json() == []


async def test_runs_are_not_found_outside_their_agent(app: FastAPI, owner: SignedUpMember) -> None:
    judge_with(app, three_tokens)
    _, project_id, agent_id = await ready_agent(app, owner)
    other = await create_agent(owner, project_id, "Benefits FAQ")
    await add_case(owner, project_id, agent_id)
    run_id = (await evaluated(owner, project_id, agent_id))["run"]["id"]

    for path in (
        evaluation_path(owner, project_id, other["id"], "runs", run_id),
        evaluation_path(owner, project_id, other["id"], "runs", run_id, "results"),
        evaluation_path(owner, project_id, agent_id, "runs", str(uuid.uuid4())),
        evaluation_path(owner, project_id, str(uuid.uuid4()), "runs"),
    ):
        assert (await owner.client.get(path)).status_code == 404
    missing_agent = await start(owner, project_id, str(uuid.uuid4()))
    assert missing_agent.status_code == 404


async def test_running_a_finished_run_again_changes_nothing(
    app: FastAPI, owner: SignedUpMember
) -> None:
    judge_with(app, three_tokens)
    _, project_id, agent_id = await ready_agent(app, owner)
    await add_case(owner, project_id, agent_id)
    results = await evaluated(owner, project_id, agent_id)

    await asyncio.to_thread(run_evaluation_task.apply, (results["run"]["id"],))

    run_id = results["run"]["id"]
    again = await owner.client.get(
        evaluation_path(owner, project_id, agent_id, "runs", run_id, "results")
    )
    assert again.json() == results


async def evaluation_rows(app: FastAPI, agent_id: str) -> dict[str, int]:
    queries = {
        "cases": "SELECT count(*) FROM evaluation_cases WHERE agent_id = :id",
        "runs": "SELECT count(*) FROM evaluation_runs WHERE agent_id = :id",
        "results": (
            "SELECT count(*) FROM evaluation_case_results r"
            " JOIN evaluation_runs u ON u.id = r.run_id WHERE u.agent_id = :id"
        ),
    }
    async with app.state.sessionmaker() as session:
        return {
            table: (await session.scalar(text(query), {"id": agent_id})) or 0
            for table, query in queries.items()
        }


async def test_permanent_deletion_removes_the_set_and_runs(
    app: FastAPI, owner: SignedUpMember
) -> None:
    judge_with(app, three_tokens)
    _, project_id, agent_id = await ready_agent(app, owner)
    await add_case(owner, project_id, agent_id)
    await evaluated(owner, project_id, agent_id)
    before = await evaluation_rows(app, agent_id)
    await archive(owner, project_id, agent_id)

    deleted = await delete_permanently(owner, project_id, agent_id, "HR helper")

    assert deleted.status_code == 204, deleted.text
    assert before == {"cases": 1, "runs": 1, "results": 1}
    assert await evaluation_rows(app, agent_id) == dict.fromkeys(before, 0)
