"""API seam and task seam: checking guidance on held-out reviews (spec 19, ticket 19-04). An Owner
checks guidance text before saving it: the Evaluation Model re-judges the held-out half of the
current Judging setup's Review sample reviews with it, and the check counts agreed, false passes
and false fails beside the current Judging setup's agreement on the same reviews. Purged targets
are left out, a re-check keeps the same split, and a check never touches a Verdict.

Reviews come from spec 18's Review sample over spec 14's Run Verdicts and spec 15's Live
Verdicts. The judge is the chat model port scripted with ``FunctionModel``: ``guided`` passes
every Verdict asked when the guidance holds ``GUIDED`` and fails it otherwise, so expected counts
don't depend on which reviews the seeded split holds out. The check's task runs eagerly, or is
held back and run by hand to watch it in progress.
"""

import asyncio
import uuid
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo
from pydantic_ai.usage import RequestUsage
from sqlalchemy import select

from app.evaluation import guidance_check_api
from app.evaluation.judge import GUIDANCE_HEADING
from app.evaluation.models import EvaluationVerdict, GuidanceJob, LiveVerdict
from app.evaluation.tasks import run_guidance_job_task
from tests.conftest import ClientFactory, MemberFactory, SignedUpMember
from tests.fakes.clock import ControllableClock
from tests.integration.test_conversations import conversations_path, listed
from tests.integration.test_evaluation import add_case, evaluated
from tests.integration.test_evaluation_budget import budget
from tests.integration.test_evaluation_settings import set_evaluation_model, set_repeats
from tests.integration.test_judging_guidance import read_guidance, saved
from tests.integration.test_live_verdict_reviews import reviewed_item
from tests.integration.test_live_verdicts import live_agent, reply, sampling, scripted
from tests.integration.test_organisation_cost import org_cost
from tests.integration.test_playground import ready_agent
from tests.integration.test_provider_credentials import ANTHROPIC_KEY, added
from tests.integration.test_verdict_reviews import next_item

GUIDED = "Partial answers that say what they don't cover pass."
UNGUIDED = "Be strict about citations."
# Each judging call reports 1,000 tokens in and 100 out: at gpt-4.1-mini's $0.40 in and $1.60
# out per million, 1,000 x $0.40 / 1M + 100 x $1.60 / 1M.
CALL_COST = Decimal("0.00056")
NOV_5 = "2026-11-05"


@pytest.fixture
async def visitor(new_client: ClientFactory) -> httpx.AsyncClient:
    return await new_client()


class Judge:
    """Passes every Verdict asked when the guidance holds ``GUIDED``, else fails it; counts the
    calls made with each guidance and runs ``during`` (if set) inside each call."""

    def __init__(self) -> None:
        self.guidance: list[str] = []
        self.during: Callable[[], None] | None = None
        self.failing = False

    def __call__(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        guidance = (info.instructions or "").partition(GUIDANCE_HEADING)[2].strip()
        self.guidance.append(guidance)
        if self.during is not None:
            self.during()
        if self.failing:
            raise ModelHTTPError(status_code=503, model_name="gpt-4.1-mini")
        passed = GUIDED in guidance
        verdict = {"passed": passed, "reason": "Scripted."}
        verdicts = {k: verdict for k in ("reference_answer", "grounding", "answers_question")}
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, verdicts)],
            usage=RequestUsage(input_tokens=1_000, output_tokens=100),
        )

    @property
    def checking(self) -> list[str]:
        """The calls made with guidance: the check's (no judgement saved any)."""
        return [g for g in self.guidance if g]


@pytest.fixture
def judge(app: FastAPI) -> Judge:
    found = Judge()
    scripted(app, judgement=found)
    return found


def jobs_path(member: SignedUpMember, *rest: str) -> str:
    return "/".join([f"/api/organisations/{member.organisation_id}/guidance-jobs", *rest])


async def start_check(member: SignedUpMember, text: str) -> httpx.Response:
    return await member.client.post(
        f"/api/organisations/{member.organisation_id}/judging-guidance/checks", json={"text": text}
    )


async def checked(member: SignedUpMember, text: str) -> dict[str, Any]:
    response = await start_check(member, text)
    assert response.status_code == 202, response.text
    job_id = response.json()["id"]
    return await job(member, job_id)


async def job(member: SignedUpMember, job_id: str) -> dict[str, Any]:
    response = await member.client.get(jobs_path(member, job_id))
    assert response.status_code == 200, response.text
    found: dict[str, Any] = response.json()
    return found


async def latest(member: SignedUpMember) -> Any:
    response = await member.client.get(jobs_path(member, "latest"))
    assert response.status_code == 200, response.text
    return response.json()


async def cancel(member: SignedUpMember, job_id: str) -> httpx.Response:
    return await member.client.post(jobs_path(member, job_id, "cancel"))


async def review_all(member: SignedUpMember, outcome: str) -> int:
    """Reviews every item the Review sample serves with ``outcome``; how many."""
    count = 0
    while (item := (await next_item(member))["item"]) is not None:
        await reviewed_item(member, item, outcome)
        count += 1
    return count


async def live_replies(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, questions: int
) -> dict[str, Any]:
    """A live Agent with every reply judged, and ``questions`` replies, each in its own
    Conversation: two reviewable checks each."""
    agent = await live_agent(app, owner)
    await sampling(owner, agent, 100)
    for n in range(questions):
        await reply(visitor, agent, f"Question {n}: how much annual leave do I get?")
    return agent


async def run_verdicts(app: FastAPI, owner: SignedUpMember, cases: int) -> None:
    """A Run of ``cases`` Reference answer cases, one answer each: two reviewable Verdicts
    (Reference answer and grounding) per case."""
    _, project_id, agent_id = await ready_agent(app, owner)
    for n in range(cases):
        await add_case(owner, project_id, agent_id, f"Question {n}: how much leave do I get?")
    await set_repeats(owner, 1)
    await evaluated(owner, project_id, agent_id)


async def verdict_rows(app: FastAPI, member: SignedUpMember) -> list[tuple[Any, ...]]:
    """Every Verdict and Live Verdict of the Organisation, as stored."""
    organisation_id = uuid.UUID(member.organisation_id)
    async with app.state.sessionmaker() as session:
        runs = await session.scalars(
            select(EvaluationVerdict)
            .where(EvaluationVerdict.organisation_id == organisation_id)
            .order_by(EvaluationVerdict.id)
        )
        lives = await session.scalars(
            select(LiveVerdict)
            .where(LiveVerdict.organisation_id == organisation_id)
            .order_by(LiveVerdict.id)
        )
        return [(v.id, v.kind, v.outcome, v.reason) for v in runs] + [
            (v.id, v.status, v.grounded, v.answers_question, v.judging_guidance_version, v.cost_usd)
            for v in lives
        ]


async def splits(app: FastAPI, member: SignedUpMember) -> list[tuple[set[str], set[str]]]:
    """Each guidance job's stored split (held-out half, other half), oldest first."""
    async with app.state.sessionmaker() as session:
        jobs = await session.scalars(
            select(GuidanceJob)
            .where(GuidanceJob.organisation_id == uuid.UUID(member.organisation_id))
            .order_by(GuidanceJob.created_at)
        )
        return [(set(j.held_out), set(j.other_half)) for j in jobs]


@pytest.fixture
def held_back(monkeypatch: pytest.MonkeyPatch) -> list[uuid.UUID]:
    """Holds back each guidance job's task; the jobs' IDs."""
    held: list[uuid.UUID] = []

    async def hold(job_id: uuid.UUID) -> None:
        held.append(job_id)

    monkeypatch.setattr(guidance_check_api, "enqueue_guidance_job", hold)
    return held


async def run_now(job_id: uuid.UUID) -> None:
    """Runs a held-back guidance job's task as the worker would (in a thread: the task runs its
    own event loop)."""
    result = await asyncio.to_thread(run_guidance_job_task.apply, args=(str(job_id),))
    result.get(disable_sync_subtasks=False)


@pytest.fixture
async def on_test_loop() -> Callable[[Any], Any]:
    """Runs a coroutine on the test's own event loop from inside the task's thread, so a call to
    the scripted judge can read or cancel the job through the API while it runs."""
    loop = asyncio.get_running_loop()

    def run(coroutine: Any) -> Any:
        return asyncio.run_coroutine_threadsafe(coroutine, loop).result()

    return run


# Checking


async def test_a_check_re_judges_the_held_out_half_with_the_guidance_beside_current_agreement(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, judge: Judge
) -> None:
    await run_verdicts(app, owner, 1)
    await live_replies(app, owner, visitor, 2)
    # Without guidance the Evaluation Model failed everything; the Editor passes everything.
    assert await review_all(owner, "pass") == 6
    before = await verdict_rows(app, owner)

    found = await checked(owner, f"  {GUIDED}  ")

    assert found == {
        "id": found["id"],
        "kind": "check",
        "status": "completed",
        "text": GUIDED,
        "held_out": 3,
        "judged": 3,
        "left_out": 0,
        "agreed": 3,
        "false_passes": 0,
        "false_fails": 0,
        "agreed_before": 0,
        "low_sample": True,
        "cost_usd": found["cost_usd"],
        "error_reason": None,
        "requested_by": owner.name,
        "created_at": found["created_at"],
        "started_at": found["started_at"],
        "finished_at": found["finished_at"],
    }
    # A Live Verdict's two checks share one call, as do a Run result's two Verdicts.
    assert 2 <= len(judge.checking) <= 3
    assert judge.checking == [GUIDED] * len(judge.checking)
    # A check never creates or changes a Verdict or Live Verdict.
    assert await verdict_rows(app, owner) == before
    assert await latest(owner) == found


async def test_guidance_that_passes_what_editors_failed_counts_false_passes(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, judge: Judge
) -> None:
    await live_replies(app, owner, visitor, 2)
    await review_all(owner, "fail")

    found = await checked(owner, GUIDED)

    assert (found["held_out"], found["judged"]) == (2, 2)
    assert (found["agreed"], found["false_passes"], found["false_fails"]) == (0, 2, 0)
    assert found["agreed_before"] == 2


async def test_guidance_that_fails_what_editors_passed_counts_false_fails(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, judge: Judge
) -> None:
    await live_replies(app, owner, visitor, 1)
    await review_all(owner, "pass")

    found = await checked(owner, UNGUIDED)

    assert (found["agreed"], found["false_passes"], found["false_fails"]) == (0, 0, 1)
    assert judge.checking == [UNGUIDED]


async def test_purged_targets_are_left_out(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, judge: Judge
) -> None:
    agent = await live_replies(app, owner, visitor, 2)
    await review_all(owner, "pass")
    for row in (await listed(owner, agent["project_id"]))["items"]:
        deleted = await owner.client.delete(
            conversations_path(owner, agent["project_id"], row["id"])
        )
        assert deleted.status_code == 204, deleted.text

    found = await checked(owner, GUIDED)

    assert found["status"] == "completed"
    assert (found["held_out"], found["judged"], found["left_out"]) == (2, 0, 2)
    assert (found["agreed"], found["agreed_before"]) == (0, 0)
    # Nothing is re-judged without its text.
    assert judge.checking == []
    assert Decimal(found["cost_usd"]) == 0


async def test_a_re_check_keeps_the_split_and_splits_only_new_reviews(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, judge: Judge
) -> None:
    agent = await live_replies(app, owner, visitor, 3)
    await review_all(owner, "pass")
    await checked(owner, GUIDED)

    await checked(owner, UNGUIDED)

    first, again = await splits(app, owner)
    assert again == first
    assert (len(first[0]), len(first[1])) == (3, 3)
    # Two more reviews arrive: the earlier halves stay, and the new ones are split.
    await reply(visitor, agent, "And how much sick leave?")
    await review_all(owner, "pass")
    third = await checked(owner, GUIDED)
    *_, (held_out, other_half) = await splits(app, owner)
    assert first[0] <= held_out
    assert first[1] <= other_half
    assert (len(held_out), len(other_half), third["held_out"]) == (4, 4, 4)


async def test_a_new_judging_setup_gets_its_own_split(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, judge: Judge
) -> None:
    agent = await live_replies(app, owner, visitor, 1)
    await review_all(owner, "pass")
    await checked(owner, GUIDED)
    await saved(owner, GUIDED)
    await reply(visitor, agent, "And how much sick leave?")
    await review_all(owner, "pass")

    found = await checked(owner, UNGUIDED)

    first, second = await splits(app, owner)
    assert not (first[0] | first[1]) & (second[0] | second[1])
    # Under the saved guidance the Evaluation Model passed both; the Editor agreed.
    assert (found["held_out"], found["agreed_before"], found["false_fails"]) == (1, 1, 1)


async def test_a_check_needs_a_model_and_enough_reviews(
    app: FastAPI, owner: SignedUpMember, judge: Judge
) -> None:
    response = await start_check(owner, GUIDED)
    assert (response.status_code, response.json()["detail"]) == (
        422,
        "The Organisation has neither an Evaluation Model nor a Default Model to judge with.",
    )
    await ready_agent(app, owner)
    response = await start_check(owner, GUIDED)
    too_few = "A check needs at least 2 Review sample reviews under the current Judging setup."
    assert (response.status_code, response.json()["detail"]) == (422, too_few)
    assert (await start_check(owner, "x" * 2001)).status_code == 422
    assert await latest(owner) is None


# One at a time, progress and cancelling


async def test_one_guidance_job_at_a_time_and_owners_cancel_it(
    app: FastAPI,
    owner: SignedUpMember,
    member_factory: MemberFactory,
    visitor: httpx.AsyncClient,
    judge: Judge,
    held_back: list[uuid.UUID],
) -> None:
    editor = await member_factory(owner, "editor")
    await live_replies(app, owner, visitor, 1)
    await review_all(owner, "pass")
    started = await start_check(owner, GUIDED)
    assert started.status_code == 202, started.text
    assert started.json()["status"] == "queued"

    second = await start_check(owner, UNGUIDED)
    assert (second.status_code, second.json()["detail"]) == (
        409,
        "A draft or check is already in progress in the Organisation.",
    )
    assert (await start_check(editor, GUIDED)).status_code == 403
    assert (await cancel(editor, started.json()["id"])).status_code == 403
    assert (await editor.client.get(jobs_path(editor, "latest"))).status_code == 403

    cancelled = await cancel(owner, started.json()["id"])
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["finished_at"] is not None
    # Its task, picked up after the cancel, judges nothing.
    await run_now(held_back[0])
    assert judge.checking == []
    assert (await job(owner, started.json()["id"]))["status"] == "cancelled"
    # Only a job in progress can be cancelled; another can start now.
    again = await cancel(owner, started.json()["id"])
    assert (again.status_code, again.json()["detail"]) == (
        409,
        "Only a draft or check in progress can be cancelled.",
    )
    assert (await start_check(owner, UNGUIDED)).status_code == 202


async def test_an_owner_reads_a_checks_progress_and_cancels_it_while_it_runs(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    judge: Judge,
    held_back: list[uuid.UUID],
    on_test_loop: Callable[[Any], Any],
) -> None:
    await live_replies(app, owner, visitor, 3)
    await review_all(owner, "pass")
    job_id = (await start_check(owner, GUIDED)).json()["id"]
    seen: list[dict[str, Any]] = []

    def watch_and_cancel() -> None:
        seen.append(on_test_loop(job(owner, job_id)))
        assert on_test_loop(cancel(owner, job_id)).status_code == 200

    judge.during = watch_and_cancel

    await run_now(held_back[0])

    (running,) = seen
    assert (running["status"], running["held_out"], running["judged"]) == ("running", 3, 0)
    assert running["started_at"] is not None
    found = await job(owner, job_id)
    assert found["status"] == "cancelled"
    # The call under way when it was cancelled still counts, with its Cost; no other is made.
    assert len(judge.checking) == 1
    assert 1 <= found["judged"] < 3
    assert Decimal(found["cost_usd"]) == CALL_COST


async def test_a_check_cancelled_during_its_last_call_stays_cancelled(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    judge: Judge,
    held_back: list[uuid.UUID],
    on_test_loop: Callable[[Any], Any],
) -> None:
    await live_replies(app, owner, visitor, 1)
    await review_all(owner, "pass")
    job_id = (await start_check(owner, GUIDED)).json()["id"]
    judge.during = lambda: on_test_loop(cancel(owner, job_id))

    await run_now(held_back[0])

    found = await job(owner, job_id)
    assert (found["status"], found["judged"]) == ("cancelled", 1)


async def test_another_job_id_is_not_found(owner: SignedUpMember) -> None:
    unknown = str(uuid.uuid4())

    assert (await owner.client.get(jobs_path(owner, unknown))).status_code == 404
    assert (await cancel(owner, unknown)).status_code == 404


async def test_a_judge_error_fails_the_check_keeping_what_it_spent(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, judge: Judge
) -> None:
    await live_replies(app, owner, visitor, 1)
    await review_all(owner, "pass")
    judge.failing = True

    found = await checked(owner, GUIDED)

    assert found["status"] == "failed"
    assert found["error_reason"]
    assert found["judged"] == 0
    assert Decimal(found["cost_usd"]) == 0
    assert found["finished_at"] is not None


async def test_a_check_started_before_the_evaluation_model_changed_fails(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    judge: Judge,
    held_back: list[uuid.UUID],
) -> None:
    await live_replies(app, owner, visitor, 1)
    await review_all(owner, "pass")
    job_id = (await start_check(owner, GUIDED)).json()["id"]
    claude = await added(owner, provider="anthropic", api_key=ANTHROPIC_KEY, name="Claude")
    await set_evaluation_model(owner, claude["id"], "claude-haiku-4-5")

    await run_now(held_back[0])

    found = await job(owner, job_id)
    assert (found["status"], found["error_reason"]) == (
        "failed",
        "The Judging setup changed after the check started. Check again.",
    )
    assert judge.checking == []


# Cost


async def test_a_checks_cost_is_in_organisation_cost_and_never_the_evaluation_budget(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    judge: Judge,
    clock: ControllableClock,
) -> None:
    await live_replies(app, owner, visitor, 2)
    await review_all(owner, "pass")
    (line,) = (await org_cost(owner, start=NOV_5, end=NOV_5, group_by="agent"))["rows"]
    spent_before = (await budget(owner))["spent_usd"]

    found = await checked(owner, GUIDED)

    calls = len(judge.checking)
    assert Decimal(found["cost_usd"]) == calls * CALL_COST
    (counted,) = (await org_cost(owner, start=NOV_5, end=NOV_5, group_by="agent"))["rows"]
    assert Decimal(counted["evaluation_usd"]) == Decimal(line["evaluation_usd"]) + calls * CALL_COST
    assert (await budget(owner))["spent_usd"] == spent_before
    # Another day's cost holds none of it.
    assert (await org_cost(owner, start="2026-11-04", end="2026-11-04"))["rows"] == []


# Saving


async def test_the_saved_version_keeps_its_latest_check_result(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, judge: Judge
) -> None:
    await live_replies(app, owner, visitor, 2)
    await review_all(owner, "pass")
    await checked(owner, UNGUIDED)
    await checked(owner, GUIDED)

    await saved(owner, GUIDED)
    await saved(owner, "Another text, never checked.")

    unchecked, kept = (await read_guidance(owner))["versions"]
    assert kept["check"] == {
        "reviews": 2,
        "agreed": 2,
        "false_passes": 0,
        "false_fails": 0,
        "agreed_before": 0,
        "low_sample": True,
    }
    assert unchecked["check"] is None
