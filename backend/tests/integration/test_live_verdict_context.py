"""API seam and task seam: a Live Verdict's context, errors and retention (spec 15).

The judge of a follow-up sees the reply's Remembered turns, and never the Agent's system prompt
or the Project Instructions. A judge error or timeout is an ``error``, tried once. A reply whose
text, or a Remembered turn's, is Purged before it is judged is ``skipped`` without calling the
judge. The Purge, and deleting a Conversation, clear a Live Verdict's reasons and stamp it
purged-at, while its outcomes and Cost stay.

Replies stream from a scripted ``FunctionModel`` and the judge is the same model's structured
output, as in ``test_live_verdicts``. To purge a reply before it is judged, the judging task is
held back from the widget and then run directly, as the worker would.
"""

import asyncio
import uuid
from datetime import timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo

from app.embed import api as embed_api
from app.evaluation.judge import TIMEOUT
from app.evaluation.ports import current_evaluation_ports
from app.evaluation.tasks import judge_live_verdict_task
from tests.agents import AUTOMATIC, parse_sse, save_draft
from tests.conftest import ClientFactory, SignedUpMember
from tests.fakes.clock import ControllableClock
from tests.integration.test_agent_versions import published
from tests.integration.test_conversations import conversations_path, listed
from tests.integration.test_embed import conversation_token, send
from tests.integration.test_live_verdicts import (
    PASSED,
    judged,
    live_agent,
    live_verdict,
    sampling,
    scripted,
)
from tests.integration.test_project_instructions_versions import published as instructions
from tests.integration.test_retention import purge, set_window
from tests.integration.test_version_metrics import roll_up

SYSTEM_PROMPT = "Secret house style: always say hello."
HOUSE_RULES = "House rules: never mention the canteen."


@pytest.fixture
async def visitor(new_client: ClientFactory) -> httpx.AsyncClient:
    """A browser on someone's website: no Studio session."""
    return await new_client()


def recording(calls: list[str]) -> Any:
    """A judge passing both checks that records the text of each request it is given."""
    judgement = judged(PASSED, PASSED)

    def judge(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        calls.append(
            "\n".join(
                str(part.content)
                for message in messages
                for part in message.parts
                if hasattr(part, "content")
            )
            + "\n"
            + str(info.instructions)
        )
        return judgement(messages, info)

    return judge


async def conversation(
    visitor: httpx.AsyncClient, agent: dict[str, Any], *questions: str
) -> list[list[tuple[str, Any]]]:
    """Asks each question in one new Visitor Conversation; each reply's events."""
    token = await conversation_token(visitor, agent["public_id"])
    replies = []
    for question in questions:
        response = await send(visitor, agent["public_id"], token, question)
        assert response.status_code == 200, response.text
        replies.append(parse_sse(response.text))
    return replies


@pytest.fixture
def held_back(monkeypatch: pytest.MonkeyPatch) -> list[uuid.UUID]:
    """Holds back the judging task of each chosen reply; the IDs of their Live Verdicts."""
    held: list[uuid.UUID] = []

    async def hold(verdict_id: uuid.UUID) -> None:
        held.append(verdict_id)

    monkeypatch.setattr(embed_api, "enqueue_live_verdict", hold)
    return held


async def judge_now(verdict_id: uuid.UUID) -> None:
    """Runs a held-back judging task as the worker would (in a thread: the task runs its own
    event loop)."""
    result = await asyncio.to_thread(judge_live_verdict_task.apply, args=(str(verdict_id),))
    result.get(disable_sync_subtasks=False)


# What the judge is given


async def test_a_follow_up_is_judged_with_its_remembered_turns_and_never_the_instructions(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    calls: list[str] = []
    scripted(app, judgement=recording(calls))
    agent = await live_agent(app, owner)
    await instructions(owner, agent["project_id"], HOUSE_RULES, "Rules")
    behaviour = {"system_prompt": SYSTEM_PROMPT, "remembered_turns": 1}
    draft = {"retrieval": AUTOMATIC, "behaviour": behaviour}
    saved = await save_draft(owner, agent["project_id"], agent["id"], draft)
    assert saved.status_code == 200, saved.text
    await published(owner, agent["project_id"], agent["id"])
    await sampling(owner, agent, 100)

    *_, follow_up = await conversation(
        visitor, agent, "How much annual leave?", "And sick days?", "What about part-timers?"
    )

    verdict = await live_verdict(owner, agent, follow_up)
    assert verdict is not None
    assert verdict["status"] == "judged"
    first, second, third = calls
    assert "<<<EARLIER_TURNS>>>\n" not in first
    assert "Question: How much annual leave?" in second
    # The Version remembers one turn, so the judge is given the one the reply was given.
    assert "<<<EARLIER_TURNS>>>\nQuestion: And sick days?\nAnswer: " in third
    assert "How much annual leave?" not in third
    assert "<<<QUESTION>>>\nWhat about part-timers?\n<<<END_QUESTION>>>" in third
    # Neither the Agent's system prompt nor the Project Instructions reach the judge.
    for call in calls:
        assert SYSTEM_PROMPT not in call
        assert HOUSE_RULES not in call


# A judge that fails


async def test_a_judge_error_is_an_error_with_its_reason_and_is_not_retried(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    calls: list[str] = []

    def outage(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        calls.append("judged")
        raise ModelHTTPError(status_code=503, model_name="gpt-4.1-mini")

    scripted(app, judgement=outage)
    agent = await live_agent(app, owner)
    await sampling(owner, agent, 100)

    (events,) = await conversation(visitor, agent, "How much annual leave?")

    verdict = await live_verdict(owner, agent, events)
    assert verdict is not None
    assert verdict["status"] == "error"
    assert verdict["error_reason"].startswith("The Evaluation Model couldn't judge the answer")
    # Tried once: an outage doesn't multiply spend.
    assert calls == ["judged"]


async def test_a_judge_that_times_out_is_an_error(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    judgement = judged(PASSED, PASSED)

    async def slow(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        await asyncio.sleep(5)
        return judgement(messages, info)  # pragma: no cover - never waited for

    scripted(app, judgement=slow)
    monkeypatch.setattr(current_evaluation_ports(), "judge_timeout_s", 0.2)
    agent = await live_agent(app, owner)
    await sampling(owner, agent, 100)

    (events,) = await conversation(visitor, agent, "How much annual leave?")

    verdict = await live_verdict(owner, agent, events)
    assert verdict is not None
    assert (verdict["status"], verdict["error_reason"]) == ("error", TIMEOUT)
    assert (verdict["grounded"], verdict["answers_question"], verdict["passed"]) == (
        None,
        None,
        None,
    )


# Purged before it is judged


async def test_a_reply_purged_before_it_is_judged_is_skipped_and_never_sent_to_the_judge(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    held_back: list[uuid.UUID],
) -> None:
    calls: list[str] = []
    scripted(app, judgement=recording(calls))
    agent = await live_agent(app, owner)
    await sampling(owner, agent, 100)
    (events,) = await conversation(visitor, agent, "My name is Ada; how much leave?")
    pending = await live_verdict(owner, agent, events)
    assert pending is not None
    assert pending["status"] == "pending"
    (row,) = (await listed(owner, agent["project_id"]))["items"]
    deleted = await owner.client.delete(conversations_path(owner, agent["project_id"], row["id"]))
    assert deleted.status_code == 204, deleted.text

    (verdict_id,) = held_back
    await judge_now(verdict_id)

    verdict = await live_verdict(owner, agent, events)
    assert verdict is not None
    assert verdict["status"] == "skipped"
    assert (verdict["grounded"], verdict["answers_question"], verdict["passed"]) == (
        None,
        None,
        None,
    )
    assert (verdict["judge_model"], verdict["cost_usd"]) == (None, None)
    assert calls == []


async def test_a_reply_whose_remembered_turn_is_purged_before_it_is_judged_is_skipped(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    held_back: list[uuid.UUID],
) -> None:
    calls: list[str] = []
    scripted(app, judgement=recording(calls))
    agent = await live_agent(app, owner)
    assert (await set_window(owner, 7)).status_code == 200
    await sampling(owner, agent, 100)
    token = await conversation_token(visitor, agent["public_id"])
    # The Visitor keeps the Conversation going with a question every 23 hours for a week.
    replies = []
    for hour in range(0, 162, 23):
        clock.advance(timedelta(hours=23 if hour else 0))
        response = await send(visitor, agent["public_id"], token, f"Question at hour {hour}?")
        assert response.status_code == 200, response.text
        replies.append(parse_sse(response.text))
    # At hour 215 the turns up to hour 46 are older than the window and Purged; the last reply
    # (hour 161) isn't, but it remembered the five turns before it, from hour 46.
    clock.advance(timedelta(hours=215 - 161))
    await roll_up(clock.now())
    await purge(clock.now())

    await judge_now(held_back[-1])

    verdict = await live_verdict(owner, agent, replies[-1])
    assert verdict is not None
    assert verdict["status"] == "skipped"
    assert calls == []


# Retention


def iso(at: Any) -> str:
    return str(at.isoformat()).replace("+00:00", "Z")


def cleared(check: dict[str, Any]) -> dict[str, Any]:
    return {"outcome": check["outcome"], "reason": None, "review": None}


def kept(verdict: dict[str, Any]) -> dict[str, Any]:
    """What a Live Verdict keeps after the Purge: everything but its reasons and purged-at."""
    return {
        **verdict,
        "grounded": {"outcome": verdict["grounded"]["outcome"], "reason": None, "review": None},
        "answers_question": {
            "outcome": verdict["answers_question"]["outcome"],
            "reason": None,
            "review": None,
        },
        "purged_at": None,
    }


async def test_the_purge_clears_a_live_verdicts_reasons_and_keeps_its_outcomes_and_cost(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    grounded = {"passed": False, "reason": "Ada's claim about 30 days isn't cited."}
    answers = {"passed": True, "reason": "It answers Ada's question about leave."}
    scripted(app, judgement=judged(grounded, answers))
    agent = await live_agent(app, owner)
    assert (await set_window(owner, 7)).status_code == 200
    await sampling(owner, agent, 100)
    (old,) = await conversation(visitor, agent, "I am Ada; how much leave?")
    clock.advance(timedelta(days=1))
    (new,) = await conversation(visitor, agent, "How much annual leave?")
    before_old = await live_verdict(owner, agent, old)
    before_new = await live_verdict(owner, agent, new)
    assert before_old is not None
    assert before_old["purged_at"] is None
    # A week and an hour after the first reply, only it is older than the window.
    clock.advance(timedelta(days=6, hours=1))
    await roll_up(clock.now())

    await purge(clock.now())

    after = await live_verdict(owner, agent, old)
    assert after is not None
    assert after["grounded"] == {"outcome": "fail", "reason": None, "review": None}
    assert after["answers_question"] == {"outcome": "pass", "reason": None, "review": None}
    assert after["purged_at"] == iso(clock.now())
    # Its status, overall pass, judge, tokens, Cost and times stay.
    assert kept(after) == kept(before_old)
    assert await live_verdict(owner, agent, new) == before_new


async def test_deleting_a_conversation_clears_its_live_verdicts_reasons_at_once(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    scripted(app, judgement=judged(PASSED, PASSED))
    agent = await live_agent(app, owner)
    await sampling(owner, agent, 100)
    first, second = await conversation(visitor, agent, "I am Ada; leave?", "And sick days?")
    clock.advance(timedelta(minutes=1))
    (kept_events,) = await conversation(visitor, agent, "How much annual leave?")
    before = await live_verdict(owner, agent, first)
    assert before is not None
    rows = (await listed(owner, agent["project_id"]))["items"]
    deleted_row = rows[-1]
    clock.advance(timedelta(minutes=5))

    response = await owner.client.delete(
        conversations_path(owner, agent["project_id"], deleted_row["id"])
    )

    assert response.status_code == 204, response.text
    for events in (first, second):
        verdict = await live_verdict(owner, agent, events)
        assert verdict is not None
        assert verdict["grounded"] == {"outcome": "pass", "reason": None, "review": None}
        assert verdict["answers_question"] == {"outcome": "pass", "reason": None, "review": None}
        assert (verdict["passed"], verdict["purged_at"]) == (True, iso(clock.now()))
    after = await live_verdict(owner, agent, first)
    assert after is not None
    assert kept(after) == kept(before)
    untouched = await live_verdict(owner, agent, kept_events)
    assert untouched is not None
    assert untouched["grounded"] == {"outcome": "pass", "reason": "Fine.", "review": None}
    assert untouched["purged_at"] is None


async def test_a_reply_purged_while_it_is_being_judged_keeps_no_reasons(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent = await live_agent(app, owner)
    loop = asyncio.get_running_loop()
    judgement = judged(PASSED, {"passed": False, "reason": "Ada asked about sick days."})

    def deleting_midway(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        # The judging task runs on its own event loop; the Owner deletes the Conversation on the
        # API's while the judge is still at work.
        (row,) = asyncio.run_coroutine_threadsafe(
            listed(owner, agent["project_id"]), loop
        ).result()["items"]
        path = conversations_path(owner, agent["project_id"], row["id"])
        deleted = asyncio.run_coroutine_threadsafe(owner.client.delete(path), loop).result()
        assert deleted.status_code == 204, deleted.text
        return judgement(messages, info)

    scripted(app, judgement=deleting_midway)
    await sampling(owner, agent, 100)

    (events,) = await conversation(visitor, agent, "I am Ada; sick days?")

    verdict = await live_verdict(owner, agent, events)
    assert verdict is not None
    assert verdict["status"] == "judged"
    assert verdict["grounded"] == {"outcome": "pass", "reason": None, "review": None}
    assert verdict["answers_question"] == {"outcome": "fail", "reason": None, "review": None}
    assert (verdict["passed"], verdict["purged_at"]) == (False, iso(clock.now()))
    assert verdict["cost_usd"] is not None
