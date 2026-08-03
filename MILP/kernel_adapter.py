"""Ready discovery and HTTP traffic adapters for MILP Kernel execution."""

from __future__ import annotations

import re
import time
from typing import Protocol

import httpx

from IBG import latency_model as exact_latency
from IBG.datapath import KERNEL_DATAPATH_MODE
from .contracts import MILPPlacement
from .kernel_contracts import (
    MILP_KERNEL_FLOW_GENERATOR_VERSION,
    MILP_TWO_HOP_ROUTE_CONTRACT_VERSION,
    MILPKernelFlowRoute,
    MILPKernelHealthResponse,
    MILPKernelHopTarget,
    MILPKernelMeasuredPairOutcome,
    MILPKernelReplicaEndpoint,
    MILPKernelRunSlotRequest,
    MILPKernelRunSlotResponse,
    MILPKernelSelectedObservation,
    MILPKernelSlotInput,
    MILPKernelTrafficResult,
)
from .phase0_contract import MILPContractError, MILPDimensions, ReplicaKey


class MILPKernelAdapterError(RuntimeError):
    pass


class MILPKernelDiscovery(Protocol):
    def discover_all(
        self,
        dimensions: MILPDimensions,
    ) -> tuple[MILPKernelReplicaEndpoint, ...]: ...


class MILPKubernetesReplicaDiscovery:
    """Map Ready StatefulSet ordinals to immutable MILP replica endpoints."""

    def __init__(self, api: object, namespace: str) -> None:
        if not namespace:
            raise ValueError("namespace must not be empty")
        self.api = api
        self.namespace = namespace

    def discover_all(
        self,
        dimensions: MILPDimensions,
    ) -> tuple[MILPKernelReplicaEndpoint, ...]:
        # The frozen Exact adapter still uses legacy flat imports.  Load its
        # readiness predicate only when discovery actually runs so importing
        # the MILP package remains safe with an ordinary repository PYTHONPATH.
        from testbed.kubernetes_adapters import _pod_is_ready

        discovered: dict[ReplicaKey, MILPKernelReplicaEndpoint] = {}
        for stage in dimensions.stage_ids:
            maximum = dimensions.replicas_per_stage[stage - 1]
            for pod in self.api.list_stage_pods(stage):
                if not _pod_is_ready(pod):
                    continue
                metadata = pod.get("metadata", {})
                pod_name = metadata.get("name", "")
                ordinal = re.search(r"-(\d+)$", pod_name)
                if ordinal is None:
                    raise MILPKernelAdapterError(
                        f"Ready stage {stage} Pod has no StatefulSet ordinal: {pod_name}"
                    )
                replica_id = int(ordinal.group(1)) + 1
                if replica_id > maximum:
                    continue
                key = ReplicaKey(stage, replica_id)
                if key in discovered:
                    raise MILPKernelAdapterError(f"duplicate Ready replica identity: {key}")
                discovered[key] = MILPKernelReplicaEndpoint(
                    key=key,
                    pod_name=pod_name,
                    node_name=pod.get("spec", {}).get("nodeName"),
                    endpoint=(
                        f"http://{pod_name}.stage-{stage}.{self.namespace}"
                        ".svc.cluster.local.:8080"
                    ),
                )
        expected = set(dimensions.replica_keys)
        if set(discovered) != expected:
            missing = tuple(sorted(expected - set(discovered)))
            extra = tuple(sorted(set(discovered) - expected))
            raise MILPKernelAdapterError(
                f"Ready replica coverage mismatch: missing={missing}, extra={extra}"
            )
        return tuple(discovered[key] for key in dimensions.replica_keys)


def wait_for_milp_ready_replicas(
    discovery: MILPKernelDiscovery,
    dimensions: MILPDimensions,
    *,
    timeout_seconds: float = 120.0,
    poll_seconds: float = 2.0,
) -> tuple[MILPKernelReplicaEndpoint, ...]:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            return discovery.discover_all(dimensions)
        except (MILPKernelAdapterError, httpx.HTTPError) as error:
            last_error = error
            time.sleep(poll_seconds)
    raise MILPKernelAdapterError(
        f"MILP replicas did not become Ready: {last_error}"
    ) from last_error


def wait_for_milp_flow_generator(
    url: str,
    *,
    timeout_seconds: float = 120.0,
    poll_seconds: float = 2.0,
) -> None:
    health_url = f"{url.rstrip('/')}/health"
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            response = httpx.get(health_url, timeout=5.0)
            response.raise_for_status()
            health = MILPKernelHealthResponse.model_validate(response.json())
            if (
                health.status == "ok"
                and health.datapath_mode == KERNEL_DATAPATH_MODE
                and health.route_contract_version == MILP_TWO_HOP_ROUTE_CONTRACT_VERSION
                and health.flow_generator_version == MILP_KERNEL_FLOW_GENERATOR_VERSION
            ):
                return
        except (httpx.HTTPError, ValueError) as error:
            last_error = error
        time.sleep(poll_seconds)
    raise MILPKernelAdapterError(
        f"MILP flow generator did not become Ready at {health_url}: {last_error}"
    ) from last_error


class MILPKubernetesTrafficAdapter:
    """Execute one complete incumbent through the versioned two-hop service."""

    def __init__(
        self,
        flow_generator_url: str,
        *,
        timeout_seconds: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not flow_generator_url:
            raise ValueError("flow_generator_url must not be empty")
        if timeout_seconds <= 0.0:
            raise ValueError("timeout_seconds must be positive")
        self.flow_generator_url = flow_generator_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    @staticmethod
    def build_request(
        slot_input: MILPKernelSlotInput,
        placement: MILPPlacement,
    ) -> MILPKernelRunSlotRequest:
        placement.validate_for(slot_input.problem)
        endpoints = slot_input.endpoint_by_key()
        final_loads = dict(placement.final_loads)
        routes = tuple(
            MILPKernelFlowRoute(
                flow_id=flow_id,
                hops=tuple(
                    MILPKernelHopTarget(
                        stage=key.stage,
                        replica_id=key.replica,
                        url=endpoints[key].endpoint,
                        assigned_load=final_loads[key],
                    )
                    for key in action.selections
                ),
            )
            for flow_id, action in placement.actions
        )
        return MILPKernelRunSlotRequest(
            slot_id=slot_input.slot_id,
            routes=routes,
        )

    def execute(
        self,
        slot_input: MILPKernelSlotInput,
        placement: MILPPlacement,
    ) -> MILPKernelTrafficResult:
        request = self.build_request(slot_input, placement)
        try:
            with httpx.Client(
                timeout=self.timeout_seconds,
                transport=self.transport,
            ) as client:
                response = client.post(
                    f"{self.flow_generator_url}/run-milp-slot",
                    json=request.model_dump(mode="json"),
                )
                response.raise_for_status()
                telemetry = MILPKernelRunSlotResponse.model_validate(response.json())
        except httpx.HTTPStatusError as error:
            raise MILPKernelAdapterError(
                f"MILP flow generator rejected slot {slot_input.slot_id}: "
                f"HTTP {error.response.status_code} {error.response.text}"
            ) from error
        except (httpx.HTTPError, ValueError) as error:
            raise MILPKernelAdapterError(
                f"MILP flow generator failed: {type(error).__name__}: {error!r}"
            ) from error
        return self._convert(slot_input, placement, request, telemetry)

    @staticmethod
    def _convert(
        slot_input: MILPKernelSlotInput,
        placement: MILPPlacement,
        request: MILPKernelRunSlotRequest,
        telemetry: MILPKernelRunSlotResponse,
    ) -> MILPKernelTrafficResult:
        if telemetry.slot_id != slot_input.slot_id:
            raise MILPKernelAdapterError("flow-generator slot correlation mismatch")
        expected_routes = {route.flow_id: route for route in request.routes}
        actual_flows = {flow.flow_id: flow for flow in telemetry.flows}
        if len(actual_flows) != len(telemetry.flows) or set(actual_flows) != set(expected_routes):
            raise MILPKernelAdapterError("flow telemetry does not cover every selected route")
        observations: list[MILPKernelSelectedObservation] = []
        pairs: list[MILPKernelMeasuredPairOutcome] = []
        actions = placement.action_by_flow()
        for flow_id in sorted(expected_routes):
            route = expected_routes[flow_id]
            flow = actual_flows[flow_id]
            if len(flow.hops) != 2:
                raise MILPKernelAdapterError(f"flow {flow_id} did not return exactly two hops")
            for expected, observed in zip(route.hops, flow.hops, strict=True):
                if (
                    observed.slot_id != slot_input.slot_id
                    or observed.flow_id != flow_id
                    or observed.stage != expected.stage
                    or observed.replica_id != expected.replica_id
                    or observed.endpoint != str(expected.url)
                    or observed.assigned_load != expected.assigned_load
                ):
                    raise MILPKernelAdapterError(f"flow {flow_id} hop identity/load mismatch")
                expected_likelihood = exact_latency.learning_signal_likelihood(
                    observed.signal_latency_ms,
                    observed.assigned_load,
                )
                if any(
                    abs(actual - expected_value) > 1e-9
                    for actual, expected_value in zip(
                        observed.state_likelihood,
                        expected_likelihood,
                        strict=True,
                    )
                ):
                    raise MILPKernelAdapterError(f"flow {flow_id} likelihood mismatch")
                observations.append(
                    MILPKernelSelectedObservation(
                        flow_id=flow_id,
                        key=ReplicaKey(observed.stage, observed.replica_id),
                        assigned_load=observed.assigned_load,
                        physical_processing_latency_ms=observed.processing_latency_ms,
                        observation_jitter_ms=observed.observation_jitter_ms,
                        noisy_signal_ms=observed.signal_latency_ms,
                        likelihood=observed.state_likelihood,
                        estimated_state=observed.state_estimate,
                        pod_name=observed.pod_name,
                        endpoint=observed.endpoint,
                        admitted_concurrency=observed.concurrency,
                        modeled_processing_latency_ms=observed.modeled_processing_latency_ms,
                        request_latency_ms=observed.request_latency_ms,
                        transport_overhead_ms=observed.transport_overhead_ms,
                    )
                )
            link = flow.measured_pair
            source, target = actions[flow_id].directed_pair
            if (
                link.slot_id != slot_input.slot_id
                or link.flow_id != flow_id
                or (link.source_stage, link.source_replica_id)
                != (source.stage, source.replica)
                or (link.target_stage, link.target_replica_id)
                != (target.stage, target.replica)
            ):
                raise MILPKernelAdapterError(f"flow {flow_id} measured-pair mismatch")
            pairs.append(
                MILPKernelMeasuredPairOutcome(
                    flow_id=flow_id,
                    source=source,
                    target=target,
                    latency_ms=link.link_cost_ms,
                    source_pod_name=link.source_pod_name,
                    target_pod_name=link.target_pod_name,
                    target_endpoint=link.target_endpoint,
                    request_latency_ms=link.request_latency_ms,
                    callee_elapsed_ms=link.callee_elapsed_ms,
                )
            )
        return MILPKernelTrafficResult(
            observations=tuple(observations),
            measured_pairs=tuple(pairs),
            flow_generator_elapsed_ms=telemetry.elapsed_ms,
        )
