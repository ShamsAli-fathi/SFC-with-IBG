"""Concurrent execution of already-selected Greedy two-hop Kernel routes."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from math import isfinite
import time
from typing import Callable

import httpx
from pydantic import ValidationError

from IBG import latency_model
from IBG.datapath import KERNEL_DATAPATH_MODE, require_datapath_mode
from testbed.route_forwarder import RouteProcessResponse

from .kernel_contracts import (
    GREEDY_KERNEL_ROUTE_TIMEOUT_SECONDS,
    GreedyClientLifecycle,
)
from .kernel_route_contracts import (
    GREEDY_KERNEL_ROUTE_CONTRACT_VERSION,
    GREEDY_KERNEL_ROUTE_EXECUTION_VERSION,
    GreedyKernelFlowRoute,
    GreedyKernelFlowTelemetry,
    GreedyKernelHopTelemetry,
    GreedyKernelMeasuredPairTelemetry,
    GreedyKernelRunSlotRequest,
    GreedyKernelRunSlotResponse,
)


class GreedyKernelRouteExecutionError(RuntimeError):
    """Raised when a selected route fails or returns mismatched telemetry."""


@dataclass(frozen=True)
class GreedyKernelRouteExecutorConfig:
    request_timeout_seconds: float = GREEDY_KERNEL_ROUTE_TIMEOUT_SECONDS
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


class GreedyKernelRouteExecutor:
    """Use one lifespan pool, with a one-call fallback only for direct tests."""

    def __init__(
        self,
        config: GreedyKernelRouteExecutorConfig | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        *,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.config = config or GreedyKernelRouteExecutorConfig()
        self.transport = transport
        self.clock = clock
        self._client: httpx.AsyncClient | None = None
        self._closed = False
        self._client_instances = 0
        self._close_calls = 0
        self.ephemeral_fallback_calls = 0
        self.route_requests_submitted = 0

    @property
    def is_started(self) -> bool:
        return self._client is not None

    @property
    def is_closed(self) -> bool:
        return self._closed

    @property
    def lifecycle(self) -> GreedyClientLifecycle:
        return GreedyClientLifecycle(
            owner="flow-generator-first-forwarder",
            scope="asgi-lifespan-or-direct-one-call-fallback",
            client_instances=self._client_instances,
            close_calls=self._close_calls,
            closed=(
                self._client_instances > 0
                and self._close_calls == self._client_instances
                and self._client is None
            ),
        )

    def _new_client(self) -> httpx.AsyncClient:
        client = httpx.AsyncClient(
            timeout=self.config.request_timeout_seconds,
            transport=self.transport,
        )
        self._client_instances += 1
        return client

    async def start(self) -> None:
        if self._closed:
            raise RuntimeError("Greedy route executor is closed")
        if self._client is None:
            self._client = self._new_client()

    async def _close_client(self, client: httpx.AsyncClient) -> None:
        if client.is_closed:
            return
        await client.aclose()
        self._close_calls += 1

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        client, self._client = self._client, None
        if client is not None:
            await self._close_client(client)

    async def __aenter__(self) -> GreedyKernelRouteExecutor:
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        del exc_type, exc_value, traceback
        await self.aclose()

    async def run_slot(
        self,
        request: GreedyKernelRunSlotRequest,
    ) -> GreedyKernelRunSlotResponse:
        if self._closed:
            raise RuntimeError("Greedy route executor is closed")
        if request.datapath_mode != self.config.datapath_mode:
            raise GreedyKernelRouteExecutionError(
                "requested and configured datapath modes differ"
            )
        started = float(self.clock())
        client = self._client
        owns_client = client is None
        if client is None:
            self.ephemeral_fallback_calls += 1
            client = self._new_client()
        try:
            self.route_requests_submitted += len(request.routes)
            outcomes = await asyncio.gather(
                *(
                    self._run_flow(client, request.slot_id, route)
                    for route in request.routes
                ),
                return_exceptions=True,
            )
        finally:
            if owns_client:
                await self._close_client(client)
        failures = [outcome for outcome in outcomes if isinstance(outcome, Exception)]
        if failures:
            raise GreedyKernelRouteExecutionError(str(failures[0])) from failures[0]
        finished = float(self.clock())
        if finished < started:
            raise ValueError("injected route-executor clock must be monotonic")
        return GreedyKernelRunSlotResponse(
            contract_version=GREEDY_KERNEL_ROUTE_CONTRACT_VERSION,
            execution_version=GREEDY_KERNEL_ROUTE_EXECUTION_VERSION,
            datapath_mode=self.config.datapath_mode,
            slot_id=request.slot_id,
            elapsed_ms=(finished - started) * 1000.0,
            flows=tuple(outcomes),
        )

    async def _run_flow(
        self,
        client: httpx.AsyncClient,
        slot_id: int,
        route: GreedyKernelFlowRoute,
    ) -> GreedyKernelFlowTelemetry:
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
        started = float(self.clock())
        try:
            response = await client.post(endpoint, json=payload)
            response.raise_for_status()
            forwarded = RouteProcessResponse.model_validate(response.json())
        except httpx.HTTPStatusError as error:
            raise GreedyKernelRouteExecutionError(
                f"flow {route.flow_id} route failed: HTTP "
                f"{error.response.status_code} {error.response.text}"
            ) from error
        except (httpx.HTTPError, ValidationError, ValueError) as error:
            raise GreedyKernelRouteExecutionError(
                f"flow {route.flow_id} route failed: "
                f"{type(error).__name__}: {error!r}"
            ) from error
        finished = float(self.clock())
        if finished < started:
            raise ValueError("injected route clock must be monotonic")
        ingress_request_ms = (finished - started) * 1000.0

        expected_hops = (first, second)
        if (
            forwarded.datapath_mode != self.config.datapath_mode
            or forwarded.slot_id != slot_id
            or forwarded.flow_id != route.flow_id
            or len(forwarded.hops) != 2
            or len(forwarded.links) != 1
        ):
            raise GreedyKernelRouteExecutionError(
                f"flow {route.flow_id} returned incomplete or mismatched route telemetry"
            )

        for position, (expected, observed) in enumerate(
            zip(expected_hops, forwarded.hops, strict=True),
            start=1,
        ):
            if (
                expected.route_position != position
                or observed.stage != expected.stage
                or observed.replica_id != expected.replica_id
                or observed.slot_id != slot_id
                or observed.flow_id != route.flow_id
                or observed.assigned_load != expected.assigned_load
            ):
                raise GreedyKernelRouteExecutionError(
                    f"flow {route.flow_id} returned mismatched hop/load/position telemetry"
                )
            expected_likelihood = latency_model.learning_signal_likelihood(
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
                    abs(actual - wanted) > 1e-9
                    for actual, wanted in zip(
                        observed.state_likelihood,
                        expected_likelihood,
                        strict=True,
                    )
                )
                or observed.state_estimate
                != latency_model.estimate_state(expected_likelihood)
            ):
                raise GreedyKernelRouteExecutionError(
                    f"flow {route.flow_id} returned invalid separated-jitter telemetry"
                )

        link = forwarded.links[0]
        source_observed, target_observed = forwarded.hops
        expected_pair_ms = max(0.0, link.request_latency_ms - link.callee_elapsed_ms)
        if (
            first.next_identity != second.identity
            or link.slot_id != slot_id
            or link.flow_id != route.flow_id
            or link.source_stage != first.stage
            or link.source_replica_id != first.replica_id
            or link.source_pod_name != source_observed.pod_name
            or link.target_stage != second.stage
            or link.target_replica_id != second.replica_id
            or link.target_pod_name != target_observed.pod_name
            or link.target_endpoint.rstrip("/") != str(second.url).rstrip("/")
            or abs(link.link_cost_ms - expected_pair_ms) > 1e-9
        ):
            raise GreedyKernelRouteExecutionError(
                f"flow {route.flow_id} returned mismatched next-hop/pair telemetry"
            )

        ingress_overhead_ms = max(0.0, ingress_request_ms - forwarded.elapsed_ms)
        incoming = (
            (ingress_request_ms, ingress_overhead_ms),
            (link.request_latency_ms, link.link_cost_ms),
        )
        hops = tuple(
            GreedyKernelHopTelemetry(
                datapath_mode=self.config.datapath_mode,
                slot_id=slot_id,
                flow_id=route.flow_id,
                stage=observed.stage,
                replica_id=observed.replica_id,
                route_position=position,
                next_stage=(second.stage if position == 1 else None),
                next_replica_id=(second.replica_id if position == 1 else None),
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
            for position, (expected, observed, (request_ms, overhead_ms)) in enumerate(
                zip(expected_hops, forwarded.hops, incoming, strict=True),
                start=1,
            )
        )
        pair = GreedyKernelMeasuredPairTelemetry(
            slot_id=slot_id,
            flow_id=route.flow_id,
            source_stage=link.source_stage,
            source_replica_id=link.source_replica_id,
            source_pod_name=link.source_pod_name,
            target_stage=link.target_stage,
            target_replica_id=link.target_replica_id,
            target_pod_name=link.target_pod_name,
            target_endpoint=link.target_endpoint,
            request_latency_ms=link.request_latency_ms,
            callee_elapsed_ms=link.callee_elapsed_ms,
            measured_pair_latency_ms=link.link_cost_ms,
        )
        return GreedyKernelFlowTelemetry(
            flow_id=route.flow_id,
            bypassed_stages=route.bypassed_stages,
            hops=hops,
            measured_pair=pair,
            ingress_request_latency_ms=ingress_request_ms,
            ingress_overhead_ms=ingress_overhead_ms,
        )
