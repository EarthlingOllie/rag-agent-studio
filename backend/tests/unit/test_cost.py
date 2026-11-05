"""The pure cost function: (credential pricing, model, token counts, at-time) -> cost.

Expected costs are worked by hand from the prices in each test, per million tokens.
"""

from datetime import UTC, datetime
from decimal import Decimal

from app.credentials.registry import Provider
from app.pricing.table import CredentialPricing, Override, PriceEntry, TokenUsage, cost

D = Decimal
SONNET = "claude-sonnet-4-5"


def at(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=UTC)


TABLE = (
    PriceEntry(Provider.ANTHROPIC, SONNET, at(2025, 1, 1), D("3"), D("15"), D("0.3")),
    PriceEntry(Provider.ANTHROPIC, SONNET, at(2026, 6, 1), D("2"), D("10"), D("0.2")),
    # The same model ID under another provider is priced separately.
    PriceEntry(Provider.BEDROCK, SONNET, at(2025, 1, 1), D("4"), D("20"), D("0.4")),
)
ANTHROPIC = CredentialPricing(Provider.ANTHROPIC)
USAGE = TokenUsage(input_tokens=1_000_000, output_tokens=200_000, cached_input_tokens=500_000)


def test_the_platform_price_in_effect_at_the_time_is_used() -> None:
    # 1M x $3 + 0.2M x $15 + 0.5M x $0.30
    assert cost(ANTHROPIC, SONNET, USAGE, at(2026, 5, 31), TABLE) == D("6.15")
    # From 1 June 2026: 1M x $2 + 0.2M x $10 + 0.5M x $0.20
    assert cost(ANTHROPIC, SONNET, USAGE, at(2026, 6, 1), TABLE) == D("4.1")
    assert cost(ANTHROPIC, SONNET, USAGE, at(2027, 1, 1), TABLE) == D("4.1")


def test_the_order_of_the_table_does_not_matter() -> None:
    reversed_table = tuple(reversed(TABLE))

    assert cost(ANTHROPIC, SONNET, USAGE, at(2026, 5, 31), reversed_table) == D("6.15")
    assert cost(ANTHROPIC, SONNET, USAGE, at(2026, 7, 1), reversed_table) == D("4.1")


def test_prices_are_per_provider() -> None:
    bedrock = CredentialPricing(Provider.BEDROCK)

    # 1M x $4 + 0.2M x $20 + 0.5M x $0.40
    assert cost(bedrock, SONNET, USAGE, at(2026, 7, 1), TABLE) == D("8.2")


def test_overrides_take_precedence_over_the_platform_price() -> None:
    negotiated = CredentialPricing(
        Provider.ANTHROPIC, {SONNET: Override(D("1.5"), D("7.5"), D("0.15"))}
    )

    # 1M x $1.50 + 0.2M x $7.50 + 0.5M x $0.15, at either platform price
    assert cost(negotiated, SONNET, USAGE, at(2025, 3, 1), TABLE) == D("3.075")
    assert cost(negotiated, SONNET, USAGE, at(2026, 7, 1), TABLE) == D("3.075")


def test_a_partial_override_keeps_the_platform_price_for_the_rest() -> None:
    output_only = CredentialPricing(Provider.ANTHROPIC, {SONNET: Override(output=D("5"))})

    # 1M x $3 + 0.2M x $5 (override) + 0.5M x $0.30
    assert cost(output_only, SONNET, USAGE, at(2026, 1, 1), TABLE) == D("4.15")


def test_an_override_for_another_model_does_not_apply() -> None:
    other = CredentialPricing(Provider.ANTHROPIC, {"claude-haiku-4-5": Override(D("0"), D("0"))})

    assert cost(other, SONNET, USAGE, at(2026, 1, 1), TABLE) == D("6.15")


def test_without_a_price_the_cost_is_unknown() -> None:
    # Before the first platform price took effect.
    assert cost(ANTHROPIC, SONNET, USAGE, at(2024, 12, 31), TABLE) is None
    # A model the table doesn't price.
    assert cost(ANTHROPIC, "claude-unpriced", USAGE, at(2026, 1, 1), TABLE) is None


def test_an_override_prices_a_model_the_table_does_not() -> None:
    rerank = CredentialPricing(Provider.BEDROCK, {"cohere.rerank-v3-5:0": Override(input=D("2"))})
    queries_only = TokenUsage(input_tokens=250_000, output_tokens=0)

    # 0.25M x $2; no output or cached tokens, so their missing prices don't matter.
    assert cost(rerank, "cohere.rerank-v3-5:0", queries_only, at(2026, 1, 1), TABLE) == D("0.5")
    # Output tokens with no price anywhere: unknown.
    assert cost(rerank, "cohere.rerank-v3-5:0", USAGE, at(2026, 1, 1), TABLE) is None


def test_no_tokens_cost_nothing() -> None:
    assert cost(ANTHROPIC, SONNET, TokenUsage(0, 0), at(2026, 1, 1), TABLE) == D("0")
