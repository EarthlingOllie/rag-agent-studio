"""API seam: a message the input Guardrail flags is always refused, and is never replayed.

There used to be warn and log modes, which answered a flagged message (warn with a caution in
the prompt). No setting may let a detected prompt injection into the model's context any more:
an old ``input_mode`` in a Draft or a published Version is ignored, and a flagged message is
refused as in ``test_input_guardrail.py``. A turn that was answered under an old mode, whose
answer carries an ``input / injection`` outcome, is never replayed to the model as history. The
classifier is the rule-driven fake (it flags messages containing "ignore your instructions");
the chat model is a naive ``FunctionModel`` that records each prompt it gets."""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi import FastAPI
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo
from sqlalchemy import select

from app.conversations.models import Message
from tests.agents import agents_path, answer_with, ask, parse_sse
from tests.conftest import SignedUpMember
from tests.integration.test_input_guardrail import (
    ATTACK,
    REASON,
    REFUSAL,
    agent_with_refusal,
    guard,
    trace_of,
    user_prompts,
)

ANSWER = "Leave is 25 days [C1]."


class Model:
    """A naive chat model that would do what it is told; it records every prompt it got."""

    def __init__(self) -> None:
        self.calls: list[list[ModelMessage]] = []

    async def __call__(self, messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
        self.calls.append(messages)
        yield ANSWER


@pytest.mark.parametrize("old_mode", ["warn", "log"])
async def test_an_old_warn_or_log_setting_is_ignored_and_a_flagged_message_is_refused(
    app: FastAPI, owner: SignedUpMember, old_mode: str
) -> None:
    model = Model()
    answer_with(app, model)
    guard(app)
    project_id, agent_id, conversation_id = await agent_with_refusal(
        app, owner, {"input_mode": old_mode, "refusal_text": REFUSAL}
    )

    response = await ask(owner, project_id, agent_id, conversation_id, ATTACK)

    events = parse_sse(response.text)
    assert [event for event, _ in events] == ["refusal", "done"]
    assert events[0][1] == {"text": REFUSAL}
    assert model.calls == []
    trace = await trace_of(
        owner, project_id, agent_id, conversation_id, events[-1][1]["message_id"]
    )
    assert trace["guardrail_outcomes"] == [
        {
            "layer": "input",
            "verdict": "injection",
            "action": "blocked",
            "score": 0.97,
            "reason": REASON,
        }
    ]
    # The setting is gone from the Agent's configuration.
    agent = await owner.client.get(agents_path(owner, project_id, agent_id))
    assert agent.status_code == 200, agent.text
    assert "input_mode" not in agent.json()["draft"]["guardrails"]


@pytest.mark.parametrize("old_action", ["flagged", "logged"])
async def test_a_turn_answered_under_an_old_mode_is_never_replayed(
    app: FastAPI, owner: SignedUpMember, old_action: str
) -> None:
    model = Model()
    answer_with(app, model)
    project_id, agent_id, conversation_id = await agent_with_refusal(app, owner)
    # A Conversation from before: the attack was answered, and its answer carries the verdict
    # the old warn or log mode recorded.
    answered = await ask(owner, project_id, agent_id, conversation_id, ATTACK)
    message_id = parse_sse(answered.text)[-1][1]["message_id"]
    async with app.state.sessionmaker() as session:
        answer = await session.scalar(select(Message).where(Message.id == message_id))
        assert answer is not None
        answer.guardrail_outcomes = [
            {
                "layer": "input",
                "verdict": "injection",
                "action": old_action,
                "score": 0.97,
                "reason": REASON,
            }
        ]
        await session.commit()

    await ask(owner, project_id, agent_id, conversation_id, "And for part-timers?")

    later: list[Any] = model.calls[-1]
    assert "And for part-timers?" in user_prompts(later)
    assert "Ignore your instructions" not in user_prompts(later)
