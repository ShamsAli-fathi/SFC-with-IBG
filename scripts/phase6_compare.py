import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "IBG"))

from testbed.profiles import load_profiles
from testbed.validation import (
    compare_backend_summaries,
    run_controlled_simulation,
)


RESULT_PREFIX = "PHASE6_RESULT="


def parse_kubernetes_results(text):
    results = []
    for line in text.splitlines():
        if RESULT_PREFIX in line:
            payload = line.split(RESULT_PREFIX, 1)[1]
            results.append(json.loads(payload))
    if not results:
        raise ValueError("no PHASE6_RESULT lines found")
    return sorted(results, key=lambda result: (result["slot_id"], result["seed"]))


def build_report(kubernetes_results, profiles):
    comparisons = []
    for kubernetes in kubernetes_results:
        configuration = kubernetes["configuration"]
        simulation = run_controlled_simulation(
            profiles,
            seed=kubernetes["seed"],
            slot_id=kubernetes["slot_id"],
            num_of_stages=configuration["stages"],
            num_of_replicas=configuration["replicas_per_stage"],
            num_of_flows=configuration["flows"],
        )
        comparisons.append(compare_backend_summaries(simulation, kubernetes))

    simulation_times = [
        item["timing"]["simulation_seconds"] for item in comparisons
    ]
    kubernetes_times = [
        item["timing"]["kubernetes_seconds"] for item in comparisons
    ]
    simulation_mean = sum(simulation_times) / len(simulation_times)
    kubernetes_mean = sum(kubernetes_times) / len(kubernetes_times)
    return {
        "gate_passed": all(item["gate_passed"] for item in comparisons),
        "repeat_count": len(comparisons),
        "comparisons": comparisons,
        "aggregate": {
            "placement_matches": sum(
                item["placements"]["matches"] for item in comparisons
            ),
            "placement_total": sum(
                item["placements"]["total"] for item in comparisons
            ),
            "observation_signal_matches": sum(
                item["observations"]["signal_matches"]
                for item in comparisons
            ),
            "observation_total": sum(
                item["observations"]["total"] for item in comparisons
            ),
            "mathematical_max_abs": max(
                [
                    item["belief_max_abs"]
                    for item in comparisons
                ]
                + [
                    value
                    for item in comparisons
                    for value in item["utility_grid_max_abs_by_stage"].values()
                ]
                + [
                    item["observations"]["likelihood_max_abs"]
                    for item in comparisons
                ]
                + [
                    item["metrics"]["aggregate_utility_abs"]
                    for item in comparisons
                ]
            ),
            "simulation_seconds_mean": simulation_mean,
            "kubernetes_seconds_mean": kubernetes_mean,
            "kubernetes_to_simulation_time_ratio": (
                kubernetes_mean / simulation_mean
            ),
        },
        "discrepancy_explanation": {
            "mathematical_fields": (
                "placements, sampled utility grids, legacy observations, beliefs, "
                "SLA, fairness, and utility must match within tolerance"
            ),
            "timing": (
                "Kubernetes elapsed time includes API, DNS, HTTP, scheduling, and "
                "telemetry overhead and is expected to exceed in-process simulation"
            ),
            "runtime_metadata": (
                "Pod, node, endpoint, admitted concurrency, and measured latency "
                "exist only in the Kubernetes backend"
            ),
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profiles",
        default="deploy/kubernetes/profiles.json",
    )
    parser.add_argument(
        "--kubernetes-log",
        default="-",
        help="controller log path, or - for stdin",
    )
    arguments = parser.parse_args()

    if arguments.kubernetes_log == "-":
        log_text = sys.stdin.read()
    else:
        log_text = Path(arguments.kubernetes_log).read_text(encoding="utf-8")
    profiles = load_profiles(arguments.profiles)
    report = build_report(parse_kubernetes_results(log_text), profiles)
    print(f"PHASE6_COMPARISON={json.dumps(report, sort_keys=True)}")
    if not report["gate_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
