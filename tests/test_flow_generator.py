import asyncio
import json
from collections import Counter, defaultdict
from types import SimpleNamespace

import httpx
from httpx import ASGITransport, AsyncClient, MockTransport, Request, Response
import pytest
from pydantic import ValidationError

from testbed.flow_generator import (
    FlowExecutionError,
    FlowGenerator,
    FlowGeneratorConfig,
    RunSlotResponse,
    RunSlotRequest,
    _has_complete_forwarding_path_v3,
    create_app,
)


def _diagnostic_link(source_worker_process_id, target_worker_process_id):
    target_runtime = SimpleNamespace()
    target_handler = SimpleNamespace(
        worker_process_id=target_worker_process_id,
        forwarder_runtime=target_runtime,
    )
    return SimpleNamespace(
        forwarding_path=SimpleNamespace(
            schema_version="forwarding_path_v3",
            source_worker_process_id=source_worker_process_id,
            target_worker_process_id=target_worker_process_id,
            target_handler_timing=target_handler,
            source_http_client_timing=SimpleNamespace(
                schema_version="http_client_path_v2"
            ),
            forwarder_runtime=SimpleNamespace(
                schema_version="forwarder_runtime_v1",
                target_handler=target_runtime,
            ),
        )
    )


def test_forwarding_path_v3_requires_source_worker_handler_chain():
    first = _diagnostic_link(101, 202)
    second = _diagnostic_link(202, 303)
    initial_handler = SimpleNamespace(worker_process_id=101)

    assert _has_complete_forwarding_path_v3(
        [first, second], initial_handler
    )
    assert _has_complete_forwarding_path_v3([first, second])

    second.forwarding_path.source_worker_process_id = 404
    assert not _has_complete_forwarding_path_v3(
        [first, second], initial_handler
    )
    assert not _has_complete_forwarding_path_v3([first, second])


def route(flow_id, replica_by_stage=None, stages=(1, 2, 3)):
    replica_by_stage = replica_by_stage or {stage: 1 for stage in stages}
    return {
        "flow_id": flow_id,
        "hops": [
            {
                "stage": stage,
                "replica_id": replica_by_stage[stage],
                "url": f"http://stage-{stage}-{replica_by_stage[stage]}",
            }
            for stage in stages
        ],
    }


class RecordingReplicaNetwork:
    def __init__(
        self,
        *,
        failing_host=None,
        mismatch_host=None,
        mismatch_correlation_host=None,
        mismatch_link=False,
        mismatch_link_metadata=None,
        omit_links=False,
    ):
        self.failing_host = failing_host
        self.mismatch_host = mismatch_host
        self.mismatch_correlation_host = mismatch_correlation_host
        self.mismatch_link = mismatch_link
        self.mismatch_link_metadata = mismatch_link_metadata
        self.omit_links = omit_links
        self.calls = []
        self.payloads = []
        self.active = Counter()
        self.peak = Counter()
        self.cgroup_snapshots = Counter()

    async def __call__(self, request: Request):
        entry_host = request.url.host
        if request.method == "GET" and request.url.path == "/runtime-cgroup":
            _, entry_stage, entry_replica_id = entry_host.split("-")
            self.cgroup_snapshots[entry_host] += 1
            sample = self.cgroup_snapshots[entry_host]
            offset = 100 * int(entry_stage) + 10 * int(entry_replica_id)
            return Response(
                200,
                request=request,
                json={
                    "stage": int(entry_stage),
                    "replica_id": int(entry_replica_id),
                    "pod_name": entry_host,
                    "cgroup_version": "v2",
                    "usage_usec": offset + (sample - 1) * 17,
                    "nr_periods": offset + (sample - 1),
                    "nr_throttled": int(entry_replica_id) + sample - 1,
                    "throttled_usec": offset + (sample - 1) * 7,
                    "quota_usec": 50_000,
                    "period_usec": 100_000,
                    "weight": 6,
                },
            )
        payload = json.loads(request.content)
        _, entry_stage, entry_replica_id = entry_host.split("-")
        route_hops = [
            {
                "stage": int(entry_stage),
                "replica_id": int(entry_replica_id),
                "url": f"http://{entry_host}",
                "assigned_load": payload["assigned_load"],
            },
            *payload["remaining_hops"],
        ]
        hosts = [
            f"stage-{hop['stage']}-{hop['replica_id']}" for hop in route_hops
        ]
        for host, hop in zip(hosts, route_hops):
            self.calls.append((payload["flow_id"], host))
            self.payloads.append((host, hop))
            self.active[host] += 1
            self.peak[host] = max(self.peak[host], self.active[host])

        try:
            await asyncio.sleep(0.01)
            if self.failing_host in hosts:
                failed_stage = self.failing_host.split("-")[1]
                return Response(
                    503,
                    request=request,
                    text=f"stage {failed_stage} request failed",
                )

            hops = []
            for host, hop in zip(hosts, route_hops):
                response_replica = hop["replica_id"]
                if host == self.mismatch_host:
                    response_replica += 1
                response_flow_id = payload["flow_id"]
                if host == self.mismatch_correlation_host:
                    response_flow_id += 1
                hops.append(
                    {
                        "slot_id": payload["slot_id"],
                        "flow_id": response_flow_id,
                        "stage": hop["stage"],
                        "replica_id": response_replica,
                        "pod_name": host,
                        "concurrency": self.active[host],
                        "assigned_load": hop["assigned_load"],
                        "modeled_processing_latency_ms": 10.0,
                        "legacy_congestion": hop["assigned_load"],
                        "processing_latency_ms": 10.0,
                        "signal_latency_ms": 10.0,
                        "state_estimate": 3,
                        "state_likelihood": [0.1, 0.2, 0.3, 0.4],
                        "legacy_signal": 3,
                        "legacy_likelihood": [0.1, 0.2, 0.3, 0.4],
                    }
                )
            links = [
                {
                    "slot_id": payload["slot_id"],
                    "flow_id": payload["flow_id"],
                    "source_stage": left["stage"],
                    "source_replica_id": left["replica_id"],
                    "source_pod_name": left_host,
                    "target_stage": right["stage"],
                    "target_replica_id": right["replica_id"],
                    "target_pod_name": right_host,
                    "target_endpoint": right["url"],
                    "request_latency_ms": 11.0,
                    "callee_elapsed_ms": 10.0,
                    "link_cost_ms": 1.0,
                }
                for left, right, left_host, right_host in zip(
                    route_hops,
                    route_hops[1:],
                    hosts,
                    hosts[1:],
                )
            ]
            if self.mismatch_link:
                links[0]["target_replica_id"] += 1
            if self.mismatch_link_metadata:
                links[0][self.mismatch_link_metadata] = "wrong"
            response_body = {
                "datapath_mode": payload["datapath_mode"],
                "slot_id": payload["slot_id"],
                "flow_id": payload["flow_id"],
                "elapsed_ms": 30.0 + len(links),
                "hops": hops,
            }
            if not self.omit_links:
                response_body["links"] = links
            return Response(
                200,
                request=request,
                json=response_body,
            )
        finally:
            for host in hosts:
                self.active[host] -= 1


def test_complete_routes_run_flows_concurrently_and_hops_sequentially():
    network = RecordingReplicaNetwork()
    generator = FlowGenerator(transport=MockTransport(network))
    request = RunSlotRequest(
        datapath_mode="kernel",
        slot_id=8,
        routes=[route(flow_id) for flow_id in (1, 2, 3)],
    )

    response = asyncio.run(generator.run_slot(request))

    assert response.slot_id == 8
    assert response.datapath_mode == "kernel"
    assert [flow.flow_id for flow in response.flows] == [1, 2, 3]
    assert all([hop.stage for hop in flow.hops] == [1, 2, 3] for flow in response.flows)
    assert network.peak["stage-1-1"] == 3
    assert network.peak["stage-2-1"] == 3
    assert network.peak["stage-3-1"] == 3
    assert all(
        payload["assigned_load"] == 3
        for _, payload in network.payloads
    )
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
        datapath_mode="kernel",
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
        generator.run_slot(
            RunSlotRequest(
                datapath_mode="kernel",
                slot_id=4,
                routes=[route(9)],
            )
        )
    )

    flow = response.flows[0]
    for hop in flow.hops:
        assert hop.datapath_mode == "kernel"
        assert hop.slot_id == 4
        assert hop.flow_id == 9
        assert hop.request_latency_ms >= hop.processing_latency_ms
        assert hop.transport_overhead_ms >= 0
        assert hop.assigned_load == 1
        assert hop.signal_latency_ms == hop.processing_latency_ms
        assert hop.state_estimate == 3
        assert hop.state_likelihood == (0.1, 0.2, 0.3, 0.4)
        assert hop.legacy_congestion == 1
        assert hop.legacy_signal == 3
        assert hop.legacy_likelihood == (0.1, 0.2, 0.3, 0.4)
    assert len(flow.links) == 2
    assert [(link.source_stage, link.target_stage) for link in flow.links] == [
        (1, 2),
        (2, 3),
    ]
    assert all(
        link.link_cost_ms
        == pytest.approx(link.request_latency_ms - link.callee_elapsed_ms)
        for link in flow.links
    )
    assert flow.ingress_request_latency_ms >= 0
    assert flow.ingress_overhead_ms >= 0


def test_opt_in_forwarder_cgroup_diagnostics_delta_each_selected_forwarder_once():
    network = RecordingReplicaNetwork()
    generator = FlowGenerator(transport=MockTransport(network))

    response = asyncio.run(
        generator.run_slot(
            RunSlotRequest(
                datapath_mode="kernel",
                slot_id=4,
                forwarder_cgroup_diagnostics=True,
                routes=[
                    route(1, {1: 1, 2: 2, 3: 1}),
                    route(2, {1: 1, 2: 1, 3: 1}),
                ],
            )
        )
    )

    cgroup = response.forwarder_cgroup
    assert cgroup.schema_version == "forwarder_cgroup_v1"
    assert cgroup.selection_scope == "selected_forwarders_only"
    assert len(cgroup.forwarders) == 4
    assert cgroup.totals == {
        "usage_usec_delta": 68,
        "periods_delta": 4,
        "throttled_periods_delta": 4,
        "throttled_usec_delta": 28,
    }
    assert all(item.usage_usec_delta == 17 for item in cgroup.forwarders)
    assert all(item.throttled_usec_delta == 7 for item in cgroup.forwarders)
    assert {
        (item.stage, item.replica_id, item.route_requests, item.source_pair_requests)
        for item in cgroup.forwarders
    } == {
        (1, 1, 2, 2),
        (2, 1, 1, 1),
        (2, 2, 1, 1),
        (3, 1, 2, 0),
    }
    assert all(count == 2 for count in network.cgroup_snapshots.values())


@pytest.mark.parametrize(
    "missing_field",
    ["links", "ingress_request_latency_ms", "ingress_overhead_ms"],
)
def test_current_flow_telemetry_requires_pairwise_and_ingress_fields(
    missing_field,
):
    generator = FlowGenerator(transport=MockTransport(RecordingReplicaNetwork()))
    response = asyncio.run(
        generator.run_slot(
            RunSlotRequest(
                datapath_mode="kernel",
                slot_id=4,
                routes=[route(9)],
            )
        )
    ).model_dump(mode="json")
    response["flows"][0].pop(missing_field)

    with pytest.raises(ValidationError):
        RunSlotResponse.model_validate(response)


@pytest.mark.parametrize(
    "payload, message",
    [
        (
            {
                "datapath_mode": "kernel",
                "slot_id": 1,
                "routes": [route(1), route(1)],
            },
            "flow_id values must be unique",
        ),
        (
            {
                "slot_id": 1,
                "datapath_mode": "kernel",
                "routes": [
                    {
                        "flow_id": 1,
                        "hops": list(reversed(route(1)["hops"])),
                    }
                ],
            },
            "contiguous stages starting at 1 in order",
        ),
        (
            {
                "slot_id": 1,
                "datapath_mode": "kernel",
                "routes": [route(1, stages=(1, 2)), route(2)],
            },
            "same stages",
        ),
    ],
)
def test_route_contract_rejects_ambiguous_input(payload, message):
    with pytest.raises(ValueError, match=message):
        RunSlotRequest.model_validate(payload)


def test_route_contract_accepts_configurable_stage_count():
    request = RunSlotRequest.model_validate(
        {
            "datapath_mode": "kernel",
            "slot_id": 1,
            "routes": [route(1, stages=(1, 2, 3, 4))],
        }
    )

    assert [hop.stage for hop in request.routes[0].hops] == [1, 2, 3, 4]


@pytest.mark.parametrize(
    "network, message",
    [
        (RecordingReplicaNetwork(failing_host="stage-2-1"), "stage 2 request failed"),
        (
            RecordingReplicaNetwork(mismatch_host="stage-2-1"),
            "mismatched hop telemetry",
        ),
        (
            RecordingReplicaNetwork(mismatch_correlation_host="stage-2-1"),
            "mismatched hop telemetry",
        ),
        (
            RecordingReplicaNetwork(mismatch_link=True),
            "mismatched pairwise link telemetry",
        ),
        (
            RecordingReplicaNetwork(
                mismatch_link_metadata="source_pod_name"
            ),
            "mismatched pairwise link telemetry",
        ),
        (
            RecordingReplicaNetwork(
                mismatch_link_metadata="target_pod_name"
            ),
            "mismatched pairwise link telemetry",
        ),
        (
            RecordingReplicaNetwork(
                mismatch_link_metadata="target_endpoint"
            ),
            "mismatched pairwise link telemetry",
        ),
        (
            RecordingReplicaNetwork(omit_links=True),
            "forwarded route failed",
        ),
    ],
)
def test_downstream_failures_are_correlated_and_reported(network, message):
    generator = FlowGenerator(transport=MockTransport(network))

    with pytest.raises(FlowExecutionError, match=message):
        asyncio.run(
            generator.run_slot(
                RunSlotRequest(
                    datapath_mode="kernel",
                    slot_id=1,
                    routes=[route(1)],
                )
            )
        )
    assert all(active == 0 for active in network.active.values())


def test_empty_httpx_error_retains_class_and_representation():
    async def connection_dropped(request):
        raise httpx.ReadError("", request=request)

    generator = FlowGenerator(transport=MockTransport(connection_dropped))

    with pytest.raises(FlowExecutionError) as raised:
        asyncio.run(
            generator.run_slot(
                RunSlotRequest(
                    datapath_mode="kernel",
                    slot_id=1,
                    routes=[route(2)],
                )
            )
        )

    assert str(raised.value) == (
        "flow 2 forwarded route failed: ReadError: ReadError('')"
    )


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
                json={
                    "datapath_mode": "kernel",
                    "slot_id": 1,
                    "routes": [route(1)],
                },
            )
            return health, failed

    health, failed = asyncio.run(scenario())

    assert health.status_code == 200
    assert health.json() == {"status": "ok", "datapath_mode": "kernel"}
    assert failed.status_code == 502
    assert "stage 2 request failed" in failed.json()["detail"]


def test_flow_generator_config_rejects_nonpositive_timeout():
    with pytest.raises(ValueError, match="request_timeout_seconds"):
        FlowGeneratorConfig(request_timeout_seconds=0)


def test_flow_generator_rejects_unimplemented_datapath_mode():
    with pytest.raises(ValueError, match="unsupported datapath mode"):
        RunSlotRequest.model_validate(
            {
                "datapath_mode": "dpdk-vpp",
                "slot_id": 1,
                "routes": [route(1)],
            }
        )
