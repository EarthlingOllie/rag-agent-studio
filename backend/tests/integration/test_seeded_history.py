"""The demo Organisation's seeded history (ticket 10-02), checked as an interviewer would see it:
through the API, signed in as the printed demo Owner.

Most tests seed a light history (a Conversation a day); the interviewer's walkthrough seeds the
full one, whose fixed random seed makes the comparison tell its story.
"""

import asyncio
import itertools
import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import func, select

from app.analytics.models import UsageDaily, UsageRollupState
from app.audit.models import AuditEvent
from app.core.clock import SystemClock
from app.credentials.registry import Provider
from app.jobs.tasks import sweep_jobs
from app.seed import content, runner
from app.seed import history as seed_history
from app.seed.runner import RealCredential, SeedError, erase_demo, seed
from tests.conftest import ClientFactory, SignedUpMember
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
        "Guardrail demo": (2, 2, False),
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

    # Most of the HR helper's replies were judged: v2's uncited ones all failed grounding, so its
    # Live score is clearly below v1's, on samples large enough not to be flagged.
    assert v2["live_score"]["rate"] == 0
    assert v2["live_score"]["high"] < v1["live_score"]["low"]
    assert v1["live_score"]["n"] > v2["live_score"]["n"] >= 30
    assert not v1["live_score"]["low_confidence"]
    assert not v2["live_score"]["low_confidence"]
    assert v3["live_score"]["low_confidence"]
    assert v3["live_score"]["rate"] > 0
    # No Live score drop alert stands on v3: it has too few Live Verdicts to compare.
    assert hr["live_score_drop_alert"] is False

    # The Suggestion made from v2 reads its 50 most recent pieces of evidence: the oldest of its
    # replies were purged since, the rest weren't.
    agent = ("projects", project, "agents", hr["id"])
    (listed,) = await get(owner, *agent, "suggestions")
    suggestion = await get(owner, *agent, "suggestions", listed["id"])
    replies = [e for e in suggestion["evidence"] if e["message_id"] is not None]
    assert {e["text_purged"] for e in replies} == {True, False}
    assert suggestion["check"]["state"] in ("clear", "regressions")
    assert suggestion["gaps"]

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
        live[name] = [(e["action"], e["occurred_at"]) for e in entries]
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


async def test_the_seed_stops_when_a_visitor_gets_no_reply(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    await erase_demo(app)
    # A question the widget API refuses (longer than a Visitor may ask) gets no reply.
    too_long = "Why? " * 1000
    monkeypatch.setattr(content, "QUESTIONS", {name: (too_long,) for name in content.QUESTIONS})

    with pytest.raises(SeedError, match="gave a Visitor no reply"):
        await seed(app, ASSETS, history=LIGHT)

    assert isinstance(app.state.clock, SystemClock)
    await erase_demo(app)


async def test_the_hr_helper_has_an_evaluation_set_and_two_runs_that_explain_the_revert(
    app: FastAPI, new_client: ClientFactory
) -> None:
    """Spec 14's demo: the HR helper's Evaluation Set, some of it added from thumbs-down
    Messages, and two finished Runs judged by the Demo model. The Run of v2 against v1 shows
    the Regressions behind the revert; the Draft against v3 shows none."""
    await erase_demo(app)
    await seed(app, ASSETS, history=LIGHT)

    owner = await signed_in(new_client, content.OWNER)
    project, agents = await demo_agents(owner)
    hr = agents["HR helper"]
    evaluation = ("projects", project, "agents", hr["id"], "evaluation")
    cases = await get(owner, *evaluation, "cases")
    assert len(cases) == len(content.EVALUATION_CASES) == 12
    sources = [case["source"] for case in cases]
    assert 1 <= sources.count("from_message") <= content.CASES_FROM_MESSAGES
    assert [case["expect_fallback"] for case in cases].count(True) >= 1
    with_sources = [case for case in cases if case["expected_sources"]]
    assert with_sources
    assert not any(case["stale"] for case in cases)
    # Each case added from a Message answers a question a Visitor gave a thumbs down.
    downvoted = set()
    for conversation in await visitor_conversations(owner, project):
        if conversation["agent_id"] != hr["id"]:
            continue
        found = await get(owner, "projects", project, "conversations", conversation["id"])
        messages = found["messages"]
        for asked, answer in itertools.pairwise(messages):
            if (answer.get("feedback") or {}).get("rating") == "down":
                downvoted.add(asked["content"])
    assert {c["question"] for c in cases if c["source"] == "from_message"} <= downvoted

    # The Runs the Agent started; the Suggestion's check is a Run of its own.
    runs = [run for run in await get(owner, *evaluation, "runs") if run["kind"] == "agent"]
    assert [run["status"] for run in runs] == ["completed", "completed"]
    draft_run, v2_run = runs
    assert v2_run["judge_provider"] == draft_run["judge_provider"] == "demo"
    assert [(s["kind"], s["version_number"]) for s in v2_run["sides"]] == [
        ("version", 1),
        ("version", 2),
    ]
    assert [(s["kind"], s["version_number"]) for s in draft_run["sides"]] == [
        ("version", 3),
        ("draft", None),
    ]
    first, second = v2_run["sides"]
    assert second["score"] < first["score"]

    # The Owner ran v2 against v1 just before reverting it, and the Editor ran the Draft
    # against v3 after publishing it: both happened during the history, under its clock.
    live = await get(owner, "projects", project, "agents", hr["id"], "live-history")
    reverted = next(e for e in live if e["action"] == "revert")
    published_v3 = live[0]
    assert v2_run["finished_at"] <= reverted["occurred_at"]
    assert published_v3["occurred_at"] <= draft_run["created_at"]
    assert datetime.fromisoformat(draft_run["finished_at"]) < datetime.now(UTC) - timedelta(
        hours=12
    )

    results = await get(owner, *evaluation, "runs", v2_run["id"], "results")
    regressions = [case for case in results["cases"] if case["change"] == "regression"]
    assert regressions
    for case in regressions:
        on_v2 = [r for r in case["results"] if r["position"] == "second"]
        failed = [v for r in on_v2 for v in r["verdicts"] if v["outcome"] == "fail"]
        assert any(v["kind"] == "grounding" for v in failed), case
        assert all(v["reason"] for v in failed)

    draft_results = await get(owner, *evaluation, "runs", draft_run["id"], "results")
    assert not [case for case in draft_results["cases"] if case["change"] is not None]
    # So the Publish dialog shows the Draft clear of Regressions against v3.
    summary = await get(owner, *evaluation, "publish-summary")
    assert summary["state"] == "clear"

    # Adding a case from a Message is audited, under the history's clock.
    events = await owner.client.get(
        f"/api/organisations/{owner.organisation_id}/audit-events",
        params={"page_size": 100, "action": "agent.evaluation_case_added_from_message"},
    )
    assert events.status_code == 200, events.text
    added = events.json()["items"]
    assert len(added) == sources.count("from_message")
    assert {e["actor"]["name"] for e in added} == {content.OWNER.name}


async def test_the_seed_stops_when_an_evaluation_run_does_not_complete(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch, quiet_seed_history: None
) -> None:
    await erase_demo(app)

    async def stalled(*_: object) -> None:
        """A Run job that never picks the Run up."""

    monkeypatch.setattr("app.evaluation.tasks.run_evaluation", stalled)

    with pytest.raises(SeedError, match="HR helper's Evaluation Run ended queued"):
        await seed(app, ASSETS)

    assert isinstance(app.state.clock, SystemClock)
    await erase_demo(app)


async def live_verdicts_of(
    owner: SignedUpMember, project: str, agent: dict[str, Any]
) -> list[dict[str, Any]]:
    """Every Live Verdict of the Agent's Visitor replies, read from each reply's Trace."""
    found = []
    for conversation in await visitor_conversations(owner, project):
        if conversation["agent_id"] != agent["id"]:
            continue
        read = await get(owner, "projects", project, "conversations", conversation["id"])
        for message in read["messages"]:
            if message["role"] != "assistant":
                continue
            trace = await get(
                owner,
                "projects",
                project,
                "conversations",
                conversation["id"],
                "messages",
                message["id"],
                "trace",
            )
            if trace["live_verdict"] is not None:
                found.append({**trace["live_verdict"], "replied_at": message["created_at"]})
    return found


async def test_the_hr_helpers_seeded_replies_have_live_verdicts_and_v2_scores_lower(
    app: FastAPI, new_client: ClientFactory
) -> None:
    """Spec 15's demo: the HR helper's Visitor replies were sampled by its Live sample rate and
    judged by the Demo model during the history, under its clock. v2's uncited replies fail
    grounding, so its Live score is lower than v1's in the comparison and the Time series, and
    no Live score drop alert stands on the current Live Version."""
    await erase_demo(app)
    await seed(app, ASSETS, history=LIGHT)

    owner = await signed_in(new_client, content.OWNER)
    project, agents = await demo_agents(owner)
    hr = agents["HR helper"]
    versions = await get(owner, "projects", project, "agents", hr["id"], "versions")
    number = {v["id"]: v["number"] for v in versions["versions"]}

    verdicts = await live_verdicts_of(owner, project, hr)
    by_version: dict[int, list[dict[str, Any]]] = {}
    for verdict in verdicts:
        by_version.setdefault(number[verdict["agent_version_id"]], []).append(verdict)
    assert {1, 2} <= set(by_version)
    assert {v["status"] for v in verdicts} == {"judged"}
    assert {(v["judge_provider"], v["judge_model"]) for v in verdicts} == {("demo", "demo-chat")}
    # Judged during the history, as the reply was given, not today.
    for verdict in verdicts:
        judged = datetime.fromisoformat(verdict["judged_at"])
        replied = datetime.fromisoformat(verdict["replied_at"])
        assert abs(judged - replied) < timedelta(minutes=5)
        assert judged.date() < datetime.now(UTC).date()
    # v2 cited nothing, so every one of its replies failed grounding, with the judge's reason
    # unless the Purge has cleared it with the reply's text since; the outcome stays.
    for verdict in by_version[2]:
        assert verdict["grounded"]["outcome"] == "fail"
        assert bool(verdict["grounded"]["reason"]) == (verdict["purged_at"] is None)
        assert verdict["passed"] is False
    assert any(v["purged_at"] is None for v in by_version[2])
    assert any(v["passed"] for v in by_version[1])
    # Only the HR helper is sampled.
    assert not await live_verdicts_of(owner, project, agents["Product FAQ"])

    metrics = await get(owner, "projects", project, "agents", hr["id"], "metrics")
    scores = {v["number"]: v["live_score"] for v in metrics["versions"]}
    assert scores[1]["n"] == len(by_version[1])
    assert scores[2]["n"] == len(by_version[2])
    assert scores[2]["rate"] == 0
    assert scores[2]["rate"] < scores[1]["rate"]

    comparison = await owner.client.get(
        f"/api/organisations/{owner.organisation_id}/projects/{project}/agents/{hr['id']}"
        "/comparison",
        params={"a": versions["versions"][2]["id"], "b": versions["versions"][1]["id"]},
    )
    assert comparison.status_code == 200, comparison.text
    (row,) = [r for r in comparison.json()["metrics"] if r["metric"] == "live_score"]
    assert row["b"] < row["a"]
    assert row["better"] == "a"

    # The Time series dips while v2 was Live.
    series = await owner.client.get(
        f"/api/organisations/{owner.organisation_id}/projects/{project}/agents/{hr['id']}"
        "/time-series",
        params={"metric": "live_score"},
    )
    assert series.status_code == 200, series.text
    live = await get(owner, "projects", project, "agents", hr["id"], "live-history")
    published_v2 = next(e for e in live if e["to_version"]["number"] == 2)
    reverted = next(e for e in live if e["action"] == "revert")
    v2_days = (
        datetime.fromisoformat(published_v2["occurred_at"]).date(),
        datetime.fromisoformat(reverted["occurred_at"]).date(),
    )
    points = [p for p in series.json()["points"] if p["n"]]
    during = [
        p["value"] for p in points if v2_days[0] <= date.fromisoformat(p["start"]) < v2_days[1]
    ]
    before = [p["value"] for p in points if date.fromisoformat(p["start"]) < v2_days[0]]
    assert during
    assert set(during) == {0}
    assert any(value > 0 for value in before)

    # The Conversations viewer finds v2's failed replies.
    failed = await owner.client.get(
        f"/api/organisations/{owner.organisation_id}/projects/{project}/conversations",
        params={"agent_id": hr["id"], "live_verdict": "failed", "page_size": 100},
    )
    assert failed.status_code == 200, failed.text
    assert failed.json()["total"] > 0
    assert all(c["failed_live_verdicts"] > 0 for c in failed.json()["items"])

    # No Live score drop alert is faked on the current Live Version, v3.
    assert hr["live_version"]["number"] == 3
    assert hr["live_score_drop_alert"] is False


async def test_the_hr_helper_has_a_stale_suggestion_with_its_check_a_gap_and_purged_evidence(
    app: FastAPI, new_client: ClientFactory
) -> None:
    """Spec 16's demo: on the morning of the revert the Owner had a Suggestion made from v2's
    failures, which asks for citations, names a Knowledge Base gap and was checked against the
    Evaluation Set. v1 replaced v2, so it reads as stale; the Organisation keeps Message text for
    two weeks, so its oldest evidence reads "Text purged" while the change and its explanation
    stay."""
    await erase_demo(app)
    await seed(app, ASSETS, history=LIGHT)

    owner = await signed_in(new_client, content.OWNER)
    organisation = await owner.client.get(f"/api/organisations/{owner.organisation_id}")
    assert organisation.json()["retention_days"] == 14
    project, agents = await demo_agents(owner)
    hr = agents["HR helper"]
    agent = ("projects", project, "agents", hr["id"])
    (listed,) = await get(owner, *agent, "suggestions")
    assert listed["status"] == "completed"
    assert listed["outcome"] == "changes"
    assert listed["base_version_number"] == 2
    assert listed["stale"] is True
    assert listed["applied_by"] is None

    # Made from v2's whole time as the Live Version, under the history's clock, just before the
    # revert.
    live = await get(owner, *agent, "live-history")
    published_v2 = datetime.fromisoformat(
        next(e for e in live if e["to_version"]["number"] == 2)["occurred_at"]
    )
    reverted = datetime.fromisoformat(
        next(e for e in live if e["action"] == "revert")["occurred_at"]
    )
    assert listed["range_start"] == str(published_v2.date())
    assert listed["range_end"] == str(reverted.date())
    assert published_v2 < datetime.fromisoformat(listed["created_at"])
    assert datetime.fromisoformat(listed["finished_at"]) <= reverted

    suggestion = await get(owner, *agent, "suggestions", listed["id"])
    (change,) = suggestion["changes"]
    assert change["path"] == "behaviour.system_prompt"
    assert change["base_value"] == content.HR_V2.system_prompt
    assert change["suggested_value"] == (
        "Answer staff questions in one short sentence. Don't quote the handbook.\n"
        "Always cite the passage you used."
    )
    assert change["explanation"]
    assert change["evidence_ids"]
    assert suggestion["gaps"]
    assert all(gap["topic"] and gap["evidence_ids"] for gap in suggestion["gaps"])

    # Its check: v2 against the Suggestion on the Evaluation Set, a Run of its own.
    check = suggestion["check"]
    assert check["state"] in ("clear", "regressions")
    assert check["live_score"] is not None
    assert check["suggestion_score"] is not None
    run = await get(owner, *agent, "evaluation", "runs", check["evaluation_run_id"])
    assert run["kind"] == "suggestion"
    assert run["status"] == "completed"
    assert [(s["kind"], s["version_number"]) for s in run["sides"]] == [
        ("version", 2),
        ("suggestion", 2),
    ]
    assert datetime.fromisoformat(run["finished_at"]) <= reverted

    # The evidence: v2's replies and the Evaluation Cases v2 failed in the Run before the revert.
    # Replies older than the Retention Window were purged since; their dates and Live Verdicts
    # stay.
    evidence = suggestion["evidence"]
    replies = [e for e in evidence if e["message_id"] is not None]
    cases = [e for e in evidence if e["run_case_id"] is not None]
    assert cases
    assert all(e["kind"] == "evaluation_case" and not e["case_deleted"] for e in cases)
    # The seed's nightly Purge ran at 00:10 today, so its cutoff is that moment less the window,
    # not now less the window (which would misjudge replies from earlier in the boundary day).
    purge_at = datetime.combine(datetime.now(UTC).date(), time(0, 10), tzinfo=UTC)
    cutoff = purge_at - timedelta(days=14)
    purged = [e for e in replies if e["text_purged"]]
    kept = [e for e in replies if not e["text_purged"]]
    assert purged
    assert kept
    assert all(datetime.fromisoformat(e["occurred_at"]) < cutoff for e in purged)
    assert all(datetime.fromisoformat(e["occurred_at"]) > cutoff for e in kept)
    assert {e["live_verdict"] for e in purged} <= {"fail", None}
    assert "fail" in {e["live_verdict"] for e in replies}
    # The Conversations viewer has the purged reply without its text.
    first = purged[0]
    conversation = await get(owner, "projects", project, "conversations", first["conversation_id"])
    (reply,) = [m for m in conversation["messages"] if m["id"] == first["message_id"]]
    assert reply["purged_at"] is not None
    assert reply["content"] == ""


async def test_the_seed_stops_when_the_suggestion_run_does_not_complete(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    await erase_demo(app)

    async def stalled(*_: object) -> None:
        """A Suggestion run job that never picks the run up."""

    monkeypatch.setattr("app.suggestions.tasks.run_suggestion", stalled)

    with pytest.raises(SeedError, match="HR helper's Suggestion run ended queued"):
        await seed(app, ASSETS, history=LIGHT)

    assert isinstance(app.state.clock, SystemClock)
    await erase_demo(app)


async def test_no_sweep_runs_while_the_seed_writes_its_history(
    app: FastAPI, new_client: ClientFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The history's jobs carry the seed's clock, weeks back, which a sweep by today's clock would
    take for jobs long dead (ticket 22-03: on the compose stack Beat's sweep ended a seeded
    Evaluation Run Interrupted). Beat's sweep, run meanwhile, finds the sweeper's lock taken."""
    sweeps: list[int | None] = []
    generate = seed_history.generate

    async def sweeping_first(*args: Any, **kwargs: Any) -> None:
        sweeps.append(await asyncio.to_thread(lambda: sweep_jobs.apply().get()))
        await generate(*args, **kwargs)

    monkeypatch.setattr(runner, "generate", sweeping_first)
    await erase_demo(app)

    await seed(app, ASSETS, history=LIGHT)

    assert sweeps == [None]
    # Once the history is written, sweeps run again.
    assert await asyncio.to_thread(lambda: sweep_jobs.apply().get()) is not None
