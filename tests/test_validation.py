import copy
import json
from pathlib import Path

from scripts.phase6_compare import build_report, parse_kubernetes_results
from testbed.profiles import load_profiles
from testbed.validation import (
    compare_backend_summaries,
    run_controlled_simulation,
)


ROOT = Path(__file__).resolve().parents[1]
PROFILES = ROOT / "deploy" / "kubernetes" / "profiles.json"


def kubernetes_shape(simulation):
    kubernetes = copy.deepcopy(simulation)
    kubernetes["backend"] = "kubernetes"
    placements = {
        (item["stage"], item["flow_id"]): item
        for item in kubernetes["placements"]
    }
    observations = {
        (item["stage"], item["flow_id"]): item
        for item in kubernetes["observations"]
    }
    for placement in kubernetes["placements"]:
        stage = placement["stage"]
        replica_id = placement["replica_id"]
        placement.update(
            {
                "pod_name": f"stage-{stage}-{replica_id - 1}",
                "node_name": f"worker-{replica_id % 2 + 1}",
                "endpoint": (
                    f"http://stage-{stage}-{replica_id - 1}.stage-{stage}."
                    "ibg-testbed.svc.cluster.local:8080"
                ),
            }
        )

    flows = []
    for flow_id in range(1, simulation["configuration"]["flows"] + 1):
        hops = []
        for stage in range(1, simulation["configuration"]["stages"] + 1):
            placement = placements[(stage, flow_id)]
            observation = observations[(stage, flow_id)]
            hops.append(
                {
                    "slot_id": simulation["slot_id"],
                    "flow_id": flow_id,
                    "stage": stage,
                    "replica_id": placement["replica_id"],
                    "pod_name": placement["pod_name"],
                    "endpoint": placement["endpoint"],
                    "concurrency": observation["congestion"],
                    "legacy_congestion": observation["congestion"],
                    "processing_latency_ms": 40.0,
                    "request_latency_ms": 41.0,
                    "legacy_signal": observation["signal"],
                    "legacy_likelihood": observation["likelihood"],
                }
            )
        flows.append({"flow_id": flow_id, "hops": hops})
    kubernetes["traffic"] = {
        "slot_id": simulation["slot_id"],
        "elapsed_ms": 150.0,
        "flows": flows,
    }
    kubernetes["metrics"]["elapsed_seconds"] += 0.15
    return kubernetes


def test_supported_profile_set_contains_five_seeded_replicas_per_stage():
    profiles = load_profiles(PROFILES)

    assert len(profiles) == 15
    assert all((stage, replica) in profiles for stage in range(1, 4) for replica in range(1, 6))
    seeds = [profile.observation_seed for profile in profiles.values()]
    assert None not in seeds
    assert len(seeds) == len(set(seeds))


def test_controlled_simulation_completes_supported_size():
    summary = run_controlled_simulation(
        load_profiles(PROFILES),
        seed=2050,
        slot_id=1,
    )

    assert len(summary["placements"]) == 9
    assert len(summary["observations"]) == 9
    assert len(summary["beliefs"]) == 15
    assert all(len(grid) == 5 for grid in summary["utility_grids"].values())


def test_comparison_accepts_math_parity_and_runtime_only_differences():
    simulation = run_controlled_simulation(
        load_profiles(PROFILES),
        seed=2051,
        slot_id=2,
    )
    comparison = compare_backend_summaries(
        simulation,
        kubernetes_shape(simulation),
    )

    assert comparison["gate_passed"] is True
    assert comparison["placements"]["matches"] == 9
    assert comparison["observations"]["signal_matches"] == 9
    assert comparison["belief_max_abs"] == 0
    assert comparison["kubernetes_telemetry"]["metadata_complete"] is True


def test_comparison_rejects_legacy_congestion_drift():
    simulation = run_controlled_simulation(
        load_profiles(PROFILES),
        seed=2052,
        slot_id=3,
    )
    kubernetes = kubernetes_shape(simulation)
    kubernetes["observations"][0]["congestion"] += 1

    comparison = compare_backend_summaries(simulation, kubernetes)

    assert comparison["gate_passed"] is False
    assert comparison["observations"]["congestion_matches"] == 8


def test_repeated_report_quantifies_only_runtime_difference():
    profiles = load_profiles(PROFILES)
    kubernetes_results = []
    lines = []
    for slot_id, seed in enumerate((2050, 2051, 2052), start=1):
        simulation = run_controlled_simulation(
            profiles,
            seed=seed,
            slot_id=slot_id,
        )
        kubernetes = kubernetes_shape(simulation)
        kubernetes_results.append(kubernetes)
        lines.append(f"PHASE6_RESULT={json.dumps(kubernetes)}")

    parsed = parse_kubernetes_results("\n".join(lines))
    report = build_report(parsed, profiles)

    assert len(parsed) == 3
    assert report["gate_passed"] is True
    assert report["aggregate"]["placement_matches"] == 27
    assert report["aggregate"]["observation_signal_matches"] == 27
    assert report["aggregate"]["mathematical_max_abs"] == 0
    assert report["aggregate"]["kubernetes_to_simulation_time_ratio"] > 1
