import asyncio

import httpx
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest

from testbed.cnf_service import ReplicaConfig, create_app as create_processor_app
from testbed.route_forwarder import (
    ForwarderConfig,
    ForwarderCgroupSnapshot,
    HttpClientTraceRecorder,
    ReplicaRouteForwarder,
    create_app as create_forwarder_app,
)


def fixed_latency(assigned_load):
    return 2.0


def test_forwarder_keepalive_is_configurable_and_defaults_to_30_seconds():
    assert ForwarderConfig().keepalive_expiry_seconds == 30.0
    assert ForwarderConfig.from_env(
        {"FORWARDER_KEEPALIVE_SECONDS": "45"}
    ).keepalive_expiry_seconds == 45.0
    with pytest.raises(ValueError, match="keepalive_expiry_seconds"):
        ForwarderConfig(keepalive_expiry_seconds=0)


def test_keepalive_applies_only_to_downstream_forwarder_requests(monkeypatch):
    created = []

    class Client:
        def __init__(self, **kwargs):
            created.append(kwargs)

        async def aclose(self):
            pass

    monkeypatch.setattr("testbed.route_forwarder.httpx.AsyncClient", Client)

    ReplicaRouteForwarder(ForwarderConfig())

    assert len(created) == 2
    assert "limits" not in created[0]
    assert created[1]["limits"].keepalive_expiry == 30.0


async def request(app, method, path, **kwargs):
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        return await client.request(method, path, **kwargs)


class HostRoutingTransport(httpx.AsyncBaseTransport):
    def __init__(self):
        self.apps = {}
        self.calls = []

    async def handle_async_request(self, request):
        self.calls.append((request.url.host, request.url.path))
        trace = request.extensions.get("trace")

        async def emit(name):
            if trace is not None:
                await trace(name, {})

        await emit("http11.send_request_headers.started")
        await emit("http11.send_request_headers.complete")
        await emit("http11.send_request_body.started")
        await emit("http11.send_request_body.complete")
        transport = ASGITransport(app=self.apps[request.url.host])
        response = await transport.handle_async_request(request)
        await emit("http11.receive_response_headers.started")
        await emit("http11.receive_response_headers.complete")
        await emit("http11.receive_response_body.started")
        await emit("http11.receive_response_body.complete")
        await emit("http11.response_closed.started")
        await emit("http11.response_closed.complete")
        return response


def isolated_route_apps():
    router = HostRoutingTransport()
    processors = {
        f"processor-{stage}": create_processor_app(
            ReplicaConfig(
                stage=stage,
                replica_id=1,
                pod_name=f"stage-{stage}-1",
            ),
            observation_source=fixed_latency,
        )
        for stage in (1, 2, 3)
    }
    forwarders = {
        f"stage-{stage}-1": create_forwarder_app(
            ForwarderConfig(
                stage=stage,
                replica_id=1,
                pod_name=f"stage-{stage}-1",
                processor_url=f"http://processor-{stage}",
            ),
            transport=router,
        )
        for stage in (1, 2, 3)
    }
    router.apps = {**processors, **forwarders}
    return router, processors, forwarders


def route_payload(flow_id=9):
    return {
        "datapath_mode": "kernel",
        "slot_id": 4,
        "flow_id": flow_id,
        "assigned_load": 1,
        "remaining_hops": [
            {
                "stage": 2,
                "replica_id": 1,
                "url": "http://stage-2-1",
                "assigned_load": 1,
            },
            {
                "stage": 3,
                "replica_id": 1,
                "url": "http://stage-3-1",
                "assigned_load": 1,
            },
        ],
    }


def test_selected_route_uses_isolated_processors_and_pairwise_links():
    router, processors, forwarders = isolated_route_apps()

    response = asyncio.run(
        request(
            forwarders["stage-1-1"],
            "POST",
            "/process-route",
            json=route_payload(),
        )
    )
    body = response.json()

    assert response.status_code == 200
    assert [(hop["stage"], hop["replica_id"]) for hop in body["hops"]] == [
        (1, 1),
        (2, 1),
        (3, 1),
    ]
    assert [
        (link["source_stage"], link["target_stage"])
        for link in body["links"]
    ] == [(1, 2), (2, 3)]
    assert all(link["link_cost_ms"] >= 0 for link in body["links"])
    assert router.calls == [
        ("processor-1", "/process"),
        ("stage-2-1", "/process-route"),
        ("processor-2", "/process"),
        ("stage-3-1", "/process-route"),
        ("processor-3", "/process"),
    ]
    assert all(
        app.state.runtime.active_requests == 0 for app in processors.values()
    )


def test_opt_in_forwarding_path_diagnostics_split_each_pair_residual():
    _, _, forwarders = isolated_route_apps()

    response = asyncio.run(
        request(
            forwarders["stage-1-1"],
            "POST",
            "/process-route",
            json={**route_payload(), "forwarding_path_diagnostics": True},
        )
    )

    assert response.status_code == 200
    for link in response.json()["links"]:
        timing = link["forwarding_path"]
        assert timing["schema_version"] == "forwarding_path_v3"
        assert timing["clock"] == "unix-epoch-ns"
        assert timing["source_worker_process_id"] > 0
        assert timing["target_worker_process_id"] > 0
        assert (
            timing["source_handler_started_unix_ns"]
            <= timing["source_local_processor_response_received_unix_ns"]
            <= timing["source_request_started_unix_ns"]
            <= timing["target_ingress_started_unix_ns"]
            <= timing["target_handler_started_unix_ns"]
            <= timing["target_handler_finished_unix_ns"]
            <= timing["source_response_received_unix_ns"]
        )
        assert timing["source_to_target_handler_ms"] >= 0
        assert timing["target_handler_ms"] >= 0
        assert timing["target_to_source_response_ms"] >= 0
        assert timing["source_to_target_handler_ms"] == pytest.approx(
            timing["source_to_target_ingress_ms"]
            + timing["target_ingress_to_handler_ms"],
            abs=1e-6,
        )
        handler = timing["target_handler_timing"]
        client = timing["source_http_client_timing"]
        processor = handler["processor_timing"]
        runtime = timing["forwarder_runtime"]
        assert handler["schema_version"] == "forwarding_path_v2"
        assert handler["worker_process_id"] == timing["target_worker_process_id"]
        assert client["schema_version"] == "http_client_path_v2"
        assert client["connection_reused"] is True
        assert runtime["schema_version"] == "forwarder_runtime_v1"
        assert runtime["target_handler"] == handler["forwarder_runtime"]
        assert runtime["source_client"]["active_route_handlers_at_start"] >= 1
        assert runtime["source_client"]["downstream_inflight_at_start"] >= 1
        assert runtime["source_client"]["socket_metadata_available"] is False
        assert runtime["source_client"].get("socket_local_port") is None
        for window in (
            runtime["source_client"]["event_loop_lag"],
            runtime["target_handler"]["event_loop_lag"],
        ):
            assert window["schema_version"] == "event_loop_lag_v1"
            assert window["clock"] == "monotonic-duration"
            assert window["sample_period_ms"] == pytest.approx(5.0)
            if window["sample_count"] == 0:
                assert window.get("max_lag_ms") is None
                assert window.get("p95_lag_ms") is None
            else:
                assert window["max_lag_ms"] >= window["p95_lag_ms"] >= 0
        assert (
            client["request_started_unix_ns"]
            <= client["transport_started_unix_ns"]
            <= client["request_headers_started_unix_ns"]
            <= client["request_headers_finished_unix_ns"]
            <= client["request_body_started_unix_ns"]
            <= client["request_body_finished_unix_ns"]
            <= client["response_headers_started_unix_ns"]
            <= client["response_headers_finished_unix_ns"]
            <= client["response_body_started_unix_ns"]
            <= client["response_body_finished_unix_ns"]
            <= client["response_close_started_unix_ns"]
            <= client["response_close_finished_unix_ns"]
            <= client["response_received_unix_ns"]
        )
        assert processor["schema_version"] == "processor_path_v1"
        decomposed_handler_ms = (
            handler["handler_to_processor_request_ms"]
            + handler["local_processor_round_trip_ms"]
            + (handler.get("processor_response_to_downstream_request_ms") or 0)
            + (handler.get("downstream_round_trip_ms") or 0)
            + handler["completion_ms"]
        )
        assert timing["target_handler_ms"] == pytest.approx(
            decomposed_handler_ms,
            abs=1e-6,
        )


def test_http_client_trace_records_new_connection_milestones(monkeypatch):
    stamps = iter(range(110, 230, 10))
    monkeypatch.setattr(
        "testbed.route_forwarder.time.time_ns",
        lambda: next(stamps),
    )
    recorder = HttpClientTraceRecorder(100)
    events = (
        "connection.connect_tcp.started",
        "connection.connect_tcp.complete",
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

    async def record():
        for event in events:
            await recorder(event, {})

    asyncio.run(record())
    timing = recorder.build(230)

    assert timing.connection_reused is False
    assert timing.pool_wait_ms == pytest.approx(0.00001)
    assert timing.connect_ms == pytest.approx(0.00001)
    assert timing.application_resume_ms == pytest.approx(0.00001)


def test_concurrent_forwarding_does_not_enter_processing_service_or_change_signal():
    router, processors, forwarders = isolated_route_apps()

    async def scenario():
        async with AsyncClient(
            transport=ASGITransport(app=forwarders["stage-1-1"]),
            base_url="http://test",
        ) as client:
            return await asyncio.gather(
                *[
                    client.post(
                        "/process-route",
                        json=route_payload(flow_id),
                    )
                    for flow_id in (1, 2, 3)
                ]
            )

    responses = asyncio.run(scenario())

    assert all(response.status_code == 200 for response in responses)
    assert all(
        hop["signal_latency_ms"] == hop["processing_latency_ms"]
        for response in responses
        for hop in response.json()["hops"]
    )
    assert all(
        hop["processing_latency_ms"] < 20.0
        for response in responses
        for hop in response.json()["hops"]
    )
    assert all(
        app.state.runtime.peak_concurrency == 3 for app in processors.values()
    )
    assert all(
        app.state.runtime.active_requests == 0 for app in processors.values()
    )


def test_processing_service_has_no_route_forwarding_endpoint():
    processor = create_processor_app(
        ReplicaConfig(stage=1, replica_id=1, pod_name="stage-1-0"),
        observation_source=fixed_latency,
    )

    response = asyncio.run(
        request(processor, "POST", "/process-route", json=route_payload())
    )

    assert response.status_code == 404


def test_forwarder_health_requires_matching_local_processor():
    router, _, forwarders = isolated_route_apps()

    response = asyncio.run(
        request(forwarders["stage-2-1"], "GET", "/health")
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "stage": 2,
        "replica_id": 1,
        "pod_name": "stage-2-1",
        "current_concurrency": 0,
    }
    assert router.calls == [("processor-2", "/health")]


def test_forwarder_exposes_its_own_cgroup_cpu_snapshot():
    forwarder = create_forwarder_app(
        ForwarderConfig(
            stage=2,
            replica_id=3,
            pod_name="stage-2-2",
            processor_url="http://processor-2",
        ),
        cgroup_reader=lambda config: ForwarderCgroupSnapshot(
            stage=config.stage,
            replica_id=config.replica_id,
            pod_name=config.pod_name,
            cgroup_version="v2",
            usage_usec=101,
            nr_periods=12,
            nr_throttled=3,
            throttled_usec=77,
            quota_usec=50_000,
            period_usec=100_000,
            weight=6,
        ),
    )

    response = asyncio.run(request(forwarder, "GET", "/runtime-cgroup"))

    assert response.status_code == 200
    assert response.json() == {
        "stage": 2,
        "replica_id": 3,
        "pod_name": "stage-2-2",
        "cgroup_version": "v2",
        "usage_usec": 101,
        "nr_periods": 12,
        "nr_throttled": 3,
        "throttled_usec": 77,
        "quota_usec": 50_000,
        "period_usec": 100_000,
        "weight": 6,
    }


def test_forwarder_maps_local_processor_failure_to_502():
    router = HostRoutingTransport()
    failing_processor = FastAPI()

    @failing_processor.post("/process")
    async def fail():
        return {"incomplete": True}

    forwarder = create_forwarder_app(
        ForwarderConfig(
            stage=1,
            replica_id=1,
            pod_name="stage-1-0",
            processor_url="http://processor-1",
        ),
        transport=router,
    )
    router.apps = {"processor-1": failing_processor}

    response = asyncio.run(
        request(
            forwarder,
            "POST",
            "/process-route",
            json={**route_payload(), "remaining_hops": []},
        )
    )

    assert response.status_code == 502
    assert "local processing failed" in response.json()["detail"]


def test_empty_httpx_error_retains_class_and_representation():
    class ConnectionDroppedTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            raise httpx.ReadError("", request=request)

    forwarder = create_forwarder_app(
        ForwarderConfig(
            stage=1,
            replica_id=1,
            pod_name="stage-1-0",
            processor_url="http://processor-1",
        ),
        transport=ConnectionDroppedTransport(),
    )

    response = asyncio.run(
        request(
            forwarder,
            "POST",
            "/process-route",
            json={**route_payload(), "remaining_hops": []},
        )
    )

    assert response.status_code == 502
    assert response.json()["detail"] == (
        "flow 9 local processing failed: ReadError: ReadError('')"
    )
