"""Belief-driven Hybrid utility using the frozen IBG-Exact latency model."""

from __future__ import annotations

from math import isfinite
from numbers import Integral
from typing import Sequence

from IBG.latency_model import expected_state_utility


def expected_stage_utility_from_belief(
    belief: Sequence[float],
    load: int,
) -> float:
    """Return expected Exact stage utility without observing a true state.

    The four belief entries correspond to Exact performance states 1 through
    4. The function delegates every state/load utility calculation to
    ``IBG.latency_model.expected_state_utility`` and only performs the belief
    mixture here.
    """

    if isinstance(load, bool) or not isinstance(load, Integral):
        raise TypeError("load must be an integer")
    if load < 1:
        raise ValueError("load must be at least 1")

    probabilities = tuple(float(value) for value in belief)
    if len(probabilities) != 4:
        raise ValueError("belief must contain the four IBG states")
    if any(not isfinite(value) or value < 0 for value in probabilities):
        raise ValueError("belief probabilities must be finite and nonnegative")
    total = sum(probabilities)
    if total <= 0:
        raise ValueError("belief probabilities must have positive mass")

    normalized = tuple(value / total for value in probabilities)
    return sum(
        probability * expected_state_utility(state, load)
        for state, probability in enumerate(normalized, start=1)
    )
