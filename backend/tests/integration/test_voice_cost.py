"""API seam and task seam: Voice Cost (spec 20, ticket 20-08).

The Price table has a per-minute price for ElevenLabs voice, dated like the rest, and an
Owner can override it for one voice credential. Ending a Call freezes its Voice Cost: its
minutes times the per-minute price in effect then, preferring the override; unknown when no
price is set. The Conversations viewer shows each Call's minutes and Voice Cost apart from its
replies' Cost; the daily rollups add Voice Cost per Agent Version, and the Agent's KPIs and the
Organisation cost (by Project and by Agent) show it as its own line and in their totals.

Calls are started and ended by a Visitor through the widget API with the fake voice layer;
the rollup Beat task is run as a task. Expected amounts are minutes times the price set in
the test or written in the repo's price table ($0.10 per minute for ElevenLabs).
"""

import asyncio
import json
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.credentials.registry import Provider
from app.pricing import table as price_table
from app.pricing.sync import sync_price_table
from app.pricing.table import PriceFileError, VoicePriceEntry, load_voice_price_file
from tests.conftest import BACKEND_ROOT, TEST_DATABASE_URL, MemberFactory, SignedUpMember
from tests.fakes.clock import ControllableClock
from tests.integration.test_bedrock_credentials import audit_events
from tests.integration.test_call_limits import run_reaper
from tests.integration.test_calls import calling_agent, end_call, started
from tests.integration.test_conversations import listed, opened
from tests.integration.test_embed import conversation_token, settings_path
from tests.integration.test_organisation_cost import org_cost
from tests.integration.test_prices import prices, prices_path
from tests.integration.test_provider_credentials import OPENAI_KEY, added
from tests.integration.test_version_metrics import metrics, roll_up

OVERRIDDEN = "credential.price_overridden"
REPO_VOICE = {"unit": "per minute", "platform": "0.1", "override": None, "effective": "0.1"}


@pytest.fixture
async def visitor(new_client: Any) -> httpx.AsyncClient:
    client: httpx.AsyncClient = await new_client()
    return client


@pytest.fixture
async def custom_voice_table(app: FastAPI) -> AsyncIterator[Any]:
    """Lets a test load its own per-minute voice prices; the repo's are reloaded afterwards."""

    async def load(entries: list[VoicePriceEntry]) -> None:
        async with app.state.engine.begin() as connection:
            await connection.run_sync(sync_price_table, None, entries)

    yield load
    async with app.state.engine.begin() as connection:
        await connection.run_sync(sync_price_table)


def voice_price_path(member: SignedUpMember, credential_id: str) -> str:
    return prices_path(member, credential_id).removesuffix("prices") + "voice-price"


async def override_voice(
    member: SignedUpMember, credential_id: str, per_minute: Any
) -> httpx.Response:
    return await member.client.put(
        voice_price_path(member, credential_id), json={"per_minute": per_minute}
    )


async def a_call(
    visitor: httpx.AsyncClient, agent: dict[str, Any], clock: ControllableClock, seconds: int
) -> None:
    """A Visitor's Call of ``seconds`` by the platform's clock, ended by the Visitor."""
    token = await conversation_token(visitor, agent["public_id"])
    await started(visitor, agent["public_id"], token)
    clock.advance(timedelta(seconds=seconds))
    response = await end_call(visitor, agent["public_id"], token)
    assert response.status_code == 204, response.text


async def calls_shown(owner: SignedUpMember, agent: dict[str, Any]) -> list[dict[str, Any]]:
    """Every Call of the Agent's Conversations, as the Conversations viewer shows them, oldest
    first."""
    page = await listed(owner, agent["project_id"], agent_id=agent["id"], page_size=100)
    found = [
        call
        for row in page["items"]
        for call in (await opened(owner, agent["project_id"], row["id"]))["calls"]
    ]
    return sorted(found, key=lambda call: call["started_at"])


def settings(owner: SignedUpMember, agent: dict[str, Any]) -> str:
    return settings_path(owner, agent["project_id"], agent["id"])


async def agent_settings(owner: SignedUpMember, agent: dict[str, Any]) -> dict[str, Any]:
    """The Agent's Operational Settings, which name its voice credential."""
    response = await owner.client.get(settings(owner, agent))
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def cost_of(call: dict[str, Any]) -> Decimal | None:
    value = call["voice_cost_usd"]
    return None if value is None else Decimal(value)


# The per-minute price and its override


async def test_a_voice_credential_shows_the_platform_per_minute_price(
    owner: SignedUpMember,
) -> None:
    agent_less = await added(owner, provider="elevenlabs", api_key="sk-voice-cost-0000")
    chat = await added(owner, provider="openai", api_key=OPENAI_KEY)

    voice = await prices(owner, agent_less["id"])
    typed = await prices(owner, chat["id"])

    assert (voice["models"], voice["voice"]) == ([], REPO_VOICE)
    assert typed["voice"] is None
    assert load_voice_price_file() == (
        VoicePriceEntry(Provider.ELEVENLABS, datetime(2025, 6, 1, tzinfo=UTC), Decimal("0.10")),
    )


async def test_the_per_minute_price_in_effect_now_is_shown(
    owner: SignedUpMember, clock: ControllableClock, custom_voice_table: Any
) -> None:
    credential = await added(owner, provider="elevenlabs", api_key="sk-voice-cost-0000")
    await custom_voice_table(
        [
            VoicePriceEntry(Provider.ELEVENLABS, datetime(2025, 1, 1, tzinfo=UTC), Decimal("0.12")),
            VoicePriceEntry(
                Provider.ELEVENLABS, datetime(2026, 12, 1, tzinfo=UTC), Decimal("0.09")
            ),
        ]
    )

    before = (await prices(owner, credential["id"]))["voice"]
    clock.advance(datetime(2026, 12, 1, tzinfo=UTC) - clock.now())
    after = (await prices(owner, credential["id"]))["voice"]
    await custom_voice_table([])
    unpriced = (await prices(owner, credential["id"]))["voice"]

    assert (before["platform"], after["platform"]) == ("0.12", "0.09")
    assert unpriced == {"unit": "per minute", "platform": None, "override": None, "effective": None}


async def test_an_owner_overrides_the_per_minute_price_and_it_is_audited(
    owner: SignedUpMember,
) -> None:
    credential = await added(owner, provider="elevenlabs", api_key="sk-voice-cost-0000")

    response = await override_voice(owner, credential["id"], "0.075")
    again = await override_voice(owner, credential["id"], 0.075)
    shown = (await prices(owner, credential["id"]))["voice"]
    cleared = await override_voice(owner, credential["id"], None)

    assert response.status_code == again.status_code == cleared.status_code == 200
    expected = {"unit": "per minute", "platform": "0.1", "override": "0.075", "effective": "0.075"}
    assert response.json() == shown == expected
    assert cleared.json() == REPO_VOICE
    # Saving the same price again records nothing.
    events = await audit_events(owner, OVERRIDDEN)
    assert [(e["before"], e["after"]) for e in events] == [
        (
            {"voice": "per minute", "per_minute": "0.075"},
            {"voice": "per minute", "per_minute": None},
        ),
        (
            {"voice": "per minute", "per_minute": None},
            {"voice": "per minute", "per_minute": "0.075"},
        ),
    ]
    assert {e["target"]["id"] for e in events} == {credential["id"]}


async def test_only_owners_override_the_per_minute_price_of_a_credential_that_carries_calls(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    voice = await added(owner, provider="elevenlabs", api_key="sk-voice-cost-0000")
    chat = await added(owner, provider="openai", api_key=OPENAI_KEY)

    by_editor = await override_voice(editor, voice["id"], "0.05")
    on_chat = await override_voice(owner, chat["id"], "0.05")
    unknown = await override_voice(owner, "00000000-0000-0000-0000-000000000000", "0.05")
    negative = await override_voice(owner, voice["id"], "-0.01")
    too_fine = await override_voice(owner, voice["id"], "0.0000001")

    assert by_editor.status_code == 403
    assert on_chat.status_code == 422
    assert "carry Calls" in on_chat.json()["detail"]
    assert unknown.status_code == 404
    assert negative.status_code == too_fine.status_code == 422
    assert (await prices(editor, voice["id"]))["voice"] == REPO_VOICE


# Ending a Call freezes its Voice Cost


async def test_ending_a_call_freezes_its_minutes_times_the_price_preferring_the_override(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent = await calling_agent(app, owner)
    credential_id = (await agent_settings(owner, agent))["call_credential_id"]

    await a_call(visitor, agent, clock, 61)
    assert (await override_voice(owner, credential_id, "0.05")).status_code == 200
    await a_call(visitor, agent, clock, 150)

    first, second = await calls_shown(owner, agent)
    # 2 minutes x $0.10, frozen: the override set afterwards doesn't change it.
    assert (first["minutes"], cost_of(first), first["end_reason"]) == (2, Decimal("0.2"), "visitor")
    # 3 minutes x $0.05 (the override).
    assert (second["minutes"], cost_of(second)) == (3, Decimal("0.15"))
    assert second["ended_at"] is not None


async def test_a_call_is_costed_at_the_price_in_effect_when_it_ended(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    custom_voice_table: Any,
) -> None:
    agent = await calling_agent(app, owner)
    clock.advance(datetime(2026, 11, 30, 23, 59, tzinfo=UTC) - clock.now())
    await custom_voice_table(
        [
            VoicePriceEntry(Provider.ELEVENLABS, datetime(2025, 1, 1, tzinfo=UTC), Decimal("0.10")),
            VoicePriceEntry(
                Provider.ELEVENLABS, datetime(2026, 12, 1, tzinfo=UTC), Decimal("0.20")
            ),
        ]
    )

    # Starts before the new price and ends after it took effect: 2 minutes x $0.20.
    await a_call(visitor, agent, clock, 90)

    (call,) = await calls_shown(owner, agent)
    assert (call["minutes"], cost_of(call)) == (2, Decimal("0.4"))


async def test_without_a_price_the_voice_cost_is_unknown_and_an_open_call_has_none_yet(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
    custom_voice_table: Any,
) -> None:
    agent = await calling_agent(app, owner)
    await custom_voice_table([])
    token = await conversation_token(visitor, agent["public_id"])
    await started(visitor, agent["public_id"], token)

    (open_call,) = await calls_shown(owner, agent)
    # Ended by Beat when it goes silent.
    clock.advance(timedelta(seconds=61))
    await run_reaper()
    (ended,) = await calls_shown(owner, agent)

    assert (open_call["ended_at"], open_call["minutes"], open_call["voice_cost_usd"]) == (
        None,
        None,
        None,
    )
    assert (ended["minutes"], ended["voice_cost_usd"], ended["end_reason"]) == (1, None, "silence")


async def test_a_call_whose_voice_credential_was_deleted_is_costed_at_the_platform_price(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent = await calling_agent(app, owner)
    credential_id = (await agent_settings(owner, agent))["call_credential_id"]
    assert (await override_voice(owner, credential_id, "0.01")).status_code == 200
    token = await conversation_token(visitor, agent["public_id"])
    await started(visitor, agent["public_id"], token)
    response = await owner.client.patch(settings(owner, agent), json={"calls_enabled": False})
    assert response.status_code == 200, response.text
    deleted = await owner.client.delete(prices_path(owner, credential_id).removesuffix("/prices"))
    assert deleted.status_code == 204, deleted.text

    clock.advance(timedelta(seconds=30))
    await end_call(visitor, agent["public_id"], token)

    (call,) = await calls_shown(owner, agent)
    # 1 minute at ElevenLabs' platform price: the Agent's voice credential (and its override)
    # went while the Call was open.
    assert cost_of(call) == Decimal("0.1")


# Voice Cost in the Agent's KPIs and the Organisation cost


async def test_voice_cost_is_its_own_line_in_organisation_cost_and_in_its_totals(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent = await calling_agent(app, owner)
    await a_call(visitor, agent, clock, 61)
    await a_call(visitor, agent, clock, 30)

    by_project = await org_cost(owner, start="2026-11-05", end="2026-11-05", group_by="project")
    by_agent = await org_cost(owner, start="2026-11-05", end="2026-11-05", group_by="agent")

    # 2 + 1 minutes x $0.10; the Calls took no turn, so no reply cost anything.
    voice = Decimal("0.3")
    for body in (by_project, by_agent):
        (row,) = body["rows"]
        assert (Decimal(row["voice_usd"]), Decimal(row["visitor_usd"])) == (voice, Decimal(0))
        assert Decimal(row["total_usd"]) == voice
        assert Decimal(body["total"]["voice_usd"]) == Decimal(body["total"]["total_usd"]) == voice
    assert by_agent["rows"][0]["agent_id"] == agent["id"]
    assert by_project["rows"][0]["project_id"] == agent["project_id"]


async def test_the_rollup_keeps_voice_cost_per_version_for_days_gone_by(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    agent = await calling_agent(app, owner)
    await a_call(visitor, agent, clock, 61)
    # The next day, Beat finalises the day: a day with Calls but no replies.
    clock.advance(datetime(2026, 11, 6, 1, tzinfo=UTC) - clock.now())
    await roll_up(clock.now())
    await a_call(visitor, agent, clock, 30)

    yesterday = await org_cost(owner, start="2026-11-05", end="2026-11-05", group_by="agent")
    both = await org_cost(owner, start="2026-11-05", end="2026-11-06", group_by="agent")
    kpis = (await metrics(owner, agent, start="2026-11-05", end="2026-11-06"))["versions"]

    assert Decimal(yesterday["total"]["voice_usd"]) == Decimal("0.2")
    assert Decimal(both["total"]["voice_usd"]) == Decimal("0.3")
    (version,) = kpis
    assert version["number"] == 1
    assert Decimal(version["cost"]["voice_usd"]) == Decimal("0.3")
    assert Decimal(version["cost"]["total_usd"]) == Decimal("0.3")


# Loading the per-minute prices on migrate


@pytest.fixture
def price_file(tmp_path: Path, settings_env: pytest.MonkeyPatch) -> Iterator[Path]:
    """Points the price table at a file the test writes; the repo's is reloaded afterwards."""
    repo_file = price_table.PRICE_FILE
    path = tmp_path / "price_table.json"
    price_table.PRICE_FILE = path
    try:
        yield path
    finally:
        price_table.PRICE_FILE = repo_file
        _migrate("head")


def _write_prices(path: Path, *voice: dict[str, str]) -> None:
    path.write_text(json.dumps({"prices": [], "voice_prices": list(voice)}))


def _voice(effective_from: str, per_minute: str, provider: str = "elevenlabs") -> dict[str, str]:
    return {"provider": provider, "effective_from": effective_from, "per_minute": per_minute}


def _loaded_voice() -> list[tuple[str, str, str]]:
    async def query() -> list[tuple[str, str, str]]:
        engine = create_async_engine(TEST_DATABASE_URL)
        try:
            async with engine.connect() as connection:
                rows = await connection.execute(
                    text(
                        "SELECT provider, effective_from::date::text, per_minute::text"
                        " FROM voice_prices ORDER BY provider, effective_from"
                    )
                )
                return [(r[0], r[1], r[2]) for r in rows]
        finally:
            await engine.dispose()

    return asyncio.run(query())


def _migrate(revision: str) -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.attributes["configure_logger"] = False
    if revision == "head":
        command.upgrade(config, revision)
    else:
        command.downgrade(config, revision)


def test_migrating_loads_the_per_minute_prices_from_the_repo(
    settings_env: pytest.MonkeyPatch, price_file: Path
) -> None:
    _write_prices(price_file, _voice("2025-01-01", "0.12"), _voice("2026-01-01", "0.09"))
    _migrate("head")
    assert _loaded_voice() == [
        ("elevenlabs", "2025-01-01", "0.120000"),
        ("elevenlabs", "2026-01-01", "0.090000"),
    ]

    # Migrating down to before voice prices still loads the model prices, then back up loads
    # the voice prices again.
    _migrate("0061_call_limits")
    _migrate("head")
    assert _loaded_voice() == [
        ("elevenlabs", "2025-01-01", "0.120000"),
        ("elevenlabs", "2026-01-01", "0.090000"),
    ]

    # A file with no voice prices empties the table.
    price_file.write_text(json.dumps({"prices": []}))
    _migrate("head")
    assert _loaded_voice() == []


@pytest.mark.parametrize(
    ("entries", "problem"),
    [
        ([_voice("2025-01-01", "-0.1")], "negative"),
        ([_voice("2025-01-01", "NaN")], "negative"),
        ([_voice("2025-13-01", "0.1")], "Malformed"),
        ([_voice("2025-01-01", "lots")], "Malformed"),
        ([_voice("2025-01-01", "0.1", provider="acme")], "Malformed"),
        ([{"provider": "elevenlabs", "effective_from": "2025-01-01"}], "per_minute"),
        ([_voice("2025-01-01", "0.1"), _voice("2025-01-01", "0.2")], "Duplicate"),
    ],
)
def test_a_malformed_voice_price_fails_the_migration_and_loads_nothing(
    settings_env: pytest.MonkeyPatch,
    price_file: Path,
    entries: list[dict[str, str]],
    problem: str,
) -> None:
    _write_prices(price_file, _voice("2025-01-01", "0.07"))
    _migrate("head")
    _write_prices(price_file, *entries)

    with pytest.raises(PriceFileError, match=problem):
        _migrate("head")

    assert _loaded_voice() == [("elevenlabs", "2025-01-01", "0.070000")]
