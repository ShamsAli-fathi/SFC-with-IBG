#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
import statistics
import sys


ROOT = Path(__file__).resolve().parents[1]
IBG_DIR = ROOT / "IBG"
if str(IBG_DIR) not in sys.path:
    sys.path.insert(0, str(IBG_DIR))

from solver_resource import (
    SOLVER_RESOURCE_SCHEMA,
    validate_solver_resource_snapshot,
)


def percentile(values, percentile_value):
    ordered = sorted(values)
    if not ordered:
        raise ValueError("cannot summarize an empty value set")
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * percentile_value / 100.0
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return float(
        ordered[lower] + (ordered[upper] - ordered[lower]) * fraction
    )


def distribution(values):
    return {
        "mean": float(statistics.fmean(values)),
        "median": percentile(values, 50),
        "p95": percentile(values, 95),
        "maximum": int(max(values)),
    }


def summarize_trace(path):
    events = []
    with path.open(encoding="utf-8") as source:
        for line in source:
            if line.strip():
                events.append(json.loads(line))
    started = [event for event in events if event.get("event") == "run_started"]
    iterations = [
        event for event in events if event.get("event") == "iteration_completed"
    ]
    completed = [
        event for event in events if event.get("event") == "run_completed"
    ]
    if len(started) != 1 or not iterations or len(completed) != 1:
        raise ValueError(f"trace is not a completed experiment: {path}")
    if started[0].get("memory_diagnostics") is not True:
        raise ValueError(f"trace was not launched with --memory 1: {path}")

    configuration = started[0].get("configuration")
    if not isinstance(configuration, dict):
        raise ValueError(f"trace has no configuration: {path}")
    stages = int(configuration["stages"])
    snapshots = []
    for event in iterations:
        snapshot = event.get("summary", {}).get("solver_resource")
        if snapshot is None:
            raise ValueError(f"trace has no solver_resource_v1 data: {path}")
        snapshots.append(
            validate_solver_resource_snapshot(
                snapshot,
                expected_stages=stages,
            )
        )

    rss_fields = (
        "before_admission",
        "peak_during_slot",
        "after_feedback",
        "peak_incremental_working_memory",
    )
    rss = {
        field: distribution(
            [snapshot["rss_bytes"][field] for snapshot in snapshots]
        )
        for field in rss_fields
    }
    rss_mib = {
        field: {
            key: value / (1024 * 1024)
            for key, value in rss[field].items()
        }
        for field in rss_fields
    }
    exact_policy = {
        "peak_memo_entries": distribution(
            [
                snapshot["exact_policy"]["peak_memo_entries"]
                for snapshot in snapshots
            ]
        ),
        "post_embedding_residual_entries": distribution(
            [
                snapshot["exact_policy"]["post_embedding_residual_entries"]
                for snapshot in snapshots
            ]
        ),
        "stages": {},
    }
    for stage in range(1, stages + 1):
        records = [
            next(
                record
                for record in snapshot["exact_policy"]["stages"]
                if record["stage"] == stage
            )
            for snapshot in snapshots
        ]
        exact_policy["stages"][str(stage)] = {
            "peak_memo_entries": distribution(
                [record["peak_memo_entries"] for record in records]
            ),
            "post_embedding_residual_entries": distribution(
                [record["post_embedding_residual_entries"] for record in records]
            ),
        }

    return {
        "trace": str(path),
        "datapath_mode": started[0].get("datapath_mode"),
        "configuration": configuration,
        "iterations": len(iterations),
        "rss_bytes": rss,
        "rss_mib": rss_mib,
        "exact_policy": exact_policy,
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Validate solver_resource_v1 traces and summarize controller RSS "
            "and exact memo-cache entries"
        )
    )
    parser.add_argument("traces", nargs="+", type=Path)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    report = {
        "schema": SOLVER_RESOURCE_SCHEMA,
        "runs": [summarize_trace(path) for path in args.traces],
    }
    print(f"SOLVER_RESOURCE_SUMMARY={json.dumps(report, sort_keys=True)}")


if __name__ == "__main__":
    main()
