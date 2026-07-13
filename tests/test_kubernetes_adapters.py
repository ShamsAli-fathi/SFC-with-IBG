import json
import random
from collections import Counter

from httpx import MockTransport, Request, Response
import numpy as np
import pytest

from runner import run_decoupled_slot
from testbed.cnf_service import ReplicaConfig
from testbed.kubernetes_adapters import (
    KubernetesApi,
    KubernetesReplicaDiscovery,
    build_replica_list,
    make_kubernetes_adapters,
)
from testbed.profiles import ReplicaProfile, expand_profiles, load_profiles


def profiles():
    states = {
        (1, 1): 4,
        (1, 2): 2,
        (2, 1): 3,
        (2, 2): 1,
        (3, 1): 4,
        (3, 2): 3,
    }
    return {
        (stage, replica_id): ReplicaProfile(
            state=states[(stage, replica_id)],
            capacity=2000 if replica_id == 1 else 5000,
            delay=25,
            cost=1,
            gamma=0.2 if replica_id == 1 else 0.3,
            base_delay_ms=40,
            congestion_delay_ms=10,
        )
        for stage in range(1, 4)
        for replica_id in range(1, 3)
    }


def ready_pod(stage, ordinal, ready=True):
    return {
        "metadata": {"name": f"stage-{stage}-{ordinal}"},
        "spec": {"nodeName": f"worker-{ordinal + 1}"},
        "status": {
            "phase": "Running",
            "conditions": [
                {"type": "Ready", "status": "True" if ready else "False"}
            ],
        },
    }


def test_profile_file_drives_statefulset_ordinal_config(tmp_path):
    document = {
        "stages": {
            "2": {
                "2": {
                    "state": 1,
                    "capacity": 5000,
                    "delay": 25,
                    "cost": 1,
                    "gamma": 0.3,
                    "base_delay_ms": 40,
                    "congestion_delay_ms": 10,
                }
            }
        }
    }
    profile_path = tmp_path / "profiles.json"
    profile_path.write_text(json.dumps(document), encoding="utf-8")

    loaded = load_profiles(profile_path)
    config = ReplicaConfig.from_env(
        {
            "STAGE": "2",
            "POD_NAME": "stage-2-1",
            "REPLICA_PROFILES_PATH": str(profile_path),
        }
    )

    assert loaded[(2, 2)].state == 1
    assert config.replica_id == 2
    assert config.state == 1
    assert config.capacity == 5000
    assert config.base_delay_ms == 40


def test_discovery_maps_only_ready_statefulset_ordinals():
    def handler(request: Request):
        assert request.url.path == "/api/v1/namespaces/ibg-testbed/pods"
        assert "ibg.stage%3D2" in str(request.url)
        return Response(
            200,
            request=request,
            json={"items": [ready_pod(2, 1), ready_pod(2, 0)]},
        )

    api = KubernetesApi(
        "ibg-testbed",
        base_url="http://kubernetes",
        token="token",
        verify=False,
        transport=MockTransport(handler),
    )
    replicas = build_replica_list(profiles(), 3, 2)
    discovery = KubernetesReplicaDiscovery(api, "ibg-testbed", 2)

    discovered = discovery.discover(2, replicas)

    assert list(discovered) == [(2, 1), (2, 2)]
    assert discovered[(2, 1)].pod_name == "stage-2-0"
    assert discovered[(2, 1)].node_name == "worker-1"
    assert discovered[(2, 2)].endpoint == (
        "http://stage-2-1.stage-2.ibg-testbed.svc.cluster.local:8080"
    )


def test_discovery_rejects_incomplete_ready_set():
    api = KubernetesApi(
        "ibg-testbed",
        base_url="http://kubernetes",
        token="token",
        verify=False,
        transport=MockTransport(
            lambda request: Response(
                200,
                request=request,
                json={"items": [ready_pod(1, 0), ready_pod(1, 1, ready=False)]},
            )
        ),
    )
    discovery = KubernetesReplicaDiscovery(api, "ibg-testbed", 2)

    with pytest.raises(RuntimeError, match=r"ready replicas \[1\].*expected \[1, 2\]"):
        discovery.discover(1, build_replica_list(profiles(), 3, 2))


@pytest.mark.parametrize("num_of_stages", [2, 3, 4])
def test_kubernetes_slot_executes_configured_routes_then_applies_telemetry(
    num_of_stages,
):
    configured_profiles = expand_profiles(profiles(), num_of_stages, 2)
    replica_list = build_replica_list(configured_profiles, num_of_stages, 2)

    class StaticDiscovery:
        def discover(self, stage, replicas):
            discovered = {}
            for replica_id in (1, 2):
                replica = replicas[(stage, replica_id)]
                replica.pod_name = f"stage-{stage}-{replica_id - 1}"
                replica.node_name = f"worker-{replica_id}"
                replica.endpoint = (
                    f"http://{replica.pod_name}.stage-{stage}."
                    "ibg-testbed.svc.cluster.local:8080"
                )
                discovered[(stage, replica_id)] = replica
            return discovered

    captured = {}

    def flow_generator(request: Request):
        payload = json.loads(request.content)
        captured["payload"] = payload
        planned_congestion = Counter(
            (hop["stage"], hop["replica_id"])
            for route in payload["routes"]
            for hop in route["hops"]
        )
        flows = []
        for route in payload["routes"]:
            flows.append(
                {
                    "flow_id": route["flow_id"],
                    "hops": [
                        {
                            "slot_id": payload["slot_id"],
                            "flow_id": route["flow_id"],
                            "stage": hop["stage"],
                            "replica_id": hop["replica_id"],
                            "pod_name": f"stage-{hop['stage']}-{hop['replica_id'] - 1}",
                                "endpoint": hop["url"],
                                "concurrency": 1,
                                "assigned_load": planned_congestion[
                                    (hop["stage"], hop["replica_id"])
                                ],
                                "modeled_processing_latency_ms": 40.0,
                                "legacy_congestion": planned_congestion[
                                    (hop["stage"], hop["replica_id"])
                                ],
                                "processing_latency_ms": 40.0,
                            "request_latency_ms": 41.0,
                            "signal_latency_ms": 40.0,
                            "state_estimate": 3,
                            "state_likelihood": [0.1, 0.2, 0.3, 0.4],
                            "legacy_signal": 3,
                            "legacy_likelihood": [0.1, 0.2, 0.3, 0.4],
                        }
                        for hop in route["hops"]
                    ],
                }
            )
        return Response(
            200,
            request=request,
            json={"slot_id": payload["slot_id"], "elapsed_ms": 123.0, "flows": flows},
        )

    adapters = make_kubernetes_adapters(
        StaticDiscovery(),
        "http://flow-generator",
        transport=MockTransport(flow_generator),
    )
    random.seed(2050)
    np.random.seed(2050)
    result = run_decoupled_slot(
        [1, 2, 3],
        replica_list,
        num_of_stages=num_of_stages,
        num_of_replicas=2,
        adapters=adapters,
        slot_id=7,
    )

    assert captured["payload"]["slot_id"] == 7
    assert len(captured["payload"]["routes"]) == 3
    assert all(
        len(route["hops"]) == num_of_stages
        for route in captured["payload"]["routes"]
    )
    assert result.traffic_telemetry.slot_id == 7
    assert all(len(items) == 3 for items in result.observations_by_stage.values())
    assert all(
        observation.measured_latency_ms == 40.0
        for items in result.observations_by_stage.values()
        for observation in items
    )
    for stage, observations in result.observations_by_stage.items():
        assignments = result.assignments_by_stage[stage]
        congestion = Counter(assignments.values())
        assert all(
            observation.congestion == congestion[observation.replica_id]
            for observation in observations
        )
    assert all(
        latency == pytest.approx(num_of_stages)
        for latency in result.link_latency_ms_per_flow.values()
    )
    assert all(
        latency == pytest.approx(num_of_stages * 40.0)
        for latency in result.processing_latency_ms_per_flow.values()
    )
    assert all(
        latency == pytest.approx(num_of_stages * 41.0)
        for latency in result.end_to_end_latency_ms_per_flow.values()
    )
    assert all(
        utility == pytest.approx(num_of_stages * 58.0)
        for utility in result.realized_utility_per_flow.values()
    )
    assert result.sla_violations == 0
