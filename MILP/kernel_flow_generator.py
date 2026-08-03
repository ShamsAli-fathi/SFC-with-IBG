"""MILP-specific two-hop flow generator using frozen public forwarders."""

from __future__ import annotations

import asyncio
import os
import time

from fastapi import FastAPI, HTTPException
import httpx
from pydantic import ValidationError

from IBG import latency_model as exact_latency
from IBG.datapath import KERNEL_DATAPATH_MODE
from testbed.flow_generator import FlowGeneratorConfig
from testbed.route_forwarder import RouteProcessResponse

from .kernel_contracts import (
    MILP_KERNEL_FLOW_GENERATOR_VERSION,
    MILP_TWO_HOP_ROUTE_CONTRACT_VERSION,
    MILPKernelFlowRoute,
    MILPKernelFlowTelemetry,
    MILPKernelHealthResponse,
    MILPKernelHopTelemetry,
    MILPKernelRunSlotRequest,
    MILPKernelRunSlotResponse,
)


class MILPKernelFlowExecutionError(RuntimeError):
    pass


class MILPKernelFlowGenerator:
    def __init__(
        self,
        config: FlowGeneratorConfig | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = config or FlowGeneratorConfig.from_env()
        self.transport = transport

    async def run_slot(self, request: MILPKernelRunSlotRequest) -> MILPKernelRunSlotResponse:
        if request.datapath_mode != self.config.datapath_mode:
            raise MILPKernelFlowExecutionError("requested and configured datapath modes differ")
        started = time.perf_counter()
        async with httpx.AsyncClient(
            timeout=self.config.request_timeout_seconds,
            transport=self.transport,
        ) as client:
            outcomes = await asyncio.gather(
                *(self._run_flow(client, request.slot_id, route) for route in request.routes),
                return_exceptions=True,
            )
        failures = [item for item in outcomes if isinstance(item, Exception)]
        if failures:
            raise MILPKernelFlowExecutionError(str(failures[0])) from failures[0]
        return MILPKernelRunSlotResponse(
            contract_version=MILP_TWO_HOP_ROUTE_CONTRACT_VERSION,
            datapath_mode=self.config.datapath_mode,
            slot_id=request.slot_id,
            elapsed_ms=(time.perf_counter() - started) * 1000.0,
            flows=tuple(outcomes),
        )

    async def _run_flow(
        self,
        client: httpx.AsyncClient,
        slot_id: int,
        route: MILPKernelFlowRoute,
    ) -> MILPKernelFlowTelemetry:
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
            raise MILPKernelFlowExecutionError(
                f"flow {route.flow_id} route failed: HTTP "
                f"{error.response.status_code} {error.response.text}"
            ) from error
        except (httpx.HTTPError, ValidationError, ValueError) as error:
            raise MILPKernelFlowExecutionError(
                f"flow {route.flow_id} route failed: {type(error).__name__}: {error!r}"
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
            raise MILPKernelFlowExecutionError(
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
                raise MILPKernelFlowExecutionError(
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
                raise MILPKernelFlowExecutionError(
                    f"flow {route.flow_id} returned invalid separated-jitter telemetry"
                )

        link = forwarded.links[0]
        source_observed, target_observed = forwarded.hops
        expected_link_cost = max(0.0, link.request_latency_ms - link.callee_elapsed_ms)
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
            or abs(link.link_cost_ms - expected_link_cost) > 1e-9
        ):
            raise MILPKernelFlowExecutionError(
                f"flow {route.flow_id} returned mismatched selected-pair telemetry"
            )

        ingress_overhead = max(0.0, ingress_request_ms - forwarded.elapsed_ms)
        incoming = (
            (ingress_request_ms, ingress_overhead),
            (link.request_latency_ms, link.link_cost_ms),
        )
        telemetry = tuple(
            MILPKernelHopTelemetry(
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
                processing_latency_ms=observed.processing_latency_ms,
                observation_jitter_ms=observed.observation_jitter_ms,
                signal_latency_ms=observed.signal_latency_ms,
                request_latency_ms=request_ms,
                transport_overhead_ms=overhead_ms,
                state_estimate=observed.state_estimate,
                state_likelihood=observed.state_likelihood,
            )
            for expected, observed, (request_ms, overhead_ms) in zip(
                expected_hops,
                forwarded.hops,
                incoming,
                strict=True,
            )
        )
        return MILPKernelFlowTelemetry(
            flow_id=route.flow_id,
            hops=telemetry,
            measured_pair=link,
            ingress_request_latency_ms=ingress_request_ms,
            ingress_overhead_ms=ingress_overhead,
        )


def create_app(generator: MILPKernelFlowGenerator | None = None) -> FastAPI:
    runtime = generator or MILPKernelFlowGenerator()
    application = FastAPI(title="MILP Two-Hop Flow Generator", version="1.0.0")
    application.state.generator = runtime

    @application.get("/health", response_model=MILPKernelHealthResponse)
    async def health():
        return MILPKernelHealthResponse(
            status="ok",
            datapath_mode=runtime.config.datapath_mode,
            route_contract_version=MILP_TWO_HOP_ROUTE_CONTRACT_VERSION,
            flow_generator_version=MILP_KERNEL_FLOW_GENERATOR_VERSION,
        )

    @application.post("/run-milp-slot", response_model=MILPKernelRunSlotResponse)
    async def run_slot(request: MILPKernelRunSlotRequest):
        try:
            return await runtime.run_slot(request)
        except MILPKernelFlowExecutionError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    return application


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run(
        app,
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8080")),
    )


if __name__ == "__main__":
    main()
