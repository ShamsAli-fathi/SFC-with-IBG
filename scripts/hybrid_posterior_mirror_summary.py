#!/usr/bin/env python3
"""Validate and summarize opt-in Hybrid posterior-mirror traces."""

from __future__ import annotations

import argparse
import json
from math import isfinite
from pathlib import Path
from typing import Mapping, Sequence

from IBG_Hybrid.contracts import ReplicaChoice
from IBG_Hybrid.posterior_mirror import (
    HYBRID_POSTERIOR_MIRROR_SCHEMA,
    validate_hybrid_posterior_mirror_snapshot,
    validate_posterior_mirror_provenance,
)


HYBRID_POSTERIOR_MIRROR_SUMMARY_SCHEMA = (
    "ibg-hybrid-posterior-mirror-summary-v1"
)
HYBRID_POSTERIOR_MIRROR_SUMMARY_BOUNDARY = (
    "instrumented non-authoritative HTTP application payload copied across "
    "a Pod boundary; excludes HTTP/TCP/IP/Ethernet wire overhead and does not "
    "represent required operational distributed-belief traffic"
)


def _percentile(values: Sequence[int], percentile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return float(ordered[lower] + (ordered[upper] - ordered[lower]) * fraction)


def _metric_summary(values: Sequence[int]) -> dict[str, object]:
    if not values:
        raise ValueError("posterior-mirror summary requires completed values")
    return {
        "per_timeslot": list(values),
        "total": sum(values),
        "median": _percentile(values, 0.50),
        "p95": _percentile(values, 0.95),
    }


def _beliefs_after(value: object) -> dict[ReplicaChoice, tuple[float, ...]]:
    if not isinstance(value, Mapping) or not value:
        raise ValueError("posterior-mirror trace lacks completed beliefs")
    beliefs = {}
    for identity, posterior in value.items():
        if not isinstance(identity, str) or identity.count(":") != 1:
            raise ValueError("posterior-mirror trace has invalid belief identity")
        try:
            stage, replica = (int(item) for item in identity.split(":"))
        except ValueError as error:
            raise ValueError(
                "posterior-mirror trace has invalid belief identity"
            ) from error
        if stage < 1 or replica < 1:
            raise ValueError("posterior-mirror trace has invalid belief identity")
        if (
            not isinstance(posterior, list)
            or len(posterior) != 4
            or any(
                isinstance(item, bool)
                or not isinstance(item, (int, float))
                or not isfinite(float(item))
                or item < 0
                for item in posterior
            )
        ):
            raise ValueError("posterior-mirror trace has invalid belief vector")
        choice = ReplicaChoice(stage, replica)
        if choice in beliefs:
            raise ValueError("posterior-mirror trace has duplicate belief identity")
        beliefs[choice] = tuple(float(item) for item in posterior)
    return beliefs


def _updated_choices(value: object) -> tuple[ReplicaChoice, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError("posterior-mirror trace lacks selected observations")
    choices = []
    for observation in value:
        if not isinstance(observation, Mapping):
            raise ValueError("posterior-mirror trace has invalid observation")
        stage = observation.get("stage")
        replica = observation.get("replica")
        if (
            isinstance(stage, bool)
            or not isinstance(stage, int)
            or stage < 1
            or isinstance(replica, bool)
            or not isinstance(replica, int)
            or replica < 1
        ):
            raise ValueError("posterior-mirror trace has invalid observation")
        choices.append(ReplicaChoice(stage, replica))
    return tuple(choices)


def summarize_trace(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as source:
        events = [json.loads(line) for line in source if line.strip()]
    if any(not isinstance(event, Mapping) for event in events):
        raise ValueError(f"trace contains a non-object event: {path}")
    started = [event for event in events if event.get("event") == "run_started"]
    iterations = [
        event for event in events if event.get("event") == "iteration_completed"
    ]
    completed = [event for event in events if event.get("event") == "run_completed"]
    if len(started) != 1 or not iterations or len(completed) != 1:
        raise ValueError(f"trace is not a completed Hybrid experiment: {path}")
    if completed[0].get("iterations") != len(iterations):
        raise ValueError(f"trace completion count is inconsistent: {path}")

    for event in events:
        validate_posterior_mirror_provenance(
            event.get("posterior_mirror_configuration"),
            expected_enabled=True,
        )

    snapshots = []
    mirror_run_id = None
    for expected_iteration, event in enumerate(iterations, start=1):
        if event.get("iteration") != expected_iteration:
            raise ValueError(f"trace iterations are not contiguous: {path}")
        snapshot = event.get("posterior_mirror")
        if snapshot is None:
            raise ValueError(f"trace lacks enabled posterior-mirror data: {path}")
        validate_hybrid_posterior_mirror_snapshot(
            snapshot,
            expected_slot_id=event.get("slot_id", expected_iteration),
            expected_beliefs=_beliefs_after(event.get("beliefs_after")),
            expected_updated_choices=_updated_choices(event.get("observations")),
        )
        current_run_id = snapshot["run_id"]
        if mirror_run_id is None:
            mirror_run_id = current_run_id
        elif current_run_id != mirror_run_id:
            raise ValueError(f"posterior-mirror run identity drifted: {path}")
        snapshots.append(snapshot)

    vector_values = [
        snapshot["payload_bytes"]["posterior_vectors"]
        for snapshot in snapshots
    ]
    body_values = [
        snapshot["payload_bytes"]["application_bodies"]
        for snapshot in snapshots
    ]
    message_values = [
        snapshot["messages"]["posterior_updates"]
        for snapshot in snapshots
    ]
    return {
        "trace": str(path),
        "configuration": started[0].get("configuration"),
        "iterations": len(iterations),
        "mirror_run_id": mirror_run_id,
        "measurement_boundary": HYBRID_POSTERIOR_MIRROR_SUMMARY_BOUNDARY,
        "metrics": {
            "posterior_vector_payload_bytes": _metric_summary(vector_values),
            "posterior_application_body_bytes": _metric_summary(body_values),
            "posterior_update_messages": _metric_summary(message_values),
        },
    }


def parse_args(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate and summarize instrumented IBG-Hybrid posterior-mirror "
            "application payloads"
        )
    )
    parser.add_argument("traces", nargs="+", type=Path)
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_args(arguments)
    report = {
        "schema": HYBRID_POSTERIOR_MIRROR_SUMMARY_SCHEMA,
        "posterior_mirror_schema": HYBRID_POSTERIOR_MIRROR_SCHEMA,
        "measurement_boundary": HYBRID_POSTERIOR_MIRROR_SUMMARY_BOUNDARY,
        "runs": [summarize_trace(path) for path in args.traces],
    }
    print(
        "HYBRID_POSTERIOR_MIRROR_SUMMARY="
        + json.dumps(report, sort_keys=True, separators=(",", ":"))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
