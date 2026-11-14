"""API seam: two questions asked at once in one Playground Conversation are both answered (no
deadlock), and a stream that fails for a reason no one expected still ends with an ``error``
event, so the Studio is never left with a stream cut short and no word of why."""

import asyncio
import uuid
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo
from sqlalchemy import select, text

from app.conversations.models import Conversation
from tests.agents import answer_with, ask, parse_sse, start_conversation
from tests.conftest import SignedUpMember
from tests.integration.test_playground import ready_agent, three_tokens

INTERNAL = "Something went wrong while answering. Try again."


async def _waiting_on_locks(app: FastAPI, count: int) -> None:
    """Returns once ``count`` other backends of this database are waiting on a row lock."""
    async with app.state.sessionmaker() as session:
        while True:
            waiting = await session.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
                    "AND wait_event_type = 'Lock' AND pid <> pg_backend_pid()"
                )
            )
            await session.rollback()
            if waiting is not None and waiting >= count:
                return
            await asyncio.sleep(0.02)


async def test_two_questions_asked_at_once_in_one_conversation_are_both_answered(
    app: FastAPI, owner: SignedUpMember
) -> None:
    arrived: asyncio.Queue[None] = asyncio.Queue()
    gate = asyncio.Event()

    async def gated(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
        arrived.put_nowait(None)
        await gate.wait()
        async for token in three_tokens(messages, info):
            yield token

    answer_with(app, gated)
    member, project_id, agent_id = await ready_agent(app, owner)
    conversation = await start_conversation(member, project_id, agent_id)
    asks = [
        asyncio.create_task(
            ask(member, project_id, agent_id, conversation["id"], f"How much leave? ({n})")
        )
        for n in range(2)
    ]
    for _ in asks:
        await asyncio.wait_for(arrived.get(), 10)
    # Both questions are saved and both answers are being written. Another transaction holds
    # the Conversation in a lock that lets the answers' rows reference it but not lock it for
    # update, so each answer gets as far as it can before taking the Conversation's lock: with
    # the wrong lock order, each then holds what the other waits for.
    async with app.state.sessionmaker() as blocker:
        await blocker.execute(
            select(Conversation)
            .where(Conversation.id == uuid.UUID(conversation["id"]))
            .with_for_update(key_share=True)
        )
        gate.set()
        await asyncio.wait_for(_waiting_on_locks(app, 2), 10)
        await blocker.rollback()

    responses = await asyncio.wait_for(asyncio.gather(*asks), 20)

    for response in responses:
        assert response.status_code == 200, response.text
        assert parse_sse(response.text)[-1][0] == "done", response.text


async def test_an_unexpected_failure_ends_the_stream_with_an_internal_error_event(
    app: FastAPI, owner: SignedUpMember, caplog: pytest.LogCaptureFixture
) -> None:
    async def broken(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
        yield "Everyone gets "
        raise RuntimeError("the database went away")

    answer_with(app, broken)
    member, project_id, agent_id = await ready_agent(app, owner)
    conversation = await start_conversation(member, project_id, agent_id)

    response = await ask(member, project_id, agent_id, conversation["id"], "How much leave?")

    assert response.status_code == 200, response.text
    assert parse_sse(response.text)[-1] == ("error", {"code": "internal", "message": INTERNAL})
    assert "the database went away" in caplog.text
