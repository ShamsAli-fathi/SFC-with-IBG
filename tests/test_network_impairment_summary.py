import json

import pytest

from scripts.network_impairment_summary import summarize_trace
from testbed.network_impairment import NetworkImpairment


def write_trace(path, *, impairment=None):
    if impairment is None:
        impairment = NetworkImpairment.enabled_with(
            delay_ms=10,
            jitter_ms=3,
        )
    metadata = {
        "seed": 2050,
        "configuration": {
            "flows": 2,
            "stages": 1,
            "replicas_per_stage": 2,
        },
        "network_impairment": impairment.to_dict(),
    }
    events = [
        {
            "event": "run_started",
            **metadata,
            "initial_replicas": [
                {
                    "stage": 1,
                    "replica_id": 1,
                    "state": 1,
                },
                {
                    "stage": 1,
                    "replica_id": 2,
                    "state": 4,
                },
            ],
        },
        {
            "event": "iteration_completed",
            **metadata,
            "iteration": 1,
            "slot_id": 1,
            "max_belief_delta": 0.2,
            "summary": {
                "placements": [
                    {"stage": 1, "flow_id": 1, "replica_id": 1},
                    {"stage": 1, "flow_id": 2, "replica_id": 2},
                ],
                "observations": [
                    {
                        "stage": 1,
                        "flow_id": 1,
                        "replica_id": 1,
                        "estimated_state": 2,
                    },
                    {
                        "stage": 1,
                        "flow_id": 2,
                        "replica_id": 2,
                        "estimated_state": 4,
                    },
                ],
                "beliefs": {
                    "1:1": [0.5, 0.2, 0.2, 0.1],
                    "1:2": [0.1, 0.1, 0.2, 0.6],
                },
                "metrics": {
                    "sla_violations": 1,
                    "realized_utility_total": 100.0,
                },
            },
        },
        {
            "event": "iteration_completed",
            **metadata,
            "iteration": 2,
            "slot_id": 2,
            "max_belief_delta": 0.02,
            "summary": {
                "placements": [
                    {"stage": 1, "flow_id": 1, "replica_id": 2},
                    {"stage": 1, "flow_id": 2, "replica_id": 2},
                ],
                "observations": [
                    {
                        "stage": 1,
                        "flow_id": 1,
                        "replica_id": 2,
                        "estimated_state": 4,
                    },
                    {
                        "stage": 1,
                        "flow_id": 2,
                        "replica_id": 2,
                        "estimated_state": 4,
                    },
                ],
                "beliefs": {
                    "1:1": [0.7, 0.1, 0.1, 0.1],
                    "1:2": [0.05, 0.05, 0.1, 0.8],
                },
                "metrics": {
                    "sla_violations": 0,
                    "realized_utility_total": 130.0,
                },
            },
        },
        {
            "event": "run_completed",
            **metadata,
            "iterations": 2,
            "reached_equilibrium": True,
        },
    ]
    path.write_text(
        "".join(json.dumps(event) + "\n" for event in events),
        encoding="utf-8",
    )


def test_summary_reports_convergence_and_better_replica_selection(tmp_path):
    path = tmp_path / "netem.jsonl"
    write_trace(path)

    report = summarize_trace(path, window=1)

    assert report["network_impairment"]["enabled"] is True
    assert report["completed_slots"] == 2
    assert report["reached_equilibrium"] is True
    assert report["selection"]["first_window_better_replica_share"] == 0.5
    assert report["selection"]["final_window_better_replica_share"] == 1.0
    assert report["beliefs"] == {
        "first_slot_mean_true_state_posterior": 0.55,
        "final_slot_mean_true_state_posterior": pytest.approx(0.75),
        "final_max_belief_delta": 0.02,
    }
    assert report["selected_predictions"] == {
        "correct": 3,
        "total": 4,
        "accuracy": 0.75,
    }
    assert report["service_outcomes"]["final_sla_violations"] == 0
    assert report["service_outcomes"]["final_realized_utility_total"] == 130.0


def test_summary_rejects_trace_without_versioned_netem_metadata(tmp_path):
    path = tmp_path / "old.jsonl"
    write_trace(path)
    events = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    for event in events:
        event.pop("network_impairment")
    path.write_text(
        "".join(json.dumps(event) + "\n" for event in events),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="metadata must be an object"):
        summarize_trace(path)
