#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
IBG_DIR = ROOT / "IBG"
if str(IBG_DIR) not in sys.path:
    sys.path.insert(0, str(IBG_DIR))

from control_plane import validate_control_plane_snapshot
from learning_signal import validate_learning_signal_snapshot


SUMMARY_FIELDS = {
    "admission_ms": ("timing_ms", "admission"),
    "feedback_ms": ("timing_ms", "feedback"),
    "active_ms": ("timing_ms", "active"),
    "data_plane_wait_ms": ("timing_ms", "data_plane_wait"),
    "active_cpu_ms": ("cpu_ms", "active"),
    "payload_bytes": ("payload_bytes", "total"),
    "selected_telemetry_rx_bytes": (
        "payload_bytes",
        "selected_telemetry_rx",
    ),
    "messages": ("messages", "total"),
}


def percentile_summary(values):
    array = np.asarray(values, dtype=float)
    return {
        "median": float(np.percentile(array, 50)),
        "p95": float(np.percentile(array, 95)),
    }


def summarize_trace(path):
    events = []
    with path.open(encoding="utf-8") as source:
        for line in source:
            if line.strip():
                events.append(json.loads(line))
    iterations = [
        event for event in events if event.get("event") == "iteration_completed"
    ]
    completed = [event for event in events if event.get("event") == "run_completed"]
    if not iterations or len(completed) != 1:
        raise ValueError(f"trace is not a completed experiment: {path}")

    configuration = iterations[0]["summary"]["configuration"]
    stages = int(configuration["stages"])
    flows = int(configuration["flows"])
    snapshots = []
    learning_snapshots = []
    for event in iterations:
        summary = event.get("summary", {})
        snapshot = summary.get("control_plane")
        if snapshot is None:
            raise ValueError(f"trace has no control_plane_v1 data: {path}")
        snapshots.append(
            validate_control_plane_snapshot(snapshot, expected_stages=stages)
        )
        learning_snapshot = summary.get("learning_signal")
        if learning_snapshot is not None:
            observations = summary.get("observations")
            if not isinstance(observations, list):
                raise ValueError(
                    f"trace learning signal has no observation records: {path}"
                )
            learning_snapshots.append(
                validate_learning_signal_snapshot(
                    learning_snapshot,
                    expected_records=flows * stages,
                    observations=observations,
                )
            )

    if learning_snapshots and len(learning_snapshots) != len(iterations):
        raise ValueError(f"trace mixes learning-signal schemas: {path}")

    metrics = {
        output_name: percentile_summary(
            [snapshot[group][field] for snapshot in snapshots]
        )
        for output_name, (group, field) in SUMMARY_FIELDS.items()
    }
    if learning_snapshots:
        metrics.update(
            {
                "learning_signal_logical_payload_bytes": percentile_summary(
                    [
                        snapshot["logical_payload_bytes"]
                        for snapshot in learning_snapshots
                    ]
                ),
                "learning_signal_records": percentile_summary(
                    [snapshot["records"] for snapshot in learning_snapshots]
                ),
                "learning_signal_mean_bytes_per_selected_hop": (
                    percentile_summary(
                        [
                            snapshot["mean_bytes_per_selected_hop"]
                            for snapshot in learning_snapshots
                        ]
                    )
                ),
            }
        )

    return {
        "trace": str(path),
        "datapath_mode": iterations[0]["summary"]["datapath_mode"],
        "configuration": configuration,
        "iterations": len(iterations),
        "metrics": metrics,
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Validate control_plane_v1 and optional learning_signal_v1 "
            "measurements and report per-run median/p95 values"
        )
    )
    parser.add_argument("traces", nargs="+", type=Path)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    report = {
        "schema": "control_plane_v1",
        "runs": [summarize_trace(path) for path in args.traces],
    }
    print(f"CONTROL_PLANE_SUMMARY={json.dumps(report, sort_keys=True)}")


if __name__ == "__main__":
    main()
