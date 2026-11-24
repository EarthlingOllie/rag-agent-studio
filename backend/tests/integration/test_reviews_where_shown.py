"""API seam and task seam: reviewing where Verdicts are shown (spec 18, ticket 18-04). An Editor
agrees or disagrees with a judged Verdict in Run results or a Live Verdict check in the Trace;
the review is stored with ``from_sample`` false, shown on the Verdict, takes its target out of
the Review sample, and can be replaced or removed.

Run Verdicts come from spec 14's flow with a scripted ``FunctionModel`` and the fake judge; Live
Verdicts from spec 15's, judged eagerly in the background.
"""

import uuid
from datetime import timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from tests.conftest import ClientFactory, MemberFactory, SignedUpMember, TenantFactory
from tests.fakes.clock import ControllableClock
from tests.integration.test_evaluation import (
    FAILING,
    REFERENCE,
    add_case,
    evaluated,
    evaluation_path,
    judge_with,
)
from tests.integration.test_evaluation_expectations import add_case as add_expectations
from tests.integration.test_evaluation_expectations import leave_document, source
from tests.integration.test_evaluation_settings import set_repeats
from tests.integration.test_live_verdict_context import conversation
from tests.integration.test_live_verdict_reviews import remembering, reviewed_item
from tests.integration.test_live_verdicts import message_id, trace
from tests.integration.test_playground import LEAVE, ready_agent, three_tokens
from tests.integration.test_retention import purge, set_window
from tests.integration.test_verdict_reviews import (
    QUESTION,
    agreement,
    judged_once,
    next_item,
    reviewed,
)
from tests.integration.test_version_metrics import roll_up

REASON_MAX = 1000


@pytest.fixture
async def visitor(new_client: ClientFactory) -> httpx.AsyncClient:
    """A browser on someone's website: no Studio session."""
    return await new_client()


def verdict_review_path(member: SignedUpMember, verdict_id: str) -> str:
    return f"/api/organisations/{member.organisation_id}/verdicts/{verdict_id}/review"


def live_review_path(member: SignedUpMember, live_verdict_id: str, check: str) -> str:
    return (
        f"/api/organisations/{member.organisation_id}/live-verdicts/{live_verdict_id}"
        f"/checks/{check}/review"
    )


async def put_review(
    member: SignedUpMember, path: str, outcome: str, reason: str | None = None
) -> httpx.Response:
    return await member.client.put(path, json={"outcome": outcome, "reason": reason})


async def put_ok(
    member: SignedUpMember, path: str, outcome: str, reason: str | None = None
) -> dict[str, Any]:
    response = await put_review(member, path, outcome, reason)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def results_of(member: SignedUpMember, project_id: str, agent_id: str, run_id: str) -> Any:
    response = await member.client.get(
        evaluation_path(member, project_id, agent_id, "runs", run_id, "results")
    )
    assert response.status_code == 200, response.text
    return response.json()


def verdicts_of(results: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The only answer's Verdicts, by kind."""
    ((case,),) = [results["cases"]]
    (answer,) = case["results"]
    return {v["kind"]: v for v in answer["verdicts"]}


async def served(member: SignedUpMember) -> set[str]:
    """Every item the Review sample serves, as Run Verdict IDs or Live Verdict IDs with the
    check, without reviewing any: each is drawn many times from the seeded random source."""
    found: set[str] = set()
    for _ in range(16):
        item = (await next_item(member))["item"]
        if item is None:
            break
        found.add(item["verdict_id"] or f"{item['live_verdict_id']}:{item['check']}")
    return found


# Run results


async def test_an_editor_agrees_or_disagrees_with_a_run_verdict_and_it_is_shown_there(
    app: FastAPI, owner: SignedUpMember, member_factory: MemberFactory, clock: ControllableClock
) -> None:
    editor = await member_factory(owner, "editor")
    project_id, agent_id, results = await judged_once(app, owner, FAILING)
    run_id = results["run"]["id"]
    verdicts = verdicts_of(results)
    reference, grounding = verdicts["reference_answer"], verdicts["grounding"]
    assert (reference["review"], grounding["review"]) == (None, None)

    given = await put_ok(
        editor, verdict_review_path(editor, reference["id"]), "pass", "It does say 25 days."
    )

    expected = {
        "outcome": "pass",
        "reason": "It does say 25 days.",
        "reviewed_by": editor.name,
        "reviewed_at": clock.now().isoformat().replace("+00:00", "Z"),
        "from_sample": False,
        "purged_at": None,
    }
    assert given == expected
    shown = verdicts_of(await results_of(owner, project_id, agent_id, run_id))
    assert shown["reference_answer"]["review"] == expected
    assert shown["grounding"]["review"] is None
    # Only the Verdict reviewed changed: its outcome and reason are the Evaluation Model's.
    assert {k: v for k, v in shown["reference_answer"].items() if k != "review"} == {
        k: v for k, v in reference.items() if k != "review"
    }
    # It left the Review sample; the other judged Verdict is still there.
    assert await served(owner) == {grounding["id"]}
    # A review from elsewhere never counts towards agreement.
    assert (await agreement(owner))["current"]["reviews"] == 0


async def test_reviewing_again_replaces_the_review_and_removing_it_returns_it_to_the_sample(
    app: FastAPI, owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    project_id, agent_id, results = await judged_once(app, owner)
    run_id = results["run"]["id"]
    grounding = verdicts_of(results)["grounding"]
    path = verdict_review_path(owner, grounding["id"])
    await put_ok(owner, path, "fail", "It cites nothing.")

    replaced = await put_ok(editor, verdict_review_path(editor, grounding["id"]), "pass")

    assert (replaced["outcome"], replaced["reason"], replaced["reviewed_by"]) == (
        "pass",
        None,
        editor.name,
    )
    shown = verdicts_of(await results_of(owner, project_id, agent_id, run_id))["grounding"]
    assert shown["review"] == replaced

    removed = await owner.client.delete(path)

    assert removed.status_code == 204, removed.text
    shown = verdicts_of(await results_of(owner, project_id, agent_id, run_id))["grounding"]
    assert shown["review"] is None
    assert grounding["id"] in await served(owner)
    # Nothing left to remove.
    assert (await owner.client.delete(path)).status_code == 404


async def test_replacing_a_sample_review_here_stops_it_counting_towards_agreement(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id, agent_id, results = await judged_once(app, owner, FAILING)
    item = (await next_item(owner))["item"]
    await reviewed(owner, item["verdict_id"], "pass", "Close enough.")
    shown = verdicts_of(await results_of(owner, project_id, agent_id, results["run"]["id"]))
    (sampled,) = [v for v in shown.values() if v["id"] == item["verdict_id"]]
    assert sampled["review"]["from_sample"] is True
    assert sampled["review"]["reason"] == "Close enough."
    assert (await agreement(owner))["current"]["reviews"] == 1

    replaced = await put_ok(owner, verdict_review_path(owner, item["verdict_id"]), "fail")

    assert replaced["from_sample"] is False
    assert (await agreement(owner))["current"]["reviews"] == 0
    # It stays out of the sample: it is reviewed.
    assert item["verdict_id"] not in await served(owner)


async def test_only_a_judged_reference_answer_or_grounding_verdict_can_be_reviewed(
    app: FastAPI, owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    judge_with(app, three_tokens)
    _, project_id, agent_id = await ready_agent(app, owner)
    await set_repeats(owner, 1)
    document = await leave_document(owner, project_id)
    await add_expectations(
        owner,
        project_id,
        agent_id,
        reference_answer=REFERENCE,
        expected_sources=[source(document["id"], LEAVE)],
    )
    verdicts = verdicts_of(await evaluated(owner, project_id, agent_id))
    other = await tenant_factory()
    reference = verdicts["reference_answer"]["id"]

    expected_source = await put_review(
        owner, verdict_review_path(owner, verdicts["expected_source"]["id"]), "pass"
    )
    unknown = await put_review(owner, verdict_review_path(owner, str(uuid.uuid4())), "pass")
    elsewhere = await put_review(other, verdict_review_path(other, reference), "pass")
    too_long = await put_review(
        owner, verdict_review_path(owner, reference), "fail", "x" * (REASON_MAX + 1)
    )
    not_an_outcome = await put_review(owner, verdict_review_path(owner, reference), "stale")

    assert [r.status_code for r in (expected_source, unknown, elsewhere)] == [404] * 3
    assert [r.status_code for r in (too_long, not_an_outcome)] == [422] * 2
    assert verdicts["expected_source"]["review"] is None
    await put_ok(owner, verdict_review_path(owner, reference), "fail", "x" * REASON_MAX)
    # Another Organisation can't remove it either.
    assert (await other.client.delete(verdict_review_path(other, reference))).status_code == 404
    assert (await owner.client.delete(verdict_review_path(owner, reference))).status_code == 204


async def test_a_run_with_several_cases_carries_each_verdicts_own_review(
    app: FastAPI, owner: SignedUpMember
) -> None:
    judge_with(app, three_tokens)
    _, project_id, agent_id = await ready_agent(app, owner)
    await set_repeats(owner, 1)
    await add_case(owner, project_id, agent_id, QUESTION)
    await add_case(owner, project_id, agent_id, "And sick days?")
    results = await evaluated(owner, project_id, agent_id)
    ids = [v["id"] for case in results["cases"] for r in case["results"] for v in r["verdicts"]]
    assert len(ids) == 4

    for verdict_id, outcome in zip(ids, ("pass", "fail", "pass", "fail"), strict=True):
        await put_ok(owner, verdict_review_path(owner, verdict_id), outcome)

    shown = await results_of(owner, project_id, agent_id, results["run"]["id"])
    by_id = {
        v["id"]: v["review"]["outcome"]
        for case in shown["cases"]
        for r in case["results"]
        for v in r["verdicts"]
    }
    assert by_id == dict(zip(ids, ("pass", "fail", "pass", "fail"), strict=True))


# The Trace


async def test_an_editor_reviews_each_check_of_a_live_verdict_in_the_trace(
    app: FastAPI,
    owner: SignedUpMember,
    member_factory: MemberFactory,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    editor = await member_factory(owner, "editor")
    agent = await remembering(app, owner, 0)
    (events,) = await conversation(visitor, agent, "How much annual leave?")
    verdict = (await trace(owner, agent, message_id(events)))["live_verdict"]
    assert (verdict["grounded"]["review"], verdict["answers_question"]["review"]) == (None, None)
    live_id = verdict["id"]

    given = await put_ok(
        editor, live_review_path(editor, live_id, "answers_question"), "pass", "It does answer."
    )

    assert given == {
        "outcome": "pass",
        "reason": "It does answer.",
        "reviewed_by": editor.name,
        "reviewed_at": clock.now().isoformat().replace("+00:00", "Z"),
        "from_sample": False,
        "purged_at": None,
    }
    shown = (await trace(owner, agent, message_id(events)))["live_verdict"]
    assert shown["answers_question"]["review"] == given
    assert shown["grounded"]["review"] is None
    # Only that check left the Review sample.
    assert await served(owner) == {f"{live_id}:grounding"}
    assert (await agreement(owner))["current"]["reviews"] == 0

    await put_ok(owner, live_review_path(owner, live_id, "grounding"), "fail")
    assert await served(owner) == set()
    removed = await owner.client.delete(live_review_path(owner, live_id, "answers_question"))

    assert removed.status_code == 204, removed.text
    shown = (await trace(owner, agent, message_id(events)))["live_verdict"]
    assert shown["answers_question"]["review"] is None
    assert shown["grounded"]["review"]["outcome"] == "fail"
    assert await served(owner) == {f"{live_id}:answers_question"}


async def test_a_live_check_review_names_a_live_check_of_the_organisation(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, tenant_factory: TenantFactory
) -> None:
    agent = await remembering(app, owner, 0)
    (events,) = await conversation(visitor, agent, "How much annual leave?")
    live_id = (await trace(owner, agent, message_id(events)))["live_verdict"]["id"]
    other = await tenant_factory()

    reference = await put_review(
        owner, live_review_path(owner, live_id, "reference_answer"), "pass"
    )
    unknown = await put_review(
        owner, live_review_path(owner, str(uuid.uuid4()), "grounding"), "pass"
    )
    elsewhere = await put_review(other, live_review_path(other, live_id, "grounding"), "pass")
    nothing_to_remove = await owner.client.delete(live_review_path(owner, live_id, "grounding"))

    assert reference.status_code == 422
    assert [r.status_code for r in (unknown, elsewhere, nothing_to_remove)] == [404] * 3
    shown = (await trace(owner, agent, message_id(events)))["live_verdict"]
    assert shown["grounded"]["review"] is None


async def test_after_the_purge_a_live_review_shows_text_purged_and_keeps_its_outcome(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent = await remembering(app, owner, 0)
    assert (await set_window(owner, 7)).status_code == 200
    (events,) = await conversation(visitor, agent, "I am Ada; how much leave?")
    item = (await next_item(owner))["item"]
    await reviewed_item(owner, item, "fail", "Ada would disagree.")
    clock.advance(timedelta(days=7, hours=1))
    await roll_up(clock.now())

    await purge(clock.now())

    verdict = (await trace(owner, agent, message_id(events)))["live_verdict"]
    check = verdict["grounded" if item["check"] == "grounding" else "answers_question"]
    review = check["review"]
    assert (review["outcome"], review["reason"], review["from_sample"]) == ("fail", None, True)
    assert review["purged_at"] == clock.now().isoformat().replace("+00:00", "Z")
    # Its text is gone, so it can't be reviewed again; its review can still be removed.
    replaced = await put_review(
        owner, live_review_path(owner, verdict["id"], item["check"]), "pass"
    )
    assert replaced.status_code == 404
    removed = await owner.client.delete(live_review_path(owner, verdict["id"], item["check"]))
    assert removed.status_code == 204
