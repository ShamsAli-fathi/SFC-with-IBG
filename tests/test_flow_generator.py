import asyncio
import json
from collections import Counter, defaultdict

from httpx import ASGITransport, AsyncClient, MockTransport, Request, Response
import pytest

from testbed.flow_generator import (
    FlowExecutionError,
    FlowGenerator,
    FlowGeneratorConfig,
    RunSlotRequest,
    create_app,
)


def route(flow_id, replica_by_stage=None):
    replica_by_stage = replica_by_stage or {1: 1, 2: 1, 3: 1}
    return {
        "flow_id": flow_id,
        "hops": [
            {
                "stage": stage,
                "replica_id": replica_by_stage[stage],
                "url": f"http://stage-{stage}-{replica_by_stage[stage]}",
            }
            for stage in (1, 2, 3)
        ],
    }


class RecordingReplicaNetwork:
    def __init__(
        self,
        *,
        failing_host=None,
        mismatch_host=None,
        mismatch_correlation_host=None,
    ):
        self.failing_host = failing_host
        self.mismatch_host = mismatch_host
        self.mismatch_correlation_host = mismatch_correlation_host
        self.calls = []
        self.active = Counter()
        self.peak = Counter()

    async def __call__(self, request: Request):
        host = request.url.host
        payload = json.loads(request.content)
        self.calls.append((payload["flow_id"], host))
        self.active[host] += 1
        self.peak[host] = max(self.peak[host], self.active[host])
        concurrency = self.active[host]

        try:
            await asyncio.sleep(0.01)
            if host == self.failing_host:
                return Response(503, request=request, text="unavailable")

            _, stage, replica_id = host.split("-")
            response_stage = int(stage)
            response_replica = int(replica_id)
            if host == self.mismatch_host:
                response_replica += 1
            response_flow_id = payload["flow_id"]
            if host == self.mismatch_correlation_host:
                response_flow_id += 1
            return Response(
                200,
                request=request,
                json={
                    "slot_id": payload["slot_id"],
                    "flow_id": response_flow_id,
                    "stage": response_stage,
                    "replica_id": response_replica,
                    "pod_name": host,
                    "concurrency": concurrency,
                    "processing_latency_ms": 10.0,
                    "legacy_signal": 3,
                    "legacy_likelihood": [0.1, 0.2, 0.3, 0.4],
                },
            )
        finally:
            self.active[host] -= 1


def test_complete_routes_run_flows_concurrently_and_hops_sequentially():
    network = RecordingReplicaNetwork()
    generator = FlowGenerator(transport=MockTransport(network))
    request = RunSlotRequest(
        slot_id=8,
        routes=[route(flow_id) for flow_id in (1, 2, 3)],
    )

    response = asyncio.run(generator.run_slot(request))

    assert response.slot_id == 8
    assert [flow.flow_id for flow in response.flows] == [1, 2, 3]
    assert all([hop.stage for hop in flow.hops] == [1, 2, 3] for flow in response.flows)
    assert network.peak["stage-1-1"] == 3
    assert network.peak["stage-2-1"] == 3
    assert network.peak["stage-3-1"] == 3
    calls_by_flow = defaultdict(list)
    for flow_id, host in network.calls:
        calls_by_flow[flow_id].append(host)
    assert all(
        hosts == ["stage-1-1", "stage-2-1", "stage-3-1"]
        for hosts in calls_by_flow.values()
    )


def test_only_selected_replica_endpoints_receive_requests():
    network = RecordingReplicaNetwork()
    generator = FlowGenerator(transport=MockTransport(network))
    request = RunSlotRequest(
        slot_id=1,
        routes=[
            route(1, {1: 1, 2: 2, 3: 1}),
            route(2, {1: 2, 2: 1, 3: 2}),
        ],
    )

    response = asyncio.run(generator.run_slot(request))

    assert {(flow_id, host) for flow_id, host in network.calls} == {
        (1, "stage-1-1"),
        (1, "stage-2-2"),
        (1, "stage-3-1"),
        (2, "stage-1-2"),
        (2, "stage-2-1"),
        (2, "stage-3-2"),
    }
    assert all(len(flow.hops) == 3 for flow in response.flows)


def test_hop_telemetry_preserves_correlation_and_latency_fields():
    generator = FlowGenerator(transport=MockTransport(RecordingReplicaNetwork()))
    response = asyncio.run(
        generator.run_slot(RunSlotRequest(slot_id=4, routes=[route(9)]))
    )

    for hop in response.flows[0].hops:
        assert hop.slot_id == 4
        assert hop.flow_id == 9
        assert hop.request_latency_ms >= hop.processing_latency_ms
        assert hop.legacy_signal == 3
        assert hop.legacy_likelihood == (0.1, 0.2, 0.3, 0.4)


@pytest.mark.parametrize(
    "payload, message",
    [
        (
            {"slot_id": 1, "routes": [route(1), route(1)]},
            "flow_id values must be unique",
        ),
        (
            {
                "slot_id": 1,
                "routes": [
                    {
                        "flow_id": 1,
                        "hops": list(reversed(route(1)["hops"])),
                    }
                ],
            },
            "stages 1, 2, and 3 in order",
        ),
    ],
)
def test_route_contract_rejects_ambiguous_input(payload, message):
    with pytest.raises(ValueError, match=message):
        RunSlotRequest.model_validate(payload)


@pytest.mark.parametrize(
    "network, message",
    [
        (RecordingReplicaNetwork(failing_host="stage-2-1"), "stage 2 request failed"),
        (RecordingReplicaNetwork(mismatch_host="stage-2-1"), "identity mismatch"),
        (
            RecordingReplicaNetwork(mismatch_correlation_host="stage-2-1"),
            "correlation mismatch",
        ),
    ],
)
def test_downstream_failures_are_correlated_and_reported(network, message):
    generator = FlowGenerator(transport=MockTransport(network))

    with pytest.raises(FlowExecutionError, match=message):
        asyncio.run(
            generator.run_slot(
                RunSlotRequest(slot_id=1, routes=[route(1)])
            )
        )
    assert all(active == 0 for active in network.active.values())


def test_http_service_exposes_health_and_maps_downstream_failure_to_502():
    generator = FlowGenerator(
        transport=MockTransport(
            RecordingReplicaNetwork(failing_host="stage-2-1")
        )
    )
    app = create_app(generator)

    async def scenario():
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            health = await client.get("/health")
            failed = await client.post(
                "/run-slot",
                json={"slot_id": 1, "routes": [route(1)]},
            )
            return health, failed

    health, failed = asyncio.run(scenario())

    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert failed.status_code == 502
    assert "stage 2 request failed" in failed.json()["detail"]


def test_flow_generator_config_rejects_nonpositive_timeout():
    with pytest.raises(ValueError, match="request_timeout_seconds"):
        FlowGeneratorConfig(request_timeout_seconds=0)
