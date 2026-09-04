"""Hybrid-specific Kernel traffic and stateful controller adapters."""

from __future__ import annotations

from collections import Counter
from concurrent.futures import Executor, ProcessPoolExecutor
from dataclasses import dataclass
from math import isclose
import multiprocessing
import sys
from typing import Mapping, Protocol, Sequence

import httpx

from IBG import latency_model as exact_latency

from .contracts import GlobalLoadState, ReplicaChoice, TwoStageAction
from .control_plane_footprint import HybridControlPlaneDataMeter
from .kernel_controller_config import HybridKernelControllerInputDocument
from .kernel_infrastructure_contract import (
    HYBRID_KERNEL_LOOKAHEAD_POOL_LIFECYCLE_VERSION,
    HYBRID_KERNEL_LOOKAHEAD_WORKERS,
    HybridKernelDiscoverySnapshot,
)
from .kernel_route_contracts import (
    HybridKernelRunSlotRequest,
    HybridKernelRunSlotResponse,
    build_hybrid_kernel_run_slot_request,
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


class HybridPosteriorMirrorPort(Protocol):
    """Transmit non-authoritative copies of completed posterior updates."""

    def mirror_slot(
        self,
        *,
        slot_id: int,
        beliefs_after: Mapping[ReplicaChoice, Sequence[float]],
        updated_choices: Sequence[ReplicaChoice],
    ) -> Mapping[str, object]:
        ...


class HybridKernelFlowGeneratorHttpClient:
    """Persistent controller-side client; exactly one POST per slot call."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 30.0,
        transport: httpx.BaseTransport | None = None,
        control_plane_meter: HybridControlPlaneDataMeter | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = float(timeout_seconds)
        self.transport = transport
        self.control_plane_meter = control_plane_meter
        if not self.base_url:
            raise ValueError("flow-generator base_url must not be empty")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._client = httpx.Client(
            timeout=self.timeout_seconds,
            transport=self.transport,
        )

    @property
    def is_closed(self) -> bool:
        return self._client.is_closed

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HybridKernelFlowGeneratorHttpClient:
        if self.is_closed:
            raise RuntimeError("Hybrid flow-generator HTTP client is closed")
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        del exc_type, exc_value, traceback
        self.close()

    def run_slot(
        self,
        request: HybridKernelRunSlotRequest,
    ) -> HybridKernelRunSlotResponse:
        if self.is_closed:
            raise RuntimeError("Hybrid flow-generator HTTP client is closed")
        payload = request.model_dump(mode="json")
        if self.control_plane_meter is not None:
            self.control_plane_meter.mark_route_dispatch()
        response = self._client.post(
            f"{self.base_url}/run-slot",
            json=payload,
        )
        if self.control_plane_meter is not None:
            self.control_plane_meter.mark_telemetry_received()
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            # The flow generator returns the whole downstream failure chain in
            # its body, including the originating ``RouteForwardingError``.
            # ``raise_for_status`` discards it, leaving only a bare 502.  Report
            # it on stderr and re-raise the original error unchanged: the
            # no-rejection route contract still fails the slot, with no retry
            # and no imputation.
            print(
                "Hybrid flow-generator slot request failed: HTTP "
                f"{error.response.status_code} {error.response.text}",
                file=sys.stderr,
                flush=True,
            )
            raise
        if self.control_plane_meter is not None:
            self.control_plane_meter.record_exchange(
                request_field="route_command_tx",
                response_field="selected_telemetry_rx",
                request_payload_bytes=len(response.request.content),
                response_payload_bytes=len(response.content),
            )
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
    control_plane: Mapping[str, object] | None = None
    posterior_mirror: Mapping[str, object] | None = None
    lookahead_process_workers: int = 0
    lookahead_pool_lifecycle_version: str | None = None
    controller_contract_version: str = HYBRID_KERNEL_CONTROLLER_ADAPTER_VERSION

    def __post_init__(self) -> None:
        if self.lookahead_process_workers not in {
            0,
            HYBRID_KERNEL_LOOKAHEAD_WORKERS,
        }:
            raise ValueError("unexpected Hybrid lookahead process-worker count")
        expected_version = (
            HYBRID_KERNEL_LOOKAHEAD_POOL_LIFECYCLE_VERSION
            if self.lookahead_process_workers
            else None
        )
        if self.lookahead_pool_lifecycle_version != expected_version:
            raise ValueError("lookahead pool lifecycle provenance is inconsistent")


class HybridKernelControllerAdapter:
    """Retain beliefs and own finite controller-side runtime resources."""

    def __init__(
        self,
        *,
        controller_inputs: HybridKernelControllerInputDocument,
        discovery: HybridKernelReadyDiscoveryPort,
        flow_generator: HybridKernelFlowGeneratorPort,
        initial_beliefs: Mapping[ReplicaChoice, Sequence[float]],
        policy_root_seed: int = 2050,
        policy_mode: str = HYBRID_SLOT_POLICY_LOOKAHEAD,
        mc_workers: int = DEFAULT_HYBRID_MC_WORKERS,
        policy: IBGHybridPolicy | None = None,
        control_plane_meter: HybridControlPlaneDataMeter | None = None,
        posterior_mirror: HybridPosteriorMirrorPort | None = None,
        lookahead_executor: Executor | None = None,
    ) -> None:
        expected = {item.choice for item in controller_inputs.admission}
        if set(initial_beliefs) != expected:
            raise ValueError("initial beliefs must cover every Hybrid replica exactly")
        if policy_mode not in {
            HYBRID_SLOT_POLICY_LOOKAHEAD,
            HYBRID_SLOT_POLICY_MC,
        }:
            raise ValueError("unsupported Hybrid controller policy mode")
        if lookahead_executor is not None and not isinstance(
            lookahead_executor,
            Executor,
        ):
            raise TypeError(
                "lookahead_executor must be a concurrent.futures.Executor"
            )
        if (
            lookahead_executor is not None
            and policy_mode != HYBRID_SLOT_POLICY_LOOKAHEAD
        ):
            raise ValueError(
                "lookahead_executor is valid only for deterministic lookahead"
            )
        self.controller_inputs = controller_inputs
        self.discovery = discovery
        self.flow_generator = flow_generator
        self.policy_root_seed = policy_root_seed
        self.policy_mode = policy_mode
        self.mc_workers = mc_workers
        self.policy = policy or IBGHybridPolicy(
            controller_inputs.configuration,
            DEFAULT_HYBRID_POLICY_PARAMETERS,
        )
        self.control_plane_meter = control_plane_meter
        self.posterior_mirror = posterior_mirror
        self._closed = False
        self._beliefs = {
            choice: tuple(float(value) for value in initial_beliefs[choice])
            for choice in sorted(expected)
        }
        self._lookahead_executor = None
        if self.policy_mode == HYBRID_SLOT_POLICY_LOOKAHEAD:
            self._lookahead_executor = lookahead_executor or ProcessPoolExecutor(
                max_workers=HYBRID_KERNEL_LOOKAHEAD_WORKERS,
                mp_context=multiprocessing.get_context("spawn"),
            )

    @property
    def beliefs(self) -> Mapping[ReplicaChoice, BeliefVector]:
        return dict(self._beliefs)

    @property
    def is_closed(self) -> bool:
        return self._closed

    @property
    def lookahead_executor(self) -> Executor | None:
        return self._lookahead_executor

    @property
    def lookahead_process_workers(self) -> int:
        return (
            HYBRID_KERNEL_LOOKAHEAD_WORKERS
            if self.policy_mode == HYBRID_SLOT_POLICY_LOOKAHEAD
            else 0
        )

    def close(self) -> None:
        """Close owned controller-side ports once, preserving the first error."""

        if self._closed:
            return
        self._closed = True
        first_error: Exception | None = None
        lookahead_executor, self._lookahead_executor = (
            self._lookahead_executor,
            None,
        )
        if lookahead_executor is not None:
            try:
                lookahead_executor.shutdown(wait=True, cancel_futures=True)
            except Exception as error:
                first_error = error
        for resource in (
            self.posterior_mirror,
            self.flow_generator,
            self.discovery,
        ):
            if resource is None:
                continue
            close = getattr(resource, "close", None)
            if not callable(close):
                continue
            try:
                close()
            except Exception as error:
                if first_error is None:
                    first_error = error
        if first_error is not None:
            raise first_error

    def __enter__(self) -> HybridKernelControllerAdapter:
        if self._closed:
            raise RuntimeError("Hybrid Kernel controller is closed")
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        del exc_type, exc_value, traceback
        self.close()

    def run_slot(
        self,
        slot_id: int,
        *,
        flows: tuple[HybridFlow, ...] | None = None,
        discovery_wait: Mapping[str, object] | None = None,
    ) -> HybridKernelControllerSlotResult:
        if self._closed:
            raise RuntimeError("Hybrid Kernel controller is closed")
        if self.control_plane_meter is not None:
            self.control_plane_meter.begin_slot()
            self.control_plane_meter.begin_discovery()
        try:
            snapshot = self.discovery.wait_for_complete_ready(
                **dict(discovery_wait or {})
            )
        finally:
            if self.control_plane_meter is not None:
                self.control_plane_meter.end_discovery()
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
            mc_workers=self.mc_workers,
            lookahead_executor=self._lookahead_executor,
        )
        if traffic.requests_submitted != 1:
            raise RuntimeError("Hybrid controller must submit exactly one slot request")
        control_plane = (
            None
            if self.control_plane_meter is None
            else self.control_plane_meter.finish_slot()
        )
        posterior_mirror = None
        if self.posterior_mirror is not None:
            posterior_mirror = self.posterior_mirror.mirror_slot(
                slot_id=slot_id,
                beliefs_after=result.beliefs_after_mapping,
                updated_choices=tuple(
                    sorted({observation.choice for observation in result.observations})
                ),
            )
        self._beliefs = dict(result.beliefs_after)
        process_workers = self.lookahead_process_workers
        return HybridKernelControllerSlotResult(
            discovery=snapshot,
            slot=result,
            control_plane=control_plane,
            posterior_mirror=posterior_mirror,
            lookahead_process_workers=process_workers,
            lookahead_pool_lifecycle_version=(
                HYBRID_KERNEL_LOOKAHEAD_POOL_LIFECYCLE_VERSION
                if process_workers
                else None
            ),
        )
