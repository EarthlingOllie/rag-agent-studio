"""The pure Voice Cost function: (a Call's minutes, the per-minute price table, the credential's
override, when it ended) -> Voice Cost.

Expected costs are worked by hand from the prices in each test.
"""

from datetime import UTC, datetime
from decimal import Decimal

from app.credentials.registry import Provider
from app.pricing.table import VoicePriceEntry, voice_cost, voice_platform_price

D = Decimal


def at(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=UTC)


TABLE = (
    VoicePriceEntry(Provider.ELEVENLABS, at(2025, 1, 1), D("0.10")),
    VoicePriceEntry(Provider.ELEVENLABS, at(2026, 6, 1), D("0.08")),
)


def test_minutes_times_the_per_minute_price_in_effect_when_the_call_ended() -> None:
    # 7 x $0.10, then from 1 June 2026 7 x $0.08
    assert voice_cost(Provider.ELEVENLABS, 7, None, at(2026, 5, 31), TABLE) == D("0.7")
    assert voice_cost(Provider.ELEVENLABS, 7, None, at(2026, 6, 1), TABLE) == D("0.56")
    assert voice_cost(Provider.ELEVENLABS, 7, None, at(2026, 6, 1), tuple(reversed(TABLE))) == D(
        "0.56"
    )


def test_an_override_takes_precedence_over_the_table() -> None:
    # 3 x $0.05, whatever the platform price
    assert voice_cost(Provider.ELEVENLABS, 3, D("0.05"), at(2025, 3, 1), TABLE) == D("0.15")
    assert voice_cost(Provider.ELEVENLABS, 3, D("0.05"), at(2024, 1, 1), ()) == D("0.15")


def test_without_a_price_the_voice_cost_is_unknown() -> None:
    assert voice_cost(Provider.ELEVENLABS, 3, None, at(2024, 12, 31), TABLE) is None
    assert voice_cost(Provider.ELEVENLABS, 3, None, at(2026, 1, 1), ()) is None
    assert voice_platform_price(Provider.DEMO, at(2026, 1, 1), TABLE) is None


def test_a_call_of_no_minutes_costs_nothing() -> None:
    assert voice_cost(Provider.ELEVENLABS, 0, None, at(2026, 1, 1), TABLE) == D("0")
