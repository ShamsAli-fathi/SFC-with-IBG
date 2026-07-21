import numpy as np
import pytest

from IBG.latency_model import (
    CALIBRATED_STATE_PARAMETERS,
    JITTER_DISTRIBUTION,
    OBSERVATION_JITTER_DISTRIBUTION,
    OBSERVATION_JITTER_MS_BY_STATE,
    LatencyParameters,
    deterministic_latency_ms,
    estimate_state,
    expected_latency_ms,
    first_negative_utility_load,
    latency_pdf,
    latency_likelihood,
    learning_signal_pdf,
    learning_signal_likelihood,
    sample_learning_signal_ms,
    sample_latency_ms,
)


def test_latency_parameters_validate_units_and_domains():
    with pytest.raises(ValueError, match="base_ms"):
        LatencyParameters(0, 1, 1, 1, 1)
    with pytest.raises(ValueError, match="capacity_flows"):
        LatencyParameters(1, 1, 1, 0, 1)
    with pytest.raises(ValueError, match="jitter_ms"):
        LatencyParameters(1, 1, 1, 1, 0)


def test_calibrated_states_have_ordered_latency_and_congestion_curves():
    for load in range(1, 11):
        latencies = [
            deterministic_latency_ms(load, CALIBRATED_STATE_PARAMETERS[state])
            for state in range(1, 5)
        ]
        assert latencies == sorted(latencies, reverse=True)


def test_seeded_latency_sample_is_additive_and_likelihood_identifies_center():
    sample = sample_latency_ms(
        2,
        CALIBRATED_STATE_PARAMETERS[2],
        np.random.default_rng(2050),
    )
    likelihood = latency_likelihood(
        deterministic_latency_ms(2, CALIBRATED_STATE_PARAMETERS[2]),
        2,
    )

    assert sample == pytest.approx(46.29192881976378)
    assert sample >= deterministic_latency_ms(2, CALIBRATED_STATE_PARAMETERS[2])
    assert sum(likelihood) == pytest.approx(1.0)
    assert estimate_state(likelihood) == 2


def test_half_normal_jitter_and_pdf_have_matching_nonnegative_support():
    parameters = CALIBRATED_STATE_PARAMETERS[4]
    center = deterministic_latency_ms(1, parameters)

    assert JITTER_DISTRIBUTION == "half-normal-additive-v1"
    assert latency_pdf(center - 0.001, 1, parameters) == 0.0
    assert latency_pdf(center, 1, parameters) > 0.0
    assert expected_latency_ms(1, parameters) == pytest.approx(
        center + parameters.jitter_ms * np.sqrt(2.0 / np.pi)
    )


def test_negative_normal_draw_adds_its_magnitude_instead_of_reducing_latency():
    class NegativeNormalSource:
        def normal(self, center, scale):
            assert center == 0.0
            assert scale == 4.0
            return -3.0

    parameters = LatencyParameters(10.0, 2.0, 1.0, 3, 4.0)

    assert sample_latency_ms(1, parameters, NegativeNormalSource()) == 13.0


def test_observation_jitter_is_separate_nonnegative_learning_noise():
    class NegativeNormalSource:
        def normal(self, center, scale):
            assert center == 0.0
            assert scale == OBSERVATION_JITTER_MS_BY_STATE[2]
            return -2.5

    signal, observation_jitter = sample_learning_signal_ms(
        45.0,
        2,
        NegativeNormalSource(),
    )

    assert OBSERVATION_JITTER_DISTRIBUTION == "half-normal-observation-v1"
    assert observation_jitter == 2.5
    assert signal == 47.5
    assert all(
        OBSERVATION_JITTER_MS_BY_STATE[state]
        > CALIBRATED_STATE_PARAMETERS[state].jitter_ms
        for state in range(1, 5)
    )


def test_learning_signal_pdf_has_convolved_nonnegative_support():
    state = 3
    load = 1
    center = deterministic_latency_ms(
        load,
        CALIBRATED_STATE_PARAMETERS[state],
    )

    assert learning_signal_pdf(center - 0.001, load, state) == 0.0
    assert learning_signal_pdf(center, load, state) == 0.0
    assert learning_signal_pdf(center + 1.0, load, state) > 0.0
    assert sum(learning_signal_likelihood(center + 5.0, load)) == pytest.approx(
        1.0
    )

    grid = np.linspace(center, center + 100.0, 20_001)
    density = [learning_signal_pdf(value, load, state) for value in grid]
    assert np.trapezoid(density, grid) == pytest.approx(1.0, abs=1e-6)


def test_calibrated_zero_crossings_are_ordered():
    crossings = [first_negative_utility_load(state, 20) for state in range(1, 5)]

    assert crossings == [3, 5, 7, 11]
