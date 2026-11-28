"""The platform price table and the pure cost functions.

Prices are US dollars per million tokens, for input, output and cached input tokens. The
platform's prices live in ``price_table.json`` beside this module, keyed by provider and
model, each with the date it took effect; migrating loads them into the ``model_prices``
table. An Owner can override any of the three prices per credential and model.

The voice layer is priced per minute instead (``voice_prices`` in the same file, loaded into
the ``voice_prices`` table), by provider and dated like the rest; an Owner can override a voice
credential's per-minute price. ``voice_cost`` is the one place a Call's Voice Cost is worked out.

``cost`` is the one place a cost is worked out. It reads nothing: callers pass the
credential's pricing and the price table, so cost reporting (spec 07) can call it with prices
loaded once.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.credentials.registry import Provider

PRICE_FILE = Path(__file__).with_name("price_table.json")
MILLION = Decimal(1_000_000)


@dataclass(frozen=True)
class PriceEntry:
    """One row of the platform price table: a model's prices from ``effective_from`` on."""

    provider: Provider
    model: str
    effective_from: datetime
    input: Decimal
    output: Decimal
    cached_input: Decimal


@dataclass(frozen=True)
class Override:
    """An Owner's prices for one model of one credential. ``None`` keeps the platform price."""

    input: Decimal | None = None
    output: Decimal | None = None
    cached_input: Decimal | None = None


@dataclass(frozen=True)
class CredentialPricing:
    """What a credential's costs depend on: its provider, and its overrides by model ID."""

    provider: Provider
    overrides: Mapping[str, Override] = field(default_factory=dict)


@dataclass(frozen=True)
class TokenUsage:
    """Token counts for one model call. ``input_tokens`` excludes the cached ones."""

    input_tokens: int
    output_tokens: int
    cached_input_tokens: int = 0


@dataclass(frozen=True)
class Prices:
    """The prices that apply, each ``None`` when neither the table nor an override has one."""

    input: Decimal | None
    output: Decimal | None
    cached_input: Decimal | None


def platform_price(
    provider: Provider, model: str, at: datetime, table: Sequence[PriceEntry]
) -> PriceEntry | None:
    """The table's entry for the model in effect at ``at``: the latest that started by then."""
    started = [
        entry
        for entry in table
        if entry.provider == provider and entry.model == model and entry.effective_from <= at
    ]
    return max(started, key=lambda entry: entry.effective_from, default=None)


def prices(
    pricing: CredentialPricing, model: str, at: datetime, table: Sequence[PriceEntry]
) -> Prices:
    """The prices a credential pays for a model at ``at``: each override, else the table's."""
    platform = platform_price(pricing.provider, model, at, table)
    override = pricing.overrides.get(model, Override())

    def pick(overridden: Decimal | None, name: str) -> Decimal | None:
        if overridden is not None:
            return overridden
        return None if platform is None else getattr(platform, name)

    return Prices(
        input=pick(override.input, "input"),
        output=pick(override.output, "output"),
        cached_input=pick(override.cached_input, "cached_input"),
    )


def cost(
    pricing: CredentialPricing,
    model: str,
    usage: TokenUsage,
    at: datetime,
    table: Sequence[PriceEntry],
) -> Decimal | None:
    """What ``usage`` of ``model`` through the credential cost at ``at``, in US dollars.

    Overrides take precedence over the platform price; the platform price is the one in
    effect at ``at``. ``None`` when tokens were used at a price nobody has set.
    """
    applied = prices(pricing, model, at, table)
    total = Decimal(0)
    for tokens, price in (
        (usage.input_tokens, applied.input),
        (usage.output_tokens, applied.output),
        (usage.cached_input_tokens, applied.cached_input),
    ):
        if tokens == 0:
            continue
        if price is None:
            return None
        total += tokens * price
    return total / MILLION


@dataclass(frozen=True)
class VoicePriceEntry:
    """One row of the platform's voice prices: a provider's US dollars per Call minute from
    ``effective_from`` on."""

    provider: Provider
    effective_from: datetime
    per_minute: Decimal


def voice_platform_price(
    provider: Provider, at: datetime, table: Sequence[VoicePriceEntry]
) -> VoicePriceEntry | None:
    """The provider's per-minute price in effect at ``at``: the latest that started by then."""
    started = [e for e in table if e.provider == provider and e.effective_from <= at]
    return max(started, key=lambda entry: entry.effective_from, default=None)


def voice_per_minute(
    provider: Provider,
    override: Decimal | None,
    at: datetime,
    table: Sequence[VoicePriceEntry],
) -> Decimal | None:
    """The per-minute price a voice credential pays at ``at``: its override, else the table's."""
    if override is not None:
        return override
    platform = voice_platform_price(provider, at, table)
    return None if platform is None else platform.per_minute


def voice_cost(
    provider: Provider,
    minutes: int,
    override: Decimal | None,
    at: datetime,
    table: Sequence[VoicePriceEntry],
) -> Decimal | None:
    """A Call's Voice Cost in US dollars: its minutes times the per-minute price in effect when
    it ended (``at``), preferring the credential's override. ``None`` when minutes were used at
    a price nobody has set."""
    if minutes == 0:
        return Decimal(0)
    price = voice_per_minute(provider, override, at, table)
    return None if price is None else minutes * price


class PriceFileError(ValueError):
    pass


def _entry(raw: Mapping[str, Any]) -> PriceEntry:
    try:
        provider = Provider(raw["provider"])
        model = raw["model"]
        effective = date.fromisoformat(raw["effective_from"])
        values = [Decimal(raw[name]) for name in ("input", "output", "cached_input")]
    except (KeyError, ValueError, ArithmeticError) as error:
        raise PriceFileError(f"Malformed price entry {dict(raw)!r}: {error!r}") from None
    if not isinstance(model, str) or not model:
        raise PriceFileError(f"Malformed price entry {dict(raw)!r}: no model")
    if any(not value.is_finite() or value < 0 for value in values):
        raise PriceFileError(f"Price entry {dict(raw)!r}: a price is negative or not a number")
    return PriceEntry(provider, model, datetime.combine(effective, time(), tzinfo=UTC), *values)


def _voice_entry(raw: Mapping[str, Any]) -> VoicePriceEntry:
    try:
        provider = Provider(raw["provider"])
        effective = date.fromisoformat(raw["effective_from"])
        per_minute = Decimal(raw["per_minute"])
    except (KeyError, ValueError, ArithmeticError) as error:
        raise PriceFileError(f"Malformed voice price entry {dict(raw)!r}: {error!r}") from None
    if not per_minute.is_finite() or per_minute < 0:
        raise PriceFileError(f"Voice price entry {dict(raw)!r}: negative or not a number")
    return VoicePriceEntry(provider, datetime.combine(effective, time(), tzinfo=UTC), per_minute)


def load_voice_price_file() -> tuple[VoicePriceEntry, ...]:
    """The voice prices as written in the repo (``PRICE_FILE``'s ``voice_prices``, none when
    it has none). Raises ``PriceFileError`` on a malformed or duplicated entry."""
    raws = json.loads(PRICE_FILE.read_text()).get("voice_prices", [])
    entries = tuple(_voice_entry(raw) for raw in raws)
    seen: set[tuple[Provider, datetime]] = set()
    for entry in entries:
        key = (entry.provider, entry.effective_from)
        if key in seen:
            raise PriceFileError(f"Duplicate voice price entry for {entry.provider}")
        seen.add(key)
    return entries


def load_price_file() -> tuple[PriceEntry, ...]:
    """The price table as written in the repo (``PRICE_FILE``). Raises ``PriceFileError`` on a
    malformed or duplicated entry, so a bad edit fails the migration instead of loading half
    a table."""
    entries = tuple(_entry(raw) for raw in json.loads(PRICE_FILE.read_text())["prices"])
    seen: set[tuple[Provider, str, datetime]] = set()
    for entry in entries:
        key = (entry.provider, entry.model, entry.effective_from)
        if key in seen:
            raise PriceFileError(f"Duplicate price entry for {entry.provider} {entry.model}")
        seen.add(key)
    return entries
