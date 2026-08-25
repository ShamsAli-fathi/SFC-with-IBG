"""Finite Greedy Kernel controller over completed sequential placement semantics."""

from __future__ import annotations

from dataclasses import dataclass
from math import isclose
import time
from typing import Callable, Mapping, Protocol, Sequence

import httpx

from IBG import latency_model

from .contracts import (
    PublicReplicaState,
    ReplicaIdentity,
)
from .kernel_contracts import (
    DEFAULT_GREEDY_KERNEL_OWNERSHIP,
    GREEDY_KERNEL_FLOW_GENERATOR_TIMEOUT_SECONDS,
    GreedyClientLifecycle,
    GreedyKernelControllerConfiguration,
    GreedyKernelControllerExperimentResult,
    GreedyKernelControllerSlotResult,
    GreedyKernelDiscoverySnapshot,
    GreedyKernelOwnership,
    GreedyKernelPhaseTimings,
)
from .kernel_kubernetes_discovery import (
    GreedyKubernetesApi,
    GreedyKubernetesReplicaDiscovery,
)
from .kernel_route_contracts import (
    GreedyKernelRunSlotRequest,
    GreedyKernelRunSlotResponse,
    build_greedy_kernel_run_slot_request,
)
from .learning import apply_selected_learning
from .metrics import compute_slot_metrics
from .policy import GreedyPolicy
from .simulation import resolve_flow_order
from .slot_contracts import (
    GREEDY_EXPERIMENT_STOP_EQUILIBRIUM,
    GREEDY_EXPERIMENT_STOP_MAX_ITERATIONS,
    GREEDY_SLOT_CONTRACT_VERSION,
    BeliefVector,
    GreedyExperimentResult,
    GreedyMeasuredPair,
    GreedyPlacement,
    GreedySimulationResult,
    GreedySlotResult,
    GreedySlotTimings,
)


GREEDY_KERNEL_CONTROLLER_ADAPTER_VERSION = "greedy-kernel-controller-adapter-v1"
GREEDY_KERNEL_OBSERVATION_PROVENANCE_VERSION = (
    "greedy-kernel-observation-provenance-v1"
)


class GreedyKernelFlowGeneratorPort(Protocol):
    def run_slot(
        self,
        request: GreedyKernelRunSlotRequest,
    ) -> GreedyKernelRunSlotResponse:
        ...


class GreedyKernelReadyDiscoveryPort(Protocol):
    def wait_for_complete_ready(self, **kwargs) -> GreedyKernelDiscoverySnapshot:
        ...


class GreedyKernelFlowGeneratorHttpClient:
    """Own one synchronous controller-to-generator client across all slots."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = GREEDY_KERNEL_FLOW_GENERATOR_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = float(timeout_seconds)
        if not self.base_url:
            raise ValueError("flow-generator base_url must not be empty")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._client = httpx.Client(
            timeout=self.timeout_seconds,
            transport=transport,
        )
        self._close_calls = 0
        self.requests_submitted = 0

    @property
    def is_closed(self) -> bool:
        return self._client.is_closed

    @property
    def lifecycle(self) -> GreedyClientLifecycle:
        return GreedyClientLifecycle(
            owner="finite-controller-flow-generator",
            scope="controller-lifetime",
            client_instances=1,
            close_calls=self._close_calls,
            closed=self.is_closed,
        )

    def close(self) -> None:
        if self.is_closed:
            return
        self._client.close()
        self._close_calls += 1

    def __enter__(self) -> GreedyKernelFlowGeneratorHttpClient:
        if self.is_closed:
            raise RuntimeError("Greedy flow-generator HTTP client is closed")
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        del exc_type, exc_value, traceback
        self.close()

    def run_slot(
        self,
        request: GreedyKernelRunSlotRequest,
    ) -> GreedyKernelRunSlotResponse:
        if self.is_closed:
            raise RuntimeError("Greedy flow-generator HTTP client is closed")
        self.requests_submitted += 1
        response = self._client.post(
            f"{self.base_url}/run-slot",
            json=request.model_dump(mode="json"),
        )
        response.raise_for_status()
        return GreedyKernelRunSlotResponse.model_validate(response.json())


@dataclass(frozen=True)
class GreedyKernelObservationProvenance:
    pod_name: str
    pod_uid: str
    endpoint: str
    source: str = "greedy-kernel-flow-generator"
    contract_version: str = GREEDY_KERNEL_OBSERVATION_PROVENANCE_VERSION

    def __post_init__(self) -> None:
        for name in ("pod_name", "pod_uid", "endpoint", "source"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise ValueError(f"{name} must be a nonempty string")
        if self.contract_version != GREEDY_KERNEL_OBSERVATION_PROVENANCE_VERSION:
            raise ValueError("unexpected Kernel observation provenance version")


@dataclass(frozen=True)
class GreedyKernelSelectedObservation:
    """Selected physical/learning telemetry without fabricated seed fields."""

    flow_id: int
    identity: ReplicaIdentity
    assigned_load: int
    physical_processing_latency_ms: float
    observation_jitter_ms: float
    learning_signal_ms: float
    likelihood: BeliefVector
    estimated_state: int
    route_position: int
    next_identity: ReplicaIdentity | None
    provenance: GreedyKernelObservationProvenance

    def __post_init__(self) -> None:
        if self.flow_id < 1 or self.assigned_load < 1:
            raise ValueError("flow identity and assigned load must be positive")
        if self.route_position not in (1, 2):
            raise ValueError("route_position must be 1 or 2")
        if (self.route_position == 1) != (self.next_identity is not None):
            raise ValueError("next identity must exist only at route position 1")
        if self.next_identity is not None and self.next_identity.stage <= self.identity.stage:
            raise ValueError("next selected identity must use a later stage")
        if not isclose(
            self.learning_signal_ms,
            self.physical_processing_latency_ms + self.observation_jitter_ms,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ValueError("Kernel learning signal must equal physical plus observation")
        expected = latency_model.learning_signal_likelihood(
            self.learning_signal_ms,
            self.assigned_load,
        )
        if any(
            not isclose(actual, wanted, rel_tol=0.0, abs_tol=1e-9)
            for actual, wanted in zip(self.likelihood, expected, strict=True)
        ):
            raise ValueError("Kernel likelihood does not match exact convolution")
        if self.estimated_state != latency_model.estimate_state(expected):
            raise ValueError("Kernel estimated state does not match likelihood")

    @property
    def stage(self) -> int:
        return self.identity.stage

    @property
    def replica_id(self) -> int:
        return self.identity.replica

    @property
    def congestion(self) -> int:
        return self.assigned_load

    @property
    def signal(self) -> float:
        return self.learning_signal_ms


class GreedyKernelSlotTrafficAdapter:
    """Build one slot request, then validate complete selected-only telemetry."""

    def __init__(
        self,
        discovery: GreedyKernelDiscoverySnapshot,
        flow_generator: GreedyKernelFlowGeneratorPort,
    ) -> None:
        self.discovery = discovery
        self.flow_generator = flow_generator
        self.requests_submitted = 0

    def build_request(
        self,
        *,
        slot_id: int,
        actions_by_flow,
    ) -> GreedyKernelRunSlotRequest:
        return build_greedy_kernel_run_slot_request(
            slot_id=slot_id,
            configuration=self.discovery.configuration,
            actions_by_flow=actions_by_flow,
            discovery=self.discovery,
        )

    def dispatch(
        self,
        request: GreedyKernelRunSlotRequest,
    ) -> GreedyKernelRunSlotResponse:
        self.requests_submitted += 1
        return self.flow_generator.run_slot(request)

    def convert_complete_response(
        self,
        *,
        request: GreedyKernelRunSlotRequest,
        response: GreedyKernelRunSlotResponse,
        final_loads,
    ) -> GreedySimulationResult:
        if response.slot_id != request.slot_id:
            raise RuntimeError("flow-generator response slot mismatch")
        request_by_flow = {route.flow_id: route for route in request.routes}
        response_by_flow = {flow.flow_id: flow for flow in response.flows}
        if len(response.flows) != len(response_by_flow) or set(response_by_flow) != set(
            request_by_flow
        ):
            raise RuntimeError("flow-generator response has partial/duplicate flow coverage")
        if response.observation_count != 2 * len(request.routes):
            raise RuntimeError("flow-generator returned a partial selected-hop set")
        if response.measured_pair_count != len(request.routes):
            raise RuntimeError("flow-generator must return one selected pair per flow")

        discovered = self.discovery.replica_by_identity()
        observations = []
        measured_pairs = []
        for flow_id in sorted(request_by_flow):
            route = request_by_flow[flow_id]
            telemetry = response_by_flow[flow_id]
            if telemetry.bypassed_stages != route.bypassed_stages:
                raise RuntimeError("telemetry bypass set does not match selected route")
            if len(telemetry.hops) != 2:
                raise RuntimeError("telemetry must contain exactly two selected hops")
            for target, hop in zip(route.hops, telemetry.hops, strict=True):
                replica = discovered[target.identity]
                if (
                    hop.slot_id != request.slot_id
                    or hop.flow_id != flow_id
                    or hop.identity != target.identity
                    or hop.route_position != target.route_position
                    or hop.next_identity != target.next_identity
                    or hop.assigned_load != target.assigned_load
                    or hop.assigned_load != final_loads.load_for(target.identity)
                    or hop.pod_name != replica.pod_name
                    or hop.endpoint.rstrip("/") != replica.endpoint.rstrip("/")
                ):
                    raise RuntimeError(
                        "selected telemetry flow/slot/identity/load/position/next-hop mismatch"
                    )
                observations.append(
                    GreedyKernelSelectedObservation(
                        flow_id=flow_id,
                        identity=target.identity,
                        assigned_load=hop.assigned_load,
                        physical_processing_latency_ms=(
                            hop.physical_processing_latency_ms
                        ),
                        observation_jitter_ms=hop.observation_jitter_ms,
                        learning_signal_ms=hop.learning_signal_ms,
                        likelihood=hop.likelihood,
                        estimated_state=hop.estimated_state,
                        route_position=hop.route_position,
                        next_identity=hop.next_identity,
                        provenance=GreedyKernelObservationProvenance(
                            pod_name=replica.pod_name,
                            pod_uid=replica.pod_uid,
                            endpoint=replica.endpoint,
                        ),
                    )
                )
            pair = telemetry.measured_pair
            first, second = route.hops
            if (
                pair.slot_id != request.slot_id
                or pair.flow_id != flow_id
                or pair.source != first.identity
                or pair.target != second.identity
                or pair.source_pod_name != discovered[first.identity].pod_name
                or pair.target_pod_name != discovered[second.identity].pod_name
                or pair.target_endpoint.rstrip("/")
                != discovered[second.identity].endpoint.rstrip("/")
            ):
                raise RuntimeError("measured selected-pair telemetry mismatch")
            measured_pairs.append(
                GreedyMeasuredPair(
                    flow_id=flow_id,
                    source=first.identity,
                    target=second.identity,
                    latency_ms=pair.measured_pair_latency_ms,
                )
            )
        return GreedySimulationResult(
            observations=tuple(observations),
            measured_pairs=tuple(measured_pairs),
        )


class GreedyKernelController:
    """Retain one policy/cache and beliefs for exactly one finite experiment."""

    def __init__(
        self,
        *,
        controller_configuration: GreedyKernelControllerConfiguration,
        discovery: GreedyKernelReadyDiscoveryPort,
        flow_generator: GreedyKernelFlowGeneratorPort,
        initial_beliefs: Mapping[ReplicaIdentity, Sequence[float]],
        policy: GreedyPolicy | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        configuration = controller_configuration.configuration
        expected = {
            ReplicaIdentity(stage, replica)
            for stage in configuration.stages
            for replica in configuration.replica_ids
        }
        if set(initial_beliefs) != expected:
            raise ValueError("initial beliefs must cover every Greedy replica exactly")
        self.controller_configuration = controller_configuration
        self.discovery = discovery
        self.flow_generator = flow_generator
        self.policy = policy or GreedyPolicy(configuration)
        if self.policy.configuration != configuration:
            raise ValueError("policy configuration does not match controller")
        self.clock = clock
        self._beliefs = {
            identity: tuple(float(value) for value in initial_beliefs[identity])
            for identity in sorted(expected)
        }
        self._closed = False

    @classmethod
    def from_http(
        cls,
        *,
        controller_configuration: GreedyKernelControllerConfiguration,
        initial_beliefs: Mapping[ReplicaIdentity, Sequence[float]],
        flow_generator_url: str,
        ownership: GreedyKernelOwnership = DEFAULT_GREEDY_KERNEL_OWNERSHIP,
        kubernetes_api_kwargs: Mapping[str, object] | None = None,
        flow_generator_kwargs: Mapping[str, object] | None = None,
        policy: GreedyPolicy | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> GreedyKernelController:
        """Construct both persistent ports and clean earlier ones on any failure."""

        resources = []
        try:
            api = GreedyKubernetesApi(
                ownership=ownership,
                **dict(kubernetes_api_kwargs or {}),
            )
            discovery = GreedyKubernetesReplicaDiscovery(
                api,
                controller_configuration.configuration,
                ownership=ownership,
            )
            resources.append(discovery)
            flow_generator = GreedyKernelFlowGeneratorHttpClient(
                flow_generator_url,
                **dict(flow_generator_kwargs or {}),
            )
            resources.append(flow_generator)
            return cls(
                controller_configuration=controller_configuration,
                discovery=discovery,
                flow_generator=flow_generator,
                initial_beliefs=initial_beliefs,
                policy=policy,
                clock=clock,
            )
        except Exception:
            for resource in reversed(resources):
                resource.close()
            raise

    @property
    def beliefs(self) -> Mapping[ReplicaIdentity, BeliefVector]:
        return dict(self._beliefs)

    @property
    def is_closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        first_error: Exception | None = None
        for resource in (self.flow_generator, self.discovery):
            close = getattr(resource, "close", None)
            if not callable(close):
                continue
            try:
                close()
            except Exception as error:  # pragma: no cover - defensive ownership path
                if first_error is None:
                    first_error = error
        if first_error is not None:
            raise first_error

    def __enter__(self) -> GreedyKernelController:
        if self._closed:
            raise RuntimeError("Greedy Kernel controller is closed")
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        del exc_type, exc_value, traceback
        self.close()

    def run_slot(
        self,
        slot_id: int,
        *,
        flow_order: Sequence[int] | None = None,
        discovery_wait: Mapping[str, object] | None = None,
        use_cache: bool = True,
    ) -> GreedyKernelControllerSlotResult:
        """Run one slot and terminate owned controller resources on failure."""

        try:
            return self._run_slot_once(
                slot_id,
                flow_order=flow_order,
                discovery_wait=discovery_wait,
                use_cache=use_cache,
            )
        except Exception:
            try:
                self.close()
            except Exception:
                # Preserve the actual request/slot failure. Cleanup is attempted
                # for every owned port and close itself is idempotent.
                pass
            raise

    def _run_slot_once(
        self,
        slot_id: int,
        *,
        flow_order: Sequence[int] | None = None,
        discovery_wait: Mapping[str, object] | None = None,
        use_cache: bool = True,
    ) -> GreedyKernelControllerSlotResult:
        if self._closed:
            raise RuntimeError("Greedy Kernel controller is closed")
        configuration = self.controller_configuration.configuration
        started_at = float(self.clock())
        snapshot = self.discovery.wait_for_complete_ready(**dict(discovery_wait or {}))
        discovered_at = float(self.clock())
        if snapshot.configuration != configuration:
            raise RuntimeError("Ready snapshot configuration does not match controller")
        public_replicas = tuple(
            PublicReplicaState(
                identity=replica.identity,
                ready=replica.ready,
                max_assigned_flows=replica.max_assigned_flows,
                belief=self._beliefs[replica.identity],
            )
            for replica in snapshot.replicas
        )
        order, flow_order_scheme, flow_order_seed = resolve_flow_order(
            num_flows=configuration.num_flows,
            root_seed=self.controller_configuration.root_seed,
            slot_id=slot_id,
            explicit_flow_order=flow_order,
        )
        policy_result = self.policy.place(
            flow_order=order,
            replica_states=public_replicas,
            use_cache=use_cache,
        )
        placements = tuple(
            GreedyPlacement(position, decision)
            for position, decision in enumerate(policy_result.decisions, start=1)
        )
        placed_at = float(self.clock())
        actions_by_flow = {
            placement.flow_id: placement.action for placement in placements
        }
        traffic = GreedyKernelSlotTrafficAdapter(snapshot, self.flow_generator)
        request = traffic.build_request(slot_id=slot_id, actions_by_flow=actions_by_flow)
        dispatched_at = float(self.clock())
        response = traffic.dispatch(request)
        telemetry_received_at = float(self.clock())
        simulation_result = traffic.convert_complete_response(
            request=request,
            response=response,
            final_loads=policy_result.final_loads,
        )
        beliefs_before, beliefs_after = apply_selected_learning(
            public_replicas,
            simulation_result.observations,
        )
        metrics = compute_slot_metrics(
            policy_result=policy_result,
            beliefs_before=beliefs_before.mapping,
            beliefs_after=beliefs_after.mapping,
            observations=simulation_result.observations,
            measured_pairs=simulation_result.measured_pairs,
        )
        finished_at = float(self.clock())
        boundaries = (
            started_at,
            discovered_at,
            placed_at,
            dispatched_at,
            telemetry_received_at,
            finished_at,
        )
        if boundaries != tuple(sorted(boundaries)):
            raise ValueError("injected controller clock must be monotonic within a slot")
        pure_timings = GreedySlotTimings(
            placement_seconds=placed_at - discovered_at,
            feedback_validation_seconds=finished_at - telemetry_received_at,
            total_seconds=(placed_at - discovered_at)
            + (finished_at - telemetry_received_at),
        )
        slot_result = GreedySlotResult(
            contract_version=GREEDY_SLOT_CONTRACT_VERSION,
            configuration=configuration,
            experiment_id=self.controller_configuration.experiment_id,
            slot_id=slot_id,
            root_seed=self.controller_configuration.root_seed,
            profile_seed=self.controller_configuration.profile_seed,
            profile_fingerprint=(
                self.controller_configuration.runtime_profile_fingerprint
            ),
            flow_order_seed_scheme=flow_order_scheme,
            flow_order_seed=flow_order_seed,
            flow_order=order,
            policy_result=policy_result,
            placements=placements,
            observations=simulation_result.observations,
            measured_pairs=simulation_result.measured_pairs,
            beliefs_before=beliefs_before,
            beliefs_after=beliefs_after,
            metrics=metrics,
            timings=pure_timings,
        )
        phase_timings = GreedyKernelPhaseTimings(
            discovery_seconds=discovered_at - started_at,
            admission_placement_seconds=placed_at - discovered_at,
            route_dispatch_seconds=dispatched_at - placed_at,
            data_plane_wait_seconds=telemetry_received_at - dispatched_at,
            feedback_validation_seconds=finished_at - telemetry_received_at,
            total_slot_seconds=finished_at - started_at,
        )
        if traffic.requests_submitted != 1:
            raise RuntimeError("controller must submit exactly one complete slot request")
        outcome = GreedyKernelControllerSlotResult(
            discovery=snapshot,
            public_replicas=public_replicas,
            slot=slot_result,
            phase_timings=phase_timings,
            controller_to_generator_requests=traffic.requests_submitted,
            selected_route_requests=len(request.routes),
        )
        # Commit only after every correlation, learning, metric, result, and
        # timing contract has succeeded. A failed slot leaves beliefs untouched.
        self._beliefs = dict(beliefs_after.mapping)
        return outcome

    def run_experiment(
        self,
        *,
        flow_orders_by_slot: Mapping[int, Sequence[int]] | None = None,
        discovery_wait: Mapping[str, object] | None = None,
        use_cache: bool = True,
    ) -> GreedyKernelControllerExperimentResult:
        """Run exactly one finite experiment and close owned ports in all cases."""

        slots = []
        stop_reason = GREEDY_EXPERIMENT_STOP_MAX_ITERATIONS
        try:
            for offset in range(self.controller_configuration.max_iterations):
                slot_id = self.controller_configuration.first_slot_id + offset
                outcome = self.run_slot(
                    slot_id,
                    flow_order=(
                        None
                        if flow_orders_by_slot is None
                        else flow_orders_by_slot.get(slot_id)
                    ),
                    discovery_wait=discovery_wait,
                    use_cache=use_cache,
                )
                slots.append(outcome)
                if outcome.slot.metrics.equilibrium:
                    stop_reason = GREEDY_EXPERIMENT_STOP_EQUILIBRIUM
                    break
            pure = GreedyExperimentResult(
                experiment_id=self.controller_configuration.experiment_id,
                max_iterations=self.controller_configuration.max_iterations,
                slots=tuple(outcome.slot for outcome in slots),
                stop_reason=stop_reason,
            )
            return GreedyKernelControllerExperimentResult(
                controller_configuration=self.controller_configuration,
                pure_experiment=pure,
                slots=tuple(slots),
            )
        finally:
            self.close()
