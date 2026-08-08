from dataclasses import FrozenInstanceError, fields, replace
import os
from pathlib import Path
import subprocess
import sys

import pytest

from IBG_Hybrid.contracts import HybridConfiguration, ReplicaChoice
from IBG_Hybrid.kernel_infrastructure_contract import (
    DEFAULT_HYBRID_KERNEL_CONTROLLER_LIFECYCLE,
    DEFAULT_HYBRID_KERNEL_IMAGE_OWNERSHIP,
    DEFAULT_HYBRID_KERNEL_OWNERSHIP,
    DEFAULT_HYBRID_KERNEL_RUNTIME_REUSE,
    HYBRID_KERNEL_CONTROLLER_STEPS,
    HYBRID_KERNEL_DISCOVERY_CONTRACT_VERSION,
    HYBRID_KERNEL_INFRASTRUCTURE_CONTRACT_VERSION,
    HYBRID_KERNEL_NAMESPACE,
    HYBRID_KERNEL_RUNTIME_PROFILE_CONTRACT_VERSION,
    HybridKernelContractError,
    HybridKernelControllerLifecycle,
    HybridKernelControllerStep,
    HybridKernelDiscoveredReplica,
    HybridKernelDiscoverySnapshot,
    HybridKernelImageOwnership,
    HybridKernelOwnership,
    HybridKernelRuntimeProfileDocument,
    HybridKernelRuntimeReplicaProfile,
    HybridKernelRuntimeReuseBoundary,
    require_complete_ready_discovery,
)


ROOT = Path(__file__).resolve().parents[1]


def configuration(replicas=2):
    return HybridConfiguration(num_flows=4, num_stages=3, num_replicas=replicas)


def runtime_profiles(config):
    return tuple(
        HybridKernelRuntimeReplicaProfile(
            ReplicaChoice(stage, replica),
            hidden_state=((stage + replica - 2) % 4) + 1,
            observation_seed=2050 + stage * 100 + replica,
        )
        for stage in range(1, config.num_stages + 1)
        for replica in range(1, config.num_replicas + 1)
    )


def discovered_replicas(config):
    ownership = DEFAULT_HYBRID_KERNEL_OWNERSHIP
    return tuple(
        HybridKernelDiscoveredReplica(
            choice=ReplicaChoice(stage, replica),
            namespace=ownership.namespace,
            pod_name=f"{ownership.stage_name(stage)}-{replica - 1}",
            pod_uid=f"uid-{stage}-{replica}",
            node_name=f"worker-{replica % 2}",
            endpoint=(
                f"http://{ownership.stage_name(stage)}-{replica - 1}."
                f"{ownership.stage_name(stage)}.{ownership.namespace}."
                "svc.cluster.local.:8080"
            ),
            labels=ownership.replica_labels(stage),
        )
        for stage in range(1, config.num_stages + 1)
        for replica in range(1, config.num_replicas + 1)
    )


def test_hybrid_owns_names_selectors_configmaps_and_images():
    ownership = DEFAULT_HYBRID_KERNEL_OWNERSHIP

    assert ownership.contract_version == HYBRID_KERNEL_INFRASTRUCTURE_CONTRACT_VERSION
    assert ownership.namespace == HYBRID_KERNEL_NAMESPACE == "ibg-hybrid-testbed"
    assert ownership.namespace not in {"ibg-testbed", "milp-testbed"}
    assert ownership.part_of_label not in {"ibg-testbed", "milp-testbed"}
    assert ownership.service_image != ownership.controller_image
    assert ownership.replica_selector(2) == (
        ("app.kubernetes.io/name", "ibg-hybrid-replica"),
        ("ibg-hybrid.stage", "2"),
    )
    assert ownership.stage_name(2) == "hybrid-stage-2"
    for name in (
        ownership.controller_name,
        ownership.controller_service_account,
        ownership.discovery_role_name,
        ownership.flow_generator_name,
        ownership.runtime_profile_config_map,
        ownership.planning_link_config_map,
    ):
        assert name.startswith("ibg-hybrid-")


@pytest.mark.parametrize("namespace", ("ibg-testbed", "milp-testbed"))
def test_hybrid_rejects_shared_namespace_ownership(namespace):
    with pytest.raises(HybridKernelContractError, match="must not share"):
        HybridKernelOwnership(namespace=namespace)


def test_runtime_profile_is_complete_canonical_and_has_no_beliefs():
    config = configuration()
    document = HybridKernelRuntimeProfileDocument(
        configuration=config,
        profiles=runtime_profiles(config),
        source_identity="hybrid-fixture-v1",
    )

    assert document.contract_version == HYBRID_KERNEL_RUNTIME_PROFILE_CONTRACT_VERSION
    assert len(document.profiles) == config.num_stages * config.num_replicas
    assert tuple(document.profile_by_choice()) == tuple(
        profile.choice for profile in document.profiles
    )
    assert {field.name for field in fields(HybridKernelRuntimeReplicaProfile)} == {
        "choice",
        "hidden_state",
        "observation_seed",
    }
    assert "belief" not in {field.name for field in fields(type(document))}
    with pytest.raises(FrozenInstanceError):
        document.source_identity = "changed"


def test_runtime_profile_rejects_missing_duplicate_and_noncanonical_entries():
    config = configuration()
    profiles = runtime_profiles(config)
    with pytest.raises(HybridKernelContractError, match="coverage mismatch"):
        HybridKernelRuntimeProfileDocument(config, profiles[:-1], "missing")
    with pytest.raises(HybridKernelContractError, match="duplicate"):
        HybridKernelRuntimeProfileDocument(
            config,
            profiles[:-1] + (profiles[0],),
            "duplicate",
        )
    with pytest.raises(HybridKernelContractError, match="canonical"):
        HybridKernelRuntimeProfileDocument(
            config,
            tuple(reversed(profiles)),
            "unordered",
        )


def test_ready_discovery_requires_complete_owned_ordinal_set():
    config = configuration()
    replicas = discovered_replicas(config)

    accepted = require_complete_ready_discovery(reversed(replicas), config)

    assert accepted == replicas
    assert len(accepted) == config.num_stages * config.num_replicas
    assert HYBRID_KERNEL_DISCOVERY_CONTRACT_VERSION.endswith("-v1")

    snapshot = HybridKernelDiscoverySnapshot(config, tuple(reversed(replicas)))
    assert snapshot.contract_version == HYBRID_KERNEL_DISCOVERY_CONTRACT_VERSION
    assert snapshot.replicas == replicas
    assert tuple(snapshot.replica_by_choice()) == tuple(
        replica.choice for replica in replicas
    )


@pytest.mark.parametrize(
    ("change", "message"),
    (
        ({"ready": False}, "not Running and Ready"),
        ({"phase": "Pending"}, "not Running and Ready"),
        ({"namespace": "ibg-testbed"}, "foreign namespace"),
        ({"pod_name": "stage-1-0"}, "unexpected StatefulSet identity"),
        ({"labels": (("app.kubernetes.io/name", "ibg-replica"),)}, "labels"),
    ),
)
def test_ready_discovery_rejects_unready_or_foreign_runtime(change, message):
    config = configuration()
    replicas = list(discovered_replicas(config))
    replicas[0] = replace(replicas[0], **change)
    with pytest.raises(HybridKernelContractError, match=message):
        require_complete_ready_discovery(replicas, config)


def test_ready_discovery_rejects_missing_and_duplicate_identity():
    config = configuration()
    replicas = discovered_replicas(config)
    with pytest.raises(HybridKernelContractError, match="coverage mismatch"):
        require_complete_ready_discovery(replicas[:-1], config)
    with pytest.raises(HybridKernelContractError, match="duplicate"):
        require_complete_ready_discovery(replicas[:-1] + (replicas[0],), config)


def test_controller_lifecycle_places_everything_before_traffic_and_keeps_beliefs():
    lifecycle = DEFAULT_HYBRID_KERNEL_CONTROLLER_LIFECYCLE

    assert lifecycle.steps == HYBRID_KERNEL_CONTROLLER_STEPS
    assert lifecycle.steps.index(HybridKernelControllerStep.PLACE_ALL_FOCAL_FLOWS) < (
        lifecycle.steps.index(HybridKernelControllerStep.EXECUTE_SELECTED_ROUTES)
    )
    assert lifecycle.beliefs_owner == "controller-private"
    assert lifecycle.beliefs_persist_across_slots
    assert lifecycle.traffic_starts_after_complete_placement
    assert not lifecycle.hidden_state_is_policy_input
    assert not lifecycle.automatic_monte_carlo_activation
    with pytest.raises(HybridKernelContractError, match="automatic"):
        HybridKernelControllerLifecycle(automatic_monte_carlo_activation=True)


def test_image_split_and_exact_runtime_reuse_are_frozen_without_resource_tuning():
    images = DEFAULT_HYBRID_KERNEL_IMAGE_OWNERSHIP
    reuse = DEFAULT_HYBRID_KERNEL_RUNTIME_REUSE

    assert images.service_image != images.controller_image
    assert images.service_components == (
        "private-processor",
        "public-forwarder",
        "flow-generator",
    )
    assert "hybrid-policy" in images.controller_components
    assert set(images.service_components).isdisjoint(images.controller_components)
    assert {"scipy", "highs", "ortools"}.issubset(
        images.milp_solver_dependencies_forbidden
    )
    assert reuse.private_processor_workers == 1
    assert reuse.private_processor_port == 8081
    assert reuse.public_forwarder_workers == 2
    assert reuse.public_forwarder_port == 8080
    assert reuse.public_forwarder_keepalive_seconds == 30
    assert reuse.separate_local_and_downstream_clients
    assert reuse.route_contract_phase == 1
    assert reuse.resource_acceptance_phase == 7
    assert not any("memory" in field.name or "cpu" in field.name for field in fields(type(reuse)))


def test_contracts_reject_route_or_resource_phase_collapse():
    with pytest.raises(HybridKernelContractError, match="deferred"):
        HybridKernelRuntimeReuseBoundary(route_contract_phase=2)
    with pytest.raises(HybridKernelContractError, match="deferred"):
        HybridKernelRuntimeReuseBoundary(resource_acceptance_phase=6)
    with pytest.raises(HybridKernelContractError, match="must differ"):
        HybridKernelImageOwnership(service_image="same", controller_image="same")


def test_contract_import_is_silent_state_neutral_and_has_no_runtime_side_effects(
    tmp_path,
):
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT)
    code = (
        "import random, numpy as np; "
        "random.seed(81); np.random.seed(82); "
        "p=random.getstate(); n=np.random.get_state(); "
        "import IBG_Hybrid.kernel_infrastructure_contract; "
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
