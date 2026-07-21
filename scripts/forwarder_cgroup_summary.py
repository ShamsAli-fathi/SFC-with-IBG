#!/usr/bin/env python3
"""Validate and summarize opt-in selected-forwarder cgroup slot deltas."""

import argparse
import json
import math
from pathlib import Path


SCHEMA_VERSION = "forwarder_cgroup_v1"
COUNTER_FIELDS = (
    "usage_usec_delta",
    "periods_delta",
    "throttled_periods_delta",
    "throttled_usec_delta",
)


def _read_events(path):
    with path.open(encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def _percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * fraction) - 1)
    return ordered[index]


def _distribution(values):
    if not values:
        return {"count": 0, "mean": None, "p50": None, "p95": None, "max": None}
    return {
        "count": len(values),
        "mean": sum(values) / len(values),
        "p50": _percentile(values, 0.50),
        "p95": _percentile(values, 0.95),
        "max": max(values),
    }


def _nonnegative_integer(value, name):
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


def _validate_slot(event):
    summary = event.get("summary", {})
    block = (summary.get("traffic") or {}).get("forwarder_cgroup")
    if not isinstance(block, dict):
        raise ValueError(
            f"slot {event.get('slot_id')} has no forwarder_cgroup_v1 data"
        )
    required = {
        "schema_version",
        "selection_scope",
        "before_snapshot_elapsed_ms",
        "after_snapshot_elapsed_ms",
        "snapshot_elapsed_ms",
        "forwarders",
        "totals",
    }
    if set(block) != required:
        raise ValueError("invalid forwarder cgroup summary fields")
    if block["schema_version"] != SCHEMA_VERSION:
        raise ValueError("unsupported forwarder cgroup schema")
    if block["selection_scope"] != "selected_forwarders_only":
        raise ValueError("forwarder cgroup data must be selected-forwarders-only")
    for field in (
        "before_snapshot_elapsed_ms",
        "after_snapshot_elapsed_ms",
        "snapshot_elapsed_ms",
    ):
        value = block[field]
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
            raise ValueError(f"{field} must be nonnegative")
    if not math.isclose(
        block["snapshot_elapsed_ms"],
        block["before_snapshot_elapsed_ms"]
        + block["after_snapshot_elapsed_ms"],
        abs_tol=1e-9,
    ):
        raise ValueError("forwarder cgroup snapshot overhead is inconsistent")

    forwarders = block["forwarders"]
    if not isinstance(forwarders, list) or not forwarders:
        raise ValueError("forwarder cgroup summary must contain selected forwarders")
    selected = {
        (item["stage"], item["replica_id"])
        for item in summary.get("placements", [])
    }
    observed = set()
    totals = {field: 0 for field in COUNTER_FIELDS}
    for item in forwarders:
        if not isinstance(item, dict):
            raise ValueError("forwarder cgroup entry must be an object")
        key = (item.get("stage"), item.get("replica_id"))
        if (
            not all(isinstance(value, int) and value > 0 for value in key)
            or key in observed
        ):
            raise ValueError("forwarder cgroup identities must be unique and positive")
        observed.add(key)
        if not isinstance(item.get("pod_name"), str) or not item["pod_name"]:
            raise ValueError("forwarder cgroup entry has no pod name")
        if not isinstance(item.get("endpoint"), str) or not item["endpoint"]:
            raise ValueError("forwarder cgroup entry has no endpoint")
        for field in ("route_requests", "source_pair_requests"):
            _nonnegative_integer(item.get(field), field)
        if item["route_requests"] < 1:
            raise ValueError("forwarder route request count must be positive")
        for field in COUNTER_FIELDS:
            totals[field] += _nonnegative_integer(item.get(field), field)
        before = item.get("before")
        after = item.get("after")
        if not isinstance(before, dict) or not isinstance(after, dict):
            raise ValueError("forwarder cgroup entry requires raw snapshots")
        for field in ("usage_usec", "nr_periods", "nr_throttled", "throttled_usec"):
            if _nonnegative_integer(after.get(field), field) < _nonnegative_integer(
                before.get(field), field
            ):
                raise ValueError("forwarder cgroup counter decreased within slot")
    if observed != selected:
        raise ValueError("forwarder cgroup entries do not match selected forwarders")
    if block["totals"] != totals:
        raise ValueError("forwarder cgroup totals do not match per-forwarder deltas")
    return block


def summarize_trace(path):
    events = _read_events(path)
    started = [event for event in events if event.get("event") == "run_started"]
    iterations = [
        event for event in events if event.get("event") == "iteration_completed"
    ]
    if len(started) != 1 or not iterations:
        raise ValueError(f"expected one run with completed iterations: {path}")
    if started[0].get("forwarder_cgroup_diagnostics") is not True:
        raise ValueError(f"trace did not enable forwarder cgroup diagnostics: {path}")
    slots = []
    for event in iterations:
        block = _validate_slot(event)
        totals = block["totals"]
        slots.append(
            {
                "slot_id": event["slot_id"],
                "selected_forwarders": len(block["forwarders"]),
                "usage_ms": totals["usage_usec_delta"] / 1000,
                "throttled_periods": totals["throttled_periods_delta"],
                "throttled_ms": totals["throttled_usec_delta"] / 1000,
                "snapshot_elapsed_ms": block["snapshot_elapsed_ms"],
            }
        )
    return {
        "trace": str(path),
        "configuration": started[0].get("configuration"),
        "learning_signal_mode": started[0].get("learning_signal_mode"),
        "slots": slots,
        "usage_ms": _distribution([item["usage_ms"] for item in slots]),
        "throttled_periods": _distribution(
            [item["throttled_periods"] for item in slots]
        ),
        "throttled_ms": _distribution([item["throttled_ms"] for item in slots]),
        "snapshot_elapsed_ms": _distribution(
            [item["snapshot_elapsed_ms"] for item in slots]
        ),
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Validate selected-forwarder cgroup-v2 slot deltas and summarize "
            "their runtime evidence"
        )
    )
    parser.add_argument("traces", type=Path, nargs="+")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    report = {
        "schema_version": SCHEMA_VERSION,
        "runs": [summarize_trace(path) for path in args.traces],
    }
    print(f"FORWARDER_CGROUP_SUMMARY={json.dumps(report, sort_keys=True)}")


if __name__ == "__main__":
    main()
