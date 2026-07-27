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
SUMMARY_SCHEMA_VERSION = "forwarding_path_summary_v3"
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
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Validate and summarize forwarding_path_v1/v2/v3 trace timing."
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
