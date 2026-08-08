"""Small live-gate validator for Hybrid Kernel Infrastructure Phase 4."""

from __future__ import annotations

from dataclasses import asdict, replace
import json
import os
from typing import Mapping

from .contracts import GlobalLoadState, ReplicaChoice
from .kernel_controller import (
    HybridKernelControllerAdapter,
    HybridKernelFlowGeneratorHttpClient,
)
from .kernel_controller_config import (
    HybridKernelControllerInputDocument,
    load_controller_input_document,
)
from .kernel_infrastructure_contract import DEFAULT_HYBRID_KERNEL_OWNERSHIP
from .kernel_kubernetes_discovery import (
    HybridKubernetesApi,
    HybridKubernetesReplicaDiscovery,
)
from .phase0_contract import DEFAULT_HYBRID_POLICY_PARAMETERS
from .policy import IBGHybridPolicy
from .runner import run_hybrid_slot
from .slot_contracts import (
    HybridFlow,
    HybridReplica,
    HybridSimulationResult,
    HybridSlotInput,
)


HYBRID_KERNEL_PHASE4_VALIDATION_VERSION = (
    "ibg-hybrid-kernel-phase4-small-validation-v1"
)


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
) -> dict[str, object]:
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
    return {
        "contract_version": HYBRID_KERNEL_PHASE4_VALIDATION_VERSION,
        "slot_id": slot.slot_id,
        "configuration": asdict(slot.configuration),
        "flow_order": list(slot.flow_order),
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
        "beliefs_before": _belief_mapping(slot.beliefs_before),
        "beliefs_after": _belief_mapping(slot.beliefs_after),
        "pure_kernel_replay_parity": _replay_kernel_semantics(
            outcome=outcome,
            inputs=inputs,
        ),
        "metrics": asdict(slot.metrics),
    }


def run_small_live_gate(
    controller: HybridKernelControllerAdapter,
    inputs: HybridKernelControllerInputDocument,
    *,
    first_slot: int = 1,
    iterations: int = 2,
) -> tuple[dict[str, object], ...]:
    if first_slot < 1 or iterations < 2:
        raise ValueError("Phase 4 requires a positive slot and at least two slots")
    evidence = []
    previous_beliefs = None
    for slot_id in range(first_slot, first_slot + iterations):
        outcome = controller.run_slot(slot_id)
        retained = (
            previous_beliefs is None
            or outcome.slot.beliefs_before == previous_beliefs
        )
        item = _slot_evidence(
            outcome=outcome,
            inputs=inputs,
            retained_from_previous=retained,
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
        evidence.append(item)
        previous_beliefs = outcome.slot.beliefs_after
    first_routes = {
        tuple(item["selected_stages"])
        for item in evidence[0]["placements"]
    }
    if not {(1, 3), (2, 3)}.issubset(first_routes):
        raise RuntimeError(
            "Phase 4 first slot must exercise noncontiguous and stage-2-first routes"
        )
    return tuple(evidence)


def _controller_from_environment(
    environ: Mapping[str, str] | None = None,
) -> tuple[HybridKernelControllerAdapter, HybridKernelControllerInputDocument]:
    values = os.environ if environ is None else environ
    inputs = load_controller_input_document(
        values.get(
            "HYBRID_CONTROLLER_INPUTS_PATH",
            "/etc/ibg-hybrid-controller/controller-inputs.json",
        )
    )
    ownership = DEFAULT_HYBRID_KERNEL_OWNERSHIP
    discovery = HybridKubernetesReplicaDiscovery(
        HybridKubernetesApi(ownership=ownership),
        inputs.configuration,
        ownership=ownership,
    )
    flow_generator = HybridKernelFlowGeneratorHttpClient(
        values.get(
            "FLOW_GENERATOR_URL",
            "http://ibg-hybrid-flow-generator.ibg-hybrid-testbed."
            "svc.cluster.local.:8080",
        )
    )
    uniform = (0.25, 0.25, 0.25, 0.25)
    return (
        HybridKernelControllerAdapter(
            controller_inputs=inputs,
            discovery=discovery,
            flow_generator=flow_generator,
            initial_beliefs={item.choice: uniform for item in inputs.admission},
        ),
        inputs,
    )


def main() -> None:
    controller, inputs = _controller_from_environment()
    evidence = run_small_live_gate(
        controller,
        inputs,
        first_slot=int(os.environ.get("SLOT_ID", "1")),
        iterations=int(os.environ.get("MAX_ITERATIONS", "2")),
    )
    for item in evidence:
        print(json.dumps(item, sort_keys=True, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    main()
