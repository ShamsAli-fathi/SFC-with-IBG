import asyncio
from collections import Counter
from dataclasses import dataclass
import os
import time

from fastapi import FastAPI, HTTPException
import httpx
from pydantic import AnyHttpUrl, BaseModel, Field, ValidationError, model_validator

from IBG.datapath import KERNEL_DATAPATH_MODE, require_datapath_mode
from testbed.cnf_service import ProcessResponse


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
        telemetry = []
        for hop in route.hops:
            telemetry.append(
                await self._run_hop(
                    client,
                    slot_id,
                    route.flow_id,
                    hop,
                    planned_congestion[(hop.stage, hop.replica_id)],
                )
            )
        return FlowTelemetry(flow_id=route.flow_id, hops=telemetry)

    async def _run_hop(
        self,
        client,
        slot_id,
        flow_id,
        hop,
        assigned_load,
    ):
        endpoint = f"{str(hop.url).rstrip('/')}/process"
        started_at = time.perf_counter()
        try:
            response = await client.post(
                endpoint,
                json={
                    "slot_id": slot_id,
                    "flow_id": flow_id,
                    "assigned_load": assigned_load,
                },
            )
            response.raise_for_status()
            replica_response = ProcessResponse.model_validate(response.json())
        except (httpx.HTTPError, ValidationError, ValueError) as error:
            raise FlowExecutionError(
                f"flow {flow_id} stage {hop.stage} request failed: {error}"
            ) from error

        if (
            replica_response.stage != hop.stage
            or replica_response.replica_id != hop.replica_id
        ):
            raise FlowExecutionError(
                f"flow {flow_id} stage {hop.stage} identity mismatch: "
                f"expected replica {hop.replica_id}, got "
                f"stage {replica_response.stage} replica {replica_response.replica_id}"
            )

        if (
            replica_response.slot_id != slot_id
            or replica_response.flow_id != flow_id
        ):
            raise FlowExecutionError(
                f"flow {flow_id} stage {hop.stage} correlation mismatch: "
                f"expected slot {slot_id} flow {flow_id}, got "
                f"slot {replica_response.slot_id} flow {replica_response.flow_id}"
            )

        if replica_response.assigned_load != assigned_load:
            raise FlowExecutionError(
                f"flow {flow_id} stage {hop.stage} assigned load mismatch: "
                f"expected {assigned_load}, got "
                f"{replica_response.assigned_load}"
            )

        request_latency_ms = (time.perf_counter() - started_at) * 1000
        return HopTelemetry(
            datapath_mode=self.config.datapath_mode,
            slot_id=slot_id,
            flow_id=flow_id,
            stage=replica_response.stage,
            replica_id=replica_response.replica_id,
            pod_name=replica_response.pod_name,
            endpoint=str(hop.url),
            concurrency=replica_response.concurrency,
            assigned_load=replica_response.assigned_load,
            modeled_processing_latency_ms=(
                replica_response.modeled_processing_latency_ms
            ),
            legacy_congestion=replica_response.legacy_congestion,
            processing_latency_ms=replica_response.processing_latency_ms,
            request_latency_ms=request_latency_ms,
            transport_overhead_ms=max(
                0.0,
                request_latency_ms - replica_response.processing_latency_ms,
            ),
            signal_latency_ms=replica_response.signal_latency_ms,
            state_estimate=replica_response.state_estimate,
            state_likelihood=replica_response.state_likelihood,
            legacy_signal=replica_response.legacy_signal,
            legacy_likelihood=replica_response.legacy_likelihood,
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
