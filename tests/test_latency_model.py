import numpy as np
import pytest

from IBG.latency_model import (
    PROVISIONAL_STATE_PARAMETERS,
    LatencyParameters,
    deterministic_latency_ms,
    estimate_state,
    first_negative_utility_load,
    latency_likelihood,
    sample_latency_ms,
)


def test_latency_parameters_validate_units_and_domains():
    with pytest.raises(ValueError, match="base_ms"):
        LatencyParameters(0, 1, 1, 1, 1)
    with pytest.raises(ValueError, match="capacity_flows"):
        LatencyParameters(1, 1, 1, 0, 1)
    with pytest.raises(ValueError, match="jitter_ms"):
        LatencyParameters(1, 1, 1, 1, 0)


def test_provisional_states_have_ordered_latency_and_congestion_curves():
    for load in range(1, 11):
        latencies = [
            deterministic_latency_ms(load, PROVISIONAL_STATE_PARAMETERS[state])
            for state in range(1, 5)
        ]
        assert latencies == sorted(latencies, reverse=True)


def test_seeded_latency_sample_is_positive_and_likelihood_identifies_center():
    sample = sample_latency_ms(
        2,
        PROVISIONAL_STATE_PARAMETERS[2],
        np.random.default_rng(2050),
    )
    likelihood = latency_likelihood(
        deterministic_latency_ms(2, PROVISIONAL_STATE_PARAMETERS[2]),
        2,
    )

    assert sample == pytest.approx(26.976040674420698)
    assert sum(likelihood) == pytest.approx(1.0)
    assert estimate_state(likelihood) == 2


def test_provisional_zero_crossings_are_ordered_for_phase2_calibration():
    crossings = [first_negative_utility_load(state, 20) for state in range(1, 5)]

    assert crossings == [3, 5, 7, 11]
