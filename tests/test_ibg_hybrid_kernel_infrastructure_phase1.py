import asyncio
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from httpx import AsyncBaseTransport, MockTransport, Request, Response
import pytest
from pydantic import ValidationError

from IBG import latency_model as exact_latency
from IBG_Hybrid.contracts import HybridConfiguration, ReplicaChoice, TwoStageAction
from IBG_Hybrid.kernel_infrastructure_contract import (
    DEFAULT_HYBRID_KERNEL_OWNERSHIP,
    HybridKernelDiscoveredReplica,
    HybridKernelDiscoverySnapshot,
)
from IBG_Hybrid.kernel_route_contracts import (
    HYBRID_KERNEL_ROUTE_CONTRACT_VERSION,
    HYBRID_KERNEL_ROUTE_EXECUTION_VERSION,
    HybridKernelFlowRoute,
    HybridKernelHopTarget,
    HybridKernelRunSlotRequest,
    build_hybrid_kernel_run_slot_request,
)
from IBG_Hybrid.kernel_route_execution import (
    HybridKernelRouteExecutionError,
    HybridKernelRouteExecutor,
    HybridKernelRouteExecutorConfig,
)
from IBG_Hybrid.kernel_route_forwarder import HybridKernelRouteForwarder
from testbed.route_forwarder import (
    ForwardHop,
    ForwarderConfig,
    ReplicaRouteForwarder,
    RouteForwardingError,
    RouteProcessRequest,
)


ROOT = Path(__file__).resolve().parents[1]


class CountingAsyncTransport(AsyncBaseTransport):
    def __init__(self, handler):
        self.handler = handler
        self.requests = []
        self.close_calls = 0

    async def handle_async_request(self, request):
        self.requests.append(request)
        return await self.handler(request)

    async def aclose(self):
        self.close_calls += 1


def action(first, second):
    return TwoStageAction((ReplicaChoice(*first), ReplicaChoice(*second)))


def discovered(config):
    ownership = DEFAULT_HYBRID_KERNEL_OWNERSHIP
    replicas = tuple(
        HybridKernelDiscoveredReplica(
            choice=ReplicaChoice(stage, replica),
            namespace=ownership.namespace,
            pod_name=f"{ownership.stage_name(stage)}-{replica - 1}",
            pod_uid=f"uid-{stage}-{replica}",
            node_name="worker-1",
            endpoint=f"http://{ownership.stage_name(stage)}-{replica - 1}",
            labels=ownership.replica_labels(stage),
        )
        for stage in range(1, config.num_stages + 1)
        for replica in range(1, config.num_replicas + 1)
    )
    return HybridKernelDiscoverySnapshot(config, replicas)


def route(flow_id, first, second, skipped_stage, first_load=1, second_load=1):
    return HybridKernelFlowRoute(
        flow_id=flow_id,
        hops=(
            HybridKernelHopTarget(
                stage=first[0],
                replica_id=first[1],
                url=f"http://hybrid-stage-{first[0]}-{first[1] - 1}",
                assigned_load=first_load,
            ),
            HybridKernelHopTarget(
                stage=second[0],
                replica_id=second[1],
                url=f"http://hybrid-stage-{second[0]}-{second[1] - 1}",
                assigned_load=second_load,
            ),
        ),
        skipped_stage=skipped_stage,
    )


def forwarded_response(payload, *, omit_second=False, pair_target_stage=None):
    match = re.fullmatch(r"hybrid-stage-(\d+)-(\d+)", payload["entry_host"])
    assert match is not None
    first = {
        "stage": int(match.group(1)),
        "replica_id": int(match.group(2)) + 1,
        "url": f"http://{payload['entry_host']}/",
        "assigned_load": payload["assigned_load"],
    }
    selected = (first, payload["remaining_hops"][0])
    hops = []
    for selected_hop in selected:
        physical = 20.0 + selected_hop["stage"]
        jitter = 4.0
        signal = physical + jitter
        likelihood = exact_latency.learning_signal_likelihood(
            signal,
            selected_hop["assigned_load"],
        )
        hops.append(
            {
                "slot_id": payload["slot_id"],
                "flow_id": payload["flow_id"],
                "stage": selected_hop["stage"],
                "replica_id": selected_hop["replica_id"],
                "pod_name": (
                    f"hybrid-stage-{selected_hop['stage']}-"
                    f"{selected_hop['replica_id'] - 1}"
                ),
                "concurrency": 1,
                "assigned_load": selected_hop["assigned_load"],
                "modeled_processing_latency_ms": physical - 1.0,
                "legacy_congestion": selected_hop["assigned_load"],
                "processing_latency_ms": physical,
                "observation_jitter_ms": jitter,
                "signal_latency_ms": signal,
                "state_estimate": exact_latency.estimate_state(likelihood),
                "state_likelihood": likelihood,
                "legacy_signal": exact_latency.estimate_state(likelihood),
                "legacy_likelihood": likelihood,
            }
        )
    response_hops = hops[:1] if omit_second else hops
    second = selected[1]
    return {
        "datapath_mode": "kernel",
        "slot_id": payload["slot_id"],
        "flow_id": payload["flow_id"],
        "elapsed_ms": 12.0,
        "hops": response_hops,
        "links": [
            {
                "slot_id": payload["slot_id"],
                "flow_id": payload["flow_id"],
                "source_stage": first["stage"],
                "source_replica_id": first["replica_id"],
                "source_pod_name": hops[0]["pod_name"],
                "target_stage": (
                    second["stage"]
                    if pair_target_stage is None
                    else pair_target_stage
                ),
                "target_replica_id": second["replica_id"],
                "target_pod_name": hops[1]["pod_name"],
                "target_endpoint": second["url"],
                "request_latency_ms": 15.0,
                "callee_elapsed_ms": 10.0,
                "link_cost_ms": 5.0,
            }
        ],
    }


def test_route_contract_accepts_noncontiguous_and_non_stage1_routes_together():
    request = HybridKernelRunSlotRequest(
        slot_id=7,
        routes=(
            route(1, (1, 1), (3, 1), skipped_stage=2),
            route(2, (2, 1), (3, 2), skipped_stage=1),
        ),
    )

    assert request.contract_version == HYBRID_KERNEL_ROUTE_CONTRACT_VERSION
    assert request.selected_assignment_count == 4
    assert tuple(item.action.stages for item in request.routes) == ((1, 3), (2, 3))
    assert tuple(item.skipped_stage for item in request.routes) == (2, 1)


@pytest.mark.parametrize(
    "hops",
    (
        ((1, 1), (1, 2)),
        ((3, 1), (2, 1)),
    ),
)
def test_route_contract_rejects_same_or_reverse_stage_order(hops):
    with pytest.raises(ValidationError, match="distinct and increasing"):
        route(1, hops[0], hops[1], skipped_stage=2)


def test_route_contract_rejects_wrong_skipped_stage_and_wrong_hop_count():
    with pytest.raises(ValidationError, match="skipped_stage"):
        route(1, (1, 1), (3, 1), skipped_stage=3)
    with pytest.raises(ValidationError):
        HybridKernelFlowRoute(
            flow_id=1,
            hops=(
                HybridKernelHopTarget(
                    stage=1,
                    replica_id=1,
                    url="http://hybrid-stage-1-0",
                    assigned_load=1,
                ),
            ),
            skipped_stage=2,
        )


def test_complete_route_builder_uses_final_loads_and_no_skipped_endpoints():
    config = HybridConfiguration(num_flows=2, num_replicas=2)
    request = build_hybrid_kernel_run_slot_request(
        slot_id=3,
        configuration=config,
        actions_by_flow={
            2: action((2, 1), (3, 1)),
            1: action((1, 1), (3, 1)),
        },
        discovery=discovered(config),
    )

    assert tuple(item.flow_id for item in request.routes) == (1, 2)
    assert tuple(item.skipped_stage for item in request.routes) == (2, 1)
    assert tuple(hop.assigned_load for hop in request.routes[0].hops) == (1, 2)
    assert tuple(hop.assigned_load for hop in request.routes[1].hops) == (1, 2)
    assert all(
        route_value.skipped_stage not in {hop.stage for hop in route_value.hops}
        for route_value in request.routes
    )


def test_route_builder_refuses_partial_placement_before_traffic():
    config = HybridConfiguration(num_flows=2, num_replicas=1)
    with pytest.raises(ValueError, match="every configured flow"):
        build_hybrid_kernel_run_slot_request(
            slot_id=1,
            configuration=config,
            actions_by_flow={1: action((1, 1), (2, 1))},
            discovery=discovered(config),
        )


def test_slot_contract_rejects_stale_assigned_load_and_endpoint_drift():
    with pytest.raises(ValidationError, match="final loads"):
        HybridKernelRunSlotRequest(
            slot_id=1,
            routes=(
                route(1, (1, 1), (3, 1), 2, second_load=1),
                route(2, (2, 1), (3, 1), 1, second_load=1),
            ),
        )
    first = route(1, (1, 1), (3, 1), 2, second_load=2)
    second = route(2, (2, 1), (3, 1), 1, second_load=2)
    second = second.model_copy(
        update={
            "hops": (
                second.hops[0],
                second.hops[1].model_copy(update={"url": "http://different"}),
            )
        }
    )
    with pytest.raises(ValidationError, match="inconsistent endpoints"):
        HybridKernelRunSlotRequest(slot_id=1, routes=(first, second))


def test_route_executor_returns_two_observations_one_pair_and_selected_only_inputs():
    calls = []

    async def handler(request_value: Request):
        payload = json.loads(request_value.content)
        payload["entry_host"] = request_value.url.host
        calls.append(payload)
        await asyncio.sleep(0.005)
        return Response(
            200,
            request=request_value,
            json=forwarded_response(payload),
        )

    request = HybridKernelRunSlotRequest(
        slot_id=9,
        routes=(
            route(1, (1, 1), (3, 1), skipped_stage=2),
            route(2, (2, 1), (3, 2), skipped_stage=1),
        ),
    )
    result = asyncio.run(
        HybridKernelRouteExecutor(transport=MockTransport(handler)).run_slot(request)
    )

    assert result.contract_version == HYBRID_KERNEL_ROUTE_CONTRACT_VERSION
    assert result.execution_version == HYBRID_KERNEL_ROUTE_EXECUTION_VERSION
    assert result.observation_count == 4
    assert result.measured_pair_count == 2
    assert len(calls) == 2
    assert all(len(payload["remaining_hops"]) == 1 for payload in calls)
    assert tuple(tuple(hop.stage for hop in flow.hops) for flow in result.flows) == (
        (1, 3),
        (2, 3),
    )
    assert tuple(flow.skipped_stage for flow in result.flows) == (2, 1)
    assert all(len(flow.selected_learning_signals_ms) == 2 for flow in result.flows)
    assert result.flows[0].selected_physical_processing_latency_ms == 44.0
    assert all(
        flow.skipped_stage not in {choice.stage for choice in flow.selected_choices}
        for flow in result.flows
    )
    assert all(
        flow.skipped_stage
        not in {
            flow.measured_pair.source_stage,
            flow.measured_pair.target_stage,
        }
        for flow in result.flows
    )


def test_route_executor_reuses_application_client_and_closes_after_failure():
    fail = False

    async def handler(request_value: Request):
        if fail:
            raise RuntimeError("injected transport failure")
        payload = json.loads(request_value.content)
        payload["entry_host"] = request_value.url.host
        return Response(
            200,
            request=request_value,
            json=forwarded_response(payload),
        )

    transport = CountingAsyncTransport(handler)
    request = HybridKernelRunSlotRequest(
        slot_id=9,
        routes=(route(1, (1, 1), (3, 1), skipped_stage=2),),
    )

    async def exercise():
        nonlocal fail
        async with HybridKernelRouteExecutor(transport=transport) as executor:
            assert executor.is_started is True
            first = await executor.run_slot(request)
            second = await executor.run_slot(
                request.model_copy(update={"slot_id": 10})
            )
            assert transport.close_calls == 0
            assert (
                first.flows[0].selected_choices
                == second.flows[0].selected_choices
            )
            fail = True
            with pytest.raises(
                HybridKernelRouteExecutionError,
                match="injected transport failure",
            ):
                await executor.run_slot(
                    request.model_copy(update={"slot_id": 11})
                )
        assert executor.is_closed is True
        with pytest.raises(RuntimeError, match="closed"):
            await executor.run_slot(request)

    asyncio.run(exercise())

    assert len(transport.requests) == 3
    assert transport.close_calls == 1


@pytest.mark.parametrize("timeout", (0, -1, float("nan"), float("inf"), True))
def test_route_executor_rejects_invalid_timeouts(timeout):
    with pytest.raises(ValueError, match="finite and positive"):
        HybridKernelRouteExecutorConfig(request_timeout_seconds=timeout)


@pytest.mark.parametrize(
    ("response_change", "message"),
    (
        ({"omit_second": True}, "incomplete"),
        ({"pair_target_stage": 2}, "selected-pair"),
    ),
)
def test_route_executor_fails_on_partial_or_mismatched_telemetry(
    response_change,
    message,
):
    async def handler(request_value: Request):
        payload = json.loads(request_value.content)
        payload["entry_host"] = request_value.url.host
        return Response(
            200,
            request=request_value,
            json=forwarded_response(payload, **response_change),
        )

    request = HybridKernelRunSlotRequest(
        slot_id=1,
        routes=(route(1, (1, 1), (3, 1), skipped_stage=2),),
    )
    with pytest.raises(HybridKernelRouteExecutionError, match=message):
        asyncio.run(
            HybridKernelRouteExecutor(transport=MockTransport(handler)).run_slot(
                request
            )
        )


def test_hybrid_forwarder_accepts_one_strictly_later_selected_stage():
    runtime = HybridKernelRouteForwarder(
        ForwarderConfig(stage=1, replica_id=1, pod_name="hybrid-stage-1-0")
    )
    noncontiguous = RouteProcessRequest(
        datapath_mode="kernel",
        slot_id=1,
        flow_id=1,
        assigned_load=1,
        remaining_hops=[
            ForwardHop(
                stage=3,
                replica_id=1,
                url="http://hybrid-stage-3-0",
                assigned_load=1,
            )
        ],
    )
    runtime._validate_next_hop(noncontiguous)

    reverse = noncontiguous.model_copy(
        update={
            "remaining_hops": [
                ForwardHop(
                    stage=1,
                    replica_id=2,
                    url="http://hybrid-stage-1-1",
                    assigned_load=1,
                )
            ]
        }
    )
    with pytest.raises(RouteForwardingError, match="strictly later"):
        runtime._validate_next_hop(reverse)
    asyncio.run(runtime.close())


def test_hybrid_forwarder_rejects_more_than_one_remaining_hop():
    runtime = HybridKernelRouteForwarder(
        ForwarderConfig(stage=1, replica_id=1, pod_name="hybrid-stage-1-0")
    )
    request = RouteProcessRequest(
        datapath_mode="kernel",
        slot_id=1,
        flow_id=1,
        assigned_load=1,
        remaining_hops=[
            ForwardHop(stage=2, replica_id=1, url="http://s2", assigned_load=1),
            ForwardHop(stage=3, replica_id=1, url="http://s3", assigned_load=1),
        ],
    )
    with pytest.raises(RouteForwardingError, match="exactly one remaining hop"):
        runtime._validate_next_hop(request)
    asyncio.run(runtime.close())


def test_frozen_exact_forwarder_still_rejects_noncontiguous_route():
    runtime = ReplicaRouteForwarder(
        ForwarderConfig(stage=1, replica_id=1, pod_name="stage-1-0")
    )
    request = RouteProcessRequest(
        datapath_mode="kernel",
        slot_id=1,
        flow_id=1,
        assigned_load=1,
        remaining_hops=[
            ForwardHop(stage=3, replica_id=1, url="http://stage-3-0", assigned_load=1)
        ],
    )
    with pytest.raises(RouteForwardingError, match="must be 2, got 3"):
        runtime._validate_next_hop(request)
    asyncio.run(runtime.close())


def test_phase1_imports_are_silent_rng_neutral_and_file_safe(
    tmp_path,
):
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT)
    code = (
        "import random, numpy as np; "
        "random.seed(81); np.random.seed(82); "
        "p=random.getstate(); n=np.random.get_state(); "
        "import IBG_Hybrid.kernel_route_contracts; "
        "import IBG_Hybrid.kernel_route_forwarder; "
        "import IBG_Hybrid.kernel_route_execution; "
        "assert random.getstate()==p; a=np.random.get_state(); "
        "assert a[0]==n[0] and np.array_equal(a[1],n[1]) and a[2:]==n[2:]"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert completed.stderr == ""
    assert list(tmp_path.iterdir()) == []
