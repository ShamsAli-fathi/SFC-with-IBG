"""Hybrid-specific Kernel traffic and stateful controller adapters."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from math import isclose
from typing import Mapping, Protocol, Sequence

import httpx

from IBG import latency_model as exact_latency

from .contracts import GlobalLoadState, ReplicaChoice, TwoStageAction
from .kernel_controller_config import HybridKernelControllerInputDocument
from .kernel_infrastructure_contract import HybridKernelDiscoverySnapshot
from .kernel_route_contracts import (
    HybridKernelRunSlotRequest,
    HybridKernelRunSlotResponse,
    build_hybrid_kernel_run_slot_request,
)
from .phase0_contract import DEFAULT_HYBRID_POLICY_PARAMETERS
from .policy import IBGHybridPolicy
from .runner import HYBRID_SLOT_POLICY_LOOKAHEAD, run_hybrid_slot
from .slot_contracts import (
    BeliefVector,
    HybridFlow,
    HybridMeasuredPair,
    HybridReplica,
    HybridSimulationResult,
    HybridSlotInput,
    HybridSlotResult,
)


HYBRID_KERNEL_OBSERVATION_PROVENANCE_VERSION = (
    "ibg-hybrid-kernel-observation-provenance-v1"
)
HYBRID_KERNEL_CONTROLLER_ADAPTER_VERSION = (
    "ibg-hybrid-kernel-controller-adapter-v1"
)


class HybridKernelFlowGeneratorPort(Protocol):
    """Submit one complete slot request and return complete telemetry."""

    def run_slot(
        self,
        request: HybridKernelRunSlotRequest,
    ) -> HybridKernelRunSlotResponse:
        ...


class HybridKernelReadyDiscoveryPort(Protocol):
    def wait_for_complete_ready(self, **kwargs) -> HybridKernelDiscoverySnapshot:
        ...


class HybridKernelFlowGeneratorHttpClient:
    """Synchronous controller-side client; exactly one POST per slot call."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = float(timeout_seconds)
        self.transport = transport
        if not self.base_url:
            raise ValueError("flow-generator base_url must not be empty")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

    def run_slot(
        self,
        request: HybridKernelRunSlotRequest,
    ) -> HybridKernelRunSlotResponse:
        with httpx.Client(
            timeout=self.timeout_seconds,
            transport=self.transport,
        ) as client:
            response = client.post(
                f"{self.base_url}/run-slot",
                json=request.model_dump(mode="json"),
            )
            response.raise_for_status()
            return HybridKernelRunSlotResponse.model_validate(response.json())


@dataclass(frozen=True)
class HybridKernelObservationProvenance:
    """Kernel source identity with no fabricated simulation seed fields."""

    pod_name: str
    pod_uid: str
    endpoint: str
    source: str = "hybrid-kernel-flow-generator"
    contract_version: str = HYBRID_KERNEL_OBSERVATION_PROVENANCE_VERSION

    def __post_init__(self) -> None:
        for field in ("pod_name", "pod_uid", "endpoint", "source"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field} must be a nonempty string")
        if self.contract_version != HYBRID_KERNEL_OBSERVATION_PROVENANCE_VERSION:
            raise ValueError("unexpected Kernel observation provenance version")


@dataclass(frozen=True)
class HybridKernelSelectedObservation:
    """Selected Kernel observation consumed by the existing learning boundary."""

    flow_id: int
    choice: ReplicaChoice
    assigned_load: int
    physical_processing_latency_ms: float
    observation_jitter_ms: float
    learning_signal_ms: float
    likelihood: BeliefVector
    estimated_state: int
    provenance: HybridKernelObservationProvenance

    def __post_init__(self) -> None:
        if self.flow_id < 1 or self.assigned_load < 1:
            raise ValueError("flow identity and assigned load must be positive")
        if not isclose(
            self.learning_signal_ms,
            self.physical_processing_latency_ms + self.observation_jitter_ms,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ValueError(
                "Kernel learning signal must equal physical plus observation jitter"
            )
        expected = exact_latency.learning_signal_likelihood(
            self.learning_signal_ms,
            self.assigned_load,
        )
        if any(
            not isclose(actual, wanted, rel_tol=0.0, abs_tol=1e-9)
            for actual, wanted in zip(self.likelihood, expected, strict=True)
        ):
            raise ValueError("Kernel likelihood does not match the exact convolution")
        if self.estimated_state != exact_latency.estimate_state(expected):
            raise ValueError("Kernel estimated state does not match its likelihood")

    @property
    def stage(self) -> int:
        return self.choice.stage

    @property
    def replica_id(self) -> int:
        return self.choice.replica

    @property
    def congestion(self) -> int:
        return self.assigned_load

    @property
    def signal(self) -> float:
        return self.learning_signal_ms

    @property
    def measured_latency_ms(self) -> float:
        return self.physical_processing_latency_ms


class HybridKernelSlotTrafficAdapter:
    """Execute one complete placement and convert only selected telemetry."""

    def __init__(
        self,
        discovery: HybridKernelDiscoverySnapshot,
        flow_generator: HybridKernelFlowGeneratorPort,
    ) -> None:
        self.discovery = discovery
        self.flow_generator = flow_generator
        self.requests_submitted = 0

    def execute(
        self,
        *,
        root_seed: int,
        slot_id: int,
        actions_by_flow: Mapping[int, TwoStageAction],
        final_loads: GlobalLoadState,
        replicas: Mapping[ReplicaChoice, HybridReplica],
        measured_pair_latency_ms: Mapping[
            tuple[ReplicaChoice, ReplicaChoice],
            float,
        ],
    ) -> HybridSimulationResult:
        del root_seed
        if measured_pair_latency_ms:
            raise RuntimeError(
                "Kernel execution must not receive simulated pair-outcome inputs"
            )
        expected_loads = Counter(
            choice
            for action in actions_by_flow.values()
            for choice in action.choices
        )
        for choice in replicas:
            if final_loads.load_for(choice) != expected_loads.get(choice, 0):
                raise RuntimeError("final Hybrid loads do not match complete placement")
        request = build_hybrid_kernel_run_slot_request(
            slot_id=slot_id,
            configuration=self.discovery.configuration,
            actions_by_flow=actions_by_flow,
            discovery=self.discovery,
        )
        self.requests_submitted += 1
        response = self.flow_generator.run_slot(request)
        return self._convert_complete_response(request, response)

    def _convert_complete_response(
        self,
        request: HybridKernelRunSlotRequest,
        response: HybridKernelRunSlotResponse,
    ) -> HybridSimulationResult:
        if response.slot_id != request.slot_id:
            raise RuntimeError("Hybrid flow-generator response slot mismatch")
        request_by_flow = {route.flow_id: route for route in request.routes}
        response_by_flow = {flow.flow_id: flow for flow in response.flows}
        if set(response_by_flow) != set(request_by_flow):
            raise RuntimeError("Hybrid flow-generator response has partial flow coverage")
        if response.observation_count != 2 * len(request.routes):
            raise RuntimeError("Hybrid flow-generator returned a partial observation set")
        if response.measured_pair_count != len(request.routes):
            raise RuntimeError("Hybrid flow-generator must return one pair per flow")

        discovered = self.discovery.replica_by_choice()
        observations = []
        pairs = []
        for flow_id in sorted(request_by_flow):
            route = request_by_flow[flow_id]
            telemetry = response_by_flow[flow_id]
            expected_choices = tuple(hop.choice for hop in route.hops)
            if (
                telemetry.selected_choices != expected_choices
                or telemetry.skipped_stage != route.skipped_stage
            ):
                raise RuntimeError("Hybrid telemetry does not match selected route")
            for target, hop in zip(route.hops, telemetry.hops, strict=True):
                replica = discovered[target.choice]
                if (
                    hop.assigned_load != target.assigned_load
                    or hop.pod_name != replica.pod_name
                    or hop.endpoint.rstrip("/") != replica.endpoint.rstrip("/")
                ):
                    raise RuntimeError(
                        "Hybrid selected telemetry identity/load does not match discovery"
                    )
                observations.append(
                    HybridKernelSelectedObservation(
                        flow_id=flow_id,
                        choice=target.choice,
                        assigned_load=hop.assigned_load,
                        physical_processing_latency_ms=(
                            hop.physical_processing_latency_ms
                        ),
                        observation_jitter_ms=hop.observation_jitter_ms,
                        learning_signal_ms=hop.learning_signal_ms,
                        likelihood=hop.likelihood,
                        estimated_state=hop.estimated_state,
                        provenance=HybridKernelObservationProvenance(
                            pod_name=replica.pod_name,
                            pod_uid=replica.pod_uid,
                            endpoint=replica.endpoint,
                        ),
                    )
                )
            pair = telemetry.measured_pair
            if route.skipped_stage in {pair.source_stage, pair.target_stage}:
                raise RuntimeError("skipped stage appeared in measured-pair telemetry")
            pairs.append(
                HybridMeasuredPair(
                    flow_id=flow_id,
                    source=expected_choices[0],
                    target=expected_choices[1],
                    latency_ms=pair.link_cost_ms,
                )
            )
        return HybridSimulationResult(
            observations=tuple(observations),
            measured_pairs=tuple(pairs),
        )


@dataclass(frozen=True)
class HybridKernelControllerSlotResult:
    discovery: HybridKernelDiscoverySnapshot
    slot: HybridSlotResult
    controller_contract_version: str = HYBRID_KERNEL_CONTROLLER_ADAPTER_VERSION


class HybridKernelControllerAdapter:
    """Retain beliefs while delegating all placement mathematics to Hybrid."""

    def __init__(
        self,
        *,
        controller_inputs: HybridKernelControllerInputDocument,
        discovery: HybridKernelReadyDiscoveryPort,
        flow_generator: HybridKernelFlowGeneratorPort,
        initial_beliefs: Mapping[ReplicaChoice, Sequence[float]],
        policy_root_seed: int = 2050,
        policy_mode: str = HYBRID_SLOT_POLICY_LOOKAHEAD,
        policy: IBGHybridPolicy | None = None,
    ) -> None:
        expected = {item.choice for item in controller_inputs.admission}
        if set(initial_beliefs) != expected:
            raise ValueError("initial beliefs must cover every Hybrid replica exactly")
        self.controller_inputs = controller_inputs
        self.discovery = discovery
        self.flow_generator = flow_generator
        self.policy_root_seed = policy_root_seed
        self.policy_mode = policy_mode
        self.policy = policy or IBGHybridPolicy(
            controller_inputs.configuration,
            DEFAULT_HYBRID_POLICY_PARAMETERS,
        )
        self._beliefs = {
            choice: tuple(float(value) for value in initial_beliefs[choice])
            for choice in sorted(expected)
        }

    @property
    def beliefs(self) -> Mapping[ReplicaChoice, BeliefVector]:
        return dict(self._beliefs)

    def run_slot(
        self,
        slot_id: int,
        *,
        flows: tuple[HybridFlow, ...] | None = None,
        discovery_wait: Mapping[str, object] | None = None,
    ) -> HybridKernelControllerSlotResult:
        snapshot = self.discovery.wait_for_complete_ready(
            **dict(discovery_wait or {})
        )
        configuration = self.controller_inputs.configuration
        if snapshot.configuration != configuration:
            raise RuntimeError("Ready snapshot configuration does not match controller")
        admission = {
            item.choice: item for item in self.controller_inputs.admission
        }
        selected_flows = flows or tuple(
            HybridFlow(flow_id)
            for flow_id in range(1, configuration.num_flows + 1)
        )
        slot_input = HybridSlotInput(
            configuration=configuration,
            parameters=DEFAULT_HYBRID_POLICY_PARAMETERS,
            root_seed=self.policy_root_seed,
            slot_id=slot_id,
            flows=selected_flows,
            replicas=tuple(
                HybridReplica(
                    choice=replica.choice,
                    belief=self._beliefs[replica.choice],
                    ready=True,
                    max_assigned_flows=(
                        admission[replica.choice].max_assigned_flows
                    ),
                    hidden_state=None,
                )
                for replica in snapshot.replicas
            ),
            planning_pair_links=self.controller_inputs.planning_pair_links,
            simulated_pair_outcomes=(),
            initial_loads=GlobalLoadState.empty(configuration),
        )
        traffic = HybridKernelSlotTrafficAdapter(snapshot, self.flow_generator)
        result = run_hybrid_slot(
            slot_input,
            policy=self.policy,
            simulation_adapter=traffic,
            policy_mode=self.policy_mode,
        )
        if traffic.requests_submitted != 1:
            raise RuntimeError("Hybrid controller must submit exactly one slot request")
        self._beliefs = dict(result.beliefs_after)
        return HybridKernelControllerSlotResult(snapshot, result)

