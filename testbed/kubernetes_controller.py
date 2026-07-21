import json
import os
import random
import time

import httpx
import numpy as np

from datapath import KERNEL_DATAPATH_MODE, require_datapath_mode
from learning_mode import (
    SEPARATED_LEARNING_SIGNAL_MODE,
    require_learning_signal_mode,
)
from runner import run_decoupled_slot
from testbed.experiment import run_until_equilibrium
from testbed.kubernetes_adapters import (
    KubernetesApi,
    KubernetesReplicaDiscovery,
    build_replica_list,
    make_kubernetes_adapters,
    wait_for_ready_replicas,
)
from testbed.profiles import load_profiles
from testbed.validation import summarize_slot


def wait_for_flow_generator(
    url,
    datapath_mode=KERNEL_DATAPATH_MODE,
    timeout_seconds=120.0,
):
    expected_mode = require_datapath_mode(datapath_mode, runtime=True)
    deadline = time.monotonic() + timeout_seconds
    last_error = None
    while time.monotonic() < deadline:
        try:
            response = httpx.get(f"{url.rstrip('/')}/health", timeout=5.0)
            response.raise_for_status()
            payload = response.json()
            if (
                payload.get("status") == "ok"
                and payload.get("datapath_mode") == expected_mode
            ):
                return
        except (httpx.HTTPError, ValueError) as error:
            last_error = error
        time.sleep(2.0)
    raise RuntimeError(f"flow generator did not become ready: {last_error}")


def read_boolean_environment(name, *, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value")


def main():
    namespace = os.environ.get("POD_NAMESPACE", "ibg-testbed")
    datapath_mode = require_datapath_mode(
        os.environ.get("DATAPATH_MODE", KERNEL_DATAPATH_MODE),
        runtime=True,
    )
    num_of_stages = int(os.environ.get("NUM_STAGES", "3"))
    num_of_replicas = int(os.environ.get("EXPECTED_REPLICAS", "2"))
    num_of_flows = int(os.environ.get("NUM_FLOWS", "3"))
    first_slot_id = int(os.environ.get("SLOT_ID", "1"))
    max_iterations = int(os.environ.get("MAX_ITERATIONS", "1"))
    learning_signal_mode = require_learning_signal_mode(
        os.environ.get(
            "LEARNING_SIGNAL_MODE",
            SEPARATED_LEARNING_SIGNAL_MODE,
        )
    )
    forwarder_cgroup_diagnostics = read_boolean_environment(
        "FORWARDER_CGROUP_DIAGNOSTICS",
    )
    if min(
        num_of_stages,
        num_of_replicas,
        num_of_flows,
        first_slot_id,
        max_iterations,
    ) < 1:
        raise ValueError(
            "stages, replicas, flows, slot ID, and max iterations must be positive"
        )
    seeds = [
        int(value.strip())
        for value in os.environ.get(
            "IBG_SEEDS",
            os.environ.get("IBG_SEED", "2050"),
        ).split(",")
        if value.strip()
    ]
    if not seeds:
        raise ValueError("at least one IBG seed is required")
    profile_path = os.environ.get(
        "REPLICA_PROFILES_PATH",
        "/etc/ibg/profiles.json",
    )
    flow_generator_url = os.environ.get(
        "FLOW_GENERATOR_URL",
        f"http://flow-generator.{namespace}.svc.cluster.local.:8080",
    )
    environment = json.loads(os.environ.get("EXPERIMENT_ENVIRONMENT", "{}"))
    if not isinstance(environment, dict):
        raise ValueError("EXPERIMENT_ENVIRONMENT must contain a JSON object")

    profiles = load_profiles(profile_path)
    api = KubernetesApi(namespace)
    discovery = KubernetesReplicaDiscovery(api, namespace, num_of_replicas)
    wait_for_flow_generator(flow_generator_url, datapath_mode)

    for offset, seed in enumerate(seeds):
        run_first_slot_id = first_slot_id + (offset * max_iterations)
        random.seed(seed)
        np.random.seed(seed)
        replica_list = build_replica_list(
            profiles,
            num_of_stages,
            num_of_replicas,
        )
        discovered = wait_for_ready_replicas(
            discovery,
            replica_list,
            num_of_stages,
        )
        adapters = make_kubernetes_adapters(
            discovery,
            flow_generator_url,
            datapath_mode=datapath_mode,
            learning_signal_mode=learning_signal_mode,
            forwarder_cgroup_diagnostics=forwarder_cgroup_diagnostics,
        )
        flow_list = list(range(1, num_of_flows + 1))

        def run_slot(slot_id):
            return run_decoupled_slot(
                flow_list,
                replica_list,
                num_of_stages=num_of_stages,
                num_of_replicas=num_of_replicas,
                adapters=adapters,
                slot_id=slot_id,
            )

        def summarize(result, slot_id):
            summary = summarize_slot(
                result,
                replica_list,
                backend="kubernetes",
                seed=seed,
                slot_id=slot_id,
                num_of_stages=num_of_stages,
                num_of_replicas=num_of_replicas,
                num_of_flows=num_of_flows,
                discovered_by_stage=discovered,
            )
            if len(summary["placements"]) != num_of_stages * num_of_flows:
                raise RuntimeError(
                    "controller did not produce every stage placement"
                )
            if len(summary["observations"]) != num_of_stages * num_of_flows:
                raise RuntimeError(
                    "controller did not receive every selected observation"
                )
            return summary

        def emit(event):
            print(f"IBG_EVENT={json.dumps(event, sort_keys=True)}", flush=True)

        outcome = run_until_equilibrium(
            replica_list=replica_list,
            first_slot_id=run_first_slot_id,
            max_iterations=max_iterations,
            run_slot=run_slot,
            summarize=summarize,
            emit=emit,
            run_metadata={
                "backend": "kubernetes",
                "datapath_mode": datapath_mode,
                "learning_signal_mode": learning_signal_mode,
                "forwarder_cgroup_diagnostics": forwarder_cgroup_diagnostics,
                "runtime_image": os.environ.get(
                    "RUNTIME_IMAGE",
                    "unknown",
                ),
                "environment": environment,
                "seed": seed,
                "configuration": {
                    "stages": num_of_stages,
                    "replicas_per_stage": num_of_replicas,
                    "flows": num_of_flows,
                },
            },
            require_equilibrium=max_iterations > 1,
        )
        if max_iterations == 1:
            print(
                "PHASE6_RESULT="
                f"{json.dumps(outcome.final_summary, sort_keys=True)}",
                flush=True,
            )


if __name__ == "__main__":
    main()
