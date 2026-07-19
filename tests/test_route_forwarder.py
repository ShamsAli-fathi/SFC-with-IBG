import asyncio

import httpx
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from testbed.cnf_service import ReplicaConfig, create_app as create_processor_app
from testbed.route_forwarder import (
    ForwarderConfig,
    create_app as create_forwarder_app,
)


def fixed_latency(assigned_load):
    return 2.0


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
        transport = ASGITransport(app=self.apps[request.url.host])
        return await transport.handle_async_request(request)


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
