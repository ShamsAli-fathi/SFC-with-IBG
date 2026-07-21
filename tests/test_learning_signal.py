import pytest

from learning_signal import (
    LEARNING_SIGNAL_FIELDS,
    LEARNING_SIGNAL_SCHEMA,
    build_learning_signal_snapshot,
    validate_learning_signal_snapshot,
)
from ports import Observation


def observation(stage, flow_id, replica_id, *, measured=10.5, state=4):
    return Observation(
        stage=stage,
        flow_id=flow_id,
        replica_id=replica_id,
        congestion=2,
        signal=11.25,
        likelihood=(0.01, 0.04, 0.15, 0.8),
        measured_latency_ms=measured,
        estimated_state=state,
        observation_jitter_ms=11.25 - measured,
    )


def test_learning_signal_is_a_selected_observation_projection():
    observations = [
        observation(stage, flow_id, replica_id=(stage + flow_id) % 5 + 1)
        for stage in range(1, 4)
        for flow_id in range(1, 3)
    ]

    snapshot = build_learning_signal_snapshot(observations)

    assert snapshot["schema"] == LEARNING_SIGNAL_SCHEMA
    assert snapshot["selection_scope"] == "selected_hops_only"
    assert snapshot["fields"] == list(LEARNING_SIGNAL_FIELDS)
    assert snapshot["records"] == 6
    assert snapshot["logical_payload_bytes"] > 0
    assert snapshot["mean_bytes_per_selected_hop"] == pytest.approx(
        snapshot["logical_payload_bytes"] / 6
    )
    validate_learning_signal_snapshot(snapshot, expected_records=2 * 3)


def test_diagnostic_telemetry_does_not_change_learning_signal_footprint():
    baseline = [observation(1, 1, 2, measured=10.5, state=4)]
    changed_diagnostics = [observation(1, 1, 2, measured=9.5, state=1)]

    assert build_learning_signal_snapshot(
        baseline
    ) == build_learning_signal_snapshot(changed_diagnostics)


def test_learning_signal_validation_enforces_selected_hop_count():
    snapshot = build_learning_signal_snapshot(
        [observation(1, 1, 2), observation(2, 1, 3)]
    )

    with pytest.raises(ValueError, match="flows times configured stages"):
        validate_learning_signal_snapshot(snapshot, expected_records=3)


def test_learning_signal_rejects_duplicate_flow_stage_records():
    with pytest.raises(ValueError, match="duplicate stage/flow"):
        build_learning_signal_snapshot(
            [observation(1, 1, 2), observation(1, 1, 3)]
        )
