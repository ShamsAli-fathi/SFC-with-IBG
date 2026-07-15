import os
import re
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from collections.abc import Mapping

from fastapi import FastAPI, HTTPException
import httpx
from pydantic import AnyHttpUrl, BaseModel, Field, ValidationError, model_validator

from IBG.datapath import KERNEL_DATAPATH_MODE, require_datapath_mode
from testbed.cnf_service import HealthResponse, ProcessRequest, ProcessResponse


@dataclass(frozen=True)
class ForwarderConfig:
    stage: int = 1
    replica_id: int = 1
    pod_name: str = "stage-1-0"
    processor_url: str = "http://127.0.0.1:8081"
    request_timeout_seconds: float = 10.0

    def __post_init__(self):
        if self.stage < 1:
            raise ValueError("stage must be at least 1")
        if self.replica_id < 1:
            raise ValueError("replica_id must be at least 1")
        if not self.pod_name:
            raise ValueError("pod_name must not be empty")
        if not self.processor_url:
            raise ValueError("processor_url must not be empty")
        if self.request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be positive")

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None):
        values = os.environ if environ is None else environ
        stage = int(values.get("STAGE", "1"))
        pod_name = values.get("POD_NAME", f"stage-{stage}-0")
        replica_value = values.get("REPLICA_ID")
        if replica_value is None:
            ordinal = re.search(r"-(\d+)$", pod_name)
            if ordinal is None:
                raise ValueError("POD_NAME must end in a StatefulSet ordinal")
            replica_id = int(ordinal.group(1)) + 1
        else:
            replica_id = int(replica_value)
        return cls(
            stage=stage,
            replica_id=replica_id,
            pod_name=pod_name,
            processor_url=values.get(
                "PROCESSOR_URL",
                "http://127.0.0.1:8081",
            ).rstrip("/"),
            request_timeout_seconds=float(
                values.get("REQUEST_TIMEOUT_SECONDS", "10")
            ),
        )


class ForwardHop(BaseModel):
    stage: int = Field(ge=1)
    replica_id: int = Field(ge=1)
    url: AnyHttpUrl
    assigned_load: int = Field(ge=1)


class RouteProcessRequest(BaseModel):
    datapath_mode: str
    slot_id: int = Field(ge=1)
    flow_id: int = Field(ge=1)
    assigned_load: int = Field(ge=1)
    remaining_hops: list[ForwardHop] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_remaining_stage_order(self):
        self.datapath_mode = require_datapath_mode(
            self.datapath_mode,
            runtime=True,
        )
        stages = [hop.stage for hop in self.remaining_hops]
        if any(right != left + 1 for left, right in zip(stages, stages[1:])):
            raise ValueError("remaining route stages must be contiguous and ordered")
        return self


class PairwiseLinkTelemetry(BaseModel):
    slot_id: int
    flow_id: int
    source_stage: int
    source_replica_id: int
    source_pod_name: str
    target_stage: int
    target_replica_id: int
    target_pod_name: str
    target_endpoint: str
    request_latency_ms: float = Field(ge=0)
    callee_elapsed_ms: float = Field(ge=0)
    link_cost_ms: float = Field(ge=0)


class RouteProcessResponse(BaseModel):
    datapath_mode: str
    slot_id: int
    flow_id: int
    elapsed_ms: float = Field(ge=0)
    hops: list[ProcessResponse] = Field(min_length=1)
    links: list[PairwiseLinkTelemetry]


class RouteForwardingError(RuntimeError):
    pass


class ReplicaRouteForwarder:
    """Forward an already-selected route outside the processing process."""

    def __init__(
        self,
        config: ForwarderConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.config = config
        self.client = httpx.AsyncClient(
            timeout=self.config.request_timeout_seconds,
            transport=transport,
        )

    async def _request(self, method, endpoint, **kwargs):
        return await self.client.request(method, endpoint, **kwargs)

    async def close(self):
        await self.client.aclose()

    def _validate_local_identity(self, response):
        if (
            response.stage != self.config.stage
            or response.replica_id != self.config.replica_id
            or response.pod_name != self.config.pod_name
        ):
            raise RouteForwardingError(
                "local processor returned mismatched replica identity"
            )

    async def health(self):
        endpoint = f"{self.config.processor_url}/health"
        try:
            response = await self._request("GET", endpoint)
            response.raise_for_status()
            health = HealthResponse.model_validate(response.json())
        except (httpx.HTTPError, ValidationError, ValueError) as error:
            raise RouteForwardingError(
                f"local processor health failed: {error}"
            ) from error
        self._validate_local_identity(health)
        return health

    async def _process_local(self, request: RouteProcessRequest):
        endpoint = f"{self.config.processor_url}/process"
        local_request = ProcessRequest(
            slot_id=request.slot_id,
            flow_id=request.flow_id,
            assigned_load=request.assigned_load,
        )
        try:
            response = await self._request(
                "POST",
                endpoint,
                json=local_request.model_dump(mode="json"),
            )
            response.raise_for_status()
            local = ProcessResponse.model_validate(response.json())
        except (httpx.HTTPError, ValidationError, ValueError) as error:
            raise RouteForwardingError(
                f"flow {request.flow_id} local processing failed: {error}"
            ) from error
        self._validate_local_identity(local)
        if (
            local.slot_id != request.slot_id
            or local.flow_id != request.flow_id
            or local.assigned_load != request.assigned_load
        ):
            raise RouteForwardingError(
                f"flow {request.flow_id} local processor returned "
                "mismatched request telemetry"
            )
        return local

    async def process_route(self, request: RouteProcessRequest):
        if request.datapath_mode != KERNEL_DATAPATH_MODE:
            raise RouteForwardingError(
                f"unsupported forwarding mode {request.datapath_mode!r}"
            )
        if request.remaining_hops:
            expected_next_stage = self.config.stage + 1
            if request.remaining_hops[0].stage != expected_next_stage:
                raise RouteForwardingError(
                    "next forwarded stage must be "
                    f"{expected_next_stage}, got {request.remaining_hops[0].stage}"
                )

        started_at = time.perf_counter()
        local = await self._process_local(request)
        hops = [local]
        links = []

        if request.remaining_hops:
            next_hop = request.remaining_hops[0]
            endpoint = f"{str(next_hop.url).rstrip('/')}/process-route"
            downstream_request = RouteProcessRequest(
                datapath_mode=request.datapath_mode,
                slot_id=request.slot_id,
                flow_id=request.flow_id,
                assigned_load=next_hop.assigned_load,
                remaining_hops=request.remaining_hops[1:],
            )
            edge_started_at = time.perf_counter()
            try:
                response = await self._request(
                    "POST",
                    endpoint,
                    json=downstream_request.model_dump(mode="json"),
                )
                response.raise_for_status()
                downstream = RouteProcessResponse.model_validate(response.json())
            except (httpx.HTTPError, ValidationError, ValueError) as error:
                raise RouteForwardingError(
                    f"flow {request.flow_id} stage {next_hop.stage} "
                    f"forwarding failed: {error}"
                ) from error
            edge_request_latency_ms = (
                time.perf_counter() - edge_started_at
            ) * 1000

            first_downstream = downstream.hops[0]
            if (
                downstream.datapath_mode != request.datapath_mode
                or downstream.slot_id != request.slot_id
                or downstream.flow_id != request.flow_id
                or first_downstream.stage != next_hop.stage
                or first_downstream.replica_id != next_hop.replica_id
                or first_downstream.assigned_load != next_hop.assigned_load
            ):
                raise RouteForwardingError(
                    f"flow {request.flow_id} stage {next_hop.stage} "
                    "returned mismatched route telemetry"
                )

            links.append(
                PairwiseLinkTelemetry(
                    slot_id=request.slot_id,
                    flow_id=request.flow_id,
                    source_stage=local.stage,
                    source_replica_id=local.replica_id,
                    source_pod_name=local.pod_name,
                    target_stage=first_downstream.stage,
                    target_replica_id=first_downstream.replica_id,
                    target_pod_name=first_downstream.pod_name,
                    target_endpoint=str(next_hop.url),
                    request_latency_ms=edge_request_latency_ms,
                    callee_elapsed_ms=downstream.elapsed_ms,
                    link_cost_ms=max(
                        0.0,
                        edge_request_latency_ms - downstream.elapsed_ms,
                    ),
                )
            )
            hops.extend(downstream.hops)
            links.extend(downstream.links)

        return RouteProcessResponse(
            datapath_mode=request.datapath_mode,
            slot_id=request.slot_id,
            flow_id=request.flow_id,
            elapsed_ms=(time.perf_counter() - started_at) * 1000,
            hops=hops,
            links=links,
        )


def create_app(
    config: ForwarderConfig | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
):
    runtime = ReplicaRouteForwarder(
        config or ForwarderConfig.from_env(),
        transport=transport,
    )

    @asynccontextmanager
    async def lifespan(application):
        yield
        await runtime.close()

    application = FastAPI(
        title="IBG Route Forwarder",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.forwarder = runtime

    @application.get("/health", response_model=HealthResponse)
    async def health():
        try:
            return await runtime.health()
        except RouteForwardingError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @application.post("/process-route", response_model=RouteProcessResponse)
    async def process_route(request: RouteProcessRequest):
        try:
            return await runtime.process_route(request)
        except RouteForwardingError as error:
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
