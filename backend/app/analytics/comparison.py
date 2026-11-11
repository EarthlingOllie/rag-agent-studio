"""Version comparison: two Agent Versions' KPIs side by side, metric by metric, with each
metric's difference (b minus a) and which side it favours, and the comparison as CSV.

Whether a metric is better higher or lower is fixed per metric: a higher thumbs-up rate or mean
rating is better; fewer tokens per reply, a cheaper Conversation, a lower fallback rate, a lower
Guardrail block rate and lower latency are better; volumes, totals and interval bounds favour
neither side, nor do mean searches per reply: more searching costs more but may answer better."""

import csv
import io
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from app.analytics.service import VersionKpis, low_confidence

Unit = Literal["count", "tokens", "usd", "rate", "rating", "ms", "searches"]
Side = Literal["a", "b"]
Direction = Literal["higher", "lower"] | None
Value = int | float | Decimal


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    unit: Unit
    direction: Direction
    value: Callable[[VersionKpis], Value | None]
    # Whether this metric's sample is small for a Version.
    small: Callable[[VersionKpis], bool] = lambda _: False


def _thumbs_low(kpis: VersionKpis) -> float | None:
    interval = kpis.thumbs_up_interval
    return None if interval is None else interval.low


def _thumbs_high(kpis: VersionKpis) -> float | None:
    interval = kpis.thumbs_up_interval
    return None if interval is None else interval.high


def _few_conversations(kpis: VersionKpis) -> bool:
    return low_confidence(kpis.usage.conversations)


def _few_votes(kpis: VersionKpis) -> bool:
    return low_confidence(kpis.thumbs)


def _few_ratings(kpis: VersionKpis) -> bool:
    return low_confidence(kpis.usage.rating_count)


METRICS = [
    Metric("conversations", "Conversations", "count", None, lambda k: k.usage.conversations,
           _few_conversations),
    Metric("messages", "Replies", "count", None, lambda k: k.usage.messages, _few_conversations),
    Metric("tokens_mean", "Mean tokens per reply", "tokens", "lower", lambda k: k.mean_tokens),
    Metric("tokens_p95", "p95 tokens per reply", "tokens", "lower",
           lambda k: k.usage.tokens_histogram.percentile(0.95)),
    Metric("cost_per_conversation_usd", "Cost per Conversation (USD)", "usd", "lower",
           lambda k: k.cost_per_conversation),
    Metric("cost_total_usd", "Total cost (USD)", "usd", None, lambda k: k.cost_total),
    Metric("thumbs_up_rate", "Thumbs-up rate", "rate", "higher", lambda k: k.thumbs_up_rate,
           _few_votes),
    Metric("thumbs_up_low", "Thumbs-up rate, 95% interval low", "rate", None, _thumbs_low,
           _few_votes),
    Metric("thumbs_up_high", "Thumbs-up rate, 95% interval high", "rate", None, _thumbs_high,
           _few_votes),
    Metric("votes", "Votes", "count", None, lambda k: k.thumbs, _few_votes),
    Metric("rating_mean", "Mean rating", "rating", "higher", lambda k: k.mean_rating,
           _few_ratings),
    Metric("ratings", "Ratings", "count", None, lambda k: k.usage.rating_count, _few_ratings),
    Metric("fallback_rate", "Fallback rate", "rate", "lower", lambda k: k.fallback_rate),
    Metric("guardrail_block_rate", "Guardrail block rate", "rate", "lower",
           lambda k: k.block_rate),
    Metric("searches_per_reply", "Mean searches per reply", "searches", None,
           lambda k: k.mean_searches, _few_conversations),
    Metric("first_token_p95_ms", "p95 time to first token (ms)", "ms", "lower",
           lambda k: k.usage.first_token_histogram.percentile(0.95)),
    Metric("total_p95_ms", "p95 total latency (ms)", "ms", "lower",
           lambda k: k.usage.latency_histogram.percentile(0.95)),
]  # fmt: skip


@dataclass(frozen=True)
class MetricRow:
    key: str
    label: str
    unit: Unit
    a: Value | None
    b: Value | None
    # b minus a; None when either side has no value.
    difference: Value | None
    # The two sides differ (one having a value and the other none counts).
    changed: bool
    # The side this metric favours; None when it favours neither or they're level.
    better: Side | None
    # Either side's sample for this metric is small.
    low_confidence: bool


def _better(direction: Direction, difference: Value | None) -> Side | None:
    if direction is None or difference is None or difference == 0:
        return None
    b_higher = difference > 0
    return "b" if b_higher == (direction == "higher") else "a"


def _minus(second: Value, first: Value) -> Value:
    # Dollars stay exact; every other metric is a count or a float.
    if isinstance(first, Decimal) and isinstance(second, Decimal):
        return second - first
    return float(second) - float(first)


def _row(metric: Metric, a: VersionKpis, b: VersionKpis) -> MetricRow:
    first, second = metric.value(a), metric.value(b)
    difference = None if first is None or second is None else _minus(second, first)
    return MetricRow(
        key=metric.key,
        label=metric.label,
        unit=metric.unit,
        a=first,
        b=second,
        difference=difference,
        changed=first != second,
        better=_better(metric.direction, difference),
        low_confidence=metric.small(a) or metric.small(b),
    )


@dataclass(frozen=True)
class Comparison:
    a: VersionKpis
    b: VersionKpis
    metrics: list[MetricRow]


def compare(a: VersionKpis, b: VersionKpis) -> Comparison:
    """Version ``a`` and Version ``b`` metric by metric, in ``METRICS`` order."""
    return Comparison(a, b, [_row(metric, a, b) for metric in METRICS])


# Counts as whole numbers; dollars as the API gives them, to the nano-dollar.
_FORMATS: dict[Unit, str] = {
    "count": ".0f",
    "usd": "f",
    "tokens": ".1f",
    "ms": ".1f",
    "rate": ".4f",
    "rating": ".2f",
    "searches": ".2f",
}


def _cell(unit: Unit, value: Value | None) -> str:
    return "" if value is None else format(value, _FORMATS[unit])


def to_csv(comparison: Comparison) -> str:
    """The comparison as CSV: a row per metric with both Versions' values, the difference and
    the Version it favours; empty cells where there is no value."""
    first = f"v{comparison.a.version.number}"
    second = f"v{comparison.b.version.number}"
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["Metric", first, second, f"Difference ({second} - {first})", "Better"])
    for row in comparison.metrics:
        better = {"a": first, "b": second, None: ""}[row.better]
        writer.writerow(
            [
                row.label,
                _cell(row.unit, row.a),
                _cell(row.unit, row.b),
                _cell(row.unit, row.difference),
                better,
            ]
        )
    return out.getvalue()
