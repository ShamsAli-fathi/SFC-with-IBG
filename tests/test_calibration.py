from pathlib import Path

import pytest

from IBG.calibration import (
    CALIBRATION_LOAD_HORIZON,
    ZERO_CROSSING_TARGET_BANDS,
    assess_live_observation,
    build_calibration_report,
    sensitivity_report,
    zero_crossings,
)
from IBG.latency_model import (
    CALIBRATED_STATE_PARAMETERS,
    DEFAULT_SLA_LATENCY_MS,
    JITTER_DISTRIBUTION,
    latency_likelihood,
)
from testbed.profiles import load_profiles


ROOT = Path(__file__).resolve().parents[1]


def test_accepted_calibration_has_declared_ordered_zero_crossings():
    assert CALIBRATION_LOAD_HORIZON == 12
    assert ZERO_CROSSING_TARGET_BANDS == {
        1: (3, 4),
        2: (4, 6),
        3: (6, 8),
        4: (10, 12),
    }
    assert zero_crossings() == {1: 3, 2: 5, 3: 7, 4: 11}


def test_sensitivity_preserves_target_bands_and_ordering():
    report = sensitivity_report()

    assert report["passed"] is True
    assert report["scenarios"]["latency_scale_low"] == {
        1: 4,
        2: 5,
        3: 7,
        4: 12,
    }
    assert report["scenarios"]["latency_scale_high"] == {
        1: 3,
        2: 5,
        3: 7,
        4: 11,
    }


def test_seeded_calibration_report_passes_model_gate():
    report = build_calibration_report(samples=500, seed=2050)

    assert report["calibration_kind"] == "synthetic-design-calibration"
    assert report["model_gate_passed"] is True
    assert report["jitter_distribution"] == JITTER_DISTRIBUTION
    assert [
        CALIBRATED_STATE_PARAMETERS[state].jitter_ms for state in range(1, 5)
    ] == [6.0, 5.25, 4.0, 3.25]
    assert DEFAULT_SLA_LATENCY_MS == 110.0
    assert report["policy"]["sla_latency_ms"] == 110.0
    assert report["classification"]["minimum_accuracy"] >= 0.90
    assert report["sla_probability"]["probability_by_state"][1] >= 0.95
    assert report["sla_probability"]["probability_by_state"][4] <= 0.05
    assert max(report["supported_load_expected_utility"].values()) >= 0


def test_deployed_profiles_use_the_calibrated_stage_cost():
    profiles = load_profiles(ROOT / "deploy/kubernetes/profiles.json")

    assert {profile.cost for profile in profiles.values()} == {1.0}


def test_live_observation_assessment_checks_model_and_signal_boundaries():
    measured = 40.5
    payload = {
        "assigned_load": 1,
        "modeled_processing_latency_ms": 40.0,
        "processing_latency_ms": measured,
        "signal_latency_ms": measured,
        "state_estimate": 1,
        "state_likelihood": latency_likelihood(measured, 1),
    }

    report = assess_live_observation(payload, state=1, load=1)

    assert report["passed"] is True
    assert report["server_overshoot_ms"] == pytest.approx(0.5)


def test_live_observation_assessment_rejects_transport_as_signal():
    payload = {
        "assigned_load": 1,
        "modeled_processing_latency_ms": 40.0,
        "processing_latency_ms": 40.5,
        "signal_latency_ms": 45.0,
        "state_estimate": 1,
        "state_likelihood": latency_likelihood(40.5, 1),
    }

    report = assess_live_observation(payload, state=1, load=1)

    assert report["passed"] is False
    assert report["checks"]["signal_is_measured_processing"] is False


def test_live_observation_assessment_rejects_modeled_latency_below_baseline():
    measured = 40.5
    payload = {
        "assigned_load": 1,
        "modeled_processing_latency_ms": 39.9,
        "processing_latency_ms": measured,
        "signal_latency_ms": measured,
        "state_estimate": 1,
        "state_likelihood": latency_likelihood(measured, 1),
    }

    report = assess_live_observation(payload, state=1, load=1)

    assert report["passed"] is False
    assert report["checks"]["model_sample_within_four_sigma"] is False
