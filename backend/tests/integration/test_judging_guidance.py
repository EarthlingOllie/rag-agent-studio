"""API seam: Judging guidance (spec 19), the Organisation's own instructions to the Evaluation
Model, in Organisation settings, Models.

Every Member reads the current guidance and its versions; only Owners save it. Each save is a
new version, made current and recorded as an Audit Event with before and after; removing saves
an empty version. New Evaluation Runs and Live Verdicts are judged with the current guidance and
record its version beside their judge model (their Judging setup); earlier ones keep theirs.
Judgements are observed through the API: Live Verdicts through the fake judge's one guidance rule,
Runs through a scripted judge that passes only what it was guided to.
"""

from collections.abc import AsyncIterator
from typing import Any

import httpx
from fastapi import FastAPI
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.evaluation.fake_judge import PARTIAL_ANSWERS_PASS, fake_judgement, is_judging
from app.gateway.fakes import FakeModelAdapters
from tests.conftest import MemberFactory, SignedUpMember
from tests.integration.test_evaluation import add_case, evaluated, evaluation_path, only_result
from tests.integration.test_live_verdicts import (
    live_agent,
    live_verdict,
    reply,
    sampling,
    scripted,
)
from tests.integration.test_live_verdicts import visitor as visitor
from tests.integration.test_playground import ready_agent, three_tokens
from tests.integration.test_provider_credentials import audit_events

CHANGED = "organisation.judging_guidance_changed"
PARTIAL = "A partial answer that says what it doesn't cover answers the question."


def guidance_path(member: SignedUpMember) -> str:
    return f"/api/organisations/{member.organisation_id}/judging-guidance"


async def read_guidance(member: SignedUpMember) -> Any:
    response = await member.client.get(guidance_path(member))
    assert response.status_code == 200, response.text
    return response.json()


async def save_guidance(member: SignedUpMember, text: str) -> Any:
    return await member.client.put(guidance_path(member), json={"text": text})


async def saved(member: SignedUpMember, text: str) -> Any:
    response = await save_guidance(member, text)
    assert response.status_code == 200, response.text
    return response.json()


async def test_an_organisation_starts_with_no_guidance(owner: SignedUpMember) -> None:
    assert await read_guidance(owner) == {"current": None, "versions": []}


async def test_an_owner_saves_guidance_as_a_new_current_version(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")

    first = await saved(owner, f"  {PARTIAL}  ")
    second = await saved(owner, "Be strict about grounding.")

    version = {
        "version": 1,
        "text": PARTIAL,
        "source": "written",
        "saved_by": owner.name,
    }
    assert {k: first["current"][k] for k in version} == version
    assert first["versions"] == [first["current"]]
    assert second["current"]["version"] == 2
    assert second["current"]["text"] == "Be strict about grounding."
    assert [v["version"] for v in second["versions"]] == [2, 1]
    # Editors read the guidance and its versions.
    assert await read_guidance(editor) == second


async def test_saving_the_current_text_again_changes_nothing(owner: SignedUpMember) -> None:
    await saved(owner, PARTIAL)

    again = await saved(owner, PARTIAL)

    assert [v["version"] for v in again["versions"]] == [1]
    assert len(await audit_events(owner, CHANGED)) == 1


async def test_removing_guidance_saves_an_empty_version(owner: SignedUpMember) -> None:
    await saved(owner, PARTIAL)

    removed = await saved(owner, "   ")

    assert removed["current"]["version"] == 2
    assert removed["current"]["text"] == ""
    # Removing what isn't there saves nothing.
    assert [v["version"] for v in (await saved(owner, ""))["versions"]] == [2, 1]


async def test_guidance_is_at_most_two_thousand_characters(owner: SignedUpMember) -> None:
    assert (await save_guidance(owner, "x" * 2001)).status_code == 422
    assert (await saved(owner, "x" * 2000))["current"]["version"] == 1


async def test_only_owners_save_guidance(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")

    assert (await save_guidance(editor, PARTIAL)).status_code == 403
    assert await read_guidance(owner) == {"current": None, "versions": []}


async def test_each_save_is_audited_with_before_and_after(owner: SignedUpMember) -> None:
    await saved(owner, PARTIAL)
    await saved(owner, "")

    removed, first = await audit_events(owner, CHANGED)
    assert first["actor"]["id"] == owner.member_id
    assert first["target"] == {"type": "organisation", "id": owner.organisation_id}
    assert (first["before"], first["after"]) == (None, {"version": 1, "text": PARTIAL})
    assert (removed["before"], removed["after"]) == (
        {"version": 1, "text": PARTIAL},
        {"version": 2, "text": ""},
    )


# Judging with guidance


async def partial_reply(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
    """Answers part of the question, and says what it doesn't cover."""
    yield "Everyone gets twenty-five days [C1]. The policy doesn't cover the rest."


async def test_new_live_verdicts_are_judged_with_the_current_guidance_and_record_it(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    scripted(app, partial_reply)
    agent = await live_agent(app, owner)
    await sampling(owner, agent, 100)
    question = "How much parental pay do I get?"
    before = await reply(visitor, agent, question)

    await saved(owner, f"Remember: {PARTIAL_ANSWERS_PASS}.")
    after = await reply(visitor, agent, question)

    unguided = await live_verdict(owner, agent, before)
    guided = await live_verdict(owner, agent, after)
    assert unguided is not None
    assert guided is not None
    # Judged before guidance was saved: it keeps its Judging setup and its Verdict.
    assert unguided["judging_guidance_version"] is None
    assert unguided["answers_question"]["outcome"] == "fail"
    assert guided["judging_guidance_version"] == 1
    assert guided["answers_question"] == {
        "outcome": "pass",
        "reason": "Fake judge: a partial answer that says what it doesn't cover passes, "
        "as the guidance says.",
    }
    assert (guided["judge_provider"], guided["judge_model"]) == ("openai", "gpt-4.1-mini")


GUIDED = "Pass an answer that mentions leave."


def guided_judge(app: FastAPI) -> None:
    """Answers as the Playground's three tokens; judges every Verdict passed when its
    instructions carry ``GUIDED``, and as the fake judge otherwise."""

    def judging(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        assert is_judging(info)
        if GUIDED not in (info.instructions or ""):
            return fake_judgement(messages, info)
        verdict = {"passed": True, "reason": "Guided."}
        judgement = {"reference_answer": verdict, "grounding": verdict}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, judgement)])

    def chat(provider: Any, secret: str, model: str) -> FunctionModel:
        return FunctionModel(
            judging,
            stream_function=three_tokens,
            model_name=model,
            profile={"supports_json_schema_output": False},
        )

    app.state.model_gateway.adapters = FakeModelAdapters(chat=chat)


async def test_new_runs_are_judged_with_the_current_guidance_and_record_it(
    app: FastAPI, owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    guided_judge(app)
    editor, project_id, agent_id = await ready_agent(
        app, owner, await member_factory(owner, "editor")
    )
    await add_case(editor, project_id, agent_id, reference_answer='It says "nothing like this".')
    before = await evaluated(editor, project_id, agent_id)

    await saved(owner, GUIDED)
    after = await evaluated(editor, project_id, agent_id)
    await saved(owner, "")
    removed = await evaluated(editor, project_id, agent_id)

    assert before["run"]["judging_guidance_version"] is None
    assert ("reference_answer", "fail") in [
        (v["kind"], v["outcome"]) for v in only_result(before)["verdicts"]
    ]
    assert after["run"]["judging_guidance_version"] == 1
    assert {v["reason"] for v in only_result(after)["verdicts"]} == {"Guided."}
    # Removed: judged under the empty version 2, without guidance.
    assert removed["run"]["judging_guidance_version"] == 2
    assert "Guided." not in {v["reason"] for v in only_result(removed)["verdicts"]}
    # A finished Run keeps the Judging setup it was judged under.
    again = await editor.client.get(
        evaluation_path(editor, project_id, agent_id, "runs", after["run"]["id"], "results")
    )
    assert again.json() == after
