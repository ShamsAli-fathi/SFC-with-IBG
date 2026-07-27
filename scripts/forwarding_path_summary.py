"""Validate and summarize opt-in selected forwarder RPC path timings."""

import argparse
import json
import math
from pathlib import Path


SCHEMA_VERSIONS = (
    "forwarding_path_v1",
    "forwarding_path_v2",
    "forwarding_path_v3",
)
SUMMARY_SCHEMA_VERSION = "forwarding_path_summary_v4"
CLOCK = "unix-epoch-ns"
COMPONENTS = (
    "source_to_target_handler_ms",
    "target_handler_ms",
    "target_to_source_response_ms",
)
V2_PATH_COMPONENTS = (
    "source_local_response_to_request_ms",
    "source_to_target_ingress_ms",
    "target_ingress_to_handler_ms",
)
V2_HANDLER_COMPONENTS = (
    "target_handler_to_processor_request_ms",
    "target_processor_request_to_ingress_ms",
    "target_processor_ingress_to_handler_ms",
    "target_processor_pre_work_ms",
    "target_processor_work_ms",
    "target_processor_post_work_ms",
    "target_processor_handler_to_response_ms",
    "target_local_processor_round_trip_ms",
    "target_processor_response_to_downstream_request_ms",
    "target_downstream_round_trip_ms",
    "target_completion_ms",
)
V3_CLIENT_COMPONENTS = (
    "source_http_pool_wait_ms",
    "source_http_connect_ms",
    "source_http_request_headers_ms",
    "source_http_request_body_ms",
    "source_http_transport_to_target_ingress_ms",
    "source_http_response_read_start_ms",
    "target_finish_to_source_response_headers_ms",
    "source_http_response_headers_wait_ms",
    "source_http_response_body_ms",
    "source_http_response_close_ms",
    "source_http_application_resume_ms",
)
FORWARDER_RUNTIME_LAG_COMPONENTS = (
    "source_event_loop_lag_max_ms",
    "source_event_loop_lag_p95_ms",
    "target_event_loop_lag_max_ms",
    "target_event_loop_lag_p95_ms",
)
FORWARDER_RUNTIME_COUNT_COMPONENTS = (
    "source_active_route_handlers_at_start",
    "source_downstream_inflight_at_start",
    "target_active_route_handlers_at_start",
)
WORKER_COMPONENTS = COMPONENTS + V2_PATH_COMPONENTS + V3_CLIENT_COMPONENTS


def _distribution(values):
    values = sorted(float(value) for value in values)
    if not values:
        return {"count": 0, "mean": None, "p50": None, "p95": None, "max": None}
    return {
        "count": len(values),
        "mean": sum(values) / len(values),
        "p50": values[round((len(values) - 1) * 0.50)],
        "p95": values[round((len(values) - 1) * 0.95)],
        "max": values[-1],
    }


def _read_events(path):
    with path.open(encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def _require_nonnegative(timing, fields, label):
    for field in fields:
        value = timing.get(field)
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError(f"{label} has invalid {field}")


def _validate_processor_timing(timing):
    if not isinstance(timing, dict):
        raise ValueError("forwarding path processor timing must be an object")
    if timing.get("schema_version") != "processor_path_v1":
        raise ValueError("unsupported processor path timing schema")
    if timing.get("clock") != CLOCK:
        raise ValueError("unsupported processor path timing clock")
    stamps = [
        timing.get("ingress_started_unix_ns"),
        timing.get("handler_started_unix_ns"),
        timing.get("work_started_unix_ns"),
        timing.get("work_finished_unix_ns"),
        timing.get("handler_finished_unix_ns"),
    ]
    if any(not isinstance(value, int) or value < 1 for value in stamps):
        raise ValueError("processor path timing has invalid timestamps")
    if stamps != sorted(stamps):
        raise ValueError("processor path timing timestamps are not ordered")
    _require_nonnegative(
        timing,
        (
            "ingress_to_handler_ms",
            "pre_work_ms",
            "work_ms",
            "post_work_ms",
            "handler_ms",
        ),
        "processor path timing",
    )


def _validate_handler_timing(timing):
    if not isinstance(timing, dict):
        raise ValueError("target handler timing must be an object")
    if timing.get("schema_version") != "forwarding_path_v2":
        raise ValueError("unsupported target handler timing schema")
    if timing.get("clock") != CLOCK:
        raise ValueError("unsupported target handler timing clock")
    processor = timing.get("processor_timing")
    _validate_processor_timing(processor)
    required_stamps = [
        timing.get("ingress_started_unix_ns"),
        timing.get("started_unix_ns"),
        timing.get("local_processor_request_started_unix_ns"),
        processor.get("ingress_started_unix_ns"),
        processor.get("handler_started_unix_ns"),
        processor.get("work_started_unix_ns"),
        processor.get("work_finished_unix_ns"),
        processor.get("handler_finished_unix_ns"),
        timing.get("local_processor_response_received_unix_ns"),
    ]
    if any(not isinstance(value, int) or value < 1 for value in required_stamps):
        raise ValueError("target handler timing has invalid timestamps")
    if required_stamps != sorted(required_stamps):
        raise ValueError("target handler timing timestamps are not ordered")
    downstream_started = timing.get("downstream_request_started_unix_ns")
    downstream_finished = timing.get("downstream_response_received_unix_ns")
    if (downstream_started is None) != (downstream_finished is None):
        raise ValueError("target handler timing has incomplete downstream timestamps")
    finish_stamps = required_stamps + (
        [] if downstream_started is None else [downstream_started, downstream_finished]
    ) + [timing.get("finished_unix_ns")]
    if any(not isinstance(value, int) or value < 1 for value in finish_stamps):
        raise ValueError("target handler timing has invalid completion timestamps")
    if finish_stamps != sorted(finish_stamps):
        raise ValueError("target handler completion timestamps are not ordered")
    _require_nonnegative(
        timing,
        (
            "elapsed_ms",
            "ingress_to_handler_ms",
            "handler_to_processor_request_ms",
            "local_processor_round_trip_ms",
            "completion_ms",
        ),
        "target handler timing",
    )
    optional_durations = (
        timing.get("processor_response_to_downstream_request_ms"),
        timing.get("downstream_round_trip_ms"),
    )
    if downstream_started is None:
        if any(value is not None for value in optional_durations):
            raise ValueError("terminal target handler has downstream durations")
    elif any(
        not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
        for value in optional_durations
    ):
        raise ValueError("target handler timing has invalid downstream durations")


def _validate_http_client_timing(timing):
    if not isinstance(timing, dict):
        raise ValueError("source HTTP client timing must be an object")
    client_schema = timing.get("schema_version")
    if client_schema not in ("http_client_path_v1", "http_client_path_v2"):
        raise ValueError("unsupported source HTTP client timing schema")
    if timing.get("clock") != CLOCK:
        raise ValueError("unsupported source HTTP client timing clock")
    connect_started = timing.get("connect_started_unix_ns")
    connect_finished = timing.get("connect_finished_unix_ns")
    connection_reused = timing.get("connection_reused")
    if not isinstance(connection_reused, bool):
        raise ValueError("source HTTP client timing has invalid reuse flag")
    if (connect_started is None) != (connect_finished is None):
        raise ValueError("source HTTP client timing has incomplete connect timestamps")
    if connection_reused != (connect_started is None):
        raise ValueError("source HTTP client timing has inconsistent reuse flag")
    stamps = [
        timing.get("request_started_unix_ns"),
        timing.get("transport_started_unix_ns"),
        *(
            []
            if connect_started is None
            else [connect_started, connect_finished]
        ),
        timing.get("request_headers_started_unix_ns"),
        timing.get("request_headers_finished_unix_ns"),
        timing.get("request_body_started_unix_ns"),
        timing.get("request_body_finished_unix_ns"),
        timing.get("response_headers_started_unix_ns"),
        timing.get("response_headers_finished_unix_ns"),
        timing.get("response_body_started_unix_ns"),
        timing.get("response_body_finished_unix_ns"),
        timing.get("response_close_started_unix_ns"),
        timing.get("response_close_finished_unix_ns"),
        timing.get("response_received_unix_ns"),
    ]
    if any(not isinstance(value, int) or value < 1 for value in stamps):
        raise ValueError("source HTTP client timing has invalid timestamps")
    if stamps != sorted(stamps):
        raise ValueError("source HTTP client timing timestamps are not ordered")
    response_read_start_field = (
        "response_wait_ms"
        if client_schema == "http_client_path_v1"
        else "response_read_start_ms"
    )
    response_headers_wait_field = (
        "response_headers_ms"
        if client_schema == "http_client_path_v1"
        else "response_headers_wait_ms"
    )
    _require_nonnegative(
        timing,
        (
            "pool_wait_ms",
            "request_headers_ms",
            "request_body_ms",
            response_read_start_field,
            response_headers_wait_field,
            "response_body_ms",
            "response_close_ms",
            "application_resume_ms",
        ),
        "source HTTP client timing",
    )
    connect_ms = timing.get("connect_ms")
    if connect_started is None:
        if connect_ms is not None:
            raise ValueError("reused source HTTP connection has connect duration")
    elif (
        not isinstance(connect_ms, (int, float))
        or not math.isfinite(connect_ms)
        or connect_ms < 0
    ):
        raise ValueError("source HTTP client timing has invalid connect duration")


def _validate_event_loop_lag(timing, label):
    if not isinstance(timing, dict):
        raise ValueError(f"{label} must be an object")
    if timing.get("schema_version") != "event_loop_lag_v1":
        raise ValueError(f"{label} has unsupported schema")
    if timing.get("clock") != "monotonic-duration":
        raise ValueError(f"{label} has unsupported clock")
    sample_count = timing.get("sample_count")
    if isinstance(sample_count, bool) or not isinstance(sample_count, int) or sample_count < 0:
        raise ValueError(f"{label} has invalid sample count")
    _require_nonnegative(timing, ("sample_period_ms",), label)
    maximum = timing.get("max_lag_ms")
    p95 = timing.get("p95_lag_ms")
    if sample_count == 0:
        if maximum is not None or p95 is not None:
            raise ValueError(f"{label} has lag values without samples")
        return
    if any(
        not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
        for value in (maximum, p95)
    ):
        raise ValueError(f"{label} has invalid lag values")
    if p95 > maximum:
        raise ValueError(f"{label} has p95 above maximum")


def _validate_runtime_handler(timing, label):
    if not isinstance(timing, dict):
        raise ValueError(f"{label} must be an object")
    active = timing.get("active_route_handlers_at_start")
    if isinstance(active, bool) or not isinstance(active, int) or active < 1:
        raise ValueError(f"{label} has invalid active handler count")
    _validate_event_loop_lag(timing.get("event_loop_lag"), f"{label} event-loop lag")


def _validate_forwarder_runtime(timing, handler):
    if not isinstance(timing, dict):
        raise ValueError("forwarder runtime timing must be an object")
    if timing.get("schema_version") != "forwarder_runtime_v1":
        raise ValueError("unsupported forwarder runtime timing schema")
    source = timing.get("source_client")
    if not isinstance(source, dict):
        raise ValueError("forwarder runtime source client must be an object")
    _validate_runtime_handler(source, "forwarder runtime source client")
    downstream = source.get("downstream_inflight_at_start")
    if isinstance(downstream, bool) or not isinstance(downstream, int) or downstream < 1:
        raise ValueError("forwarder runtime has invalid downstream inflight count")
    socket_available = source.get("socket_metadata_available")
    socket_port = source.get("socket_local_port")
    if not isinstance(socket_available, bool):
        raise ValueError("forwarder runtime has invalid socket availability")
    if socket_available:
        if isinstance(socket_port, bool) or not isinstance(socket_port, int) or not 1 <= socket_port <= 65535:
            raise ValueError("forwarder runtime has invalid socket local port")
    elif socket_port is not None:
        raise ValueError("forwarder runtime has unexpected socket local port")
    target = timing.get("target_handler")
    _validate_runtime_handler(target, "forwarder runtime target handler")
    if handler.get("forwarder_runtime") != target:
        raise ValueError("forwarder runtime target handler is inconsistent")


def _validate_timing(timing):
    if not isinstance(timing, dict):
        raise ValueError("forwarding path timing must be an object")
    schema_version = timing.get("schema_version")
    if schema_version not in SCHEMA_VERSIONS:
        raise ValueError("unsupported forwarding path timing schema")
    if timing.get("clock") != CLOCK:
        raise ValueError("unsupported forwarding path timing clock")
    stamps = [
        timing.get("source_request_started_unix_ns"),
        timing.get("target_handler_started_unix_ns"),
        timing.get("target_handler_finished_unix_ns"),
        timing.get("source_response_received_unix_ns"),
    ]
    if any(not isinstance(value, int) or value < 1 for value in stamps):
        raise ValueError("forwarding path timing has invalid timestamps")
    if stamps != sorted(stamps):
        raise ValueError("forwarding path timestamps are not ordered")
    _require_nonnegative(timing, COMPONENTS, "forwarding path timing")
    if schema_version == "forwarding_path_v1":
        return
    target_ingress = timing.get("target_ingress_started_unix_ns")
    source_handler_started = timing.get("source_handler_started_unix_ns")
    source_local_response = timing.get(
        "source_local_processor_response_received_unix_ns"
    )
    v2_stamps = [
        source_handler_started,
        source_local_response,
        timing.get("source_request_started_unix_ns"),
        target_ingress,
        timing.get("target_handler_started_unix_ns"),
        timing.get("target_handler_finished_unix_ns"),
        timing.get("source_response_received_unix_ns"),
    ]
    if any(not isinstance(value, int) or value < 1 for value in v2_stamps):
        raise ValueError("forwarding path v2 timing has invalid timestamps")
    if v2_stamps != sorted(v2_stamps):
        raise ValueError("forwarding path v2 timestamps are not ordered")
    _require_nonnegative(timing, V2_PATH_COMPONENTS, "forwarding path v2 timing")
    handler = timing.get("target_handler_timing")
    _validate_handler_timing(handler)
    if (
        handler.get("ingress_started_unix_ns") != target_ingress
        or handler.get("started_unix_ns")
        != timing.get("target_handler_started_unix_ns")
        or handler.get("finished_unix_ns")
        != timing.get("target_handler_finished_unix_ns")
    ):
        raise ValueError("forwarding path v2 target timing is inconsistent")
    if schema_version == "forwarding_path_v2":
        return
    client = timing.get("source_http_client_timing")
    _validate_http_client_timing(client)
    if (
        client.get("request_started_unix_ns")
        != timing.get("source_request_started_unix_ns")
        or client.get("response_received_unix_ns")
        != timing.get("source_response_received_unix_ns")
        or client.get("transport_started_unix_ns") > target_ingress
        or client.get("response_headers_finished_unix_ns")
        < timing.get("target_handler_finished_unix_ns")
    ):
        raise ValueError("forwarding path v3 client timing is inconsistent")
    source_worker = timing.get("source_worker_process_id")
    target_worker = timing.get("target_worker_process_id")
    handler_worker = handler.get("worker_process_id")
    identity_values = (source_worker, target_worker, handler_worker)
    if any(value is not None for value in identity_values):
        if any(not isinstance(value, int) or value < 1 for value in identity_values):
            raise ValueError("forwarding path v3 has incomplete worker identity")
        if target_worker != handler_worker:
            raise ValueError("forwarding path v3 target worker identity is inconsistent")
    runtime = timing.get("forwarder_runtime")
    if runtime is not None:
        _validate_forwarder_runtime(runtime, handler)


def _v2_handler_components(timing):
    handler = timing["target_handler_timing"]
    processor = handler["processor_timing"]
    request_started = handler["local_processor_request_started_unix_ns"]
    response_received = handler["local_processor_response_received_unix_ns"]
    values = {
        "target_handler_to_processor_request_ms": handler[
            "handler_to_processor_request_ms"
        ],
        "target_processor_request_to_ingress_ms": (
            processor["ingress_started_unix_ns"] - request_started
        )
        / 1_000_000,
        "target_processor_ingress_to_handler_ms": processor[
            "ingress_to_handler_ms"
        ],
        "target_processor_pre_work_ms": processor["pre_work_ms"],
        "target_processor_work_ms": processor["work_ms"],
        "target_processor_post_work_ms": processor["post_work_ms"],
        "target_processor_handler_to_response_ms": (
            response_received - processor["handler_finished_unix_ns"]
        )
        / 1_000_000,
        "target_local_processor_round_trip_ms": handler[
            "local_processor_round_trip_ms"
        ],
        "target_processor_response_to_downstream_request_ms": handler.get(
            "processor_response_to_downstream_request_ms"
        ),
        "target_downstream_round_trip_ms": handler.get(
            "downstream_round_trip_ms"
        ),
        "target_completion_ms": handler["completion_ms"],
    }
    return values


def _v3_client_components(timing):
    client = timing["source_http_client_timing"]
    historical_client = client["schema_version"] == "http_client_path_v1"
    return {
        "source_http_pool_wait_ms": client["pool_wait_ms"],
        "source_http_connect_ms": client.get("connect_ms"),
        "source_http_request_headers_ms": client["request_headers_ms"],
        "source_http_request_body_ms": client["request_body_ms"],
        "source_http_transport_to_target_ingress_ms": (
            timing["target_ingress_started_unix_ns"]
            - client["transport_started_unix_ns"]
        )
        / 1_000_000,
        "source_http_response_read_start_ms": client[
            "response_wait_ms" if historical_client else "response_read_start_ms"
        ],
        "target_finish_to_source_response_headers_ms": (
            client["response_headers_finished_unix_ns"]
            - timing["target_handler_finished_unix_ns"]
        )
        / 1_000_000,
        "source_http_response_headers_wait_ms": client[
            "response_headers_ms"
            if historical_client
            else "response_headers_wait_ms"
        ],
        "source_http_response_body_ms": client["response_body_ms"],
        "source_http_response_close_ms": client["response_close_ms"],
        "source_http_application_resume_ms": client["application_resume_ms"],
    }


def _forwarder_runtime_components(timing):
    runtime = timing["forwarder_runtime"]
    source = runtime["source_client"]
    target = runtime["target_handler"]
    source_lag = source["event_loop_lag"]
    target_lag = target["event_loop_lag"]
    return {
        "source_active_route_handlers_at_start": source[
            "active_route_handlers_at_start"
        ],
        "source_downstream_inflight_at_start": source[
            "downstream_inflight_at_start"
        ],
        "target_active_route_handlers_at_start": target[
            "active_route_handlers_at_start"
        ],
        "source_event_loop_lag_max_ms": source_lag.get("max_lag_ms"),
        "source_event_loop_lag_p95_ms": source_lag.get("p95_lag_ms"),
        "target_event_loop_lag_max_ms": target_lag.get("max_lag_ms"),
        "target_event_loop_lag_p95_ms": target_lag.get("p95_lag_ms"),
    }


def _worker_group():
    return {
        "link_cost_ms": [],
        "components_ms": {component: [] for component in WORKER_COMPONENTS},
    }


def _worker_label(pod_name, process_id, direction):
    if not isinstance(pod_name, str) or not pod_name:
        raise ValueError(f"worker-identified {direction} link has invalid pod name")
    if not isinstance(process_id, int) or process_id < 1:
        raise ValueError(f"worker-identified {direction} link has invalid process ID")
    return f"{pod_name}:pid-{process_id}"


def summarize_trace(path):
    events = _read_events(path)
    started = [event for event in events if event.get("event") == "run_started"]
    iterations = [
        event for event in events if event.get("event") == "iteration_completed"
    ]
    completed = [event for event in events if event.get("event") == "run_completed"]
    if len(started) != 1 or not iterations or len(completed) != 1:
        raise ValueError(f"expected one complete trace: {path}")
    if started[0].get("forwarding_path_diagnostics") is not True:
        raise ValueError(f"trace did not enable forwarding path diagnostics: {path}")

    values = {component: [] for component in COMPONENTS}
    boundary_values = {
        component: []
        for component in (
            V2_PATH_COMPONENTS + V2_HANDLER_COMPONENTS + V3_CLIENT_COMPONENTS
        )
    }
    observed_schema_versions = set()
    pairs = {}
    worker_processes = {"source": {}, "target": {}}
    worker_identity_links = 0
    runtime_values = {
        component: []
        for component in (
            FORWARDER_RUNTIME_COUNT_COMPONENTS
            + FORWARDER_RUNTIME_LAG_COMPONENTS
        )
    }
    runtime_links = 0
    runtime_source_sampled_links = 0
    runtime_target_sampled_links = 0
    runtime_socket_metadata_links = 0
    runtime_socket_groups = {}
    for event in iterations:
        flows = ((event.get("summary") or {}).get("traffic") or {}).get("flows", [])
        for flow in flows:
            for link in flow.get("links", []):
                timing = link.get("forwarding_path")
                _validate_timing(timing)
                observed_schema_versions.add(timing["schema_version"])
                key = f"{link.get('source_stage')}->{link.get('target_stage')}"
                pair_values = pairs.setdefault(
                    key,
                    {
                        component: []
                        for component in (
                            COMPONENTS
                            + V2_PATH_COMPONENTS
                            + V2_HANDLER_COMPONENTS
                            + V3_CLIENT_COMPONENTS
                        )
                    },
                )
                for component in COMPONENTS:
                    value = float(timing[component])
                    values[component].append(value)
                    pair_values[component].append(value)
                if timing["schema_version"] in (
                    "forwarding_path_v2",
                    "forwarding_path_v3",
                ):
                    for component in V2_PATH_COMPONENTS:
                        value = float(timing[component])
                        boundary_values[component].append(value)
                        pair_values[component].append(value)
                    for component, value in _v2_handler_components(timing).items():
                        if value is not None:
                            value = float(value)
                            boundary_values[component].append(value)
                            pair_values[component].append(value)
                if timing["schema_version"] == "forwarding_path_v3":
                    for component, value in _v3_client_components(timing).items():
                        if value is not None:
                            value = float(value)
                            boundary_values[component].append(value)
                            pair_values[component].append(value)
                    source_worker = timing.get("source_worker_process_id")
                    target_worker = timing.get("target_worker_process_id")
                    if source_worker is not None:
                        link_cost = link.get("link_cost_ms")
                        if (
                            not isinstance(link_cost, (int, float))
                            or not math.isfinite(link_cost)
                            or link_cost < 0
                        ):
                            raise ValueError(
                                "worker-identified link has invalid link_cost_ms"
                            )
                        worker_identity_links += 1
                        component_values = {
                            **{
                                component: float(timing[component])
                                for component in COMPONENTS + V2_PATH_COMPONENTS
                            },
                            **{
                                component: float(value)
                                for component, value in _v3_client_components(
                                    timing
                                ).items()
                                if value is not None
                            },
                        }
                        for direction, pod_name, process_id in (
                            (
                                "source",
                                link.get("source_pod_name"),
                                source_worker,
                            ),
                            (
                                "target",
                                link.get("target_pod_name"),
                                target_worker,
                            ),
                        ):
                            label = _worker_label(pod_name, process_id, direction)
                            group = worker_processes[direction].setdefault(
                                label, _worker_group()
                            )
                            group["link_cost_ms"].append(float(link_cost))
                            for component, value in component_values.items():
                                group["components_ms"][component].append(value)
                    runtime = timing.get("forwarder_runtime")
                    if runtime is not None:
                        runtime_links += 1
                        runtime_components = _forwarder_runtime_components(timing)
                        for component in FORWARDER_RUNTIME_COUNT_COMPONENTS:
                            runtime_values[component].append(
                                float(runtime_components[component])
                            )
                        for component in FORWARDER_RUNTIME_LAG_COMPONENTS:
                            value = runtime_components[component]
                            if value is not None:
                                runtime_values[component].append(float(value))
                        source_runtime = runtime["source_client"]
                        target_runtime = runtime["target_handler"]
                        if source_runtime["event_loop_lag"]["sample_count"] > 0:
                            runtime_source_sampled_links += 1
                        if target_runtime["event_loop_lag"]["sample_count"] > 0:
                            runtime_target_sampled_links += 1
                        if source_runtime["socket_metadata_available"]:
                            runtime_socket_metadata_links += 1
                            port = source_runtime["socket_local_port"]
                            label = (
                                f"{_worker_label(link.get('source_pod_name'), source_worker, 'source')}"
                                f":port-{port}"
                            )
                            group = runtime_socket_groups.setdefault(
                                label,
                                {
                                    "link_cost_ms": [],
                                    "source_http_pool_wait_ms": [],
                                },
                            )
                            link_cost = link.get("link_cost_ms")
                            if (
                                not isinstance(link_cost, (int, float))
                                or not math.isfinite(link_cost)
                                or link_cost < 0
                            ):
                                raise ValueError(
                                    "socket-identified link has invalid link_cost_ms"
                                )
                            group["link_cost_ms"].append(float(link_cost))
                            group["source_http_pool_wait_ms"].append(
                                float(timing["source_http_client_timing"]["pool_wait_ms"])
                            )
    if not values[COMPONENTS[0]]:
        raise ValueError(f"trace has no selected pair timings: {path}")
    return {
        "trace": str(path),
        "slots": len(iterations),
        "schema_versions": sorted(observed_schema_versions),
        "components_ms": {
            component: _distribution(values[component]) for component in COMPONENTS
        },
        "boundary_components_ms": {
            component: _distribution(boundary_values[component])
            for component in (
                V2_PATH_COMPONENTS + V2_HANDLER_COMPONENTS + V3_CLIENT_COMPONENTS
            )
        },
        "stage_pairs_ms": {
            pair: {
                **{
                    component: _distribution(component_values[component])
                    for component in COMPONENTS
                },
                "boundary_components_ms": {
                    component: _distribution(component_values[component])
                    for component in (
                        V2_PATH_COMPONENTS
                        + V2_HANDLER_COMPONENTS
                        + V3_CLIENT_COMPONENTS
                    )
                },
            }
            for pair, component_values in sorted(pairs.items())
        },
        "worker_processes": {
            "identity_links": worker_identity_links,
            **{
                direction: {
                    label: {
                        "links": len(values["link_cost_ms"]),
                        "link_cost_ms": _distribution(values["link_cost_ms"]),
                        "components_ms": {
                            component: _distribution(component_values)
                            for component, component_values in values[
                                "components_ms"
                            ].items()
                        },
                    }
                    for label, values in sorted(groups.items())
                }
                for direction, groups in worker_processes.items()
            },
        },
        "forwarder_runtime": {
            "links": runtime_links,
            "source_event_loop_sampled_links": runtime_source_sampled_links,
            "target_event_loop_sampled_links": runtime_target_sampled_links,
            "socket_metadata_links": runtime_socket_metadata_links,
            "values": {
                component: _distribution(runtime_values[component])
                for component in (
                    FORWARDER_RUNTIME_COUNT_COMPONENTS
                    + FORWARDER_RUNTIME_LAG_COMPONENTS
                )
            },
            "source_sockets": {
                label: {
                    "links": len(values["link_cost_ms"]),
                    "link_cost_ms": _distribution(values["link_cost_ms"]),
                    "source_http_pool_wait_ms": _distribution(
                        values["source_http_pool_wait_ms"]
                    ),
                }
                for label, values in sorted(runtime_socket_groups.items())
            },
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Validate and summarize forwarding_path_v1/v2/v3 timing and "
            "additive forwarder-runtime diagnostics."
        )
    )
    parser.add_argument("traces", nargs="+", type=Path)
    args = parser.parse_args(argv)
    report = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "runs": [summarize_trace(path) for path in args.traces],
    }
    print(f"FORWARDING_PATH_SUMMARY={json.dumps(report, sort_keys=True)}")


if __name__ == "__main__":
    main()
