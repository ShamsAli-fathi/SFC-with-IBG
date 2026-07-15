from dataclasses import dataclass
import math
from statistics import NormalDist
from typing import Mapping, Sequence

import numpy as np


DEFAULT_REWARD = 100.0
DEFAULT_LATENCY_WEIGHT = 1.0
DEFAULT_COST = 1.0
DEFAULT_LINK_LATENCY_WEIGHT = 1.0
DEFAULT_SLA_LATENCY_MS = 110.0


@dataclass(frozen=True)
class LatencyParameters:
    """State-conditioned processing-latency parameters.

    ``capacity_flows`` and ``load`` are both measured in concurrent-flow
    units. Every latency-valued field is measured in milliseconds.
    """

    base_ms: float
    congestion_ms: float
    knee_ms: float
    capacity_flows: int
    jitter_ms: float

    def __post_init__(self):
        if self.base_ms <= 0:
            raise ValueError("base_ms must be positive")
        if self.congestion_ms < 0 or self.knee_ms < 0:
            raise ValueError("congestion penalties must not be negative")
        if self.capacity_flows < 1:
            raise ValueError("capacity_flows must be at least 1")
        if self.jitter_ms <= 0:
            raise ValueError("jitter_ms must be positive")


# Phase 2 accepted design calibration, ordered from state 1 (bad) to state 4
# (good). These values characterize the synthetic FastAPI replica behavior;
# they are not measured Kernel or DPDK/VPP capacity claims.
CALIBRATED_STATE_PARAMETERS: Mapping[int, LatencyParameters] = {
    1: LatencyParameters(40.0, 8.0, 12.0, 1, 4.0),
    2: LatencyParameters(28.0, 6.0, 8.0, 2, 3.0),
    3: LatencyParameters(18.0, 4.0, 5.0, 3, 2.0),
    4: LatencyParameters(10.0, 2.0, 2.0, 5, 1.0),
}

# Transitional import alias for Phase 1 callers. Active code and new tests
# should use CALIBRATED_STATE_PARAMETERS.
PROVISIONAL_STATE_PARAMETERS = CALIBRATED_STATE_PARAMETERS


def require_state_parameters(
    state: int,
    parameters_by_state: Mapping[int, LatencyParameters] = (
        CALIBRATED_STATE_PARAMETERS
    ),
) -> LatencyParameters:
    try:
        return parameters_by_state[state]
    except KeyError as error:
        raise ValueError(f"unknown latency state {state}") from error


def deterministic_latency_ms(load: int, parameters: LatencyParameters) -> float:
    if load < 1:
        raise ValueError("load must be at least 1")
    ordinary = parameters.congestion_ms * max(0, load - 1)
    overload = parameters.knee_ms * max(
        0,
        load - parameters.capacity_flows,
    ) ** 2
    return parameters.base_ms + ordinary + overload


def sample_latency_ms(
    load: int,
    parameters: LatencyParameters,
    random_source=None,
) -> float:
    """Sample positive processing latency from the shifted normal law."""
    random_source = random_source or np.random
    center = deterministic_latency_ms(load, parameters)
    sample = -1.0
    while sample <= 0:
        sample = float(random_source.normal(center, parameters.jitter_ms))
    return sample


def expected_latency_ms(load: int, parameters: LatencyParameters) -> float:
    """Return the mean of the positive-truncated shifted normal law."""
    center = deterministic_latency_ms(load, parameters)
    standardized = center / parameters.jitter_ms
    normal = NormalDist()
    retained_probability = normal.cdf(standardized)
    correction = (
        parameters.jitter_ms
        * math.exp(-(standardized**2) / 2)
        / math.sqrt(2 * math.pi)
        / retained_probability
    )
    return center + correction


def latency_pdf(
    latency_ms: float,
    load: int,
    parameters: LatencyParameters,
) -> float:
    if latency_ms <= 0:
        return 0.0
    center = deterministic_latency_ms(load, parameters)
    sigma = parameters.jitter_ms
    standardized = (latency_ms - center) / sigma
    retained_probability = NormalDist().cdf(center / sigma)
    return (
        math.exp(-(standardized**2) / 2)
        / (math.sqrt(2 * math.pi) * sigma * retained_probability)
    )


def latency_likelihood(
    latency_ms: float,
    load: int,
    parameters_by_state: Mapping[int, LatencyParameters] = (
        CALIBRATED_STATE_PARAMETERS
    ),
) -> tuple[float, float, float, float]:
    """Return normalized state likelihoods ordered as states 1..4."""
    densities = np.asarray(
        [
            latency_pdf(
                latency_ms,
                load,
                require_state_parameters(state, parameters_by_state),
            )
            for state in range(1, 5)
        ],
        dtype=float,
    )
    total = float(densities.sum())
    if not math.isfinite(total) or total <= 0:
        return (0.25, 0.25, 0.25, 0.25)
    return tuple(float(value) for value in densities / total)


def estimate_state(likelihood: Sequence[float]) -> int:
    if len(likelihood) != 4:
        raise ValueError("likelihood must contain four state values")
    return int(np.argmax(np.asarray(likelihood, dtype=float))) + 1


def sample_belief_latency_ms(
    belief: Sequence[float],
    load: int,
    random_source=None,
    parameters_by_state: Mapping[int, LatencyParameters] = (
        CALIBRATED_STATE_PARAMETERS
    ),
) -> float:
    random_source = random_source or np.random
    probabilities = np.asarray(belief, dtype=float)
    if (
        probabilities.shape != (4,)
        or (probabilities < 0).any()
        or probabilities.sum() <= 0
    ):
        raise ValueError(
            "belief must contain four non-negative, positive-total values"
        )
    probabilities = probabilities / probabilities.sum()
    state = int(random_source.choice(np.arange(1, 5), p=probabilities))
    return sample_latency_ms(
        load,
        require_state_parameters(state, parameters_by_state),
        random_source,
    )


def expected_state_utility(
    state: int,
    load: int,
    *,
    reward: float = DEFAULT_REWARD,
    latency_weight: float = DEFAULT_LATENCY_WEIGHT,
    cost: float = DEFAULT_COST,
    parameters_by_state: Mapping[int, LatencyParameters] = (
        CALIBRATED_STATE_PARAMETERS
    ),
) -> float:
    return (
        reward
        - latency_weight
        * expected_latency_ms(
            load,
            require_state_parameters(state, parameters_by_state),
        )
        - cost
    )


def first_negative_utility_load(
    state: int,
    max_load: int,
    *,
    reward: float = DEFAULT_REWARD,
    latency_weight: float = DEFAULT_LATENCY_WEIGHT,
    cost: float = DEFAULT_COST,
    parameters_by_state: Mapping[int, LatencyParameters] = (
        CALIBRATED_STATE_PARAMETERS
    ),
) -> int | None:
    if max_load < 1:
        raise ValueError("max_load must be at least 1")
    for load in range(1, max_load + 1):
        if expected_state_utility(
            state,
            load,
            reward=reward,
            latency_weight=latency_weight,
            cost=cost,
            parameters_by_state=parameters_by_state,
        ) < 0:
            return load
    return None
