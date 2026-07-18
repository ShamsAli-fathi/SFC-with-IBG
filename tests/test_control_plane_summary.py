import json

import pytest

from scripts.control_plane_summary import summarize_trace
from learning_signal import build_learning_signal_snapshot


def snapshot(active, wait, payload):
    return {
        "schema": "control_plane_v1",
        "timing_ms": {
            "discovery": 1.0,
            "admission": active - 2.0,
            "feedback": 2.0,
            "active": active,
            "data_plane_wait": wait,
        },
        "cpu_ms": {
            "discovery": 0.5,
            "admission": 2.0,
            "feedback": 1.0,
            "active": 3.0,
        },
        "payload_bytes": {
            "kubernetes_discovery_tx": 0,
            "kubernetes_discovery_rx": payload - 30,
            "route_command_tx": 10,
            "selected_telemetry_rx": 20,
            "belief_tx": 0,
            "belief_rx": 0,
            "total": payload,
        },
        "messages": {
            "kubernetes_discovery_tx": 3,
            "kubernetes_discovery_rx": 3,
            "route_command_tx": 1,
            "selected_telemetry_rx": 1,
            "belief_tx": 0,
            "belief_rx": 0,
            "total": 8,
        },
    }


def test_trace_summary_reports_per_run_median_and_p95(tmp_path):
    trace = tmp_path / "run.jsonl"
    events = [
        {
            "event": "iteration_completed",
            "summary": {
                "datapath_mode": "kernel",
                "configuration": {"flows": 3, "stages": 3, "replicas_per_stage": 5},
                "control_plane": snapshot(5.0, 10.0, 100),
            },
        },
        {
            "event": "iteration_completed",
            "summary": {
                "datapath_mode": "kernel",
                "configuration": {"flows": 3, "stages": 3, "replicas_per_stage": 5},
                "control_plane": snapshot(7.0, 14.0, 200),
            },
        },
        {"event": "run_completed", "reached_equilibrium": True},
    ]
    trace.write_text(
        "".join(json.dumps(event) + "\n" for event in events),
        encoding="utf-8",
    )

    report = summarize_trace(trace)

    assert report["iterations"] == 2
    assert report["metrics"]["active_ms"] == {
        "median": 6.0,
        "p95": pytest.approx(6.9),
    }
    assert report["metrics"]["data_plane_wait_ms"]["median"] == 12.0
    assert report["metrics"]["payload_bytes"]["median"] == 150.0
    assert report["metrics"]["selected_telemetry_rx_bytes"]["median"] == 20.0
    assert report["metrics"]["messages"] == {"median": 8.0, "p95": 8.0}


def test_trace_summary_reports_separate_learning_signal_footprint(tmp_path):
    trace = tmp_path / "run.jsonl"
    observations = [
        {
            "stage": stage,
            "flow_id": flow_id,
            "replica_id": stage,
            "congestion": 1,
            "signal": 10.0 + flow_id,
            "likelihood": [0.1, 0.2, 0.3, 0.4],
        }
        for stage in range(1, 4)
        for flow_id in range(1, 4)
    ]
    learning_signal = build_learning_signal_snapshot(observations)
    events = [
        {
            "event": "iteration_completed",
            "summary": {
                "datapath_mode": "kernel",
                "configuration": {
                    "flows": 3,
                    "stages": 3,
                    "replicas_per_stage": 5,
                },
                "observations": observations,
                "control_plane": snapshot(5.0, 10.0, 100),
                "learning_signal": learning_signal,
            },
        },
        {"event": "run_completed", "reached_equilibrium": True},
    ]
    trace.write_text(
        "".join(json.dumps(event) + "\n" for event in events),
        encoding="utf-8",
    )

    report = summarize_trace(trace)

    metrics = report["metrics"]
    assert metrics["learning_signal_records"] == {
        "median": 9.0,
        "p95": 9.0,
    }
    assert metrics["learning_signal_logical_payload_bytes"]["median"] == (
        learning_signal["logical_payload_bytes"]
    )
    assert metrics["learning_signal_mean_bytes_per_selected_hop"][
        "median"
    ] == pytest.approx(learning_signal["mean_bytes_per_selected_hop"])
