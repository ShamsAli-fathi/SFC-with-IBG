"""Pure validation for dimension-driven Hybrid Kernel lookahead evidence."""

from __future__ import annotations

from collections import Counter
from typing import Mapping, Sequence

from .contracts import HybridConfiguration
from .kernel_profile_expansion import assigned_flow_capacity


HYBRID_KERNEL_DYNAMIC_TOPOLOGY_EVIDENCE_VERSION = (
    "ibg-hybrid-kernel-dynamic-topology-evidence-v1"
)


class HybridKernelDynamicTopologyEvidenceError(ValueError):
    """Raised when a dynamic lookahead slot is incomplete or inconsistent."""


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise HybridKernelDynamicTopologyEvidenceError(
            f"{field} must be a mapping"
        )
    return value


def validate_dynamic_lookahead_slots(
    slots: Sequence[Mapping[str, object]],
    configuration: HybridConfiguration,
) -> tuple[Mapping[str, object], ...]:
    """Require at least two complete lookahead slots at any valid topology."""

    if not isinstance(configuration, HybridConfiguration):
        raise TypeError("configuration must be HybridConfiguration")
    records = tuple(slots)
    if len(records) < 2:
        raise HybridKernelDynamicTopologyEvidenceError(
            "dynamic topology evidence requires at least two slots"
        )
    expected_configuration = {
        "num_flows": configuration.num_flows,
        "num_stages": configuration.num_stages,
        "num_replicas": configuration.num_replicas,
        "stage_budget": configuration.stage_budget,
    }
    capacity = assigned_flow_capacity(configuration)
    previous_beliefs = None
    for index, raw in enumerate(records):
        slot = _mapping(raw, f"slot {index}")
        if slot.get("configuration") != expected_configuration:
            raise HybridKernelDynamicTopologyEvidenceError(
                "slot configuration differs from the requested topology"
            )
        if slot.get("policy_mode") != "lookahead" or slot.get("mc_workers") is not None:
            raise HybridKernelDynamicTopologyEvidenceError(
                "dynamic scale evidence must use lookahead without MC workers"
            )
        if slot.get("placement_paths") != [
            "deterministic-lookahead"
        ] * configuration.num_flows:
            raise HybridKernelDynamicTopologyEvidenceError(
                "every focal placement must use deterministic lookahead"
            )
        if (
            slot.get("observation_count") != 2 * configuration.num_flows
            or slot.get("measured_pair_count") != configuration.num_flows
        ):
            raise HybridKernelDynamicTopologyEvidenceError(
                "slot does not contain exactly two observations and one pair per flow"
            )
        for field in (
            "complete_placement_before_one_request",
            "skipped_stage_absent",
            "separated_jitter_valid",
            "seedless_kernel_provenance",
            "belief_retained_from_previous",
            "pure_kernel_replay_parity",
        ):
            if slot.get(field) is not True:
                raise HybridKernelDynamicTopologyEvidenceError(
                    f"slot failed required semantic boundary: {field}"
                )
        if slot.get("active_child_processes_after_slot") != 0:
            raise HybridKernelDynamicTopologyEvidenceError(
                "lookahead slot retained an unexpected child process"
            )

        placements = slot.get("placements")
        observations = slot.get("observations")
        final_loads = slot.get("final_loads")
        if (
            not isinstance(placements, list)
            or len(placements) != configuration.num_flows
            or not isinstance(observations, list)
            or len(observations) != 2 * configuration.num_flows
            or not isinstance(final_loads, list)
            or len(final_loads) != 3
            or any(
                not isinstance(row, list)
                or len(row) != configuration.num_replicas
                for row in final_loads
            )
        ):
            raise HybridKernelDynamicTopologyEvidenceError(
                "placement, observation, or final-load shape is incomplete"
            )
        if any(
            isinstance(load, bool)
            or not isinstance(load, int)
            or load < 0
            or load > capacity
            for row in final_loads
            for load in row
        ) or sum(load for row in final_loads for load in row) != (
            configuration.stage_budget * configuration.num_flows
        ):
            raise HybridKernelDynamicTopologyEvidenceError(
                "final loads violate admission capacity or selected-load total"
            )

        flow_ids = []
        routes = set()
        for placement in placements:
            item = _mapping(placement, "placement")
            flow_id = item.get("flow_id")
            stages = item.get("selected_stages")
            replicas = item.get("selected_replicas")
            if (
                isinstance(flow_id, bool)
                or not isinstance(flow_id, int)
                or not isinstance(stages, list)
                or len(stages) != 2
                or stages != sorted(stages)
                or len(set(stages)) != 2
                or any(stage not in (1, 2, 3) for stage in stages)
                or not isinstance(replicas, list)
                or len(replicas) != 2
                or any(
                    isinstance(replica, bool)
                    or not isinstance(replica, int)
                    or replica not in range(1, configuration.num_replicas + 1)
                    for replica in replicas
                )
                or "planning_link_ms" not in item
                or "measured_pair_ms" not in item
            ):
                raise HybridKernelDynamicTopologyEvidenceError(
                    "placement route or planning/measured pair is incomplete"
                )
            flow_ids.append(flow_id)
            routes.add(tuple(stages))
        if sorted(flow_ids) != list(range(1, configuration.num_flows + 1)):
            raise HybridKernelDynamicTopologyEvidenceError(
                "focal placement coverage differs from the requested flows"
            )
        if index == 0 and not {(1, 3), (2, 3)}.issubset(routes):
            raise HybridKernelDynamicTopologyEvidenceError(
                "first slot lacks noncontiguous or stage-2-first routing"
            )

        observation_counts = Counter()
        for observation in observations:
            item = _mapping(observation, "observation")
            flow_id = item.get("flow_id")
            stage = item.get("stage")
            replica = item.get("replica")
            assigned_load = item.get("assigned_load")
            if (
                isinstance(flow_id, bool)
                or not isinstance(flow_id, int)
                or flow_id not in range(1, configuration.num_flows + 1)
                or isinstance(stage, bool)
                or not isinstance(stage, int)
                or stage not in (1, 2, 3)
                or isinstance(replica, bool)
                or not isinstance(replica, int)
                or replica not in range(1, configuration.num_replicas + 1)
                or assigned_load != final_loads[stage - 1][replica - 1]
            ):
                raise HybridKernelDynamicTopologyEvidenceError(
                    "observation identity or final assigned-load propagation failed"
                )
            if "hidden_state" in item or "observation_seed" in item:
                raise HybridKernelDynamicTopologyEvidenceError(
                    "Kernel observation exposed hidden state or seed"
                )
            observation_counts[flow_id] += 1
        if observation_counts != Counter(
            {flow: 2 for flow in range(1, configuration.num_flows + 1)}
        ):
            raise HybridKernelDynamicTopologyEvidenceError(
                "each flow must provide exactly two selected observations"
            )
        if previous_beliefs is not None and slot.get("beliefs_before") != previous_beliefs:
            raise HybridKernelDynamicTopologyEvidenceError(
                "belief state was not retained across slots"
            )
        previous_beliefs = slot.get("beliefs_after")
    return records
