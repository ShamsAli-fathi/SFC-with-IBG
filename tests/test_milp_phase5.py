import asyncio
import json
import os
from pathlib import Path
import random
import subprocess
import sys
from types import SimpleNamespace
import importlib.util

import httpx
from httpx import MockTransport, Request, Response
import numpy as np
import pytest
from pydantic import ValidationError

from IBG import latency_model as exact_latency
from IBG.report import SLA_v
from MILP.contracts import MILPConfiguration, MILPPlacement, MILPSolverResult, build_problem_input
from MILP.kernel_adapter import (
    MILPKernelAdapterError,
    MILPKubernetesReplicaDiscovery,
    MILPKubernetesTrafficAdapter,
    wait_for_milp_flow_generator,
)
from MILP.kernel_contracts import (
    MILP_PHASE5_KERNEL_CONTRACT_VERSION,
    MILP_TWO_HOP_ROUTE_CONTRACT_VERSION,
    MILPKernelFlowRoute,
    MILPKernelHopTarget,
    MILPKernelMeasuredPairOutcome,
    MILPKernelReplicaEndpoint,
    MILPKernelRunSlotRequest,
    MILPKernelSelectedObservation,
    MILPKernelSlotInput,
    MILPKernelTrafficResult,
)
from MILP.kernel_controller import build_parser as build_kernel_controller_parser
from MILP.kernel_controller import execute_milp_kernel_controller
from MILP.kubernetes_api import MILPKubernetesApi
from MILP.kernel_flow_generator import MILPKernelFlowGenerator
from MILP.kernel_profiles import build_kernel_problem_input, planning_link_costs_from_document
from MILP.kernel_resources import (
    MILP_FORWARDER_RESOURCES,
    MILP_PROCESSOR_RESOURCES,
    build_milp_kernel_runtime_resources,
)
from MILP.kernel_route_forwarder import MILPKernelRouteForwarder
from MILP.kernel_runner import format_milp_kernel_metrics, run_milp_kernel_slot
from MILP.model import exact_known_state_expected_utility
from MILP.phase0_contract import (
    MILPContractError,
    MILPDimensions,
    ReplicaAdmission,
    ReplicaKey,
    SolverResultStatus,
    SolverRunProvenance,
    TwoStageAction,
    reconstruct_social_welfare,
    required_directed_pairs,
)
from MILP.runtime_profiles import (
    MILPRuntimeReplicaProfile,
    milp_runtime_profiles_document,
)
from testbed.route_forwarder import (
    ForwardHop,
    ForwarderConfig,
    ReplicaRouteForwarder,
    RouteForwardingError,
    RouteProcessRequest,
)


ROOT = Path(__file__).resolve().parents[1]


def profile(state=4, capacity=20, seed=100):
    return MILPRuntimeReplicaProfile(
        state=state,
        capacity=capacity,
        delay=25,
        cost=1,
        gamma=0.2,
        base_delay_ms=10,
        congestion_delay_ms=2,
        observation_seed=seed,
    )


def profiles_for(dimensions):
    return {
        (key.stage, key.replica): profile(
            state=((key.stage + key.replica - 2) % 4) + 1,
            capacity=dimensions.flow_count,
            seed=1000 + key.stage * 100 + key.replica,
        )
        for key in dimensions.replica_keys
    }


def endpoints_for(dimensions):
    return tuple(
        MILPKernelReplicaEndpoint(
            key=key,
            pod_name=f"stage-{key.stage}-{key.replica - 1}",
            node_name=f"worker-{key.replica % 2}",
            endpoint=f"http://stage-{key.stage}-{key.replica - 1}",
        )
        for key in dimensions.replica_keys
    )


def link_document(cost=2.0):
    return {
        "contract_version": "milp-planning-links-v1",
        "uniform_cost_ms": cost,
    }


def problem_for(dimensions, cutoff=5.0, planning=2.0):
    configuration = MILPConfiguration(dimensions, cutoff)
    return build_kernel_problem_input(
        configuration,
        profiles=profiles_for(dimensions),
        endpoints=endpoints_for(dimensions),
        planning_link_document=link_document(planning),
    )


def incumbent(problem, actions=None, status=SolverResultStatus.PROVEN_OPTIMAL, bound_delta=0.0):
    dimensions = problem.configuration.dimensions
    if actions is None:
        actions = {
            flow_id: TwoStageAction.canonical(ReplicaKey(1, 1), ReplicaKey(2, 1))
            for flow_id in dimensions.flow_ids
        }
    placement = MILPPlacement.from_actions(dimensions, actions)
    placement.validate_for(problem)
    objective = reconstruct_social_welfare(
        dimensions,
        actions,
        exact_known_state_expected_utility(problem),
        problem.planning_link_costs_ms(),
    )
    value = objective.total_social_welfare_utility
    provenance = SolverRunProvenance(
        status=status,
        requested_cutoff_seconds=problem.configuration.cutoff_seconds,
        model_build_seconds=0.01,
        solve_seconds=0.02,
        backend_name="phase5-fixture",
        backend_version="1",
        termination_reason=status.value,
        incumbent_objective_utility=value,
        best_bound_utility=value + bound_delta,
        absolute_gap_utility=bound_delta,
        relative_gap=bound_delta / max(1.0, abs(value)),
        variable_count=10,
        constraint_count=20,
    )
    return MILPSolverResult(provenance, placement, objective)


def selected_observation(flow_id, key, load, physical=40.0, jitter=8.0):
    signal = physical + jitter
    likelihood = exact_latency.learning_signal_likelihood(signal, load)
    return MILPKernelSelectedObservation(
        flow_id=flow_id,
        key=key,
        assigned_load=load,
        physical_processing_latency_ms=physical,
        observation_jitter_ms=jitter,
        noisy_signal_ms=signal,
        likelihood=likelihood,
        estimated_state=exact_latency.estimate_state(likelihood),
        pod_name=f"stage-{key.stage}-{key.replica - 1}",
        endpoint=f"http://stage-{key.stage}-{key.replica - 1}",
        admitted_concurrency=1,
        modeled_processing_latency_ms=physical - 1,
        request_latency_ms=physical + 3,
        transport_overhead_ms=3,
    )


class CompleteTraffic:
    def __init__(self, pair_ms=7.0, physical=40.0, jitter=8.0):
        self.calls = 0
        self.pair_ms = pair_ms
        self.physical = physical
        self.jitter = jitter

    def execute(self, slot_input, placement):
        self.calls += 1
        loads = dict(placement.final_loads)
        observations = []
        pairs = []
        for flow_id, action in placement.actions:
            observations.extend(
                selected_observation(
                    flow_id,
                    key,
                    loads[key],
                    physical=self.physical,
                    jitter=self.jitter,
                )
                for key in action.selections
            )
            source, target = action.directed_pair
            pairs.append(
                MILPKernelMeasuredPairOutcome(
                    flow_id=flow_id,
                    source=source,
                    target=target,
                    latency_ms=self.pair_ms,
                    source_pod_name=f"stage-{source.stage}-{source.replica - 1}",
                    target_pod_name=f"stage-{target.stage}-{target.replica - 1}",
                    target_endpoint=f"http://stage-{target.stage}-{target.replica - 1}",
                    request_latency_ms=self.pair_ms + 10,
                    callee_elapsed_ms=10,
                )
            )
        return MILPKernelTrafficResult(tuple(observations), tuple(pairs), 2.0)


def kernel_input(dimensions, actions=None):
    problem = problem_for(dimensions)
    return MILPKernelSlotInput(
        problem=problem,
        slot_id=3,
        endpoints=endpoints_for(dimensions),
    ), lambda supplied: incumbent(supplied, actions=actions)


def test_two_hop_contract_accepts_noncontiguous_and_non_stage1_routes():
    request = MILPKernelRunSlotRequest(
        slot_id=1,
        routes=(
            MILPKernelFlowRoute(
                flow_id=1,
                hops=(
                    MILPKernelHopTarget(stage=1, replica_id=1, url="http://s1", assigned_load=1),
                    MILPKernelHopTarget(stage=3, replica_id=1, url="http://s3", assigned_load=1),
                ),
            ),
            MILPKernelFlowRoute(
                flow_id=2,
                hops=(
                    MILPKernelHopTarget(stage=2, replica_id=1, url="http://s2", assigned_load=1),
                    MILPKernelHopTarget(stage=4, replica_id=1, url="http://s4", assigned_load=1),
                ),
            ),
        ),
    )

    assert request.contract_version == MILP_TWO_HOP_ROUTE_CONTRACT_VERSION
    assert [tuple(hop.stage for hop in route.hops) for route in request.routes] == [(1, 3), (2, 4)]


@pytest.mark.parametrize("stages", [(1, 1), (3, 2)])
def test_two_hop_contract_rejects_same_or_reverse_stage_routes(stages):
    with pytest.raises(ValidationError, match="distinct and increasing"):
        MILPKernelFlowRoute(
            flow_id=1,
            hops=(
                MILPKernelHopTarget(stage=stages[0], replica_id=1, url="http://a", assigned_load=1),
                MILPKernelHopTarget(stage=stages[1], replica_id=1, url="http://b", assigned_load=1),
            ),
        )


def test_route_contract_rejects_loads_not_derived_from_complete_placement():
    route = MILPKernelFlowRoute(
        flow_id=1,
        hops=(
            MILPKernelHopTarget(stage=1, replica_id=1, url="http://a", assigned_load=2),
            MILPKernelHopTarget(stage=3, replica_id=1, url="http://b", assigned_load=1),
        ),
    )
    with pytest.raises(ValidationError, match="final loads"):
        MILPKernelRunSlotRequest(slot_id=1, routes=(route,))


def test_request_builder_preserves_k_minus_two_bypass_and_final_loads():
    dimensions = MILPDimensions(flow_count=2, replicas_per_stage=(1, 1, 1, 1))
    actions = {
        1: TwoStageAction.canonical(ReplicaKey(1, 1), ReplicaKey(3, 1)),
        2: TwoStageAction.canonical(ReplicaKey(2, 1), ReplicaKey(4, 1)),
    }
    slot_input, solver = kernel_input(dimensions, actions)
    placement = solver(slot_input.problem).placement

    request = MILPKubernetesTrafficAdapter.build_request(slot_input, placement)

    assert [tuple(hop.stage for hop in route.hops) for route in request.routes] == [(1, 3), (2, 4)]
    assert all(hop.assigned_load == 1 for route in request.routes for hop in route.hops)
    assert sum(len(action.bypassed_stages(dimensions)) for action in actions.values()) == 4


def ready_pod(stage, ordinal, ready=True):
    return {
        "metadata": {"name": f"stage-{stage}-{ordinal}"},
        "spec": {"nodeName": f"worker-{ordinal}"},
        "status": {
            "phase": "Running",
            "conditions": [{"type": "Ready", "status": "True" if ready else "False"}],
        },
    }


def test_ready_discovery_requires_complete_stable_ordinal_identity_set():
    def handler(request: Request):
        stage = int(request.url.params["labelSelector"].split("=")[-1])
        items = [ready_pod(stage, 1), ready_pod(stage, 0)]
        return Response(200, request=request, json={"items": items})

    api = MILPKubernetesApi(
        "milp-testbed",
        base_url="http://kubernetes",
        token="token",
        verify=False,
        transport=MockTransport(handler),
    )
    discovered = MILPKubernetesReplicaDiscovery(api, "milp-testbed").discover_all(
        MILPDimensions(flow_count=1, replicas_per_stage=(2, 2, 2))
    )

    assert tuple(item.key for item in discovered) == tuple(
        ReplicaKey(stage, replica) for stage in (1, 2, 3) for replica in (1, 2)
    )
    assert discovered[0].pod_name == "stage-1-0"
    assert discovered[-1].endpoint.endswith("stage-3.milp-testbed.svc.cluster.local.:8080")


def test_ready_discovery_rejects_incomplete_stage_before_model_construction():
    api = SimpleNamespace(
        list_stage_pods=lambda stage: [ready_pod(stage, 0), ready_pod(stage, 1, ready=False)]
    )
    discovery = MILPKubernetesReplicaDiscovery(api, "milp-testbed")
    with pytest.raises(MILPKernelAdapterError, match="coverage mismatch"):
        discovery.discover_all(MILPDimensions(flow_count=1, replicas_per_stage=(2, 2)))


def test_controller_default_uses_absolute_flow_generator_service_url(monkeypatch):
    monkeypatch.setenv("POD_NAMESPACE", "milp-testbed")

    arguments = build_kernel_controller_parser().parse_args(["--cutoff", "10"])

    assert arguments.flow_generator_url == (
        "http://milp-flow-generator.milp-testbed.svc.cluster.local.:8080"
    )


def test_flow_generator_readiness_uses_absolute_health_url(monkeypatch):
    requested = []

    def healthy_get(url, *, timeout):
        requested.append((url, timeout))
        request = Request("GET", url)
        return Response(
            200,
            request=request,
            json={
                "status": "ok",
                "datapath_mode": "kernel",
                "route_contract_version": MILP_TWO_HOP_ROUTE_CONTRACT_VERSION,
                "flow_generator_version": "milp-kernel-flow-generator-v1",
            },
        )

    monkeypatch.setattr("MILP.kernel_adapter.httpx.get", healthy_get)
    wait_for_milp_flow_generator(
        "http://milp-flow-generator.milp-testbed.svc.cluster.local.:8080/",
        timeout_seconds=0.1,
        poll_seconds=0.0,
    )

    assert requested == [
        (
            "http://milp-flow-generator.milp-testbed.svc.cluster.local.:8080/health",
            5.0,
        )
    ]


def test_flow_generator_readiness_failure_reports_exact_health_url(monkeypatch):
    health_url = (
        "http://milp-flow-generator.milp-testbed.svc.cluster.local.:8080/health"
    )

    def failing_get(url, *, timeout):
        del timeout
        raise httpx.ConnectError("temporary DNS failure", request=Request("GET", url))

    monkeypatch.setattr("MILP.kernel_adapter.httpx.get", failing_get)
    with pytest.raises(MILPKernelAdapterError) as captured:
        wait_for_milp_flow_generator(
            health_url.removesuffix("/health"),
            timeout_seconds=0.001,
            poll_seconds=0.0,
        )

    assert health_url in str(captured.value)
    assert "temporary DNS failure" in str(captured.value)


def test_planning_link_document_expands_completely_and_rejects_partial_explicit_data():
    configuration = MILPConfiguration.uniform(
        flow_count=1,
        stage_count=3,
        replicas_per_stage=2,
        cutoff_seconds=1,
    )
    expanded = planning_link_costs_from_document(link_document(3.5), configuration)
    assert len(expanded) == 12
    assert set(expanded.values()) == {3.5}
    with pytest.raises(MILPContractError, match="mismatch"):
        planning_link_costs_from_document(
            {
                "contract_version": "milp-planning-links-v1",
                "links": [
                    {
                        "source_stage": 1,
                        "source_replica": 1,
                        "target_stage": 2,
                        "target_replica": 1,
                        "cost_ms": 1,
                    }
                ],
            },
            configuration,
        )


def test_kernel_problem_rejects_missing_capacity_profile_before_solver():
    dimensions = MILPDimensions(flow_count=1, replicas_per_stage=(1, 1, 1))
    configuration = MILPConfiguration(dimensions, 1.0)
    incomplete = profiles_for(dimensions)
    incomplete.pop((3, 1))
    with pytest.raises(MILPContractError, match="profile mismatch"):
        build_kernel_problem_input(
            configuration,
            profiles=incomplete,
            endpoints=endpoints_for(dimensions),
            planning_link_document=link_document(),
        )


def test_controller_discovers_before_problem_build_and_invokes_solver_once():
    dimensions = MILPDimensions(flow_count=1, replicas_per_stage=(1, 1, 1))
    configuration = MILPConfiguration(dimensions, 2.5)
    events = []

    class Discovery:
        def discover_all(self, supplied):
            events.append("discover")
            assert supplied == dimensions
            return endpoints_for(dimensions)

    traffic = CompleteTraffic()

    def solve(problem):
        events.append("solve")
        assert events == ["discover", "solve"]
        return incumbent(problem)

    result = execute_milp_kernel_controller(
        configuration,
        slot_id=2,
        profiles=profiles_for(dimensions),
        planning_link_document=link_document(),
        discovery=Discovery(),
        traffic_adapter=traffic,
        solver=solve,
        verify_replay=True,
    )

    assert events == ["discover", "solve"]
    assert traffic.calls == 1
    assert result.configuration.cutoff_seconds == 2.5


def test_complete_placement_precedes_traffic_and_only_selected_outcomes_exist():
    dimensions = MILPDimensions(flow_count=2, replicas_per_stage=(1, 1, 1, 1))
    actions = {
        1: TwoStageAction.canonical(ReplicaKey(1, 1), ReplicaKey(4, 1)),
        2: TwoStageAction.canonical(ReplicaKey(2, 1), ReplicaKey(3, 1)),
    }
    slot_input, solver = kernel_input(dimensions, actions)
    traffic = CompleteTraffic()
    result = run_milp_kernel_slot(slot_input, solver=solver, traffic_adapter=traffic)

    assert result.contract_version == MILP_PHASE5_KERNEL_CONTRACT_VERSION
    assert len(result.placement.actions) == 2
    assert len(result.observations) == 4
    assert len(result.measured_pairs) == 2
    assert sum(load for _key, load in result.final_replica_loads) == 4
    assert {item.key.stage for item in result.observations} == {1, 2, 3, 4}
    assert all(len(stages) == 2 for _flow, stages in result.bypassed_stages_by_flow)


def test_timed_incumbent_executes_and_remains_unproven():
    dimensions = MILPDimensions(flow_count=1, replicas_per_stage=(1, 1))
    slot_input, _ = kernel_input(dimensions)
    result = run_milp_kernel_slot(
        slot_input,
        solver=lambda problem: incumbent(
            problem,
            status=SolverResultStatus.TIME_LIMIT_WITH_INCUMBENT,
            bound_delta=5.0,
        ),
        traffic_adapter=CompleteTraffic(),
    )
    assert result.metrics.common.solver_status is SolverResultStatus.TIME_LIMIT_WITH_INCUMBENT
    assert not result.solver_result.provenance.optimality_proven
    assert result.metrics.common.absolute_gap_utility == 5.0


@pytest.mark.parametrize(
    "status",
    [
        SolverResultStatus.TIME_LIMIT_WITHOUT_INCUMBENT,
        SolverResultStatus.INFEASIBLE,
        SolverResultStatus.UNBOUNDED,
        SolverResultStatus.SOLVER_OR_CONFIGURATION_ERROR,
    ],
)
def test_nonincumbent_status_fails_before_kernel_traffic(status):
    dimensions = MILPDimensions(flow_count=1, replicas_per_stage=(1, 1))
    slot_input, _ = kernel_input(dimensions)
    traffic = CompleteTraffic()
    provenance = SolverRunProvenance(
        status=status,
        requested_cutoff_seconds=slot_input.problem.configuration.cutoff_seconds,
        model_build_seconds=0,
        solve_seconds=0,
        backend_name="fixture",
        backend_version="1",
        termination_reason=status.value,
    )
    with pytest.raises(RuntimeError, match="validated complete incumbent"):
        run_milp_kernel_slot(
            slot_input,
            solver=lambda _problem: MILPSolverResult(provenance),
            traffic_adapter=traffic,
        )
    assert traffic.calls == 0


def test_partial_observation_and_pair_telemetry_fail_explicitly():
    dimensions = MILPDimensions(flow_count=1, replicas_per_stage=(1, 1))
    slot_input, solver = kernel_input(dimensions)
    complete = CompleteTraffic().execute(slot_input, solver(slot_input.problem).placement)

    class Partial:
        def __init__(self, observations, pairs):
            self.value = MILPKernelTrafficResult(observations, pairs, 1.0)

        def execute(self, _input, _placement):
            return self.value

    with pytest.raises(RuntimeError, match="observations"):
        run_milp_kernel_slot(
            slot_input,
            solver=solver,
            traffic_adapter=Partial(complete.observations[:-1], complete.measured_pairs),
        )
    with pytest.raises(RuntimeError, match="pair"):
        run_milp_kernel_slot(
            slot_input,
            solver=solver,
            traffic_adapter=Partial(complete.observations, ()),
        )


def test_kernel_metrics_preserve_hybrid_exact_latency_utility_and_pair_policies():
    dimensions = MILPDimensions(flow_count=2, replicas_per_stage=(1, 1))
    slot_input, solver = kernel_input(dimensions)
    result = run_milp_kernel_slot(
        slot_input,
        solver=solver,
        traffic_adapter=CompleteTraffic(pair_ms=200.0, physical=60.0, jitter=500.0),
    )
    metrics = result.metrics.common
    physical_by_flow = dict(metrics.physical_processing_latency_ms_per_flow)

    assert all(
        item.noisy_signal_ms
        == item.physical_processing_latency_ms + item.observation_jitter_ms
        for item in result.observations
    )
    assert metrics.physical_realized_utility == pytest.approx(
        sum(
            exact_latency.DEFAULT_REWARD
            - item.physical_processing_latency_ms
            - exact_latency.DEFAULT_COST
            for item in result.observations
        )
    )
    assert metrics.physical_only_sla_violations == SLA_v(
        physical_by_flow,
        exact_latency.DEFAULT_SLA_LATENCY_MS,
    )
    assert metrics.measured_pair_latency_ms == 400.0
    assert metrics.solver_configured_planning_link_cost_ms == 4.0
    assert metrics.raw_end_to_end_latency_ms == pytest.approx(
        metrics.physical_processing_latency_ms + metrics.measured_pair_latency_ms
    )
    assert metrics.physical_plus_pair_reference_utility == pytest.approx(
        metrics.physical_realized_utility - metrics.measured_pair_latency_ms
    )


def _forwarder_response(payload):
    hops = []
    selected = [
        {
            "stage": int(payload["entry_stage"]),
            "replica_id": int(payload["entry_replica"]),
            "url": payload["entry_url"],
            "assigned_load": payload["assigned_load"],
        },
        payload["remaining_hops"][0],
    ]
    for hop in selected:
        physical = 20.0 + hop["stage"]
        jitter = 4.0
        signal = physical + jitter
        likelihood = exact_latency.learning_signal_likelihood(signal, hop["assigned_load"])
        hops.append(
            {
                "slot_id": payload["slot_id"],
                "flow_id": payload["flow_id"],
                "stage": hop["stage"],
                "replica_id": hop["replica_id"],
                "pod_name": f"stage-{hop['stage']}-{hop['replica_id'] - 1}",
                "concurrency": 1,
                "assigned_load": hop["assigned_load"],
                "modeled_processing_latency_ms": physical - 1,
                "legacy_congestion": hop["assigned_load"],
                "processing_latency_ms": physical,
                "observation_jitter_ms": jitter,
                "signal_latency_ms": signal,
                "state_estimate": exact_latency.estimate_state(likelihood),
                "state_likelihood": likelihood,
                "legacy_signal": exact_latency.estimate_state(likelihood),
                "legacy_likelihood": likelihood,
            }
        )
    first, second = selected
    return {
        "datapath_mode": "kernel",
        "slot_id": payload["slot_id"],
        "flow_id": payload["flow_id"],
        "elapsed_ms": 42,
        "hops": hops,
        "links": [
            {
                "slot_id": payload["slot_id"],
                "flow_id": payload["flow_id"],
                "source_stage": first["stage"],
                "source_replica_id": first["replica_id"],
                "source_pod_name": hops[0]["pod_name"],
                "target_stage": second["stage"],
                "target_replica_id": second["replica_id"],
                "target_pod_name": hops[1]["pod_name"],
                "target_endpoint": second["url"],
                "request_latency_ms": 15,
                "callee_elapsed_ms": 10,
                "link_cost_ms": 5,
            }
        ],
    }


def test_milp_flow_generator_executes_noncontiguous_routes_concurrently():
    calls = []

    async def handler(request: Request):
        payload = json.loads(request.content)
        host = request.url.host
        parts = host.split("-")
        payload.update(
            entry_stage=parts[1],
            entry_replica=int(parts[2]) + 1,
            entry_url=f"http://{host}",
        )
        calls.append((payload["flow_id"], payload["entry_stage"], payload["remaining_hops"][0]["stage"]))
        await asyncio.sleep(0.01)
        return Response(200, request=request, json=_forwarder_response(payload))

    request = MILPKernelRunSlotRequest(
        slot_id=9,
        routes=(
            MILPKernelFlowRoute(
                flow_id=1,
                hops=(
                    MILPKernelHopTarget(stage=1, replica_id=1, url="http://stage-1-0", assigned_load=1),
                    MILPKernelHopTarget(stage=3, replica_id=1, url="http://stage-3-0", assigned_load=1),
                ),
            ),
            MILPKernelFlowRoute(
                flow_id=2,
                hops=(
                    MILPKernelHopTarget(stage=2, replica_id=1, url="http://stage-2-0", assigned_load=1),
                    MILPKernelHopTarget(stage=3, replica_id=2, url="http://stage-3-1", assigned_load=1),
                ),
            ),
        ),
    )
    response = asyncio.run(
        MILPKernelFlowGenerator(transport=MockTransport(handler)).run_slot(request)
    )

    assert response.slot_id == 9
    assert len(response.flows) == 2
    assert calls == [(1, "1", 3), (2, "2", 3)]
    assert [tuple(hop.stage for hop in flow.hops) for flow in response.flows] == [(1, 3), (2, 3)]
    assert all(flow.measured_pair.link_cost_ms == 5 for flow in response.flows)


def test_kubernetes_traffic_adapter_converts_complete_correlated_two_hop_telemetry():
    dimensions = MILPDimensions(flow_count=1, replicas_per_stage=(1, 1, 1))
    actions = {1: TwoStageAction.canonical(ReplicaKey(1, 1), ReplicaKey(3, 1))}
    slot_input, solver = kernel_input(dimensions, actions)
    placement = solver(slot_input.problem).placement
    request = MILPKubernetesTrafficAdapter.build_request(slot_input, placement)

    async def forwarder(request_value: Request):
        payload = json.loads(request_value.content)
        payload.update(entry_stage=1, entry_replica=1, entry_url="http://stage-1-0")
        return Response(200, request=request_value, json=_forwarder_response(payload))

    generated = asyncio.run(
        MILPKernelFlowGenerator(transport=MockTransport(forwarder)).run_slot(request)
    )

    def flow_generator(request_value: Request):
        posted = MILPKernelRunSlotRequest.model_validate(json.loads(request_value.content))
        assert posted == request
        return Response(
            200,
            request=request_value,
            json=generated.model_dump(mode="json"),
        )

    traffic = MILPKubernetesTrafficAdapter(
        "http://milp-flow-generator",
        transport=MockTransport(flow_generator),
    ).execute(slot_input, placement)

    assert len(traffic.observations) == 2
    assert [item.key.stage for item in traffic.observations] == [1, 3]
    assert all(item.assigned_load == 1 for item in traffic.observations)
    assert len(traffic.measured_pairs) == 1
    assert traffic.measured_pairs[0].source == ReplicaKey(1, 1)
    assert traffic.measured_pairs[0].target == ReplicaKey(3, 1)
    assert traffic.measured_pairs[0].latency_ms == 5.0
    assert not hasattr(traffic.observations[0], "true_state")


def test_kernel_imports_are_silent_file_safe_and_global_rng_neutral(tmp_path):
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT)
    code = (
        "import importlib, random, numpy as np; "
        "random.seed(81); np.random.seed(82); p=random.getstate(); n=np.random.get_state(); "
        "[importlib.import_module(x) for x in "
        "('MILP.kernel_contracts','MILP.kernel_profiles','MILP.kernel_adapter',"
        "'MILP.kernel_runner','MILP.kernel_controller','MILP.kernel_flow_generator')]; "
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
    assert tuple(tmp_path.iterdir()) == ()


def test_pure_kernel_runner_is_silent_and_formatter_is_one_compact_line(capsys):
    dimensions = MILPDimensions(flow_count=1, replicas_per_stage=(1, 1))
    slot_input, solver = kernel_input(dimensions)
    result = run_milp_kernel_slot(
        slot_input,
        solver=solver,
        traffic_adapter=CompleteTraffic(),
    )
    assert capsys.readouterr().out == ""
    line = format_milp_kernel_metrics(result)
    assert "\n" not in line
    assert line.startswith("MILP-Kernel scale=1x2x1 slot=3 cutoff=5s")
    assert "status=proven-optimal optimal=1" in line
    assert "routes=1 observations=2 pairs=1" in line
    assert "expected-stage=" in line
    assert "planning=" in line
    assert "physical-ms=" in line
    assert "measured-pair-ms=" in line


def test_default_15x3x10_kernel_boundary_has_exact_counts_with_supplied_incumbent():
    dimensions = MILPDimensions()
    slot_input, solver = kernel_input(dimensions)
    result = run_milp_kernel_slot(
        slot_input,
        solver=solver,
        traffic_adapter=CompleteTraffic(),
    )
    assert len(result.placement.actions) == 15
    assert len(result.observations) == 30
    assert len(result.measured_pairs) == 15
    assert sum(load for _key, load in result.final_replica_loads) == 30
    assert all(len(stages) == 1 for _flow, stages in result.bypassed_stages_by_flow)


def test_kernel_modules_do_not_import_hybrid_algorithm_code():
    kernel_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "MILP").glob("kernel_*.py")
    )
    assert "IBG_Hybrid" not in kernel_sources
    assert "lookahead" not in kernel_sources.lower()
    assert "monte_carlo" not in kernel_sources.lower()


def test_milp_forwarder_accepts_one_strictly_later_selected_stage():
    runtime = MILPKernelRouteForwarder(
        ForwarderConfig(stage=1, replica_id=1, pod_name="stage-1-0")
    )
    noncontiguous = RouteProcessRequest(
        datapath_mode="kernel",
        slot_id=1,
        flow_id=1,
        assigned_load=1,
        remaining_hops=[
            ForwardHop(stage=3, replica_id=1, url="http://stage-3-0", assigned_load=1)
        ],
    )
    runtime._validate_next_hop(noncontiguous)

    reverse = noncontiguous.model_copy(
        update={
            "remaining_hops": [
                ForwardHop(stage=1, replica_id=2, url="http://stage-1-1", assigned_load=1)
            ]
        }
    )
    with pytest.raises(RouteForwardingError, match="strictly later"):
        runtime._validate_next_hop(reverse)
    asyncio.run(runtime.close())


def test_exact_forwarder_still_rejects_noncontiguous_selected_stage():
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


def test_isolated_runtime_owns_milp_resource_shape_and_forwarder():
    dimensions = MILPDimensions(flow_count=1, replicas_per_stage=(2, 2, 2))
    resources = build_milp_kernel_runtime_resources(
        profiles_for(dimensions),
        num_of_stages=3,
        num_of_replicas=2,
        namespace="milp-testbed",
        image="milp-testbed:kernel-service-phase5",
    )
    statefulsets = [
        item for item in resources["items"] if item["kind"] == "StatefulSet"
    ]
    assert len(statefulsets) == 3
    config_map = next(item for item in resources["items"] if item["kind"] == "ConfigMap")
    assert config_map["metadata"]["name"] == "milp-replica-profiles"
    assert statefulsets[0]["metadata"]["labels"]["app.kubernetes.io/name"] == "milp-replica"
    assert statefulsets[0]["spec"]["template"]["metadata"]["annotations"][
        "milp.route-contract-version"
    ] == MILP_TWO_HOP_ROUTE_CONTRACT_VERSION
    assert "milp.profile-hash" not in statefulsets[0]["spec"]["template"]["metadata"]["annotations"]
    pod = statefulsets[0]["spec"]["template"]["spec"]
    processor, forwarder = pod["containers"]
    assert processor["command"][-1] == "8081"
    assert {item["name"]: item.get("value") for item in processor["env"]}["REPLICA_PROFILES_PATH"] == "/etc/milp/profiles.json"
    assert "--workers" not in processor["command"]
    assert processor["resources"] == {
        "requests": {"cpu": "50m", "memory": "64Mi"},
        "limits": {"cpu": "1", "memory": "256Mi"},
    }
    assert processor["resources"] == MILP_PROCESSOR_RESOURCES
    assert forwarder["command"][-4:] == [
        "--workers",
        "2",
        "--timeout-keep-alive",
        "30",
    ]
    assert "MILP.kernel_route_forwarder:app" in forwarder["command"]
    assert "testbed.route_forwarder:app" not in forwarder["command"]
    assert forwarder["resources"] == {
        "requests": {"cpu": "25m", "memory": "128Mi"},
        "limits": {"cpu": "1", "memory": "256Mi"},
    }
    assert forwarder["resources"] == MILP_FORWARDER_RESOURCES
    assert {item["name"]: item.get("value") for item in forwarder["env"]}[
        "FORWARDER_KEEPALIVE_SECONDS"
    ] == "30"
    assert "initContainers" not in pod


def test_milp_resource_and_discovery_boundaries_do_not_import_exact_deployment_helpers():
    resource_source = (ROOT / "MILP/kernel_resources.py").read_text(encoding="utf-8")
    discovery_source = (ROOT / "MILP/kubernetes_api.py").read_text(encoding="utf-8")
    runtime_profile_source = (ROOT / "MILP/runtime_profiles.py").read_text(encoding="utf-8")
    combined = resource_source + discovery_source + runtime_profile_source
    assert "testbed.kubernetes_resources" not in combined
    assert "testbed.kubernetes_adapters" not in combined
    assert "testbed.profiles" not in combined


def test_milp_kernel_launcher_keeps_runtime_dimensions_cutoff_and_verbose_explicit():
    path = ROOT / "scripts/run_milp_kernel.py"
    spec = importlib.util.spec_from_file_location("run_milp_kernel", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    arguments = module.build_parser().parse_args(
        [
            "--flow",
            "4",
            "--stage",
            "5",
            "--replica",
            "6",
            "--cutoff",
            "12.5",
            "--planning-link-ms",
            "2.75",
            "--rollout-batch-size",
            "3",
            "--verbose",
        ]
    )
    job = module._controller_job(arguments, "fixture-job")
    controller = job["spec"]["template"]["spec"]["containers"][0]
    assert controller["args"] == [
        "--flow",
        "4",
        "--stage",
        "5",
        "--replica",
        "6",
        "--cutoff",
        "12.5",
        "--slot-id",
        "1",
        "--verbose",
    ]
    assert controller["image"] == "milp-testbed:kernel-controller-phase5"
    assert job["metadata"]["namespace"] == "milp-testbed"
    preflight = module._preflight_lines(arguments)
    assert preflight[:3] == (
        "requested scale=4 flows x 5 stages x 6 replicas/stage; L=2",
        "topology=30 replica Pods / 60 containers / about 90 serving Uvicorn workers",
        "solver cutoff=12.5s planning-link=2.75ms slot=1",
    )
    assert "capacity notice" in preflight[-1]
    assert arguments.rollout_batch_size == 3
    default_arguments = module.build_parser().parse_args(
        ["--cutoff", "5", "--planning-link-ms", "2"]
    )
    assert default_arguments.rollout_batch_size == 2


@pytest.mark.parametrize(
    ("replicas", "batch_size", "expected"),
    [
        (1, 2, (1,)),
        (2, 2, (2,)),
        (3, 2, (2, 3)),
        (6, 2, (2, 4, 6)),
        (10, 2, (2, 4, 6, 8, 10)),
        (7, 3, (3, 6, 7)),
    ],
)
def test_milp_kernel_rollout_batch_targets_are_bounded_and_deterministic(
    replicas, batch_size, expected
):
    path = ROOT / "scripts/run_milp_kernel.py"
    spec = importlib.util.spec_from_file_location("run_milp_kernel_batches", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.rollout_batch_targets(replicas, batch_size) == expected


@pytest.mark.parametrize(
    ("existing", "target", "batch_size", "expected"),
    [
        (3, 6, 2, (3, 5, 6)),
        (2, 6, 2, (2, 4, 6)),
        (6, 6, 2, (6,)),
        (6, 3, 2, (3,)),
        (0, 6, 2, (2, 4, 6)),
    ],
)
def test_milp_kernel_rollout_preserves_existing_replicas_on_scale_up(
    existing, target, batch_size, expected
):
    path = ROOT / "scripts/run_milp_kernel.py"
    spec = importlib.util.spec_from_file_location("run_milp_kernel_existing_batches", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.rollout_batch_targets(target, batch_size, existing) == expected


@pytest.mark.parametrize("batch_size", ["0", "-1", "not-an-integer"])
def test_milp_kernel_launcher_rejects_invalid_rollout_batch_sizes(batch_size):
    path = ROOT / "scripts/run_milp_kernel.py"
    spec = importlib.util.spec_from_file_location("run_milp_kernel_invalid_batches", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(SystemExit):
        module.build_parser().parse_args(
            [
                "--cutoff",
                "5",
                "--planning-link-ms",
                "2",
                "--rollout-batch-size",
                batch_size,
            ]
        )


def test_milp_kernel_launcher_scales_and_waits_every_batch_before_the_next(monkeypatch):
    path = ROOT / "scripts/run_milp_kernel.py"
    spec = importlib.util.spec_from_file_location("run_milp_kernel_rollout", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    args = module.build_parser().parse_args(
        [
            "--flow",
            "1",
            "--stage",
            "3",
            "--replica",
            "3",
            "--cutoff",
            "5",
            "--planning-link-ms",
            "2",
            "--rollout-batch-size",
            "2",
        ]
    )
    calls = []

    def fake_run(command, **_kwargs):
        calls.append((command, _kwargs))
        if command[3:5] == ["get", "statefulset/stage-1"]:
            return SimpleNamespace(stdout="")
        if command[3:5] == ["get", "statefulset/stage-2"]:
            return SimpleNamespace(stdout="")
        if command[3:5] == ["get", "statefulset/stage-3"]:
            return SimpleNamespace(stdout="")
        return SimpleNamespace(stdout="NAME READY DESIRED\n")

    monkeypatch.setattr(module, "_run", fake_run)
    monkeypatch.setattr(module, "_announce", lambda _message: None)
    profile, profiles = module.build_launcher_experiment_profile(args)
    module._apply_long_running("kind-ibg", args, profile, profiles)

    commands = [command for command, _kwargs in calls]
    resource_manifest = next(
        json.loads(kwargs["input_text"])
        for command, kwargs in calls
        if command[-1] == "-" and '"kind": "List"' in kwargs.get("input_text", "")
    )
    assert {
        item["spec"]["replicas"]
        for item in resource_manifest["items"]
        if item["kind"] == "StatefulSet"
    } == {2}
    scale_commands = [command for command in commands if "scale" in command]
    assert scale_commands == [
        [
            "kubectl", "--context", "kind-ibg", "scale", "statefulset/stage-1",
            "--namespace", "milp-testbed", "--replicas=3",
        ],
        [
            "kubectl", "--context", "kind-ibg", "scale", "statefulset/stage-2",
            "--namespace", "milp-testbed", "--replicas=3",
        ],
        [
            "kubectl", "--context", "kind-ibg", "scale", "statefulset/stage-3",
            "--namespace", "milp-testbed", "--replicas=3",
        ],
    ]
    wait_commands = [command for command in commands if "rollout" in command]
    assert [command[5] for command in wait_commands] == [
        "statefulset/stage-1",
        "statefulset/stage-2",
        "statefulset/stage-3",
        "statefulset/stage-1",
        "statefulset/stage-2",
        "statefulset/stage-3",
        "deployment/milp-flow-generator",
    ]
    scale_indices = [index for index, command in enumerate(commands) if "scale" in command]
    wait_indices = [index for index, command in enumerate(commands) if "rollout" in command]
    assert scale_indices[0] > wait_indices[2]
    assert scale_indices[-1] < wait_indices[3]


def test_milp_kernel_launcher_adds_only_missing_replicas_to_an_existing_scale(monkeypatch):
    path = ROOT / "scripts/run_milp_kernel.py"
    spec = importlib.util.spec_from_file_location("run_milp_kernel_existing_rollout", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    args = module.build_parser().parse_args(
        [
            "--flow", "1", "--stage", "3", "--replica", "6", "--cutoff", "5",
            "--planning-link-ms", "2", "--rollout-batch-size", "2",
        ]
    )
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        if command[3] == "get" and command[4].startswith("statefulset/stage-"):
            return SimpleNamespace(stdout="3")
        if command[3] == "get" and command[4] == "configmap/milp-replica-profiles":
            return SimpleNamespace(stdout=json.dumps(milp_runtime_profiles_document(profiles)))
        return SimpleNamespace(stdout="NAME READY DESIRED\n")

    monkeypatch.setattr(module, "_run", fake_run)
    monkeypatch.setattr(module, "_announce", lambda _message: None)
    profile, profiles = module.build_launcher_experiment_profile(args)
    module._apply_long_running("kind-ibg", args, profile, profiles)

    resource_manifest = next(
        json.loads(kwargs["input_text"])
        for command, kwargs in calls
        if command[-1] == "-" and '"kind": "List"' in kwargs.get("input_text", "")
    )
    assert {
        item["spec"]["replicas"]
        for item in resource_manifest["items"]
        if item["kind"] == "StatefulSet"
    } == {3}
    scale_targets = [
        command[-1]
        for command, _kwargs in calls
        if "scale" in command
    ]
    assert scale_targets == [
        "--replicas=5", "--replicas=5", "--replicas=5",
        "--replicas=6", "--replicas=6", "--replicas=6",
    ]


def test_milp_kernel_launcher_rejects_existing_runtime_profile_drift(monkeypatch):
    path = ROOT / "scripts/run_milp_kernel.py"
    spec = importlib.util.spec_from_file_location("run_milp_kernel_profile_drift", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    args = module.build_parser().parse_args(
        ["--flow", "1", "--stage", "3", "--replica", "4", "--cutoff", "5", "--planning-link-ms", "2"]
    )
    experiment_profile, profiles = module.build_launcher_experiment_profile(args)
    stale_profiles = dict(profiles)
    stale_profiles[(1, 1)] = profile(state=1)

    def fake_run(command, **_kwargs):
        if command[3] == "get" and command[4].startswith("statefulset/stage-"):
            return SimpleNamespace(stdout="3")
        if command[3] == "get" and command[4] == "configmap/milp-replica-profiles":
            return SimpleNamespace(
                stdout=json.dumps(milp_runtime_profiles_document(stale_profiles))
            )
        return SimpleNamespace(stdout="NAME READY DESIRED\n")

    monkeypatch.setattr(module, "_run", fake_run)
    with pytest.raises(RuntimeError, match="would change the runtime profile"):
        module._apply_long_running("kind-ibg", args, experiment_profile, profiles)


def test_milp_service_image_excludes_controller_solver_dependencies():
    service = (ROOT / "deploy/milp-kubernetes/Dockerfile.service").read_text(
        encoding="utf-8"
    )
    controller = (ROOT / "deploy/milp-kubernetes/Dockerfile.controller").read_text(
        encoding="utf-8"
    )
    requirements = (
        ROOT / "deploy/milp-kubernetes/requirements-service.txt"
    ).read_text(encoding="utf-8")

    assert "requirements-runtime.txt" not in service
    assert "scipy" not in requirements.lower()
    assert "pandas" not in requirements.lower()
    assert "scipy==1.18.0" in controller
    assert "service_package_init.py" in service
