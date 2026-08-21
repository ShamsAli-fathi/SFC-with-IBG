"""Pure evidence validation for Hybrid Kernel Phase 8 Gate 1."""

from __future__ import annotations

from collections import Counter
from typing import Mapping, Sequence

from .kernel_infrastructure_contract import (
    HYBRID_KERNEL_LOOKAHEAD_POOL_LIFECYCLE_VERSION,
    HYBRID_KERNEL_LOOKAHEAD_WORKERS,
)


HYBRID_KERNEL_PHASE8_GATE1_EVIDENCE_VERSION = (
    "ibg-hybrid-kernel-phase8-gate1-evidence-v1"
)


class HybridKernelPhase8EvidenceError(ValueError):
    """Raised when 4x3x2 lookahead evidence is incomplete or inconsistent."""


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise HybridKernelPhase8EvidenceError(f"{field} must be a mapping")
    return value


def validate_phase8_gate1_slots(
    slots: Sequence[Mapping[str, object]],
) -> tuple[Mapping[str, object], ...]:
    """Require two complete 4x3x2 deterministic-lookahead Kernel slots."""

    records = tuple(slots)
    if len(records) < 2:
        raise HybridKernelPhase8EvidenceError(
            "Phase 8 Gate 1 requires at least two slots"
        )
    previous_beliefs = None
    for index, raw in enumerate(records):
        slot = _mapping(raw, f"slot {index}")
        if slot.get("configuration") != {
            "num_flows": 4,
            "num_stages": 3,
            "num_replicas": 2,
            "stage_budget": 2,
        }:
            raise HybridKernelPhase8EvidenceError(
                "slot does not use exact 4x3x2 configuration"
            )
        if slot.get("policy_mode") != "lookahead" or slot.get("mc_workers") is not None:
            raise HybridKernelPhase8EvidenceError(
                "Phase 8 Gate 1 must use lookahead without MC workers"
            )
        if slot.get("placement_paths") != ["deterministic-lookahead"] * 4:
            raise HybridKernelPhase8EvidenceError(
                "all four focal placements must use deterministic lookahead"
            )
        if slot.get("observation_count") != 8 or slot.get("measured_pair_count") != 4:
            raise HybridKernelPhase8EvidenceError(
                "each slot requires eight observations and four measured pairs"
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
                raise HybridKernelPhase8EvidenceError(
                    f"slot failed required semantic boundary: {field}"
                )
        lookahead_workers = slot.get("lookahead_process_workers", 0)
        expected_lifecycle = (
            HYBRID_KERNEL_LOOKAHEAD_POOL_LIFECYCLE_VERSION
            if lookahead_workers == HYBRID_KERNEL_LOOKAHEAD_WORKERS
            else None
        )
        if (
            lookahead_workers not in {0, HYBRID_KERNEL_LOOKAHEAD_WORKERS}
            or slot.get("lookahead_pool_lifecycle_version")
            != expected_lifecycle
            or slot.get("active_child_processes_after_slot")
            != lookahead_workers
        ):
            raise HybridKernelPhase8EvidenceError(
                "lookahead process-pool lifecycle evidence is inconsistent"
            )

        placements = slot.get("placements")
        observations = slot.get("observations")
        final_loads = slot.get("final_loads")
        if (
            not isinstance(placements, list)
            or len(placements) != 4
            or not isinstance(observations, list)
            or len(observations) != 8
            or not isinstance(final_loads, list)
            or len(final_loads) != 3
            or any(not isinstance(row, list) or len(row) != 2 for row in final_loads)
        ):
            raise HybridKernelPhase8EvidenceError(
                "placement, observation, or final-load shape is incomplete"
            )
        if any(
            isinstance(load, bool) or not isinstance(load, int) or load < 0 or load > 2
            for row in final_loads
            for load in row
        ) or sum(load for row in final_loads for load in row) != 8:
            raise HybridKernelPhase8EvidenceError(
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
                or not isinstance(replicas, list)
                or len(replicas) != 2
                or "planning_link_ms" not in item
                or "measured_pair_ms" not in item
            ):
                raise HybridKernelPhase8EvidenceError(
                    "placement route or planning/measured pair is incomplete"
                )
            flow_ids.append(flow_id)
            routes.add(tuple(stages))
        if sorted(flow_ids) != [1, 2, 3, 4]:
            raise HybridKernelPhase8EvidenceError(
                "focal placement coverage must be exactly flows 1 through 4"
            )
        if index == 0 and not {(1, 3), (2, 3)}.issubset(routes):
            raise HybridKernelPhase8EvidenceError(
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
                or isinstance(stage, bool)
                or not isinstance(stage, int)
                or stage not in range(1, 4)
                or isinstance(replica, bool)
                or not isinstance(replica, int)
                or replica not in range(1, 3)
                or assigned_load != final_loads[stage - 1][replica - 1]
            ):
                raise HybridKernelPhase8EvidenceError(
                    "observation identity or final assigned-load propagation failed"
                )
            observation_counts[flow_id] += 1
            if "hidden_state" in item or "observation_seed" in item:
                raise HybridKernelPhase8EvidenceError(
                    "Kernel observation exposed hidden state or seed"
                )
        if observation_counts != Counter({flow: 2 for flow in range(1, 5)}):
            raise HybridKernelPhase8EvidenceError(
                "each flow must provide exactly two selected observations"
            )

        if previous_beliefs is not None and slot.get("beliefs_before") != previous_beliefs:
            raise HybridKernelPhase8EvidenceError(
                "belief state was not retained across slots"
            )
        previous_beliefs = slot.get("beliefs_after")
    return records
