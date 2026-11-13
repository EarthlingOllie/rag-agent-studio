"""API seam and task seam: Guardrail analytics and alerts.

Visitors chat through the widget API; the input Guardrail's classifier is the rule-driven fake,
flagging any message containing "ignore your instructions" (``ATTACK``). The ``usage_daily``
rollup Beat task is called directly as a task, as Beat would at a given time. Editors read each
Agent Version's Guardrail block rate from the Version metrics endpoint, filter the
Conversations viewer by Guardrail outcome, and see the Agent's Block rate alert on the Agent.
Owners' emails are read from the in-memory outbox the task is given in place of the real
mailer.

Assertions are on HTTP responses and sent emails only."""

from datetime import timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select

import app.analytics.tasks as analytics_tasks
from app.conversations.models import Message, MessageRole
from app.mail.outbox import OutboxMailer
from tests.agents import save_draft
from tests.conftest import STUDIO_URL, ClientFactory, MemberFactory, SignedUpMember
from tests.documents import project_path
from tests.fakes.clock import ControllableClock
from tests.integration.test_agent_versions import published
from tests.integration.test_conversations import listed, playground_chat
from tests.integration.test_embed import conversation_token, send
from tests.integration.test_input_guardrail import ATTACK, guard
from tests.integration.test_version_metrics import live_agent, roll_up, version_kpis

BENIGN = "How much leave do I get? words:5"
SPIKE_SUBJECT = "HR helper is blocking an unusual share of messages"


@pytest.fixture
async def visitor(new_client: ClientFactory) -> httpx.AsyncClient:
    """A browser on someone's website: no Studio session."""
    return await new_client()


@pytest.fixture
def task_outbox(outbox: OutboxMailer, monkeypatch: pytest.MonkeyPatch) -> OutboxMailer:
    """The rollup task builds its own mailer from the settings; here it sends through the
    app's in-memory outbox, so the test can read what it sent."""
    monkeypatch.setattr(analytics_tasks, "build_mailer", lambda settings: outbox)
    return outbox


async def guarded_agent(app: FastAPI, owner: SignedUpMember) -> dict[str, Any]:
    """A live Agent (v1, block mode by default) whose input Guardrail flags ``ATTACK``."""
    agent = await live_agent(app, owner)
    guard(app)
    return agent


async def ask_all(
    visitor: httpx.AsyncClient, clock: ControllableClock, agent: dict[str, Any], *questions: str
) -> str:
    """A new Visitor Conversation asking each question, a few seconds apart (under the rate
    limits); its token."""
    token = await conversation_token(visitor, agent["public_id"])
    for question in questions:
        clock.advance(timedelta(seconds=7))
        response = await send(visitor, agent["public_id"], token, question)
        assert response.status_code == 200, response.text
    return token


async def answered_under_warn_mode(app: FastAPI, *conversation_ids: str) -> None:
    """Rewrites the replies of these Conversations as the removed warn mode saved them: the
    input Guardrail's verdict ``flagged`` instead of ``blocked`` (data from before C3)."""
    async with app.state.sessionmaker() as session:
        replies = await session.scalars(
            select(Message).where(
                Message.conversation_id.in_(conversation_ids),
                Message.role == MessageRole.ASSISTANT,
            )
        )
        for reply in replies:
            reply.guardrail_outcomes = [
                {**outcome, "action": "flagged"} for outcome in reply.guardrail_outcomes
            ]
        await session.commit()


async def get_agent(owner: SignedUpMember, agent: dict[str, Any]) -> dict[str, Any]:
    response = await owner.client.get(
        f"{project_path(owner, agent['project_id'])}/agents/{agent['id']}"
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def listed_agents(owner: SignedUpMember, agent: dict[str, Any]) -> list[dict[str, Any]]:
    response = await owner.client.get(f"{project_path(owner, agent['project_id'])}/agents")
    assert response.status_code == 200, response.text
    items: list[dict[str, Any]] = response.json()
    return items


def spike_emails(outbox: OutboxMailer, *members: SignedUpMember) -> list[tuple[str, str]]:
    """The Block rate alert emails sent to these Members (the test database holds other
    tests' Agents too, which the hourly check also looks at)."""
    to = {member.email for member in members}
    return [(e.to, e.subject) for e in outbox.sent if "unusual share" in e.subject and e.to in to]


# The block rate in rollups and KPI cards


async def test_the_block_rate_is_the_share_of_a_versions_replies_the_input_guardrail_blocked(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    agent = await guarded_agent(app, owner)
    await ask_all(visitor, clock, agent, BENIGN, ATTACK, BENIGN)
    await ask_all(visitor, clock, agent, BENIGN)
    # The Playground's blocked questions never count.
    await playground_chat(owner, agent["project_id"], agent["id"], ATTACK, ATTACK)

    kpis = await version_kpis(owner, agent, agent["v1"], start="2026-11-05", end="2026-11-05")

    assert kpis["messages"] == 4
    assert kpis["guardrail_blocks"] == {"count": 1, "rate": 0.25}
    # A refusal asked no model: it isn't counted in the tokens per reply.
    assert kpis["tokens"]["n"] == 3


async def test_the_block_rate_comes_from_the_rollups_once_the_day_is_final_per_version(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    agent = await guarded_agent(app, owner)
    await ask_all(visitor, clock, agent, ATTACK, ATTACK, BENIGN)
    saved = await save_draft(
        owner, agent["project_id"], agent["id"], {"behaviour": {"system_prompt": "Be brief."}}
    )
    assert saved.status_code == 200, saved.text
    v2 = await published(owner, agent["project_id"], agent["id"])
    await ask_all(visitor, clock, agent, BENIGN, BENIGN, BENIGN, ATTACK)
    live_v1 = await version_kpis(owner, agent, agent["v1"], start="2026-11-05", end="2026-11-05")
    live_v2 = await version_kpis(owner, agent, v2, start="2026-11-05", end="2026-11-05")

    clock.advance(timedelta(days=1))
    await roll_up(clock.now())
    final_v1 = await version_kpis(owner, agent, agent["v1"], start="2026-11-05", end="2026-11-05")
    final_v2 = await version_kpis(owner, agent, v2, start="2026-11-05", end="2026-11-05")

    assert (final_v1, final_v2) == (live_v1, live_v2)
    assert final_v1["guardrail_blocks"] == {"count": 2, "rate": pytest.approx(2 / 3)}
    assert final_v2["guardrail_blocks"] == {"count": 1, "rate": 0.25}


async def test_a_version_without_replies_has_no_block_rate(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock
) -> None:
    agent = await guarded_agent(app, owner)

    kpis = await version_kpis(owner, agent, agent["v1"], start="2026-11-05", end="2026-11-05")

    assert kpis["guardrail_blocks"] == {"count": 0, "rate": None}


async def test_an_old_warn_or_log_setting_is_ignored_so_attacks_are_still_blocks(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    agent = await guarded_agent(app, owner)
    for mode in ("warn", "log"):
        saved = await save_draft(
            owner, agent["project_id"], agent["id"], {"guardrails": {"input_mode": mode}}
        )
        assert saved.status_code == 200, saved.text
        version = await published(owner, agent["project_id"], agent["id"])
        await ask_all(visitor, clock, agent, ATTACK, BENIGN)

        kpis = await version_kpis(owner, agent, version, start="2026-11-05", end="2026-11-05")

        assert kpis["messages"] == 2
        assert kpis["guardrail_blocks"] == {"count": 1, "rate": 0.5}


# Filtering Conversations by Guardrail outcome


async def test_conversations_are_filtered_by_guardrail_outcome(
    app: FastAPI,
    owner: SignedUpMember,
    member_factory: MemberFactory,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    editor = await member_factory(owner, "editor")
    agent = await guarded_agent(app, owner)
    await ask_all(visitor, clock, agent, BENIGN, ATTACK, ATTACK)  # blocked twice
    await ask_all(visitor, clock, agent, BENIGN)  # no Guardrail outcome
    await ask_all(visitor, clock, agent, ATTACK)  # flagged, under the old warn mode (below)
    clock.advance(timedelta(minutes=1))
    playground = await playground_chat(owner, agent["project_id"], agent["id"], ATTACK)

    everything = await listed(editor, agent["project_id"])
    rows = everything["items"]
    assert len(rows) == 4
    playground_row, flagged_row, clean_row, blocked_row = rows
    assert playground_row["id"] == playground
    # Conversations from before the warn mode was removed keep their ``flagged`` outcome, and
    # the filter still finds them.
    await answered_under_warn_mode(app, playground_row["id"], flagged_row["id"])

    async def ids(outcome: str) -> list[str]:
        page = await listed(editor, agent["project_id"], guardrail=outcome)
        assert page["total"] == len(page["items"])
        return [row["id"] for row in page["items"]]

    assert await ids("blocked") == [blocked_row["id"]]
    assert await ids("flagged") == [playground_row["id"], flagged_row["id"]]
    assert await ids("any") == [playground_row["id"], flagged_row["id"], blocked_row["id"]]
    assert await ids("none") == [clean_row["id"]]
    assert await ids("logged") == []
    assert await ids("replaced") == []
    # Each row says how many of its replies have a Guardrail outcome.
    assert [row["guardrail_events"] for row in rows] == [1, 1, 0, 2]
    # The filter combines with the others.
    visitors_flagged = await listed(
        editor, agent["project_id"], guardrail="flagged", playground="false"
    )
    assert [row["id"] for row in visitors_flagged["items"]] == [flagged_row["id"]]


async def test_an_unknown_guardrail_outcome_is_refused(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock
) -> None:
    agent = await guarded_agent(app, owner)

    response = await owner.client.get(
        f"{project_path(owner, agent['project_id'])}/conversations", params={"guardrail": "evil"}
    )

    assert response.status_code == 422, response.text


# The Block rate alert


async def baseline(
    visitor: httpx.AsyncClient, clock: ControllableClock, agent: dict[str, Any]
) -> None:
    """A normal week before: ten benign replies a day for three days, then on to the next
    morning (2026-11-08 09:00)."""
    for _ in range(3):
        await ask_all(visitor, clock, agent, *[BENIGN] * 5)
        await ask_all(visitor, clock, agent, *[BENIGN] * 5)
        clock.advance(timedelta(days=1) - timedelta(seconds=70))


async def test_a_spike_in_the_block_rate_raises_the_alert_and_emails_every_owner_once(
    app: FastAPI,
    owner: SignedUpMember,
    member_factory: MemberFactory,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    task_outbox: OutboxMailer,
) -> None:
    second_owner = await member_factory(owner, "owner")
    await member_factory(owner, "editor")
    agent = await guarded_agent(app, owner)
    await baseline(visitor, clock, agent)
    await roll_up(clock.now())
    calm = await get_agent(owner, agent)

    # An attack: within the hour, 6 of 8 messages are blocked.
    await ask_all(visitor, clock, agent, *[ATTACK] * 3, BENIGN)
    await ask_all(visitor, clock, agent, *[ATTACK] * 3, BENIGN)
    await roll_up(clock.now())

    assert calm["block_rate_alert"] is False
    assert (await get_agent(owner, agent))["block_rate_alert"] is True
    (listed_agent,) = await listed_agents(owner, agent)
    assert listed_agent["block_rate_alert"] is True
    assert sorted(spike_emails(task_outbox, owner, second_owner)) == sorted(
        [(owner.email, SPIKE_SUBJECT), (second_owner.email, SPIKE_SUBJECT)]
    )
    email = next(e for e in task_outbox.sent if e.to == owner.email)
    assert "6 of the last hour's 8 Visitor messages (75%)" in email.text
    assert "0% over the week before" in email.text
    assert (
        f"{STUDIO_URL}/organisations/{owner.organisation_id}/projects/{agent['project_id']}"
        f"/conversations?agent={agent['id']}&guardrail=blocked"
    ) in email.text

    # The attack goes on: the alert stays and nobody is emailed again.
    clock.advance(timedelta(minutes=50))
    await ask_all(visitor, clock, agent, *[ATTACK] * 5)
    await roll_up(clock.now())
    assert (await get_agent(owner, agent))["block_rate_alert"] is True
    assert len(spike_emails(task_outbox, owner, second_owner)) == 2

    # An hour later it has stopped: the next run clears the alert.
    clock.advance(timedelta(hours=1))
    await ask_all(visitor, clock, agent, BENIGN)
    await roll_up(clock.now())
    assert (await get_agent(owner, agent))["block_rate_alert"] is False

    # A new attack raises it again, with a new email.
    await ask_all(visitor, clock, agent, *[ATTACK] * 5)
    await roll_up(clock.now())
    assert (await get_agent(owner, agent))["block_rate_alert"] is True
    assert len(spike_emails(task_outbox, owner, second_owner)) == 4


async def test_a_handful_of_blocks_is_not_a_spike(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    task_outbox: OutboxMailer,
) -> None:
    agent = await guarded_agent(app, owner)
    # Four blocks out of four: a high rate, but too few to call it an attack.
    await ask_all(visitor, clock, agent, *[ATTACK] * 4)

    await roll_up(clock.now())

    assert (await get_agent(owner, agent))["block_rate_alert"] is False
    assert spike_emails(task_outbox, owner) == []


async def test_a_block_rate_as_high_as_usual_is_not_a_spike(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    task_outbox: OutboxMailer,
) -> None:
    agent = await guarded_agent(app, owner)
    # An Agent that is always probed: half its messages were blocked every day this week.
    for _ in range(3):
        await ask_all(visitor, clock, agent, *[ATTACK, BENIGN] * 4)
        await ask_all(visitor, clock, agent, *[ATTACK, BENIGN] * 4)
        clock.advance(timedelta(days=1))
    # This hour, 5 of 8 (62.5%): not three times the usual rate.
    await ask_all(visitor, clock, agent, *[ATTACK] * 3, BENIGN)
    await ask_all(visitor, clock, agent, *[ATTACK] * 2, BENIGN, BENIGN)

    await roll_up(clock.now())

    assert (await get_agent(owner, agent))["block_rate_alert"] is False
    assert spike_emails(task_outbox, owner) == []


async def test_blocks_older_than_an_hour_or_in_the_playground_dont_make_a_spike(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    task_outbox: OutboxMailer,
) -> None:
    agent = await guarded_agent(app, owner)
    await ask_all(visitor, clock, agent, *[ATTACK] * 6)
    clock.advance(timedelta(hours=1))
    await playground_chat(owner, agent["project_id"], agent["id"], *[ATTACK] * 6)
    await ask_all(visitor, clock, agent, BENIGN)

    await roll_up(clock.now())

    assert (await get_agent(owner, agent))["block_rate_alert"] is False
    assert spike_emails(task_outbox, owner) == []


async def test_each_agent_has_its_own_alert(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    task_outbox: OutboxMailer,
    tenant_factory: Any,
) -> None:
    attacked = await guarded_agent(app, owner)
    stranger = await tenant_factory()
    quiet = await live_agent(app, stranger)
    await ask_all(visitor, clock, quiet, BENIGN)
    await ask_all(visitor, clock, attacked, *[ATTACK] * 5)

    await roll_up(clock.now())

    assert (await get_agent(owner, attacked))["block_rate_alert"] is True
    assert (await get_agent(stranger, quiet))["block_rate_alert"] is False
    assert [to for to, _ in spike_emails(task_outbox, owner, stranger)] == [owner.email]
