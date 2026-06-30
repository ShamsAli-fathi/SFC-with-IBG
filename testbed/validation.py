from collections import Counter
import random

import numpy as np

from ports import AdapterBundle, Observation
from runner import run_decoupled_slot
from simulation_adapters import (
    NullResultSink,
    SimulationReplicaDiscovery,
    SimulationTrafficExecutor,
)
from testbed.cnf_service import ReplicaConfig, SeededLegacyObservationSource
from testbed.kubernetes_adapters import build_replica_list


class SeededSimulationObservationCollector:
    """Apply the legacy model with request-stable Phase 6 samples."""

    def __init__(self, profiles, slot_id):
        self.slot_id = slot_id
        self.sources = {}
        for (stage, replica_id), profile in profiles.items():
            if profile.observation_seed is None:
                raise ValueError(
                    f"stage {stage} replica {replica_id} has no observation_seed"
                )
            config = ReplicaConfig(
                stage=stage,
                replica_id=replica_id,
                pod_name=f"stage-{stage}-{replica_id - 1}",
                state=profile.state,
                capacity=profile.capacity,
                base_delay_ms=profile.base_delay_ms,
                congestion_delay_ms=profile.congestion_delay_ms,
                observation_seed=profile.observation_seed,
            )
            self.sources[(stage, replica_id)] = SeededLegacyObservationSource(config)

    def collect(self, stage, assignments, replica_list):
        congestion_by_replica = Counter(assignments.values())
        observations = []
        for flow_id, replica_id in assignments.items():
            congestion = congestion_by_replica[replica_id]
            signal, likelihood = self.sources[(stage, replica_id)](
                congestion,
                self.slot_id,
                flow_id,
            )
            observations.append(
                Observation(
                    stage=stage,
                    flow_id=flow_id,
                    replica_id=replica_id,
                    congestion=congestion,
                    signal=signal,
                    likelihood=tuple(likelihood),
                    measured_latency_ms=None,
                )
            )
        return observations


def make_seeded_simulation_adapters(profiles, slot_id):
    return AdapterBundle(
        replica_discovery=SimulationReplicaDiscovery(),
        traffic_executor=SimulationTrafficExecutor(),
        observation_collector=SeededSimulationObservationCollector(
            profiles,
            slot_id,
        ),
        result_sink=NullResultSink(),
    )


def summarize_slot(
    result,
    replica_list,
    *,
    backend,
    seed,
    slot_id,
    num_of_stages,
    num_of_replicas,
    num_of_flows,
    discovered_by_stage=None,
):
    placements = []
    for stage, assignments in sorted(result.assignments_by_stage.items()):
        for flow_id, replica_id in sorted(assignments.items()):
            placement = {
                "stage": stage,
                "flow_id": flow_id,
                "replica_id": replica_id,
            }
            if discovered_by_stage is not None:
                replica = discovered_by_stage[stage][(stage, replica_id)]
                placement.update(
                    {
                        "pod_name": replica.pod_name,
                        "node_name": replica.node_name,
                        "endpoint": replica.endpoint,
                    }
                )
            placements.append(placement)

    observations = [
        {
            "stage": observation.stage,
            "flow_id": observation.flow_id,
            "replica_id": observation.replica_id,
            "congestion": observation.congestion,
            "signal": observation.signal,
            "likelihood": [float(value) for value in observation.likelihood],
            "measured_latency_ms": observation.measured_latency_ms,
        }
        for stage_observations in result.observations_by_stage.values()
        for observation in stage_observations
    ]

    utility_grids = {
        str(stage): {
            str(int(replica_id)): [float(value) for value in row]
            for replica_id, row in zip(frame.index, frame.to_numpy())
        }
        for stage, frame in sorted(result.utility_grids.items())
    }
    traffic = (
        None
        if result.traffic_telemetry is None
        else result.traffic_telemetry.model_dump(mode="json")
    )

    return {
        "backend": backend,
        "solver": "br_eibg_exact",
        "observation_mode": "seeded-final-assignment-congestion",
        "seed": seed,
        "slot_id": slot_id,
        "configuration": {
            "stages": num_of_stages,
            "replicas_per_stage": num_of_replicas,
            "flows": num_of_flows,
        },
        "flow_order_by_stage": {
            str(stage): [int(flow_id) for flow_id in flow_order]
            for stage, flow_order in sorted(result.flow_order_by_stage.items())
        },
        "placements": placements,
        "observations": observations,
        "utility_grids": utility_grids,
        "traffic": traffic,
        "metrics": {
            "aggregate_utility_total": float(result.aggregate_utility_total),
            "aggregate_utility_per_flow": {
                str(flow_id): float(value)
                for flow_id, value in result.aggregate_utility_per_flow.items()
            },
            "sla_violations": int(result.sla_violations),
            "jain_fairness": float(result.jain_fairness),
            "equilibrium": int(result.equilibrium),
            "elapsed_seconds": float(result.elapsed_seconds),
        },
        "beliefs": {
            f"{stage}:{replica_id}": [float(value) for value in replica.belief]
            for (stage, replica_id), replica in sorted(replica_list.items())
        },
    }


def run_controlled_simulation(
    profiles,
    *,
    seed,
    slot_id,
    num_of_stages=3,
    num_of_replicas=5,
    num_of_flows=3,
):
    random.seed(seed)
    np.random.seed(seed)
    replica_list = build_replica_list(
        profiles,
        num_of_stages,
        num_of_replicas,
    )
    result = run_decoupled_slot(
        list(range(1, num_of_flows + 1)),
        replica_list,
        num_of_stages=num_of_stages,
        num_of_replicas=num_of_replicas,
        adapters=make_seeded_simulation_adapters(profiles, slot_id),
        slot_id=slot_id,
    )
    return summarize_slot(
        result,
        replica_list,
        backend="simulation",
        seed=seed,
        slot_id=slot_id,
        num_of_stages=num_of_stages,
        num_of_replicas=num_of_replicas,
        num_of_flows=num_of_flows,
    )


def _indexed(items):
    return {(item["stage"], item["flow_id"]): item for item in items}


def _max_abs(left, right):
    return max(
        (abs(float(a) - float(b)) for a, b in zip(left, right)),
        default=0.0,
    )


def compare_backend_summaries(simulation, kubernetes, tolerance=1e-10):
    simulation_placements = _indexed(simulation["placements"])
    kubernetes_placements = _indexed(kubernetes["placements"])
    placement_keys = sorted(set(simulation_placements) | set(kubernetes_placements))
    placement_matches = sum(
        simulation_placements.get(key, {}).get("replica_id")
        == kubernetes_placements.get(key, {}).get("replica_id")
        for key in placement_keys
    )
    placement_by_stage = {
        str(stage): {
            "matches": sum(
                simulation_placements.get(key, {}).get("replica_id")
                == kubernetes_placements.get(key, {}).get("replica_id")
                for key in placement_keys
                if key[0] == stage
            ),
            "total": sum(key[0] == stage for key in placement_keys),
        }
        for stage in range(1, simulation["configuration"]["stages"] + 1)
    }

    utility_max_by_stage = {}
    for stage, simulation_grid in simulation["utility_grids"].items():
        kubernetes_grid = kubernetes["utility_grids"][stage]
        utility_max_by_stage[stage] = max(
            (
                _max_abs(values, kubernetes_grid[replica_id])
                for replica_id, values in simulation_grid.items()
            ),
            default=0.0,
        )

    simulation_observations = _indexed(simulation["observations"])
    kubernetes_observations = _indexed(kubernetes["observations"])
    observation_keys = sorted(
        set(simulation_observations) | set(kubernetes_observations)
    )
    observation_replica_matches = 0
    observation_congestion_matches = 0
    observation_signal_matches = 0
    likelihood_max_abs = 0.0
    for key in observation_keys:
        left = simulation_observations.get(key, {})
        right = kubernetes_observations.get(key, {})
        observation_replica_matches += left.get("replica_id") == right.get("replica_id")
        observation_congestion_matches += left.get("congestion") == right.get("congestion")
        observation_signal_matches += left.get("signal") == right.get("signal")
        likelihood_max_abs = max(
            likelihood_max_abs,
            _max_abs(left.get("likelihood", ()), right.get("likelihood", ())),
        )

    belief_max_abs = max(
        (
            _max_abs(values, kubernetes["beliefs"][replica_key])
            for replica_key, values in simulation["beliefs"].items()
        ),
        default=0.0,
    )
    simulation_metrics = simulation["metrics"]
    kubernetes_metrics = kubernetes["metrics"]
    per_flow_utility_max_abs = max(
        (
            abs(
                simulation_metrics["aggregate_utility_per_flow"][flow_id]
                - kubernetes_metrics["aggregate_utility_per_flow"][flow_id]
            )
            for flow_id in simulation_metrics["aggregate_utility_per_flow"]
        ),
        default=0.0,
    )

    traffic = kubernetes.get("traffic") or {}
    traffic_hops = [
        hop
        for flow in traffic.get("flows", [])
        for hop in flow.get("hops", [])
    ]
    metadata_complete = all(
        placement.get("pod_name")
        and placement.get("node_name")
        and placement.get("endpoint")
        for placement in kubernetes["placements"]
    )
    latency_values = [hop["processing_latency_ms"] for hop in traffic_hops]

    exact_metrics = {
        "aggregate_utility_abs": abs(
            simulation_metrics["aggregate_utility_total"]
            - kubernetes_metrics["aggregate_utility_total"]
        ),
        "per_flow_utility_max_abs": per_flow_utility_max_abs,
        "jain_fairness_abs": abs(
            simulation_metrics["jain_fairness"]
            - kubernetes_metrics["jain_fairness"]
        ),
        "sla_match": (
            simulation_metrics["sla_violations"]
            == kubernetes_metrics["sla_violations"]
        ),
        "equilibrium_match": (
            simulation_metrics["equilibrium"]
            == kubernetes_metrics["equilibrium"]
        ),
    }
    expected_hops = (
        kubernetes["configuration"]["stages"]
        * kubernetes["configuration"]["flows"]
    )
    gate_passed = all(
        [
            simulation["configuration"] == kubernetes["configuration"],
            simulation["solver"] == kubernetes["solver"] == "br_eibg_exact",
            placement_matches == len(placement_keys) == expected_hops,
            max(utility_max_by_stage.values(), default=0.0) <= tolerance,
            observation_replica_matches == len(observation_keys) == expected_hops,
            observation_congestion_matches == expected_hops,
            observation_signal_matches == expected_hops,
            likelihood_max_abs <= tolerance,
            belief_max_abs <= tolerance,
            exact_metrics["aggregate_utility_abs"] <= tolerance,
            exact_metrics["per_flow_utility_max_abs"] <= tolerance,
            exact_metrics["jain_fairness_abs"] <= tolerance,
            exact_metrics["sla_match"],
            exact_metrics["equilibrium_match"],
            len(traffic_hops) == expected_hops,
            metadata_complete,
        ]
    )

    return {
        "seed": kubernetes["seed"],
        "slot_id": kubernetes["slot_id"],
        "gate_passed": gate_passed,
        "placements": {
            "matches": placement_matches,
            "total": len(placement_keys),
            "by_stage": placement_by_stage,
        },
        "utility_grid_max_abs_by_stage": utility_max_by_stage,
        "observations": {
            "replica_matches": observation_replica_matches,
            "congestion_matches": observation_congestion_matches,
            "signal_matches": observation_signal_matches,
            "total": len(observation_keys),
            "likelihood_max_abs": likelihood_max_abs,
        },
        "belief_max_abs": belief_max_abs,
        "metrics": exact_metrics,
        "timing": {
            "simulation_seconds": simulation_metrics["elapsed_seconds"],
            "kubernetes_seconds": kubernetes_metrics["elapsed_seconds"],
        },
        "kubernetes_telemetry": {
            "complete_hops": len(traffic_hops),
            "metadata_complete": metadata_complete,
            "max_admitted_concurrency": max(
                (hop["concurrency"] for hop in traffic_hops),
                default=0,
            ),
            "processing_latency_ms_mean": (
                sum(latency_values) / len(latency_values)
                if latency_values
                else None
            ),
            "processing_latency_ms_max": max(latency_values, default=None),
        },
    }
