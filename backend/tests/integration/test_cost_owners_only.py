"""API seam: cost is for Owners only. The Organisation cost page is Owner-only, so the Agent
analytics that Editors may read (Version KPIs, the time series and the Version comparison, also
as CSV) must not hand them the same spend per Agent: Editors get every other number, with the
cost left out, and asking for the cost time series is refused."""

import csv
import io
from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI

from tests.conftest import ClientFactory, MemberFactory, SignedUpMember
from tests.fakes.clock import ControllableClock
from tests.integration.test_time_series import get_series, series
from tests.integration.test_version_comparison import get_comparison, two_versions
from tests.integration.test_version_metrics import chat, live_agent, metrics

COST_METRICS = {"cost_per_conversation_usd", "cost_total_usd"}
COST_LABELS = {"Cost per Conversation (USD)", "Total cost (USD)"}


@pytest.fixture
async def visitor(new_client: ClientFactory) -> httpx.AsyncClient:
    """A browser on someone's website: no Studio session."""
    return await new_client()


async def test_editors_read_version_kpis_without_the_cost(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    member_factory: MemberFactory,
    clock: ControllableClock,
) -> None:
    agent = await live_agent(app, owner)
    await chat(visitor, agent, "Leave? words:20")
    editor = await member_factory(owner, "editor")

    (owners,) = (await metrics(owner, agent))["versions"]
    (editors,) = (await metrics(editor, agent))["versions"]

    assert Decimal(owners["cost"]["total_usd"]) > 0
    assert editors["cost"] is None
    # Every other number is the same for both.
    assert {**editors, "cost": owners["cost"]} == owners


async def test_editors_are_refused_the_cost_time_series_but_not_the_others(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    member_factory: MemberFactory,
    clock: ControllableClock,
) -> None:
    agent = await live_agent(app, owner)
    await chat(visitor, agent, "Leave? words:20")
    editor = await member_factory(owner, "editor")

    refused = await get_series(editor, agent, metric="cost_usd")
    replies = await series(editor, agent, metric="replies")
    owners = await series(owner, agent, metric="cost_usd")

    assert refused.status_code == 403, refused.text
    assert refused.json() == {"detail": "Only Owners can do this"}
    assert sum(point["value"] or 0 for point in replies["points"]) == 1
    assert sum(point["value"] or 0 for point in owners["points"]) > 0


async def test_editors_compare_versions_without_the_cost(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    member_factory: MemberFactory,
    clock: ControllableClock,
) -> None:
    agent, v1, v2 = await two_versions(app, owner, visitor)
    editor = await member_factory(owner, "editor")
    sides = {"a": v1["id"], "b": v2["id"]}

    owners = (await get_comparison(owner, agent, **sides)).json()
    shown = await get_comparison(editor, agent, **sides)
    exported = await get_comparison(editor, agent, csv=True, **sides)
    owners_csv = (await get_comparison(owner, agent, csv=True, **sides)).text

    assert shown.status_code == 200, shown.text
    editors = shown.json()
    assert editors["a"]["cost"] is None
    assert editors["b"]["cost"] is None
    assert owners["a"]["cost"] is not None
    owner_rows = [row["metric"] for row in owners["metrics"]]
    assert set(owner_rows) >= COST_METRICS
    assert [row["metric"] for row in editors["metrics"]] == [
        metric for metric in owner_rows if metric not in COST_METRICS
    ]
    assert exported.status_code == 200, exported.text
    editor_labels = [row[0] for row in csv.reader(io.StringIO(exported.text))]
    owner_labels = [row[0] for row in csv.reader(io.StringIO(owners_csv))]
    assert set(owner_labels) >= COST_LABELS
    assert editor_labels == [label for label in owner_labels if label not in COST_LABELS]
