from collections import Counter
import random

import numpy as np

from ports import AdapterBundle, Observation
from datapath import KERNEL_DATAPATH_MODE, SIMULATION_DATAPATH_MODE
from runner import run_decoupled_slot
from simulation_adapters import (
    NullResultSink,
    SimulationReplicaDiscovery,
    SimulationTrafficExecutor,
)
from IBG.latency_model import estimate_state, latency_likelihood
from testbed.cnf_service import ReplicaConfig, SeededLatencyObservationSource
from testbed.kubernetes_adapters import build_replica_list


class SeededSimulationObservationCollector:
    """Apply the Phase 1 latency model with request-stable samples."""

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
            self.sources[(stage, replica_id)] = SeededLatencyObservationSource(config)

    def collect(self, stage, assignments, replica_list):
        congestion_by_replica = Counter(assignments.values())
        observations = []
        for flow_id, replica_id in assignments.items():
            congestion = congestion_by_replica[replica_id]
            signal = self.sources[(stage, replica_id)](
                congestion,
                self.slot_id,
                flow_id,
            )
            likelihood = latency_likelihood(signal, congestion)
            observations.append(
                Observation(
                    stage=stage,
                    flow_id=flow_id,
                    replica_id=replica_id,
                    congestion=congestion,
                    signal=signal,
                    likelihood=tuple(likelihood),
                    measured_latency_ms=signal,
                    estimated_state=estimate_state(likelihood),
                )
            )
        return observations


class ReplayObservationCollector:
    """Replay selected Kernel signals without changing the learning boundary."""

    def __init__(self):
        self.summary = None

    def set_summary(self, summary):
        self.summary = summary

    def collect(self, stage, assignments, replica_list):
        if self.summary is None:
            raise RuntimeError("no Kernel summary is loaded for replay")
        captured = {
            (item["stage"], item["flow_id"]): item
            for item in self.summary["observations"]
        }
        observations = []
        for flow_id, replica_id in assignments.items():
            try:
                item = captured[(stage, flow_id)]
            except KeyError as error:
                raise RuntimeError(
                    f"missing replay observation for flow {flow_id} stage {stage}"
                ) from error
            if item["replica_id"] != replica_id:
                raise RuntimeError(
                    f"replay placement drift for flow {flow_id} stage {stage}"
                )
            observations.append(
                Observation(
                    stage=stage,
                    flow_id=flow_id,
                    replica_id=replica_id,
                    congestion=item["congestion"],
                    signal=item["signal"],
                    likelihood=tuple(item["likelihood"]),
                    measured_latency_ms=item["measured_latency_ms"],
                    estimated_state=item["estimated_state"],
                )
            )
        return observations


class ReplaySlotTrafficExecutor:
    def execute_slot(self, slot_id, assignments_by_stage, discovered_by_stage):
        return None


class ReplayLinkLatencyCollector:
    def __init__(self):
        self.summary = None

    def set_summary(self, summary):
        self.summary = summary

    def collect(self, traffic_telemetry):
        if self.summary is None:
            raise RuntimeError("no Kernel summary is loaded for replay")
        return {
            int(flow_id): float(value)
            for flow_id, value in self.summary["metrics"][
                "link_latency_ms_per_flow"
            ].items()
        }


def make_seeded_simulation_adapters(profiles, slot_id):
    return AdapterBundle(
        replica_discovery=SimulationReplicaDiscovery(),
        traffic_executor=SimulationTrafficExecutor(),
        observation_collector=SeededSimulationObservationCollector(
            profiles,
            slot_id,
        ),
        result_sink=NullResultSink(),
        datapath_mode=SIMULATION_DATAPATH_MODE,
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
            "estimated_state": observation.estimated_state,
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
        "datapath_mode": result.datapath_mode,
        "solver": "br_eibg_exact",
        "observation_mode": "processing-latency-conditioned-on-assigned-load",
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
            "processing_latency_ms_per_flow": {
                str(flow_id): float(value)
                for flow_id, value in result.processing_latency_ms_per_flow.items()
            },
            "link_latency_ms_per_flow": {
                str(flow_id): float(value)
                for flow_id, value in result.link_latency_ms_per_flow.items()
            },
            "end_to_end_latency_ms_per_flow": {
                str(flow_id): float(value)
                for flow_id, value in result.end_to_end_latency_ms_per_flow.items()
            },
            "realized_utility_total": float(result.realized_utility_total),
            "realized_utility_per_flow": {
                str(flow_id): float(value)
                for flow_id, value in result.realized_utility_per_flow.items()
            },
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


def replay_kernel_trace(events, profiles):
    started = [event for event in events if event.get("event") == "run_started"]
    iterations = [
        event for event in events if event.get("event") == "iteration_completed"
    ]
    if len(started) != 1 or not iterations:
        raise ValueError("expected one Kernel run with completed iterations")
    transport_schemas = {
        "pairwise"
        if any(
            "links" in flow
            or "ingress_request_latency_ms" in flow
            or "ingress_overhead_ms" in flow
            for flow in (event["summary"].get("traffic") or {}).get(
                "flows", []
            )
        )
        else "historical"
        for event in iterations
    }
    transport_schema_consistent = len(transport_schemas) == 1
    if not transport_schema_consistent:
        return {
            "gate_passed": False,
            "transport_schema_consistent": False,
            "transport_schemas": sorted(transport_schemas),
            "iterations": len(iterations),
            "slots": [],
            "max_belief_abs": 0.0,
            "max_mathematical_abs": 0.0,
        }
    metadata = started[0]
    configuration = metadata["configuration"]
    seed = metadata["seed"]
    random.seed(seed)
    np.random.seed(seed)
    replica_list = build_replica_list(
        profiles,
        configuration["stages"],
        configuration["replicas_per_stage"],
    )
    observation_collector = ReplayObservationCollector()
    link_collector = ReplayLinkLatencyCollector()
    adapters = AdapterBundle(
        replica_discovery=SimulationReplicaDiscovery(),
        traffic_executor=SimulationTrafficExecutor(),
        observation_collector=observation_collector,
        result_sink=NullResultSink(),
        slot_traffic_executor=ReplaySlotTrafficExecutor(),
        link_latency_collector=link_collector,
        datapath_mode=SIMULATION_DATAPATH_MODE,
    )
    flow_list = list(range(1, configuration["flows"] + 1))
    comparisons = []
    for event in iterations:
        captured = event["summary"]
        observation_collector.set_summary(captured)
        link_collector.set_summary(captured)
        result = run_decoupled_slot(
            flow_list,
            replica_list,
            num_of_stages=configuration["stages"],
            num_of_replicas=configuration["replicas_per_stage"],
            adapters=adapters,
            slot_id=event["slot_id"],
        )
        replayed = summarize_slot(
            result,
            replica_list,
            backend="simulation",
            seed=seed,
            slot_id=event["slot_id"],
            num_of_stages=configuration["stages"],
            num_of_replicas=configuration["replicas_per_stage"],
            num_of_flows=configuration["flows"],
        )
        comparisons.append(compare_backend_summaries(replayed, captured))
    return {
        "gate_passed": transport_schema_consistent
        and all(item["gate_passed"] for item in comparisons),
        "transport_schema_consistent": transport_schema_consistent,
        "transport_schemas": sorted(transport_schemas),
        "iterations": len(comparisons),
        "slots": [
            {
                "slot_id": item["slot_id"],
                "gate_passed": item["gate_passed"],
                "placement_matches": item["placements"]["matches"],
                "observation_matches": item["observations"]["signal_matches"],
                "belief_max_abs": item["belief_max_abs"],
                "aggregate_utility_abs": item["metrics"][
                    "aggregate_utility_abs"
                ],
            }
            for item in comparisons
        ],
        "max_belief_abs": max(
            (item["belief_max_abs"] for item in comparisons),
            default=0.0,
        ),
        "max_mathematical_abs": max(
            (
                max(
                    [item["belief_max_abs"]]
                    + list(item["utility_grid_max_abs_by_stage"].values())
                    + [
                        item["observations"]["likelihood_max_abs"],
                        item["metrics"]["aggregate_utility_abs"],
                        item["metrics"]["realized_utility_abs"],
                    ]
                )
                for item in comparisons
            ),
            default=0.0,
        ),
    }


def _indexed(items):
    return {(item["stage"], item["flow_id"]): item for item in items}


def _max_abs(left, right):
    return max(
        (abs(float(a) - float(b)) for a, b in zip(left, right)),
        default=0.0,
    )


def _normalized_endpoint(value):
    if not isinstance(value, str) or not value:
        return None
    return value.rstrip("/")


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
    realized_per_flow_utility_max_abs = max(
        (
            abs(
                simulation_metrics["realized_utility_per_flow"][flow_id]
                - kubernetes_metrics["realized_utility_per_flow"][flow_id]
            )
            for flow_id in simulation_metrics["realized_utility_per_flow"]
        ),
        default=0.0,
    )
    latency_metric_max_abs = {
        metric: max(
            (
                abs(
                    simulation_metrics[metric][flow_id]
                    - kubernetes_metrics[metric][flow_id]
                )
                for flow_id in simulation_metrics[metric]
            ),
            default=0.0,
        )
        for metric in (
            "processing_latency_ms_per_flow",
            "link_latency_ms_per_flow",
            "end_to_end_latency_ms_per_flow",
        )
    }

    traffic = kubernetes.get("traffic") or {}
    traffic_hops = [
        hop
        for flow in traffic.get("flows", [])
        for hop in flow.get("hops", [])
    ]
    traffic_flows = traffic.get("flows", [])
    traffic_keys = {
        (hop.get("stage"), hop.get("flow_id")) for hop in traffic_hops
    }
    selected_keys = set(kubernetes_placements)
    observation_selected_keys = set(kubernetes_observations)
    mode_contract = {
        "simulation": simulation.get("datapath_mode") == SIMULATION_DATAPATH_MODE,
        "kubernetes": kubernetes.get("datapath_mode") == KERNEL_DATAPATH_MODE,
        "slot_traffic": traffic.get("datapath_mode") == KERNEL_DATAPATH_MODE,
        "all_hops": all(
            hop.get("datapath_mode") == KERNEL_DATAPATH_MODE
            for hop in traffic_hops
        ),
    }
    selected_only = (
        selected_keys == observation_selected_keys == traffic_keys
    )
    pairwise_schema_declared = any(
        "links" in flow
        or "ingress_request_latency_ms" in flow
        or "ingress_overhead_ms" in flow
        for flow in traffic_flows
    )
    if pairwise_schema_declared:
        # New traces keep broad flow-generator ingress timing separate and
        # report exactly one measured RPC/link cost for every selected
        # consecutive-stage pair. Hop transport fields remain only as a
        # backwards-compatible view and are not the pairwise utility cost.
        transport_telemetry_complete = all(
            float(hop.get("transport_overhead_ms", -1.0)) >= 0
            for hop in traffic_hops
        )
        pairwise_link_checks = []
        expected_links_per_flow = max(
            0,
            kubernetes["configuration"]["stages"] - 1,
        )
        for flow in traffic_flows:
            flow_id = int(flow.get("flow_id", -1))
            hops_by_stage = {
                int(hop["stage"]): hop for hop in flow.get("hops", [])
            }
            links = flow.get("links")
            pairwise_link_checks.append(isinstance(links, list))
            if not isinstance(links, list):
                continue
            pairwise_link_checks.extend(
                [
                    len(links) == expected_links_per_flow,
                    float(flow.get("ingress_request_latency_ms", -1.0)) >= 0,
                    float(flow.get("ingress_overhead_ms", -1.0)) >= 0,
                ]
            )
            observed_stage_pairs = set()
            link_cost_sum = 0.0
            for link in links:
                source_stage = int(link.get("source_stage", -1))
                target_stage = int(link.get("target_stage", -1))
                source_hop = hops_by_stage.get(source_stage, {})
                target_hop = hops_by_stage.get(target_stage, {})
                source_placement = kubernetes_placements.get(
                    (source_stage, flow_id), {}
                )
                target_placement = kubernetes_placements.get(
                    (target_stage, flow_id), {}
                )
                request_latency = float(link.get("request_latency_ms", -1.0))
                callee_elapsed = float(link.get("callee_elapsed_ms", -1.0))
                cost = float(link.get("link_cost_ms", -1.0))
                link_cost_sum += cost
                observed_stage_pairs.add((source_stage, target_stage))
                pairwise_link_checks.append(
                    target_stage == source_stage + 1
                    and int(link.get("slot_id", -1)) == kubernetes["slot_id"]
                    and int(link.get("flow_id", -1)) == flow_id
                    and link.get("source_replica_id")
                    == source_hop.get("replica_id")
                    == source_placement.get("replica_id")
                    and link.get("source_pod_name")
                    == source_hop.get("pod_name")
                    == source_placement.get("pod_name")
                    and link.get("target_replica_id")
                    == target_hop.get("replica_id")
                    == target_placement.get("replica_id")
                    and link.get("target_pod_name")
                    == target_hop.get("pod_name")
                    == target_placement.get("pod_name")
                    and _normalized_endpoint(link.get("target_endpoint"))
                    == _normalized_endpoint(target_hop.get("endpoint"))
                    == _normalized_endpoint(target_placement.get("endpoint"))
                    and request_latency >= 0
                    and callee_elapsed >= 0
                    and cost >= 0
                    and abs(
                        cost - max(0.0, request_latency - callee_elapsed)
                    )
                    <= tolerance
                )
            pairwise_link_checks.append(
                observed_stage_pairs
                == {
                    (stage, stage + 1)
                    for stage in range(1, expected_links_per_flow + 1)
                }
            )
            link_metric = kubernetes_metrics[
                "link_latency_ms_per_flow"
            ].get(str(flow_id))
            pairwise_link_checks.append(
                link_metric is not None
                and abs(link_cost_sum - float(link_metric)) <= tolerance
            )
        pairwise_link_telemetry_complete = bool(pairwise_link_checks) and all(
            pairwise_link_checks
        )
    else:
        # Historical traces measured each independent flow-generator request.
        transport_telemetry_complete = all(
            float(hop.get("transport_overhead_ms", -1.0)) >= 0
            and abs(
                float(hop["transport_overhead_ms"])
                - max(
                    0.0,
                    float(hop["request_latency_ms"])
                    - float(hop["processing_latency_ms"]),
                )
            )
            <= tolerance
            for hop in traffic_hops
        )
        pairwise_link_telemetry_complete = True
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
        "realized_utility_abs": abs(
            simulation_metrics["realized_utility_total"]
            - kubernetes_metrics["realized_utility_total"]
        ),
        "realized_per_flow_utility_max_abs": (
            realized_per_flow_utility_max_abs
        ),
        "latency_metric_max_abs": latency_metric_max_abs,
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
            all(mode_contract.values()),
            placement_matches == len(placement_keys) == expected_hops,
            max(utility_max_by_stage.values(), default=0.0) <= tolerance,
            observation_replica_matches == len(observation_keys) == expected_hops,
            observation_congestion_matches == expected_hops,
            observation_signal_matches == expected_hops,
            likelihood_max_abs <= tolerance,
            belief_max_abs <= tolerance,
            exact_metrics["aggregate_utility_abs"] <= tolerance,
            exact_metrics["per_flow_utility_max_abs"] <= tolerance,
            exact_metrics["realized_utility_abs"] <= tolerance,
            exact_metrics["realized_per_flow_utility_max_abs"] <= tolerance,
            max(latency_metric_max_abs.values(), default=0.0) <= tolerance,
            exact_metrics["jain_fairness_abs"] <= tolerance,
            exact_metrics["sla_match"],
            exact_metrics["equilibrium_match"],
            len(traffic_hops) == expected_hops,
            selected_only,
            transport_telemetry_complete,
            pairwise_link_telemetry_complete,
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
            "datapath_mode": kubernetes.get("datapath_mode"),
            "mode_contract": mode_contract,
            "complete_hops": len(traffic_hops),
            "selected_only": selected_only,
            "transport_telemetry_complete": transport_telemetry_complete,
            "pairwise_link_telemetry_complete": (
                pairwise_link_telemetry_complete
            ),
            "pairwise_schema_declared": pairwise_schema_declared,
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
