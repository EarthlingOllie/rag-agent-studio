"""API seam and task seam: the Organisation cost page's query. Visitors chat through the widget
API and Members try Agents in the Playground (answers from a ``FunctionModel``); the
``usage_daily`` rollup Beat task is called directly as a task; Owners read what the Organisation
spent over a period, by Project or by Agent, with Playground usage in its own column.

Assertions are on HTTP responses only. The amounts the cost is checked against come from the
Conversations viewer (each reply's own frozen cost), not from the rollups."""

from datetime import timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from tests.agents import create_agent
from tests.conftest import MemberFactory, SignedUpMember, TenantFactory
from tests.documents import create_project, upload
from tests.fakes.clock import ControllableClock
from tests.integration.test_agent_archive import archive
from tests.integration.test_agent_versions import published
from tests.integration.test_conversations import listed, opened, playground_chat
from tests.integration.test_playground import LEAVE
from tests.integration.test_prices import override
from tests.integration.test_version_metrics import chat, live_agent, roll_up

ZERO = Decimal(0)


@pytest.fixture
async def visitor(new_client: Any) -> httpx.AsyncClient:
    """A browser on someone's website: no Studio session."""
    client: httpx.AsyncClient = await new_client()
    return client


def cost_path(member: SignedUpMember) -> str:
    return f"/api/organisations/{member.organisation_id}/cost"


async def get_cost(member: SignedUpMember, **params: Any) -> httpx.Response:
    return await member.client.get(cost_path(member), params=params)


async def org_cost(member: SignedUpMember, **params: Any) -> dict[str, Any]:
    response = await get_cost(member, **params)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def spent(
    owner: SignedUpMember, project_id: str, *, playground: bool, agent_id: str | None = None
) -> Decimal:
    """What the Project's (or one Agent's) Visitor or Playground replies cost, read back from the
    Conversations viewer: the sum of each reply's frozen cost."""
    filters: dict[str, Any] = {"playground": str(playground).lower(), "page_size": 100}
    if agent_id is not None:
        filters["agent_id"] = agent_id
    page = await listed(owner, project_id, **filters)
    total = ZERO
    for row in page["items"]:
        detail = await opened(owner, project_id, row["id"])
        total += sum(
            (Decimal(m["cost_usd"]) for m in detail["messages"] if m["role"] == "assistant"), ZERO
        )
    return total


async def second_project(app: FastAPI, owner: SignedUpMember, name: str) -> dict[str, Any]:
    """Another Project holding the leave policy, with a live Agent answered the same way."""
    project_id = await create_project(owner, name)
    await upload(app, owner, project_id, "leave.txt", LEAVE.encode())
    agent: dict[str, Any] = await create_agent(owner, project_id, f"{name} helper")
    agent["project_id"] = project_id
    agent["v1"] = await published(owner, project_id, agent["id"])
    return agent


def amounts(row: dict[str, Any]) -> tuple[Decimal, Decimal, Decimal]:
    return (Decimal(row["visitor_usd"]), Decimal(row["playground_usd"]), Decimal(row["total_usd"]))


# By Project


async def test_owners_see_each_projects_cost_with_playground_usage_in_its_own_column(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    handbook = await live_agent(app, owner)
    payroll = await second_project(app, owner, "Payroll")
    await chat(visitor, handbook, "Leave? words:40", "Sick days? words:80")
    await chat(visitor, payroll, "Payday? words:10")
    await playground_chat(owner, handbook["project_id"], handbook["id"], "Testing words:300")

    body = await org_cost(owner, start="2026-11-05", end="2026-11-05", group_by="project")

    handbook_visitor = await spent(owner, handbook["project_id"], playground=False)
    handbook_playground = await spent(owner, handbook["project_id"], playground=True)
    payroll_visitor = await spent(owner, payroll["project_id"], playground=False)
    assert ZERO not in (handbook_visitor, handbook_playground, payroll_visitor)
    assert (body["start"], body["end"], body["group_by"]) == ("2026-11-05", "2026-11-05", "project")
    # Most expensive first.
    assert [(r["project_id"], r["project_name"], r["agent_id"]) for r in body["rows"]] == [
        (handbook["project_id"], "Handbook", None),
        (payroll["project_id"], "Payroll", None),
    ]
    assert amounts(body["rows"][0]) == (
        handbook_visitor,
        handbook_playground,
        handbook_visitor + handbook_playground,
    )
    assert amounts(body["rows"][1]) == (payroll_visitor, ZERO, payroll_visitor)
    assert amounts(body["total"]) == (
        handbook_visitor + payroll_visitor,
        handbook_playground,
        handbook_visitor + payroll_visitor + handbook_playground,
    )


# By Agent


async def test_by_agent_each_agent_has_its_own_line_including_archived_agents(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    hr = await live_agent(app, owner)
    leave: dict[str, Any] = await create_agent(owner, hr["project_id"], "Leave helper")
    leave["v1"] = await published(owner, hr["project_id"], leave["id"])
    tried: dict[str, Any] = await create_agent(owner, hr["project_id"], "Tried once")
    await chat(visitor, hr, "Leave? words:200")
    await chat(visitor, leave, "Holiday? words:20")
    await playground_chat(owner, hr["project_id"], leave["id"], "Testing words:60")
    await playground_chat(owner, hr["project_id"], tried["id"], "Testing words:5")
    archived = await archive(owner, hr["project_id"], tried["id"])
    assert archived.status_code == 200, archived.text
    # An Agent that never replied in the period has no line.
    await create_agent(owner, hr["project_id"], "Unused")

    body = await org_cost(owner, start="2026-11-05", end="2026-11-05", group_by="agent")

    project = hr["project_id"]
    hr_visitor = await spent(owner, project, playground=False, agent_id=hr["id"])
    leave_visitor = await spent(owner, project, playground=False, agent_id=leave["id"])
    leave_playground = await spent(owner, project, playground=True, agent_id=leave["id"])
    tried_playground = await spent(owner, project, playground=True, agent_id=tried["id"])
    assert hr_visitor > leave_visitor + leave_playground > tried_playground > ZERO
    assert body["group_by"] == "agent"
    assert [
        (r["project_id"], r["project_name"], r["agent_id"], r["agent_name"], *amounts(r))
        for r in body["rows"]
    ] == [
        (project, "Handbook", hr["id"], "HR helper", hr_visitor, ZERO, hr_visitor),
        (
            project,
            "Handbook",
            leave["id"],
            "Leave helper",
            leave_visitor,
            leave_playground,
            leave_visitor + leave_playground,
        ),
        (
            project,
            "Handbook",
            tried["id"],
            "Tried once",
            ZERO,
            tried_playground,
            tried_playground,
        ),
    ]
    by_project = await org_cost(owner, start="2026-11-05", end="2026-11-05")
    assert by_project["group_by"] == "project"
    (row,) = by_project["rows"]
    assert amounts(row) == amounts(by_project["total"]) == amounts(body["total"])
    assert amounts(row) == (
        hr_visitor + leave_visitor,
        leave_playground + tried_playground,
        hr_visitor + leave_visitor + leave_playground + tried_playground,
    )


# The period


async def test_past_days_come_from_the_rollups_and_days_outside_the_period_dont_count(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    agent = await live_agent(app, owner)
    project = agent["project_id"]
    await chat(visitor, agent, "Thursday words:30")  # 2026-11-05
    await playground_chat(owner, project, agent["id"], "Thursday test words:30")
    thursday = (
        await spent(owner, project, playground=False),
        await spent(owner, project, playground=True),
    )
    # Worked out from the raw tables: Thursday is today.
    live_thursday = await org_cost(owner, start="2026-11-05", end="2026-11-05")
    clock.advance(timedelta(days=1))
    await chat(visitor, agent, "Friday words:90")  # 2026-11-06
    await playground_chat(owner, project, agent["id"], "Friday test words:90")
    friday = (
        await spent(owner, project, playground=False) - thursday[0],
        await spent(owner, project, playground=True) - thursday[1],
    )

    clock.advance(timedelta(days=1))
    await roll_up(clock.now())
    # 2026-11-07: both days are over and rolled up.
    final_thursday = await org_cost(owner, start="2026-11-05", end="2026-11-05")
    final_friday = await org_cost(owner, start="2026-11-06", end="2026-11-06")
    both = await org_cost(owner, start="2026-11-05", end="2026-11-07")
    today = await org_cost(owner, start="2026-11-07", end="2026-11-07")

    assert amounts(final_thursday["total"]) == (*thursday, sum(thursday))
    assert final_thursday == live_thursday
    assert amounts(final_friday["total"]) == (*friday, sum(friday))
    assert amounts(both["total"]) == (
        thursday[0] + friday[0],
        thursday[1] + friday[1],
        sum(thursday) + sum(friday),
    )
    assert today["rows"] == []
    assert amounts(today["total"]) == (ZERO, ZERO, ZERO)


async def test_by_default_the_last_30_days_by_project(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    agent = await live_agent(app, owner)
    await chat(visitor, agent, "Old words:5")  # 2026-11-05
    clock.advance(timedelta(days=30))
    await roll_up(clock.now())
    await chat(visitor, agent, "New words:5")  # 2026-12-05

    body = await org_cost(owner)
    replies = await spent(owner, agent["project_id"], playground=False)

    assert (body["start"], body["end"], body["group_by"]) == ("2026-11-06", "2026-12-05", "project")
    (row,) = body["rows"]
    # Only the new reply: the old one is 30 days ago, outside the period.
    assert ZERO < Decimal(row["visitor_usd"]) < replies


async def test_cost_uses_the_prices_frozen_when_each_reply_was_made(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    agent = await live_agent(app, owner)
    project = agent["project_id"]
    await chat(visitor, agent, "Cheap words:50")
    await playground_chat(owner, project, agent["id"], "Cheap test words:50")
    cheap = await org_cost(owner, start="2026-11-05", end="2026-11-05")
    changed = await override(
        owner, agent["credential_id"], model="gpt-4.1-mini", input="100", output="400"
    )
    assert changed.status_code == 200, changed.text
    after_override = await org_cost(owner, start="2026-11-05", end="2026-11-05")
    await chat(visitor, agent, "Dear words:50")
    await playground_chat(owner, project, agent["id"], "Dear test words:50")

    dear = await org_cost(owner, start="2026-11-05", end="2026-11-05")

    # Changing a price doesn't move what was already spent.
    assert after_override == cheap
    visitor_usd = await spent(owner, project, playground=False)
    playground_usd = await spent(owner, project, playground=True)
    assert Decimal(dear["total"]["visitor_usd"]) == visitor_usd
    assert Decimal(dear["total"]["playground_usd"]) == playground_usd
    assert visitor_usd > 10 * Decimal(cheap["total"]["visitor_usd"])


async def test_an_organisation_with_no_replies_spent_nothing(
    owner: SignedUpMember, clock: ControllableClock
) -> None:
    body = await org_cost(owner, group_by="agent")

    assert body["rows"] == []
    assert body["total"] == {
        "visitor_usd": "0",
        "playground_usd": "0",
        "total_usd": "0",
    }


# Who may see it


async def test_editors_may_not_see_the_cost(
    owner: SignedUpMember, member_factory: MemberFactory, clock: ControllableClock
) -> None:
    editor = await member_factory(owner, "editor")

    response = await get_cost(editor)

    assert response.status_code == 403, response.text
    assert response.json()["detail"] == "Only Owners can do this"


async def test_only_the_organisations_own_spending_is_shown(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    tenant_factory: TenantFactory,
    clock: ControllableClock,
) -> None:
    agent = await live_agent(app, owner)
    await chat(visitor, agent, "Leave words:5")
    await playground_chat(owner, agent["project_id"], agent["id"], "Test words:5")
    stranger = await tenant_factory()

    theirs = await org_cost(stranger)
    peeking = await stranger.client.get(cost_path(owner))

    assert theirs["rows"] == []
    assert peeking.status_code == 404, peeking.text


@pytest.mark.parametrize(
    "params",
    [
        {"start": "2026-11-06", "end": "2026-11-05"},
        {"start": "2025-01-01", "end": "2026-11-05"},
        {"start": "yesterday"},
        {"group_by": "version"},
    ],
)
async def test_bad_queries_are_refused(
    owner: SignedUpMember, clock: ControllableClock, params: dict[str, str]
) -> None:
    response = await get_cost(owner, **params)

    assert response.status_code == 422, response.text
