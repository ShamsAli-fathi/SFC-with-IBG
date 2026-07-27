#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from statistics import mean
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from testbed.network_impairment import NetworkImpairment


STATE_NAMES = {
    1: "bad",
    2: "degraded",
    3: "good",
    4: "excellent",
}


def _read_events(path):
    events = []
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"invalid JSON at {path}:{line_number}"
                ) from error
    return events


def _one(events, event_name, path):
    matches = [event for event in events if event.get("event") == event_name]
    if len(matches) != 1:
        raise ValueError(
            f"{path} must contain exactly one {event_name} event"
        )
    return matches[0]


def _state_counts(placements, state_by_replica):
    counts = {name: 0 for name in STATE_NAMES.values()}
    for placement in placements:
        key = (int(placement["stage"]), int(placement["replica_id"]))
        try:
            state = state_by_replica[key]
        except KeyError as error:
            raise ValueError(
                f"placement references unknown replica {key}"
            ) from error
        counts[STATE_NAMES[state]] += 1
    return counts


def _mean_counts(items):
    return {
        name: mean(item[name] for item in items)
        for name in STATE_NAMES.values()
    }


def _better_share(counts):
    total = sum(counts.values())
    if total == 0:
        raise ValueError("selected-state counts cannot be empty")
    return (counts["good"] + counts["excellent"]) / total


def summarize_trace(path, *, window=5):
    if window < 1:
        raise ValueError("window must be positive")
    events = _read_events(path)
    started = _one(events, "run_started", path)
    completed = _one(events, "run_completed", path)
    iterations = [
        event
        for event in events
        if event.get("event") == "iteration_completed"
    ]
    if not iterations:
        raise ValueError(f"{path} has no completed slots")
    if completed.get("iterations") != len(iterations):
        raise ValueError(f"{path} completed-slot count is inconsistent")

    impairment = NetworkImpairment.from_dict(
        started.get("network_impairment")
    )
    if any(
        event.get("network_impairment") != impairment.to_dict()
        for event in (*iterations, completed)
    ):
        raise ValueError(
            f"{path} changes network-impairment metadata within one run"
        )

    state_by_replica = {}
    for replica in started.get("initial_replicas", []):
        state = int(replica["state"])
        if state not in STATE_NAMES:
            raise ValueError(f"{path} contains an unsupported replica state")
        state_by_replica[
            (int(replica["stage"]), int(replica["replica_id"]))
        ] = state

    slot_reports = []
    correct_predictions = 0
    prediction_count = 0
    true_state_posteriors = []
    for event in iterations:
        summary = event["summary"]
        placements = summary["placements"]
        observations = summary["observations"]
        placement_keys = {
            (int(item["stage"]), int(item["flow_id"]), int(item["replica_id"]))
            for item in placements
        }
        observation_keys = {
            (int(item["stage"]), int(item["flow_id"]), int(item["replica_id"]))
            for item in observations
        }
        if placement_keys != observation_keys:
            raise ValueError(
                f"{path} placement and selected-observation sets differ"
            )

        counts = _state_counts(placements, state_by_replica)
        beliefs = summary["beliefs"]
        slot_true_posteriors = []
        for key, state in state_by_replica.items():
            belief_key = f"{key[0]}:{key[1]}"
            values = beliefs[belief_key]
            slot_true_posteriors.append(float(values[state - 1]))
        true_state_posteriors.append(mean(slot_true_posteriors))

        for observation in observations:
            key = (
                int(observation["stage"]),
                int(observation["replica_id"]),
            )
            estimated_state = observation.get("estimated_state")
            if estimated_state is not None:
                prediction_count += 1
                correct_predictions += (
                    int(estimated_state) == state_by_replica[key]
                )

        metrics = summary["metrics"]
        slot_reports.append(
            {
                "slot_id": int(event["slot_id"]),
                "iteration": int(event["iteration"]),
                "max_belief_delta": float(event["max_belief_delta"]),
                "mean_true_state_posterior": true_state_posteriors[-1],
                "selected_state_counts": counts,
                "better_replica_share": _better_share(counts),
                "sla_violations": int(metrics["sla_violations"]),
                "realized_utility_total": float(
                    metrics["realized_utility_total"]
                ),
            }
        )

    window = min(window, len(slot_reports))
    first = slot_reports[:window]
    final = slot_reports[-window:]
    first_counts = _mean_counts(
        [item["selected_state_counts"] for item in first]
    )
    final_counts = _mean_counts(
        [item["selected_state_counts"] for item in final]
    )
    return {
        "trace": str(path),
        "configuration": started["configuration"],
        "seed": int(started["seed"]),
        "network_impairment": impairment.to_dict(),
        "completed_slots": len(slot_reports),
        "reached_equilibrium": bool(completed["reached_equilibrium"]),
        "selection": {
            "window_slots": window,
            "first_window_mean_state_counts": first_counts,
            "final_window_mean_state_counts": final_counts,
            "first_window_better_replica_share": mean(
                item["better_replica_share"] for item in first
            ),
            "final_window_better_replica_share": mean(
                item["better_replica_share"] for item in final
            ),
        },
        "beliefs": {
            "first_slot_mean_true_state_posterior": (
                true_state_posteriors[0]
            ),
            "final_slot_mean_true_state_posterior": (
                true_state_posteriors[-1]
            ),
            "final_max_belief_delta": slot_reports[-1][
                "max_belief_delta"
            ],
        },
        "selected_predictions": {
            "correct": correct_predictions,
            "total": prediction_count,
            "accuracy": (
                correct_predictions / prediction_count
                if prediction_count
                else None
            ),
        },
        "service_outcomes": {
            "mean_sla_violations_per_slot": mean(
                item["sla_violations"] for item in slot_reports
            ),
            "final_sla_violations": slot_reports[-1]["sla_violations"],
            "first_realized_utility_total": slot_reports[0][
                "realized_utility_total"
            ],
            "final_realized_utility_total": slot_reports[-1][
                "realized_utility_total"
            ],
        },
        "slots": slot_reports,
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Validate and summarize matched netem_v1 IBG-Exact traces."
        )
    )
    parser.add_argument("traces", nargs="+", type=Path)
    parser.add_argument(
        "--window",
        type=int,
        default=5,
        help="number of first/final completed slots used for selection summaries",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    report = {
        "schema": "network_impairment_summary_v1",
        "runs": [
            summarize_trace(path, window=args.window)
            for path in args.traces
        ],
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
