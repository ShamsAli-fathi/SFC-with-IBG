from __future__ import annotations

import asyncio
import os
import re
import time
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass
from collections.abc import Mapping
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, HTTPException, Request
import httpx
from pydantic import AnyHttpUrl, BaseModel, Field, ValidationError, model_validator

from IBG.datapath import KERNEL_DATAPATH_MODE, require_datapath_mode
from testbed.cnf_service import (
    FORWARDING_PATH_DIAGNOSTIC_HEADER,
    HealthResponse,
    ProcessRequest,
    ProcessResponse,
    ProcessorPathTiming,
)


@dataclass(frozen=True)
class ForwarderConfig:
    stage: int = 1
    replica_id: int = 1
    pod_name: str = "stage-1-0"
    processor_url: str = "http://127.0.0.1:8081"
    request_timeout_seconds: float = 10.0
    keepalive_expiry_seconds: float = 30.0

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
        if self.keepalive_expiry_seconds <= 0:
            raise ValueError("keepalive_expiry_seconds must be positive")

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
            keepalive_expiry_seconds=float(
                values.get("FORWARDER_KEEPALIVE_SECONDS", "30")
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
    forwarding_path_diagnostics: bool = False
    source_request_started_unix_ns: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_remaining_stage_order(self):
        self.datapath_mode = require_datapath_mode(
            self.datapath_mode,
            runtime=True,
        )
        stages = [hop.stage for hop in self.remaining_hops]
        if any(right != left + 1 for left, right in zip(stages, stages[1:])):
            raise ValueError("remaining route stages must be contiguous and ordered")
        if (
            not self.forwarding_path_diagnostics
            and self.source_request_started_unix_ns is not None
        ):
            raise ValueError(
                "source request timing requires forwarding path diagnostics"
            )
        return self


class ForwarderHandlerTiming(BaseModel):
    """Shared-clock timing at a public forwarder's application boundary."""

    schema_version: str
    clock: str
    # This PID is meaningful only with the accompanying Pod identity.  It is
    # opt-in diagnostic metadata so a two-worker public forwarder can be
    # correlated with an individual request without changing its timing.
    worker_process_id: int | None = Field(default=None, ge=1)
    started_unix_ns: int = Field(ge=1)
    finished_unix_ns: int = Field(ge=1)
    elapsed_ms: float = Field(ge=0)
    ingress_started_unix_ns: int | None = Field(default=None, ge=1)
    local_processor_request_started_unix_ns: int | None = Field(
        default=None,
        ge=1,
    )
    local_processor_response_received_unix_ns: int | None = Field(
        default=None,
        ge=1,
    )
    downstream_request_started_unix_ns: int | None = Field(default=None, ge=1)
    downstream_response_received_unix_ns: int | None = Field(
        default=None,
        ge=1,
    )
    ingress_to_handler_ms: float | None = Field(default=None, ge=0)
    handler_to_processor_request_ms: float | None = Field(default=None, ge=0)
    local_processor_round_trip_ms: float | None = Field(default=None, ge=0)
    processor_response_to_downstream_request_ms: float | None = Field(
        default=None,
        ge=0,
    )
    downstream_round_trip_ms: float | None = Field(default=None, ge=0)
    completion_ms: float | None = Field(default=None, ge=0)
    processor_timing: ProcessorPathTiming | None = None
    forwarder_runtime: ForwarderRuntimeHandlerTiming | None = None


class EventLoopLagTiming(BaseModel):
    """Bounded scheduler-delay samples from one public-forwarder worker."""

    schema_version: str
    clock: str
    sample_period_ms: float = Field(gt=0)
    sample_count: int = Field(ge=0)
    max_lag_ms: float | None = Field(default=None, ge=0)
    p95_lag_ms: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_sample_summary(self):
        has_samples = self.sample_count > 0
        if has_samples != (self.max_lag_ms is not None):
            raise ValueError("event-loop lag max must match sample count")
        if has_samples != (self.p95_lag_ms is not None):
            raise ValueError("event-loop lag p95 must match sample count")
        return self


class ForwarderRuntimeHandlerTiming(BaseModel):
    """Diagnostic-only public-worker state over one handler window."""

    active_route_handlers_at_start: int = Field(ge=1)
    event_loop_lag: EventLoopLagTiming


class ForwarderRuntimeClientTiming(BaseModel):
    """Diagnostic-only source client state over one selected RPC."""

    active_route_handlers_at_start: int = Field(ge=1)
    downstream_inflight_at_start: int = Field(ge=1)
    event_loop_lag: EventLoopLagTiming
    socket_metadata_available: bool
    socket_local_port: int | None = Field(default=None, ge=1, le=65535)

    @model_validator(mode="after")
    def validate_socket_metadata(self):
        if self.socket_metadata_available != (self.socket_local_port is not None):
            raise ValueError("socket metadata availability must match local port")
        return self


class ForwarderRuntimeTiming(BaseModel):
    """Additive, opt-in runtime diagnostics for a selected pair RPC."""

    schema_version: str
    source_client: ForwarderRuntimeClientTiming
    target_handler: ForwarderRuntimeHandlerTiming


class HttpClientPathTiming(BaseModel):
    """Opt-in HTTP Core milestones for one downstream forwarder request."""

    schema_version: str
    clock: str
    connection_reused: bool
    request_started_unix_ns: int = Field(ge=1)
    transport_started_unix_ns: int = Field(ge=1)
    connect_started_unix_ns: int | None = Field(default=None, ge=1)
    connect_finished_unix_ns: int | None = Field(default=None, ge=1)
    request_headers_started_unix_ns: int = Field(ge=1)
    request_headers_finished_unix_ns: int = Field(ge=1)
    request_body_started_unix_ns: int = Field(ge=1)
    request_body_finished_unix_ns: int = Field(ge=1)
    response_headers_started_unix_ns: int = Field(ge=1)
    response_headers_finished_unix_ns: int = Field(ge=1)
    response_body_started_unix_ns: int = Field(ge=1)
    response_body_finished_unix_ns: int = Field(ge=1)
    response_close_started_unix_ns: int = Field(ge=1)
    response_close_finished_unix_ns: int = Field(ge=1)
    response_received_unix_ns: int = Field(ge=1)
    pool_wait_ms: float = Field(ge=0)
    connect_ms: float | None = Field(default=None, ge=0)
    request_headers_ms: float = Field(ge=0)
    request_body_ms: float = Field(ge=0)
    response_read_start_ms: float = Field(ge=0)
    response_headers_wait_ms: float = Field(ge=0)
    response_body_ms: float = Field(ge=0)
    response_close_ms: float = Field(ge=0)
    application_resume_ms: float = Field(ge=0)


class ForwardingPathTiming(BaseModel):
    """Opt-in split of one selected forwarder-to-forwarder RPC residual."""

    schema_version: str
    clock: str
    source_request_started_unix_ns: int = Field(ge=1)
    target_handler_started_unix_ns: int = Field(ge=1)
    target_handler_finished_unix_ns: int = Field(ge=1)
    source_response_received_unix_ns: int = Field(ge=1)
    source_to_target_handler_ms: float = Field(ge=0)
    target_handler_ms: float = Field(ge=0)
    target_to_source_response_ms: float = Field(ge=0)
    source_handler_started_unix_ns: int | None = Field(default=None, ge=1)
    source_worker_process_id: int | None = Field(default=None, ge=1)
    target_worker_process_id: int | None = Field(default=None, ge=1)
    source_local_processor_response_received_unix_ns: int | None = Field(
        default=None,
        ge=1,
    )
    target_ingress_started_unix_ns: int | None = Field(default=None, ge=1)
    source_local_response_to_request_ms: float | None = Field(
        default=None,
        ge=0,
    )
    source_to_target_ingress_ms: float | None = Field(default=None, ge=0)
    target_ingress_to_handler_ms: float | None = Field(default=None, ge=0)
    target_handler_timing: ForwarderHandlerTiming | None = None
    source_http_client_timing: HttpClientPathTiming | None = None
    forwarder_runtime: ForwarderRuntimeTiming | None = None


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
    forwarding_path: ForwardingPathTiming | None = None


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
    handler_timing: ForwarderHandlerTiming | None = None


class RouteForwardingError(RuntimeError):
    pass


class ForwarderCgroupError(RuntimeError):
    pass


class HttpClientTraceRecorder:
    """Capture successful HTTP Core milestones without changing the request."""

    REQUIRED_EVENTS = (
        "http11.send_request_headers.started",
        "http11.send_request_headers.complete",
        "http11.send_request_body.started",
        "http11.send_request_body.complete",
        "http11.receive_response_headers.started",
        "http11.receive_response_headers.complete",
        "http11.receive_response_body.started",
        "http11.receive_response_body.complete",
        "http11.response_closed.started",
        "http11.response_closed.complete",
    )
    CONNECT_EVENTS = (
        "connection.connect_tcp.started",
        "connection.connect_tcp.complete",
    )

    def __init__(self, request_started_unix_ns):
        self.request_started_unix_ns = request_started_unix_ns
        self.events = {}

    async def __call__(self, name, info):
        del info
        if name in self.REQUIRED_EVENTS + self.CONNECT_EVENTS:
            self.events.setdefault(name, time.time_ns())

    def build(self, response_received_unix_ns):
        missing = [name for name in self.REQUIRED_EVENTS if name not in self.events]
        if missing:
            raise RouteForwardingError(
                "downstream HTTP client timing omitted milestones: "
                + ", ".join(missing)
            )
        connect_started = self.events.get("connection.connect_tcp.started")
        connect_finished = self.events.get("connection.connect_tcp.complete")
        if (connect_started is None) != (connect_finished is None):
            raise RouteForwardingError(
                "downstream HTTP client timing has incomplete connect milestones"
            )
        headers_started = self.events["http11.send_request_headers.started"]
        headers_finished = self.events["http11.send_request_headers.complete"]
        body_started = self.events["http11.send_request_body.started"]
        body_finished = self.events["http11.send_request_body.complete"]
        response_headers_started = self.events[
            "http11.receive_response_headers.started"
        ]
        response_headers_finished = self.events[
            "http11.receive_response_headers.complete"
        ]
        response_body_started = self.events["http11.receive_response_body.started"]
        response_body_finished = self.events[
            "http11.receive_response_body.complete"
        ]
        response_close_started = self.events["http11.response_closed.started"]
        response_close_finished = self.events["http11.response_closed.complete"]
        transport_started = connect_started or headers_started
        stamps = [
            self.request_started_unix_ns,
            transport_started,
            *(
                []
                if connect_started is None
                else [connect_started, connect_finished]
            ),
            headers_started,
            headers_finished,
            body_started,
            body_finished,
            response_headers_started,
            response_headers_finished,
            response_body_started,
            response_body_finished,
            response_close_started,
            response_close_finished,
            response_received_unix_ns,
        ]
        if stamps != sorted(stamps):
            raise RouteForwardingError(
                "downstream HTTP client timing milestones are not ordered"
            )
        return HttpClientPathTiming(
            schema_version="http_client_path_v2",
            clock="unix-epoch-ns",
            connection_reused=connect_started is None,
            request_started_unix_ns=self.request_started_unix_ns,
            transport_started_unix_ns=transport_started,
            connect_started_unix_ns=connect_started,
            connect_finished_unix_ns=connect_finished,
            request_headers_started_unix_ns=headers_started,
            request_headers_finished_unix_ns=headers_finished,
            request_body_started_unix_ns=body_started,
            request_body_finished_unix_ns=body_finished,
            response_headers_started_unix_ns=response_headers_started,
            response_headers_finished_unix_ns=response_headers_finished,
            response_body_started_unix_ns=response_body_started,
            response_body_finished_unix_ns=response_body_finished,
            response_close_started_unix_ns=response_close_started,
            response_close_finished_unix_ns=response_close_finished,
            response_received_unix_ns=response_received_unix_ns,
            pool_wait_ms=(transport_started - self.request_started_unix_ns)
            / 1_000_000,
            connect_ms=(
                None
                if connect_started is None
                else (connect_finished - connect_started) / 1_000_000
            ),
            request_headers_ms=(headers_finished - headers_started) / 1_000_000,
            request_body_ms=(body_finished - body_started) / 1_000_000,
            response_read_start_ms=(response_headers_started - body_finished)
            / 1_000_000,
            response_headers_wait_ms=(
                response_headers_finished - response_headers_started
            )
            / 1_000_000,
            response_body_ms=(response_body_finished - response_body_started)
            / 1_000_000,
            response_close_ms=(response_close_finished - response_close_started)
            / 1_000_000,
            application_resume_ms=(
                response_received_unix_ns - response_close_finished
            )
            / 1_000_000,
        )


class EventLoopLagTracker:
    """Sample one worker's event-loop scheduling lag only while diagnostics run."""

    SAMPLE_PERIOD_SECONDS = 0.005
    MAX_SAMPLES = 4_096

    def __init__(self):
        self._active_windows = 0
        self._samples = deque(maxlen=self.MAX_SAMPLES)
        self._handle = None

    def start_window(self):
        self._active_windows += 1
        if self._handle is None:
            loop = asyncio.get_running_loop()
            self._schedule(loop, loop.time() + self.SAMPLE_PERIOD_SECONDS)

    def finish_window(self):
        if self._active_windows < 1:
            raise RouteForwardingError("event-loop diagnostic window underflow")
        self._active_windows -= 1
        if self._active_windows == 0 and self._handle is not None:
            self._handle.cancel()
            self._handle = None

    def _schedule(self, loop, due_loop_time):
        self._handle = loop.call_at(due_loop_time, self._record, loop, due_loop_time)

    def _record(self, loop, due_loop_time):
        self._handle = None
        actual_loop_time = loop.time()
        actual_unix_ns = time.time_ns()
        lag_seconds = max(0.0, actual_loop_time - due_loop_time)
        due_unix_ns = actual_unix_ns - round(lag_seconds * 1_000_000_000)
        self._samples.append((due_unix_ns, actual_unix_ns, lag_seconds * 1000))
        if self._active_windows > 0:
            next_due = max(
                due_loop_time + self.SAMPLE_PERIOD_SECONDS,
                actual_loop_time + self.SAMPLE_PERIOD_SECONDS,
            )
            self._schedule(loop, next_due)

    def summarize_window(self, started_unix_ns, finished_unix_ns):
        if (
            not isinstance(started_unix_ns, int)
            or not isinstance(finished_unix_ns, int)
            or started_unix_ns < 1
            or finished_unix_ns < started_unix_ns
        ):
            raise RouteForwardingError("invalid event-loop diagnostic window")
        lags = sorted(
            lag_ms
            for due_unix_ns, observed_unix_ns, lag_ms in self._samples
            if due_unix_ns <= finished_unix_ns
            and observed_unix_ns >= started_unix_ns
        )
        if not lags:
            return EventLoopLagTiming(
                schema_version="event_loop_lag_v1",
                clock="monotonic-duration",
                sample_period_ms=self.SAMPLE_PERIOD_SECONDS * 1000,
                sample_count=0,
            )
        return EventLoopLagTiming(
            schema_version="event_loop_lag_v1",
            clock="monotonic-duration",
            sample_period_ms=self.SAMPLE_PERIOD_SECONDS * 1000,
            sample_count=len(lags),
            max_lag_ms=lags[-1],
            p95_lag_ms=lags[round((len(lags) - 1) * 0.95)],
        )


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
        self.processor_client = httpx.AsyncClient(
            timeout=self.config.request_timeout_seconds,
            transport=transport,
        )
        self.client = httpx.AsyncClient(
            timeout=self.config.request_timeout_seconds,
            transport=transport,
            limits=httpx.Limits(
                keepalive_expiry=self.config.keepalive_expiry_seconds,
            ),
        )
        self.cgroup_reader = cgroup_reader or read_forwarder_cgroup_snapshot
        self._event_loop_lag_tracker = EventLoopLagTracker()
        self._diagnostic_active_route_handlers = 0
        self._diagnostic_downstream_requests = 0

    async def _request_processor(self, method, endpoint, **kwargs):
        return await self.processor_client.request(method, endpoint, **kwargs)

    async def _request_downstream(self, method, endpoint, **kwargs):
        return await self.client.request(method, endpoint, **kwargs)

    async def close(self):
        await self.processor_client.aclose()
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

    def _downstream_socket_metadata(self, response):
        """Return an opaque local TCP port when the current HTTPX backend exposes it."""
        try:
            stream = response.extensions.get("network_stream")
            socket = stream.get_extra_info("socket")
            address = socket.getsockname()
            port = address[1]
        except (AttributeError, IndexError, OSError, TypeError, ValueError):
            return False, None
        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
            return False, None
        return True, port

    async def health(self):
        endpoint = f"{self.config.processor_url}/health"
        try:
            response = await self._request_processor("GET", endpoint)
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
            forwarding_path_diagnostics=request.forwarding_path_diagnostics,
        )
        request_started_unix_ns = (
            time.time_ns() if request.forwarding_path_diagnostics else None
        )
        try:
            response = await self._request_processor(
                "POST",
                endpoint,
                json=local_request.model_dump(mode="json"),
                headers=(
                    {FORWARDING_PATH_DIAGNOSTIC_HEADER: "1"}
                    if request.forwarding_path_diagnostics
                    else None
                ),
            )
            response.raise_for_status()
            local = ProcessResponse.model_validate(response.json())
        except (httpx.HTTPError, ValidationError, ValueError) as error:
            raise RouteForwardingError(
                f"flow {request.flow_id} local processing failed: "
                f"{type(error).__name__}: {error!r}"
            ) from error
        response_received_unix_ns = (
            time.time_ns() if request.forwarding_path_diagnostics else None
        )
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
        if request.forwarding_path_diagnostics:
            processor_timing = local.processor_timing
            if (
                request_started_unix_ns is None
                or response_received_unix_ns is None
                or processor_timing is None
                or processor_timing.schema_version != "processor_path_v1"
                or processor_timing.clock != "unix-epoch-ns"
                or not (
                    request_started_unix_ns
                    <= processor_timing.ingress_started_unix_ns
                    <= processor_timing.handler_started_unix_ns
                    <= processor_timing.work_started_unix_ns
                    <= processor_timing.work_finished_unix_ns
                    <= processor_timing.handler_finished_unix_ns
                    <= response_received_unix_ns
                )
            ):
                raise RouteForwardingError(
                    f"flow {request.flow_id} local processor returned "
                    "invalid path timing"
                )
        return local, request_started_unix_ns, response_received_unix_ns

    async def process_route(
        self,
        request: RouteProcessRequest,
        *,
        ingress_started_unix_ns: int | None = None,
    ):
        if not request.forwarding_path_diagnostics:
            return await self._process_route_impl(
                request,
                ingress_started_unix_ns=ingress_started_unix_ns,
                diagnostic_active_route_handlers=None,
            )
        self._diagnostic_active_route_handlers += 1
        diagnostic_active_route_handlers = self._diagnostic_active_route_handlers
        self._event_loop_lag_tracker.start_window()
        try:
            return await self._process_route_impl(
                request,
                ingress_started_unix_ns=ingress_started_unix_ns,
                diagnostic_active_route_handlers=diagnostic_active_route_handlers,
            )
        finally:
            self._event_loop_lag_tracker.finish_window()
            self._diagnostic_active_route_handlers -= 1

    async def _process_route_impl(
        self,
        request: RouteProcessRequest,
        *,
        ingress_started_unix_ns: int | None = None,
        diagnostic_active_route_handlers: int | None,
    ):
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
        handler_started_unix_ns = (
            time.time_ns() if request.forwarding_path_diagnostics else None
        )
        worker_process_id = (
            os.getpid() if request.forwarding_path_diagnostics else None
        )
        if request.forwarding_path_diagnostics:
            ingress_started_unix_ns = (
                ingress_started_unix_ns or handler_started_unix_ns
            )
            if (
                handler_started_unix_ns is None
                or ingress_started_unix_ns is None
                or diagnostic_active_route_handlers is None
                or diagnostic_active_route_handlers < 1
                or ingress_started_unix_ns > handler_started_unix_ns
            ):
                raise RouteForwardingError("invalid forwarder ingress timing")
        elif diagnostic_active_route_handlers is not None:
            raise RouteForwardingError(
                "forwarder runtime diagnostics require forwarding path diagnostics"
            )
        (
            local,
            local_processor_request_started_unix_ns,
            local_processor_response_received_unix_ns,
        ) = await self._process_local(request)
        hops = [local]
        links = []
        downstream_request_started_unix_ns = None
        downstream_response_received_unix_ns = None
        source_downstream_inflight_at_start = None
        source_socket_metadata_available = None
        source_socket_local_port = None

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
            source_request_started_unix_ns = (
                time.time_ns() if request.forwarding_path_diagnostics else None
            )
            http_client_trace = (
                HttpClientTraceRecorder(source_request_started_unix_ns)
                if source_request_started_unix_ns is not None
                else None
            )
            downstream_request_started_unix_ns = source_request_started_unix_ns
            if request.forwarding_path_diagnostics:
                self._diagnostic_downstream_requests += 1
                source_downstream_inflight_at_start = (
                    self._diagnostic_downstream_requests
                )
            try:
                response = await self._request_downstream(
                    "POST",
                    endpoint,
                    json=downstream_request.model_copy(
                        update={
                            "forwarding_path_diagnostics": (
                                request.forwarding_path_diagnostics
                            ),
                            "source_request_started_unix_ns": (
                                source_request_started_unix_ns
                            ),
                        }
                    ).model_dump(mode="json"),
                    headers=(
                        {FORWARDING_PATH_DIAGNOSTIC_HEADER: "1"}
                        if request.forwarding_path_diagnostics
                        else None
                    ),
                    extensions=(
                        {"trace": http_client_trace}
                        if http_client_trace is not None
                        else None
                    ),
                )
                response.raise_for_status()
                if request.forwarding_path_diagnostics:
                    (
                        source_socket_metadata_available,
                        source_socket_local_port,
                    ) = self._downstream_socket_metadata(response)
                downstream = RouteProcessResponse.model_validate(response.json())
            except (httpx.HTTPError, ValidationError, ValueError) as error:
                raise RouteForwardingError(
                    f"flow {request.flow_id} stage {next_hop.stage} "
                    f"forwarding failed: {type(error).__name__}: {error!r}"
                ) from error
            finally:
                if request.forwarding_path_diagnostics:
                    self._diagnostic_downstream_requests -= 1
            edge_request_latency_ms = (
                time.perf_counter() - edge_started_at
            ) * 1000
            source_response_received_unix_ns = (
                time.time_ns() if request.forwarding_path_diagnostics else None
            )
            downstream_response_received_unix_ns = (
                source_response_received_unix_ns
            )
            source_http_client_timing = (
                http_client_trace.build(source_response_received_unix_ns)
                if http_client_trace is not None
                and source_response_received_unix_ns is not None
                else None
            )

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

            forwarding_path = None
            if request.forwarding_path_diagnostics:
                handler_timing = downstream.handler_timing
                if (
                    source_request_started_unix_ns is None
                    or source_response_received_unix_ns is None
                    or handler_timing is None
                    or handler_timing.schema_version != "forwarding_path_v2"
                    or handler_timing.clock != "unix-epoch-ns"
                    or handler_timing.worker_process_id is None
                    or handler_timing.ingress_started_unix_ns is None
                    or handler_timing.forwarder_runtime is None
                    or local_processor_response_received_unix_ns is None
                    or source_http_client_timing is None
                    or source_downstream_inflight_at_start is None
                    or source_socket_metadata_available is None
                    or source_http_client_timing.request_started_unix_ns
                    != source_request_started_unix_ns
                    or source_http_client_timing.response_received_unix_ns
                    != source_response_received_unix_ns
                    or not (
                        source_request_started_unix_ns
                        <= handler_timing.ingress_started_unix_ns
                        <= handler_timing.started_unix_ns
                        <= handler_timing.finished_unix_ns
                        <= source_response_received_unix_ns
                    )
                ):
                    raise RouteForwardingError(
                        f"flow {request.flow_id} stage {next_hop.stage} "
                        "returned invalid forwarding path timing"
                    )
                forwarding_path = ForwardingPathTiming(
                    schema_version="forwarding_path_v3",
                    clock="unix-epoch-ns",
                    source_request_started_unix_ns=source_request_started_unix_ns,
                    target_handler_started_unix_ns=handler_timing.started_unix_ns,
                    target_handler_finished_unix_ns=handler_timing.finished_unix_ns,
                    source_response_received_unix_ns=source_response_received_unix_ns,
                    source_to_target_handler_ms=(
                        handler_timing.started_unix_ns
                        - source_request_started_unix_ns
                    )
                    / 1_000_000,
                    target_handler_ms=(
                        handler_timing.finished_unix_ns
                        - handler_timing.started_unix_ns
                    )
                    / 1_000_000,
                    target_to_source_response_ms=(
                        source_response_received_unix_ns
                        - handler_timing.finished_unix_ns
                    )
                    / 1_000_000,
                    source_handler_started_unix_ns=handler_started_unix_ns,
                    source_worker_process_id=worker_process_id,
                    target_worker_process_id=handler_timing.worker_process_id,
                    source_local_processor_response_received_unix_ns=(
                        local_processor_response_received_unix_ns
                    ),
                    target_ingress_started_unix_ns=(
                        handler_timing.ingress_started_unix_ns
                    ),
                    source_local_response_to_request_ms=(
                        source_request_started_unix_ns
                        - local_processor_response_received_unix_ns
                    )
                    / 1_000_000,
                    source_to_target_ingress_ms=(
                        handler_timing.ingress_started_unix_ns
                        - source_request_started_unix_ns
                    )
                    / 1_000_000,
                    target_ingress_to_handler_ms=(
                        handler_timing.started_unix_ns
                        - handler_timing.ingress_started_unix_ns
                    )
                    / 1_000_000,
                    target_handler_timing=handler_timing,
                    source_http_client_timing=source_http_client_timing,
                    forwarder_runtime=ForwarderRuntimeTiming(
                        schema_version="forwarder_runtime_v1",
                        source_client=ForwarderRuntimeClientTiming(
                            active_route_handlers_at_start=(
                                diagnostic_active_route_handlers
                            ),
                            downstream_inflight_at_start=(
                                source_downstream_inflight_at_start
                            ),
                            event_loop_lag=(
                                self._event_loop_lag_tracker.summarize_window(
                                    source_request_started_unix_ns,
                                    source_response_received_unix_ns,
                                )
                            ),
                            socket_metadata_available=(
                                source_socket_metadata_available
                            ),
                            socket_local_port=source_socket_local_port,
                        ),
                        target_handler=handler_timing.forwarder_runtime,
                    ),
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
                    forwarding_path=forwarding_path,
                )
            )
            hops.extend(downstream.hops)
            links.extend(downstream.links)

        elapsed_ms = (time.perf_counter() - started_at) * 1000
        handler_timing = None
        if request.forwarding_path_diagnostics:
            handler_finished_unix_ns = time.time_ns()
            processor_timing = local.processor_timing
            if (
                handler_started_unix_ns is None
                or ingress_started_unix_ns is None
                or diagnostic_active_route_handlers is None
                or local_processor_request_started_unix_ns is None
                or local_processor_response_received_unix_ns is None
                or processor_timing is None
                or not (
                    ingress_started_unix_ns
                    <= handler_started_unix_ns
                    <= local_processor_request_started_unix_ns
                    <= processor_timing.ingress_started_unix_ns
                    <= processor_timing.handler_started_unix_ns
                    <= processor_timing.work_started_unix_ns
                    <= processor_timing.work_finished_unix_ns
                    <= processor_timing.handler_finished_unix_ns
                    <= local_processor_response_received_unix_ns
                    <= (
                        downstream_request_started_unix_ns
                        or handler_finished_unix_ns
                    )
                    <= (
                        downstream_response_received_unix_ns
                        or handler_finished_unix_ns
                    )
                    <= handler_finished_unix_ns
                )
                or handler_finished_unix_ns < handler_started_unix_ns
            ):
                raise RouteForwardingError("invalid local forwarding path timing")
            completion_started_unix_ns = (
                downstream_response_received_unix_ns
                or local_processor_response_received_unix_ns
            )
            forwarder_runtime = ForwarderRuntimeHandlerTiming(
                active_route_handlers_at_start=diagnostic_active_route_handlers,
                event_loop_lag=self._event_loop_lag_tracker.summarize_window(
                    handler_started_unix_ns,
                    handler_finished_unix_ns,
                ),
            )
            handler_timing = ForwarderHandlerTiming(
                schema_version="forwarding_path_v2",
                clock="unix-epoch-ns",
                worker_process_id=worker_process_id,
                started_unix_ns=handler_started_unix_ns,
                finished_unix_ns=handler_finished_unix_ns,
                elapsed_ms=elapsed_ms,
                ingress_started_unix_ns=ingress_started_unix_ns,
                local_processor_request_started_unix_ns=(
                    local_processor_request_started_unix_ns
                ),
                local_processor_response_received_unix_ns=(
                    local_processor_response_received_unix_ns
                ),
                downstream_request_started_unix_ns=(
                    downstream_request_started_unix_ns
                ),
                downstream_response_received_unix_ns=(
                    downstream_response_received_unix_ns
                ),
                ingress_to_handler_ms=(
                    handler_started_unix_ns - ingress_started_unix_ns
                )
                / 1_000_000,
                handler_to_processor_request_ms=(
                    local_processor_request_started_unix_ns
                    - handler_started_unix_ns
                )
                / 1_000_000,
                local_processor_round_trip_ms=(
                    local_processor_response_received_unix_ns
                    - local_processor_request_started_unix_ns
                )
                / 1_000_000,
                processor_response_to_downstream_request_ms=(
                    None
                    if downstream_request_started_unix_ns is None
                    else (
                        downstream_request_started_unix_ns
                        - local_processor_response_received_unix_ns
                    )
                    / 1_000_000
                ),
                downstream_round_trip_ms=(
                    None
                    if downstream_request_started_unix_ns is None
                    or downstream_response_received_unix_ns is None
                    else (
                        downstream_response_received_unix_ns
                        - downstream_request_started_unix_ns
                    )
                    / 1_000_000
                ),
                completion_ms=(
                    handler_finished_unix_ns - completion_started_unix_ns
                )
                / 1_000_000,
                processor_timing=processor_timing,
                forwarder_runtime=forwarder_runtime,
            )
        return RouteProcessResponse(
            datapath_mode=request.datapath_mode,
            slot_id=request.slot_id,
            flow_id=request.flow_id,
            elapsed_ms=elapsed_ms,
            hops=hops,
            links=links,
            handler_timing=handler_timing,
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

    @application.middleware("http")
    async def capture_diagnostic_ingress(http_request, call_next):
        if (
            http_request.headers.get(FORWARDING_PATH_DIAGNOSTIC_HEADER)
            == "1"
        ):
            http_request.state.forwarding_path_ingress_unix_ns = time.time_ns()
        return await call_next(http_request)

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

    @application.post(
        "/process-route",
        response_model=RouteProcessResponse,
        response_model_exclude_none=True,
    )
    async def process_route(request: RouteProcessRequest, http_request: Request):
        try:
            return await runtime.process_route(
                request,
                ingress_started_unix_ns=getattr(
                    http_request.state,
                    "forwarding_path_ingress_unix_ns",
                    None,
                ),
            )
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
        timeout_keep_alive=int(
            os.environ.get("FORWARDER_KEEPALIVE_SECONDS", "30")
        ),
    )


if __name__ == "__main__":
    main()
