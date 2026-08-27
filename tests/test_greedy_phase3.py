from __future__ import annotations

import asyncio
from dataclasses import replace
import inspect
import itertools
import json
import os
from pathlib import Path
import random
import subprocess
import sys
from urllib.parse import urlparse

import httpx
import numpy as np
import pytest
from pydantic import ValidationError

from Greedy.contracts import (
    GreedyConfiguration,
    PublicReplicaState,
    ReplicaIdentity,
    TwoStageAction,
)
from Greedy.comparison import (
    CANONICAL_MATCHED_COMPARISON,
    GREEDY_PHASE3_HYBRID_AUDIT_HEAD,
    GREEDY_PHASE3_HYBRID_SOURCE_AUDIT,
)
from Greedy.kernel_contracts import (
    DEFAULT_GREEDY_KERNEL_OWNERSHIP,
    GREEDY_KERNEL_DOWNSTREAM_KEEPALIVE_SECONDS,
    GREEDY_KERNEL_PRIVATE_PROCESSOR_PORT,
    GREEDY_KERNEL_PUBLIC_FORWARDER_PORT,
    GreedyKernelContractError,
    GreedyKernelControllerConfiguration,
    GreedyKernelDiscoveredReplica,
    GreedyKernelDiscoverySnapshot,
)
from Greedy.kernel_controller import (
    GreedyKernelController,
    GreedyKernelFlowGeneratorHttpClient,
)
from Greedy.kernel_controller_config import (
    GREEDY_KERNEL_CONTROLLER_INPUT_VERSION,
    controller_input_document_from_mapping,
)
from Greedy.kernel_flow_generator import create_app as create_generator_app
from Greedy.kernel_processor_service import create_app as create_processor_app
from Greedy.kernel_kubernetes_discovery import (
    GreedyKubernetesApi,
    GreedyKubernetesReplicaDiscovery,
)
from Greedy.kernel_oracle import (
    capture_greedy_kernel_slot,
    replay_captured_kernel_slot,
)
from Greedy.kernel_route_contracts import (
    GreedyKernelFlowTelemetry,
    GreedyKernelHopTarget,
    GreedyKernelHopTelemetry,
    GreedyKernelMeasuredPairTelemetry,
    GreedyKernelRunSlotRequest,
    GreedyKernelRunSlotResponse,
    build_greedy_kernel_run_slot_request,
)
from Greedy.kernel_route_execution import (
    GreedyKernelRouteExecutionError,
    GreedyKernelRouteExecutor,
    GreedyKernelRouteExecutorConfig,
)
from Greedy.kernel_route_forwarder import GreedyKernelRouteForwarder
from Greedy.policy import GreedyPolicy
from IBG import latency_model
from testbed.route_forwarder import (
    ForwardHop,
    ForwarderConfig,
    RouteForwardingError,
    RouteProcessRequest,
)
from testbed.cnf_service import ReplicaConfig


ROOT = Path(__file__).resolve().parents[1]
UNIFORM = (0.25, 0.25, 0.25, 0.25)
FIXED = (0.0, 0.0, 1.0, 0.0)


def identities(configuration):
    return tuple(
        ReplicaIdentity(stage, replica)
        for stage in configuration.stages
        for replica in configuration.replica_ids
    )


def snapshot(configuration):
    ownership = DEFAULT_GREEDY_KERNEL_OWNERSHIP
    return GreedyKernelDiscoverySnapshot(
        configuration=configuration,
        replicas=tuple(
            GreedyKernelDiscoveredReplica(
                identity=identity,
                namespace=ownership.namespace,
                pod_name=f"{ownership.stage_name(identity.stage)}-{identity.replica - 1}",
                pod_uid=f"uid-{identity.stage}-{identity.replica}",
                node_name="worker-1",
                endpoint=(
                    f"http://{ownership.stage_name(identity.stage)}-"
                    f"{identity.replica - 1}"
                ),
                phase="Running",
                ready=True,
                labels=ownership.replica_labels(identity.stage),
            )
            for identity in identities(configuration)
        ),
    )


def actions_for(configuration):
    return {
        flow_id: TwoStageAction(
            (
                ReplicaIdentity(1 + ((flow_id - 1) % (configuration.num_stages - 1)), 1),
                ReplicaIdentity(configuration.num_stages, 1),
            )
        )
        for flow_id in range(1, configuration.num_flows + 1)
    }


def response_for_request(
    request,
    *,
    physical_ms=20.0,
    jitter_ms=2.0,
    pair_ms=5.0,
):
    flows = []
    for route in request.routes:
        hops = []
        for target in route.hops:
            physical = float(physical_ms)
            signal = physical + float(jitter_ms)
            likelihood = latency_model.learning_signal_likelihood(
                signal,
                target.assigned_load,
            )
            hops.append(
                GreedyKernelHopTelemetry(
                    slot_id=request.slot_id,
                    flow_id=route.flow_id,
                    stage=target.stage,
                    replica_id=target.replica_id,
                    route_position=target.route_position,
                    next_stage=target.next_stage,
                    next_replica_id=target.next_replica_id,
                    pod_name=urlparse(str(target.url)).hostname.split(".")[0],
                    endpoint=str(target.url),
                    concurrency=1,
                    assigned_load=target.assigned_load,
                    modeled_processing_latency_ms=physical - 1.0,
                    physical_processing_latency_ms=physical,
                    observation_jitter_ms=jitter_ms,
                    learning_signal_ms=signal,
                    request_latency_ms=10.0,
                    transport_overhead_ms=1.0,
                    estimated_state=latency_model.estimate_state(likelihood),
                    likelihood=likelihood,
                )
            )
        first, second = route.hops
        pair = GreedyKernelMeasuredPairTelemetry(
            slot_id=request.slot_id,
            flow_id=route.flow_id,
            source_stage=first.stage,
            source_replica_id=first.replica_id,
            source_pod_name=hops[0].pod_name,
            target_stage=second.stage,
            target_replica_id=second.replica_id,
            target_pod_name=hops[1].pod_name,
            target_endpoint=str(second.url),
            request_latency_ms=10.0 + pair_ms,
            callee_elapsed_ms=10.0,
            measured_pair_latency_ms=pair_ms,
        )
        flows.append(
            GreedyKernelFlowTelemetry(
                flow_id=route.flow_id,
                bypassed_stages=route.bypassed_stages,
                hops=tuple(hops),
                measured_pair=pair,
                ingress_request_latency_ms=20.0,
                ingress_overhead_ms=2.0,
            )
        )
    return GreedyKernelRunSlotResponse(
        slot_id=request.slot_id,
        elapsed_ms=1.0,
        flows=tuple(flows),
    )


class FakeDiscovery:
    def __init__(self, value, *, failure=None):
        self.value = value
        self.failure = failure
        self.calls = 0
        self.close_calls = 0

    def wait_for_complete_ready(self, **_kwargs):
        self.calls += 1
        if self.failure is not None:
            raise self.failure
        return self.value

    def close(self):
        self.close_calls += 1


class FakeFlowGenerator:
    def __init__(self, transform=None, *, failure=None, **response_kwargs):
        self.transform = transform
        self.failure = failure
        self.response_kwargs = response_kwargs
        self.requests = []
        self.close_calls = 0

    def run_slot(self, request):
        self.requests.append(request)
        if self.failure is not None:
            raise self.failure
        result = response_for_request(request, **self.response_kwargs)
        return result if self.transform is None else self.transform(result)

    def close(self):
        self.close_calls += 1


def controller(
    *,
    flows=3,
    stages=4,
    replicas=2,
    beliefs=UNIFORM,
    max_iterations=2,
    generator=None,
    discovery=None,
    clock=lambda: 0.0,
):
    configuration = GreedyConfiguration(flows, stages, replicas)
    ready = snapshot(configuration)
    return GreedyKernelController(
        controller_configuration=GreedyKernelControllerConfiguration(
            configuration=configuration,
            experiment_id=1,
            root_seed=2050,
            profile_seed=17,
            runtime_profile_fingerprint="fixture-profile-fingerprint",
            max_iterations=max_iterations,
        ),
        discovery=discovery or FakeDiscovery(ready),
        flow_generator=generator or FakeFlowGenerator(),
        initial_beliefs={identity: beliefs for identity in identities(configuration)},
        clock=clock,
    )


def pod(configuration, stage, replica, **changes):
    ownership = DEFAULT_GREEDY_KERNEL_OWNERSHIP
    value = {
        "metadata": {
            "name": f"{ownership.stage_name(stage)}-{replica - 1}",
            "namespace": ownership.namespace,
            "uid": f"uid-{stage}-{replica}",
            "labels": dict(ownership.replica_labels(stage)),
        },
        "spec": {"nodeName": "worker-1"},
        "status": {
            "phase": "Running",
            "conditions": [{"type": "Ready", "status": "True"}],
        },
    }
    for section, update in changes.items():
        value[section].update(update)
    return value


def pod_list(configuration):
    return [
        pod(configuration, stage, replica)
        for stage in configuration.stages
        for replica in configuration.replica_ids
    ]


def discovery_from_items(configuration, items, transport=None):
    def handler(request):
        return httpx.Response(200, request=request, json={"items": items})

    api = GreedyKubernetesApi(
        base_url="https://kubernetes.test",
        token="token",
        verify=False,
        transport=transport or httpx.MockTransport(handler),
    )
    return GreedyKubernetesReplicaDiscovery(api, configuration)


def forwarded_response(payload, host):
    first_stage = int(host.split("-")[2])
    first_ordinal = int(host.split("-")[3])
    selected = (
        {
            "stage": first_stage,
            "replica_id": first_ordinal + 1,
            "url": f"http://{host}/",
            "assigned_load": payload["assigned_load"],
        },
        payload["remaining_hops"][0],
    )
    hops = []
    for item in selected:
        physical = 20.0
        jitter = 2.0
        signal = physical + jitter
        likelihood = latency_model.learning_signal_likelihood(
            signal,
            item["assigned_load"],
        )
        hops.append(
            {
                "slot_id": payload["slot_id"],
                "flow_id": payload["flow_id"],
                "stage": item["stage"],
                "replica_id": item["replica_id"],
                "pod_name": f"greedy-stage-{item['stage']}-{item['replica_id'] - 1}",
                "concurrency": 1,
                "assigned_load": item["assigned_load"],
                "modeled_processing_latency_ms": 19.0,
                "legacy_congestion": item["assigned_load"],
                "processing_latency_ms": physical,
                "observation_jitter_ms": jitter,
                "signal_latency_ms": signal,
                "state_estimate": latency_model.estimate_state(likelihood),
                "state_likelihood": likelihood,
                "legacy_signal": latency_model.estimate_state(likelihood),
                "legacy_likelihood": likelihood,
            }
        )
    second = selected[1]
    return {
        "datapath_mode": "kernel",
        "slot_id": payload["slot_id"],
        "flow_id": payload["flow_id"],
        "elapsed_ms": 10.0,
        "hops": hops,
        "links": [
            {
                "slot_id": payload["slot_id"],
                "flow_id": payload["flow_id"],
                "source_stage": selected[0]["stage"],
                "source_replica_id": selected[0]["replica_id"],
                "source_pod_name": hops[0]["pod_name"],
                "target_stage": second["stage"],
                "target_replica_id": second["replica_id"],
                "target_pod_name": hops[1]["pod_name"],
                "target_endpoint": second["url"],
                "request_latency_ms": 15.0,
                "callee_elapsed_ms": 10.0,
                "link_cost_ms": 5.0,
            }
        ],
    }


def test_arbitrary_k_route_builder_has_exact_two_hops_bypasses_and_final_loads():
    configuration = GreedyConfiguration(3, 5, 2)
    actions = {
        1: TwoStageAction((ReplicaIdentity(1, 1), ReplicaIdentity(5, 1))),
        2: TwoStageAction((ReplicaIdentity(2, 1), ReplicaIdentity(5, 1))),
        3: TwoStageAction((ReplicaIdentity(3, 1), ReplicaIdentity(4, 1))),
    }
    request = build_greedy_kernel_run_slot_request(
        slot_id=7,
        configuration=configuration,
        actions_by_flow=actions,
        discovery=snapshot(configuration),
    )

    assert len(request.routes) == 3
    assert request.selected_assignment_count == 6
    assert tuple(hop.stage for hop in request.routes[0].hops) == (1, 5)
    assert request.routes[0].bypassed_stages == (2, 3, 4)
    assert request.routes[0].hops[0].next_identity == ReplicaIdentity(5, 1)
    assert tuple(hop.assigned_load for hop in request.routes[:2] for hop in hop.hops)[1::2] == (2, 2)
    assert all(
        not set(route.bypassed_stages) & {hop.stage for hop in route.hops}
        for route in request.routes
    )


def test_route_contract_rejects_position_next_hop_stale_load_and_partial_flow():
    configuration = GreedyConfiguration(2, 4, 2)
    request = build_greedy_kernel_run_slot_request(
        slot_id=1,
        configuration=configuration,
        actions_by_flow={
            1: TwoStageAction((ReplicaIdentity(1, 1), ReplicaIdentity(4, 1))),
            2: TwoStageAction((ReplicaIdentity(2, 1), ReplicaIdentity(4, 1))),
        },
        discovery=snapshot(configuration),
    )
    with pytest.raises(ValidationError, match="final load"):
        GreedyKernelRunSlotRequest.model_validate(
            request.model_copy(
                update={
                    "routes": (
                        request.routes[0],
                        request.routes[1].model_copy(
                            update={
                                "hops": (
                                    request.routes[1].hops[0],
                                    request.routes[1].hops[1].model_copy(
                                        update={"assigned_load": 1}
                                    ),
                                )
                            }
                        ),
                    )
                }
            ).model_dump(mode="json")
        )
    with pytest.raises(GreedyKernelContractError, match="every configured flow"):
        build_greedy_kernel_run_slot_request(
            slot_id=1,
            configuration=configuration,
            actions_by_flow={1: request.routes[0].action},
            discovery=snapshot(configuration),
        )
    with pytest.raises(ValidationError, match="next hop"):
        GreedyKernelHopTarget(
            stage=1,
            replica_id=1,
            url="http://s1",
            assigned_load=1,
            route_position=1,
        )


def test_route_executor_runs_one_request_per_flow_concurrently_and_orders_hops():
    configuration = GreedyConfiguration(3, 5, 2)
    request = build_greedy_kernel_run_slot_request(
        slot_id=3,
        configuration=configuration,
        actions_by_flow=actions_for(configuration),
        discovery=snapshot(configuration),
    )
    active = 0
    peak = 0
    calls = []

    async def handler(http_request):
        nonlocal active, peak
        calls.append(http_request)
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        payload = json.loads(http_request.content)
        active -= 1
        return httpx.Response(
            200,
            request=http_request,
            json=forwarded_response(payload, http_request.url.host),
        )

    executor = GreedyKernelRouteExecutor(transport=httpx.MockTransport(handler))
    result = asyncio.run(executor.run_slot(request))

    assert len(calls) == configuration.num_flows
    assert peak == configuration.num_flows
    assert all(call.url.path == "/process-route" for call in calls)
    assert result.observation_count == 2 * configuration.num_flows
    assert result.measured_pair_count == configuration.num_flows
    assert all(tuple(hop.route_position for hop in flow.hops) == (1, 2) for flow in result.flows)
    assert all(flow.hops[0].next_identity == flow.hops[1].identity for flow in result.flows)
    assert executor.ephemeral_fallback_calls == 1
    assert executor.lifecycle.close_calls == 1


def test_route_executor_lifespan_pool_reuse_failure_and_exactly_once_cleanup():
    configuration = GreedyConfiguration(1, 3, 1)
    request = build_greedy_kernel_run_slot_request(
        slot_id=1,
        configuration=configuration,
        actions_by_flow={
            1: TwoStageAction((ReplicaIdentity(1, 1), ReplicaIdentity(3, 1)))
        },
        discovery=snapshot(configuration),
    )
    fail = False
    close_calls = 0

    class Transport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, http_request):
            if fail:
                raise httpx.ConnectError("down", request=http_request)
            payload = json.loads(http_request.content)
            return httpx.Response(
                200,
                request=http_request,
                json=forwarded_response(payload, http_request.url.host),
            )

        async def aclose(self):
            nonlocal close_calls
            close_calls += 1

    async def exercise():
        nonlocal fail
        executor = GreedyKernelRouteExecutor(transport=Transport())
        await executor.start()
        await executor.run_slot(request)
        await executor.run_slot(request.model_copy(update={"slot_id": 2}))
        assert executor.ephemeral_fallback_calls == 0
        fail = True
        with pytest.raises(GreedyKernelRouteExecutionError, match="down"):
            await executor.run_slot(request.model_copy(update={"slot_id": 3}))
        await executor.aclose()
        await executor.aclose()
        return executor

    executor = asyncio.run(exercise())
    assert close_calls == 1
    assert executor.lifecycle.close_calls == 1
    assert executor.is_closed


@pytest.mark.parametrize("timeout", (0, -1, True, float("nan"), float("inf")))
def test_route_executor_rejects_invalid_timeout(timeout):
    with pytest.raises(ValueError, match="finite and positive"):
        GreedyKernelRouteExecutorConfig(request_timeout_seconds=timeout)


def test_flow_generator_lifespan_owns_one_persistent_pool_and_closes_on_start_failure():
    class Executor:
        def __init__(self, fail=False):
            self.fail = fail
            self.start_calls = 0
            self.close_calls = 0

        async def start(self):
            self.start_calls += 1
            if self.fail:
                raise RuntimeError("start failed")

        async def aclose(self):
            self.close_calls += 1

    async def normal():
        executor = Executor()
        app = create_generator_app(executor)
        async with app.router.lifespan_context(app):
            assert executor.start_calls == 1
            assert executor.close_calls == 0
        assert executor.close_calls == 1

    async def failed():
        executor = Executor(fail=True)
        app = create_generator_app(executor)
        with pytest.raises(RuntimeError, match="start failed"):
            async with app.router.lifespan_context(app):
                pass
        assert executor.close_calls == 1

    asyncio.run(normal())
    asyncio.run(failed())


def test_greedy_service_health_and_private_processor_warmup_are_in_process_only():
    processor = create_processor_app(
        ReplicaConfig(stage=2, replica_id=1, pod_name="greedy-stage-2-0"),
        observation_source=lambda _load: 0.001,
        observation_jitter_source=lambda _load: 0.0,
    )

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=processor),
            base_url="http://processor.test",
        ) as client:
            health = await client.get("/health")
            warmup = await client.get("/warmup")
        return health, warmup

    health, warmup = asyncio.run(exercise())
    assert health.status_code == warmup.status_code == 200
    assert health.json()["pod_name"] == warmup.json()["pod_name"] == (
        "greedy-stage-2-0"
    )


def test_forwarder_supports_nonconsecutive_arbitrary_stage_and_separate_clients():
    runtime = GreedyKernelRouteForwarder(
        ForwarderConfig(
            stage=2,
            replica_id=1,
            pod_name="greedy-stage-2-0",
            keepalive_expiry_seconds=GREEDY_KERNEL_DOWNSTREAM_KEEPALIVE_SECONDS,
        )
    )
    request = RouteProcessRequest(
        datapath_mode="kernel",
        slot_id=1,
        flow_id=1,
        assigned_load=1,
        remaining_hops=[
            ForwardHop(stage=7, replica_id=1, url="http://s7", assigned_load=1)
        ],
    )
    runtime._validate_next_hop(request)
    assert runtime.processor_client is not runtime.client
    assert GREEDY_KERNEL_PRIVATE_PROCESSOR_PORT == 8081
    assert GREEDY_KERNEL_PUBLIC_FORWARDER_PORT == 8080
    asyncio.run(runtime.close())
    asyncio.run(runtime.close())
    assert tuple(item.close_calls for item in runtime.client_lifecycles) == (1, 1)


def test_forwarder_propagates_private_processor_and_downstream_failures():
    class Transport(httpx.AsyncBaseTransport):
        def __init__(self, private_failure=False):
            self.private_failure = private_failure

        async def handle_async_request(self, request):
            if request.url.host == "processor":
                if self.private_failure:
                    return httpx.Response(503, request=request, text="private down")
                payload = json.loads(request.content)
                signal = 22.0
                likelihood = latency_model.learning_signal_likelihood(
                    signal, payload["assigned_load"]
                )
                return httpx.Response(
                    200,
                    request=request,
                    json={
                        "slot_id": payload["slot_id"],
                        "flow_id": payload["flow_id"],
                        "stage": 1,
                        "replica_id": 1,
                        "pod_name": "greedy-stage-1-0",
                        "concurrency": 1,
                        "assigned_load": payload["assigned_load"],
                        "modeled_processing_latency_ms": 19.0,
                        "legacy_congestion": payload["assigned_load"],
                        "processing_latency_ms": 20.0,
                        "observation_jitter_ms": 2.0,
                        "signal_latency_ms": signal,
                        "state_estimate": latency_model.estimate_state(likelihood),
                        "state_likelihood": likelihood,
                        "legacy_signal": latency_model.estimate_state(likelihood),
                        "legacy_likelihood": likelihood,
                    },
                )
            return httpx.Response(503, request=request, text="downstream down")

    async def exercise(private_failure):
        runtime = GreedyKernelRouteForwarder(
            ForwarderConfig(
                stage=1,
                replica_id=1,
                pod_name="greedy-stage-1-0",
                processor_url="http://processor",
            ),
            transport=Transport(private_failure),
        )
        request = RouteProcessRequest(
            datapath_mode="kernel",
            slot_id=1,
            flow_id=1,
            assigned_load=1,
            remaining_hops=[
                ForwardHop(stage=3, replica_id=1, url="http://downstream", assigned_load=1)
            ],
        )
        try:
            with pytest.raises(RouteForwardingError, match=("local processing" if private_failure else "forwarding failed")):
                await runtime.process_route(request)
        finally:
            await runtime.close()

    asyncio.run(exercise(True))
    asyncio.run(exercise(False))


def test_discovery_accepts_exact_public_coverage_and_reuses_one_client():
    configuration = GreedyConfiguration(4, 3, 2)
    calls = []
    close_calls = 0

    class Transport(httpx.BaseTransport):
        def handle_request(self, request):
            calls.append(request)
            return httpx.Response(200, request=request, json={"items": pod_list(configuration)})

        def close(self):
            nonlocal close_calls
            close_calls += 1

    discovery = discovery_from_items(configuration, pod_list(configuration), Transport())
    first = discovery.discover_complete_ready()
    second = discovery.discover_complete_ready()
    assert first == second
    assert len(calls) == 2
    assert all(not hasattr(replica, "max_assigned_flows") for replica in first.replicas)
    assert not any(hasattr(replica, "hidden_state") for replica in first.replicas)
    discovery.close()
    discovery.close()
    assert close_calls == 1
    assert discovery.lifecycle.close_calls == 1


@pytest.mark.parametrize(
    ("mutate", "message"),
    (
        (lambda config, items: items[:-1], "coverage mismatch"),
        (lambda config, items: items + [items[0]], "duplicate"),
        (lambda config, items: items[:-1] + [pod(config, 3, 3)], "coverage mismatch"),
        (
            lambda config, items: [
                pod(config, 1, 1, status={"phase": "Pending", "conditions": []})
            ]
            + items[1:],
            "not Running and Ready",
        ),
        (
            lambda config, items: [
                pod(config, 1, 1, metadata={"namespace": "foreign"})
            ]
            + items[1:],
            "foreign namespace",
        ),
        (
            lambda config, items: [
                pod(config, 1, 1, metadata={"name": "malformed"})
            ]
            + items[1:],
            "identity mismatch",
        ),
        (
            lambda config, items: [
                pod(
                    config,
                    1,
                    1,
                    metadata={"labels": {"greedy.stage": "x"}},
                )
            ]
            + items[1:],
            "stage label",
        ),
    ),
)
def test_discovery_rejects_missing_duplicate_unexpected_unready_foreign_and_malformed(
    mutate, message
):
    configuration = GreedyConfiguration(4, 3, 2)
    discovery = discovery_from_items(
        configuration,
        mutate(configuration, pod_list(configuration)),
    )
    try:
        with pytest.raises(GreedyKernelContractError, match=message):
            discovery.discover_complete_ready()
    finally:
        discovery.close()


def test_controller_preserves_sequential_placement_then_one_complete_slot_request():
    generator = FakeFlowGenerator()
    runtime = controller(generator=generator)
    outcome = runtime.run_slot(1, flow_order=(3, 1, 2))

    assert outcome.slot.flow_order == (3, 1, 2)
    assert tuple(item.flow_id for item in outcome.slot.placements) == (3, 1, 2)
    assert len(generator.requests) == 1
    assert tuple(route.flow_id for route in generator.requests[0].routes) == (1, 2, 3)
    assert outcome.controller_to_generator_requests == 1
    assert outcome.selected_route_requests == 3
    assert len(outcome.slot.observations) == 6
    assert len(outcome.slot.measured_pairs) == 3
    assert outcome.slot.final_loads.total_assignments == 6
    assert all(
        observation.assigned_load
        == outcome.slot.final_loads.load_for(observation.identity)
        for observation in outcome.slot.observations
    )
    runtime.close()


def test_controller_document_requires_explicit_dimensions_and_rejects_hidden_fields():
    value = {
        "configuration": {
            "num_flows": 3,
            "num_stages": 4,
            "num_replicas": 2,
        },
        "experiment_id": 1,
        "root_seed": 2050,
        "profile_seed": 17,
        "runtime_profile_fingerprint": "fingerprint",
        "max_iterations": 2,
        "source_identity": "fixture",
        "contract_version": GREEDY_KERNEL_CONTROLLER_INPUT_VERSION,
    }
    document = controller_input_document_from_mapping(value)
    assert document.controller.configuration == GreedyConfiguration(3, 4, 2)
    with pytest.raises(ValueError, match="forbidden fields"):
        controller_input_document_from_mapping({**value, "hidden_state": 4})
    with pytest.raises(ValueError, match="explicit N, K, and M"):
        controller_input_document_from_mapping(
            {**value, "configuration": {"num_flows": 3, "num_stages": 4}}
        )


def _mutate_hop(response, **changes):
    flow = response.flows[0]
    hop = flow.hops[0].model_copy(update=changes)
    changed_flow = flow.model_copy(update={"hops": (hop, flow.hops[1])})
    return response.model_copy(update={"flows": (changed_flow, *response.flows[1:])})


@pytest.mark.parametrize(
    "transform",
    (
        lambda value: value.model_copy(update={"slot_id": value.slot_id + 1}),
        lambda value: value.model_copy(update={"flows": value.flows[:-1]}),
        lambda value: _mutate_hop(value, flow_id=999),
        lambda value: _mutate_hop(value, stage=4),
        lambda value: _mutate_hop(value, replica_id=2),
        lambda value: _mutate_hop(value, assigned_load=999),
        lambda value: _mutate_hop(value, route_position=2),
        lambda value: _mutate_hop(value, next_stage=999),
    ),
)
def test_controller_rejects_every_flow_slot_identity_load_position_next_mismatch(transform):
    runtime = controller(generator=FakeFlowGenerator(transform=transform))
    before = runtime.beliefs
    try:
        with pytest.raises(RuntimeError, match="mismatch|partial"):
            runtime.run_slot(1)
        assert runtime.is_closed
    finally:
        runtime.close()
    assert runtime.beliefs == before


def test_whole_slot_failure_has_no_partial_learning_and_experiment_closes_ports():
    configuration = GreedyConfiguration(2, 3, 2)
    discovery = FakeDiscovery(snapshot(configuration))
    generator = FakeFlowGenerator(failure=RuntimeError("request failed"))
    runtime = controller(
        flows=2,
        stages=3,
        replicas=2,
        discovery=discovery,
        generator=generator,
    )
    before = runtime.beliefs
    with pytest.raises(RuntimeError, match="request failed"):
        runtime.run_experiment()
    assert runtime.beliefs == before
    assert discovery.close_calls == generator.close_calls == 1
    runtime.close()
    assert discovery.close_calls == generator.close_calls == 1


def test_controller_http_clients_persist_across_slots_and_close_once():
    configuration = GreedyConfiguration(1, 2, 1)
    kube_close = 0
    flow_close = 0
    kube_requests = []
    flow_requests = []

    class SyncTransport(httpx.BaseTransport):
        def __init__(self, handler, kind):
            self.handler = handler
            self.kind = kind

        def handle_request(self, request):
            (kube_requests if self.kind == "kube" else flow_requests).append(request)
            return self.handler(request)

        def close(self):
            nonlocal kube_close, flow_close
            if self.kind == "kube":
                kube_close += 1
            else:
                flow_close += 1

    kube_transport = SyncTransport(
        lambda request: httpx.Response(
            200, request=request, json={"items": pod_list(configuration)}
        ),
        "kube",
    )
    api = GreedyKubernetesApi(
        base_url="https://kubernetes.test",
        token="token",
        verify=False,
        transport=kube_transport,
    )
    discovery = GreedyKubernetesReplicaDiscovery(api, configuration)

    def flow_handler(request):
        slot_request = GreedyKernelRunSlotRequest.model_validate_json(request.content)
        return httpx.Response(
            200,
            request=request,
            content=response_for_request(slot_request).model_dump_json(),
            headers={"content-type": "application/json"},
        )

    flow_transport = SyncTransport(flow_handler, "flow")
    generator = GreedyKernelFlowGeneratorHttpClient(
        "http://flow-generator.test",
        transport=flow_transport,
    )
    runtime = controller(
        flows=1,
        stages=2,
        replicas=1,
        beliefs=UNIFORM,
        max_iterations=2,
        discovery=discovery,
        generator=generator,
    )
    runtime.run_experiment()

    assert len(kube_requests) == len(flow_requests) == 2
    assert kube_close == flow_close == 1
    assert api.lifecycle.close_calls == generator.lifecycle.close_calls == 1
    assert runtime.is_closed


def test_partial_http_construction_closes_discovery_client(monkeypatch):
    configuration = GreedyConfiguration(1, 2, 1)
    api = GreedyKubernetesApi(
        base_url="https://kubernetes.test",
        token="token",
        verify=False,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, request=request, json={"items": []})
        ),
    )
    monkeypatch.setattr("Greedy.kernel_controller.GreedyKubernetesApi", lambda **kwargs: api)

    class FailClient:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("construction failed")

    monkeypatch.setattr("Greedy.kernel_controller.GreedyKernelFlowGeneratorHttpClient", FailClient)
    config = GreedyKernelControllerConfiguration(
        configuration=configuration,
        experiment_id=1,
        root_seed=1,
        profile_seed=1,
        runtime_profile_fingerprint="fingerprint",
        max_iterations=1,
    )
    with pytest.raises(RuntimeError, match="construction failed"):
        GreedyKernelController.from_http(
            controller_configuration=config,
            initial_beliefs={identity: UNIFORM for identity in identities(configuration)},
            flow_generator_url="http://flow",
        )
    assert api.lifecycle.close_calls == 1


def test_telemetry_cannot_change_completed_selection_and_learning_is_selected_only():
    first = controller(generator=FakeFlowGenerator(physical_ms=10.0, pair_ms=0.0))
    second = controller(generator=FakeFlowGenerator(physical_ms=30.0, pair_ms=30.0))
    first_outcome = first.run_slot(1, flow_order=(1, 2, 3))
    second_outcome = second.run_slot(1, flow_order=(1, 2, 3))

    assert first_outcome.slot.policy_result == second_outcome.slot.policy_result
    selected = {observation.identity for observation in first_outcome.slot.observations}
    assert all(
        first_outcome.slot.beliefs_before.mapping[identity]
        == first_outcome.slot.beliefs_after.mapping[identity]
        for identity in identities(first_outcome.slot.configuration)
        if identity not in selected
    )
    assert first_outcome.slot.metrics.physical_realized_aggregate_utility != second_outcome.slot.metrics.physical_realized_aggregate_utility
    first.close()
    second.close()


def test_kernel_metrics_keep_physical_utility_pair_reference_and_strict_80ms_sla():
    boundary = controller(
        flows=1,
        stages=2,
        replicas=1,
        generator=FakeFlowGenerator(physical_ms=20.0, pair_ms=40.0),
    )
    above = controller(
        flows=1,
        stages=2,
        replicas=1,
        generator=FakeFlowGenerator(physical_ms=20.0, pair_ms=40.000001),
    )
    boundary_result = boundary.run_slot(1).slot
    above_result = above.run_slot(1).slot

    assert boundary_result.metrics.physical_realized_aggregate_utility == pytest.approx(158.0)
    assert boundary_result.metrics.raw_end_to_end_reference_utility == pytest.approx(118.0)
    assert dict(boundary_result.metrics.raw_end_to_end_latency_ms_per_flow)[1] == pytest.approx(80.0)
    assert boundary_result.metrics.end_to_end_sla_violations == 0
    assert boundary_result.metrics.end_to_end_sla_excess_ms == 0
    assert above_result.metrics.end_to_end_sla_violations == 1
    assert above_result.metrics.end_to_end_sla_excess_ms == pytest.approx(0.000001)
    boundary.close()
    above.close()


def test_belief_continuity_equilibrium_and_exact_iteration_stopping():
    equilibrium = controller(
        flows=1,
        stages=2,
        replicas=1,
        beliefs=FIXED,
        max_iterations=4,
    )
    early = equilibrium.run_experiment()
    assert early.pure_experiment.iterations_completed == 1
    assert early.pure_experiment.reached_equilibrium

    limited = controller(
        flows=1,
        stages=2,
        replicas=1,
        beliefs=UNIFORM,
        max_iterations=2,
    )
    result = limited.run_experiment()
    assert result.pure_experiment.iterations_completed == 2
    assert not result.pure_experiment.reached_equilibrium
    assert result.slots[1].slot.beliefs_before == result.slots[0].slot.beliefs_after


def test_injected_monotonic_timings_cover_all_controller_phases():
    values = itertools.count()
    runtime = controller(clock=lambda: float(next(values)))
    result = runtime.run_slot(1)
    timings = result.phase_timings
    assert (
        timings.discovery_seconds,
        timings.admission_placement_seconds,
        timings.route_dispatch_seconds,
        timings.data_plane_wait_seconds,
        timings.feedback_validation_seconds,
        timings.total_slot_seconds,
    ) == (1, 1, 1, 1, 1, 5)
    assert result.slot.timings.placement_seconds == 1
    assert result.slot.timings.feedback_validation_seconds == 1
    runtime.close()


def test_captured_pure_kernel_replay_matches_without_http_or_redraw():
    runtime = controller()
    outcome = runtime.run_slot(1, flow_order=(2, 1, 3))
    requests_before = len(runtime.flow_generator.requests)
    validation = replay_captured_kernel_slot(capture_greedy_kernel_slot(outcome))

    assert validation.matched
    assert validation.http_requests == validation.stochastic_redraws == 0
    assert len(runtime.flow_generator.requests) == requests_before
    assert validation.replayed_pure_slot.policy_result == outcome.slot.policy_result
    runtime.close()


def test_normal_controller_solves_once_and_cached_uncached_results_match():
    class CountingPolicy(GreedyPolicy):
        def __init__(self, configuration):
            super().__init__(configuration)
            self.calls = 0

        def place(self, **kwargs):
            self.calls += 1
            return super().place(**kwargs)

    configuration = GreedyConfiguration(3, 3, 2)
    policy = CountingPolicy(configuration)
    first = controller(flows=3, stages=3, replicas=2)
    first.policy = policy
    cached = first.run_slot(1, flow_order=(1, 2, 3), use_cache=True)
    assert policy.calls == 1
    assert "kernel_oracle" not in inspect.getsource(GreedyKernelController.run_slot)

    second = controller(flows=3, stages=3, replicas=2)
    uncached = second.run_slot(1, flow_order=(1, 2, 3), use_cache=False)
    assert cached.slot.policy_result == uncached.slot.policy_result
    assert cached.slot.metrics == uncached.slot.metrics
    first.close()
    second.close()


def test_controller_is_deterministic_input_immutable_and_global_rng_neutral():
    random.seed(811)
    np.random.seed(812)
    python_before = random.getstate()
    numpy_before = np.random.get_state()
    first = controller()
    initial = first.beliefs
    first_result = first.run_slot(1, flow_order=(1, 2, 3)).slot
    second = controller()
    second_result = second.run_slot(1, flow_order=(1, 2, 3)).slot

    assert first_result.policy_result == second_result.policy_result
    assert first_result.observations == second_result.observations
    assert initial == first_result.beliefs_before.mapping
    assert random.getstate() == python_before
    numpy_after = np.random.get_state()
    assert numpy_after[0] == numpy_before[0]
    assert np.array_equal(numpy_after[1], numpy_before[1])
    assert numpy_after[2:] == numpy_before[2:]
    first.close()
    second.close()


def test_phase3_source_excludes_hidden_policy_and_output_dependencies():
    service_source = "\n".join(
        (ROOT / "Greedy" / name).read_text()
        for name in (
            "kernel_route_contracts.py",
            "kernel_route_execution.py",
            "kernel_flow_generator.py",
            "kernel_route_forwarder.py",
            "kernel_route_forwarder_service.py",
            "kernel_processor_service.py",
        )
    )
    controller_source = (ROOT / "Greedy" / "kernel_controller.py").read_text()
    for forbidden in (
        "IBG_Hybrid.policy",
        "ProcessPoolExecutor",
        "candidate_pruning",
        "lookahead_executor",
        "monte_carlo",
        "mc_workers",
        "planning_link",
        "--policy",
        "--runs",
        "jsonl",
        "csv.writer",
        "kubectl",
    ):
        assert forbidden not in service_source + controller_source
    assert "hidden_state" not in controller_source
    assert "profile_seed" not in inspect.signature(GreedyPolicy.place).parameters


def test_phase3_comparison_audit_records_matched_http_lifecycle_and_request_shape():
    fixture = CANONICAL_MATCHED_COMPARISON
    assert GREEDY_PHASE3_HYBRID_AUDIT_HEAD == (
        "19229c274038db440f3cfdd62ed2102ea4c2c545"
    )
    assert len(GREEDY_PHASE3_HYBRID_SOURCE_AUDIT) == 15
    assert all(item.git_blob and ":" in item.source_location for item in GREEDY_PHASE3_HYBRID_SOURCE_AUDIT)
    assert {item.disposition for item in GREEDY_PHASE3_HYBRID_SOURCE_AUDIT} == {
        "reuse",
        "adapt",
    }
    assert fixture.matched_value("discovery_http_timeout_seconds") == 10
    assert fixture.matched_value("controller_flow_generator_timeout_seconds") == 30
    assert fixture.matched_value("flow_generator_first_forwarder_timeout_seconds") == 10
    assert fixture.matched_value("public_forwarder_request_timeout_seconds") == 10
    assert fixture.matched_value("controller_generator_requests_per_slot") == 1
    assert fixture.matched_value("first_forwarder_requests_per_slot") == (
        "N-one-per-logical-flow"
    )
    assert fixture.matched_value("selected_hop_records_per_flow") == 2
    assert fixture.matched_value("selected_pair_records_per_flow") == 1
    assert fixture.matched_value("flow_generator_first_forwarder_client_ownership") == (
        "one-persistent-async-asgi-lifespan"
    )


def test_phase3_modules_import_silently_without_files_or_rng_changes(tmp_path):
    modules = (
        "Greedy.kernel_contracts",
        "Greedy.kernel_kubernetes_discovery",
        "Greedy.kernel_route_contracts",
        "Greedy.kernel_route_execution",
        "Greedy.kernel_flow_generator",
        "Greedy.kernel_route_forwarder",
        "Greedy.kernel_route_forwarder_service",
        "Greedy.kernel_processor_service",
        "Greedy.kernel_controller_config",
        "Greedy.kernel_controller",
        "Greedy.kernel_controller_service",
        "Greedy.kernel_oracle",
    )
    code = (
        "import random, numpy as np; random.seed(81); np.random.seed(82); "
        "p=random.getstate(); n=np.random.get_state(); "
        + "; ".join(f"import {module}" for module in modules)
        + "; assert random.getstate()==p; a=np.random.get_state(); "
        "assert a[0]==n[0] and np.array_equal(a[1],n[1]) and a[2:]==n[2:]"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env={"PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == completed.stderr == ""
    assert list(tmp_path.iterdir()) == []
