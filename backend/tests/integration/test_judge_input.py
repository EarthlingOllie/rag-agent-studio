"""Task seam: what the Evaluation Model was given for a judged Run Verdict or Live Verdict is
rebuilt, from what was stored, exactly as it was judged (spec 18, ticket 18-01).

The judge records the request text it is given; ``judge_input`` then rebuilds each judged
target's request from its rows, and the rebuilt request's text must be the text the judge saw.
Without its text (an answer that errored, a reply Purged) there is nothing to rebuild.
"""

import uuid
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, UserPromptPart
from pydantic_ai.models.function import AgentInfo
from sqlalchemy import select

from app.evaluation.fake_judge import fake_judgement
from app.evaluation.judge import judge_message
from app.evaluation.judge_input import judge_input
from app.evaluation.models import (
    EvaluationCaseResult,
    EvaluationVerdict,
    LiveVerdict,
    VerdictKind,
)
from tests.conftest import ClientFactory, SignedUpMember
from tests.documents import upload
from tests.integration.test_conversations import conversations_path, listed
from tests.integration.test_evaluation import add_case, evaluated
from tests.integration.test_live_verdict_context import conversation
from tests.integration.test_live_verdicts import (
    PASSED,
    judged,
    live_agent,
    message_id,
    sampling,
    scripted,
)
from tests.integration.test_playground import ready_agent

SICK = "Sick days are paid in full for up to ten days a year."


@pytest.fixture
async def visitor(new_client: ClientFactory) -> httpx.AsyncClient:
    """A browser on someone's website: no Studio session."""
    return await new_client()


def prompt_of(messages: list[ModelMessage]) -> str:
    (prompt,) = [
        str(part.content)
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, UserPromptPart)
    ]
    return prompt


def recording(calls: list[str], judgement: Any = fake_judgement) -> Any:
    """A judge that records the request text it is given, then judges with ``judgement``."""

    def judge(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        calls.append(prompt_of(messages))
        response: ModelResponse = judgement(messages, info)
        return response

    return judge


async def test_a_run_verdict_is_rebuilt_as_the_run_judged_it(
    app: FastAPI, owner: SignedUpMember
) -> None:
    calls: list[str] = []
    scripted(app, judgement=recording(calls))
    _, project_id, agent_id = await ready_agent(app, owner)
    await add_case(owner, project_id, agent_id)

    results = await evaluated(owner, project_id, agent_id)

    run_id = uuid.UUID(results["run"]["id"])
    async with app.state.sessionmaker() as session:
        verdicts = list(
            await session.scalars(
                select(EvaluationVerdict)
                .join(EvaluationCaseResult, EvaluationCaseResult.id == EvaluationVerdict.result_id)
                .where(
                    EvaluationCaseResult.run_id == run_id,
                    EvaluationVerdict.kind == VerdictKind.GROUNDING,
                )
            )
        )
        rebuilt = [await judge_input(session, verdict) for verdict in verdicts]
    # Each of the 3 answers was judged once, and its grounding Verdict rebuilds that request.
    assert len(calls) == len(verdicts) == 3
    assert sorted(judge_message(r) for r in rebuilt if r is not None) == sorted(calls)
    (prompt, *_) = calls
    assert "<<<CITED_EXCERPTS>>>\n[C1] leave.txt\n" in prompt
    assert prompt.endswith("Judge: reference_answer, grounding")


async def test_an_answer_that_errored_has_nothing_to_rebuild(
    app: FastAPI, owner: SignedUpMember
) -> None:
    _, project_id, agent_id = await ready_agent(app, owner)
    await add_case(owner, project_id, agent_id, "Please simulate a rate limit.")

    results = await evaluated(owner, project_id, agent_id)

    run_id = uuid.UUID(results["run"]["id"])
    async with app.state.sessionmaker() as session:
        errored = list(
            await session.scalars(
                select(EvaluationCaseResult).where(EvaluationCaseResult.run_id == run_id)
            )
        )
        assert [await judge_input(session, result) for result in errored] == [None] * 3


async def stored_live_verdict(app: FastAPI, events: list[tuple[str, Any]]) -> LiveVerdict:
    async with app.state.sessionmaker() as session:
        found: LiveVerdict | None = await session.scalar(
            select(LiveVerdict).where(LiveVerdict.message_id == uuid.UUID(message_id(events)))
        )
        assert found is not None
        return found


async def rebuilt_live(app: FastAPI, verdict: LiveVerdict) -> str | None:
    async with app.state.sessionmaker() as session:
        request = await judge_input(session, verdict)
        return None if request is None else judge_message(request)


async def test_a_live_verdict_is_rebuilt_as_it_was_judged_until_its_reply_is_purged(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    calls: list[str] = []
    scripted(app, judgement=recording(calls, judged(PASSED, PASSED)))
    agent = await live_agent(app, owner)
    await upload(app, owner, agent["project_id"], "sick.txt", SICK.encode())
    await sampling(owner, agent, 100)

    replies = await conversation(
        visitor, agent, "How much annual leave?", "And sick days?", "What about part-timers?"
    )

    verdicts = [await stored_live_verdict(app, events) for events in replies]
    assert [await rebuilt_live(app, verdict) for verdict in verdicts] == calls
    follow_up = calls[-1]
    assert "<<<EARLIER_TURNS>>>\nQuestion: How much annual leave?\nAnswer: " in follow_up
    assert "<<<CITED_EXCERPTS>>>\n[C1] " in follow_up
    assert "<<<GIVEN_EXCERPTS>>>\n[C2] " in follow_up
    assert follow_up.endswith("Judge: grounding, answers_question")
    # Once the Conversation is deleted its text is Purged, and nothing is rebuilt without it.
    (row,) = (await listed(owner, agent["project_id"]))["items"]
    deleted = await owner.client.delete(conversations_path(owner, agent["project_id"], row["id"]))
    assert deleted.status_code == 204, deleted.text
    assert [await rebuilt_live(app, verdict) for verdict in verdicts] == [None] * 3
