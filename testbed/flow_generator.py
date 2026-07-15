import asyncio
from collections import Counter
from dataclasses import dataclass
import os
import time

from fastapi import FastAPI, HTTPException
import httpx
from pydantic import AnyHttpUrl, BaseModel, Field, ValidationError, model_validator

from IBG.datapath import KERNEL_DATAPATH_MODE, require_datapath_mode
from testbed.cnf_service import (
    PairwiseLinkTelemetry,
    RouteProcessResponse,
)


class HopTarget(BaseModel):
    stage: int = Field(ge=1)
    replica_id: int = Field(ge=1)
    url: AnyHttpUrl


class FlowRoute(BaseModel):
    flow_id: int = Field(ge=1)
    hops: list[HopTarget] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_stage_order(self):
        stages = [hop.stage for hop in self.hops]
        expected = list(range(1, len(self.hops) + 1))
        if stages != expected:
            raise ValueError(
                "route hops must contain contiguous stages starting at 1 in order"
            )
        return self


class RunSlotRequest(BaseModel):
    datapath_mode: str
    slot_id: int = Field(ge=1)
    routes: list[FlowRoute] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_flows(self):
        self.datapath_mode = require_datapath_mode(
            self.datapath_mode,
            runtime=True,
        )
        flow_ids = [route.flow_id for route in self.routes]
        if len(flow_ids) != len(set(flow_ids)):
            raise ValueError("flow_id values must be unique within a slot")
        stage_sequences = {
            tuple(hop.stage for hop in route.hops) for route in self.routes
        }
        if len(stage_sequences) != 1:
            raise ValueError("all routes in a slot must contain the same stages")
        return self


class GeneratorHealthResponse(BaseModel):
    status: str
    datapath_mode: str


class HopTelemetry(BaseModel):
    datapath_mode: str
    slot_id: int
    flow_id: int
    stage: int
    replica_id: int
    pod_name: str
    endpoint: str
    concurrency: int
    assigned_load: int
    modeled_processing_latency_ms: float
    legacy_congestion: int
    processing_latency_ms: float
    request_latency_ms: float
    transport_overhead_ms: float = Field(ge=0)
    signal_latency_ms: float
    state_estimate: int
    state_likelihood: tuple[float, float, float, float]
    legacy_signal: int
    legacy_likelihood: tuple[float, float, float, float]


class FlowTelemetry(BaseModel):
    flow_id: int
    hops: list[HopTelemetry]
    links: list[PairwiseLinkTelemetry] = Field(default_factory=list)
    ingress_request_latency_ms: float = Field(default=0.0, ge=0)
    ingress_overhead_ms: float = Field(default=0.0, ge=0)


class RunSlotResponse(BaseModel):
    datapath_mode: str
    slot_id: int
    elapsed_ms: float
    flows: list[FlowTelemetry]


@dataclass(frozen=True)
class FlowGeneratorConfig:
    request_timeout_seconds: float = 10.0
    datapath_mode: str = KERNEL_DATAPATH_MODE

    def __post_init__(self):
        if self.request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be positive")
        object.__setattr__(
            self,
            "datapath_mode",
            require_datapath_mode(self.datapath_mode, runtime=True),
        )

    @classmethod
    def from_env(cls):
        return cls(
            request_timeout_seconds=float(
                os.environ.get("REQUEST_TIMEOUT_SECONDS", "10")
            ),
            datapath_mode=os.environ.get(
                "DATAPATH_MODE",
                KERNEL_DATAPATH_MODE,
            ),
        )


class FlowExecutionError(RuntimeError):
    pass


class FlowGenerator:
    def __init__(
        self,
        config: FlowGeneratorConfig | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.config = config or FlowGeneratorConfig.from_env()
        self.transport = transport

    async def run_slot(self, request: RunSlotRequest):
        if request.datapath_mode != self.config.datapath_mode:
            raise FlowExecutionError(
                "requested datapath mode "
                f"{request.datapath_mode!r} does not match flow-generator mode "
                f"{self.config.datapath_mode!r}"
            )
        started_at = time.perf_counter()
        planned_congestion = Counter(
            (hop.stage, hop.replica_id)
            for route in request.routes
            for hop in route.hops
        )
        async with httpx.AsyncClient(
            timeout=self.config.request_timeout_seconds,
            transport=self.transport,
        ) as client:
            outcomes = await asyncio.gather(
                *[
                    self._run_flow(
                        client,
                        request.slot_id,
                        route,
                        planned_congestion,
                    )
                    for route in request.routes
                ],
                return_exceptions=True,
            )

        failures = [outcome for outcome in outcomes if isinstance(outcome, Exception)]
        if failures:
            raise FlowExecutionError(str(failures[0])) from failures[0]

        return RunSlotResponse(
            datapath_mode=self.config.datapath_mode,
            slot_id=request.slot_id,
            elapsed_ms=(time.perf_counter() - started_at) * 1000,
            flows=outcomes,
        )

    async def _run_flow(self, client, slot_id, route, planned_congestion):
        first_hop = route.hops[0]
        endpoint = f"{str(first_hop.url).rstrip('/')}/process-route"
        remaining_hops = [
            {
                "stage": hop.stage,
                "replica_id": hop.replica_id,
                "url": str(hop.url),
                "assigned_load": planned_congestion[(hop.stage, hop.replica_id)],
            }
            for hop in route.hops[1:]
        ]
        started_at = time.perf_counter()
        try:
            response = await client.post(
                endpoint,
                json={
                    "datapath_mode": self.config.datapath_mode,
                    "slot_id": slot_id,
                    "flow_id": route.flow_id,
                    "assigned_load": planned_congestion[
                        (first_hop.stage, first_hop.replica_id)
                    ],
                    "remaining_hops": remaining_hops,
                },
            )
            response.raise_for_status()
            route_response = RouteProcessResponse.model_validate(response.json())
        except httpx.HTTPStatusError as error:
            raise FlowExecutionError(
                f"flow {route.flow_id} forwarded route failed: "
                f"HTTP {error.response.status_code} {error.response.text}"
            ) from error
        except (httpx.HTTPError, ValidationError, ValueError) as error:
            raise FlowExecutionError(
                f"flow {route.flow_id} forwarded route failed: {error}"
            ) from error
        request_latency_ms = (time.perf_counter() - started_at) * 1000

        if (
            route_response.datapath_mode != self.config.datapath_mode
            or route_response.slot_id != slot_id
            or route_response.flow_id != route.flow_id
        ):
            raise FlowExecutionError(
                f"flow {route.flow_id} forwarded route correlation mismatch"
            )
        if len(route_response.hops) != len(route.hops):
            raise FlowExecutionError(
                f"flow {route.flow_id} returned {len(route_response.hops)} hops; "
                f"expected {len(route.hops)}"
            )
        expected_link_count = max(0, len(route.hops) - 1)
        if len(route_response.links) != expected_link_count:
            raise FlowExecutionError(
                f"flow {route.flow_id} returned {len(route_response.links)} links; "
                f"expected {expected_link_count}"
            )
        for expected_source, expected_target, observed_link in zip(
            route.hops,
            route.hops[1:],
            route_response.links,
        ):
            expected_link_cost = max(
                0.0,
                observed_link.request_latency_ms
                - observed_link.callee_elapsed_ms,
            )
            if (
                observed_link.slot_id != slot_id
                or observed_link.flow_id != route.flow_id
                or observed_link.source_stage != expected_source.stage
                or observed_link.source_replica_id != expected_source.replica_id
                or observed_link.target_stage != expected_target.stage
                or observed_link.target_replica_id != expected_target.replica_id
                or abs(observed_link.link_cost_ms - expected_link_cost) > 1e-9
            ):
                raise FlowExecutionError(
                    f"flow {route.flow_id} returned mismatched pairwise "
                    "link telemetry"
                )

        ingress_overhead_ms = max(
            0.0,
            request_latency_ms - route_response.elapsed_ms,
        )
        incoming_measurements = {
            route.hops[0].stage: (request_latency_ms, ingress_overhead_ms)
        }
        for link in route_response.links:
            incoming_measurements[link.target_stage] = (
                link.request_latency_ms,
                link.link_cost_ms,
            )

        telemetry = []
        for expected, observed in zip(route.hops, route_response.hops):
            expected_load = planned_congestion[
                (expected.stage, expected.replica_id)
            ]
            if (
                observed.stage != expected.stage
                or observed.replica_id != expected.replica_id
                or observed.slot_id != slot_id
                or observed.flow_id != route.flow_id
                or observed.assigned_load != expected_load
            ):
                raise FlowExecutionError(
                    f"flow {route.flow_id} stage {expected.stage} returned "
                    "mismatched hop telemetry"
                )
            incoming_request_ms, incoming_overhead_ms = incoming_measurements[
                expected.stage
            ]
            telemetry.append(
                HopTelemetry(
                    datapath_mode=self.config.datapath_mode,
                    slot_id=slot_id,
                    flow_id=route.flow_id,
                    stage=observed.stage,
                    replica_id=observed.replica_id,
                    pod_name=observed.pod_name,
                    endpoint=str(expected.url),
                    concurrency=observed.concurrency,
                    assigned_load=observed.assigned_load,
                    modeled_processing_latency_ms=(
                        observed.modeled_processing_latency_ms
                    ),
                    legacy_congestion=observed.legacy_congestion,
                    processing_latency_ms=observed.processing_latency_ms,
                    request_latency_ms=incoming_request_ms,
                    transport_overhead_ms=incoming_overhead_ms,
                    signal_latency_ms=observed.signal_latency_ms,
                    state_estimate=observed.state_estimate,
                    state_likelihood=observed.state_likelihood,
                    legacy_signal=observed.legacy_signal,
                    legacy_likelihood=observed.legacy_likelihood,
                )
            )

        return FlowTelemetry(
            flow_id=route.flow_id,
            hops=telemetry,
            links=route_response.links,
            ingress_request_latency_ms=request_latency_ms,
            ingress_overhead_ms=ingress_overhead_ms,
        )


def create_app(generator: FlowGenerator | None = None):
    runtime = generator or FlowGenerator()
    application = FastAPI(title="IBG Flow Generator", version="0.1.0")
    application.state.generator = runtime

    @application.get("/health", response_model=GeneratorHealthResponse)
    async def health():
        return GeneratorHealthResponse(
            status="ok",
            datapath_mode=runtime.config.datapath_mode,
        )

    @application.post("/run-slot", response_model=RunSlotResponse)
    async def run_slot(request: RunSlotRequest):
        try:
            return await runtime.run_slot(request)
        except FlowExecutionError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    return application


app = create_app()


def main():
    import uvicorn

    uvicorn.run(
        app,
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8080")),
    )


if __name__ == "__main__":
    main()
