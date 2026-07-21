import os
import re
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from collections.abc import Mapping
from pathlib import Path
from typing import Callable

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


class ForwarderCgroupSnapshot(BaseModel):
    """A public-forwarder cgroup-v2 CPU counter snapshot."""

    stage: int = Field(ge=1)
    replica_id: int = Field(ge=1)
    pod_name: str = Field(min_length=1)
    cgroup_version: str
    usage_usec: int = Field(ge=0)
    nr_periods: int = Field(ge=0)
    nr_throttled: int = Field(ge=0)
    throttled_usec: int = Field(ge=0)
    quota_usec: int | None = Field(default=None, ge=1)
    period_usec: int = Field(ge=1)
    weight: int = Field(ge=1)


class RouteProcessResponse(BaseModel):
    datapath_mode: str
    slot_id: int
    flow_id: int
    elapsed_ms: float = Field(ge=0)
    hops: list[ProcessResponse] = Field(min_length=1)
    links: list[PairwiseLinkTelemetry]


class RouteForwardingError(RuntimeError):
    pass


class ForwarderCgroupError(RuntimeError):
    pass


CGROUP_CPU_STAT_PATH = Path("/sys/fs/cgroup/cpu.stat")
CGROUP_CPU_MAX_PATH = Path("/sys/fs/cgroup/cpu.max")
CGROUP_CPU_WEIGHT_PATH = Path("/sys/fs/cgroup/cpu.weight")


def _read_cgroup_key_value_file(path):
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ForwarderCgroupError(
            f"cannot read cgroup counter {path.name}: {type(error).__name__}: {error!r}"
        ) from error
    values = {}
    for line in content.splitlines():
        key, separator, value = line.partition(" ")
        if not separator or not key or not value:
            raise ForwarderCgroupError(
                f"invalid cgroup counter line in {path.name}: {line!r}"
            )
        try:
            values[key] = int(value)
        except ValueError as error:
            raise ForwarderCgroupError(
                f"invalid cgroup counter value in {path.name}: {line!r}"
            ) from error
    return values


def read_forwarder_cgroup_snapshot(config):
    """Read local CPU counters without making a route or processor request."""
    stats = _read_cgroup_key_value_file(CGROUP_CPU_STAT_PATH)
    required = (
        "usage_usec",
        "nr_periods",
        "nr_throttled",
        "throttled_usec",
    )
    missing = [key for key in required if key not in stats]
    if missing:
        raise ForwarderCgroupError(
            "cgroup-v2 cpu.stat is missing required counters: "
            + ", ".join(missing)
        )
    try:
        quota_text, period_text = CGROUP_CPU_MAX_PATH.read_text(
            encoding="utf-8"
        ).split()
        weight = int(CGROUP_CPU_WEIGHT_PATH.read_text(encoding="utf-8").strip())
        quota_usec = None if quota_text == "max" else int(quota_text)
        period_usec = int(period_text)
    except (OSError, ValueError) as error:
        raise ForwarderCgroupError(
            "cannot read cgroup-v2 CPU limit metadata: "
            f"{type(error).__name__}: {error!r}"
        ) from error
    return ForwarderCgroupSnapshot(
        stage=config.stage,
        replica_id=config.replica_id,
        pod_name=config.pod_name,
        cgroup_version="v2",
        usage_usec=stats["usage_usec"],
        nr_periods=stats["nr_periods"],
        nr_throttled=stats["nr_throttled"],
        throttled_usec=stats["throttled_usec"],
        quota_usec=quota_usec,
        period_usec=period_usec,
        weight=weight,
    )


class ReplicaRouteForwarder:
    """Forward an already-selected route outside the processing process."""

    def __init__(
        self,
        config: ForwarderConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        cgroup_reader: Callable[[ForwarderConfig], ForwarderCgroupSnapshot]
        | None = None,
    ):
        self.config = config
        self.client = httpx.AsyncClient(
            timeout=self.config.request_timeout_seconds,
            transport=transport,
        )
        self.cgroup_reader = cgroup_reader or read_forwarder_cgroup_snapshot

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
                "local processor health failed: "
                f"{type(error).__name__}: {error!r}"
            ) from error
        self._validate_local_identity(health)
        return health

    def cgroup_snapshot(self):
        snapshot = self.cgroup_reader(self.config)
        self._validate_local_identity(snapshot)
        return snapshot

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
                f"flow {request.flow_id} local processing failed: "
                f"{type(error).__name__}: {error!r}"
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
                    f"forwarding failed: {type(error).__name__}: {error!r}"
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
    cgroup_reader: Callable[[ForwarderConfig], ForwarderCgroupSnapshot]
    | None = None,
):
    runtime = ReplicaRouteForwarder(
        config or ForwarderConfig.from_env(),
        transport=transport,
        cgroup_reader=cgroup_reader,
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

    @application.get("/runtime-cgroup", response_model=ForwarderCgroupSnapshot)
    async def runtime_cgroup():
        try:
            return runtime.cgroup_snapshot()
        except ForwarderCgroupError as error:
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
