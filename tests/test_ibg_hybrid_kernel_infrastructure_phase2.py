import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys

from httpx import (
    ASGITransport,
    AsyncClient,
    HTTPStatusError,
    MockTransport,
    Request,
    Response,
)
import pytest

from IBG import latency_model as exact_latency
from IBG_Hybrid.contracts import HybridConfiguration, ReplicaChoice
from IBG_Hybrid.kernel_controller import (
    HYBRID_KERNEL_OBSERVATION_PROVENANCE_VERSION,
    HybridKernelControllerAdapter,
    HybridKernelFlowGeneratorHttpClient,
)
from IBG_Hybrid.control_plane_footprint import (
    HYBRID_CONTROL_PLANE_DATA_SCHEMA,
    HybridControlPlaneDataMeter,
)
from IBG_Hybrid.kernel_controller_config import (
    controller_input_document_from_mapping,
    load_controller_input_document,
)
from IBG_Hybrid.kernel_flow_generator import create_app
from IBG_Hybrid.kernel_infrastructure_contract import (
    DEFAULT_HYBRID_KERNEL_OWNERSHIP,
    HybridKernelContractError,
    HybridKernelDiscoveredReplica,
    HybridKernelDiscoverySnapshot,
)
from IBG_Hybrid.kernel_kubernetes_discovery import (
    HybridKubernetesApi,
    HybridKubernetesReplicaDiscovery,
)
from IBG_Hybrid.kernel_processor_service import processor_config_from_env
from IBG_Hybrid.kernel_route_contracts import (
    HybridKernelFlowTelemetry,
    HybridKernelHopTelemetry,
    HybridKernelRunSlotRequest,
    HybridKernelRunSlotResponse,
)
from IBG_Hybrid.kernel_runtime_profiles import load_runtime_profile_document
from testbed.route_forwarder import PairwiseLinkTelemetry


ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy" / "hybrid-kubernetes"


class CountingTransport:
    def __init__(self, handler):
        self.handler = handler
        self.requests = []
        self.close_calls = 0

    def handle_request(self, request):
        self.requests.append(request)
        return self.handler(request)

    def close(self):
        self.close_calls += 1


def pod(stage, replica, **changes):
    ownership = DEFAULT_HYBRID_KERNEL_OWNERSHIP
    value = {
        "metadata": {
            "name": f"{ownership.stage_name(stage)}-{replica - 1}",
            "namespace": ownership.namespace,
            "uid": f"uid-{stage}-{replica}",
            "labels": dict(ownership.replica_labels(stage)),
        },
        "spec": {"nodeName": f"worker-{replica % 2}"},
        "status": {
            "phase": "Running",
            "conditions": [{"type": "Ready", "status": "True"}],
        },
    }
    for section, section_changes in changes.items():
        value[section].update(section_changes)
    return value


def pod_list(config):
    return [
        pod(stage, replica)
        for stage in range(1, config.num_stages + 1)
        for replica in range(1, config.num_replicas + 1)
    ]


def discovery_from_items(config, items, calls=None):
    def handler(request: Request):
        if calls is not None:
            calls.append(request)
        return Response(200, request=request, json={"items": items})

    api = HybridKubernetesApi(
        base_url="https://kubernetes.test",
        token="token",
        verify=False,
        transport=MockTransport(handler),
    )
    return HybridKubernetesReplicaDiscovery(api, config)


def snapshot(config):
    ownership = DEFAULT_HYBRID_KERNEL_OWNERSHIP
    return HybridKernelDiscoverySnapshot(
        config,
        tuple(
            HybridKernelDiscoveredReplica(
                choice=ReplicaChoice(stage, replica),
                namespace=ownership.namespace,
                pod_name=f"{ownership.stage_name(stage)}-{replica - 1}",
                pod_uid=f"uid-{stage}-{replica}",
                endpoint=(
                    f"http://{ownership.stage_name(stage)}-{replica - 1}."
                    f"{ownership.stage_name(stage)}.{ownership.namespace}."
                    "svc.cluster.local.:8080"
                ),
                labels=ownership.replica_labels(stage),
                node_name="worker-1",
            )
            for stage in range(1, config.num_stages + 1)
            for replica in range(1, config.num_replicas + 1)
        ),
    )


def small_controller_inputs():
    return controller_input_document_from_mapping(
        {
            "contract_version": "ibg-hybrid-kernel-controller-inputs-v1",
            "source_identity": "phase2-controller-test-v1",
            "configuration": {
                "num_flows": 2,
                "num_stages": 3,
                "num_replicas": 1,
                "stage_budget": 2,
            },
            "admission": [
                {"stage": stage, "replica": 1, "max_assigned_flows": 2}
                for stage in (1, 2, 3)
            ],
            "planning_pair_links": [
                {
                    "source_stage": source,
                    "source_replica": 1,
                    "target_stage": target,
                    "target_replica": 1,
                    "latency_ms": 0.25 * (target - source),
                }
                for source, target in ((1, 2), (1, 3), (2, 3))
            ],
        }
    )


def response_for_request(request):
    replica_count = max(
        hop.replica_id for route in request.routes for hop in route.hops
    )
    discovered = snapshot(
        HybridConfiguration(
            num_flows=len(request.routes),
            num_replicas=replica_count,
        )
    ).replica_by_choice()
    flows = []
    for route in request.routes:
        hops = []
        for target in route.hops:
            physical = 20.0 + target.stage
            jitter = 4.0
            signal = physical + jitter
            likelihood = exact_latency.learning_signal_likelihood(
                signal,
                target.assigned_load,
            )
            identity = discovered[target.choice]
            hops.append(
                HybridKernelHopTelemetry(
                    slot_id=request.slot_id,
                    flow_id=route.flow_id,
                    stage=target.stage,
                    replica_id=target.replica_id,
                    pod_name=identity.pod_name,
                    endpoint=str(target.url),
                    concurrency=1,
                    assigned_load=target.assigned_load,
                    modeled_processing_latency_ms=physical - 1.0,
                    physical_processing_latency_ms=physical,
                    observation_jitter_ms=jitter,
                    learning_signal_ms=signal,
                    request_latency_ms=30.0,
                    transport_overhead_ms=5.0,
                    estimated_state=exact_latency.estimate_state(likelihood),
                    likelihood=likelihood,
                )
            )
        first, second = hops
        pair = PairwiseLinkTelemetry(
            slot_id=request.slot_id,
            flow_id=route.flow_id,
            source_stage=first.stage,
            source_replica_id=first.replica_id,
            source_pod_name=first.pod_name,
            target_stage=second.stage,
            target_replica_id=second.replica_id,
            target_pod_name=second.pod_name,
            target_endpoint=second.endpoint,
            request_latency_ms=15.0,
            callee_elapsed_ms=10.0,
            link_cost_ms=5.0,
        )
        flows.append(
            HybridKernelFlowTelemetry(
                flow_id=route.flow_id,
                skipped_stage=route.skipped_stage,
                hops=tuple(hops),
                measured_pair=pair,
                ingress_request_latency_ms=30.0,
                ingress_overhead_ms=5.0,
            )
        )
    return HybridKernelRunSlotResponse(
        slot_id=request.slot_id,
        elapsed_ms=30.0,
        flows=tuple(flows),
    )


class FakeExecutor:
    def __init__(self):
        self.requests = []

    async def run_slot(self, request):
        self.requests.append(request)
        return response_for_request(request)


class LifecycleExecutor(FakeExecutor):
    def __init__(self):
        super().__init__()
        self.start_calls = 0
        self.close_calls = 0

    async def start(self):
        self.start_calls += 1

    async def aclose(self):
        self.close_calls += 1


class FakeDiscovery:
    def __init__(self, value):
        self.value = value
        self.calls = 0

    def wait_for_complete_ready(self, **kwargs):
        self.calls += 1
        return self.value


class FakeFlowGenerator:
    def __init__(self, *, partial=False):
        self.requests = []
        self.partial = partial

    def run_slot(self, request):
        self.requests.append(request)
        response = response_for_request(request)
        if self.partial:
            return response.model_copy(update={"flows": response.flows[:-1]})
        return response


def test_runtime_and_controller_documents_are_complete_and_information_isolated():
    runtime = load_runtime_profile_document(DEPLOY / "runtime-profiles.json")
    controller = load_controller_input_document(DEPLOY / "controller-inputs.json")

    assert runtime.configuration == controller.configuration
    assert len(runtime.profiles) == 6
    assert len(controller.admission) == 6
    assert len(controller.planning_pair_links) == 12
    runtime_text = (DEPLOY / "runtime-profiles.json").read_text()
    controller_text = (DEPLOY / "controller-inputs.json").read_text()
    assert "belief" not in runtime_text
    assert "max_assigned_flows" not in runtime_text
    assert "planning_pair_links" not in runtime_text
    assert "hidden_state" not in controller_text
    assert "observation_seed" not in controller_text
    assert "belief" not in controller_text


def test_processor_reads_only_hidden_state_and_observation_seed_from_profile():
    config = processor_config_from_env(
        {
            "STAGE": "2",
            "POD_NAME": "hybrid-stage-2-1",
            "HYBRID_RUNTIME_PROFILES_PATH": str(
                DEPLOY / "runtime-profiles.json"
            ),
        }
    )

    assert (config.stage, config.replica_id, config.state) == (2, 2, 1)
    assert config.observation_seed == 1202
    assert config.capacity == 1


def test_manifests_are_hybrid_owned_narrow_and_preserve_runtime_resources():
    manifest_text = "\n".join(
        path.read_text() for path in sorted(DEPLOY.glob("*.yaml"))
    )
    rbac = (DEPLOY / "rbac.yaml").read_text()
    replicas = (DEPLOY / "replicas.yaml").read_text()
    controller = (DEPLOY / "controller-job.yaml").read_text()

    assert "namespace: ibg-hybrid-testbed" in manifest_text
    assert "milp-testbed" not in manifest_text
    assert "app.kubernetes.io/name: ibg-replica" not in manifest_text
    assert 'resources: ["pods"]' in rbac
    assert 'verbs: ["get", "list"]' in rbac
    assert "ClusterRole" not in rbac and "secrets" not in rbac
    assert "ibg-hybrid-testbed:kernel-service-v1" in replicas
    assert "ibg-hybrid-testbed:kernel-controller-v1" in controller
    assert '"--workers", "2"' in replicas
    assert '"--timeout-keep-alive", "30"' in replicas
    assert "requests: {cpu: 50m, memory: 128Mi}" in replicas
    assert 'limits: {cpu: "1", memory: 768Mi}' in replicas
    assert "requests: {cpu: 25m, memory: 128Mi}" in replicas
    assert 'limits: {cpu: "1", memory: 256Mi}' in replicas
    assert "64Mi" not in replicas
    assert "ibg-hybrid-runtime-profiles" not in controller


def test_kubernetes_discovery_uses_hybrid_selector_and_exact_ready_coverage():
    config = HybridConfiguration(num_flows=4, num_replicas=2)
    calls = []
    discovery = discovery_from_items(config, pod_list(config), calls)

    accepted = discovery.discover_complete_ready()

    assert len(accepted.replicas) == 6
    assert calls[0].url.path == (
        "/api/v1/namespaces/ibg-hybrid-testbed/pods"
    )
    selector = calls[0].url.params["labelSelector"]
    assert "app.kubernetes.io/name=ibg-hybrid-replica" in selector
    assert "app.kubernetes.io/part-of=ibg-hybrid-testbed" in selector


@pytest.mark.parametrize(
    ("mutate", "message"),
    (
        (lambda values: values[:-1], "coverage mismatch"),
        (lambda values: values + [values[0]], "duplicate replica"),
        (
            lambda values: values[:-1] + [pod(3, 3)],
            "coverage mismatch",
        ),
        (
            lambda values: [
                pod(1, 1, metadata={"namespace": "ibg-testbed"})
            ]
            + values[1:],
            "foreign namespace",
        ),
        (
            lambda values: [
                pod(1, 1, status={"phase": "Pending", "conditions": []})
            ]
            + values[1:],
            "not Running and Ready",
        ),
        (
            lambda values: [
                pod(1, 1, metadata={"labels": {"ibg-hybrid.stage": "1"}})
            ]
            + values[1:],
            "labels",
        ),
        (
            lambda values: [
                pod(1, 1, metadata={"name": "hybrid-stage-2-0"})
            ]
            + values[1:],
            "identity mismatch",
        ),
    ),
)
def test_kubernetes_discovery_rejects_every_incomplete_or_foreign_case(
    mutate,
    message,
):
    config = HybridConfiguration(num_flows=4, num_replicas=2)
    discovery = discovery_from_items(config, mutate(pod_list(config)))
    with pytest.raises(HybridKernelContractError, match=message):
        discovery.discover_complete_ready()


def test_hybrid_http_boundary_accepts_both_route_shapes_and_rejects_exact_shape():
    executor = FakeExecutor()
    application = create_app(executor)
    request = HybridKernelRunSlotRequest(
        slot_id=1,
        routes=(
            {
                "flow_id": 1,
                "hops": (
                    {"stage": 1, "replica_id": 1, "url": "http://hybrid-stage-1-0", "assigned_load": 1},
                    {"stage": 3, "replica_id": 1, "url": "http://hybrid-stage-3-0", "assigned_load": 2},
                ),
                "skipped_stage": 2,
            },
            {
                "flow_id": 2,
                "hops": (
                    {"stage": 2, "replica_id": 1, "url": "http://hybrid-stage-2-0", "assigned_load": 1},
                    {"stage": 3, "replica_id": 1, "url": "http://hybrid-stage-3-0", "assigned_load": 2},
                ),
                "skipped_stage": 1,
            },
        ),
    )

    async def exercise():
        async with AsyncClient(
            transport=ASGITransport(app=application),
            base_url="http://hybrid-flow-generator.test",
        ) as client:
            accepted = await client.post(
                "/run-slot",
                json=request.model_dump(mode="json"),
            )
            rejected = await client.post("/run-slot", json=exact_request)
            wrong_version = request.model_dump(mode="json")
            wrong_version["contract_version"] = "ibg-exact-contiguous-route-v1"
            rejected_version = await client.post(
                "/run-slot",
                json=wrong_version,
            )
        return accepted, rejected, rejected_version

    exact_request = {
        "datapath_mode": "kernel",
        "slot_id": 1,
        "routes": [
            {
                "flow_id": 1,
                "hops": [
                    {"stage": 1, "replica_id": 1, "url": "http://stage-1-0"},
                    {"stage": 2, "replica_id": 1, "url": "http://stage-2-0"},
                ],
            }
        ],
    }
    response, rejected, rejected_version = asyncio.run(exercise())
    assert response.status_code == 200
    assert len(executor.requests) == 1
    assert response.json()["flows"][0]["skipped_stage"] == 2
    assert rejected.status_code == 422
    assert rejected_version.status_code == 422


def test_flow_generator_application_owns_one_executor_lifecycle():
    executor = LifecycleExecutor()
    application = create_app(executor)
    request = HybridKernelRunSlotRequest(
        slot_id=1,
        routes=(
            {
                "flow_id": 1,
                "hops": (
                    {
                        "stage": 1,
                        "replica_id": 1,
                        "url": "http://hybrid-stage-1-0",
                        "assigned_load": 1,
                    },
                    {
                        "stage": 3,
                        "replica_id": 1,
                        "url": "http://hybrid-stage-3-0",
                        "assigned_load": 1,
                    },
                ),
                "skipped_stage": 2,
            },
        ),
    )

    async def exercise():
        async with application.router.lifespan_context(application):
            assert executor.start_calls == 1
            assert executor.close_calls == 0
            async with AsyncClient(
                transport=ASGITransport(app=application),
                base_url="http://hybrid-flow-generator.test",
            ) as client:
                first = await client.post(
                    "/run-slot", json=request.model_dump(mode="json")
                )
                second = await client.post(
                    "/run-slot", json=request.model_dump(mode="json")
                )
            assert first.status_code == second.status_code == 200
            assert executor.close_calls == 0
        assert executor.close_calls == 1

    asyncio.run(exercise())

    assert len(executor.requests) == 2


def test_controller_places_every_flow_then_sends_one_request_and_retains_beliefs():
    inputs = small_controller_inputs()
    ready = snapshot(inputs.configuration)
    discovery = FakeDiscovery(ready)
    generator = FakeFlowGenerator()
    uniform = {item.choice: (0.25, 0.25, 0.25, 0.25) for item in inputs.admission}
    controller = HybridKernelControllerAdapter(
        controller_inputs=inputs,
        discovery=discovery,
        flow_generator=generator,
        initial_beliefs=uniform,
    )

    first = controller.run_slot(1)

    assert discovery.calls == 1
    assert len(generator.requests) == 1
    assert len(generator.requests[0].routes) == inputs.configuration.num_flows
    assert len(first.slot.placements) == inputs.configuration.num_flows
    assert len(first.slot.observations) == 2 * inputs.configuration.num_flows
    assert len(first.slot.measured_pairs) == inputs.configuration.num_flows
    assert all(pair.latency_ms == 5.0 for pair in first.slot.measured_pairs)
    planning_by_pair = {
        link.pair: link.latency_ms for link in inputs.planning_pair_links
    }
    selected_planning_links = {
        placement.action.choices: planning_by_pair[placement.action.choices]
        for placement in first.slot.placements
    }
    assert all(value != 5.0 for value in selected_planning_links.values())
    action_by_flow = {
        placement.flow.flow_id: placement.action
        for placement in first.slot.placements
    }
    assert all(
        observation.choice in action_by_flow[observation.flow_id].choices
        for observation in first.slot.observations
    )
    assert all(
        pair.source == action_by_flow[pair.flow_id].choices[0]
        and pair.target == action_by_flow[pair.flow_id].choices[1]
        for pair in first.slot.measured_pairs
    )
    assert all(
        observation.learning_signal_ms
        == observation.physical_processing_latency_ms
        + observation.observation_jitter_ms
        for observation in first.slot.observations
    )
    assert all(
        observation.provenance.contract_version
        == HYBRID_KERNEL_OBSERVATION_PROVENANCE_VERSION
        for observation in first.slot.observations
    )
    assert all(
        not hasattr(observation, "physical_seed")
        and not hasattr(observation, "observation_seed")
        for observation in first.slot.observations
    )
    assert set(controller.beliefs) == set(uniform)
    assert controller.beliefs != uniform
    assert first.control_plane is None

    second = controller.run_slot(2)
    assert second.slot.beliefs_before == first.slot.beliefs_after
    assert len(generator.requests) == 2
    controller.close()


def test_controller_footprint_counts_actual_http_bodies_and_exact_messages():
    inputs = small_controller_inputs()
    meter = HybridControlPlaneDataMeter()
    observed = {}

    def kubernetes_handler(request: Request):
        response = Response(
            200,
            request=request,
            json={"items": pod_list(inputs.configuration)},
        )
        observed["kubernetes_request"] = len(request.content)
        observed["kubernetes_response"] = len(response.content)
        return response

    api = HybridKubernetesApi(
        base_url="https://kubernetes.test",
        token="token",
        verify=False,
        transport=MockTransport(kubernetes_handler),
        control_plane_meter=meter,
    )
    discovery = HybridKubernetesReplicaDiscovery(api, inputs.configuration)

    def flow_generator_handler(request: Request):
        slot_request = HybridKernelRunSlotRequest.model_validate(
            json.loads(request.content)
        )
        body = response_for_request(slot_request).model_dump_json().encode("utf-8")
        observed["route_request"] = len(request.content)
        observed["telemetry_response"] = len(body)
        return Response(
            200,
            request=request,
            content=body,
            headers={"content-type": "application/json"},
        )

    flow_generator = HybridKernelFlowGeneratorHttpClient(
        "http://hybrid-flow-generator.test",
        transport=MockTransport(flow_generator_handler),
        control_plane_meter=meter,
    )
    uniform = {item.choice: (0.25, 0.25, 0.25, 0.25) for item in inputs.admission}
    controller = HybridKernelControllerAdapter(
        controller_inputs=inputs,
        discovery=discovery,
        flow_generator=flow_generator,
        initial_beliefs=uniform,
        control_plane_meter=meter,
    )
    try:
        outcome = controller.run_slot(1)
    finally:
        controller.close()

    footprint = outcome.control_plane
    assert footprint["schema"] == HYBRID_CONTROL_PLANE_DATA_SCHEMA
    assert set(footprint) == {"schema", "payload_bytes", "messages"}
    assert footprint["payload_bytes"] == {
        "kubernetes_discovery_tx": observed["kubernetes_request"],
        "kubernetes_discovery_rx": observed["kubernetes_response"],
        "route_command_tx": observed["route_request"],
        "selected_telemetry_rx": observed["telemetry_response"],
        "belief_tx": 0,
        "belief_rx": 0,
        "total": sum(observed.values()),
    }
    assert footprint["messages"] == {
        "kubernetes_discovery_tx": 1,
        "kubernetes_discovery_rx": 1,
        "route_command_tx": 1,
        "selected_telemetry_rx": 1,
        "belief_tx": 0,
        "belief_rx": 0,
        "total": 4,
    }


def test_controller_reuses_http_clients_across_slots_and_closes_owned_ports():
    inputs = small_controller_inputs()
    meter = HybridControlPlaneDataMeter()

    def kubernetes_handler(request: Request):
        return Response(
            200,
            request=request,
            json={"items": pod_list(inputs.configuration)},
        )

    kubernetes_transport = CountingTransport(kubernetes_handler)
    api = HybridKubernetesApi(
        base_url="https://kubernetes.test",
        token="token",
        verify=False,
        transport=kubernetes_transport,
        control_plane_meter=meter,
    )
    discovery = HybridKubernetesReplicaDiscovery(api, inputs.configuration)

    def flow_generator_handler(request: Request):
        slot_request = HybridKernelRunSlotRequest.model_validate_json(
            request.content
        )
        return Response(
            200,
            request=request,
            content=response_for_request(slot_request).model_dump_json(),
            headers={"content-type": "application/json"},
        )

    flow_transport = CountingTransport(flow_generator_handler)
    flow_generator = HybridKernelFlowGeneratorHttpClient(
        "http://hybrid-flow-generator.test",
        transport=flow_transport,
        control_plane_meter=meter,
    )
    uniform = {
        item.choice: (0.25, 0.25, 0.25, 0.25)
        for item in inputs.admission
    }
    controller = HybridKernelControllerAdapter(
        controller_inputs=inputs,
        discovery=discovery,
        flow_generator=flow_generator,
        initial_beliefs=uniform,
        control_plane_meter=meter,
    )

    with controller:
        first = controller.run_slot(1)
        second = controller.run_slot(2)
        assert kubernetes_transport.close_calls == 0
        assert flow_transport.close_calls == 0

    assert len(kubernetes_transport.requests) == 2
    assert len(flow_transport.requests) == 2
    assert kubernetes_transport.close_calls == 1
    assert flow_transport.close_calls == 1
    assert api.is_closed is flow_generator.is_closed is controller.is_closed is True
    assert first.slot.beliefs_after == second.slot.beliefs_before
    assert first.control_plane["messages"]["total"] == 4
    assert second.control_plane["messages"]["total"] == 4
    with pytest.raises(RuntimeError, match="closed"):
        controller.run_slot(3)


def test_controller_closes_both_http_clients_after_slot_failure():
    inputs = small_controller_inputs()

    kubernetes_transport = CountingTransport(
        lambda request: Response(
            200,
            request=request,
            json={"items": pod_list(inputs.configuration)},
        )
    )
    api = HybridKubernetesApi(
        base_url="https://kubernetes.test",
        token="token",
        verify=False,
        transport=kubernetes_transport,
    )
    flow_transport = CountingTransport(
        lambda request: Response(503, request=request, text="unavailable")
    )
    flow_generator = HybridKernelFlowGeneratorHttpClient(
        "http://hybrid-flow-generator.test",
        transport=flow_transport,
    )
    uniform = {
        item.choice: (0.25, 0.25, 0.25, 0.25)
        for item in inputs.admission
    }
    controller = HybridKernelControllerAdapter(
        controller_inputs=inputs,
        discovery=HybridKubernetesReplicaDiscovery(api, inputs.configuration),
        flow_generator=flow_generator,
        initial_beliefs=uniform,
    )

    with pytest.raises(HTTPStatusError, match="503"):
        with controller:
            controller.run_slot(1)

    assert api.is_closed is flow_generator.is_closed is controller.is_closed is True
    assert kubernetes_transport.close_calls == 1
    assert flow_transport.close_calls == 1


def test_partial_kernel_telemetry_fails_before_learning_and_preserves_beliefs():
    inputs = small_controller_inputs()
    uniform = {item.choice: (0.25, 0.25, 0.25, 0.25) for item in inputs.admission}
    controller = HybridKernelControllerAdapter(
        controller_inputs=inputs,
        discovery=FakeDiscovery(snapshot(inputs.configuration)),
        flow_generator=FakeFlowGenerator(partial=True),
        initial_beliefs=uniform,
    )

    try:
        with pytest.raises(RuntimeError, match="partial flow coverage"):
            controller.run_slot(1)
    finally:
        controller.close()
    assert controller.beliefs == uniform


def test_phase2_modules_are_import_safe_rng_neutral_and_file_safe(tmp_path):
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT)
    code = (
        "import random, numpy as np; "
        "random.seed(81); np.random.seed(82); "
        "p=random.getstate(); n=np.random.get_state(); "
        "import IBG_Hybrid.kernel_runtime_profiles; "
        "import IBG_Hybrid.kernel_controller_config; "
        "import IBG_Hybrid.kernel_kubernetes_discovery; "
        "import IBG_Hybrid.kernel_flow_generator; "
        "import IBG_Hybrid.kernel_processor_service; "
        "import IBG_Hybrid.kernel_route_forwarder_service; "
        "import IBG_Hybrid.kernel_controller; "
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


def test_service_only_modules_do_not_import_hybrid_policy_or_milp():
    for name in (
        "kernel_processor_service.py",
        "kernel_route_forwarder_service.py",
        "kernel_flow_generator.py",
    ):
        source = (ROOT / "IBG_Hybrid" / name).read_text()
        assert "MILP" not in source
        assert "from .policy" not in source
        assert "from .runner" not in source
