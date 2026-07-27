import json

import pytest

from scripts.forwarding_path_summary import summarize_trace


def _timing():
    return {
        "schema_version": "forwarding_path_v1",
        "clock": "unix-epoch-ns",
        "source_request_started_unix_ns": 100,
        "target_handler_started_unix_ns": 300,
        "target_handler_finished_unix_ns": 700,
        "source_response_received_unix_ns": 900,
        "source_to_target_handler_ms": 0.0002,
        "target_handler_ms": 0.0004,
        "target_to_source_response_ms": 0.0002,
    }


def _timing_v2():
    processor = {
        "schema_version": "processor_path_v1",
        "clock": "unix-epoch-ns",
        "ingress_started_unix_ns": 400,
        "handler_started_unix_ns": 450,
        "work_started_unix_ns": 500,
        "work_finished_unix_ns": 600,
        "handler_finished_unix_ns": 650,
        "ingress_to_handler_ms": 0.00005,
        "pre_work_ms": 0.00005,
        "work_ms": 0.0001,
        "post_work_ms": 0.00005,
        "handler_ms": 0.0002,
    }
    handler = {
        "schema_version": "forwarding_path_v2",
        "clock": "unix-epoch-ns",
        "ingress_started_unix_ns": 200,
        "started_unix_ns": 300,
        "local_processor_request_started_unix_ns": 320,
        "local_processor_response_received_unix_ns": 700,
        "downstream_request_started_unix_ns": 720,
        "downstream_response_received_unix_ns": 900,
        "finished_unix_ns": 950,
        "elapsed_ms": 0.00065,
        "ingress_to_handler_ms": 0.0001,
        "handler_to_processor_request_ms": 0.00002,
        "local_processor_round_trip_ms": 0.00038,
        "processor_response_to_downstream_request_ms": 0.00002,
        "downstream_round_trip_ms": 0.00018,
        "completion_ms": 0.00005,
        "processor_timing": processor,
    }
    return {
        "schema_version": "forwarding_path_v2",
        "clock": "unix-epoch-ns",
        "source_handler_started_unix_ns": 50,
        "source_local_processor_response_received_unix_ns": 90,
        "source_request_started_unix_ns": 100,
        "target_ingress_started_unix_ns": 200,
        "target_handler_started_unix_ns": 300,
        "target_handler_finished_unix_ns": 950,
        "source_response_received_unix_ns": 1000,
        "source_local_response_to_request_ms": 0.00001,
        "source_to_target_ingress_ms": 0.0001,
        "target_ingress_to_handler_ms": 0.0001,
        "source_to_target_handler_ms": 0.0002,
        "target_handler_ms": 0.00065,
        "target_to_source_response_ms": 0.00005,
        "target_handler_timing": handler,
    }


def _timing_v3():
    timing = _timing_v2()
    timing["schema_version"] = "forwarding_path_v3"
    timing["source_http_client_timing"] = {
        "schema_version": "http_client_path_v2",
        "clock": "unix-epoch-ns",
        "connection_reused": True,
        "request_started_unix_ns": 100,
        "transport_started_unix_ns": 110,
        "connect_started_unix_ns": None,
        "connect_finished_unix_ns": None,
        "request_headers_started_unix_ns": 110,
        "request_headers_finished_unix_ns": 120,
        "request_body_started_unix_ns": 120,
        "request_body_finished_unix_ns": 130,
        "response_headers_started_unix_ns": 960,
        "response_headers_finished_unix_ns": 970,
        "response_body_started_unix_ns": 970,
        "response_body_finished_unix_ns": 980,
        "response_close_started_unix_ns": 980,
        "response_close_finished_unix_ns": 990,
        "response_received_unix_ns": 1000,
        "pool_wait_ms": 0.00001,
        "connect_ms": None,
        "request_headers_ms": 0.00001,
        "request_body_ms": 0.00001,
        "response_read_start_ms": 0.00083,
        "response_headers_wait_ms": 0.00001,
        "response_body_ms": 0.00001,
        "response_close_ms": 0.00001,
        "application_resume_ms": 0.00001,
    }
    return timing


def _timing_v3_with_worker_identity():
    timing = _timing_v3()
    timing["source_worker_process_id"] = 101
    timing["target_worker_process_id"] = 202
    timing["target_handler_timing"]["worker_process_id"] = 202
    return timing


def _timing_v3_with_runtime():
    timing = _timing_v3_with_worker_identity()
    target_handler = {
        "active_route_handlers_at_start": 2,
        "event_loop_lag": {
            "schema_version": "event_loop_lag_v1",
            "clock": "monotonic-duration",
            "sample_period_ms": 5.0,
            "sample_count": 3,
            "max_lag_ms": 1.5,
            "p95_lag_ms": 1.25,
        },
    }
    timing["target_handler_timing"]["forwarder_runtime"] = target_handler
    timing["forwarder_runtime"] = {
        "schema_version": "forwarder_runtime_v1",
        "source_client": {
            "active_route_handlers_at_start": 3,
            "downstream_inflight_at_start": 2,
            "event_loop_lag": {
                "schema_version": "event_loop_lag_v1",
                "clock": "monotonic-duration",
                "sample_period_ms": 5.0,
                "sample_count": 2,
                "max_lag_ms": 2.0,
                "p95_lag_ms": 1.75,
            },
            "socket_metadata_available": True,
            "socket_local_port": 43210,
        },
        "target_handler": target_handler,
    }
    return timing


def _trace(path, timing=None):
    events = [
        {"event": "run_started", "forwarding_path_diagnostics": True},
        {
            "event": "iteration_completed",
            "summary": {
                "traffic": {
                    "flows": [
                        {
                            "links": [
                                {
                                    "source_stage": 1,
                                    "target_stage": 2,
                                    "forwarding_path": timing or _timing(),
                                }
                            ]
                        }
                    ]
                }
            },
        },
        {"event": "run_completed"},
    ]
    path.write_text(
        "\n".join(json.dumps(event) for event in events) + "\n",
        encoding="utf-8",
    )


def test_forwarding_path_summary_reports_each_component(tmp_path):
    path = tmp_path / "trace.jsonl"
    _trace(path)

    report = summarize_trace(path)

    assert report["slots"] == 1
    assert report["components_ms"]["source_to_target_handler_ms"]["mean"] == pytest.approx(0.0002)
    assert report["stage_pairs_ms"]["1->2"]["target_handler_ms"]["count"] == 1


def test_forwarding_path_summary_rejects_unordered_timestamps(tmp_path):
    path = tmp_path / "trace.jsonl"
    timing = _timing()
    timing["source_response_received_unix_ns"] = 600
    _trace(path, timing)

    with pytest.raises(ValueError, match="not ordered"):
        summarize_trace(path)


def test_forwarding_path_summary_reports_v2_boundary_components(tmp_path):
    path = tmp_path / "trace.jsonl"
    _trace(path, _timing_v2())

    report = summarize_trace(path)

    assert report["schema_versions"] == ["forwarding_path_v2"]
    boundaries = report["boundary_components_ms"]
    assert boundaries["source_to_target_ingress_ms"]["mean"] == pytest.approx(
        0.0001
    )
    assert boundaries["target_processor_work_ms"]["mean"] == pytest.approx(
        0.0001
    )
    stage_boundaries = report["stage_pairs_ms"]["1->2"][
        "boundary_components_ms"
    ]
    assert stage_boundaries["target_downstream_round_trip_ms"]["count"] == 1


def test_forwarding_path_summary_reports_v3_http_client_components(tmp_path):
    path = tmp_path / "trace.jsonl"
    _trace(path, _timing_v3())

    report = summarize_trace(path)

    assert report["schema_versions"] == ["forwarding_path_v3"]
    boundaries = report["boundary_components_ms"]
    assert boundaries["source_http_pool_wait_ms"]["mean"] == pytest.approx(
        0.00001
    )
    assert boundaries["source_http_connect_ms"]["count"] == 0
    assert boundaries["source_http_transport_to_target_ingress_ms"][
        "mean"
    ] == pytest.approx(0.00009)
    assert boundaries["target_finish_to_source_response_headers_ms"][
        "mean"
    ] == pytest.approx(0.00002)


def test_forwarding_path_summary_groups_v3_links_by_forwarder_worker(tmp_path):
    path = tmp_path / "trace.jsonl"
    timing = _timing_v3_with_worker_identity()
    events = [
        {"event": "run_started", "forwarding_path_diagnostics": True},
        {
            "event": "iteration_completed",
            "summary": {
                "traffic": {
                    "flows": [
                        {
                            "links": [
                                {
                                    "source_stage": 1,
                                    "target_stage": 2,
                                    "source_pod_name": "stage-1-0",
                                    "target_pod_name": "stage-2-0",
                                    "link_cost_ms": 7.5,
                                    "forwarding_path": timing,
                                }
                            ]
                        }
                    ]
                }
            },
        },
        {"event": "run_completed"},
    ]
    path.write_text(
        "\n".join(json.dumps(event) for event in events) + "\n",
        encoding="utf-8",
    )

    report = summarize_trace(path)

    workers = report["worker_processes"]
    assert workers["identity_links"] == 1
    assert workers["source"]["stage-1-0:pid-101"]["links"] == 1
    assert workers["target"]["stage-2-0:pid-202"]["link_cost_ms"][
        "mean"
    ] == pytest.approx(7.5)


def test_forwarding_path_summary_reports_additive_forwarder_runtime(tmp_path):
    path = tmp_path / "trace.jsonl"
    timing = _timing_v3_with_runtime()
    events = [
        {"event": "run_started", "forwarding_path_diagnostics": True},
        {
            "event": "iteration_completed",
            "summary": {
                "traffic": {
                    "flows": [
                        {
                            "links": [
                                {
                                    "source_stage": 1,
                                    "target_stage": 2,
                                    "source_pod_name": "stage-1-0",
                                    "target_pod_name": "stage-2-0",
                                    "link_cost_ms": 7.5,
                                    "forwarding_path": timing,
                                }
                            ]
                        }
                    ]
                }
            },
        },
        {"event": "run_completed"},
    ]
    path.write_text(
        "\n".join(json.dumps(event) for event in events) + "\n",
        encoding="utf-8",
    )

    report = summarize_trace(path)

    runtime = report["forwarder_runtime"]
    assert runtime["links"] == 1
    assert runtime["source_event_loop_sampled_links"] == 1
    assert runtime["target_event_loop_sampled_links"] == 1
    assert runtime["socket_metadata_links"] == 1
    assert runtime["values"]["source_event_loop_lag_max_ms"]["mean"] == pytest.approx(
        2.0
    )
    assert runtime["source_sockets"]["stage-1-0:pid-101:port-43210"]["link_cost_ms"][
        "mean"
    ] == pytest.approx(7.5)


def test_forwarding_path_summary_scopes_socket_groups_to_source_worker(tmp_path):
    path = tmp_path / "trace.jsonl"
    first = _timing_v3_with_runtime()
    second = _timing_v3_with_runtime()
    second["source_worker_process_id"] = 102
    events = [
        {"event": "run_started", "forwarding_path_diagnostics": True},
        {
            "event": "iteration_completed",
            "summary": {
                "traffic": {
                    "flows": [
                        {
                            "links": [
                                {
                                    "source_stage": 1,
                                    "target_stage": 2,
                                    "source_pod_name": "stage-1-0",
                                    "target_pod_name": "stage-2-0",
                                    "link_cost_ms": 7.5,
                                    "forwarding_path": first,
                                },
                                {
                                    "source_stage": 1,
                                    "target_stage": 2,
                                    "source_pod_name": "stage-1-1",
                                    "target_pod_name": "stage-2-0",
                                    "link_cost_ms": 8.5,
                                    "forwarding_path": second,
                                },
                            ]
                        }
                    ]
                }
            },
        },
        {"event": "run_completed"},
    ]
    path.write_text(
        "\n".join(json.dumps(event) for event in events) + "\n",
        encoding="utf-8",
    )

    sockets = summarize_trace(path)["forwarder_runtime"]["source_sockets"]

    assert sorted(sockets) == [
        "stage-1-0:pid-101:port-43210",
        "stage-1-1:pid-102:port-43210",
    ]


def test_forwarding_path_summary_rejects_inconsistent_v3_worker_identity(tmp_path):
    path = tmp_path / "trace.jsonl"
    timing = _timing_v3_with_worker_identity()
    timing["target_worker_process_id"] = 203
    _trace(path, timing)

    with pytest.raises(ValueError, match="worker identity"):
        summarize_trace(path)


def test_forwarding_path_summary_rejects_incomplete_v3_http_client_timing(
    tmp_path,
):
    path = tmp_path / "trace.jsonl"
    timing = _timing_v3()
    del timing["source_http_client_timing"][
        "response_headers_started_unix_ns"
    ]
    _trace(path, timing)

    with pytest.raises(ValueError, match="invalid timestamps"):
        summarize_trace(path)
