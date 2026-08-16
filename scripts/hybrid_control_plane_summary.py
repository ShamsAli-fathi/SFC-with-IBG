#!/usr/bin/env python3
"""Summarize data-only Hybrid controller footprint traces."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from IBG_Hybrid.control_plane_footprint import (
    HYBRID_CONTROL_PLANE_DATA_SCHEMA,
    HYBRID_CONTROL_PLANE_MESSAGE_FIELDS,
    HYBRID_CONTROL_PLANE_PAYLOAD_FIELDS,
    validate_hybrid_control_plane_data_snapshot,
)


HYBRID_CONTROL_PLANE_SUMMARY_SCHEMA = (
    "ibg-hybrid-control-plane-data-summary-v1"
)


def _percentile(values: Sequence[int], percentile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return float(ordered[lower] + (ordered[upper] - ordered[lower]) * fraction)


def _summary(values: Sequence[int]) -> dict[str, float]:
    if not values:
        raise ValueError("Hybrid footprint summary requires at least one value")
    return {
        "median": _percentile(values, 0.50),
        "p95": _percentile(values, 0.95),
    }


def summarize_trace(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as source:
        events = [json.loads(line) for line in source if line.strip()]
    started = [event for event in events if event.get("event") == "run_started"]
    iterations = [
        event for event in events if event.get("event") == "iteration_completed"
    ]
    completed = [event for event in events if event.get("event") == "run_completed"]
    if len(started) != 1 or not iterations or len(completed) != 1:
        raise ValueError(f"trace is not a completed Hybrid experiment: {path}")
    if completed[0].get("iterations") != len(iterations):
        raise ValueError(f"trace completion count is inconsistent: {path}")

    snapshots = []
    for expected_iteration, event in enumerate(iterations, start=1):
        if event.get("iteration") != expected_iteration:
            raise ValueError(f"trace iterations are not contiguous: {path}")
        snapshot = event.get("control_plane")
        if snapshot is None:
            raise ValueError(f"trace has no enabled Hybrid footprint data: {path}")
        snapshots.append(validate_hybrid_control_plane_data_snapshot(snapshot))

    metrics = {}
    for group, fields in (
        ("payload_bytes", HYBRID_CONTROL_PLANE_PAYLOAD_FIELDS),
        ("messages", HYBRID_CONTROL_PLANE_MESSAGE_FIELDS),
    ):
        suffix = "bytes" if group == "payload_bytes" else "messages"
        for field in fields:
            metrics[f"{field}_{suffix}"] = _summary(
                [snapshot[group][field] for snapshot in snapshots]
            )
        metrics[f"belief_exchange_total_{suffix}"] = _summary(
            [
                snapshot[group]["belief_tx"] + snapshot[group]["belief_rx"]
                for snapshot in snapshots
            ]
        )
        total_name = (
            "control_plane_payload_total_bytes"
            if group == "payload_bytes"
            else "control_plane_messages_total"
        )
        metrics[total_name] = _summary(
            [snapshot[group]["total"] for snapshot in snapshots]
        )

    return {
        "trace": str(path),
        "configuration": started[0].get("configuration"),
        "iterations": len(iterations),
        "metrics": metrics,
    }


def parse_args(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate and summarize data-only IBG-Hybrid controller payload "
            "and message footprint traces"
        )
    )
    parser.add_argument("traces", nargs="+", type=Path)
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_args(arguments)
    report = {
        "schema": HYBRID_CONTROL_PLANE_SUMMARY_SCHEMA,
        "footprint_schema": HYBRID_CONTROL_PLANE_DATA_SCHEMA,
        "runs": [summarize_trace(path) for path in args.traces],
    }
    print(
        "HYBRID_CONTROL_PLANE_DATA_SUMMARY="
        + json.dumps(report, sort_keys=True, separators=(",", ":"))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
