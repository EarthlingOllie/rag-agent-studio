"""The demo Organisation's seeded history (ticket 10-02), checked as an interviewer would see it:
through the API, signed in as the printed demo Owner.

Most tests seed a light history (a Conversation a day); the interviewer's walkthrough seeds the
full one, whose fixed random seed makes the comparison tell its story.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from pydantic_ai.exceptions import ModelHTTPError, ModelRateLimitError
from sqlalchemy import func, select

from app.analytics.models import UsageDaily, UsageRollupState
from app.audit.models import AuditEvent
from app.core.clock import SystemClock
from app.credentials.registry import Provider
from app.seed import content
from app.seed.runner import RealCredential, SeedError, erase_demo, seed
from tests.agents import answer_with
from tests.conftest import ClientFactory, SignedUpMember
from tests.integration.test_playground_errors import failing
from tests.integration.test_seed import ASSETS, demo_project, get, signed_in

LIGHT = content.History(conversations_per_day={content.HR_AGENT: 1, content.SHOP_AGENT: 1})


async def demo_agents(owner: SignedUpMember) -> tuple[str, dict[str, Any]]:
    project = await demo_project(owner)
    agents = {a["name"]: a for a in await get(owner, "projects", project["id"], "agents")}
    return project["id"], agents


async def test_the_hr_agent_has_three_versions_with_v2_reverted(
    app: FastAPI, new_client: ClientFactory
) -> None:
    await erase_demo(app)
    await seed(app, ASSETS, history=LIGHT)

    owner = await signed_in(new_client, content.OWNER)
    project, agents = await demo_agents(owner)
    hr = agents["HR helper"]
    assert hr["live_version"]["number"] == 3
    versions = await get(owner, "projects", project, "agents", hr["id"], "versions")
    assert [v["number"] for v in versions["versions"]] == [3, 2, 1]
    history = await get(owner, "projects", project, "agents", hr["id"], "live-history")
    assert [
        (e["action"], e["from_version"] and e["from_version"]["number"], e["to_version"]["number"])
        for e in history
    ] == [("publish", 1, 3), ("revert", 2, 1), ("publish", 1, 2), ("publish", None, 1)]
    # The history happened over the past four weeks, not all at once today.
    times = [datetime.fromisoformat(e["occurred_at"]) for e in history]
    today = datetime.now(UTC)
    assert today - times[-1] > timedelta(days=27)
    assert today - times[0] > timedelta(days=2)
    assert times == sorted(times, reverse=True)
    # The Editor shipped v2 and v3; the Owner reverted v2.
    assert [e["actor"]["name"] for e in history] == [
        content.EDITOR.name,
        content.OWNER.name,
        content.EDITOR.name,
        content.OWNER.name,
    ]
    assert (
        hr["draft"]["behaviour"]["system_prompt"]
        == versions["versions"][0]["config"]["behaviour"]["system_prompt"]
    )


async def test_the_instructions_have_two_versions_with_the_product_faq_behind(
    app: FastAPI, new_client: ClientFactory
) -> None:
    await erase_demo(app)
    await seed(app, ASSETS, history=LIGHT)

    owner = await signed_in(new_client, content.OWNER)
    project, agents = await demo_agents(owner)
    instructions = await get(owner, "projects", project, "instructions", "versions")
    assert [(v["number"], v["note"]) for v in instructions["versions"]] == [
        (2, "No promises beyond policy"),
        (1, "House style"),
    ]
    assert instructions["current_version_id"] == instructions["versions"][0]["id"]
    rollout = await get(owner, "projects", project, "instructions", "rollout")
    assert rollout["current_version"]["number"] == 2
    assert rollout["behind"] == 1
    assert {
        a["name"]: (a["live_version"]["number"], a["instructions_version"]["number"], a["behind"])
        for a in rollout["agents"]
    } == {
        "HR helper": (3, 2, False),
        "Product FAQ": (1, 1, True),
        # Rolled out with a bulk publish.
        "Low-budget helper": (2, 2, False),
    }
    assert not any(a["has_draft_changes"] for a in rollout["agents"])
    budget = agents["Low-budget helper"]
    history = await get(owner, "projects", project, "agents", budget["id"], "live-history")
    assert [e["action"] for e in history] == ["bulk_publish", "publish"]


async def test_an_interviewer_sees_four_weeks_of_history_that_tells_the_v2_story(
    app: FastAPI, new_client: ClientFactory
) -> None:
    """The full history, as the README's demo walks through it: the comparison shows v2 clearly
    worse than v1, v3 promising but on a small sample, and every day of it in the rollups."""
    await erase_demo(app)
    await seed(app, ASSETS)

    owner = await signed_in(new_client, content.OWNER)
    project, agents = await demo_agents(owner)
    today = datetime.now(UTC).date()
    start = today - timedelta(days=content.HISTORY_DAYS)
    hr = agents["HR helper"]
    # The Studio's default range, the last 30 days, holds the whole history.
    metrics = await get(owner, "projects", project, "agents", hr["id"], "metrics")
    versions = {v["number"]: v for v in metrics["versions"]}
    assert set(versions) == {1, 2, 3}
    v1, v2, v3 = versions[1], versions[2], versions[3]
    assert [v["is_live"] for v in (v1, v2, v3)] == [False, False, True]

    # v2 is clearly worse than v1: fewer thumbs up, and the intervals don't overlap.
    assert v2["thumbs_up"]["rate"] < v1["thumbs_up"]["rate"] < v3["thumbs_up"]["rate"]
    assert v2["thumbs_up"]["high"] < v1["thumbs_up"]["low"]
    assert v2["rating"]["mean"] < v1["rating"]["mean"]
    assert not v1["low_confidence"]
    assert not v2["low_confidence"]
    assert not v1["thumbs_up"]["low_confidence"]
    assert not v2["thumbs_up"]["low_confidence"]
    # v3 has only been Live three days: a small sample, flagged, its interval overlapping v1's.
    assert v3["low_confidence"]
    assert v3["thumbs_up"]["low_confidence"]
    assert v3["conversations"] < 30 < v2["conversations"] < v1["conversations"]
    assert v3["thumbs_up"]["low"] < v1["thumbs_up"]["high"]
    # Every reply was the demo model's, with tokens counted.
    for version in (v1, v2, v3):
        assert version["tokens"]["n"] == version["messages"] > 0
        assert version["fallback"]["count"] == 0

    faq = agents["Product FAQ"]
    faq_metrics = await get(owner, "projects", project, "agents", faq["id"], "metrics")
    (faq_v1,) = faq_metrics["versions"]
    assert faq_v1["conversations"] > 30
    assert faq_v1["thumbs_up"]["n"] > 30

    # Conversations are spread over every day of the four weeks, none of them today.
    conversations = []
    page = 1
    while True:
        found = await owner.client.get(
            f"/api/organisations/{owner.organisation_id}/projects/{project}/conversations",
            params={"page": page, "page_size": 100, "playground": "false"},
        )
        conversations += found.json()["items"]
        if len(conversations) >= found.json()["total"]:
            break
        page += 1
    days = {datetime.fromisoformat(c["created_at"]).date() for c in conversations}
    assert days == {start + timedelta(days=n) for n in range(content.HISTORY_DAYS)}
    assert sum(1 for c in conversations if c["rating"] is not None) > 50
    assert v1["conversations"] + v2["conversations"] + v3["conversations"] + faq_v1[
        "conversations"
    ] == len(conversations)

    # The rollup ran for every historical day: each is final, and holds that day's usage.
    async with app.state.sessionmaker() as session:
        finalised = await session.scalar(
            select(UsageRollupState.finalised_through).where(
                UsageRollupState.organisation_id == uuid.UUID(owner.organisation_id)
            )
        )
        rolled = set(
            await session.scalars(
                select(UsageDaily.day)
                .where(UsageDaily.organisation_id == uuid.UUID(owner.organisation_id))
                .distinct()
            )
        )
    assert finalised == today - timedelta(days=1)
    assert rolled == days
    one_day = await owner.client.get(
        f"/api/organisations/{owner.organisation_id}/projects/{project}/agents/{hr['id']}/metrics",
        params={"start": str(start), "end": str(start)},
    )
    on_the_first_day = {v["number"]: v["conversations"] for v in one_day.json()["versions"]}
    assert on_the_first_day == {1: 5, 2: 0, 3: 0}

    # The Audit tab tells the same story, from the sign-up four weeks ago.
    events = await owner.client.get(
        f"/api/organisations/{owner.organisation_id}/audit-events", params={"page_size": 100}
    )
    assert events.status_code == 200, events.text
    items = events.json()["items"]
    actions = [e["action"] for e in items]
    for action in (
        "organisation.created",
        "project.instructions_published",
        "agent.published",
        "agent.reverted",
        "agent.bulk_published",
        "project.agents_bulk_published",
    ):
        assert action in actions, action
    oldest = min(datetime.fromisoformat(e["occurred_at"]) for e in items)
    assert oldest.date() == start


async def visitor_conversations(owner: SignedUpMember, project: str) -> list[dict[str, Any]]:
    found = await owner.client.get(
        f"/api/organisations/{owner.organisation_id}/projects/{project}/conversations",
        params={"page_size": 100, "playground": "false"},
    )
    assert found.status_code == 200, found.text
    assert found.json()["total"] <= 100
    items: list[dict[str, Any]] = found.json()["items"]
    return items


async def history_counts(app: FastAPI, owner: SignedUpMember) -> dict[str, Any]:
    project, agents = await demo_agents(owner)
    live = {}
    for name, agent in agents.items():
        entries = await get(owner, "projects", project, "agents", agent["id"], "live-history")
        live[name] = [e["id"] for e in entries]
    async with app.state.sessionmaker() as session:
        audit_events = await session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.organisation_id == uuid.UUID(owner.organisation_id))
        )
    instructions = await get(owner, "projects", project, "instructions", "versions")
    return {
        "conversations": sorted(c["id"] for c in await visitor_conversations(owner, project)),
        "live_history": live,
        "instructions": [v["id"] for v in instructions["versions"]],
        "audit_events": audit_events,
    }


async def test_seeding_again_never_replays_the_history(
    app: FastAPI, new_client: ClientFactory
) -> None:
    await erase_demo(app)
    first = await seed(app, ASSETS, history=LIGHT)
    owner = await signed_in(new_client, content.OWNER)
    before = await history_counts(app, owner)

    again = await seed(app, ASSETS, history=LIGHT)

    assert again == first
    assert await history_counts(app, owner) == before
    assert len(before["conversations"]) == 2 * content.HISTORY_DAYS
    # The seed put the app's own clock back when it was done.
    assert isinstance(app.state.clock, SystemClock)


async def test_the_history_is_answered_by_the_demo_model_even_with_a_real_credential(
    app: FastAPI, new_client: ClientFactory
) -> None:
    await erase_demo(app)
    real = RealCredential(Provider.OPENAI, "sk-real-key-from-env-0000", "gpt-4.1")

    report = await seed(app, ASSETS, real, history=LIGHT)

    assert report.default_model == "GPT-4.1 (Northwind OpenAI)"
    owner = await signed_in(new_client, content.OWNER)
    project, _ = await demo_agents(owner)
    providers = set()
    for conversation in await visitor_conversations(owner, project):
        found = await get(owner, "projects", project, "conversations", conversation["id"])
        providers |= {m["model_provider"] for m in found["messages"] if m["role"] == "assistant"}
    assert providers == {"demo"}


async def test_the_seed_will_not_complete_a_demo_organisation_without_its_history(
    app: FastAPI, new_client: ClientFactory, quiet_seed_history: None
) -> None:
    await erase_demo(app)
    await seed(app, ASSETS)
    owner = await signed_in(new_client, content.OWNER)
    project, agents = await demo_agents(owner)
    # Someone deletes the HR helper, so seeding again would make a new one without Versions.
    path = f"/api/organisations/{owner.organisation_id}/projects/{project}/agents"
    hr = agents["HR helper"]
    archived = await owner.client.post(f"{path}/{hr['id']}/archive")
    assert archived.status_code == 200, archived.text
    deleted = await owner.client.request(
        "DELETE", f"{path}/{hr['id']}", json={"confirm_name": "HR helper"}
    )
    assert deleted.status_code == 204, deleted.text

    with pytest.raises(SeedError, match=r"HR helper has no Versions.*make seed-reset"):
        await seed(app, ASSETS)

    assert isinstance(app.state.clock, SystemClock)


async def test_the_seed_stops_when_a_visitor_gets_no_reply(app: FastAPI) -> None:
    await erase_demo(app)
    error = ModelHTTPError.for_category(ModelRateLimitError, status_code=429, model_name="m")
    answer_with(app, failing(error))

    with pytest.raises(SeedError, match="gave a Visitor no reply"):
        await seed(app, ASSETS, history=LIGHT)

    assert isinstance(app.state.clock, SystemClock)
    await erase_demo(app)
