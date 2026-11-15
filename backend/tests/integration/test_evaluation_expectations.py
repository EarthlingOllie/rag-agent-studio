"""API seam: Expected sources and Expect Fallback Text. An Editor picks passages of a Document as
Expected sources, or marks a case Expect Fallback Text, and a Run checks whether the answer cited
the passage or gave the Fallback Text. An Expected source whose passage no longer exists is a
Stale expectation: skipped, neither pass nor fail, and flagged.

As in ``test_evaluation``, the Draft answers through the real Guardrails and retrieval with a
scripted ``FunctionModel`` and the fake judge, and the Run's task runs eagerly.
"""

import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo

from app.agents.config import DEFAULT_FALLBACK_TEXT
from tests.agents import AUTOMATIC, create_automatic_agent, save_draft, use_default_model
from tests.conftest import SignedUpMember, TenantFactory
from tests.documents import create_project, project_path, upload
from tests.integration.test_evaluation import (
    evaluated,
    evaluation_path,
    judge_with,
    only_result,
    outcomes,
)
from tests.integration.test_input_guardrail import ATTACK, REFUSAL
from tests.integration.test_input_guardrail import RULE as GUARDRAIL_RULE
from tests.integration.test_playground import ready_agent, three_tokens

PARKING = "Visitors park in the north car park."
NO_EXPECTATION = (
    "An Evaluation Case needs at least one expectation: an Expected source, a Reference answer "
    "or Expect Fallback Text."
)
FALLBACK_WITH_REFERENCE = (
    "Expect Fallback Text can't be combined with a Reference answer: clear the Reference answer "
    "or untick Expect Fallback Text."
)
FALLBACK_WITH_SOURCE = (
    "Expect Fallback Text can't be combined with an Expected source: remove the Expected sources "
    "or untick Expect Fallback Text."
)
DOCUMENT_NOT_FOUND = "Choose a Document of this Project for each Expected source."


async def leave_document(member: SignedUpMember, project_id: str) -> dict[str, Any]:
    response = await member.client.get(f"{project_path(member, project_id)}/documents")
    (document,) = [d for d in response.json() if d["name"] == "leave.txt"]
    found: dict[str, Any] = document
    return found


async def post_case(member: SignedUpMember, project_id: str, agent_id: str, **fields: Any) -> Any:
    return await member.client.post(
        evaluation_path(member, project_id, agent_id, "cases"),
        json={"question": "How much leave do I get?", **fields},
    )


async def add_case(member: SignedUpMember, project_id: str, agent_id: str, **fields: Any) -> Any:
    response = await post_case(member, project_id, agent_id, **fields)
    assert response.status_code == 201, response.text
    return response.json()


def source(document_id: str, passage: str) -> dict[str, str]:
    return {"document_id": document_id, "passage": passage}


# Keeping expectations


async def test_a_case_holds_several_expected_sources(app: FastAPI, owner: SignedUpMember) -> None:
    _, project_id, agent_id = await ready_agent(app, owner)
    leave = await leave_document(owner, project_id)
    parking = await upload(app, owner, project_id, "parking.txt", PARKING.encode())

    case = await add_case(
        owner,
        project_id,
        agent_id,
        expected_sources=[
            source(leave["id"], "  25 days of annual leave  "),
            source(parking["id"], "north car park"),
        ],
    )

    assert case["reference_answer"] is None
    assert case["expect_fallback"] is False
    assert case["stale"] is False
    assert [
        (s["document_id"], s["document_name"], s["passage"], s["stale"], s["stale_reason"])
        for s in case["expected_sources"]
    ] == [
        (leave["id"], "leave.txt", "25 days of annual leave", False, None),
        (parking["id"], "parking.txt", "north car park", False, None),
    ]
    path = evaluation_path(owner, project_id, agent_id, "cases")
    assert (await owner.client.get(f"{path}/{case['id']}")).json() == case
    assert (await owner.client.get(path)).json() == [case]

    # Editing replaces them.
    edited = await owner.client.put(
        f"{path}/{case['id']}",
        json={"question": "Q", "expected_sources": [source(parking["id"], "car park")]},
    )
    assert edited.status_code == 200, edited.text
    assert [s["passage"] for s in edited.json()["expected_sources"]] == ["car park"]


async def test_a_passage_is_up_to_a_thousand_characters_of_a_document_in_the_project(
    app: FastAPI, owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    _, project_id, agent_id = await ready_agent(app, owner)
    leave = await leave_document(owner, project_id)
    other_project = await create_project(owner, "Elsewhere")
    elsewhere = await upload(app, owner, other_project, "parking.txt", PARKING.encode())

    for passage in ("x" * 1001, "   "):
        refused = await post_case(
            owner, project_id, agent_id, expected_sources=[source(leave["id"], passage)]
        )
        assert refused.status_code == 422
    assert (
        await post_case(
            owner, project_id, agent_id, expected_sources=[source(leave["id"], "x" * 1000)]
        )
    ).status_code == 201
    for document_id in (elsewhere["id"], str(uuid.uuid4())):
        refused = await post_case(
            owner, project_id, agent_id, expected_sources=[source(document_id, "car park")]
        )
        assert (refused.status_code, refused.json()) == (422, {"detail": DOCUMENT_NOT_FOUND})


async def test_a_passage_no_chunk_holds_is_flagged_stale_when_saved(
    app: FastAPI, owner: SignedUpMember
) -> None:
    _, project_id, agent_id = await ready_agent(app, owner)
    leave = await leave_document(owner, project_id)

    case = await add_case(
        owner, project_id, agent_id, expected_sources=[source(leave["id"], "forty days")]
    )

    assert case["stale"] is True
    (expected,) = case["expected_sources"]
    assert (expected["stale"], expected["stale_reason"]) == (True, "passage_missing")


async def test_expect_fallback_text_stands_alone_and_the_refusal_names_the_field(
    app: FastAPI, owner: SignedUpMember
) -> None:
    _, project_id, agent_id = await ready_agent(app, owner)
    leave = await leave_document(owner, project_id)

    case = await add_case(owner, project_id, agent_id, expect_fallback=True)
    assert (case["expect_fallback"], case["reference_answer"], case["expected_sources"]) == (
        True,
        None,
        [],
    )

    with_reference = await post_case(
        owner, project_id, agent_id, expect_fallback=True, reference_answer="25 days."
    )
    assert (with_reference.status_code, with_reference.json()) == (
        422,
        {"detail": FALLBACK_WITH_REFERENCE},
    )
    with_source = await post_case(
        owner,
        project_id,
        agent_id,
        expect_fallback=True,
        expected_sources=[source(leave["id"], "25 days")],
    )
    assert (with_source.status_code, with_source.json()) == (422, {"detail": FALLBACK_WITH_SOURCE})
    edited = await owner.client.put(
        evaluation_path(owner, project_id, agent_id, "cases", case["id"]),
        json={"question": "Q", "expect_fallback": True, "reference_answer": "Yes."},
    )
    assert (edited.status_code, edited.json()) == (422, {"detail": FALLBACK_WITH_REFERENCE})

    nothing = await post_case(owner, project_id, agent_id, expect_fallback=False)
    assert (nothing.status_code, nothing.json()) == (422, {"detail": NO_EXPECTATION})


# Checking expectations in a Run


async def test_an_expected_source_the_answer_cited_passes(
    app: FastAPI, owner: SignedUpMember
) -> None:
    judge_with(app, three_tokens)
    _, project_id, agent_id = await ready_agent(app, owner)
    leave = await leave_document(owner, project_id)
    # Matched ignoring case and whitespace.
    await add_case(
        owner,
        project_id,
        agent_id,
        expected_sources=[source(leave["id"], "25   DAYS of annual\nleave")],
    )

    results = await evaluated(owner, project_id, agent_id)

    result = only_result(results)
    assert result["passed"] is True
    assert result["verdicts"] == [
        {
            "kind": "expected_source",
            "outcome": "pass",
            "reason": "The answer cited the passage of leave.txt.",
        },
        {
            "kind": "grounding",
            "outcome": "pass",
            "reason": "Fake judge: the answer cites the knowledge base.",
        },
    ]
    (case,) = results["cases"]
    assert case["stale_expectation"] is False
    assert case["expect_fallback"] is False
    assert [(s["document_name"], s["passage"]) for s in case["expected_sources"]] == [
        ("leave.txt", "25   DAYS of annual\nleave")
    ]


async def uncited(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
    yield "Everyone gets twenty-five days of annual leave a year."


async def test_an_expected_source_retrieved_but_uncited_fails_and_says_so(
    app: FastAPI, owner: SignedUpMember
) -> None:
    judge_with(app, uncited)
    _, project_id, agent_id = await ready_agent(app, owner)
    leave = await leave_document(owner, project_id)
    await add_case(owner, project_id, agent_id, expected_sources=[source(leave["id"], "25 days")])

    result = only_result(await evaluated(owner, project_id, agent_id))

    assert result["passed"] is False
    assert result["verdicts"][0] == {
        "kind": "expected_source",
        "outcome": "fail",
        "reason": "The passage of leave.txt was retrieved but the answer didn't cite it.",
    }


async def test_an_expected_source_never_retrieved_fails(
    app: FastAPI, owner: SignedUpMember
) -> None:
    judge_with(app, three_tokens)
    _, project_id, agent_id = await ready_agent(app, owner)
    parking = await upload(app, owner, project_id, "parking.txt", PARKING.encode())
    # Only the leave policy reaches the model.
    saved = await save_draft(owner, project_id, agent_id, {"retrieval": {**AUTOMATIC, "top_k": 1}})
    assert saved.status_code == 200, saved.text
    await add_case(
        owner, project_id, agent_id, expected_sources=[source(parking["id"], "north car park")]
    )

    result = only_result(await evaluated(owner, project_id, agent_id))

    assert result["verdicts"][0] == {
        "kind": "expected_source",
        "outcome": "fail",
        "reason": "The passage of parking.txt wasn't retrieved, so the answer didn't cite it.",
    }


async def test_a_stale_expected_source_is_skipped_and_its_case_flagged(
    app: FastAPI, owner: SignedUpMember
) -> None:
    judge_with(app, three_tokens)
    _, project_id, agent_id = await ready_agent(app, owner)
    leave = await leave_document(owner, project_id)
    parking = await upload(app, owner, project_id, "parking.txt", PARKING.encode())
    case = await add_case(
        owner,
        project_id,
        agent_id,
        expected_sources=[source(leave["id"], "25 days"), source(parking["id"], "north car park")],
        reference_answer='Everyone gets "twenty-five days".',
    )
    deleted = await owner.client.delete(
        f"{project_path(owner, project_id)}/documents/{parking['id']}"
    )
    assert deleted.status_code == 204, deleted.text

    results = await evaluated(owner, project_id, agent_id)

    result = only_result(results)
    assert outcomes(result) == [
        ("expected_source", "pass"),
        ("expected_source", "stale"),
        ("reference_answer", "pass"),
        ("grounding", "pass"),
    ]
    assert result["verdicts"][1]["reason"] == "parking.txt has been deleted, so this was skipped."
    # A Stale Verdict is neither pass nor fail.
    assert result["passed"] is True
    assert results["run"]["sides"][0]["cases_passed"] == 1
    (copied,) = results["cases"]
    assert copied["stale_expectation"] is True
    # The set flags the case too; the Document's name stays as a tombstone.
    listed = (await owner.client.get(evaluation_path(owner, project_id, agent_id, "cases"))).json()
    (flagged,) = listed
    assert flagged["id"] == case["id"]
    assert flagged["stale"] is True
    assert [
        (s["document_id"], s["document_name"], s["stale"], s["stale_reason"])
        for s in flagged["expected_sources"]
    ] == [
        (leave["id"], "leave.txt", False, None),
        (None, "parking.txt", True, "document_deleted"),
    ]


async def test_a_passage_missing_from_the_current_edition_is_stale(
    app: FastAPI, owner: SignedUpMember
) -> None:
    judge_with(app, three_tokens)
    _, project_id, agent_id = await ready_agent(app, owner)
    leave = await leave_document(owner, project_id)
    await add_case(
        owner,
        project_id,
        agent_id,
        expected_sources=[source(leave["id"], "thirty days")],
        reference_answer='"twenty-five days"',
    )

    result = only_result(await evaluated(owner, project_id, agent_id))

    assert result["verdicts"][0] == {
        "kind": "expected_source",
        "outcome": "stale",
        "reason": "No Chunk of leave.txt's current Edition holds the passage, so this was skipped.",
    }


async def test_expect_fallback_text_passes_on_the_fallback_text(
    app: FastAPI, owner: SignedUpMember
) -> None:
    await use_default_model(owner)
    project_id = await create_project(owner)
    agent = await create_automatic_agent(owner, project_id)
    await add_case(
        owner, project_id, agent["id"], question="What is on the menu?", expect_fallback=True
    )

    result = only_result(await evaluated(owner, project_id, agent["id"]))

    assert result["answer"] == DEFAULT_FALLBACK_TEXT
    # The Fallback Text has nothing to ground, and nothing else is asked: no judge.
    assert result["verdicts"] == [
        {"kind": "fallback", "outcome": "pass", "reason": "The answer was the Fallback Text."}
    ]
    assert result["passed"] is True


async def test_expect_fallback_text_passes_on_the_refusal_text(
    app: FastAPI, owner: SignedUpMember
) -> None:
    judge_with(app, three_tokens)
    _, project_id, agent_id = await ready_agent(app, owner)
    saved = await save_draft(
        owner,
        project_id,
        agent_id,
        {"retrieval": AUTOMATIC, "guardrails": {"input_mode": "block", "refusal_text": REFUSAL}},
    )
    assert saved.status_code == 200, saved.text
    app.state.guardrails.classifier.rules = [GUARDRAIL_RULE]
    await add_case(owner, project_id, agent_id, question=ATTACK, expect_fallback=True)

    result = only_result(await evaluated(owner, project_id, agent_id))

    assert result["answer"] == REFUSAL
    assert outcomes(result)[0] == ("fallback", "pass")
    assert result["verdicts"][0]["reason"] == "The answer was the Refusal text."


async def test_expect_fallback_text_fails_on_any_other_answer(
    app: FastAPI, owner: SignedUpMember
) -> None:
    judge_with(app, three_tokens)
    _, project_id, agent_id = await ready_agent(app, owner)
    await add_case(owner, project_id, agent_id, expect_fallback=True)

    result = only_result(await evaluated(owner, project_id, agent_id))

    assert result["passed"] is False
    assert result["verdicts"] == [
        {
            "kind": "fallback",
            "outcome": "fail",
            "reason": "The answer wasn't the Fallback Text or the Refusal text.",
        },
        {
            "kind": "grounding",
            "outcome": "pass",
            "reason": "Fake judge: the answer cites the knowledge base.",
        },
    ]
