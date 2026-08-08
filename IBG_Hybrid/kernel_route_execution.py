"""Pure concurrent executor for the Hybrid Phase 1 two-hop route contract."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from math import isfinite
import time

import httpx
from pydantic import ValidationError

from IBG import latency_model as exact_latency
from IBG.datapath import KERNEL_DATAPATH_MODE, require_datapath_mode
from testbed.route_forwarder import RouteProcessResponse

from .kernel_route_contracts import (
    HYBRID_KERNEL_ROUTE_CONTRACT_VERSION,
    HYBRID_KERNEL_ROUTE_EXECUTION_VERSION,
    HybridKernelFlowRoute,
    HybridKernelFlowTelemetry,
    HybridKernelHopTelemetry,
    HybridKernelRunSlotRequest,
    HybridKernelRunSlotResponse,
)


class HybridKernelRouteExecutionError(RuntimeError):
    """Raised when selected-route execution or correlation is incomplete."""


@dataclass(frozen=True)
class HybridKernelRouteExecutorConfig:
    request_timeout_seconds: float = 10.0
    datapath_mode: str = KERNEL_DATAPATH_MODE

    def __post_init__(self) -> None:
        timeout = float(self.request_timeout_seconds)
        if (
            isinstance(self.request_timeout_seconds, bool)
            or not isfinite(timeout)
            or timeout <= 0
        ):
            raise ValueError("request_timeout_seconds must be finite and positive")
        object.__setattr__(self, "request_timeout_seconds", timeout)
        object.__setattr__(
            self,
            "datapath_mode",
            require_datapath_mode(self.datapath_mode, runtime=True),
        )


class HybridKernelRouteExecutor:
    """Send complete two-hop routes through the selected public forwarders."""

    def __init__(
        self,
        config: HybridKernelRouteExecutorConfig | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = config or HybridKernelRouteExecutorConfig()
        self.transport = transport

    async def run_slot(
        self,
        request: HybridKernelRunSlotRequest,
    ) -> HybridKernelRunSlotResponse:
        if request.datapath_mode != self.config.datapath_mode:
            raise HybridKernelRouteExecutionError(
                "requested and configured datapath modes differ"
            )
        started = time.perf_counter()
        async with httpx.AsyncClient(
            timeout=self.config.request_timeout_seconds,
            transport=self.transport,
        ) as client:
            outcomes = await asyncio.gather(
                *(
                    self._run_flow(client, request.slot_id, route)
                    for route in request.routes
                ),
                return_exceptions=True,
            )
        failures = [outcome for outcome in outcomes if isinstance(outcome, Exception)]
        if failures:
            raise HybridKernelRouteExecutionError(str(failures[0])) from failures[0]
        return HybridKernelRunSlotResponse(
            contract_version=HYBRID_KERNEL_ROUTE_CONTRACT_VERSION,
            execution_version=HYBRID_KERNEL_ROUTE_EXECUTION_VERSION,
            datapath_mode=self.config.datapath_mode,
            slot_id=request.slot_id,
            elapsed_ms=(time.perf_counter() - started) * 1000.0,
            flows=tuple(outcomes),
        )

    async def _run_flow(
        self,
        client: httpx.AsyncClient,
        slot_id: int,
        route: HybridKernelFlowRoute,
    ) -> HybridKernelFlowTelemetry:
        first, second = route.hops
        endpoint = f"{str(first.url).rstrip('/')}/process-route"
        payload = {
            "datapath_mode": self.config.datapath_mode,
            "slot_id": slot_id,
            "flow_id": route.flow_id,
            "assigned_load": first.assigned_load,
            "remaining_hops": [
                {
                    "stage": second.stage,
                    "replica_id": second.replica_id,
                    "url": str(second.url),
                    "assigned_load": second.assigned_load,
                }
            ],
        }
        started = time.perf_counter()
        try:
            response = await client.post(endpoint, json=payload)
            response.raise_for_status()
            forwarded = RouteProcessResponse.model_validate(response.json())
        except httpx.HTTPStatusError as error:
            raise HybridKernelRouteExecutionError(
                f"flow {route.flow_id} route failed: HTTP "
                f"{error.response.status_code} {error.response.text}"
            ) from error
        except (httpx.HTTPError, ValidationError, ValueError) as error:
            raise HybridKernelRouteExecutionError(
                f"flow {route.flow_id} route failed: "
                f"{type(error).__name__}: {error!r}"
            ) from error
        ingress_request_ms = (time.perf_counter() - started) * 1000.0

        expected_hops = (first, second)
        if (
            forwarded.datapath_mode != self.config.datapath_mode
            or forwarded.slot_id != slot_id
            or forwarded.flow_id != route.flow_id
            or len(forwarded.hops) != 2
            or len(forwarded.links) != 1
        ):
            raise HybridKernelRouteExecutionError(
                f"flow {route.flow_id} returned incomplete or mismatched route telemetry"
            )

        for expected, observed in zip(expected_hops, forwarded.hops, strict=True):
            if (
                observed.stage != expected.stage
                or observed.replica_id != expected.replica_id
                or observed.slot_id != slot_id
                or observed.flow_id != route.flow_id
                or observed.assigned_load != expected.assigned_load
            ):
                raise HybridKernelRouteExecutionError(
                    f"flow {route.flow_id} returned mismatched hop telemetry"
                )
            expected_likelihood = exact_latency.learning_signal_likelihood(
                observed.signal_latency_ms,
                observed.assigned_load,
            )
            if (
                abs(
                    observed.signal_latency_ms
                    - observed.processing_latency_ms
                    - observed.observation_jitter_ms
                )
                > 1e-9
                or any(
                    abs(actual - expected_value) > 1e-9
                    for actual, expected_value in zip(
                        observed.state_likelihood,
                        expected_likelihood,
                        strict=True,
                    )
                )
                or observed.state_estimate
                != exact_latency.estimate_state(observed.state_likelihood)
            ):
                raise HybridKernelRouteExecutionError(
                    f"flow {route.flow_id} returned invalid separated-jitter telemetry"
                )

        link = forwarded.links[0]
        source_observed, target_observed = forwarded.hops
        expected_pair_ms = max(0.0, link.request_latency_ms - link.callee_elapsed_ms)
        if (
            link.slot_id != slot_id
            or link.flow_id != route.flow_id
            or link.source_stage != first.stage
            or link.source_replica_id != first.replica_id
            or link.source_pod_name != source_observed.pod_name
            or link.target_stage != second.stage
            or link.target_replica_id != second.replica_id
            or link.target_pod_name != target_observed.pod_name
            or link.target_endpoint != str(second.url)
            or abs(link.link_cost_ms - expected_pair_ms) > 1e-9
        ):
            raise HybridKernelRouteExecutionError(
                f"flow {route.flow_id} returned mismatched selected-pair telemetry"
            )

        ingress_overhead_ms = max(0.0, ingress_request_ms - forwarded.elapsed_ms)
        incoming = (
            (ingress_request_ms, ingress_overhead_ms),
            (link.request_latency_ms, link.link_cost_ms),
        )
        hops = tuple(
            HybridKernelHopTelemetry(
                datapath_mode=self.config.datapath_mode,
                slot_id=slot_id,
                flow_id=route.flow_id,
                stage=observed.stage,
                replica_id=observed.replica_id,
                pod_name=observed.pod_name,
                endpoint=str(expected.url),
                concurrency=observed.concurrency,
                assigned_load=observed.assigned_load,
                modeled_processing_latency_ms=observed.modeled_processing_latency_ms,
                physical_processing_latency_ms=observed.processing_latency_ms,
                observation_jitter_ms=observed.observation_jitter_ms,
                learning_signal_ms=observed.signal_latency_ms,
                request_latency_ms=request_ms,
                transport_overhead_ms=overhead_ms,
                estimated_state=observed.state_estimate,
                likelihood=observed.state_likelihood,
            )
            for expected, observed, (request_ms, overhead_ms) in zip(
                expected_hops,
                forwarded.hops,
                incoming,
                strict=True,
            )
        )
        return HybridKernelFlowTelemetry(
            flow_id=route.flow_id,
            skipped_stage=route.skipped_stage,
            hops=hops,
            measured_pair=link,
            ingress_request_latency_ms=ingress_request_ms,
            ingress_overhead_ms=ingress_overhead_ms,
        )
