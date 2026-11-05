"""API seam: the platform price table, per-credential price overrides, and the cost that
cost reporting reads.

Credentials are added through the API with the fake verifier. Prices, overrides and Audit
Events are observed through the API; the cost through ``credential_cost``, the entry point
spec 07's cost reporting calls. Expected prices are the repo's price table as written
(``app/pricing/price_table.json``) or worked by hand.
"""

import asyncio
import itertools
import json
import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.credentials.models import ProviderCredential
from app.credentials.registry import Provider
from app.pricing import table as price_table
from app.pricing.service import credential_cost
from app.pricing.sync import sync_price_table
from app.pricing.table import PriceEntry, PriceFileError, TokenUsage
from tests.conftest import BACKEND_ROOT, TEST_DATABASE_URL, MemberFactory, SignedUpMember
from tests.fakes.clock import ControllableClock
from tests.integration.test_provider_credentials import (
    ANTHROPIC_KEY,
    OPENAI_KEY,
    VOYAGE_KEY,
    added,
    audit_events,
    credentials_path,
)

OVERRIDDEN = "credential.price_overridden"
SONNET = {"model": "claude-sonnet-4-5", "model_name": "Claude Sonnet 4.5"}
SONNET_PLATFORM = {"input": "3", "output": "15", "cached_input": "0.3"}
NO_OVERRIDE = {"input": None, "output": None, "cached_input": None}


def prices_path(member: SignedUpMember, credential_id: str) -> str:
    return credentials_path(member.organisation_id, credential_id, "prices")


async def prices(member: SignedUpMember, credential_id: str) -> Any:
    response = await member.client.get(prices_path(member, credential_id))
    assert response.status_code == 200, response.text
    return response.json()


async def model_prices(member: SignedUpMember, credential_id: str, model: str) -> Any:
    (row,) = [m for m in (await prices(member, credential_id))["models"] if m["model"] == model]
    return row


async def override(member: SignedUpMember, credential_id: str, **body: Any) -> Any:
    return await member.client.put(prices_path(member, credential_id), json=body)


# The platform price table


async def test_a_credentials_models_show_the_platform_price_table(owner: SignedUpMember) -> None:
    claude = await added(owner, provider="anthropic", api_key=ANTHROPIC_KEY)

    listed = await prices(owner, claude["id"])

    assert listed["credential_id"] == claude["id"]
    assert listed["currency"] == "USD"
    assert listed["unit"] == "per million tokens"
    assert listed["models"] == [
        {
            "model": "claude-opus-4-1",
            "model_name": "Claude Opus 4.1",
            "capability": "chat",
            "platform": {"input": "15", "output": "75", "cached_input": "1.5"},
            "override": None,
            "effective": {"input": "15", "output": "75", "cached_input": "1.5"},
        },
        {
            **SONNET,
            "capability": "chat",
            "platform": SONNET_PLATFORM,
            "override": None,
            "effective": SONNET_PLATFORM,
        },
        {
            "model": "claude-haiku-4-5",
            "model_name": "Claude Haiku 4.5",
            "capability": "chat",
            "platform": {"input": "1", "output": "5", "cached_input": "0.1"},
            "override": None,
            "effective": {"input": "1", "output": "5", "cached_input": "0.1"},
        },
    ]


async def test_every_capability_the_credential_has_is_priced(owner: SignedUpMember) -> None:
    openai = await added(owner, provider="openai", api_key=OPENAI_KEY)
    embeddings_only = await added(
        owner, name="Search", provider="openai", api_key=OPENAI_KEY, capabilities=["embeddings"]
    )

    listed = (await prices(owner, openai["id"]))["models"]
    limited = (await prices(owner, embeddings_only["id"]))["models"]

    assert [(m["model"], m["capability"]) for m in listed] == [
        ("gpt-4.1", "chat"),
        ("gpt-4.1-mini", "chat"),
        ("gpt-4o-mini", "chat"),
        ("text-embedding-3-small", "embeddings"),
        ("text-embedding-3-large", "embeddings"),
    ]
    assert listed[3]["platform"] == {"input": "0.02", "output": "0", "cached_input": "0.02"}
    assert [m["model"] for m in limited] == ["text-embedding-3-small", "text-embedding-3-large"]


@pytest.fixture
async def custom_table(app: FastAPI) -> AsyncIterator[Any]:
    """Lets a test load its own platform price table; the repo's is reloaded afterwards."""

    async def load(entries: list[PriceEntry]) -> None:
        async with app.state.engine.begin() as connection:
            await connection.run_sync(sync_price_table, entries)

    yield load
    async with app.state.engine.begin() as connection:
        await connection.run_sync(sync_price_table)


def _at(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=UTC)


async def test_the_price_in_effect_now_is_shown(
    owner: SignedUpMember, clock: ControllableClock, custom_table: Any
) -> None:
    voyage = await added(owner, provider="voyage", api_key=VOYAGE_KEY)
    d = Decimal
    await custom_table(
        [
            PriceEntry(Provider.VOYAGE, "voyage-3.5", _at(2025, 1, 1), d("0.06"), d(0), d("0.06")),
            PriceEntry(Provider.VOYAGE, "voyage-3.5", _at(2026, 12, 1), d("0.05"), d(0), d("0.05")),
            # Another provider's price for the same model ID doesn't apply.
            PriceEntry(Provider.OPENAI, "voyage-3.5", _at(2025, 1, 1), d(9), d(9), d(9)),
        ]
    )

    before = await model_prices(owner, voyage["id"], "voyage-3.5")
    clock.advance(datetime(2026, 12, 1, tzinfo=UTC) - clock.now())
    after = await model_prices(owner, voyage["id"], "voyage-3.5")
    unpriced = await model_prices(owner, voyage["id"], "voyage-3.5-lite")

    assert before["platform"] == {"input": "0.06", "output": "0", "cached_input": "0.06"}
    assert after["platform"] == {"input": "0.05", "output": "0", "cached_input": "0.05"}
    # A model the table doesn't price has no platform price, and so no effective price.
    assert unpriced["platform"] is None
    assert unpriced["effective"] == NO_OVERRIDE


# Overrides


async def test_an_owner_overrides_a_models_prices_for_one_credential(
    owner: SignedUpMember,
) -> None:
    claude = await added(owner, provider="anthropic", api_key=ANTHROPIC_KEY)
    other = await added(owner, name="Other Claude", provider="anthropic", api_key=ANTHROPIC_KEY)

    response = await override(
        owner, claude["id"], model="claude-sonnet-4-5", input="2.5", output=12, cached_input="0.25"
    )

    negotiated = {"input": "2.5", "output": "12", "cached_input": "0.25"}
    assert response.status_code == 200, response.text
    assert response.json() == {
        **SONNET,
        "capability": "chat",
        "platform": SONNET_PLATFORM,
        "override": negotiated,
        "effective": negotiated,
    }
    assert await model_prices(owner, claude["id"], "claude-sonnet-4-5") == response.json()
    # The override is the credential's own: the same model through another is unchanged.
    assert (await model_prices(owner, other["id"], "claude-sonnet-4-5"))["override"] is None


async def test_a_price_left_out_keeps_the_platform_price(owner: SignedUpMember) -> None:
    claude = await added(owner, provider="anthropic", api_key=ANTHROPIC_KEY)

    response = await override(owner, claude["id"], model="claude-sonnet-4-5", output="10.125")

    assert response.status_code == 200, response.text
    assert response.json()["override"] == {"input": None, "output": "10.125", "cached_input": None}
    assert response.json()["effective"] == {"input": "3", "output": "10.125", "cached_input": "0.3"}


async def test_an_override_is_cleared_by_leaving_every_price_out(owner: SignedUpMember) -> None:
    claude = await added(owner, provider="anthropic", api_key=ANTHROPIC_KEY)
    await override(owner, claude["id"], model="claude-sonnet-4-5", input="1")

    response = await override(owner, claude["id"], model="claude-sonnet-4-5")

    assert response.status_code == 200, response.text
    assert response.json()["override"] is None
    assert response.json()["effective"] == SONNET_PLATFORM
    assert (await model_prices(owner, claude["id"], "claude-sonnet-4-5"))["override"] is None


async def test_overrides_are_audited(owner: SignedUpMember) -> None:
    claude = await added(owner, provider="anthropic", api_key=ANTHROPIC_KEY)

    await override(owner, claude["id"], model="claude-sonnet-4-5", input="2", output="10")
    await override(owner, claude["id"], model="claude-sonnet-4-5", input="2", output="9")
    await override(owner, claude["id"], model="claude-sonnet-4-5")

    events = await audit_events(owner, OVERRIDDEN)
    assert [(e["before"], e["after"]) for e in reversed(events)] == [
        (
            {"model": "claude-sonnet-4-5", **NO_OVERRIDE},
            {"model": "claude-sonnet-4-5", "input": "2", "output": "10", "cached_input": None},
        ),
        (
            {"model": "claude-sonnet-4-5", "input": "2", "output": "10", "cached_input": None},
            {"model": "claude-sonnet-4-5", "input": "2", "output": "9", "cached_input": None},
        ),
        (
            {"model": "claude-sonnet-4-5", "input": "2", "output": "9", "cached_input": None},
            {"model": "claude-sonnet-4-5", **NO_OVERRIDE},
        ),
    ]
    for event in events:
        assert event["actor"]["id"] == owner.member_id
        assert event["target"] == {"type": "provider_credential", "id": claude["id"]}


async def test_saving_the_same_prices_again_records_nothing(owner: SignedUpMember) -> None:
    claude = await added(owner, provider="anthropic", api_key=ANTHROPIC_KEY)

    await override(owner, claude["id"], model="claude-sonnet-4-5", input="2")
    # The same value written differently is the same price.
    again = await override(owner, claude["id"], model="claude-sonnet-4-5", input="2.000")
    # Clearing an override that doesn't exist changes nothing either.
    nothing = await override(owner, claude["id"], model="claude-haiku-4-5")

    assert again.status_code == nothing.status_code == 200
    assert again.json()["override"] == {"input": "2", "output": None, "cached_input": None}
    assert len(await audit_events(owner, OVERRIDDEN)) == 1


@pytest.mark.parametrize(
    ("provider", "key", "capabilities", "model"),
    [
        # Not a model of this provider.
        ("anthropic", ANTHROPIC_KEY, None, "gpt-4.1"),
        ("anthropic", ANTHROPIC_KEY, None, "claude-unknown"),
        # A model of the provider for a capability the credential wasn't given.
        ("openai", OPENAI_KEY, ["chat"], "text-embedding-3-small"),
    ],
)
async def test_only_a_model_the_credential_offers_can_be_overridden(
    owner: SignedUpMember, provider: str, key: str, capabilities: list[str] | None, model: str
) -> None:
    credential = await added(
        owner,
        provider=provider,
        api_key=key,
        **({} if capabilities is None else {"capabilities": capabilities}),
    )

    response = await override(owner, credential["id"], model=model, input="1")

    assert response.status_code == 422
    assert response.json() == {"detail": f"This credential doesn't offer {model}."}
    assert await audit_events(owner, OVERRIDDEN) == []


@pytest.mark.parametrize("price", ["-1", "0.0000001", "1000000", "NaN", "Infinity", "lots", True])
async def test_a_price_must_be_a_plain_amount(owner: SignedUpMember, price: Any) -> None:
    claude = await added(owner, provider="anthropic", api_key=ANTHROPIC_KEY)

    response = await override(owner, claude["id"], model="claude-sonnet-4-5", output=price)

    assert response.status_code == 422
    assert (await model_prices(owner, claude["id"], "claude-sonnet-4-5"))["override"] is None


async def test_a_free_price_can_be_set(owner: SignedUpMember) -> None:
    claude = await added(owner, provider="anthropic", api_key=ANTHROPIC_KEY)

    response = await override(owner, claude["id"], model="claude-haiku-4-5", cached_input="0")

    assert response.json()["effective"] == {"input": "1", "output": "5", "cached_input": "0"}


async def test_editors_see_prices_but_cannot_override_them(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    claude = await added(owner, provider="anthropic", api_key=ANTHROPIC_KEY)
    await override(owner, claude["id"], model="claude-sonnet-4-5", input="2")
    editor = await member_factory(owner, "editor")

    seen = await model_prices(editor, claude["id"], "claude-sonnet-4-5")
    refused = await override(editor, claude["id"], model="claude-sonnet-4-5", input="1")

    assert seen["override"] == {"input": "2", "output": None, "cached_input": None}
    assert refused.status_code == 403
    assert (await model_prices(owner, claude["id"], "claude-sonnet-4-5"))["override"][
        "input"
    ] == "2"


async def test_an_unknown_credential_has_no_prices(owner: SignedUpMember) -> None:
    unknown = str(uuid.uuid4())

    read = await owner.client.get(prices_path(owner, unknown))
    written = await override(owner, unknown, model="claude-sonnet-4-5", input="1")

    assert read.status_code == written.status_code == 404
    assert read.json() == written.json() == {"detail": "Not found"}


async def test_a_deleted_credentials_overrides_go_with_it(
    owner: SignedUpMember, app: FastAPI
) -> None:
    claude = await added(owner, provider="anthropic", api_key=ANTHROPIC_KEY)
    await override(owner, claude["id"], model="claude-sonnet-4-5", input="1")

    deleted = await owner.client.delete(credentials_path(owner.organisation_id, claude["id"]))

    assert deleted.status_code == 204
    async with app.state.engine.connect() as connection:
        left = await connection.scalar(
            text("SELECT count(*) FROM price_overrides WHERE credential_id = :id"),
            {"id": claude["id"]},
        )
    assert left == 0


async def test_concurrent_overrides_of_one_model_are_applied_one_after_the_other(
    owner: SignedUpMember,
) -> None:
    claude = await added(owner, provider="anthropic", api_key=ANTHROPIC_KEY)

    responses = await asyncio.gather(
        *(
            override(owner, claude["id"], model="claude-sonnet-4-5", input=str(n))
            for n in range(1, 6)
        )
    )

    assert {r.status_code for r in responses} == {200}
    events = list(reversed(await audit_events(owner, OVERRIDDEN)))
    # Each change starts from the one before it: no lost update.
    assert events[0]["before"]["input"] is None
    for previous, following in itertools.pairwise(events):
        assert following["before"] == previous["after"]
    final = await model_prices(owner, claude["id"], "claude-sonnet-4-5")
    assert final["override"]["input"] == events[-1]["after"]["input"]


# The cost cost reporting reads


async def _credential(app: FastAPI, credential_id: str) -> ProviderCredential:
    async with app.state.sessionmaker() as session:
        credential: ProviderCredential | None = await session.get(
            ProviderCredential, uuid.UUID(credential_id)
        )
        assert credential is not None
        return credential


async def test_cost_reporting_uses_the_credentials_overrides_and_the_platform_price(
    owner: SignedUpMember, app: FastAPI
) -> None:
    claude = await added(owner, provider="anthropic", api_key=ANTHROPIC_KEY)
    await override(owner, claude["id"], model="claude-sonnet-4-5", output="10")
    usage = TokenUsage(input_tokens=2_000_000, output_tokens=100_000, cached_input_tokens=1_000_000)
    credential = await _credential(app, claude["id"])
    now = datetime(2026, 11, 5, tzinfo=UTC)

    async with app.state.sessionmaker() as session:
        sonnet = await credential_cost(session, credential, "claude-sonnet-4-5", usage, now)
        haiku = await credential_cost(session, credential, "claude-haiku-4-5", usage, now)
        before_haiku = await credential_cost(
            session, credential, "claude-haiku-4-5", usage, datetime(2025, 10, 14, tzinfo=UTC)
        )

    # 2M x $3 + 0.1M x $10 (override) + 1M x $0.30
    assert sonnet == Decimal("7.3")
    # 2M x $1 + 0.1M x $5 + 1M x $0.10
    assert haiku == Decimal("2.6")
    # Claude Haiku 4.5's platform price starts on 15 October 2025.
    assert before_haiku is None


# Loading the table on migrate


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
        _upgrade()


def _upgrade() -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.attributes["configure_logger"] = False
    command.upgrade(config, "head")


def _loaded() -> list[tuple[str, str, str, str]]:
    async def query() -> list[tuple[str, str, str, str]]:
        engine = create_async_engine(TEST_DATABASE_URL)
        try:
            async with engine.connect() as connection:
                rows = await connection.execute(
                    text(
                        "SELECT provider, model, effective_from::date::text, output::text"
                        " FROM model_prices ORDER BY provider, model, effective_from"
                    )
                )
                return [(r[0], r[1], r[2], r[3]) for r in rows]
        finally:
            await engine.dispose()

    return asyncio.run(query())


def _write(path: Path, *entries: dict[str, str]) -> None:
    path.write_text(json.dumps({"prices": list(entries)}))


def _entry(model: str, effective_from: str, output: str) -> dict[str, str]:
    return {
        "provider": "anthropic",
        "model": model,
        "effective_from": effective_from,
        "input": "1",
        "output": output,
        "cached_input": "0.1",
    }


def test_migrating_loads_the_price_table_from_the_repo(
    settings_env: pytest.MonkeyPatch, price_file: Path
) -> None:
    _write(price_file, _entry("model-a", "2025-01-01", "5"), _entry("model-a", "2026-01-01", "4"))
    _upgrade()
    assert _loaded() == [
        ("anthropic", "model-a", "2025-01-01", "5.000000"),
        ("anthropic", "model-a", "2026-01-01", "4.000000"),
    ]

    # Editing the file and migrating again replaces the table, even with no new migration.
    _write(price_file, _entry("model-b", "2026-02-01", "3"))
    _upgrade()
    assert _loaded() == [("anthropic", "model-b", "2026-02-01", "3.000000")]

    # An empty table empties it.
    _write(price_file)
    _upgrade()
    assert _loaded() == []


def test_the_repos_price_table_is_what_migrating_loads(settings_env: pytest.MonkeyPatch) -> None:
    _upgrade()

    written = sorted(
        (str(e.provider), e.model, e.effective_from.date().isoformat(), f"{e.output:.6f}")
        for e in price_table.load_price_file()
    )
    assert _loaded() == written
    assert ("anthropic", "claude-sonnet-4-5", "2025-09-29", "15.000000") in written


@pytest.mark.parametrize(
    ("entries", "problem"),
    [
        ([_entry("model-a", "2025-01-01", "-1")], "negative"),
        ([_entry("model-a", "2025-01-01", "NaN")], "negative"),
        ([_entry("model-a", "2025-13-01", "1")], "Malformed"),
        ([_entry("model-a", "2025-01-01", "lots")], "Malformed"),
        ([{**_entry("model-a", "2025-01-01", "1"), "provider": "acme"}], "Malformed"),
        (
            [{k: v for k, v in _entry("model-a", "2025-01-01", "1").items() if k != "input"}],
            "input",
        ),
        ([{**_entry("model-a", "2025-01-01", "1"), "model": ""}], "no model"),
        ([_entry("model-a", "2025-01-01", "1"), _entry("model-a", "2025-01-01", "2")], "Duplicate"),
    ],
)
def test_a_malformed_price_table_fails_the_migration_and_loads_nothing(
    settings_env: pytest.MonkeyPatch,
    price_file: Path,
    entries: list[dict[str, str]],
    problem: str,
) -> None:
    _write(price_file, _entry("model-ok", "2025-01-01", "7"))
    _upgrade()
    _write(price_file, *entries)

    with pytest.raises(PriceFileError, match=problem):
        _upgrade()

    assert _loaded() == [("anthropic", "model-ok", "2025-01-01", "7.000000")]


def test_the_repos_price_table_prices_only_models_in_the_capability_registry() -> None:
    from app.credentials.registry import PROVIDERS

    offered = {
        (provider, model.id)
        for provider, spec in PROVIDERS.items()
        for models in spec.models.values()
        for model in models
    }
    priced = {(e.provider, e.model) for e in price_table.load_price_file()}

    assert priced <= offered
    # Cohere Rerank on Bedrock is priced per search, not per token: Owners override it.
    assert offered - priced == {(Provider.BEDROCK, "cohere.rerank-v3-5:0")}
