from __future__ import annotations

from copy import deepcopy
import io
import inspect
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tarfile

import numpy as np
import pytest

from Greedy.comparison import (
    GREEDY_PHASE5_HYBRID_AUDIT_HEAD,
    GREEDY_PHASE5_HYBRID_SOURCE_AUDIT,
)
from Greedy.contracts import GreedyConfiguration
from Greedy.kernel_infrastructure import (
    GREEDY_CONTROLLER_IMAGE,
    GREEDY_CONTROLLER_INPUT_CONFIG_MAP,
    GREEDY_CONTROLLER_JOB,
    GREEDY_FLOW_GENERATOR,
    GREEDY_NAMESPACE,
    GREEDY_RUNTIME_PROFILE_CONFIG_MAP,
    GREEDY_SERVICE_IMAGE,
    GREEDY_WORKLOAD_NODE_LABEL,
    GreedyStaticDeploymentInput,
    parse_resource_documents,
    render_long_running_resources,
)
from Greedy.kernel_lifecycle import (
    CONTROLLER_SOURCE_FILES,
    GREEDY_CLUSTER_NAME,
    GREEDY_CONTEXT,
    GREEDY_CONTROL_PLANE_NODE,
    GREEDY_KIND_NODE_IMAGE,
    GREEDY_LAUNCHER_STATE_CONFIG_MAP,
    GREEDY_NORMALIZED_CONTROLLER_IMAGE,
    GREEDY_NORMALIZED_SERVICE_IMAGE,
    GREEDY_PART_OF,
    GREEDY_WORKER_NODE,
    SERVICE_SOURCE_FILES,
    GreedyLaunchConfiguration,
    GreedyLauncherState,
    GreedyLifecycleError,
    _launcher_state_resource,
    cleanup,
    image_source_fingerprints,
    launcher_state_from_mapping,
    launcher_state_to_mapping,
    resolve_root_seed,
    run_greedy_lifecycle,
    preflight,
    validate_cluster_inventory,
)
from Greedy.kernel_profile_reconciliation import (
    GreedyProfileReconciliationError,
    matched_observation_seed,
    materialize_runtime_profiles,
    seeded_hidden_state_sequence,
    validate_profile_transition,
)
from Greedy.kernel_rollout import (
    GreedyKernelRolloutError,
    discover_existing_topology,
    plan_replica_batches,
    plan_topology_reconciliation,
    validate_ready_coverage,
)
from scripts.run_greedy_kernel import launch_configuration_from_args, parse_args


ROOT = Path(__file__).resolve().parents[1]
SERVICE_ID = "a" * 64
CONTROLLER_ID = "b" * 64


def make_launch(
    flows=4,
    stages=3,
    replicas=2,
    *,
    profile_seed=17,
    root_seed=2050,
    max_iterations=9,
    rollout_batch_size=1,
    skip_build=False,
    csv=0,
    parity_replay=0,
):
    return GreedyLaunchConfiguration(
        configuration=GreedyConfiguration(flows, stages, replicas),
        max_iterations=max_iterations,
        profile_seed=profile_seed,
        root_seed=root_seed,
        rollout_batch_size=rollout_batch_size,
        skip_build=skip_build,
        csv=csv,
        parity_replay=parity_replay,
    )


def deployment_for(configuration, profile_seed=17, root_seed=2050):
    return GreedyStaticDeploymentInput(
        runtime_profiles=materialize_runtime_profiles(
            configuration, profile_seed=profile_seed
        ),
        experiment_id=1,
        root_seed=root_seed,
        profile_seed=profile_seed,
        max_iterations=9,
        first_slot_id=1,
        source_identity=(
            f"greedy-kernel-launch-v1:{configuration.num_flows}x"
            f"{configuration.num_stages}x{configuration.num_replicas}"
        ),
    )


def node_document(*, cpu="64", memory="128Gi", extra=()):
    items = [
        {
            "metadata": {
                "name": GREEDY_CONTROL_PLANE_NODE,
                "labels": {"node-role.kubernetes.io/control-plane": ""},
            },
            "status": {
                "conditions": [{"type": "Ready", "status": "True"}],
                "allocatable": {"cpu": "8", "memory": "8Gi"},
            },
        },
        {
            "metadata": {
                "name": GREEDY_WORKER_NODE,
                "labels": {GREEDY_WORKLOAD_NODE_LABEL: "true"},
            },
            "status": {
                "conditions": [{"type": "Ready", "status": "True"}],
                "allocatable": {"cpu": cpu, "memory": memory},
            },
        },
    ]
    items.extend(extra)
    return {"items": items}


def namespace_document(*, greedy=True, foreign=()):
    names = ["default", "kube-system", "kube-public", "kube-node-lease"]
    names.extend(foreign)
    items = [{"metadata": {"name": name, "labels": {}}} for name in names]
    if greedy:
        items.append(
            {
                "metadata": {
                    "name": GREEDY_NAMESPACE,
                    "labels": {"app.kubernetes.io/part-of": GREEDY_PART_OF},
                }
            }
        )
    return {"items": items}


class FakeGreedyCluster:
    def __init__(
        self,
        *,
        existing=True,
        configuration=GreedyConfiguration(4, 3, 2),
        profile_seed=17,
        worker_cpu="64",
        worker_memory="128Gi",
    ):
        self.exists = existing
        self.configuration = configuration
        self.profile_seed = profile_seed
        self.worker_cpu = worker_cpu
        self.worker_memory = worker_memory
        self.commands = []
        self.events = []
        self.namespaces = set(
            ["default", "kube-system", "kube-public", "kube-node-lease"]
            + ([GREEDY_NAMESPACE] if existing else [])
        )
        self.statefulsets = {}
        self.services = set()
        self.configmaps = {}
        self.flow_generator = False
        self.job_exists = False
        self.jobs_created = 0
        self.extra_owned_resources = []
        self.pod_capacity = configuration.admission_capacity_per_replica
        self.uid_generation = 0
        self.local_image_ids = {
            GREEDY_SERVICE_IMAGE: SERVICE_ID,
            GREEDY_CONTROLLER_IMAGE: CONTROLLER_ID,
        }
        self.node_image_ids = dict(self.local_image_ids)
        if existing:
            deployment = deployment_for(configuration, profile_seed)
            for resource in render_long_running_resources(deployment):
                self._store_resource(deepcopy(resource))
            fingerprints = image_source_fingerprints()
            state = GreedyLauncherState(
                stable_configuration=configuration,
                target_configuration=configuration,
                profile_seed=profile_seed,
                profile_fingerprint=deployment.runtime_profiles.fingerprint,
                service_source_fingerprint=fingerprints["service"],
                controller_source_fingerprint=fingerprints["controller"],
                service_image_id=SERVICE_ID,
                controller_image_id=CONTROLLER_ID,
                transition_active=False,
            )
            self._store_resource(_launcher_state_resource(state))

    def wheelhouses(self, roles):
        self.events.append(("wheelhouses", tuple(roles)))

    def _store_resource(self, resource):
        kind = resource["kind"]
        metadata = resource["metadata"]
        name = metadata["name"]
        if kind == "Namespace":
            self.namespaces.add(name)
        elif kind == "ConfigMap":
            self.configmaps[name] = resource
        elif kind == "StatefulSet":
            self.statefulsets[name] = resource
        elif kind == "Service":
            self.services.add(name)
        elif kind == "Deployment" and name == GREEDY_FLOW_GENERATOR:
            self.flow_generator = True
        elif kind == "Job" and name == GREEDY_CONTROLLER_JOB:
            self.job_exists = True
            self.jobs_created += 1

    def _context(self):
        return {
            "current-context": GREEDY_CONTEXT,
            "contexts": [
                {"name": GREEDY_CONTEXT, "context": {"cluster": GREEDY_CONTEXT}}
            ],
            "clusters": [{"name": GREEDY_CONTEXT, "cluster": {"server": "https://x"}}],
        }

    def _namespaces(self):
        return namespace_document(
            greedy=GREEDY_NAMESPACE in self.namespaces,
            foreign=sorted(
                self.namespaces
                - {
                    "default",
                    "kube-system",
                    "kube-public",
                    "kube-node-lease",
                    GREEDY_NAMESPACE,
                }
            ),
        )

    def _pods(self):
        if GREEDY_NAMESPACE not in self.namespaces:
            return {"items": []}
        items = []
        for name, statefulset in sorted(self.statefulsets.items()):
            stage = int(name.rsplit("-", 1)[1])
            labels = dict(statefulset["spec"]["template"]["metadata"]["labels"])
            labels["greedy.max-assigned-flows"] = str(self.pod_capacity)
            for ordinal in range(statefulset["spec"]["replicas"]):
                pod_name = f"{name}-{ordinal}"
                items.append(
                    {
                        "metadata": {
                            "name": pod_name,
                            "namespace": GREEDY_NAMESPACE,
                            "uid": f"uid-{self.uid_generation}-{pod_name}",
                            "labels": labels,
                        },
                        "spec": {"nodeName": GREEDY_WORKER_NODE},
                        "status": {
                            "phase": "Running",
                            "conditions": [{"type": "Ready", "status": "True"}],
                            "containerStatuses": [
                                {"name": "private-processor", "restartCount": 0},
                                {"name": "public-forwarder", "restartCount": 0},
                            ],
                        },
                    }
                )
        if self.flow_generator:
            items.append(
                {
                    "metadata": {
                        "name": "greedy-flow-generator-abcde",
                        "namespace": GREEDY_NAMESPACE,
                        "uid": f"uid-{self.uid_generation}-flow-generator",
                        "labels": {
                            "app.kubernetes.io/name": GREEDY_FLOW_GENERATOR,
                            "app.kubernetes.io/part-of": GREEDY_PART_OF,
                            "app.kubernetes.io/component": "flow-generator",
                        },
                    },
                    "spec": {"nodeName": GREEDY_WORKER_NODE},
                    "status": {
                        "phase": "Running",
                        "conditions": [{"type": "Ready", "status": "True"}],
                        "containerStatuses": [
                            {"name": "flow-generator", "restartCount": 0}
                        ],
                    },
                }
            )
        return {"items": items}

    def _node_images(self):
        images = []
        for image, normalized in (
            (GREEDY_SERVICE_IMAGE, GREEDY_NORMALIZED_SERVICE_IMAGE),
            (GREEDY_CONTROLLER_IMAGE, GREEDY_NORMALIZED_CONTROLLER_IMAGE),
        ):
            if image in self.node_image_ids:
                images.append(
                    {
                        "id": "sha256:" + self.node_image_ids[image],
                        "repoTags": [normalized],
                    }
                )
        return {"images": images}

    def _owned_resources(self):
        items = list(self.statefulsets.values()) + list(self.configmaps.values())
        for service in sorted(self.services):
            if service.startswith("greedy-stage-"):
                labels = dict(self.statefulsets[service]["metadata"]["labels"])
            else:
                labels = {
                    "app.kubernetes.io/name": GREEDY_FLOW_GENERATOR,
                    "app.kubernetes.io/part-of": GREEDY_PART_OF,
                    "app.kubernetes.io/component": "flow-generator",
                }
            items.append(
                {
                    "kind": "Service",
                    "metadata": {
                        "name": service,
                        "namespace": GREEDY_NAMESPACE,
                        "labels": labels,
                    },
                }
            )
        if self.flow_generator:
            items.append(
                {
                    "kind": "Deployment",
                    "metadata": {
                        "name": GREEDY_FLOW_GENERATOR,
                        "namespace": GREEDY_NAMESPACE,
                        "labels": {
                            "app.kubernetes.io/name": GREEDY_FLOW_GENERATOR,
                            "app.kubernetes.io/part-of": GREEDY_PART_OF,
                            "app.kubernetes.io/component": "flow-generator",
                        },
                    },
                }
            )
        for kind, name in (
            ("ServiceAccount", "greedy-controller"),
            ("Role", "greedy-replica-discovery"),
            ("RoleBinding", "greedy-controller-discovers-replicas"),
        ):
            items.append(
                {
                    "kind": kind,
                    "metadata": {
                        "name": name,
                        "namespace": GREEDY_NAMESPACE,
                        "labels": {
                            "app.kubernetes.io/part-of": GREEDY_PART_OF,
                        },
                    },
                }
            )
        if self.job_exists:
            items.append(
                {
                    "kind": "Job",
                    "metadata": {
                        "name": GREEDY_CONTROLLER_JOB,
                        "namespace": GREEDY_NAMESPACE,
                        "labels": {
                            "app.kubernetes.io/part-of": GREEDY_PART_OF,
                        },
                    },
                }
            )
        items.extend(self.extra_owned_resources)
        return {"items": items}

    def execute(self, command, capture_output):
        self.commands.append(command)
        self.events.append(("command", command))
        if command == ("kind", "get", "clusters"):
            return (GREEDY_CLUSTER_NAME + "\n") if self.exists else ""
        if command[:3] == ("docker", "image", "inspect"):
            if "--format" in command:
                image = command[-1]
                identity = self.local_image_ids.get(image)
                return "" if identity is None else "sha256:" + identity + "\n"
            return "{}\n"
        if command[:3] == ("docker", "image", "save"):
            image = command[-1]
            identity = self.local_image_ids.get(image)
            if identity is None:
                raise RuntimeError(f"missing local image: {image}")
            archive_path = Path(command[command.index("--output") + 1])
            manifest_digest = "e" * 64
            documents = {
                "index.json": {
                    "manifests": [
                        {"digest": f"sha256:{manifest_digest}"}
                    ]
                },
                f"blobs/sha256/{manifest_digest}": {
                    "config": {"digest": f"sha256:{identity}"}
                },
            }
            with tarfile.open(archive_path, mode="w") as archive:
                for name, payload in documents.items():
                    encoded = json.dumps(payload).encode("utf-8")
                    member = tarfile.TarInfo(name)
                    member.size = len(encoded)
                    archive.addfile(member, io.BytesIO(encoded))
            return ""
        if command[:2] == ("docker", "build"):
            image = command[command.index("--tag") + 1]
            self.local_image_ids[image] = (
                "c" * 64 if image == GREEDY_SERVICE_IMAGE else "d" * 64
            )
            return ""
        if command[:4] == ("kind", "create", "cluster", "--name"):
            self.exists = True
            return ""
        if command[:4] == ("kind", "load", "docker-image", "--name"):
            for image in command[5:]:
                self.node_image_ids[image] = self.local_image_ids[image]
            return ""
        if command == ("kind", "get", "nodes", "--name", GREEDY_CLUSTER_NAME):
            return f"{GREEDY_CONTROL_PLANE_NODE}\n{GREEDY_WORKER_NODE}\n"
        if command[:2] == ("kind", "delete"):
            self.exists = False
            return ""
        if command[:3] == ("docker", "exec", GREEDY_CONTROL_PLANE_NODE) or command[:3] == (
            "docker",
            "exec",
            GREEDY_WORKER_NODE,
        ):
            return json.dumps(self._node_images())
        if command[:4] == ("kubectl", "config", "view", "--context"):
            return json.dumps(self._context())
        if command == (
            "kubectl",
            "--context",
            GREEDY_CONTEXT,
            "get",
            "nodes",
            "-o",
            "json",
        ):
            return json.dumps(
                node_document(cpu=self.worker_cpu, memory=self.worker_memory)
            )
        if command == (
            "kubectl",
            "--context",
            GREEDY_CONTEXT,
            "get",
            "namespaces",
            "-o",
            "json",
        ):
            return json.dumps(self._namespaces())
        if command == (
            "kubectl",
            "--context",
            GREEDY_CONTEXT,
            "get",
            "pods",
            "-A",
            "-o",
            "json",
        ):
            return json.dumps(self._pods())
        if command == (
            "kubectl",
            "--context",
            GREEDY_CONTEXT,
            "get",
            "pods",
            "-n",
            GREEDY_NAMESPACE,
            "-o",
            "json",
        ):
            return json.dumps(self._pods())
        if command == (
            "kubectl",
            "--context",
            GREEDY_CONTEXT,
            "get",
            "statefulsets",
            "-n",
            GREEDY_NAMESPACE,
            "-o",
            "json",
        ):
            return json.dumps({"items": list(self.statefulsets.values())})
        if command == (
            "kubectl",
            "--context",
            GREEDY_CONTEXT,
            "get",
            "configmaps",
            "-n",
            GREEDY_NAMESPACE,
            "-o",
            "json",
        ):
            return json.dumps({"items": list(self.configmaps.values())})
        if command == (
            "kubectl",
            "--context",
            GREEDY_CONTEXT,
            "get",
            "services,deployments,statefulsets,jobs,configmaps,serviceaccounts,roles,rolebindings",
            "-n",
            GREEDY_NAMESPACE,
            "-o",
            "json",
        ):
            return json.dumps(self._owned_resources())
        if command[:5] == (
            "kubectl",
            "--context",
            GREEDY_CONTEXT,
            "apply",
            "-f",
        ):
            path = Path(command[5])
            for resource in parse_resource_documents(path.read_text(encoding="utf-8")):
                self._store_resource(deepcopy(resource))
            return ""
        if "label" in command and "node" in command:
            return ""
        if "label" in command and "pods" in command:
            value = next(
                part for part in command if part.startswith("greedy.max-assigned-flows=")
            )
            self.pod_capacity = int(value.split("=", 1)[1])
            return ""
        if "scale" in command:
            count = int(
                next(part for part in command if part.startswith("--replicas=")).split(
                    "=", 1
                )[1]
            )
            for part in command:
                if part.startswith("statefulset/greedy-stage-"):
                    name = part.removeprefix("statefulset/")
                    self.statefulsets[name]["spec"]["replicas"] = count
            return ""
        if "delete" in command and "job" in command:
            self.job_exists = False
            return ""
        if "delete" in command and any(
            part.startswith("statefulset/greedy-stage-") for part in command
        ):
            for part in command:
                if part.startswith("statefulset/greedy-stage-"):
                    self.statefulsets.pop(part.removeprefix("statefulset/"), None)
                if part.startswith("service/greedy-stage-"):
                    self.services.discard(part.removeprefix("service/"))
            return ""
        if "rollout" in command and "restart" in command:
            self.uid_generation += 1
            return ""
        if "rollout" in command and "status" in command:
            return ""
        if "wait" in command:
            return ""
        return ""


def command_index(commands, predicate):
    return next(index for index, command in enumerate(commands) if predicate(command))


def test_cli_requires_every_dimension_and_finite_input_and_has_no_runs():
    parsed = parse_args(
        [
            "run",
            "--flow",
            "10",
            "--stage",
            "3",
            "--replica",
            "5",
            "--max-iterations",
            "50",
            "--profile-seed",
            "42",
        ]
    )
    assert (
        parsed.requested_flows,
        parsed.requested_stages,
        parsed.requested_replicas,
        parsed.max_iterations,
        parsed.profile_seed,
        parsed.rollout_batch_size,
        parsed.csv,
        parsed.parity_replay,
    ) == (10, 3, 5, 50, 42, 1, 0, 0)
    launch = launch_configuration_from_args(parsed, root_seed=2050)
    assert launch.configuration == GreedyConfiguration(10, 3, 5)
    assert launch.root_seed == 2050

    required = ("--flow", "--stage", "--replica", "--max-iterations", "--profile-seed")
    complete = [
        "run",
        "--flow", "10",
        "--stage", "3",
        "--replica", "5",
        "--max-iterations", "50",
        "--profile-seed", "42",
    ]
    for option in required:
        index = complete.index(option)
        with pytest.raises(SystemExit):
            parse_args(complete[:index] + complete[index + 2 :])
    with pytest.raises(SystemExit):
        parse_args(complete + ["--runs", "2"])
    with pytest.raises(SystemExit):
        parse_args([*complete[:5], "1", *complete[6:]])
    with pytest.raises(SystemExit):
        parse_args(complete + ["--rollout-batch-size", "0"])
    with pytest.raises(SystemExit):
        parse_args(complete + ["--csv", "2"])
    with pytest.raises(SystemExit):
        parse_args(complete + ["--parity-replay", "2"])


def test_phase5_hybrid_audit_is_exact_versioned_and_classified():
    assert GREEDY_PHASE5_HYBRID_AUDIT_HEAD == "f2e0065204570d9631f26953c94729b451ff92b5"
    assert len(GREEDY_PHASE5_HYBRID_SOURCE_AUDIT) == 10
    assert {item.disposition for item in GREEDY_PHASE5_HYBRID_SOURCE_AUDIT} == {
        "reuse",
        "adapt",
    }
    assert all(item.git_blob and ":" in item.source_location for item in GREEDY_PHASE5_HYBRID_SOURCE_AUDIT)
    findings = " ".join(item.finding for item in GREEDY_PHASE5_HYBRID_SOURCE_AUDIT)
    assert "exclude" in findings.lower() or "no series" in findings.lower()


def test_launch_flags_remain_public_only_and_cli_excludes_hybrid_controls():
    launch = make_launch(csv=1, parity_replay=1)
    assert (launch.csv, launch.parity_replay) == (1, 1)
    controller = launch.deployment.controller_document
    assert not hasattr(controller, "csv")
    assert not hasattr(controller, "parity_replay")
    source = (ROOT / "scripts" / "run_greedy_kernel.py").read_text(encoding="utf-8")
    assert "--runs" not in source
    assert "--policy" not in source
    assert "--mc-workers" not in source
    assert "ProcessPool" not in source
    help_result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_greedy_kernel.py"), "run", "--help"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    assert "--csv {0,1}" in help_result.stdout
    assert "--parity-replay {0,1}" in help_result.stdout
    assert "reserved" not in help_result.stdout.lower()


def test_profile_allocator_matches_hybrid_prefix_and_preserves_expansion():
    from IBG_Hybrid.kernel_profile_expansion import (
        generate_dynamic_topology_documents,
        seeded_hidden_state_sequence as hybrid_hidden_states,
    )
    from IBG_Hybrid.contracts import HybridConfiguration

    for stage in range(1, 4):
        assert seeded_hidden_state_sequence(
            stage=stage, replica_count=25, profile_seed=42
        ) == hybrid_hidden_states(
            stage=stage, replica_count=25, profile_seed=42
        )
    small = materialize_runtime_profiles(GreedyConfiguration(10, 3, 2), profile_seed=42)
    large = materialize_runtime_profiles(GreedyConfiguration(10, 3, 5), profile_seed=42)
    assert large.profiles[:2] == small.profiles[:2]
    small_by_identity = small.profile_by_identity()
    large_by_identity = large.profile_by_identity()
    assert all(large_by_identity[key] == value for key, value in small_by_identity.items())

    hybrid_runtime, _controller = generate_dynamic_topology_documents(
        canonical_runtime=json.loads(
            (ROOT / "deploy/hybrid-kubernetes-phase6-3x3x2/runtime-profiles.json").read_text()
        ),
        canonical_controller=json.loads(
            (ROOT / "deploy/hybrid-kubernetes-phase6-3x3x2/controller-inputs.json").read_text()
        ),
        configuration=HybridConfiguration(10, 3, 5, 2),
        profile_seed=42,
    )
    greedy_map = [
        (item.identity.stage, item.identity.replica, item.hidden_state, item.observation_seed)
        for item in large.profiles
    ]
    hybrid_map = [
        (item["stage"], item["replica"], item["hidden_state"], item["observation_seed"])
        for item in hybrid_runtime["profiles"]
    ]
    assert greedy_map == hybrid_map
    assert matched_observation_seed(large.profiles[0].identity) == 4101


def test_profile_transition_rejects_seed_or_retained_drift():
    old = materialize_runtime_profiles(GreedyConfiguration(4, 3, 2), profile_seed=17)
    target = materialize_runtime_profiles(GreedyConfiguration(8, 4, 3), profile_seed=17)
    transition = validate_profile_transition(
        deployed=old, proposed=target, profile_seed=17
    )
    assert len(transition.retained_identities) == 6
    assert len(transition.added_identities) == 6
    with pytest.raises(GreedyProfileReconciliationError, match="profile seed"):
        validate_profile_transition(
            deployed=old,
            proposed=materialize_runtime_profiles(
                GreedyConfiguration(4, 3, 2), profile_seed=18
            ),
            profile_seed=18,
        )
    drifted = deepcopy(launcher_state_to_mapping(
        GreedyLauncherState(
            stable_configuration=old.configuration,
            target_configuration=old.configuration,
            profile_seed=17,
            profile_fingerprint=old.fingerprint,
            service_source_fingerprint="s",
            controller_source_fingerprint="c",
            service_image_id=SERVICE_ID,
            controller_image_id=CONTROLLER_ID,
            transition_active=False,
        )
    ))
    assert launcher_state_from_mapping(drifted).profile_fingerprint == old.fingerprint


def test_arbitrary_stage_rollout_is_bounded_high_suffix_only_and_exact_ready():
    deployment = deployment_for(GreedyConfiguration(8, 4, 3))
    statefulsets = {
        "items": [
            item for item in render_long_running_resources(deployment)
            if item["kind"] == "StatefulSet"
        ]
    }
    current = discover_existing_topology(statefulsets)
    plan = plan_topology_reconciliation(
        current,
        GreedyConfiguration(8, 6, 7),
        rollout_batch_size=2,
    )
    assert tuple(batch.target_count for batch in plan.replica_batches) == (5, 7)
    assert plan.added_stages == (5, 6)
    down = plan_topology_reconciliation(
        current,
        GreedyConfiguration(8, 2, 1),
        rollout_batch_size=1,
    )
    assert down.removed_stages == (4, 3)
    assert down.replica_batches[0].removed_ordinals == (1, 2)

    cluster = FakeGreedyCluster(configuration=GreedyConfiguration(8, 4, 3))
    validate_ready_coverage(
        cluster._pods(), configuration=GreedyConfiguration(8, 4, 3)
    )
    missing = cluster._pods()
    missing["items"].pop(0)
    with pytest.raises(GreedyKernelRolloutError, match="coverage mismatch"):
        validate_ready_coverage(
            missing, configuration=GreedyConfiguration(8, 4, 3)
        )


def test_fresh_bootstrap_orders_offline_build_nodes_images_ready_and_one_job():
    cluster = FakeGreedyCluster(existing=False, configuration=GreedyConfiguration(5, 3, 3))
    result = run_greedy_lifecycle(
        make_launch(5, 3, 3, rollout_batch_size=1),
        execute=cluster.execute,
        validate_wheelhouses=cluster.wheelhouses,
    )
    commands = cluster.commands
    first_docker = command_index(commands, lambda command: command[0] == "docker")
    wheel = next(index for index, event in enumerate(cluster.events) if event[0] == "wheelhouses")
    first_docker_event = next(
        index
        for index, event in enumerate(cluster.events)
        if event[0] == "command" and event[1][0] == "docker"
    )
    assert wheel < first_docker_event
    builds = [command for command in commands if command[:2] == ("docker", "build")]
    assert len(builds) == 2
    assert all("--pull=false" in command and "--network=none" in command for command in builds)
    assert first_docker >= 0
    assert result.cluster_created is True
    assert result.built_images == ("service", "controller")
    assert result.loaded_images == ("service", "controller")
    assert result.controller_jobs_created == cluster.jobs_created == 1
    assert set(cluster.statefulsets) == {"greedy-stage-1", "greedy-stage-2", "greedy-stage-3"}
    assert {item["spec"]["replicas"] for item in cluster.statefulsets.values()} == {3}
    load_index = command_index(commands, lambda command: command[:4] == ("kind", "load", "docker-image", "--name"))
    first_apply = command_index(commands, lambda command: "apply" in command)
    resource_reads = [
        index
        for index, command in enumerate(commands)
        if command[-4:] == ("get", "nodes", "-o", "json")
    ]
    assert resource_reads and resource_reads[-1] < first_apply
    assert load_index < first_apply
    job_apply = max(index for index, command in enumerate(commands) if "apply" in command)
    last_ready = max(index for index, command in enumerate(commands) if "rollout" in command and "status" in command)
    assert last_ready < job_apply


def test_skip_build_fresh_refuses_and_existing_equal_is_serving_noop():
    fresh = FakeGreedyCluster(existing=False)
    wheel_calls = []
    with pytest.raises(GreedyLifecycleError, match="cannot bootstrap"):
        run_greedy_lifecycle(
            make_launch(skip_build=True),
            execute=fresh.execute,
            validate_wheelhouses=lambda roles: wheel_calls.append(tuple(roles)),
        )
    assert wheel_calls == []
    assert not any(command[:2] == ("docker", "build") for command in fresh.commands)

    cluster = FakeGreedyCluster()
    before = cluster._pods()
    result = run_greedy_lifecycle(
        make_launch(skip_build=True),
        execute=cluster.execute,
        validate_wheelhouses=lambda roles: pytest.fail("wheelhouse validation ran"),
    )
    serving_mutations = [
        command
        for command in cluster.commands
        if "scale" in command
        or ("rollout" in command and "restart" in command)
        or ("label" in command and "pods" in command)
        or (
            "delete" in command
            and any(part.startswith("statefulset/") for part in command)
        )
    ]
    assert serving_mutations == []
    assert result.serving_changed is False
    assert before == cluster._pods()
    assert not any(command[:2] == ("docker", "build") for command in cluster.commands)
    assert not any(command[:4] == ("kind", "load", "docker-image", "--name") for command in cluster.commands)

    missing_local = FakeGreedyCluster()
    missing_local.local_image_ids.pop(GREEDY_CONTROLLER_IMAGE)
    with pytest.raises(GreedyLifecycleError, match="local image"):
        run_greedy_lifecycle(
            make_launch(skip_build=True),
            execute=missing_local.execute,
            validate_wheelhouses=lambda roles: None,
        )
    assert missing_local.jobs_created == 0

    missing_node = FakeGreedyCluster()
    missing_node.node_image_ids.pop(GREEDY_SERVICE_IMAGE)
    with pytest.raises(GreedyLifecycleError, match="absent or mismatched"):
        run_greedy_lifecycle(
            make_launch(skip_build=True),
            execute=missing_node.execute,
            validate_wheelhouses=lambda roles: None,
        )
    assert missing_node.jobs_created == 0


def test_flow_only_change_updates_capacity_and_controller_without_serving_restart():
    cluster = FakeGreedyCluster(configuration=GreedyConfiguration(4, 3, 2))
    before = cluster._pods()
    result = run_greedy_lifecycle(
        make_launch(9, 3, 2, skip_build=True),
        execute=cluster.execute,
        validate_wheelhouses=lambda roles: None,
    )
    assert result.serving_changed is False
    assert cluster.pod_capacity == 5
    assert not any("scale" in command for command in cluster.commands)
    assert not any("restart" in command for command in cluster.commands)
    after = cluster._pods()
    assert {
        item["metadata"]["name"]: item["metadata"]["uid"] for item in before["items"]
    } == {
        item["metadata"]["name"]: item["metadata"]["uid"] for item in after["items"]
    }
    controller_text = cluster.configmaps[GREEDY_CONTROLLER_INPUT_CONFIG_MAP]["data"][
        "controller-inputs.json"
    ]
    assert json.loads(controller_text)["configuration"]["num_flows"] == 9


def test_replica_scale_up_is_batched_all_stage_ready_before_job():
    cluster = FakeGreedyCluster(configuration=GreedyConfiguration(4, 3, 1))
    run_greedy_lifecycle(
        make_launch(4, 3, 5, rollout_batch_size=2, skip_build=True),
        execute=cluster.execute,
        validate_wheelhouses=lambda roles: None,
    )
    scales = [command for command in cluster.commands if "scale" in command]
    assert [
        next(part for part in command if part.startswith("--replicas="))
        for command in scales
    ] == ["--replicas=3", "--replicas=5"]
    assert all(
        all(f"statefulset/greedy-stage-{stage}" in command for stage in range(1, 4))
        for command in scales
    )
    job_apply = max(index for index, command in enumerate(cluster.commands) if "apply" in command)
    last_ready = max(
        index
        for index, command in enumerate(cluster.commands)
        if "rollout" in command and "status" in command
    )
    assert last_ready < job_apply


def test_scale_down_and_stage_changes_remove_only_high_suffix_and_preserve_prefix():
    cluster = FakeGreedyCluster(configuration=GreedyConfiguration(8, 4, 4))
    before = {item["metadata"]["name"]: item["metadata"]["uid"] for item in cluster._pods()["items"]}
    run_greedy_lifecycle(
        make_launch(8, 2, 2, skip_build=True),
        execute=cluster.execute,
        validate_wheelhouses=lambda roles: None,
    )
    assert set(cluster.statefulsets) == {"greedy-stage-1", "greedy-stage-2"}
    assert {item["spec"]["replicas"] for item in cluster.statefulsets.values()} == {2}
    delete_commands = [command for command in cluster.commands if "delete" in command]
    assert any("statefulset/greedy-stage-4" in command for command in delete_commands)
    assert any("statefulset/greedy-stage-3" in command for command in delete_commands)
    assert not any("statefulset/greedy-stage-1" in command for command in delete_commands)
    after = {item["metadata"]["name"]: item["metadata"]["uid"] for item in cluster._pods()["items"]}
    assert all(after[name] == before[name] for name in after)

    expansion = FakeGreedyCluster(configuration=GreedyConfiguration(8, 2, 2))
    run_greedy_lifecycle(
        make_launch(8, 5, 2, skip_build=True),
        execute=expansion.execute,
        validate_wheelhouses=lambda roles: None,
    )
    assert set(expansion.statefulsets) == {
        "greedy-stage-1",
        "greedy-stage-2",
        "greedy-stage-3",
        "greedy-stage-4",
        "greedy-stage-5",
    }


def test_interrupted_marked_transition_recovers_but_unmarked_partial_refuses():
    stable = GreedyConfiguration(4, 3, 2)
    target = GreedyConfiguration(4, 4, 3)
    cluster = FakeGreedyCluster(configuration=target)
    # Represent an interrupted all-stage scale command: one stage is still at 2.
    cluster.statefulsets["greedy-stage-2"]["spec"]["replicas"] = 2
    fingerprints = image_source_fingerprints()
    transition = GreedyLauncherState(
        stable_configuration=stable,
        target_configuration=target,
        profile_seed=17,
        profile_fingerprint=materialize_runtime_profiles(target, profile_seed=17).fingerprint,
        service_source_fingerprint=fingerprints["service"],
        controller_source_fingerprint=fingerprints["controller"],
        service_image_id=SERVICE_ID,
        controller_image_id=CONTROLLER_ID,
        transition_active=True,
    )
    cluster._store_resource(_launcher_state_resource(transition))
    run_greedy_lifecycle(
        make_launch(4, 4, 3, skip_build=True),
        execute=cluster.execute,
        validate_wheelhouses=lambda roles: None,
    )
    assert {item["spec"]["replicas"] for item in cluster.statefulsets.values()} == {3}

    unsafe = FakeGreedyCluster(configuration=target)
    unsafe.statefulsets["greedy-stage-2"]["spec"]["replicas"] = 2
    with pytest.raises(GreedyLifecycleError, match="unmarked partial"):
        run_greedy_lifecycle(
            make_launch(4, 4, 3, skip_build=True),
            execute=unsafe.execute,
            validate_wheelhouses=lambda roles: None,
        )
    assert unsafe.jobs_created == 0


def test_resource_and_foreign_inventory_refuse_before_topology_or_job():
    cluster = FakeGreedyCluster(worker_cpu="100m", worker_memory="128Gi")
    with pytest.raises(GreedyLifecycleError, match="resource preflight"):
        run_greedy_lifecycle(
            make_launch(10, 3, 5, skip_build=True),
            execute=cluster.execute,
            validate_wheelhouses=lambda roles: None,
        )
    assert not any("apply" in command or "scale" in command for command in cluster.commands)
    assert cluster.jobs_created == 0

    with pytest.raises(GreedyLifecycleError, match="foreign namespaces"):
        validate_cluster_inventory(
            nodes=node_document(),
            namespaces=namespace_document(foreign=("foreign",)),
            pods={"items": []},
        )
    foreign_pod = {
        "metadata": {
            "name": "foreign",
            "namespace": GREEDY_NAMESPACE,
            "labels": {"app.kubernetes.io/part-of": "foreign"},
        },
        "spec": {"nodeName": GREEDY_WORKER_NODE},
    }
    with pytest.raises(GreedyLifecycleError, match="foreign workload"):
        validate_cluster_inventory(
            nodes=node_document(),
            namespaces=namespace_document(),
            pods={"items": [foreign_pod]},
        )


def test_profile_fingerprint_drift_refuses_before_mutation():
    cluster = FakeGreedyCluster()
    runtime = cluster.configmaps[GREEDY_RUNTIME_PROFILE_CONFIG_MAP]
    value = json.loads(runtime["data"]["runtime-profiles.json"])
    value["profiles"][0]["hidden_state"] = (
        value["profiles"][0]["hidden_state"] % 4
    ) + 1
    runtime["data"]["runtime-profiles.json"] = json.dumps(value)
    with pytest.raises((GreedyLifecycleError, GreedyProfileReconciliationError), match="drift"):
        run_greedy_lifecycle(
            make_launch(skip_build=True),
            execute=cluster.execute,
            validate_wheelhouses=lambda roles: None,
        )
    assert not any("apply" in command or "scale" in command for command in cluster.commands)


def test_change_scoped_build_rebuilds_only_controller_and_not_serving(monkeypatch):
    current = image_source_fingerprints()
    monkeypatch.setattr(
        "Greedy.kernel_lifecycle.image_source_fingerprints",
        lambda: {"service": current["service"], "controller": "changed-controller"},
    )
    skip_cluster = FakeGreedyCluster()
    with pytest.raises(GreedyLifecycleError, match="source provenance changed"):
        run_greedy_lifecycle(
            make_launch(skip_build=True),
            execute=skip_cluster.execute,
            validate_wheelhouses=skip_cluster.wheelhouses,
        )
    assert not any(
        command[:2] in (("docker", "build"), ("kind", "load"))
        or "apply" in command
        or "scale" in command
        for command in skip_cluster.commands
    )

    cluster = FakeGreedyCluster()
    result = run_greedy_lifecycle(
        make_launch(),
        execute=cluster.execute,
        validate_wheelhouses=cluster.wheelhouses,
    )
    builds = [command for command in cluster.commands if command[:2] == ("docker", "build")]
    assert len(builds) == 1
    assert str(ROOT / "deploy/greedy-kubernetes/Dockerfile.controller") in builds[0]
    assert result.built_images == ("controller",)
    assert result.loaded_images == ("controller",)
    assert not any("restart" in command for command in cluster.commands)


def test_cleanup_is_explicit_greedy_only_and_refuses_ambiguous_ownership():
    cluster = FakeGreedyCluster()
    cleanup(execute=cluster.execute)
    assert cluster.commands[-1] == (
        "kind",
        "delete",
        "cluster",
        "--name",
        GREEDY_CLUSTER_NAME,
    )
    assert not cluster.exists

    foreign = FakeGreedyCluster()
    foreign.namespaces.add("ibg-hybrid-testbed")
    with pytest.raises(GreedyLifecycleError, match="foreign baseline"):
        cleanup(execute=foreign.execute)
    assert foreign.exists
    assert not any(command[:2] == ("kind", "delete") for command in foreign.commands)

    wrong_owner = FakeGreedyCluster()
    wrong_owner.extra_owned_resources.append(
        {
            "kind": "Service",
            "metadata": {
                "name": "foreign-service",
                "namespace": GREEDY_NAMESPACE,
                "labels": {"app.kubernetes.io/part-of": "foreign"},
            },
        }
    )
    with pytest.raises(GreedyLifecycleError, match="foreign or unexpected"):
        cleanup(execute=wrong_owner.execute)
    assert wrong_owner.exists


def test_preflight_is_read_only():
    cluster = FakeGreedyCluster()
    preflight(execute=cluster.execute)
    assert cluster.commands
    assert all(
        command[:3] == ("kind", "get", "clusters")
        or command[:2] == ("kubectl", "config")
        or (command[:3] == ("kubectl", "--context", GREEDY_CONTEXT) and "get" in command)
        for command in cluster.commands
    )


def test_root_seed_is_profile_independent_and_does_not_use_global_rng():
    seen = []
    assert resolve_root_seed(lambda bits: seen.append(bits) or 1234) == 1234
    assert seen == [63]
    first = make_launch(profile_seed=1, root_seed=999)
    second = make_launch(profile_seed=2, root_seed=999)
    assert first.root_seed == second.root_seed == 999
    assert first.runtime_profiles != second.runtime_profiles

    python_state = random.getstate()
    numpy_state = np.random.get_state()
    materialize_runtime_profiles(GreedyConfiguration(10, 4, 5), profile_seed=42)
    assert random.getstate() == python_state
    after = np.random.get_state()
    assert after[0] == numpy_state[0]
    assert np.array_equal(after[1], numpy_state[1])
    assert after[2:] == numpy_state[2:]


def test_repeated_fake_execution_is_deterministic_and_inputs_are_immutable():
    launch = make_launch(skip_build=True)
    before = deepcopy(launch)
    first = FakeGreedyCluster()
    second = FakeGreedyCluster()
    first_result = run_greedy_lifecycle(
        launch, execute=first.execute, validate_wheelhouses=lambda roles: None
    )
    second_result = run_greedy_lifecycle(
        launch, execute=second.execute, validate_wheelhouses=lambda roles: None
    )
    assert first_result == second_result
    def normalized(commands):
        return tuple(
            tuple("<temporary>" if index > 0 and command[index - 1] in {"-f", "--output"} else part
                  for index, part in enumerate(command))
            for command in commands
        )

    assert normalized(first.commands) == normalized(second.commands)
    assert launch == before


def test_phase5_imports_are_silent_rng_neutral_and_file_safe(tmp_path):
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    code = (
        "import random,numpy as np;random.seed(57);np.random.seed(75);"
        "p=random.getstate();n=np.random.get_state();"
        "import Greedy.kernel_profile_reconciliation,Greedy.kernel_rollout;"
        "import Greedy.kernel_lifecycle,scripts.run_greedy_kernel;"
        "assert random.getstate()==p;a=np.random.get_state();"
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

    lifecycle_source = (ROOT / "Greedy/kernel_lifecycle.py").read_text()
    launcher_source = (ROOT / "scripts/run_greedy_kernel.py").read_text()
    assert "IBG_Hybrid" not in lifecycle_source
    assert "IBG_Hybrid" not in launcher_source
    assert "ProcessPool" not in lifecycle_source + launcher_source
    assert "Monte Carlo" not in lifecycle_source + launcher_source
    assert inspect.signature(run_greedy_lifecycle).parameters["launch"].default is inspect.Parameter.empty
    assert set(SERVICE_SOURCE_FILES).isdisjoint({"Greedy/policy.py", "Greedy/kernel_controller.py"})
    assert "Greedy/policy.py" in CONTROLLER_SOURCE_FILES
