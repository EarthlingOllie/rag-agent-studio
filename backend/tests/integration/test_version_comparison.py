"""API seam: Version comparison. Visitors chat with two Versions of an Agent through the widget
API (answers from a ``FunctionModel``) and give feedback; Editors compare the two Versions'
metrics side by side, each metric's difference and which side it favours, with the config diff
between them alongside, over a chosen range of UTC days, and export the comparison as CSV.

Assertions are on HTTP responses only. Expected numbers are worked out from what the Visitors
did (counts, votes, ratings) or read from the Version metrics endpoint, which 07-04 checks
against each reply's own values."""

import csv
import io
from datetime import timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from tests.agents import create_agent
from tests.conftest import ClientFactory, MemberFactory, SignedUpMember
from tests.documents import project_path
from tests.fakes.clock import ControllableClock
from tests.integration.test_agent_versions import published
from tests.integration.test_conversations import playground_chat
from tests.integration.test_guardrail_analytics import BENIGN, ask_all, guarded_agent
from tests.integration.test_input_guardrail import ATTACK
from tests.integration.test_version_metrics import (
    chat,
    live_agent,
    publish_next,
    rate,
    roll_up,
    thumb,
    version_kpis,
)

DAY = {"start": "2026-11-05", "end": "2026-11-05"}


@pytest.fixture
async def visitor(new_client: ClientFactory) -> httpx.AsyncClient:
    """A browser on someone's website: no Studio session."""
    return await new_client()


def comparison_path(member: SignedUpMember, agent: dict[str, Any], csv: bool = False) -> str:
    suffix = ".csv" if csv else ""
    return f"{project_path(member, agent['project_id'])}/agents/{agent['id']}/comparison{suffix}"


async def get_comparison(
    member: SignedUpMember, agent: dict[str, Any], csv: bool = False, **params: Any
) -> httpx.Response:
    return await member.client.get(comparison_path(member, agent, csv), params=params)


async def comparison(
    member: SignedUpMember,
    agent: dict[str, Any],
    a: dict[str, Any],
    b: dict[str, Any],
    **params: Any,
) -> dict[str, Any]:
    response = await get_comparison(member, agent, a=a["id"], b=b["id"], **params)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def rows(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["metric"]: row for row in body["metrics"]}


async def two_versions(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """An Agent whose v1 had two Conversations (two thumbs up, a 5 and a 3) and whose v2, with a
    new system prompt, had one (a thumbs down, a 1); v2 is Live."""
    agent = await live_agent(app, owner)
    first, (a1, a2) = await chat(visitor, agent, "Leave? words:10", "Sick? words:30")
    await thumb(visitor, agent, first, a1, "up")
    await thumb(visitor, agent, first, a2, "up")
    await rate(visitor, agent, first, 5)
    second, _ = await chat(visitor, agent, "Pay? words:20")
    await rate(visitor, agent, second, 3)
    v2 = await publish_next(owner, agent, "Answer in one sentence.")
    third, (c1,) = await chat(visitor, agent, "Holidays? words:4")
    await thumb(visitor, agent, third, c1, "down")
    await rate(visitor, agent, third, 1)
    return agent, agent["v1"], v2


async def test_two_versions_are_compared_side_by_side_with_each_difference(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    agent, v1, v2 = await two_versions(app, owner, visitor)
    # The Playground never counts.
    await playground_chat(owner, agent["project_id"], agent["id"], "Testing words:500")

    body = await comparison(owner, agent, v1, v2, **DAY)

    v1_kpis = await version_kpis(owner, agent, v1, **DAY)
    v2_kpis = await version_kpis(owner, agent, v2, **DAY)
    assert body["agent_id"] == agent["id"]
    assert (body["start"], body["end"]) == ("2026-11-05", "2026-11-05")
    # The two Versions' KPIs, exactly as the Version metrics endpoint gives them.
    assert (body["a"], body["b"]) == (v1_kpis, v2_kpis)
    found = rows(body)
    assert list(found) == [
        "conversations",
        "messages",
        "tokens_mean",
        "tokens_p95",
        "cost_per_conversation_usd",
        "cost_total_usd",
        "thumbs_up_rate",
        "thumbs_up_low",
        "thumbs_up_high",
        "votes",
        "rating_mean",
        "ratings",
        "fallback_rate",
        "guardrail_block_rate",
        "first_token_p95_ms",
        "total_p95_ms",
    ]
    assert found["conversations"] == {
        "metric": "conversations",
        "label": "Conversations",
        "unit": "count",
        "a": 2,
        "b": 1,
        "difference": -1,
        "changed": True,
        # More or fewer Conversations is neither better nor worse.
        "better": None,
        "low_confidence": True,
    }
    assert (found["messages"]["a"], found["messages"]["b"]) == (3, 1)
    # Thumbs: 2 of 2 up for v1, 0 of 1 for v2; a higher rate is better.
    assert found["thumbs_up_rate"] | {"low_confidence": None} == {
        "metric": "thumbs_up_rate",
        "label": "Thumbs-up rate",
        "unit": "rate",
        "a": 1.0,
        "b": 0.0,
        "difference": -1.0,
        "changed": True,
        "better": "a",
        "low_confidence": None,
    }
    assert found["thumbs_up_rate"]["low_confidence"] is True
    assert found["thumbs_up_low"]["a"] == v1_kpis["thumbs_up"]["low"]
    assert found["thumbs_up_high"]["b"] == v2_kpis["thumbs_up"]["high"]
    assert (found["votes"]["a"], found["votes"]["b"]) == (2, 1)
    # Ratings: mean 4 for v1, 1 for v2.
    assert (found["rating_mean"]["a"], found["rating_mean"]["b"]) == (4.0, 1.0)
    assert (found["rating_mean"]["difference"], found["rating_mean"]["better"]) == (-3.0, "a")
    assert (found["ratings"]["a"], found["ratings"]["b"]) == (2, 1)
    # Tokens per reply: v1's replies were longer (10 and 30 words against 4); fewer is better.
    assert found["tokens_mean"]["a"] == v1_kpis["tokens"]["mean"]
    assert found["tokens_mean"]["b"] == v2_kpis["tokens"]["mean"]
    assert found["tokens_mean"]["b"] < found["tokens_mean"]["a"]
    assert found["tokens_mean"]["better"] == "b"
    assert found["tokens_mean"]["difference"] == pytest.approx(
        v2_kpis["tokens"]["mean"] - v1_kpis["tokens"]["mean"]
    )
    assert found["tokens_p95"]["better"] == "b"
    # Cost, from the frozen costs; a cheaper Conversation is better, the total is neither.
    assert found["cost_per_conversation_usd"]["a"] == float(v1_kpis["cost"]["per_conversation_usd"])
    assert found["cost_total_usd"]["b"] == float(v2_kpis["cost"]["total_usd"])
    assert found["cost_total_usd"]["better"] is None
    assert found["cost_per_conversation_usd"]["better"] in ("a", "b")
    # Neither Version fell back.
    assert found["fallback_rate"] | {"low_confidence": False} == {
        "metric": "fallback_rate",
        "label": "Fallback rate",
        "unit": "rate",
        "a": 0.0,
        "b": 0.0,
        "difference": 0.0,
        "changed": False,
        "better": None,
        "low_confidence": False,
    }
    # The input Guardrail blocked no question; a lower block rate is better.
    assert found["guardrail_block_rate"] | {"low_confidence": False} == {
        "metric": "guardrail_block_rate",
        "label": "Guardrail block rate",
        "unit": "rate",
        "a": 0.0,
        "b": 0.0,
        "difference": 0.0,
        "changed": False,
        "better": None,
        "low_confidence": False,
    }
    assert found["total_p95_ms"]["a"] == v1_kpis["latency"]["total_p95_ms"]
    assert found["first_token_p95_ms"]["b"] == v2_kpis["latency"]["first_token_p95_ms"]
    assert found["total_p95_ms"]["unit"] == "ms"


async def test_the_version_whose_input_guardrail_blocked_a_smaller_share_is_favoured(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    agent = await guarded_agent(app, owner)
    # v1 refused 2 of 3 questions; v2 refused 1 of 4.
    await ask_all(visitor, clock, agent, ATTACK, ATTACK, BENIGN)
    v2 = await publish_next(owner, agent, "Be brief.")
    await ask_all(visitor, clock, agent, BENIGN, BENIGN, BENIGN, ATTACK)

    found = rows(await comparison(owner, agent, agent["v1"], v2, **DAY))

    row = found["guardrail_block_rate"]
    assert (row["a"], row["b"]) == (pytest.approx(2 / 3), 0.25)
    assert row["difference"] == pytest.approx(0.25 - 2 / 3)
    assert (row["changed"], row["better"]) == (True, "b")


async def test_the_config_diff_between_the_two_versions_comes_alongside(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    agent, v1, v2 = await two_versions(app, owner, visitor)

    forwards = await comparison(owner, agent, v1, v2, **DAY)
    backwards = await comparison(owner, agent, v2, v1, **DAY)

    diff = forwards["config_diff"]
    assert diff["from"] == {"kind": "version", "version": {"id": v1["id"], "number": 1}}
    assert diff["to"] == {"kind": "version", "version": {"id": v2["id"], "number": 2}}
    (change,) = diff["changes"]
    assert change["path"] == "behaviour.system_prompt"
    assert change["after"] == "Answer in one sentence."
    assert {"op": "insert", "text": "Answer in one sentence."} in change["lines"]
    # The diff is the Agent diff's, from a to b.
    agent_diff = await owner.client.get(
        f"{project_path(owner, agent['project_id'])}/agents/{agent['id']}/diff",
        params={"from": v1["id"], "to": v2["id"]},
    )
    assert diff == agent_diff.json()
    # Swapping the sides swaps the diff and every difference.
    assert backwards["config_diff"]["changes"][0]["before"] == "Answer in one sentence."
    assert rows(backwards)["conversations"]["difference"] == 1
    assert rows(backwards)["thumbs_up_rate"]["better"] == "b"


async def test_versions_with_the_same_settings_have_an_empty_config_diff(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    agent = await live_agent(app, owner)
    # Publishing again with no changes makes a new Version with the same settings.
    v2 = await published(owner, agent["project_id"], agent["id"])

    body = await comparison(owner, agent, agent["v1"], v2, **DAY)

    assert body["config_diff"]["changes"] == []
    assert body["config_diff"]["instructions"] is None
    # No use at all: nothing to compare, nothing changed.
    found = rows(body)
    assert found["thumbs_up_rate"] | {"label": None, "unit": None} == {
        "metric": "thumbs_up_rate",
        "label": None,
        "unit": None,
        "a": None,
        "b": None,
        "difference": None,
        "changed": False,
        "better": None,
        "low_confidence": True,
    }
    assert (found["votes"]["a"], found["votes"]["changed"]) == (0, False)


async def test_a_side_with_no_value_has_no_difference_but_counts_as_changed(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    agent = await live_agent(app, owner)
    token, (r1,) = await chat(visitor, agent, "Leave words:5")
    await thumb(visitor, agent, token, r1, "up")
    v2 = await publish_next(owner, agent, "Two.")

    found = rows(await comparison(owner, agent, agent["v1"], v2, **DAY))

    assert found["thumbs_up_rate"] | {"low_confidence": None} == {
        "metric": "thumbs_up_rate",
        "label": "Thumbs-up rate",
        "unit": "rate",
        "a": 1.0,
        "b": None,
        "difference": None,
        "changed": True,
        "better": None,
        "low_confidence": None,
    }


async def test_the_date_range_chooses_the_days_compared(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    agent = await live_agent(app, owner)
    await chat(visitor, agent, "Thursday words:5")  # 2026-11-05, v1
    v2 = await publish_next(owner, agent, "Two.")
    await chat(visitor, agent, "Thursday again words:5")  # 2026-11-05, v2
    clock.advance(timedelta(days=1))
    await chat(visitor, agent, "Friday words:5", "More words:5")  # 2026-11-06, v2
    clock.advance(timedelta(days=1))
    await roll_up(clock.now())
    await chat(visitor, agent, "Saturday words:5")  # 2026-11-07, v2, the live day

    thursday = rows(await comparison(owner, agent, agent["v1"], v2, **DAY))
    friday = rows(
        await comparison(owner, agent, agent["v1"], v2, start="2026-11-06", end="2026-11-06")
    )
    every_day = await comparison(owner, agent, agent["v1"], v2, start="2026-11-05")
    by_default = await comparison(owner, agent, agent["v1"], v2)

    assert (thursday["messages"]["a"], thursday["messages"]["b"]) == (1, 1)
    assert (friday["messages"]["a"], friday["messages"]["b"]) == (0, 2)
    assert (every_day["start"], every_day["end"]) == ("2026-11-05", "2026-11-07")
    assert (rows(every_day)["messages"]["a"], rows(every_day)["messages"]["b"]) == (1, 4)
    # The last 30 days to today by default, as the Version metrics.
    assert (by_default["start"], by_default["end"]) == ("2026-10-09", "2026-11-07")
    assert rows(by_default) == rows(every_day)


# CSV export


def parsed(response: httpx.Response) -> list[list[str]]:
    return list(csv.reader(io.StringIO(response.text)))


async def test_the_comparison_is_exported_as_csv(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    agent, v1, v2 = await two_versions(app, owner, visitor)
    body = await comparison(owner, agent, v1, v2, **DAY)

    response = await get_comparison(owner, agent, csv=True, a=v1["id"], b=v2["id"], **DAY)

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert response.headers["content-disposition"] == (
        'attachment; filename="comparison-v1-v2-2026-11-05-to-2026-11-05.csv"'
    )
    table = parsed(response)
    assert table[0] == ["Metric", "v1", "v2", "Difference (v2 - v1)", "Better"]
    by_label = {row[0]: row for row in table[1:]}
    assert [row[0] for row in table[1:]] == [row["label"] for row in body["metrics"]]
    assert by_label["Conversations"] == ["Conversations", "2", "1", "-1", ""]
    assert by_label["Replies"] == ["Replies", "3", "1", "-2", ""]
    assert by_label["Thumbs-up rate"] == ["Thumbs-up rate", "1.0000", "0.0000", "-1.0000", "v1"]
    assert by_label["Mean rating"] == ["Mean rating", "4.00", "1.00", "-3.00", "v1"]
    assert by_label["Fallback rate"] == ["Fallback rate", "0.0000", "0.0000", "0.0000", ""]
    # Dollars to the nano-dollar, as the API gives them.
    cost = by_label["Cost per Conversation (USD)"]
    assert cost[1] == body["a"]["cost"]["per_conversation_usd"]
    assert cost[2] == body["b"]["cost"]["per_conversation_usd"]
    tokens = by_label["Mean tokens per reply"]
    assert tokens[1] == f"{body['a']['tokens']['mean']:.1f}"
    assert tokens[4] == "v2"


async def test_missing_values_are_left_empty_in_the_csv(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    agent = await live_agent(app, owner)
    await chat(visitor, agent, "Leave words:5")
    v2 = await publish_next(owner, agent, "Two.")

    response = await get_comparison(owner, agent, csv=True, a=v2["id"], b=agent["v1"]["id"], **DAY)

    table = parsed(response)
    assert table[0] == ["Metric", "v2", "v1", "Difference (v1 - v2)", "Better"]
    by_label = {row[0]: row for row in table[1:]}
    assert by_label["Mean rating"] == ["Mean rating", "", "", "", ""]
    assert by_label["Cost per Conversation (USD)"][1] == ""
    tokens = by_label["Mean tokens per reply"]
    assert tokens[1] == ""
    assert tokens[2] != ""
    assert tokens[3:] == ["", ""]


# Refusals


@pytest.mark.parametrize("csv", [False, True])
async def test_the_same_version_twice_or_a_missing_side_is_refused(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock, csv: bool
) -> None:
    agent = await live_agent(app, owner)
    v1 = agent["v1"]["id"]

    same = await get_comparison(owner, agent, csv, a=v1, b=v1)
    missing = await get_comparison(owner, agent, csv, a=v1)
    backwards = await get_comparison(
        owner, agent, csv, a=v1, b=v1, start="2026-11-06", end="2026-11-05"
    )
    too_long = await get_comparison(owner, agent, csv, a=v1, b=v1, start="2025-01-01")

    assert same.status_code == 422
    assert same.json() == {"detail": "Pick two different Versions to compare."}
    assert missing.status_code == 422
    assert backwards.status_code == 422
    assert too_long.status_code == 422


@pytest.mark.parametrize("csv", [False, True])
async def test_another_agents_version_or_an_unknown_agent_is_not_found(
    app: FastAPI, owner: SignedUpMember, tenant_factory: Any, clock: ControllableClock, csv: bool
) -> None:
    agent = await live_agent(app, owner)
    other = await create_agent(owner, agent["project_id"], "Other")
    other_version = await published(owner, agent["project_id"], other["id"])
    v1 = agent["v1"]["id"]

    wrong_version = await get_comparison(owner, agent, csv, a=v1, b=other_version["id"])
    unknown_agent = await get_comparison(
        owner, agent | {"id": other_version["id"]}, csv, a=v1, b=other_version["id"]
    )

    assert wrong_version.status_code == 404, wrong_version.text
    assert wrong_version.json() == {"detail": "Not found"}
    assert unknown_agent.status_code == 404, unknown_agent.text


async def test_editors_compare_versions(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    member_factory: MemberFactory,
    clock: ControllableClock,
) -> None:
    agent, v1, v2 = await two_versions(app, owner, visitor)
    editor = await member_factory(owner, "editor")

    shown = await get_comparison(editor, agent, a=v1["id"], b=v2["id"])
    exported = await get_comparison(editor, agent, csv=True, a=v1["id"], b=v2["id"])

    assert shown.status_code == 200, shown.text
    assert exported.status_code == 200, exported.text
