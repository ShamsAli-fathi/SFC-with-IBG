#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
import sys

import httpx


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "IBG"))

from calibration import (
    MINIMUM_LIVE_CLASSIFICATION_ACCURACY,
    assess_live_observation,
    build_calibration_report,
)
from latency_model import require_state_parameters


def collect_live_checks(base_url, state, loads, repetitions, timeout_seconds):
    checks = []
    classification_accuracy_by_load = {}
    with httpx.Client(
        base_url=base_url.rstrip("/"),
        timeout=timeout_seconds,
    ) as client:
        health = client.get("/health")
        health.raise_for_status()
        flow_id = 0
        for load in loads:
            correct = 0
            for _ in range(repetitions):
                flow_id += 1
                response = client.post(
                    "/process",
                    json={
                        "slot_id": 1,
                        "flow_id": flow_id,
                        "assigned_load": load,
                    },
                )
                response.raise_for_status()
                observation = assess_live_observation(
                    response.json(),
                    state=state,
                    load=load,
                )
                checks.append(observation)
                correct += observation["state_estimate"] == state
            classification_accuracy_by_load[load] = correct / repetitions
    minimum_classification_accuracy = min(
        classification_accuracy_by_load.values()
    )
    return {
        "base_url": base_url,
        "configured_hidden_state": state,
        "loads": loads,
        "repetitions_per_load": repetitions,
        "classification_accuracy_by_load": classification_accuracy_by_load,
        "minimum_classification_accuracy": minimum_classification_accuracy,
        "minimum_classification_accuracy_required": (
            MINIMUM_LIVE_CLASSIFICATION_ACCURACY
        ),
        "observations": checks,
        "passed": (
            all(item["passed"] for item in checks)
            and minimum_classification_accuracy
            >= MINIMUM_LIVE_CLASSIFICATION_ACCURACY
        ),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Reproduce the accepted Phase 2 latency calibration",
    )
    parser.add_argument("--samples", type=int, default=5_000)
    parser.add_argument("--seed", type=int, default=2050)
    parser.add_argument("--live-url")
    parser.add_argument("--live-state", type=int, choices=range(1, 5))
    parser.add_argument("--live-load", type=int, action="append")
    parser.add_argument("--live-repetitions", type=int, default=5)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    arguments = parser.parse_args()

    if arguments.samples < 1:
        parser.error("--samples must be positive")
    if arguments.live_url and arguments.live_state is None:
        parser.error("--live-state is required with --live-url")
    if arguments.live_state is not None and not arguments.live_url:
        parser.error("--live-url is required with --live-state")
    if arguments.live_load and not arguments.live_url:
        parser.error("--live-url is required with --live-load")
    if arguments.live_load and any(load < 1 for load in arguments.live_load):
        parser.error("--live-load values must be positive")
    if arguments.live_repetitions < 1:
        parser.error("--live-repetitions must be positive")

    report = build_calibration_report(
        samples=arguments.samples,
        seed=arguments.seed,
    )
    if arguments.live_url:
        parameters = require_state_parameters(arguments.live_state)
        loads = arguments.live_load or [1, parameters.capacity_flows + 1]
        report["live"] = collect_live_checks(
            arguments.live_url,
            arguments.live_state,
            loads,
            arguments.live_repetitions,
            arguments.timeout_seconds,
        )
    report["gate_passed"] = report["model_gate_passed"] and report.get(
        "live",
        {"passed": True},
    )["passed"]
    print(f"PHASE2_CALIBRATION={json.dumps(report, sort_keys=True)}")
    if not report["gate_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
