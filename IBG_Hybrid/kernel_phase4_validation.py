"""Small live-gate validator for Hybrid Kernel Infrastructure Phase 4."""

from __future__ import annotations

from contextlib import ExitStack
from dataclasses import asdict, dataclass, replace
import json
import multiprocessing
import os
from typing import Callable, Mapping

from .contracts import GlobalLoadState, ReplicaChoice
from .control_plane_footprint import (
    HYBRID_CONTROL_PLANE_DATA_ENV,
    HybridControlPlaneDataMeter,
    validate_hybrid_control_plane_data_snapshot,
)
from .console_output import (
    HYBRID_SLOT_EVIDENCE_PREFIX,
    format_hybrid_slot_metrics,
)
from .kernel_controller import (
    HybridKernelControllerAdapter,
    HybridKernelFlowGeneratorHttpClient,
)
from .kernel_controller_config import (
    HybridKernelControllerInputDocument,
    load_controller_input_document,
)
from .kernel_infrastructure_contract import (
    DEFAULT_HYBRID_KERNEL_OWNERSHIP,
    HYBRID_KERNEL_LOOKAHEAD_POOL_LIFECYCLE_VERSION,
    HYBRID_KERNEL_LOOKAHEAD_WORKERS,
)
from .kernel_kubernetes_discovery import (
    HybridKubernetesApi,
    HybridKubernetesReplicaDiscovery,
)
from .phase0_contract import DEFAULT_HYBRID_POLICY_PARAMETERS
from .policy import IBGHybridPolicy
from .runner import (
    DEFAULT_HYBRID_MC_WORKERS,
    HYBRID_SLOT_POLICY_LOOKAHEAD,
    HYBRID_SLOT_POLICY_MC,
    run_hybrid_slot,
)
from .slot_contracts import (
    HybridFlow,
    HybridReplica,
    HybridSimulationResult,
    HybridSlotInput,
    HybridSlotResult,
)


HYBRID_KERNEL_PHASE4_VALIDATION_VERSION = (
    "ibg-hybrid-kernel-phase4-small-validation-v1"
)
HYBRID_KERNEL_EXPERIMENT_LIFECYCLE_VERSION = (
    "ibg-hybrid-kernel-experiment-lifecycle-v1"
)

CompletedSlotCallback = Callable[
    [int, HybridSlotResult, dict[str, object]], None
]


@dataclass(frozen=True)
class HybridKernelExperimentResult:
    """Finite production-loop outcome without exposing controller beliefs."""

    iterations_completed: int
    reached_equilibrium: bool
    first_slot: int
    last_slot: int
    evidence: tuple[dict[str, object], ...]
    contract_version: str = HYBRID_KERNEL_EXPERIMENT_LIFECYCLE_VERSION

    def __post_init__(self) -> None:
        if self.iterations_completed < 1:
            raise ValueError("an experiment result requires a completed iteration")
        if self.first_slot < 1 or self.last_slot < self.first_slot:
            raise ValueError("experiment slot bounds are invalid")
        if self.last_slot - self.first_slot + 1 != self.iterations_completed:
            raise ValueError("experiment slot bounds do not match iteration count")
        if len(self.evidence) != self.iterations_completed:
            raise ValueError("experiment evidence does not cover every iteration")


class _KernelTelemetryReplayAdapter:
    """Replay complete Kernel telemetry without executing a second request."""

    def __init__(self, result: HybridSimulationResult) -> None:
        self.result = result
        self.calls = 0

    def execute(self, **kwargs) -> HybridSimulationResult:
        del kwargs
        self.calls += 1
        return self.result


def _belief_mapping(values) -> dict[str, list[float]]:
    return {
        f"{choice.stage}:{choice.replica}": list(belief)
        for choice, belief in values
    }


def _replay_kernel_semantics(
    *,
    outcome,
    inputs: HybridKernelControllerInputDocument,
    policy_mode: str,
    mc_workers: int,
) -> bool:
    slot = outcome.slot
    admission = {item.choice: item for item in inputs.admission}
    before = dict(slot.beliefs_before)
    replay_input = HybridSlotInput(
        configuration=inputs.configuration,
        parameters=DEFAULT_HYBRID_POLICY_PARAMETERS,
        root_seed=slot.root_seed,
        slot_id=slot.slot_id,
        flows=tuple(
            HybridFlow(placement.flow.flow_id, placement.flow.high_priority)
            for placement in sorted(
                slot.placements,
                key=lambda item: item.flow.flow_id,
            )
        ),
        replicas=tuple(
            HybridReplica(
                choice=replica.choice,
                belief=before[replica.choice],
                ready=True,
                max_assigned_flows=(
                    admission[replica.choice].max_assigned_flows
                ),
                hidden_state=None,
            )
            for replica in outcome.discovery.replicas
        ),
        planning_pair_links=inputs.planning_pair_links,
        simulated_pair_outcomes=(),
        initial_loads=GlobalLoadState.empty(inputs.configuration),
    )
    replay_adapter = _KernelTelemetryReplayAdapter(
        HybridSimulationResult(slot.observations, slot.measured_pairs)
    )
    replay = run_hybrid_slot(
        replay_input,
        policy=IBGHybridPolicy(inputs.configuration),
        simulation_adapter=replay_adapter,
        policy_mode=policy_mode,
        mc_workers=mc_workers,
    )
    return (
        replay_adapter.calls == 1
        and tuple(item.action for item in replay.placements)
        == tuple(item.action for item in slot.placements)
        and replay.final_loads == slot.final_loads
        and replay.beliefs_before == slot.beliefs_before
        and replay.beliefs_after == slot.beliefs_after
        and replace(replay.metrics, elapsed_seconds=0.0)
        == replace(slot.metrics, elapsed_seconds=0.0)
    )


def _slot_evidence(
    *,
    outcome,
    inputs: HybridKernelControllerInputDocument,
    retained_from_previous: bool,
    policy_mode: str,
    mc_workers: int,
    parity_replay_enabled: bool = True,
) -> dict[str, object]:
    if not isinstance(parity_replay_enabled, bool):
        raise TypeError("parity_replay_enabled must be boolean")
    slot = outcome.slot
    planning = {item.pair: item.latency_ms for item in inputs.planning_pair_links}
    action_by_flow = {
        item.flow.flow_id: item.action for item in slot.placements
    }
    observations_by_flow = {
        flow_id: tuple(
            observation
            for observation in slot.observations
            if observation.flow_id == flow_id
        )
        for flow_id in action_by_flow
    }
    pair_by_flow = {pair.flow_id: pair for pair in slot.measured_pairs}
    skipped_absent = all(
        placement.skipped_stage not in placement.action.stages
        and placement.skipped_stage
        not in {
            observation.choice.stage
            for observation in observations_by_flow[placement.flow.flow_id]
        }
        and placement.skipped_stage
        not in {
            pair_by_flow[placement.flow.flow_id].source.stage,
            pair_by_flow[placement.flow.flow_id].target.stage,
        }
        for placement in slot.placements
    )
    separated_jitter = all(
        abs(
            observation.learning_signal_ms
            - observation.physical_processing_latency_ms
            - observation.observation_jitter_ms
        )
        <= 1e-9
        for observation in slot.observations
    )
    seedless_kernel_provenance = all(
        hasattr(observation, "provenance")
        and not hasattr(observation, "physical_seed")
        and not hasattr(observation, "observation_seed")
        for observation in slot.observations
    )
    item = {
        "contract_version": HYBRID_KERNEL_PHASE4_VALIDATION_VERSION,
        "slot_id": slot.slot_id,
        "root_seed": slot.root_seed,
        "configuration": asdict(slot.configuration),
        "flow_order": list(slot.flow_order),
        "policy_mode": policy_mode,
        "mc_workers": (
            mc_workers if policy_mode == HYBRID_SLOT_POLICY_MC else None
        ),
        "placement_paths": [placement.path.value for placement in slot.placements],
        "final_loads": [list(row) for row in slot.final_loads.loads],
        "ready_replicas": [
            {
                "stage": replica.choice.stage,
                "replica": replica.choice.replica,
                "pod_name": replica.pod_name,
                "pod_uid": replica.pod_uid,
                "node_name": replica.node_name,
            }
            for replica in outcome.discovery.replicas
        ],
        "placements": [
            {
                "flow_id": placement.flow.flow_id,
                "selected_stages": list(placement.action.stages),
                "selected_replicas": [
                    choice.replica for choice in placement.action.choices
                ],
                "skipped_stage": placement.skipped_stage,
                "planning_link_ms": planning[placement.action.choices],
                "measured_pair_ms": pair_by_flow[
                    placement.flow.flow_id
                ].latency_ms,
            }
            for placement in slot.placements
        ],
        "observations": [
            {
                "flow_id": observation.flow_id,
                "stage": observation.choice.stage,
                "replica": observation.choice.replica,
                "assigned_load": observation.assigned_load,
                "physical_processing_latency_ms": (
                    observation.physical_processing_latency_ms
                ),
                "observation_jitter_ms": observation.observation_jitter_ms,
                "learning_signal_ms": observation.learning_signal_ms,
                "estimated_state": observation.estimated_state,
                "pod_name": observation.provenance.pod_name,
                "pod_uid": observation.provenance.pod_uid,
            }
            for observation in slot.observations
        ],
        "observation_count": len(slot.observations),
        "measured_pair_count": len(slot.measured_pairs),
        "complete_placement_before_one_request": True,
        "skipped_stage_absent": skipped_absent,
        "separated_jitter_valid": separated_jitter,
        "seedless_kernel_provenance": seedless_kernel_provenance,
        "belief_retained_from_previous": retained_from_previous,
        "active_child_processes_after_slot": len(
            multiprocessing.active_children()
        ),
        "lookahead_process_workers": getattr(
            outcome,
            "lookahead_process_workers",
            0,
        ),
        "lookahead_pool_lifecycle_version": getattr(
            outcome,
            "lookahead_pool_lifecycle_version",
            None,
        ),
        "beliefs_before": _belief_mapping(slot.beliefs_before),
        "beliefs_after": _belief_mapping(slot.beliefs_after),
        "pure_kernel_replay_performed": parity_replay_enabled,
        "metrics": asdict(slot.metrics),
    }
    if parity_replay_enabled:
        item["pure_kernel_replay_parity"] = _replay_kernel_semantics(
            outcome=outcome,
            inputs=inputs,
            policy_mode=policy_mode,
            mc_workers=mc_workers,
        )
    control_plane = getattr(outcome, "control_plane", None)
    if control_plane is not None:
        validate_hybrid_control_plane_data_snapshot(control_plane)
        item["control_plane"] = control_plane
    return item


def run_small_live_gate(
    controller: HybridKernelControllerAdapter,
    inputs: HybridKernelControllerInputDocument,
    *,
    first_slot: int = 1,
    iterations: int = 2,
    policy_mode: str = HYBRID_SLOT_POLICY_LOOKAHEAD,
    mc_workers: int = DEFAULT_HYBRID_MC_WORKERS,
    on_slot_completed: CompletedSlotCallback | None = None,
) -> tuple[dict[str, object], ...]:
    if first_slot < 1 or iterations < 2:
        raise ValueError("Phase 4 requires a positive slot and at least two slots")
    evidence = []
    previous_beliefs = None
    for iteration, slot_id in enumerate(
        range(first_slot, first_slot + iterations), start=1
    ):
        outcome = controller.run_slot(slot_id)
        retained = (
            previous_beliefs is None
            or outcome.slot.beliefs_before == previous_beliefs
        )
        item = _slot_evidence(
            outcome=outcome,
            inputs=inputs,
            retained_from_previous=retained,
            policy_mode=policy_mode,
            mc_workers=mc_workers,
        )
        if item["observation_count"] != 2 * inputs.configuration.num_flows:
            raise RuntimeError("Phase 4 did not receive two observations per flow")
        if item["measured_pair_count"] != inputs.configuration.num_flows:
            raise RuntimeError("Phase 4 did not receive one measured pair per flow")
        for required in (
            "complete_placement_before_one_request",
            "skipped_stage_absent",
            "separated_jitter_valid",
            "seedless_kernel_provenance",
            "belief_retained_from_previous",
            "pure_kernel_replay_parity",
        ):
            if not item[required]:
                raise RuntimeError(f"Phase 4 validation failed: {required}")
        expected_children = item["lookahead_process_workers"]
        expected_lifecycle = (
            HYBRID_KERNEL_LOOKAHEAD_POOL_LIFECYCLE_VERSION
            if expected_children == HYBRID_KERNEL_LOOKAHEAD_WORKERS
            else None
        )
        if (
            expected_children not in {0, HYBRID_KERNEL_LOOKAHEAD_WORKERS}
            or item["lookahead_pool_lifecycle_version"]
            != expected_lifecycle
            or item["active_child_processes_after_slot"]
            != expected_children
        ):
            raise RuntimeError(
                "Hybrid controller child-process count does not match its "
                "lookahead pool lifecycle"
            )
        expected_path = (
            "monte-carlo"
            if policy_mode == HYBRID_SLOT_POLICY_MC
            else "deterministic-lookahead"
        )
        if set(item["placement_paths"]) != {expected_path}:
            raise RuntimeError("Hybrid controller used an unexpected policy path")
        if iteration == 1:
            first_routes = {
                tuple(placement["selected_stages"])
                for placement in item["placements"]
            }
            if not {(1, 3), (2, 3)}.issubset(first_routes):
                raise RuntimeError(
                    "Phase 4 first slot must exercise noncontiguous and "
                    "stage-2-first routes"
                )
        evidence.append(item)
        if on_slot_completed is not None:
            on_slot_completed(iteration, outcome.slot, item)
        previous_beliefs = outcome.slot.beliefs_after
    return tuple(evidence)


def run_kernel_experiment(
    controller: HybridKernelControllerAdapter,
    inputs: HybridKernelControllerInputDocument,
    *,
    first_slot: int = 1,
    max_iterations: int,
    policy_mode: str = HYBRID_SLOT_POLICY_LOOKAHEAD,
    mc_workers: int = DEFAULT_HYBRID_MC_WORKERS,
    parity_replay_enabled: bool = False,
    on_slot_completed: CompletedSlotCallback | None = None,
) -> HybridKernelExperimentResult:
    """Run sequential slots until frozen equilibrium or the explicit limit.

    Unlike ``run_small_live_gate``, this production lifecycle does not require
    particular route shapes or a minimum slot count.  The controller adapter
    remains responsible for complete Ready discovery, placement-before-traffic,
    exactly one complete request, telemetry validation, learning, and belief
    retention.
    """

    for value, field in (
        (first_slot, "first_slot"),
        (max_iterations, "max_iterations"),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{field} must be a positive integer")
    if not isinstance(parity_replay_enabled, bool):
        raise TypeError("parity_replay_enabled must be boolean")

    evidence: list[dict[str, object]] = []
    previous_beliefs = None
    for iteration, slot_id in enumerate(
        range(first_slot, first_slot + max_iterations), start=1
    ):
        outcome = controller.run_slot(slot_id)
        retained = (
            previous_beliefs is None
            or outcome.slot.beliefs_before == previous_beliefs
        )
        if not retained:
            raise RuntimeError(
                "Hybrid production controller did not retain beliefs between slots"
            )
        item = _slot_evidence(
            outcome=outcome,
            inputs=inputs,
            retained_from_previous=retained,
            policy_mode=policy_mode,
            mc_workers=mc_workers,
            parity_replay_enabled=parity_replay_enabled,
        )
        if (
            parity_replay_enabled
            and item.get("pure_kernel_replay_parity") is not True
        ):
            raise RuntimeError("Hybrid Pure/Kernel parity replay failed")
        item["experiment_contract_version"] = (
            HYBRID_KERNEL_EXPERIMENT_LIFECYCLE_VERSION
        )
        evidence.append(item)
        if on_slot_completed is not None:
            on_slot_completed(iteration, outcome.slot, item)
        previous_beliefs = outcome.slot.beliefs_after
        if outcome.slot.metrics.equilibrium:
            return HybridKernelExperimentResult(
                iterations_completed=iteration,
                reached_equilibrium=True,
                first_slot=first_slot,
                last_slot=slot_id,
                evidence=tuple(evidence),
            )

    return HybridKernelExperimentResult(
        iterations_completed=max_iterations,
        reached_equilibrium=False,
        first_slot=first_slot,
        last_slot=first_slot + max_iterations - 1,
        evidence=tuple(evidence),
    )


def _print_completed_slot(
    iteration: int,
    slot: HybridSlotResult,
    evidence: dict[str, object],
) -> None:
    print(format_hybrid_slot_metrics(slot, iteration=iteration), flush=True)
    print(
        HYBRID_SLOT_EVIDENCE_PREFIX
        + json.dumps(evidence, sort_keys=True, separators=(",", ":")),
        flush=True,
    )


def _controller_from_environment(
    environ: Mapping[str, str] | None = None,
    *,
    policy_mode: str = HYBRID_SLOT_POLICY_LOOKAHEAD,
    mc_workers: int = DEFAULT_HYBRID_MC_WORKERS,
    policy_root_seed: int = 2050,
) -> tuple[HybridKernelControllerAdapter, HybridKernelControllerInputDocument]:
    values = os.environ if environ is None else environ
    footprint_setting = values.get(HYBRID_CONTROL_PLANE_DATA_ENV, "0")
    if footprint_setting not in {"0", "1"}:
        raise ValueError(f"{HYBRID_CONTROL_PLANE_DATA_ENV} must be 0 or 1")
    control_plane_meter = (
        HybridControlPlaneDataMeter() if footprint_setting == "1" else None
    )
    inputs = load_controller_input_document(
        values.get(
            "HYBRID_CONTROLLER_INPUTS_PATH",
            "/etc/ibg-hybrid-controller/controller-inputs.json",
        )
    )
    ownership = DEFAULT_HYBRID_KERNEL_OWNERSHIP
    with ExitStack() as pending_resources:
        api = HybridKubernetesApi(
            ownership=ownership,
            control_plane_meter=control_plane_meter,
        )
        pending_resources.callback(api.close)
        discovery = HybridKubernetesReplicaDiscovery(
            api,
            inputs.configuration,
            ownership=ownership,
        )
        flow_generator = HybridKernelFlowGeneratorHttpClient(
            values.get(
                "FLOW_GENERATOR_URL",
                "http://ibg-hybrid-flow-generator.ibg-hybrid-testbed."
                "svc.cluster.local.:8080",
            ),
            control_plane_meter=control_plane_meter,
        )
        pending_resources.callback(flow_generator.close)
        uniform = (0.25, 0.25, 0.25, 0.25)
        controller = HybridKernelControllerAdapter(
            controller_inputs=inputs,
            discovery=discovery,
            flow_generator=flow_generator,
            initial_beliefs={item.choice: uniform for item in inputs.admission},
            policy_root_seed=policy_root_seed,
            policy_mode=policy_mode,
            mc_workers=mc_workers,
            control_plane_meter=control_plane_meter,
        )
        # Ownership transfers to the finite controller only after its complete
        # construction. Earlier failures close every already-created client.
        pending_resources.pop_all()
        return controller, inputs


def main() -> None:
    controller, inputs = _controller_from_environment()
    try:
        run_small_live_gate(
            controller,
            inputs,
            first_slot=int(os.environ.get("SLOT_ID", "1")),
            iterations=int(os.environ.get("MAX_ITERATIONS", "2")),
            policy_mode=HYBRID_SLOT_POLICY_LOOKAHEAD,
            mc_workers=DEFAULT_HYBRID_MC_WORKERS,
            on_slot_completed=_print_completed_slot,
        )
    finally:
        controller.close()


if __name__ == "__main__":
    main()
