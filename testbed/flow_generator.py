import asyncio
from dataclasses import dataclass
import os
import time

from fastapi import FastAPI, HTTPException
import httpx
from pydantic import AnyHttpUrl, BaseModel, Field, ValidationError, model_validator

from testbed.cnf_service import ProcessResponse


class HopTarget(BaseModel):
    stage: int = Field(ge=1)
    replica_id: int = Field(ge=1)
    url: AnyHttpUrl


class FlowRoute(BaseModel):
    flow_id: int = Field(ge=1)
    hops: list[HopTarget] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def validate_stage_order(self):
        stages = [hop.stage for hop in self.hops]
        if stages != [1, 2, 3]:
            raise ValueError("route hops must contain stages 1, 2, and 3 in order")
        return self


class RunSlotRequest(BaseModel):
    slot_id: int = Field(ge=1)
    routes: list[FlowRoute] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_flows(self):
        flow_ids = [route.flow_id for route in self.routes]
        if len(flow_ids) != len(set(flow_ids)):
            raise ValueError("flow_id values must be unique within a slot")
        return self


class GeneratorHealthResponse(BaseModel):
    status: str


class HopTelemetry(BaseModel):
    slot_id: int
    flow_id: int
    stage: int
    replica_id: int
    pod_name: str
    endpoint: str
    concurrency: int
    processing_latency_ms: float
    request_latency_ms: float
    legacy_signal: int
    legacy_likelihood: tuple[float, float, float, float]


class FlowTelemetry(BaseModel):
    flow_id: int
    hops: list[HopTelemetry]


class RunSlotResponse(BaseModel):
    slot_id: int
    elapsed_ms: float
    flows: list[FlowTelemetry]


@dataclass(frozen=True)
class FlowGeneratorConfig:
    request_timeout_seconds: float = 10.0

    def __post_init__(self):
        if self.request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be positive")

    @classmethod
    def from_env(cls):
        return cls(
            request_timeout_seconds=float(
                os.environ.get("REQUEST_TIMEOUT_SECONDS", "10")
            )
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
        started_at = time.perf_counter()
        async with httpx.AsyncClient(
            timeout=self.config.request_timeout_seconds,
            transport=self.transport,
        ) as client:
            outcomes = await asyncio.gather(
                *[
                    self._run_flow(client, request.slot_id, route)
                    for route in request.routes
                ],
                return_exceptions=True,
            )

        failures = [outcome for outcome in outcomes if isinstance(outcome, Exception)]
        if failures:
            raise FlowExecutionError(str(failures[0])) from failures[0]

        return RunSlotResponse(
            slot_id=request.slot_id,
            elapsed_ms=(time.perf_counter() - started_at) * 1000,
            flows=outcomes,
        )

    async def _run_flow(self, client, slot_id, route):
        telemetry = []
        for hop in route.hops:
            telemetry.append(
                await self._run_hop(client, slot_id, route.flow_id, hop)
            )
        return FlowTelemetry(flow_id=route.flow_id, hops=telemetry)

    async def _run_hop(self, client, slot_id, flow_id, hop):
        endpoint = f"{str(hop.url).rstrip('/')}/process"
        started_at = time.perf_counter()
        try:
            response = await client.post(
                endpoint,
                json={"slot_id": slot_id, "flow_id": flow_id},
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

        return HopTelemetry(
            slot_id=slot_id,
            flow_id=flow_id,
            stage=replica_response.stage,
            replica_id=replica_response.replica_id,
            pod_name=replica_response.pod_name,
            endpoint=str(hop.url),
            concurrency=replica_response.concurrency,
            processing_latency_ms=replica_response.processing_latency_ms,
            request_latency_ms=(time.perf_counter() - started_at) * 1000,
            legacy_signal=replica_response.legacy_signal,
            legacy_likelihood=replica_response.legacy_likelihood,
        )


def create_app(generator: FlowGenerator | None = None):
    runtime = generator or FlowGenerator()
    application = FastAPI(title="IBG Flow Generator", version="0.1.0")
    application.state.generator = runtime

    @application.get("/health", response_model=GeneratorHealthResponse)
    async def health():
        return GeneratorHealthResponse(status="ok")

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
