"""API seam and task seam: Searches in metrics and retention (spec 13, ADR-0015).

Visitors chat through the widget API with an Agentic Live Version answered by a scripted
``FunctionModel`` that makes as many Knowledge Searches as the question asks for
(``searches:N``); the ``usage_daily`` rollup and the daily purge Beat tasks are called directly
as tasks. Everything is read back through the Studio API: Version KPIs, Version comparison (and
its CSV), the Version list and Version Diff, the Conversations viewer and the Trace."""

import csv
import io
import json
import re
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic_ai.messages import ModelMessage, ModelRequest, ToolReturnPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, DeltaToolCalls

from tests.agents import answer_with, create_agent, save_draft, use_default_model
from tests.conftest import ClientFactory, SignedUpMember
from tests.documents import create_project, project_path, upload
from tests.fakes.clock import ControllableClock
from tests.integration.test_agent_versions import published
from tests.integration.test_agentic_retrieval import agentic
from tests.integration.test_conversations import (
    conversations_path,
    listed,
    opened,
    playground_chat,
    trace_of,
)
from tests.integration.test_playground import LEAVE
from tests.integration.test_retention import purge, set_window
from tests.integration.test_version_comparison import comparison_path
from tests.integration.test_version_metrics import chat, metrics, roll_up, version_kpis

_SEARCHES = re.compile(r"searches:(\d+)")


def _question(messages: list[ModelMessage]) -> str:
    """The Visitor's latest question: the last user prompt the model was given."""
    return [
        str(part.content)
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, UserPromptPart)
    ][-1]


def _searched(messages: list[ModelMessage]) -> int:
    return sum(
        isinstance(part, ToolReturnPart)
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
    )


async def searcher(
    messages: list[ModelMessage], info: AgentInfo
) -> AsyncIterator[str | DeltaToolCalls]:
    """Makes as many Knowledge Searches as the question asks for (``searches:N``; none
    otherwise), one per model call, each for ``leave query K``; then answers citing C1 (or
    without a citation when it made no Search)."""
    question = _question(messages)
    found = _SEARCHES.findall(question)
    wanted = int(found[-1]) if found else 0
    made = _searched(messages)
    # In Automatic mode the model has no tool: it answers from the Chunks it was given.
    if made < wanted and info.function_tools:
        (tool,) = info.function_tools
        args = json.dumps({"query": f"leave query {made + 1}"})
        yield {0: DeltaToolCall(name=tool.name, json_args=args, tool_call_id=f"call-{made}")}
        return
    yield "Leave is 25 days [C1]." if wanted else "Hello there."


@pytest.fixture
async def visitor(new_client: ClientFactory) -> httpx.AsyncClient:
    """A browser on someone's website: no Studio session."""
    return await new_client()


async def agentic_live_agent(app: FastAPI, owner: SignedUpMember) -> dict[str, Any]:
    """A Project holding the leave policy and an Agent whose Live Version (v1) is Agentic,
    answered by ``searcher``; with its ``project_id``."""
    answer_with(app, searcher)
    await use_default_model(owner)
    project_id = await create_project(owner)
    await upload(app, owner, project_id, "leave.txt", LEAVE.encode())
    agent: dict[str, Any] = await create_agent(owner, project_id)
    agent["project_id"] = project_id
    await agentic(owner, project_id, agent["id"])
    agent["v1"] = await published(owner, project_id, agent["id"])
    return agent


# Version KPIs


async def test_a_versions_kpis_show_its_searches_and_mean_searches_per_reply(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent = await agentic_live_agent(app, owner)
    # Four replies making 2, 1, 0 and 3 Searches: 6 Searches, 1.5 per reply.
    await chat(visitor, agent, "Leave? searches:2", "Sick days? searches:1", "Thanks!")
    await chat(visitor, agent, "Parental leave? searches:3")

    kpis = await version_kpis(owner, agent, agent["v1"], start="2026-11-05", end="2026-11-05")

    assert kpis["messages"] == 4
    assert kpis["retrieval_mode"] == "agentic"
    assert kpis["searches"] == {"total": 6, "mean_per_reply": 1.5}


async def test_the_rollup_records_the_search_count_per_version_per_day(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent = await agentic_live_agent(app, owner)
    await chat(visitor, agent, "Leave? searches:2")  # Nov 5
    clock.advance(timedelta(days=1))
    await roll_up(clock.now())  # Nov 5 is final
    await chat(visitor, agent, "Leave? searches:1", "Thanks!")  # Nov 6
    live_day = await version_kpis(owner, agent, agent["v1"], start="2026-11-06", end="2026-11-06")

    clock.advance(timedelta(days=1))
    await roll_up(clock.now())
    # Nov 7: both days are read from their final rollups.
    nov_5, nov_6 = [
        await version_kpis(owner, agent, agent["v1"], start=day, end=day)
        for day in ("2026-11-05", "2026-11-06")
    ]
    both = await version_kpis(owner, agent, agent["v1"], start="2026-11-05", end="2026-11-06")

    assert nov_6 == live_day
    assert nov_5["searches"] == {"total": 2, "mean_per_reply": 2.0}
    assert nov_6["searches"] == {"total": 1, "mean_per_reply": 0.5}
    assert both["searches"] == {"total": 3, "mean_per_reply": 1.0}


async def test_playground_searches_stay_out_of_the_visitor_kpis(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent = await agentic_live_agent(app, owner)
    await chat(visitor, agent, "Leave? searches:1")
    await playground_chat(owner, agent["project_id"], agent["id"], "Testing searches:3")
    clock.advance(timedelta(days=1))
    await roll_up(clock.now())
    await playground_chat(owner, agent["project_id"], agent["id"], "Today searches:2")

    kpis = await version_kpis(owner, agent, agent["v1"], start="2026-11-05", end="2026-11-06")

    assert (kpis["messages"], kpis["searches"]) == (1, {"total": 1, "mean_per_reply": 1.0})


async def test_a_version_without_replies_has_no_mean_and_an_automatic_one_searches_never(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent = await agentic_live_agent(app, owner)
    unused = await version_kpis(owner, agent, agent["v1"])
    automatic = await automatic_next(owner, agent)
    await chat(visitor, agent, "Leave? searches:2")

    kpis = await version_kpis(owner, agent, automatic)

    assert unused["searches"] == {"total": 0, "mean_per_reply": None}
    assert kpis["retrieval_mode"] == "automatic"
    assert kpis["searches"] == {"total": 0, "mean_per_reply": 0.0}


async def automatic_next(owner: SignedUpMember, agent: dict[str, Any]) -> dict[str, Any]:
    """Publishes the Draft switched back to Automatic as the next Version (now Live)."""
    saved = await save_draft(
        owner, agent["project_id"], agent["id"], {"retrieval": {"mode": "automatic"}}
    )
    assert saved.status_code == 200, saved.text
    return await published(owner, agent["project_id"], agent["id"])


# Version comparison


async def test_comparison_shows_mean_searches_per_reply_and_each_versions_retrieval_mode(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent = await agentic_live_agent(app, owner)
    await chat(visitor, agent, "Leave? searches:2", "Sick days? searches:1")
    v2 = await automatic_next(owner, agent)
    await chat(visitor, agent, "Leave? searches:2")
    sides = {"a": agent["v1"]["id"], "b": v2["id"], "start": "2026-11-05", "end": "2026-11-05"}

    response = await owner.client.get(comparison_path(owner, agent), params=sides)
    exported = await owner.client.get(comparison_path(owner, agent, csv=True), params=sides)

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["a"]["retrieval_mode"], body["b"]["retrieval_mode"]) == ("agentic", "automatic")
    (row,) = [row for row in body["metrics"] if row["metric"] == "searches_per_reply"]
    # More searching costs more but may answer better: it favours neither Version.
    assert row == {
        "metric": "searches_per_reply",
        "label": "Mean searches per reply",
        "unit": "searches",
        "a": 1.5,
        "b": 0.0,
        "difference": -1.5,
        "changed": True,
        "better": None,
        "low_confidence": True,
    }
    # The Version Diff from v1 to v2 shows the Retrieval Mode change.
    assert {
        "path": "retrieval.mode",
        "before": "agentic",
        "after": "automatic",
    }.items() <= body["config_diff"]["changes"][0].items()
    table = list(csv.reader(io.StringIO(exported.text)))
    assert ["Mean searches per reply", "1.50", "0.00", "-1.50", ""] in table


async def test_the_version_list_gives_each_versions_retrieval_mode(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock
) -> None:
    agent = await agentic_live_agent(app, owner)
    await automatic_next(owner, agent)

    response = await owner.client.get(
        f"{project_path(owner, agent['project_id'])}/agents/{agent['id']}/versions"
    )

    assert response.status_code == 200, response.text
    found = [(v["number"], v["config"]["retrieval"]["mode"]) for v in response.json()["versions"]]
    assert found == [(2, "automatic"), (1, "agentic")]


# Retention


async def search_queries(
    owner: SignedUpMember, project_id: str, conversation_id: str
) -> list[list[str]]:
    """Each reply's Search queries in the Conversation, from its Trace."""
    detail = await opened(owner, project_id, conversation_id)
    found = []
    for message in detail["messages"]:
        if message["role"] == "assistant":
            path = trace_of(owner, project_id, conversation_id, message["id"])
            trace = await owner.client.get(path)
            assert trace.status_code == 200, trace.text
            found.append([search["query"] for search in trace.json()["searches"]])
    return found


async def test_purging_message_text_also_purges_search_queries(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent = await agentic_live_agent(app, owner)
    project_id = agent["project_id"]
    assert (await set_window(owner, 7)).status_code == 200
    await chat(visitor, agent, "Leave? searches:2")  # Nov 5
    clock.advance(timedelta(minutes=1))
    await playground_chat(owner, project_id, agent["id"], "Testing searches:1")
    clock.advance(timedelta(days=1))
    await chat(visitor, agent, "Sick days? searches:1")  # Nov 6
    clock.advance(timedelta(days=6, hours=1))
    await roll_up(clock.now())
    before = await metrics(owner, agent, start="2026-11-01", end="2026-11-30")
    old, playground, new = [
        row["id"] for row in reversed((await listed(owner, project_id))["items"])
    ]
    assert await search_queries(owner, project_id, old) == [["leave query 1", "leave query 2"]]

    await purge(clock.now())

    # The queries of purged replies are cleared; how many Searches there were stays.
    assert await search_queries(owner, project_id, old) == [["", ""]]
    assert await search_queries(owner, project_id, playground) == [[""]]
    assert await search_queries(owner, project_id, new) == [["leave query 1"]]
    assert await metrics(owner, agent, start="2026-11-01", end="2026-11-30") == before


async def test_deleting_a_conversation_purges_its_search_queries(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent = await agentic_live_agent(app, owner)
    project_id = agent["project_id"]
    await chat(visitor, agent, "My name is Ada; leave? searches:1")
    (row,) = (await listed(owner, project_id))["items"]

    response = await owner.client.delete(conversations_path(owner, project_id, row["id"]))

    assert response.status_code == 204, response.text
    assert await search_queries(owner, project_id, row["id"]) == [[""]]
