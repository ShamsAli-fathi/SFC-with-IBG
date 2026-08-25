"""Greedy-owned deterministic expected-utility adapter and bounded cache."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from math import isfinite
from numbers import Integral
from typing import Sequence

from IBG.latency_model import expected_state_utility


GREEDY_EXPECTED_UTILITY_ADAPTER_VERSION = "greedy-expected-stage-utility-v1"
DEFAULT_EXPECTED_UTILITY_CACHE_MAX_ENTRIES = 4096


def _validated_key(
    belief: Sequence[float],
    projected_load: int,
) -> tuple[tuple[float, ...], int]:
    if isinstance(projected_load, bool) or not isinstance(projected_load, Integral):
        raise TypeError("projected_load must be an integer")
    if projected_load < 1:
        raise ValueError("projected_load must be at least 1")
    probabilities = tuple(float(value) for value in belief)
    if len(probabilities) != 4:
        raise ValueError("belief must contain the four IBG states")
    if any(not isfinite(value) or value < 0 for value in probabilities):
        raise ValueError("belief probabilities must be finite and nonnegative")
    if sum(probabilities) <= 0:
        raise ValueError("belief probabilities must have positive mass")
    return probabilities, int(projected_load)


def expected_stage_utility_from_belief(
    belief: Sequence[float],
    projected_load: int,
) -> float:
    """Mix the active deterministic state utilities using a public belief."""

    probabilities, load = _validated_key(belief, projected_load)
    total = sum(probabilities)
    return sum(
        (probability / total) * expected_state_utility(state, load)
        for state, probability in enumerate(probabilities, start=1)
    )


@dataclass(frozen=True)
class ExpectedUtilityCacheInfo:
    max_entries: int
    size: int
    hits: int
    misses: int
    evictions: int


class BoundedExpectedUtilityCache:
    """Controller-lifetime LRU keyed exactly by belief tuple and load."""

    def __init__(
        self,
        max_entries: int = DEFAULT_EXPECTED_UTILITY_CACHE_MAX_ENTRIES,
    ) -> None:
        if isinstance(max_entries, bool) or not isinstance(max_entries, Integral):
            raise TypeError("max_entries must be an integer")
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        self._max_entries = int(max_entries)
        self._values: OrderedDict[tuple[tuple[float, ...], int], float] = OrderedDict()
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def value(
        self,
        belief: Sequence[float],
        projected_load: int,
        *,
        use_cache: bool = True,
    ) -> float:
        key = _validated_key(belief, projected_load)
        if not use_cache:
            return expected_stage_utility_from_belief(*key)
        try:
            value = self._values.pop(key)
        except KeyError:
            self._misses += 1
            value = expected_stage_utility_from_belief(*key)
            if len(self._values) >= self._max_entries:
                self._values.popitem(last=False)
                self._evictions += 1
        else:
            self._hits += 1
        self._values[key] = value
        return value

    def clear(self) -> None:
        self._values.clear()

    @property
    def info(self) -> ExpectedUtilityCacheInfo:
        return ExpectedUtilityCacheInfo(
            max_entries=self._max_entries,
            size=len(self._values),
            hits=self._hits,
            misses=self._misses,
            evictions=self._evictions,
        )

