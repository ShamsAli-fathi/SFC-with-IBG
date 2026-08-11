import copy
import json
import os
from pathlib import Path
import random
from types import SimpleNamespace
import subprocess
import sys

import pytest
import numpy as np

from IBG_Hybrid.contracts import (
    GlobalLoadState,
    HybridConfiguration,
    ReplicaChoice,
)
from IBG_Hybrid.kernel_controller_config import (
    controller_input_document_from_mapping,
)
from IBG_Hybrid.kernel_dynamic_topology_evidence import (
    HybridKernelDynamicTopologyEvidenceError,
    validate_dynamic_lookahead_slots,
)
from IBG_Hybrid.kernel_infrastructure_contract import (
    DEFAULT_HYBRID_KERNEL_OWNERSHIP,
)
from IBG_Hybrid.kernel_phase4_validation import run_small_live_gate
from IBG_Hybrid.kernel_profile_expansion import (
    HYBRID_PROFILE_STATE_ALLOCATION_VERSION,
    HYBRID_PROFILE_STATE_ORDER,
    HybridKernelProfileExpansionError,
    assigned_flow_capacity,
    generate_dynamic_topology_documents,
    seeded_hidden_state_sequence,
    seeded_profile_state_counts,
    validate_dynamic_topology_transition,
)
from IBG_Hybrid.kernel_runtime_profiles import (
    runtime_profile_document_from_mapping,
)
from IBG_Hybrid.phase0_contract import DEFAULT_HYBRID_POLICY_PARAMETERS
from IBG_Hybrid.runner import run_hybrid_slot
from IBG_Hybrid.slot_contracts import HybridFlow, HybridReplica, HybridSlotInput
from scripts import run_hybrid_kernel_phase4 as runner


ROOT = Path(__file__).resolve().parents[1]
PHASE4 = ROOT / "deploy" / "hybrid-kubernetes-phase4-small"
PHASE6 = ROOT / "deploy" / "hybrid-kubernetes-phase6-3x3x2"
PHASE8 = ROOT / "deploy" / "hybrid-kubernetes-phase8-gate1-4x3x2"
SERVICE_ID = "a" * 64
CONTROLLER_ID = "b" * 64


def _mapping(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_documents():
    return (
        _mapping(PHASE6 / "runtime-profiles.json"),
        _mapping(PHASE6 / "controller-inputs.json"),
    )


def _generated(flows=10, replicas=5, profile_seed=None):
    runtime, controller = _canonical_documents()
    configuration = HybridConfiguration(flows, 3, replicas, 2)
    return (
        configuration,
        *generate_dynamic_topology_documents(
            canonical_runtime=runtime,
            canonical_controller=controller,
            configuration=configuration,
            profile_seed=profile_seed,
        ),
    )


def test_completed_dynamic_controller_pod_remains_owned_during_rerun_preflight():
    runner.validate_cluster_inventory(
        nodes={"items": [{"metadata": {"name": "ibg-hybrid-control-plane"}}]},
        namespaces={
            "items": [
                {"metadata": {"name": name}}
                for name in (
                    "default",
                    "kube-system",
                    "local-path-storage",
                    runner.HYBRID_NAMESPACE,
                )
            ]
        },
        pods={
            "items": [
                {
                    "metadata": {
                        "name": "ibg-hybrid-controller-dynamic-abcde",
                        "namespace": runner.HYBRID_NAMESPACE,
                        "labels": {
                            "app.kubernetes.io/name": "ibg-hybrid-controller",
                            "app.kubernetes.io/part-of": "ibg-hybrid-testbed",
                        },
                    },
                    "status": {"phase": "Succeeded"},
                }
            ]
        },
    )


def test_dynamic_documents_are_deterministic_complete_and_append_only():
    configuration, runtime, controller = _generated()
    repeated = _generated()
    assert repeated == (configuration, runtime, controller)
    assert json.dumps(runtime, sort_keys=True, separators=(",", ":")) == json.dumps(
        repeated[1], sort_keys=True, separators=(",", ":")
    )
    assert len(runtime["profiles"]) == 15
    assert len(controller["admission"]) == 15
    assert len(controller["planning_pair_links"]) == 75
    assert {item["max_assigned_flows"] for item in controller["admission"]} == {2}
    assert len({item["observation_seed"] for item in runtime["profiles"]}) == 15
    assert "belief" not in json.dumps(runtime).lower()
    assert "belief" not in json.dumps(controller).lower()
    assert "hidden_state" not in json.dumps(controller)
    assert "observation_seed" not in json.dumps(controller)

    old_runtime, old_controller = _canonical_documents()
    old_profiles = {
        (item["stage"], item["replica"]): item
        for item in old_runtime["profiles"]
    }
    new_profiles = {
        (item["stage"], item["replica"]): item
        for item in runtime["profiles"]
    }
    assert all(new_profiles[choice] == item for choice, item in old_profiles.items())
    old_links = {
        (
            item["source_stage"],
            item["source_replica"],
            item["target_stage"],
            item["target_replica"],
        ): item["latency_ms"]
        for item in old_controller["planning_pair_links"]
    }
    new_links = {
        (
            item["source_stage"],
            item["source_replica"],
            item["target_stage"],
            item["target_replica"],
        ): item["latency_ms"]
        for item in controller["planning_pair_links"]
    }
    assert all(new_links[pair] == value for pair, value in old_links.items())


def test_historical_generated_documents_match_all_accepted_projections():
    canonical_runtime, canonical_controller = _canonical_documents()
    for flows, replicas, directory in (
        (2, 1, PHASE4),
        (3, 2, PHASE6),
        (4, 2, PHASE8),
    ):
        runtime, controller = generate_dynamic_topology_documents(
            canonical_runtime=canonical_runtime,
            canonical_controller=canonical_controller,
            configuration=HybridConfiguration(flows, 3, replicas, 2),
        )
        assert runtime == _mapping(directory / "runtime-profiles.json")
        assert controller == _mapping(directory / "controller-inputs.json")


def test_dynamic_transition_accepts_formula_changes_and_rejects_drift():
    canonical_runtime, canonical_controller = _canonical_documents()
    deployed_runtime = _mapping(PHASE8 / "runtime-profiles.json")
    deployed_controller = _mapping(PHASE8 / "controller-inputs.json")
    configuration = HybridConfiguration(5, 3, 2, 2)
    proposed_runtime, proposed_controller = generate_dynamic_topology_documents(
        canonical_runtime=canonical_runtime,
        canonical_controller=canonical_controller,
        configuration=configuration,
    )
    transition = validate_dynamic_topology_transition(
        deployed_runtime=deployed_runtime,
        deployed_controller=deployed_controller,
        proposed_runtime=proposed_runtime,
        proposed_controller=proposed_controller,
        canonical_runtime=canonical_runtime,
        canonical_controller=canonical_controller,
        existing_replica_count=2,
        target_configuration=configuration,
    )
    assert assigned_flow_capacity(configuration) == 3
    assert len(transition.changed_admission_identities) == 6
    assert transition.added_runtime_identities == ()

    mutations = []
    drifted_runtime = copy.deepcopy(deployed_runtime)
    drifted_runtime["profiles"][0]["hidden_state"] = 1
    mutations.append((drifted_runtime, deployed_controller, proposed_runtime, proposed_controller))
    drifted_seed = copy.deepcopy(deployed_runtime)
    drifted_seed["profiles"][0]["observation_seed"] = 999
    mutations.append((drifted_seed, deployed_controller, proposed_runtime, proposed_controller))
    drifted_admission = copy.deepcopy(deployed_controller)
    drifted_admission["admission"][0]["max_assigned_flows"] = 99
    mutations.append((deployed_runtime, drifted_admission, proposed_runtime, proposed_controller))
    drifted_link = copy.deepcopy(deployed_controller)
    drifted_link["planning_pair_links"][0]["latency_ms"] = 99.0
    mutations.append((deployed_runtime, drifted_link, proposed_runtime, proposed_controller))
    partial = copy.deepcopy(proposed_runtime)
    partial["profiles"].pop()
    mutations.append((deployed_runtime, deployed_controller, partial, proposed_controller))
    for current_runtime, current_controller, target_runtime, target_controller in mutations:
        with pytest.raises(HybridKernelProfileExpansionError):
            validate_dynamic_topology_transition(
                deployed_runtime=current_runtime,
                deployed_controller=current_controller,
                proposed_runtime=target_runtime,
                proposed_controller=target_controller,
                canonical_runtime=canonical_runtime,
                canonical_controller=canonical_controller,
                existing_replica_count=2,
                target_configuration=configuration,
            )


def test_dynamic_transition_accepts_only_deterministic_high_ordinal_removal():
    canonical_runtime, canonical_controller = _canonical_documents()
    deployed_configuration = HybridConfiguration(10, 3, 8, 2)
    target_configuration = HybridConfiguration(10, 3, 5, 2)
    deployed_runtime, deployed_controller = generate_dynamic_topology_documents(
        canonical_runtime=canonical_runtime,
        canonical_controller=canonical_controller,
        configuration=deployed_configuration,
    )
    proposed_runtime, proposed_controller = generate_dynamic_topology_documents(
        canonical_runtime=canonical_runtime,
        canonical_controller=canonical_controller,
        configuration=target_configuration,
    )

    transition = validate_dynamic_topology_transition(
        deployed_runtime=deployed_runtime,
        deployed_controller=deployed_controller,
        proposed_runtime=proposed_runtime,
        proposed_controller=proposed_controller,
        canonical_runtime=canonical_runtime,
        canonical_controller=canonical_controller,
        existing_replica_count=8,
        target_configuration=target_configuration,
    )

    assert len(transition.retained_runtime_identities) == 15
    assert {
        choice.replica for choice in transition.removed_runtime_identities
    } == {6, 7, 8}
    assert transition.added_runtime_identities == ()
    assert transition.removed_admission_identities == (
        transition.removed_runtime_identities
    )
    assert transition.changed_admission_identities == ()
    assert len(transition.retained_planning_pairs) == 75
    assert len(transition.removed_planning_pairs) == 117
    assert all(
        source.replica > 5 or target.replica > 5
        for source, target in transition.removed_planning_pairs
    )

    retained_drift = copy.deepcopy(proposed_runtime)
    retained_drift["profiles"][0]["observation_seed"] += 1
    with pytest.raises(HybridKernelProfileExpansionError, match="deterministic"):
        validate_dynamic_topology_transition(
            deployed_runtime=deployed_runtime,
            deployed_controller=deployed_controller,
            proposed_runtime=retained_drift,
            proposed_controller=proposed_controller,
            canonical_runtime=canonical_runtime,
            canonical_controller=canonical_controller,
            existing_replica_count=8,
            target_configuration=target_configuration,
        )

    deployed_source_drift = copy.deepcopy(deployed_controller)
    deployed_source_drift["source_identity"] = "foreign-source"
    with pytest.raises(HybridKernelProfileExpansionError, match="versioned rule"):
        validate_dynamic_topology_transition(
            deployed_runtime=deployed_runtime,
            deployed_controller=deployed_source_drift,
            proposed_runtime=proposed_runtime,
            proposed_controller=proposed_controller,
            canonical_runtime=canonical_runtime,
            canonical_controller=canonical_controller,
            existing_replica_count=8,
            target_configuration=target_configuration,
        )


def test_arbitrary_positive_cli_and_invalid_dimensions_fail_before_contact():
    parsed = runner.parse_args(
        [
            "run-small",
            "--skip-build",
            "--flows",
            "10",
            "--stages",
            "3",
            "--replicas",
            "5",
            "--rollout-batch-size",
            "2",
        ]
    )
    assert (parsed.requested_flows, parsed.requested_stages, parsed.requested_replicas) == (
        10,
        3,
        5,
    )
    assert parsed.rollout_batch_size == 2
    assert "APPROVED_PROFILE_BOUNDARIES" not in (
        ROOT / "scripts" / "run_hybrid_kernel_phase4.py"
    ).read_text(encoding="utf-8")

    for flows, stages, replicas in ((0, 3, 1), (1, 0, 1), (1, 4, 1), (1, 3, 0)):
        commands = []
        with pytest.raises(RuntimeError):
            runner.run_small(
                requested_flows=flows,
                requested_stages=stages,
                requested_replicas=replicas,
                execute=lambda command, capture: commands.append(command) or "",
            )
        assert commands == []


def _statefulsets(replicas):
    ownership = DEFAULT_HYBRID_KERNEL_OWNERSHIP
    items = []
    for stage in range(1, 4):
        labels = dict(ownership.replica_labels(stage))
        items.append(
            {
                "apiVersion": "apps/v1",
                "kind": "StatefulSet",
                "metadata": {
                    "name": f"hybrid-stage-{stage}",
                    "namespace": runner.HYBRID_NAMESPACE,
                    "labels": labels,
                },
                "spec": {
                    "serviceName": f"hybrid-stage-{stage}",
                    "replicas": replicas,
                    "selector": {
                        "matchLabels": dict(ownership.replica_selector(stage))
                    },
                    "template": {
                        "metadata": {"labels": labels},
                        "spec": {
                            "containers": [
                                {
                                    "name": "private-processor",
                                    "resources": {
                                        "requests": {"cpu": "50m", "memory": "64Mi"}
                                    },
                                },
                                {
                                    "name": "public-forwarder",
                                    "resources": {
                                        "requests": {"cpu": "25m", "memory": "128Mi"}
                                    },
                                },
                            ]
                        },
                    },
                },
            }
        )
    return {"items": items}


def _pods(replicas, generations=None):
    generations = {} if generations is None else generations
    ownership = DEFAULT_HYBRID_KERNEL_OWNERSHIP
    items = []
    for stage in range(1, 4):
        for ordinal in range(replicas):
            name = f"hybrid-stage-{stage}-{ordinal}"
            items.append(
                {
                    "metadata": {
                        "name": name,
                        "namespace": runner.HYBRID_NAMESPACE,
                        "uid": f"uid-{name}-generation-{generations.get(name, 0)}",
                        "labels": dict(ownership.replica_labels(stage)),
                    },
                    "spec": _statefulsets(replicas)["items"][stage - 1]["spec"][
                        "template"
                    ]["spec"],
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
    items.append(
        {
            "metadata": {
                "name": "ibg-hybrid-flow-generator-abcde",
                "namespace": runner.HYBRID_NAMESPACE,
                "uid": "uid-flow-generator",
                "labels": {
                    "app.kubernetes.io/name": "ibg-hybrid-flow-generator",
                    "app.kubernetes.io/part-of": "ibg-hybrid-testbed",
                },
            },
            "spec": {
                "containers": [
                    {
                        "name": "flow-generator",
                        "resources": {
                            "requests": {"cpu": "50m", "memory": "128Mi"}
                        },
                    }
                ]
            },
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


def _names(names):
    return {"items": [{"metadata": {"name": name}} for name in names]}


def _configmaps(runtime, controller):
    return {
        "items": [
            {
                "metadata": {
                    "name": "ibg-hybrid-runtime-profiles",
                    "namespace": runner.HYBRID_NAMESPACE,
                },
                "data": {"runtime-profiles.json": json.dumps(runtime)},
            },
            {
                "metadata": {
                    "name": "ibg-hybrid-planning-links",
                    "namespace": runner.HYBRID_NAMESPACE,
                },
                "data": {"controller-inputs.json": json.dumps(controller)},
            },
        ]
    }


class FakeDynamicCluster:
    def __init__(self, *, replicas=2, flows=4, profile_seed=None):
        self.replicas = replicas
        _configuration, self.runtime, self.controller = _generated(
            flows=flows, replicas=replicas, profile_seed=profile_seed
        )
        self.commands = []
        self.rollout_events = []
        self.pod_generations = {}

    def execute(self, command, capture_output):
        self.commands.append((command, capture_output))
        if command == ("kind", "get", "clusters"):
            return "ibg-hybrid\n"
        if command == runner._kubectl("get", "nodes", "-o", "json"):
            document = _names(["ibg-hybrid-control-plane"])
            document["items"][0]["status"] = {
                "allocatable": {"cpu": "4", "memory": "16Gi"}
            }
            return json.dumps(document)
        if command == runner._kubectl("get", "namespaces", "-o", "json"):
            return json.dumps(
                _names(["default", "kube-system", runner.HYBRID_NAMESPACE])
            )
        if command in {
            runner._kubectl("get", "pods", "-A", "-o", "json"),
            runner._kubectl(
                "get", "pods", "-n", runner.HYBRID_NAMESPACE, "-o", "json"
            ),
        }:
            return json.dumps(_pods(self.replicas, self.pod_generations))
        if command == runner._kubectl(
            "get", "statefulsets", "-n", runner.HYBRID_NAMESPACE, "-o", "json"
        ):
            return json.dumps(_statefulsets(self.replicas))
        if command == runner._kubectl(
            "get",
            "configmap",
            "ibg-hybrid-runtime-profiles",
            "ibg-hybrid-planning-links",
            "-n",
            runner.HYBRID_NAMESPACE,
            "-o",
            "json",
        ):
            return json.dumps(_configmaps(self.runtime, self.controller))
        if command == ("kind", "get", "nodes", "--name", runner.CLUSTER_NAME):
            return "ibg-hybrid-control-plane\n"
        if command[:4] == (
            "docker",
            "exec",
            "ibg-hybrid-control-plane",
            "crictl",
        ):
            return json.dumps(
                {
                    "images": [
                        {
                            "id": f"sha256:{SERVICE_ID}",
                            "repoTags": [runner.NORMALIZED_SERVICE_IMAGE],
                        },
                        {
                            "id": f"sha256:{CONTROLLER_ID}",
                            "repoTags": [runner.NORMALIZED_CONTROLLER_IMAGE],
                        },
                    ]
                }
            )
        if (
            command[:5]
            == (
                "kubectl",
                "--context",
                runner.KUBECTL_CONTEXT,
                "create",
                "configmap",
            )
            and runner.PHASE75_CONTROLLER_SOURCE_CONFIGMAP in command
        ):
            return json.dumps(
                {
                    "apiVersion": "v1",
                    "kind": "ConfigMap",
                    "metadata": {
                        "name": runner.PHASE75_CONTROLLER_SOURCE_CONFIGMAP,
                        "namespace": runner.HYBRID_NAMESPACE,
                    },
                    "data": {
                        source.name: source.read_text(encoding="utf-8")
                        for source in runner.PHASE75_CONTROLLER_SOURCES
                    },
                }
            )
        if (
            command[:4]
            == (
                "kubectl",
                "--context",
                runner.KUBECTL_CONTEXT,
                "create",
            )
            and "-f" in command
        ):
            return json.dumps(
                {
                    "apiVersion": "batch/v1",
                    "kind": "Job",
                    "metadata": {
                        "name": runner.DYNAMIC_CONTROLLER_JOB_NAME,
                        "namespace": runner.HYBRID_NAMESPACE,
                    },
                    "spec": {
                        "activeDeadlineSeconds": 600,
                        "template": {
                            "spec": {
                                "containers": [
                                    {
                                        "name": "controller",
                                        "env": [],
                                    }
                                ]
                            }
                        },
                    },
                }
            )
        if command[:4] == (
            "kubectl",
            "--context",
            runner.KUBECTL_CONTEXT,
            "apply",
        ) and "-k" in command:
            directory = Path(command[command.index("-k") + 1])
            counts = {
                int(line.split(":", 1)[1])
                for line in (directory / "kustomization.yaml").read_text(
                    encoding="utf-8"
                ).splitlines()
                if line.strip().startswith("count:")
            }
            assert len(counts) == 1
            target = counts.pop()
            if "--dry-run=server" in command:
                self.rollout_events.append(
                    ("dry-run", target, len(self.runtime["profiles"]))
                )
                return json.dumps(_statefulsets(target))
            self.rollout_events.append(
                ("apply", target, len(self.runtime["profiles"]))
            )
            self.runtime = json.loads(
                (directory / "runtime-profiles.json").read_text(encoding="utf-8")
            )
            self.controller = json.loads(
                (directory / "controller-inputs.json").read_text(encoding="utf-8")
            )
            self.replicas = target
            return ""
        if "scale" in command:
            target = int(
                next(item for item in command if item.startswith("--replicas=")).split(
                    "=", 1
                )[1]
            )
            self.rollout_events.append(
                ("scale", target, len(self.runtime["profiles"]))
            )
            self.replicas = target
            return ""
        if (
            len(command) > 4
            and command[:3] == ("kubectl", "--context", runner.KUBECTL_CONTEXT)
            and command[3] == "delete"
            and any(item.startswith("pod/hybrid-stage-") for item in command)
        ):
            for item in command:
                if item.startswith("pod/hybrid-stage-"):
                    name = item.removeprefix("pod/")
                    self.pod_generations[name] = self.pod_generations.get(name, 0) + 1
            return ""
        if "logs" in command:
            return '{"configuration":{"num_flows":10,"num_stages":3,"num_replicas":5}}\n'
        return ""


def test_mocked_dynamic_2_to_4_to_5_rollout_and_unchanged_rerun(monkeypatch):
    cluster = FakeDynamicCluster()
    monkeypatch.setattr(
        runner,
        "_local_platform_image_id",
        lambda execute, image: (
            SERVICE_ID if image == runner.SERVICE_IMAGE else CONTROLLER_ID
        ),
    )
    output = runner.run_small(
        skip_build=True,
        requested_flows=10,
        requested_stages=3,
        requested_replicas=5,
        rollout_batch_size=2,
        execute=cluster.execute,
    )
    assert '"num_flows":10' in output
    commands = [command for command, _capture in cluster.commands]
    scales = [command for command in commands if "scale" in command]
    assert [
        next(item for item in command if item.startswith("--replicas="))
        for command in scales
    ] == ["--replicas=4", "--replicas=5"]
    assert all(
        all(resource in command for resource in runner.STATEFULSET_RESOURCES)
        for command in scales
    )
    assert cluster.replicas == 5
    assert len(cluster.runtime["profiles"]) == 15
    assert len(cluster.controller["admission"]) == 15
    assert len(cluster.controller["planning_pair_links"]) == 75
    assert not any(command[:2] == ("docker", "build") for command in commands)
    assert not any(command[:3] == ("kind", "load", "docker-image") for command in commands)
    assert not any("restart" in command for command in commands)
    first_processes = runner._serving_process_snapshot(_pods(5), replica_count=5)

    command_count = len(cluster.commands)
    runner.run_small(
        skip_build=True,
        requested_flows=10,
        requested_stages=3,
        requested_replicas=5,
        rollout_batch_size=2,
        execute=cluster.execute,
    )
    rerun_commands = [command for command, _capture in cluster.commands[command_count:]]
    assert not any("scale" in command or "restart" in command for command in rerun_commands)
    assert runner._serving_process_snapshot(_pods(5), replica_count=5) == first_processes


def test_mocked_dynamic_8_to_5_scales_before_reducing_profiles(monkeypatch):
    cluster = FakeDynamicCluster(replicas=8, flows=10)
    monkeypatch.setattr(
        runner,
        "_local_platform_image_id",
        lambda execute, image: (
            SERVICE_ID if image == runner.SERVICE_IMAGE else CONTROLLER_ID
        ),
    )
    before = runner._serving_process_snapshot(_pods(8), replica_count=8)

    runner.run_experiment(
        skip_build=True,
        requested_flows=10,
        requested_stages=3,
        requested_replicas=5,
        rollout_batch_size=2,
        max_iterations=2,
        execute=cluster.execute,
    )

    assert cluster.replicas == 5
    assert len(cluster.runtime["profiles"]) == 15
    assert len(cluster.controller["admission"]) == 15
    assert len(cluster.controller["planning_pair_links"]) == 75
    assert cluster.rollout_events[:3] == [
        ("dry-run", 5, 24),
        ("scale", 5, 24),
        ("dry-run", 5, 24),
    ]
    assert cluster.rollout_events[3] == ("apply", 5, 24)
    after = runner._serving_process_snapshot(_pods(5), replica_count=5)
    runner._validate_scale_down_process_preservation(
        before,
        after,
        existing_count=8,
        requested_count=5,
    )
    assert not any(
        item.pod_name.startswith("hybrid-stage-")
        and int(item.pod_name.rsplit("-", 1)[1]) >= 5
        for item in after
    )
    commands = [command for command, _capture in cluster.commands]
    scale_commands = [command for command in commands if "scale" in command]
    assert len(scale_commands) == 1
    assert "--replicas=5" in scale_commands[0]
    assert all(resource in scale_commands[0] for resource in runner.STATEFULSET_RESOURCES)
    deletion_wait = next(
        command
        for command in commands
        if "--for=delete" in command
    )
    assert {
        f"pod/hybrid-stage-{stage}-{ordinal}"
        for stage in range(1, 4)
        for ordinal in (5, 6, 7)
    }.issubset(deletion_wait)
    assert not any("restart" in command for command in commands)
    scale_index = commands.index(scale_commands[0])
    target_apply_index = next(
        index
        for index, command in enumerate(commands)
        if index > scale_index
        and command[:4]
        == ("kubectl", "--context", runner.KUBECTL_CONTEXT, "apply")
        and "-k" in command
        and "--dry-run=server" not in command
    )
    controller_delete_index = next(
        index
        for index, command in enumerate(commands)
        if "delete" in command and "job" in command
    )
    final_ready_index = max(
        index
        for index, command in enumerate(commands[:controller_delete_index])
        if command == runner._kubectl(
            "get", "pods", "-n", runner.HYBRID_NAMESPACE, "-o", "json"
        )
    )
    assert (
        scale_index
        < target_apply_index
        < final_ready_index
        < controller_delete_index
    )

    command_count = len(cluster.commands)
    retained = after
    runner.run_experiment(
        skip_build=True,
        requested_flows=10,
        requested_stages=3,
        requested_replicas=5,
        rollout_batch_size=2,
        max_iterations=2,
        execute=cluster.execute,
    )
    rerun_commands = [command for command, _capture in cluster.commands[command_count:]]
    assert not any("scale" in command or "restart" in command for command in rerun_commands)
    assert runner._serving_process_snapshot(_pods(5), replica_count=5) == retained


def test_dynamic_kustomize_projection_keeps_templates_and_generated_configmaps():
    boundary = runner._profile_boundary(
        5, requested_flows=10, requested_stages=3
    )
    rendered = []

    def render(command, capture_output):
        directory = Path(command[command.index("-k") + 1])
        if "--dry-run=server" in command:
            return json.dumps(_statefulsets(2))
        completed = subprocess.run(
            ["kubectl", "kustomize", str(directory)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        rendered.append(completed.stdout)
        return ""

    expected_templates = runner._statefulset_template_snapshot(_statefulsets(2))
    runner._apply_reconciled_boundary(
        render,
        replica_count=2,
        boundary=boundary,
        deployment_overlay=boundary.overlay,
        expected_templates=expected_templates,
    )
    document = rendered[0]
    assert document.count("kind: StatefulSet") == 3
    assert document.count("replicas: 2") == 3
    assert document.count("memory: 64Mi") == 3
    assert "ibg-hybrid-kernel-dynamic-topology-v1:10x3x5" in document
    assert '"num_flows":10' in document
    assert '"num_replicas":5' in document
    assert "kind: Job" not in document


def _pure_input(configuration, runtime_mapping, controller_mapping, *, slot_id=1, beliefs=None):
    runtime = runtime_profile_document_from_mapping(runtime_mapping)
    controller = controller_input_document_from_mapping(controller_mapping)
    admission = {item.choice: item.max_assigned_flows for item in controller.admission}
    uniform = (0.25, 0.25, 0.25, 0.25)
    return HybridSlotInput(
        configuration=configuration,
        parameters=DEFAULT_HYBRID_POLICY_PARAMETERS,
        root_seed=2050,
        slot_id=slot_id,
        flows=tuple(HybridFlow(flow) for flow in range(1, configuration.num_flows + 1)),
        replicas=tuple(
            HybridReplica(
                choice=profile.choice,
                belief=uniform if beliefs is None else beliefs[profile.choice],
                ready=True,
                max_assigned_flows=admission[profile.choice],
                hidden_state=profile.hidden_state,
            )
            for profile in runtime.profiles
        ),
        planning_pair_links=controller.planning_pair_links,
        simulated_pair_outcomes=controller.planning_pair_links,
        initial_loads=GlobalLoadState.empty(configuration),
    )


def _kernelized(result, configuration):
    observations = tuple(
        SimpleNamespace(
            flow_id=item.flow_id,
            choice=item.choice,
            assigned_load=item.assigned_load,
            physical_processing_latency_ms=item.physical_processing_latency_ms,
            observation_jitter_ms=item.observation_jitter_ms,
            learning_signal_ms=item.learning_signal_ms,
            likelihood=item.likelihood,
            estimated_state=item.estimated_state,
            stage=item.choice.stage,
            replica_id=item.choice.replica,
            congestion=item.assigned_load,
            signal=item.learning_signal_ms,
            measured_latency_ms=item.physical_processing_latency_ms,
            provenance=SimpleNamespace(
                pod_name=f"hybrid-stage-{item.choice.stage}-{item.choice.replica - 1}",
                pod_uid=f"uid-{item.choice.stage}-{item.choice.replica}",
                endpoint="http://selected",
            ),
        )
        for item in result.observations
    )
    slot = SimpleNamespace(**vars(result))
    slot.observations = observations
    return SimpleNamespace(
        slot=slot,
        discovery=SimpleNamespace(
            replicas=tuple(
                SimpleNamespace(
                    choice=ReplicaChoice(stage, replica),
                    pod_name=f"hybrid-stage-{stage}-{replica - 1}",
                    pod_uid=f"uid-{stage}-{replica}",
                    node_name="ibg-hybrid-control-plane",
                )
                for stage in range(1, 4)
                for replica in range(1, configuration.num_replicas + 1)
            )
        ),
    )


def test_10x3x5_pure_kernel_semantics_and_dynamic_evidence():
    configuration, runtime, controller = _generated()
    first = run_hybrid_slot(_pure_input(configuration, runtime, controller))
    second = run_hybrid_slot(
        _pure_input(
            configuration,
            runtime,
            controller,
            slot_id=2,
            beliefs=first.beliefs_after_mapping,
        )
    )

    class FakeController:
        outcomes = [
            _kernelized(first, configuration),
            _kernelized(second, configuration),
        ]

        def run_slot(self, slot_id):
            outcome = self.outcomes.pop(0)
            assert outcome.slot.slot_id == slot_id
            return outcome

    inputs = controller_input_document_from_mapping(controller)
    evidence = run_small_live_gate(FakeController(), inputs)
    validate_dynamic_lookahead_slots(evidence, configuration)
    assert all(item["observation_count"] == 20 for item in evidence)
    assert all(item["measured_pair_count"] == 10 for item in evidence)
    assert evidence[1]["beliefs_before"] == evidence[0]["beliefs_after"]
    assert sum(sum(row) for row in first.final_loads.loads) == 20

    invalid = copy.deepcopy(evidence)
    invalid[0]["observation_count"] = 19
    with pytest.raises(HybridKernelDynamicTopologyEvidenceError):
        validate_dynamic_lookahead_slots(invalid, configuration)


def test_seeded_profile_allocator_is_balanced_deterministic_and_rng_neutral():
    python_state = random.getstate()
    numpy_state = np.random.get_state()
    layouts = {}
    for seed in (0, 1, 42):
        layouts[seed] = tuple(
            seeded_hidden_state_sequence(
                stage=stage,
                replica_count=10,
                profile_seed=seed,
            )
            for stage in range(1, 4)
        )
        assert seeded_profile_state_counts(
            replica_count=10,
            profile_seed=seed,
        ) == {
            stage: {4: 3, 3: 3, 2: 2, 1: 2}
            for stage in range(1, 4)
        }
    assert len(set(layouts.values())) == len(layouts)
    assert layouts[0] != (
        (4, 2, 4, 2, 4, 2, 4, 2, 4, 2),
        (3, 1, 3, 1, 3, 1, 3, 1, 3, 1),
        (4, 3, 4, 3, 4, 3, 4, 3, 4, 3),
    )
    assert random.getstate() == python_state
    current_numpy = np.random.get_state()
    assert current_numpy[0] == numpy_state[0]
    assert np.array_equal(current_numpy[1], numpy_state[1])
    assert current_numpy[2:] == numpy_state[2:]


def test_seeded_profile_arbitrary_prefix_quota_and_append_only_behavior():
    weights = {4: 0.3, 3: 0.3, 2: 0.2, 1: 0.2}
    for stage in range(1, 4):
        long_sequence = seeded_hidden_state_sequence(
            stage=stage,
            replica_count=73,
            profile_seed=90210,
        )
        for replica_count in range(1, 74):
            prefix = long_sequence[:replica_count]
            assert prefix == seeded_hidden_state_sequence(
                stage=stage,
                replica_count=replica_count,
                profile_seed=90210,
            )
            for state, weight in weights.items():
                assert abs(prefix.count(state) - replica_count * weight) <= 1


def test_seeded_documents_are_byte_stable_isolated_and_preserve_observation_seeds():
    canonical_runtime, canonical_controller = _canonical_documents()
    configuration = HybridConfiguration(15, 3, 10, 2)
    runtime, controller = generate_dynamic_topology_documents(
        canonical_runtime=canonical_runtime,
        canonical_controller=canonical_controller,
        configuration=configuration,
        profile_seed=42,
    )
    repeated = generate_dynamic_topology_documents(
        canonical_runtime=canonical_runtime,
        canonical_controller=canonical_controller,
        configuration=configuration,
        profile_seed=42,
    )
    other_runtime, other_controller = generate_dynamic_topology_documents(
        canonical_runtime=canonical_runtime,
        canonical_controller=canonical_controller,
        configuration=configuration,
        profile_seed=43,
    )
    assert (runtime, controller) == repeated
    assert json.dumps(runtime, sort_keys=True, separators=(",", ":")) == json.dumps(
        repeated[0], sort_keys=True, separators=(",", ":")
    )
    assert controller == other_controller
    assert [item["hidden_state"] for item in runtime["profiles"]] != [
        item["hidden_state"] for item in other_runtime["profiles"]
    ]
    assert HYBRID_PROFILE_STATE_ALLOCATION_VERSION in runtime["source_identity"]
    controller_text = json.dumps(controller, sort_keys=True)
    assert "profile-seed" not in controller_text
    assert "hidden_state" not in controller_text
    assert "observation_seed" not in controller_text
    canonical_seeds = {
        (item["stage"], item["replica"]): item["observation_seed"]
        for item in canonical_runtime["profiles"]
    }
    assert all(
        item["observation_seed"] == canonical_seeds[(item["stage"], item["replica"])]
        for item in runtime["profiles"]
        if (item["stage"], item["replica"]) in canonical_seeds
    )
    assert all(set(item) == {"stage", "replica", "hidden_state", "observation_seed"}
               for item in runtime["profiles"])


def test_seeded_transition_requires_refresh_then_supports_append_and_trim():
    canonical_runtime, canonical_controller = _canonical_documents()
    deployed_configuration = HybridConfiguration(15, 3, 10, 2)
    legacy_runtime, legacy_controller = generate_dynamic_topology_documents(
        canonical_runtime=canonical_runtime,
        canonical_controller=canonical_controller,
        configuration=deployed_configuration,
    )
    seeded_runtime, seeded_controller = generate_dynamic_topology_documents(
        canonical_runtime=canonical_runtime,
        canonical_controller=canonical_controller,
        configuration=deployed_configuration,
        profile_seed=42,
    )
    with pytest.raises(
        HybridKernelProfileExpansionError,
        match="--refresh-runtime-profiles",
    ):
        validate_dynamic_topology_transition(
            deployed_runtime=legacy_runtime,
            deployed_controller=legacy_controller,
            proposed_runtime=seeded_runtime,
            proposed_controller=seeded_controller,
            canonical_runtime=canonical_runtime,
            canonical_controller=canonical_controller,
            existing_replica_count=10,
            target_configuration=deployed_configuration,
            profile_seed=42,
        )
    refresh = validate_dynamic_topology_transition(
        deployed_runtime=legacy_runtime,
        deployed_controller=legacy_controller,
        proposed_runtime=seeded_runtime,
        proposed_controller=seeded_controller,
        canonical_runtime=canonical_runtime,
        canonical_controller=canonical_controller,
        existing_replica_count=10,
        target_configuration=deployed_configuration,
        profile_seed=42,
        allow_runtime_profile_refresh=True,
    )
    assert refresh.profile_refresh_required
    assert refresh.deployed_profile_seed is None
    assert refresh.target_profile_seed == 42
    assert refresh.changed_runtime_identities
    old_by_choice = {
        (item["stage"], item["replica"]): item for item in legacy_runtime["profiles"]
    }
    new_by_choice = {
        (item["stage"], item["replica"]): item for item in seeded_runtime["profiles"]
    }
    assert all(
        old_by_choice[choice]["observation_seed"]
        == new_by_choice[choice]["observation_seed"]
        for choice in old_by_choice
    )
    reseeded_runtime, reseeded_controller = generate_dynamic_topology_documents(
        canonical_runtime=canonical_runtime,
        canonical_controller=canonical_controller,
        configuration=deployed_configuration,
        profile_seed=43,
    )
    with pytest.raises(HybridKernelProfileExpansionError, match="refresh"):
        validate_dynamic_topology_transition(
            deployed_runtime=seeded_runtime,
            deployed_controller=seeded_controller,
            proposed_runtime=reseeded_runtime,
            proposed_controller=reseeded_controller,
            canonical_runtime=canonical_runtime,
            canonical_controller=canonical_controller,
            existing_replica_count=10,
            target_configuration=deployed_configuration,
            profile_seed=43,
        )

    larger_configuration = HybridConfiguration(15, 3, 13, 2)
    larger_runtime, larger_controller = generate_dynamic_topology_documents(
        canonical_runtime=canonical_runtime,
        canonical_controller=canonical_controller,
        configuration=larger_configuration,
        profile_seed=42,
    )
    growth = validate_dynamic_topology_transition(
        deployed_runtime=seeded_runtime,
        deployed_controller=seeded_controller,
        proposed_runtime=larger_runtime,
        proposed_controller=larger_controller,
        canonical_runtime=canonical_runtime,
        canonical_controller=canonical_controller,
        existing_replica_count=10,
        target_configuration=larger_configuration,
        profile_seed=42,
    )
    assert not growth.profile_refresh_required
    assert growth.changed_runtime_identities == ()
    assert {choice.replica for choice in growth.added_runtime_identities} == {11, 12, 13}

    smaller_configuration = HybridConfiguration(15, 3, 6, 2)
    smaller_runtime, smaller_controller = generate_dynamic_topology_documents(
        canonical_runtime=canonical_runtime,
        canonical_controller=canonical_controller,
        configuration=smaller_configuration,
        profile_seed=42,
    )
    shrink = validate_dynamic_topology_transition(
        deployed_runtime=seeded_runtime,
        deployed_controller=seeded_controller,
        proposed_runtime=smaller_runtime,
        proposed_controller=smaller_controller,
        canonical_runtime=canonical_runtime,
        canonical_controller=canonical_controller,
        existing_replica_count=10,
        target_configuration=smaller_configuration,
        profile_seed=42,
    )
    assert shrink.changed_runtime_identities == ()
    assert {choice.replica for choice in shrink.removed_runtime_identities} == {
        7, 8, 9, 10
    }


def test_seeded_profile_does_not_change_first_slot_policy_information():
    canonical_runtime, canonical_controller = _canonical_documents()
    configuration = HybridConfiguration(4, 3, 10, 2)
    legacy_runtime, controller = generate_dynamic_topology_documents(
        canonical_runtime=canonical_runtime,
        canonical_controller=canonical_controller,
        configuration=configuration,
    )
    seeded_runtime, seeded_controller = generate_dynamic_topology_documents(
        canonical_runtime=canonical_runtime,
        canonical_controller=canonical_controller,
        configuration=configuration,
        profile_seed=42,
    )
    assert controller == seeded_controller
    legacy_input = _pure_input(configuration, legacy_runtime, controller)
    seeded_input = _pure_input(configuration, seeded_runtime, controller)
    legacy = run_hybrid_slot(legacy_input)
    seeded = run_hybrid_slot(seeded_input)
    assert legacy.placements == seeded.placements
    assert all(
        belief == (0.25, 0.25, 0.25, 0.25)
        for belief in (replica.belief for replica in seeded_input.replicas)
    )


def test_profile_seed_cli_validation_occurs_before_cluster_contact():
    parsed = runner.parse_args(
        [
            "run",
            "--skip-build",
            "--flow",
            "15",
            "--stage",
            "3",
            "--replica",
            "10",
            "--profile-seed",
            "42",
            "--max-iterations",
            "6",
        ]
    )
    assert parsed.profile_seed == 42
    assert not parsed.refresh_runtime_profiles
    with pytest.raises(SystemExit):
        runner.parse_args(
            [
                "run",
                "--flow",
                "1",
                "--stage",
                "3",
                "--replica",
                "1",
                "--profile-seed",
                "-1",
                "--max-iterations",
                "1",
            ]
        )
    with pytest.raises(SystemExit):
        runner.parse_args(
            [
                "run",
                "--flow",
                "1",
                "--stage",
                "3",
                "--replica",
                "1",
                "--max-iterations",
                "1",
            ]
        )


def test_mocked_legacy_to_seeded_refresh_replaces_only_changed_pods(monkeypatch):
    cluster = FakeDynamicCluster(replicas=10, flows=15)
    monkeypatch.setattr(
        runner,
        "_local_platform_image_id",
        lambda execute, image: (
            SERVICE_ID if image == runner.SERVICE_IMAGE else CONTROLLER_ID
        ),
    )
    before = runner._serving_process_snapshot(
        _pods(10, cluster.pod_generations), replica_count=10
    )
    runner.run_experiment(
        skip_build=True,
        requested_flows=15,
        requested_stages=3,
        requested_replicas=10,
        rollout_batch_size=3,
        max_iterations=2,
        profile_seed=42,
        refresh_runtime_profiles=True,
        execute=cluster.execute,
    )
    expected_runtime, _expected_controller = generate_dynamic_topology_documents(
        canonical_runtime=_canonical_documents()[0],
        canonical_controller=_canonical_documents()[1],
        configuration=HybridConfiguration(15, 3, 10, 2),
        profile_seed=42,
    )
    assert cluster.runtime == expected_runtime
    changed = {
        (old["stage"], old["replica"])
        for old, new in zip(
            _generated(flows=15, replicas=10)[1]["profiles"],
            expected_runtime["profiles"],
        )
        if old["hidden_state"] != new["hidden_state"]
    }
    after = runner._serving_process_snapshot(
        _pods(10, cluster.pod_generations), replica_count=10
    )
    runner._validate_runtime_profile_refresh_processes(
        before,
        after,
        changed_identities=tuple(ReplicaChoice(*choice) for choice in changed),
    )
    commands = [command for command, _capture in cluster.commands]
    target_apply = next(
        index
        for index, command in enumerate(commands)
        if command[:4] == ("kubectl", "--context", runner.KUBECTL_CONTEXT, "apply")
        and "-k" in command
        and "--dry-run=server" not in command
    )
    pod_deletes = [
        index
        for index, command in enumerate(commands)
        if len(command) > 4
        and command[3] == "delete"
        and any(item.startswith("pod/hybrid-stage-") for item in command)
    ]
    controller_delete = next(
        index
        for index, command in enumerate(commands)
        if len(command) > 3 and command[3] == "delete" and "job" in command
    )
    assert pod_deletes
    assert target_apply < min(pod_deletes) < max(pod_deletes) < controller_delete
    assert len(pod_deletes) <= 3
    assert not any("rollout" in command and "restart" in command for command in commands)


def test_mocked_seeded_rerun_preserves_pods_and_unconfirmed_change_fails(monkeypatch):
    monkeypatch.setattr(
        runner,
        "_local_platform_image_id",
        lambda execute, image: (
            SERVICE_ID if image == runner.SERVICE_IMAGE else CONTROLLER_ID
        ),
    )
    seeded = FakeDynamicCluster(replicas=10, flows=15, profile_seed=42)
    before = runner._serving_process_snapshot(
        _pods(10, seeded.pod_generations), replica_count=10
    )
    runner.run_experiment(
        skip_build=True,
        requested_flows=15,
        requested_stages=3,
        requested_replicas=10,
        rollout_batch_size=3,
        max_iterations=2,
        profile_seed=42,
        execute=seeded.execute,
    )
    after = runner._serving_process_snapshot(
        _pods(10, seeded.pod_generations), replica_count=10
    )
    assert after == before
    assert not any(
        command[3] == "delete"
        and any(item.startswith("pod/hybrid-stage-") for item in command)
        for command, _capture in seeded.commands
        if len(command) > 3
    )

    legacy = FakeDynamicCluster(replicas=10, flows=15)
    with pytest.raises(
        HybridKernelProfileExpansionError,
        match="--refresh-runtime-profiles",
    ):
        runner.run_experiment(
            skip_build=True,
            requested_flows=15,
            requested_stages=3,
            requested_replicas=10,
            rollout_batch_size=3,
            max_iterations=2,
            profile_seed=42,
            execute=legacy.execute,
        )
    assert not any(
        command[:4] == ("kubectl", "--context", runner.KUBECTL_CONTEXT, "apply")
        and "--dry-run=server" not in command
        for command, _capture in legacy.commands
    )


def test_kernel_controller_and_dynamic_job_remain_runtime_profile_blind():
    controller_source = (ROOT / "IBG_Hybrid" / "kernel_controller.py").read_text(
        encoding="utf-8"
    )
    job = (ROOT / "deploy" / "hybrid-kubernetes" / "dynamic-controller-job.yaml").read_text(
        encoding="utf-8"
    )
    assert "hidden_state=None" in controller_source
    assert "ibg-hybrid-runtime-profiles" not in job
    assert "PROFILE_SEED" not in job


def test_dynamic_imports_are_silent_rng_neutral_and_file_safe(tmp_path):
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    code = (
        "import random,numpy as np; random.seed(85); np.random.seed(58); "
        "p=random.getstate(); n=np.random.get_state(); "
        "import IBG_Hybrid.kernel_dynamic_topology_evidence; "
        "import IBG_Hybrid.kernel_profile_expansion; "
        "import scripts.run_hybrid_kernel_phase4; "
        "assert random.getstate()==p; a=np.random.get_state(); "
        "assert a[0]==n[0] and np.array_equal(a[1],n[1]) and a[2:]==n[2:]"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
        check=True,
    )
    assert completed.stdout == ""
    assert completed.stderr == ""
    assert list(tmp_path.iterdir()) == []
