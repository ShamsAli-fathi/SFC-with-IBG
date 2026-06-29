import json
import os
import random
import time

import httpx
import numpy as np

from runner import run_decoupled_slot
from testbed.kubernetes_adapters import (
    KubernetesApi,
    KubernetesReplicaDiscovery,
    build_replica_list,
    make_kubernetes_adapters,
    wait_for_ready_replicas,
)
from testbed.profiles import load_profiles


def wait_for_flow_generator(url, timeout_seconds=120.0):
    deadline = time.monotonic() + timeout_seconds
    last_error = None
    while time.monotonic() < deadline:
        try:
            response = httpx.get(f"{url.rstrip('/')}/health", timeout=5.0)
            response.raise_for_status()
            if response.json().get("status") == "ok":
                return
        except (httpx.HTTPError, ValueError) as error:
            last_error = error
        time.sleep(2.0)
    raise RuntimeError(f"flow generator did not become ready: {last_error}")


def _slot_summary(result, replica_list, discovered_by_stage):
    placements = []
    for stage, assignments in sorted(result.assignments_by_stage.items()):
        for flow_id, replica_id in sorted(assignments.items()):
            replica = discovered_by_stage[stage][(stage, replica_id)]
            placements.append(
                {
                    "stage": stage,
                    "flow_id": flow_id,
                    "replica_id": replica_id,
                    "pod_name": replica.pod_name,
                    "node_name": replica.node_name,
                    "endpoint": replica.endpoint,
                }
            )

    observations = [
        {
            "stage": observation.stage,
            "flow_id": observation.flow_id,
            "replica_id": observation.replica_id,
            "congestion": observation.congestion,
            "signal": observation.signal,
            "likelihood": list(observation.likelihood),
            "measured_latency_ms": observation.measured_latency_ms,
        }
        for stage_observations in result.observations_by_stage.values()
        for observation in stage_observations
    ]

    return {
        "slot_id": int(os.environ.get("SLOT_ID", "1")),
        "placements": placements,
        "observations": observations,
        "traffic": result.traffic_telemetry.model_dump(mode="json"),
        "metrics": {
            "aggregate_utility_total": float(result.aggregate_utility_total),
            "aggregate_utility_per_flow": {
                str(flow_id): float(value)
                for flow_id, value in result.aggregate_utility_per_flow.items()
            },
            "sla_violations": int(result.sla_violations),
            "jain_fairness": float(result.jain_fairness),
            "equilibrium": int(result.equilibrium),
            "elapsed_seconds": float(result.elapsed_seconds),
        },
        "beliefs": {
            f"{stage}:{replica_id}": [float(value) for value in replica.belief]
            for (stage, replica_id), replica in sorted(replica_list.items())
        },
    }


def main():
    namespace = os.environ.get("POD_NAMESPACE", "ibg-testbed")
    num_of_stages = 3
    num_of_replicas = int(os.environ.get("EXPECTED_REPLICAS", "2"))
    num_of_flows = int(os.environ.get("NUM_FLOWS", "3"))
    slot_id = int(os.environ.get("SLOT_ID", "1"))
    seed = int(os.environ.get("IBG_SEED", "2050"))
    profile_path = os.environ.get(
        "REPLICA_PROFILES_PATH",
        "/etc/ibg/profiles.json",
    )
    flow_generator_url = os.environ.get(
        "FLOW_GENERATOR_URL",
        "http://flow-generator:8080",
    )

    random.seed(seed)
    np.random.seed(seed)
    profiles = load_profiles(profile_path)
    replica_list = build_replica_list(
        profiles,
        num_of_stages,
        num_of_replicas,
    )
    api = KubernetesApi(namespace)
    discovery = KubernetesReplicaDiscovery(api, namespace, num_of_replicas)
    discovered = wait_for_ready_replicas(
        discovery,
        replica_list,
        num_of_stages,
    )
    wait_for_flow_generator(flow_generator_url)
    adapters = make_kubernetes_adapters(discovery, flow_generator_url)

    result = run_decoupled_slot(
        list(range(1, num_of_flows + 1)),
        replica_list,
        num_of_stages=num_of_stages,
        num_of_replicas=num_of_replicas,
        adapters=adapters,
        slot_id=slot_id,
    )
    summary = _slot_summary(result, replica_list, discovered)
    if len(summary["placements"]) != num_of_stages * num_of_flows:
        raise RuntimeError("controller did not produce every stage placement")
    if len(summary["observations"]) != num_of_stages * num_of_flows:
        raise RuntimeError("controller did not receive every selected observation")
    print(f"PHASE5_RESULT={json.dumps(summary, sort_keys=True)}")


if __name__ == "__main__":
    main()
