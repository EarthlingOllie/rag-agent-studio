"""The statistics behind the Version KPIs: Wilson score intervals for rates, and percentiles read
from fixed-bucket histograms, which can be stored per day and merged across days."""

import bisect
import itertools
import math
from dataclasses import dataclass, field

# The two-sided 95% normal quantile.
Z_95 = 1.959963984540054

# Bucket 0 holds values below 1; bucket i (1 to LAST_BUCKET - 1) holds [GROWTH^(i-1), GROWTH^i);
# LAST_BUCKET holds everything from GROWTH^(LAST_BUCKET-1) up (about 1.2 billion). With 10%
# wide buckets and interpolation inside one, a percentile is within 10% of the exact value.
GROWTH = 1.1
LAST_BUCKET = 220


@dataclass(frozen=True)
class Interval:
    low: float
    high: float


def wilson(successes: int, n: int, z: float = Z_95) -> Interval | None:
    """The Wilson score interval for ``successes`` out of ``n`` (95% by default); None when
    there is no sample."""
    if n == 0:
        return None
    p = successes / n
    z2 = z * z
    denominator = 1 + z2 / n
    centre = (p + z2 / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denominator
    return Interval(low=max(0.0, centre - half), high=min(1.0, centre + half))


# The buckets' lower edges, from bucket 1 up: GROWTH^0, GROWTH^1, … GROWTH^(LAST_BUCKET-1).
_EDGES = [GROWTH**power for power in range(LAST_BUCKET)]


def _bucket(value: float) -> int:
    return bisect.bisect_right(_EDGES, value)


@dataclass
class Histogram:
    """How many values fell in each fixed bucket. Merging two gives the histogram of all their
    values, so a day's histograms add up to a period's."""

    counts: dict[int, int] = field(default_factory=dict)

    @property
    def count(self) -> int:
        return sum(self.counts.values())

    def add(self, value: float) -> None:
        index = _bucket(value)
        self.counts[index] = self.counts.get(index, 0) + 1

    def merged(self, other: "Histogram") -> "Histogram":
        counts = dict(self.counts)
        for index, count in other.counts.items():
            counts[index] = counts.get(index, 0) + count
        return Histogram(counts)

    def percentile(self, p: float) -> float | None:
        """The nearest-rank ``p`` percentile (0 < p <= 1), interpolated inside its bucket; None
        for an empty histogram."""
        total = self.count
        if total == 0:
            return None
        target = max(math.ceil(p * total), 1)
        indexes = sorted(self.counts)
        running = list(itertools.accumulate(self.counts[index] for index in indexes))
        position = bisect.bisect_left(running, target)
        index = indexes[position]
        if index == 0:
            return 0.0
        low = _EDGES[index - 1]
        if index == LAST_BUCKET:
            return low
        high = _EDGES[index]
        count = self.counts[index]
        seen = running[position] - count
        return low + (high - low) * (target - seen) / count

    def stored(self) -> dict[str, int]:
        """The JSON form kept in a rollup row."""
        return {str(index): count for index, count in sorted(self.counts.items())}

    @classmethod
    def from_stored(cls, stored: dict[str, int]) -> "Histogram":
        return cls({int(index): count for index, count in stored.items()})
