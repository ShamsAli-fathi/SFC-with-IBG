"""Policy-free validation helpers for Hybrid Kernel Infrastructure Phase 7.5."""

from __future__ import annotations

from typing import Mapping, Sequence


HYBRID_KERNEL_MC_EVIDENCE_VERSION = "ibg-hybrid-kernel-mc-evidence-v1"


class HybridKernelMcEvidenceError(ValueError):
    """Raised when manual MC controller evidence is incomplete or inconsistent."""


def parse_direct_child_pids(sample: str) -> tuple[int, ...]:
    marker = "__DIRECT_CHILDREN__"
    lines = sample.splitlines()
    matches = [index for index, line in enumerate(lines) if line.strip() == marker]
    if len(matches) != 1:
        raise HybridKernelMcEvidenceError(
            "controller sample must contain one direct-child section"
        )
    index = matches[0]
    if index + 1 >= len(lines):
        return ()
    value = lines[index + 1].strip()
    if not value or value.startswith("__"):
        return ()
    try:
        pids = tuple(int(field) for field in value.split())
    except ValueError as error:
        raise HybridKernelMcEvidenceError(
            "controller direct-child PID evidence is malformed"
        ) from error
    if any(pid < 2 for pid in pids) or len(set(pids)) != len(pids):
        raise HybridKernelMcEvidenceError(
            "controller direct-child PID evidence is invalid"
        )
    return tuple(sorted(pids))


def validate_mc_slot_evidence(
    slots: Sequence[Mapping[str, object]],
    *,
    worker_count: int,
    expected_slots: int = 2,
) -> None:
    if len(slots) != expected_slots:
        raise HybridKernelMcEvidenceError(
            f"manual MC gate requires exactly {expected_slots} slots"
        )
    previous_beliefs = None
    for slot in slots:
        if slot.get("configuration") != {
            "num_flows": 3,
            "num_stages": 3,
            "num_replicas": 2,
            "stage_budget": 2,
        }:
            raise HybridKernelMcEvidenceError("manual MC topology is not 3x3x2")
        if (
            slot.get("policy_mode") != "mc"
            or slot.get("mc_workers") != worker_count
            or slot.get("explicit_policy") is not True
            or set(slot.get("placement_paths", ())) != {"monte-carlo"}
        ):
            raise HybridKernelMcEvidenceError(
                "manual MC policy/worker provenance is incomplete"
            )
        if (
            slot.get("observation_count") != 6
            or slot.get("measured_pair_count") != 3
            or slot.get("active_child_processes_after_slot") != 0
            or slot.get("lookahead_process_workers", 0) != 0
            or slot.get("lookahead_pool_lifecycle_version") is not None
        ):
            raise HybridKernelMcEvidenceError(
                "manual MC telemetry or pool cleanup is incomplete"
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
                raise HybridKernelMcEvidenceError(
                    f"manual MC semantic evidence failed: {field}"
                )
        if previous_beliefs is not None and slot.get("beliefs_before") != previous_beliefs:
            raise HybridKernelMcEvidenceError(
                "manual MC beliefs were not retained across slots"
            )
        previous_beliefs = slot.get("beliefs_after")


def mc_decision_projection(
    slots: Sequence[Mapping[str, object]],
) -> tuple[tuple[object, ...], ...]:
    return tuple(
        (
            slot.get("slot_id"),
            tuple(slot.get("flow_order", ())),
            tuple(
                (
                    placement.get("flow_id"),
                    tuple(placement.get("selected_stages", ())),
                    tuple(placement.get("selected_replicas", ())),
                    placement.get("skipped_stage"),
                )
                for placement in slot.get("placements", ())
                if isinstance(placement, dict)
            ),
            tuple(tuple(row) for row in slot.get("final_loads", ())),
        )
        for slot in slots
    )


def require_worker_count_decision_equality(
    one_worker: Sequence[Mapping[str, object]],
    multi_worker: Sequence[Mapping[str, object]],
) -> None:
    if mc_decision_projection(one_worker) != mc_decision_projection(multi_worker):
        raise HybridKernelMcEvidenceError(
            "one-worker and multi-worker MC decisions/final loads differ"
        )
