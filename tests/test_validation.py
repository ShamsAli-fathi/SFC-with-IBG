import copy
import json
from pathlib import Path

from scripts.phase6_compare import build_report, parse_kubernetes_results
from testbed.profiles import load_profiles
from testbed.validation import (
    compare_backend_summaries,
    replay_kernel_trace,
    run_controlled_simulation,
)


ROOT = Path(__file__).resolve().parents[1]
PROFILES = ROOT / "deploy" / "kubernetes" / "profiles.json"


def kubernetes_shape(simulation):
    kubernetes = copy.deepcopy(simulation)
    kubernetes["backend"] = "kubernetes"
    kubernetes["datapath_mode"] = "kernel"
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
                    "datapath_mode": "kernel",
                    "slot_id": simulation["slot_id"],
                    "flow_id": flow_id,
                    "stage": stage,
                    "replica_id": placement["replica_id"],
                    "pod_name": placement["pod_name"],
                    "endpoint": placement["endpoint"],
                    "concurrency": observation["congestion"],
                    "assigned_load": observation["congestion"],
                    "modeled_processing_latency_ms": observation[
                        "measured_latency_ms"
                    ],
                    "legacy_congestion": observation["congestion"],
                    "processing_latency_ms": observation[
                        "measured_latency_ms"
                    ],
                    "observation_jitter_ms": observation[
                        "observation_jitter_ms"
                    ],
                    "request_latency_ms": (
                        observation["measured_latency_ms"] + 1.0
                    ),
                    "transport_overhead_ms": 1.0,
                    "signal_latency_ms": observation["signal"],
                    "state_estimate": observation["estimated_state"],
                    "state_likelihood": observation["likelihood"],
                    "legacy_signal": observation["estimated_state"],
                    "legacy_likelihood": observation["likelihood"],
                }
            )
        flows.append({"flow_id": flow_id, "hops": hops})
    kubernetes["traffic"] = {
        "datapath_mode": "kernel",
        "slot_id": simulation["slot_id"],
        "elapsed_ms": 150.0,
        "flows": flows,
    }
    kubernetes["metrics"]["elapsed_seconds"] += 0.15
    return kubernetes


def pairwise_kubernetes_shape(simulation):
    kubernetes = kubernetes_shape(simulation)
    for flow in kubernetes["traffic"]["flows"]:
        flow["ingress_request_latency_ms"] = 125.0
        flow["ingress_overhead_ms"] = 0.5
        flow["links"] = []
        for source, target in zip(flow["hops"], flow["hops"][1:]):
            flow["links"].append(
                {
                    "slot_id": simulation["slot_id"],
                    "flow_id": flow["flow_id"],
                    "source_stage": source["stage"],
                    "source_replica_id": source["replica_id"],
                    "source_pod_name": source["pod_name"],
                    "target_stage": target["stage"],
                    "target_replica_id": target["replica_id"],
                    "target_pod_name": target["pod_name"],
                    "target_endpoint": target["endpoint"],
                    "request_latency_ms": 50.0,
                    "callee_elapsed_ms": 50.0,
                    "link_cost_ms": 0.0,
                }
            )
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
    assert summary["datapath_mode"] == "simulation"
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
    assert comparison["kubernetes_telemetry"]["datapath_mode"] == "kernel"
    assert comparison["kubernetes_telemetry"]["selected_only"] is True
    assert (
        comparison["kubernetes_telemetry"]["transport_telemetry_complete"]
        is True
    )


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


def test_comparison_rejects_datapath_mode_or_transport_drift():
    simulation = run_controlled_simulation(
        load_profiles(PROFILES),
        seed=2050,
        slot_id=1,
    )
    kubernetes = kubernetes_shape(simulation)
    kubernetes["traffic"]["flows"][0]["hops"][0][
        "transport_overhead_ms"
    ] = -1.0

    comparison = compare_backend_summaries(simulation, kubernetes)

    assert comparison["gate_passed"] is False
    assert (
        comparison["kubernetes_telemetry"]["transport_telemetry_complete"]
        is False
    )


def test_comparison_accepts_pairwise_links_and_separate_ingress_telemetry():
    simulation = run_controlled_simulation(
        load_profiles(PROFILES),
        seed=2050,
        slot_id=1,
    )

    comparison = compare_backend_summaries(
        simulation,
        pairwise_kubernetes_shape(simulation),
    )

    assert comparison["gate_passed"] is True
    assert (
        comparison["kubernetes_telemetry"]["pairwise_schema_declared"]
        is True
    )
    assert (
        comparison["kubernetes_telemetry"][
            "pairwise_link_telemetry_complete"
        ]
        is True
    )


def test_comparison_normalizes_endpoint_root_slashes():
    simulation = run_controlled_simulation(
        load_profiles(PROFILES),
        seed=2050,
        slot_id=1,
    )
    kubernetes = pairwise_kubernetes_shape(simulation)
    for flow in kubernetes["traffic"]["flows"]:
        for hop in flow["hops"]:
            hop["endpoint"] += "/"
        for link in flow["links"]:
            link["target_endpoint"] += "/"

    comparison = compare_backend_summaries(simulation, kubernetes)

    assert comparison["gate_passed"] is True


def test_comparison_rejects_pairwise_link_cost_drift():
    simulation = run_controlled_simulation(
        load_profiles(PROFILES),
        seed=2050,
        slot_id=1,
    )
    kubernetes = pairwise_kubernetes_shape(simulation)
    kubernetes["traffic"]["flows"][0]["links"][0]["link_cost_ms"] = 2.0

    comparison = compare_backend_summaries(simulation, kubernetes)

    assert comparison["gate_passed"] is False
    assert (
        comparison["kubernetes_telemetry"][
            "pairwise_link_telemetry_complete"
        ]
        is False
    )


def test_comparison_rejects_pairwise_link_metric_sum_drift():
    simulation = run_controlled_simulation(
        load_profiles(PROFILES),
        seed=2050,
        slot_id=1,
    )
    kubernetes = pairwise_kubernetes_shape(simulation)
    link = kubernetes["traffic"]["flows"][0]["links"][0]
    link["callee_elapsed_ms"] = 49.0
    link["link_cost_ms"] = 1.0

    comparison = compare_backend_summaries(simulation, kubernetes)

    assert comparison["gate_passed"] is False
    assert (
        comparison["kubernetes_telemetry"][
            "pairwise_link_telemetry_complete"
        ]
        is False
    )


def test_comparison_rejects_pairwise_pod_or_endpoint_drift():
    simulation = run_controlled_simulation(
        load_profiles(PROFILES),
        seed=2050,
        slot_id=1,
    )
    for field in ("source_pod_name", "target_pod_name", "target_endpoint"):
        kubernetes = pairwise_kubernetes_shape(simulation)
        kubernetes["traffic"]["flows"][0]["links"][0][field] = "wrong"

        comparison = compare_backend_summaries(simulation, kubernetes)

        assert comparison["gate_passed"] is False
        assert (
            comparison["kubernetes_telemetry"][
                "pairwise_link_telemetry_complete"
            ]
            is False
        )


def test_kernel_signal_replay_preserves_the_unchanged_runner_math():
    profiles = load_profiles(PROFILES)
    simulation = run_controlled_simulation(
        profiles,
        seed=2050,
        slot_id=1,
    )
    kubernetes = kubernetes_shape(simulation)
    metadata = {
        "backend": "kubernetes",
        "datapath_mode": "kernel",
        "runtime_image": "ibg-testbed:kernel-phase3",
        "environment": {"kubernetes_server": "v1.35.0"},
        "seed": 2050,
        "configuration": simulation["configuration"],
    }
    replay = replay_kernel_trace(
        [
            {"event": "run_started", **metadata},
            {
                "event": "iteration_completed",
                **metadata,
                "slot_id": 1,
                "summary": kubernetes,
            },
        ],
        profiles,
    )

    assert replay["gate_passed"] is True
    assert replay["iterations"] == 1
    assert replay["max_mathematical_abs"] == 0


def test_kernel_signal_replay_rejects_mixed_transport_schemas():
    profiles = load_profiles(PROFILES)
    simulation = run_controlled_simulation(
        profiles,
        seed=2050,
        slot_id=1,
    )
    metadata = {
        "backend": "kubernetes",
        "datapath_mode": "kernel",
        "runtime_image": "ibg-testbed:kernel-phase3",
        "environment": {"kubernetes_server": "v1.35.0"},
        "seed": 2050,
        "configuration": simulation["configuration"],
    }
    replay = replay_kernel_trace(
        [
            {"event": "run_started", **metadata},
            {
                "event": "iteration_completed",
                **metadata,
                "slot_id": 1,
                "summary": kubernetes_shape(simulation),
            },
            {
                "event": "iteration_completed",
                **metadata,
                "slot_id": 2,
                "summary": pairwise_kubernetes_shape(simulation),
            },
        ],
        profiles,
    )

    assert replay["gate_passed"] is False
    assert replay["transport_schema_consistent"] is False
    assert replay["transport_schemas"] == ["historical", "pairwise"]


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
