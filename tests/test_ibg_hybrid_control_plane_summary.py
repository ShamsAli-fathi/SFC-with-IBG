import json

import pytest

from IBG_Hybrid.control_plane_footprint import HYBRID_CONTROL_PLANE_DATA_SCHEMA
from scripts.hybrid_control_plane_summary import main, summarize_trace


def _snapshot(value):
    payload = {
        "kubernetes_discovery_tx": 0,
        "kubernetes_discovery_rx": value,
        "route_command_tx": value + 10,
        "selected_telemetry_rx": value + 20,
        "belief_tx": 0,
        "belief_rx": 0,
    }
    messages = {
        "kubernetes_discovery_tx": 1,
        "kubernetes_discovery_rx": 1,
        "route_command_tx": 1,
        "selected_telemetry_rx": 1,
        "belief_tx": 0,
        "belief_rx": 0,
    }
    return {
        "schema": HYBRID_CONTROL_PLANE_DATA_SCHEMA,
        "timing_ms": {
            "discovery": value / 100,
            "admission": value / 10,
            "feedback": value / 20,
            "active": value / 10 + value / 20,
            "data_plane_wait": value / 5,
        },
        "payload_bytes": {**payload, "total": sum(payload.values())},
        "messages": {**messages, "total": sum(messages.values())},
    }


def _trace(path, *, second_footprint=True):
    second = {
        "event": "iteration_completed",
        "iteration": 2,
    }
    if second_footprint:
        second["control_plane"] = _snapshot(200)
    events = [
        {
            "event": "run_started",
            "configuration": {
                "num_flows": 2,
                "num_stages": 3,
                "num_replicas": 1,
                "stage_budget": 2,
            },
        },
        {
            "event": "iteration_completed",
            "iteration": 1,
            "control_plane": _snapshot(100),
        },
        second,
        {"event": "run_completed", "iterations": 2},
    ]
    path.write_text(
        "".join(json.dumps(event) + "\n" for event in events),
        encoding="utf-8",
    )


def test_summary_reports_wall_time_every_data_category_and_exact_totals(tmp_path):
    path = tmp_path / "trace.jsonl"
    _trace(path)

    report = summarize_trace(path)

    assert report["iterations"] == 2
    metrics = report["metrics"]
    assert metrics["admission_time_ms"] == {
        "median": 15.0,
        "p95": pytest.approx(19.5),
    }
    assert metrics["data_plane_wait_time_ms"]["median"] == 30.0
    assert metrics["kubernetes_discovery_rx_bytes"] == {
        "median": 150.0,
        "p95": pytest.approx(195.0),
    }
    assert metrics["belief_tx_bytes"] == {"median": 0.0, "p95": 0.0}
    assert metrics["belief_exchange_total_bytes"] == {
        "median": 0.0,
        "p95": 0.0,
    }
    assert metrics["control_plane_payload_total_bytes"]["median"] == 480.0
    assert metrics["control_plane_messages_total"] == {
        "median": 4.0,
        "p95": 4.0,
    }
    assert not any("cpu" in name for name in metrics)


def test_summary_rejects_mixed_enabled_and_disabled_trace(tmp_path):
    path = tmp_path / "trace.jsonl"
    _trace(path, second_footprint=False)

    with pytest.raises(ValueError, match="no enabled"):
        summarize_trace(path)


def test_summary_cli_emits_hybrid_data_schema(tmp_path, capsys):
    path = tmp_path / "trace.jsonl"
    _trace(path)

    assert main([str(path)]) == 0
    prefix, payload = capsys.readouterr().out.strip().split("=", 1)
    assert prefix == "HYBRID_CONTROL_PLANE_DATA_SUMMARY"
    assert json.loads(payload)["footprint_schema"] == (
        HYBRID_CONTROL_PLANE_DATA_SCHEMA
    )
