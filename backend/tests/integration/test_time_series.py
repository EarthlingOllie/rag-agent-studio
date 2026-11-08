"""API seam and task seam: the time series. Visitors chat through the widget API (answers from a
``FunctionModel``) and give feedback; Editors publish and revert; the ``usage_daily`` rollup
Beat task is called directly as a task; Editors read one metric of an Agent over a range of UTC
days, by day, week or month, with markers where the Live Version changed (from the Live
History) and the Documents that changed in the Project during the range (the confounder note).

Assertions are on HTTP responses only. Expected values come from the Live History endpoint, the
Documents list and the Version metrics endpoint, never from rollup or audit tables."""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from tests.conftest import ClientFactory, SignedUpMember, TenantFactory
from tests.documents import create_project, documents, project_path, replace, upload
from tests.fakes.clock import ControllableClock
from tests.integration.test_agent_revert import reverted
from tests.integration.test_agent_versions import live_history
from tests.integration.test_conversations import playground_chat
from tests.integration.test_playground import LEAVE
from tests.integration.test_version_metrics import (
    chat,
    live_agent,
    metrics,
    publish_next,
    rate,
    roll_up,
    thumb,
)


@pytest.fixture
async def visitor(new_client: ClientFactory) -> httpx.AsyncClient:
    """A browser on someone's website: no Studio session."""
    return await new_client()


METRICS = [
    "conversations",
    "replies",
    "cost_usd",
    "mean_tokens",
    "thumbs_up_rate",
    "mean_rating",
    "fallback_rate",
    "p95_latency_ms",
]


def series_path(member: SignedUpMember, agent: dict[str, Any]) -> str:
    return f"{project_path(member, agent['project_id'])}/agents/{agent['id']}/time-series"


async def get_series(
    member: SignedUpMember, agent: dict[str, Any], **params: Any
) -> httpx.Response:
    return await member.client.get(series_path(member, agent), params=params)


async def series(member: SignedUpMember, agent: dict[str, Any], **params: Any) -> dict[str, Any]:
    response = await get_series(member, agent, **params)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def points(body: dict[str, Any]) -> list[tuple[str, str, Any, int]]:
    return [(p["start"], p["end"], p["value"], p["n"]) for p in body["points"]]


def markers_of(body: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "occurred_at": datetime.fromisoformat(m["occurred_at"]),
            "action": m["action"],
            "from": None if m["from_version"] is None else m["from_version"]["number"],
            "to": m["to_version"]["number"],
        }
        for m in body["markers"]
    ]


async def history(owner: SignedUpMember, agent: dict[str, Any]) -> list[dict[str, Any]]:
    """The Agent's Live History, oldest first, as the markers should show it."""
    entries = await live_history(owner, agent["project_id"], agent["id"])
    found = [
        {
            "occurred_at": datetime.fromisoformat(e["occurred_at"]),
            "action": e["action"],
            "from": None if e["from_version"] is None else e["from_version"]["number"],
            "to": e["to_version"]["number"],
        }
        for e in entries
    ]
    return sorted(found, key=lambda e: e["occurred_at"])


async def three_days(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> dict[str, Any]:
    """v1 published on 5 November with one thumbs up; v2 published on the 6th with two thumbs
    down; on the 7th (today, with no rollup since midnight) a revert to v1 and one thumbs up.
    The 5th and 6th are rolled up and final."""
    agent = await live_agent(app, owner)
    token, (a1,) = await chat(visitor, agent, "Leave?")
    await thumb(visitor, agent, token, a1, "up")
    # Playground use never counts.
    await playground_chat(owner, agent["project_id"], agent["id"], "Testing")
    clock.advance(timedelta(days=1))
    await publish_next(owner, agent, "Be brief.")
    token, (b1, b2) = await chat(visitor, agent, "Leave?", "Sick days?")
    await thumb(visitor, agent, token, b1, "down")
    await thumb(visitor, agent, token, b2, "down")
    clock.advance(timedelta(days=1))
    await roll_up(clock.now())
    await reverted(owner, agent["project_id"], agent["id"])
    token, (c1,) = await chat(visitor, agent, "Holidays?")
    await thumb(visitor, agent, token, c1, "up")
    return agent


# The series and its markers


async def test_a_metric_by_day_includes_today_and_is_marked_where_the_live_version_changed(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent = await three_days(app, owner, visitor, clock)

    body = await series(owner, agent, metric="thumbs_up_rate", start="2026-11-04", end="2026-11-07")

    assert body["agent_id"] == agent["id"]
    assert (body["metric"], body["granularity"]) == ("thumbs_up_rate", "day")
    assert (body["start"], body["end"]) == ("2026-11-04", "2026-11-07")
    assert points(body) == [
        ("2026-11-04", "2026-11-04", None, 0),
        ("2026-11-05", "2026-11-05", 1.0, 1),
        ("2026-11-06", "2026-11-06", 0.0, 2),
        # Today, the live partial day, from the raw tables.
        ("2026-11-07", "2026-11-07", 1.0, 1),
    ]
    # The markers are the Live History: publish v1, publish v2, revert to v1.
    expected = await history(owner, agent)
    assert [(e["action"], e["from"], e["to"]) for e in expected] == [
        ("publish", None, 1),
        ("publish", 1, 2),
        ("revert", 2, 1),
    ]
    assert markers_of(body) == expected
    assert [m["day"] for m in body["markers"]] == ["2026-11-05", "2026-11-06", "2026-11-07"]
    assert [m["point_start"] for m in body["markers"]] == [m["day"] for m in body["markers"]]
    # By week, each marker sits on the point of the week it happened in (clipped to the range).
    weekly = await series(
        owner,
        agent,
        metric="thumbs_up_rate",
        granularity="week",
        start="2026-11-04",
        end="2026-11-07",
    )
    assert points(weekly) == [("2026-11-04", "2026-11-07", 0.5, 4)]
    assert [m["point_start"] for m in weekly["markers"]] == ["2026-11-04"] * 3


async def test_only_live_version_changes_inside_the_range_are_marked(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent = await three_days(app, owner, visitor, clock)

    body = await series(owner, agent, metric="replies", start="2026-11-06", end="2026-11-06")

    assert points(body) == [("2026-11-06", "2026-11-06", 2, 2)]
    (only,) = markers_of(body)
    assert only == (await history(owner, agent))[1]
    none = await series(owner, agent, metric="replies", start="2026-10-01", end="2026-11-04")
    assert none["markers"] == []


async def test_every_metric_matches_the_version_kpis_of_the_same_day(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent = await live_agent(app, owner)
    first, (a1, a2) = await chat(visitor, agent, "Leave? words:12", "And sick days? words:40")
    await thumb(visitor, agent, first, a1, "up")
    await thumb(visitor, agent, first, a2, "down")
    await rate(visitor, agent, first, 4)
    second, (b1,) = await chat(visitor, agent, "Parental leave? words:3")
    await thumb(visitor, agent, second, b1, "up")
    await rate(visitor, agent, second, 1)
    day = {"start": "2026-11-05", "end": "2026-11-05"}
    (kpis,) = (await metrics(owner, agent, **day))["versions"]
    expected = {
        "conversations": (kpis["conversations"], kpis["conversations"]),
        "replies": (kpis["messages"], kpis["messages"]),
        "cost_usd": (pytest.approx(float(kpis["cost"]["total_usd"])), kpis["conversations"]),
        "mean_tokens": (pytest.approx(kpis["tokens"]["mean"]), kpis["tokens"]["n"]),
        "thumbs_up_rate": (pytest.approx(kpis["thumbs_up"]["rate"]), kpis["thumbs_up"]["n"]),
        "mean_rating": (pytest.approx(kpis["rating"]["mean"]), kpis["rating"]["n"]),
        "fallback_rate": (pytest.approx(kpis["fallback"]["rate"]), kpis["messages"]),
        "p95_latency_ms": (pytest.approx(kpis["latency"]["total_p95_ms"]), kpis["latency"]["n"]),
    }
    assert (kpis["conversations"], kpis["messages"], kpis["rating"]["n"]) == (2, 3, 2)
    assert float(kpis["cost"]["total_usd"]) > 0

    found = {}
    for metric in METRICS:
        ((value, n),) = [
            (p["value"], p["n"])
            for p in (await series(owner, agent, metric=metric, **day))["points"]
        ]
        found[metric] = (value, n)

    assert found == expected
    # The same numbers once the day is rolled up and final.
    clock.advance(timedelta(days=1))
    await roll_up(clock.now())
    for metric in METRICS:
        ((value, n),) = [
            (p["value"], p["n"])
            for p in (await series(owner, agent, metric=metric, **day))["points"]
        ]
        assert (value, n) == expected[metric], metric


async def test_a_series_covers_every_version_of_the_agent(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent = await live_agent(app, owner)
    await chat(visitor, agent, "Leave?")
    await publish_next(owner, agent, "Be brief.")
    await chat(visitor, agent, "Leave?", "Sick days?")

    body = await series(owner, agent, metric="replies", start="2026-11-05", end="2026-11-05")

    assert points(body) == [("2026-11-05", "2026-11-05", 3, 3)]


# Granularity and range


async def chat_on(
    visitor: httpx.AsyncClient, agent: dict[str, Any], clock: ControllableClock, day: date
) -> None:
    clock.advance(datetime(day.year, day.month, day.day, 9, tzinfo=UTC) - clock.now())
    await chat(visitor, agent, "Leave?")


async def test_weeks_and_months_add_up_their_days_clipped_to_the_range(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent = await live_agent(app, owner)
    # Thursday 5, Sunday 8, Monday 9 and Monday 16 November.
    for day in (date(2026, 11, 5), date(2026, 11, 8), date(2026, 11, 9), date(2026, 11, 16)):
        await chat_on(visitor, agent, clock, day)
    clock.advance(timedelta(days=1))
    await roll_up(clock.now())

    weeks = await series(
        owner,
        agent,
        metric="conversations",
        granularity="week",
        start="2026-11-05",
        end="2026-11-17",
    )
    months = await series(
        owner,
        agent,
        metric="conversations",
        granularity="month",
        start="2026-10-20",
        end="2026-12-03",
    )

    assert weeks["granularity"] == "week"
    # ISO weeks, Monday to Sunday; the first and last are clipped to the range.
    assert points(weeks) == [
        ("2026-11-05", "2026-11-08", 2, 2),
        ("2026-11-09", "2026-11-15", 1, 1),
        ("2026-11-16", "2026-11-17", 1, 1),
    ]
    assert points(months) == [
        ("2026-10-20", "2026-10-31", 0, 0),
        ("2026-11-01", "2026-11-30", 4, 4),
        ("2026-12-01", "2026-12-03", 0, 0),
    ]
    rates = await series(
        owner,
        agent,
        metric="thumbs_up_rate",
        granularity="month",
        start="2026-11-01",
        end="2026-11-30",
    )
    # No votes: no rate, rather than zero.
    assert points(rates) == [("2026-11-01", "2026-11-30", None, 0)]


async def test_by_default_the_last_30_days_by_day_are_shown(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock
) -> None:
    agent = await live_agent(app, owner)

    body = await series(owner, agent, metric="conversations")

    assert (body["start"], body["end"], body["granularity"]) == ("2026-10-07", "2026-11-05", "day")
    assert len(body["points"]) == 30
    assert body["points"][0]["start"] == "2026-10-07"
    assert body["points"][-1]["end"] == "2026-11-05"


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"metric": "happiness"},
        {"metric": "conversations", "granularity": "hour"},
        {"metric": "conversations", "start": "2026-11-06", "end": "2026-11-05"},
        {"metric": "conversations", "start": "2025-11-04", "end": "2026-11-05"},
        {"metric": "conversations", "start": "not a day"},
    ],
)
async def test_bad_queries_are_refused(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock, params: dict[str, str]
) -> None:
    agent = await live_agent(app, owner)

    response = await get_series(owner, agent, **params)

    assert response.status_code == 422, response.text


async def test_an_unknown_agent_or_another_organisations_is_not_found(
    app: FastAPI, owner: SignedUpMember, tenant_factory: TenantFactory, clock: ControllableClock
) -> None:
    agent = await live_agent(app, owner)
    unknown = agent | {"id": "00000000-0000-4000-8000-000000000000"}
    stranger = await tenant_factory()
    stranger_project = await create_project(stranger)

    missing = await get_series(owner, unknown, metric="conversations")
    elsewhere = await stranger.client.get(
        f"{project_path(stranger, stranger_project)}/agents/{agent['id']}/time-series",
        params={"metric": "conversations"},
    )

    assert missing.status_code == 404, missing.text
    assert elsewhere.status_code == 404, elsewhere.text


# The confounder: Documents that changed during the range


def day_of(timestamp: str) -> date:
    return datetime.fromisoformat(timestamp).astimezone(UTC).date()


def changes(body: dict[str, Any]) -> dict[str, int]:
    return dict(body["document_changes"])


async def test_documents_added_or_replaced_during_the_range_are_reported(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock
) -> None:
    agent = await live_agent(app, owner)
    (leave,) = await documents(owner, agent["project_id"])
    added = day_of(leave["created_at"])
    # A Document in another Project doesn't count.
    await upload(app, owner, await create_project(owner, "Other"), "other.txt", b"Other words.")

    during = await series(owner, agent, metric="conversations", start=str(added), end=str(added))
    before = await series(
        owner,
        agent,
        metric="conversations",
        start=str(added - timedelta(days=10)),
        end=str(added - timedelta(days=1)),
    )
    replaced = await replace(
        app, owner, agent["project_id"], leave["id"], "leave.txt", LEAVE.encode() + b" More."
    )
    assert replaced.status_code == 202, replaced.text
    (changed,) = await documents(owner, agent["project_id"])
    later = day_of(changed["updated_at"])
    after_replacing = await series(
        owner, agent, metric="conversations", start=str(added), end=str(later)
    )

    assert changes(during) == {"changed": 1, "deleted": 0}
    assert changes(before) == {"changed": 0, "deleted": 0}
    # Added and then replaced: one Document changed, counted once.
    assert changed["edition"] == 2
    assert changes(after_replacing) == {"changed": 1, "deleted": 0}


async def test_documents_deleted_during_the_range_are_reported(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock
) -> None:
    agent = await live_agent(app, owner)
    (leave,) = await documents(owner, agent["project_id"])
    other_project = await create_project(owner, "Other")
    other = await upload(app, owner, other_project, "other.txt", b"Other words.")
    clock.advance(timedelta(days=2))  # 7 November

    deleted = await owner.client.delete(
        f"{project_path(owner, agent['project_id'])}/documents/{leave['id']}"
    )
    assert deleted.status_code == 204, deleted.text
    # A deletion in another Project doesn't count.
    elsewhere = await owner.client.delete(
        f"{project_path(owner, other_project)}/documents/{other['id']}"
    )
    assert elsewhere.status_code == 204, elsewhere.text

    on_the_day = await series(
        owner, agent, metric="conversations", start="2026-11-07", end="2026-11-07"
    )
    days_before = await series(
        owner, agent, metric="conversations", start="2026-11-05", end="2026-11-06"
    )

    assert changes(on_the_day)["deleted"] == 1
    assert changes(days_before)["deleted"] == 0
