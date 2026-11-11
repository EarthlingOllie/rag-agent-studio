"""The analytics statistics, through their public functions: Wilson score intervals against
published reference values, and percentiles read from fixed-bucket histograms against the exact
percentiles of the same values."""

import math
import random

import pytest

from app.analytics.stats import Histogram, wilson

# Reference values: the Wilson score interval at 95% (z = 1.959964), computed independently with
# statsmodels 0.14 `proportion_confint(count, nobs, method="wilson")`.
WILSON_REFERENCES = [
    # (successes, n, lower, upper)
    (8, 10, 0.4901625, 0.9433178),
    (0, 5, 0.0, 0.4344825),
    (5, 5, 0.5655175, 1.0),
    (1, 1, 0.2065493, 1.0),
    (50, 100, 0.4038315, 0.5961685),
    (81, 263, 0.2552885, 0.3662096),
    (3, 3, 0.4385030, 1.0),
]


@pytest.mark.parametrize(("successes", "n", "lower", "upper"), WILSON_REFERENCES)
def test_wilson_intervals_match_reference_values(
    successes: int, n: int, lower: float, upper: float
) -> None:
    interval = wilson(successes, n)

    assert interval is not None
    assert interval.low == pytest.approx(lower, abs=1e-6)
    assert interval.high == pytest.approx(upper, abs=1e-6)


def test_there_is_no_interval_without_a_sample() -> None:
    assert wilson(0, 0) is None


def exact_percentile(values: list[int], p: float) -> int:
    """The nearest-rank percentile: the smallest value with at least ``p`` of them at or below."""
    ordered = sorted(values)
    return ordered[max(math.ceil(p * len(ordered)) - 1, 0)]


def histogram_of(values: list[int]) -> Histogram:
    histogram = Histogram()
    for value in values:
        histogram.add(value)
    return histogram


def test_an_empty_histogram_has_no_percentile_or_mean() -> None:
    assert Histogram().percentile(0.95) is None
    assert Histogram().count == 0


@pytest.mark.parametrize("seed", [1, 2, 3])
@pytest.mark.parametrize("p", [0.5, 0.95, 0.99])
def test_percentiles_from_a_histogram_are_within_tolerance_of_the_exact_values(
    seed: int, p: float
) -> None:
    generator = random.Random(seed)  # noqa: S311 (test data, not security)
    # Token counts: mostly a few hundred, with a long tail.
    values = [round(generator.lognormvariate(6, 0.8)) for _ in range(2000)]

    estimate = histogram_of(values).percentile(p)

    assert estimate is not None
    assert estimate == pytest.approx(exact_percentile(values, p), rel=0.10)


def test_percentiles_of_a_known_small_sample() -> None:
    # 20 latencies in ms; the exact p95 (nearest rank: the 19th) is 1900, the median 1000.
    values = [100 * i for i in range(1, 21)]
    histogram = histogram_of(values)

    assert histogram.percentile(0.95) == pytest.approx(1900, rel=0.10)
    assert histogram.percentile(0.5) == pytest.approx(1000, rel=0.10)
    assert histogram.count == 20


def test_histograms_merge_across_days_to_the_histogram_of_all_values() -> None:
    generator = random.Random(7)  # noqa: S311 (test data, not security)
    monday = [generator.randint(50, 900) for _ in range(300)]
    tuesday = [generator.randint(400, 4000) for _ in range(500)]

    merged = histogram_of(monday).merged(histogram_of(tuesday))

    assert merged == histogram_of(monday + tuesday)
    assert merged.percentile(0.95) == pytest.approx(
        exact_percentile(monday + tuesday, 0.95), rel=0.10
    )


def test_a_histogram_round_trips_through_its_stored_form() -> None:
    histogram = histogram_of([0, 0, 1, 7, 7, 250, 10**12])

    assert Histogram.from_stored(histogram.stored()) == histogram
    assert histogram.count == 7


def test_zero_and_values_beyond_the_last_bucket_are_kept() -> None:
    assert histogram_of([0, 0, 0]).percentile(0.95) == 0
    huge = histogram_of([10**12])
    estimate = huge.percentile(0.95)
    assert estimate is not None
    assert estimate > 10**8
