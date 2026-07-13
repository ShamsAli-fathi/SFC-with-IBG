from dataclasses import asdict, replace
from typing import Mapping

import numpy as np

from latency_model import (
    CALIBRATED_STATE_PARAMETERS,
    DEFAULT_COST,
    DEFAULT_LATENCY_WEIGHT,
    DEFAULT_LINK_LATENCY_WEIGHT,
    DEFAULT_REWARD,
    DEFAULT_SLA_LATENCY_MS,
    LatencyParameters,
    deterministic_latency_ms,
    estimate_state,
    expected_state_utility,
    first_negative_utility_load,
    latency_likelihood,
    require_state_parameters,
    sample_latency_ms,
)


CALIBRATION_LOAD_HORIZON = 12
SUPPORTED_EXACT_LOAD = 3
CALIBRATION_SEED = 2050
CALIBRATION_MONTE_CARLO_SAMPLES = 5_000
CALIBRATION_SENSITIVITY_FRACTION = 0.10
MINIMUM_STATE_CLASSIFICATION_ACCURACY = 0.90
MINIMUM_LIVE_CLASSIFICATION_ACCURACY = 0.80
LIVE_ABSOLUTE_TOLERANCE_MS = 10.0
LIVE_RELATIVE_TOLERANCE = 0.10

# Inclusive bands for the first load whose expected stage utility is negative.
ZERO_CROSSING_TARGET_BANDS: Mapping[int, tuple[int, int]] = {
    1: (3, 4),
    2: (4, 6),
    3: (6, 8),
    4: (10, 12),
}


def zero_crossings(
    parameters_by_state: Mapping[int, LatencyParameters] = (
        CALIBRATED_STATE_PARAMETERS
    ),
    *,
    reward: float = DEFAULT_REWARD,
    latency_weight: float = DEFAULT_LATENCY_WEIGHT,
    cost: float = DEFAULT_COST,
) -> dict[int, int | None]:
    return {
        state: first_negative_utility_load(
            state,
            CALIBRATION_LOAD_HORIZON,
            reward=reward,
            latency_weight=latency_weight,
            cost=cost,
            parameters_by_state=parameters_by_state,
        )
        for state in range(1, 5)
    }


def crossings_meet_targets(crossings: Mapping[int, int | None]) -> bool:
    values = [crossings[state] for state in range(1, 5)]
    if any(value is None for value in values):
        return False
    if values != sorted(values) or len(set(values)) != len(values):
        return False
    return all(
        ZERO_CROSSING_TARGET_BANDS[state][0]
        <= crossings[state]
        <= ZERO_CROSSING_TARGET_BANDS[state][1]
        for state in range(1, 5)
    )


def state_ordering_report(
    parameters_by_state: Mapping[int, LatencyParameters] = (
        CALIBRATED_STATE_PARAMETERS
    ),
) -> dict:
    parameters = [parameters_by_state[state] for state in range(1, 5)]
    semantic_checks = {
        "base_ms": [value.base_ms for value in parameters]
        == sorted((value.base_ms for value in parameters), reverse=True),
        "congestion_ms": [value.congestion_ms for value in parameters]
        == sorted(
            (value.congestion_ms for value in parameters),
            reverse=True,
        ),
        "knee_ms": [value.knee_ms for value in parameters]
        == sorted((value.knee_ms for value in parameters), reverse=True),
        "capacity_flows": [value.capacity_flows for value in parameters]
        == sorted(value.capacity_flows for value in parameters),
        "jitter_ms": [value.jitter_ms for value in parameters]
        == sorted((value.jitter_ms for value in parameters), reverse=True),
    }
    curve_checks = {}
    for load in range(1, CALIBRATION_LOAD_HORIZON + 1):
        latencies = [
            deterministic_latency_ms(load, parameters_by_state[state])
            for state in range(1, 5)
        ]
        curve_checks[load] = latencies == sorted(latencies, reverse=True)
    return {
        "semantic_checks": semantic_checks,
        "curve_checks": curve_checks,
        "passed": all(semantic_checks.values()) and all(curve_checks.values()),
    }


def _scaled_parameters(
    factor: float,
    parameters_by_state: Mapping[int, LatencyParameters],
) -> dict[int, LatencyParameters]:
    return {
        state: replace(
            parameters,
            base_ms=parameters.base_ms * factor,
            congestion_ms=parameters.congestion_ms * factor,
            knee_ms=parameters.knee_ms * factor,
            jitter_ms=parameters.jitter_ms * factor,
        )
        for state, parameters in parameters_by_state.items()
    }


def sensitivity_report(
    parameters_by_state: Mapping[int, LatencyParameters] = (
        CALIBRATED_STATE_PARAMETERS
    ),
) -> dict:
    fraction = CALIBRATION_SENSITIVITY_FRACTION
    scenarios = {
        "latency_scale_low": zero_crossings(
            _scaled_parameters(1.0 - fraction, parameters_by_state)
        ),
        "latency_scale_high": zero_crossings(
            _scaled_parameters(1.0 + fraction, parameters_by_state)
        ),
        "reward_low": zero_crossings(
            parameters_by_state,
            reward=DEFAULT_REWARD * (1.0 - (fraction / 2.0)),
        ),
        "reward_high": zero_crossings(
            parameters_by_state,
            reward=DEFAULT_REWARD * (1.0 + (fraction / 2.0)),
        ),
        "latency_weight_low": zero_crossings(
            parameters_by_state,
            latency_weight=DEFAULT_LATENCY_WEIGHT * (1.0 - fraction),
        ),
        "latency_weight_high": zero_crossings(
            parameters_by_state,
            latency_weight=DEFAULT_LATENCY_WEIGHT * (1.0 + fraction),
        ),
    }
    return {
        "fraction": fraction,
        "scenarios": scenarios,
        "passed": all(crossings_meet_targets(item) for item in scenarios.values()),
    }


def classification_report(
    *,
    samples_per_state_load: int = CALIBRATION_MONTE_CARLO_SAMPLES,
    seed: int = CALIBRATION_SEED,
    parameters_by_state: Mapping[int, LatencyParameters] = (
        CALIBRATED_STATE_PARAMETERS
    ),
) -> dict:
    if samples_per_state_load < 1:
        raise ValueError("samples_per_state_load must be positive")
    random_source = np.random.default_rng(seed)
    accuracy_by_load = {}
    minimum_accuracy = 1.0
    for load in range(1, CALIBRATION_LOAD_HORIZON + 1):
        accuracy_by_state = {}
        for state in range(1, 5):
            correct = 0
            for _ in range(samples_per_state_load):
                latency = sample_latency_ms(
                    load,
                    require_state_parameters(state, parameters_by_state),
                    random_source,
                )
                inferred = estimate_state(
                    latency_likelihood(latency, load, parameters_by_state)
                )
                correct += inferred == state
            accuracy = correct / samples_per_state_load
            accuracy_by_state[state] = accuracy
            minimum_accuracy = min(minimum_accuracy, accuracy)
        accuracy_by_load[load] = accuracy_by_state
    return {
        "samples_per_state_load": samples_per_state_load,
        "seed": seed,
        "accuracy_by_load": accuracy_by_load,
        "minimum_accuracy": minimum_accuracy,
        "minimum_required": MINIMUM_STATE_CLASSIFICATION_ACCURACY,
        "passed": minimum_accuracy >= MINIMUM_STATE_CLASSIFICATION_ACCURACY,
    }


def sla_probability_report(
    *,
    samples_per_state: int = CALIBRATION_MONTE_CARLO_SAMPLES,
    seed: int = CALIBRATION_SEED,
    stages: int = 3,
    load: int = SUPPORTED_EXACT_LOAD,
    parameters_by_state: Mapping[int, LatencyParameters] = (
        CALIBRATED_STATE_PARAMETERS
    ),
) -> dict:
    if samples_per_state < 1:
        raise ValueError("samples_per_state must be positive")
    if stages < 1:
        raise ValueError("stages must be positive")
    random_source = np.random.default_rng(seed)
    probability_by_state = {}
    for state in range(1, 5):
        violations = 0
        parameters = require_state_parameters(state, parameters_by_state)
        for _ in range(samples_per_state):
            end_to_end_latency = sum(
                sample_latency_ms(load, parameters, random_source)
                for _ in range(stages)
            )
            violations += end_to_end_latency > DEFAULT_SLA_LATENCY_MS
        probability_by_state[state] = violations / samples_per_state
    return {
        "samples_per_state": samples_per_state,
        "seed": seed,
        "stages": stages,
        "assigned_load": load,
        "transport_latency_ms": 0.0,
        "threshold_ms": DEFAULT_SLA_LATENCY_MS,
        "probability_by_state": probability_by_state,
        "passed": (
            probability_by_state[1] >= 0.95
            and probability_by_state[4] <= 0.05
        ),
    }


def assess_live_observation(payload: Mapping, *, state: int, load: int) -> dict:
    parameters = require_state_parameters(state)
    modeled = float(payload["modeled_processing_latency_ms"])
    measured = float(payload["processing_latency_ms"])
    signal = float(payload["signal_latency_ms"])
    expected_likelihood = latency_likelihood(measured, load)
    observed_likelihood = tuple(float(value) for value in payload["state_likelihood"])
    overshoot = measured - modeled
    overshoot_tolerance = max(
        LIVE_ABSOLUTE_TOLERANCE_MS,
        LIVE_RELATIVE_TOLERANCE * modeled,
    )
    checks = {
        "assigned_load": int(payload["assigned_load"]) == load,
        "positive_latencies": modeled > 0 and measured > 0,
        "signal_is_measured_processing": abs(signal - measured) <= 1e-9,
        "model_sample_within_four_sigma": abs(
            modeled - deterministic_latency_ms(load, parameters)
        )
        <= 4.0 * parameters.jitter_ms,
        "server_overshoot_within_tolerance": (
            -0.1 <= overshoot <= overshoot_tolerance
        ),
        "likelihood_matches_signal": np.allclose(
            observed_likelihood,
            expected_likelihood,
            rtol=1e-9,
            atol=1e-12,
        ),
    }
    return {
        "state": state,
        "load": load,
        "modeled_processing_latency_ms": modeled,
        "measured_processing_latency_ms": measured,
        "server_overshoot_ms": overshoot,
        "server_overshoot_tolerance_ms": overshoot_tolerance,
        "state_estimate": int(payload["state_estimate"]),
        "checks": checks,
        "passed": all(checks.values()),
    }


def build_calibration_report(
    *,
    samples: int = CALIBRATION_MONTE_CARLO_SAMPLES,
    seed: int = CALIBRATION_SEED,
) -> dict:
    crossings = zero_crossings()
    ordering = state_ordering_report()
    sensitivity = sensitivity_report()
    classification = classification_report(
        samples_per_state_load=samples,
        seed=seed,
    )
    sla = sla_probability_report(samples_per_state=samples, seed=seed)
    low_load_utility = {
        state: expected_state_utility(state, 1) for state in range(1, 5)
    }
    supported_load_utility = {
        state: expected_state_utility(state, SUPPORTED_EXACT_LOAD)
        for state in range(1, 5)
    }
    model_gate = all(
        (
            crossings_meet_targets(crossings),
            ordering["passed"],
            sensitivity["passed"],
            classification["passed"],
            sla["passed"],
            all(value > 0 for value in low_load_utility.values()),
            max(supported_load_utility.values()) >= 0,
        )
    )
    return {
        "calibration_kind": "synthetic-design-calibration",
        "units": {
            "latency": "milliseconds",
            "load_and_capacity": "concurrent flows",
            "reward_and_cost": "utility units per selected stage",
            "latency_weight": "utility units per millisecond",
            "link_latency_weight": "utility units per millisecond",
        },
        "load_horizon": CALIBRATION_LOAD_HORIZON,
        "supported_exact_load": SUPPORTED_EXACT_LOAD,
        "target_zero_crossing_bands": ZERO_CROSSING_TARGET_BANDS,
        "parameters_by_state": {
            state: asdict(parameters)
            for state, parameters in CALIBRATED_STATE_PARAMETERS.items()
        },
        "policy": {
            "reward": DEFAULT_REWARD,
            "latency_weight": DEFAULT_LATENCY_WEIGHT,
            "cost": DEFAULT_COST,
            "link_latency_weight": DEFAULT_LINK_LATENCY_WEIGHT,
            "sla_latency_ms": DEFAULT_SLA_LATENCY_MS,
        },
        "expected_zero_crossings": crossings,
        "low_load_expected_utility": low_load_utility,
        "supported_load_expected_utility": supported_load_utility,
        "ordering": ordering,
        "sensitivity": sensitivity,
        "classification": classification,
        "sla_probability": sla,
        "model_gate_passed": model_gate,
    }
