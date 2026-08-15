import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys

import pytest

from scripts import run_hybrid_kernel_phase4 as cluster_runner

from IBG_Hybrid.contracts import GlobalLoadState, ReplicaChoice
from IBG_Hybrid.kernel_controller_config import load_controller_input_document
from IBG_Hybrid.kernel_phase4_validation import (
    HYBRID_KERNEL_PHASE4_VALIDATION_VERSION,
    run_small_live_gate,
)
from IBG_Hybrid.kernel_runtime_profiles import load_runtime_profile_document
from IBG_Hybrid.phase0_contract import DEFAULT_HYBRID_POLICY_PARAMETERS
from IBG_Hybrid.runner import run_hybrid_slot
from IBG_Hybrid.slot_contracts import (
    HybridFlow,
    HybridReplica,
    HybridSlotInput,
)


ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy" / "hybrid-kubernetes-phase4-small"


def small_pure_input(*, slot_id=1, beliefs=None):
    inputs = load_controller_input_document(DEPLOY / "controller-inputs.json")
    profiles = load_runtime_profile_document(DEPLOY / "runtime-profiles.json")
    uniform = (0.25, 0.25, 0.25, 0.25)
    return HybridSlotInput(
        configuration=inputs.configuration,
        parameters=DEFAULT_HYBRID_POLICY_PARAMETERS,
        root_seed=2050,
        slot_id=slot_id,
        flows=(HybridFlow(1), HybridFlow(2)),
        replicas=tuple(
            HybridReplica(
                choice=profile.choice,
                belief=(
                    uniform if beliefs is None else beliefs[profile.choice]
                ),
                ready=True,
                max_assigned_flows=2,
                hidden_state=profile.hidden_state,
            )
            for profile in profiles.profiles
        ),
        planning_pair_links=inputs.planning_pair_links,
        simulated_pair_outcomes=inputs.planning_pair_links,
        initial_loads=GlobalLoadState.empty(inputs.configuration),
    )


def kernelized_outcome(result):
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
                pod_name=f"hybrid-stage-{item.choice.stage}-0",
                pod_uid=f"uid-{item.choice.stage}-1",
                endpoint=f"http://hybrid-stage-{item.choice.stage}-0",
            ),
        )
        for item in result.observations
    )
    slot = SimpleNamespace(**vars(result))
    slot.observations = observations
    discovery = SimpleNamespace(
        replicas=tuple(
            SimpleNamespace(
                choice=ReplicaChoice(stage, 1),
                pod_name=f"hybrid-stage-{stage}-0",
                pod_uid=f"uid-{stage}-1",
                node_name="worker-1",
            )
            for stage in (1, 2, 3)
        )
    )
    return SimpleNamespace(slot=slot, discovery=discovery)


def test_small_profiles_are_complete_separate_and_minimal():
    runtime = load_runtime_profile_document(DEPLOY / "runtime-profiles.json")
    controller = load_controller_input_document(DEPLOY / "controller-inputs.json")

    assert runtime.configuration == controller.configuration
    assert runtime.configuration.num_flows == 2
    assert runtime.configuration.num_stages == 3
    assert runtime.configuration.num_replicas == 1
    assert len(runtime.profiles) == 3
    assert len(controller.admission) == 3
    assert len(controller.planning_pair_links) == 3
    assert "belief" not in (DEPLOY / "runtime-profiles.json").read_text()
    controller_text = (DEPLOY / "controller-inputs.json").read_text()
    assert "hidden_state" not in controller_text
    assert "observation_seed" not in controller_text
    assert "belief" not in controller_text


def test_small_planning_profile_exercises_both_required_route_shapes():
    result = run_hybrid_slot(small_pure_input())
    stages = {placement.action.stages for placement in result.placements}

    assert stages == {(1, 3), (2, 3)}
    assert {placement.skipped_stage for placement in result.placements} == {1, 2}
    assert len(result.observations) == 4
    assert len(result.measured_pairs) == 2


def test_phase4_validator_proves_retention_skips_and_replay_parity():
    inputs = load_controller_input_document(DEPLOY / "controller-inputs.json")
    first = run_hybrid_slot(small_pure_input())
    second = run_hybrid_slot(
        small_pure_input(
            slot_id=2,
            beliefs=first.beliefs_after_mapping,
        )
    )

    lifecycle = []

    class FakeController:
        def __init__(self):
            self.outcomes = [kernelized_outcome(first), kernelized_outcome(second)]

        def run_slot(self, slot_id):
            lifecycle.append(f"run-{slot_id}")
            outcome = self.outcomes.pop(0)
            assert outcome.slot.slot_id == slot_id
            return outcome

    evidence = run_small_live_gate(
        FakeController(),
        inputs,
        on_slot_completed=lambda iteration, slot, item: lifecycle.append(
            f"print-{iteration}-{slot.slot_id}-{item['slot_id']}"
        ),
    )

    assert len(evidence) == 2
    assert all(
        item["contract_version"] == HYBRID_KERNEL_PHASE4_VALIDATION_VERSION
        for item in evidence
    )
    assert all(item["observation_count"] == 4 for item in evidence)
    assert all(item["measured_pair_count"] == 2 for item in evidence)
    assert all(item["skipped_stage_absent"] for item in evidence)
    assert all(item["pure_kernel_replay_parity"] for item in evidence)
    assert evidence[0]["metrics"][
        "physical_processing_latency_ms_per_flow"
    ] == first.metrics.physical_processing_latency_ms_per_flow
    assert evidence[0]["metrics"][
        "measured_pair_latency_ms_per_flow"
    ] == first.metrics.measured_pair_latency_ms_per_flow
    assert evidence[0]["metrics"][
        "raw_end_to_end_latency_ms_per_flow"
    ] == first.metrics.raw_end_to_end_latency_ms_per_flow
    assert evidence[1]["beliefs_before"] == evidence[0]["beliefs_after"]
    assert lifecycle == ["run-1", "print-1-1-1", "run-2", "print-2-2-2"]


def test_small_kustomize_boundary_keeps_base_resources_and_one_replica():
    completed = subprocess.run(
        ["kubectl", "kustomize", str(DEPLOY)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    rendered = completed.stdout
    assert rendered.count("kind: StatefulSet") == 3
    assert rendered.count("replicas: 1") == 4
    assert rendered.count("image: ibg-hybrid-testbed:kernel-service-v1") == 7
    assert "kind: Job" not in rendered
    assert "namespace: ibg-hybrid-testbed" in rendered
    assert "milp-testbed" not in rendered
    assert "ibg-testbed" not in rendered


def test_phase4_job_runs_two_validation_slots_without_hidden_profile_mount():
    job = (DEPLOY / "controller-job.yaml").read_text()

    assert "IBG_Hybrid.kernel_phase4_validation" in job
    assert 'value: "2"' in job
    assert "ibg-hybrid-testbed:kernel-controller-v1" in job
    assert "ibg-hybrid-runtime-profiles" not in job
    assert "hidden_state" not in job
    assert "belief" not in job
    assert "imagePullPolicy: Never" in job


def test_phase4_validation_import_is_silent_rng_neutral_and_file_safe(tmp_path):
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    code = (
        "import random,numpy as np; random.seed(84); np.random.seed(48); "
        "p=random.getstate(); n=np.random.get_state(); "
        "import IBG_Hybrid.kernel_phase4_validation; "
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


def test_phase4_scope_adds_no_rollout_resource_or_algorithm_change():
    all_text = "\n".join(path.read_text() for path in sorted(DEPLOY.iterdir()))
    assert "64Mi" not in all_text
    assert "--policy" not in all_text
    assert "netem" not in all_text.lower()
    assert "dpdk" not in all_text.lower()
    assert "diagnostic" not in all_text.lower()
    assert "automatic" not in all_text.lower()


def _inventory(names, *, namespace=None, ready=False):
    items = []
    for name in names:
        metadata = {"name": name}
        if namespace is not None:
            metadata["namespace"] = namespace
        if namespace == cluster_runner.HYBRID_NAMESPACE:
            if name.startswith("hybrid-stage-"):
                stage = int(name.split("-")[2])
                metadata["uid"] = f"uid-{name}"
                metadata["labels"] = {
                    "app.kubernetes.io/name": "ibg-hybrid-replica",
                    "app.kubernetes.io/part-of": "ibg-hybrid-testbed",
                    "app.kubernetes.io/component": "replica-stage",
                    "ibg-hybrid.stage": str(stage),
                }
            elif name.startswith("ibg-hybrid-flow-generator-"):
                metadata["uid"] = f"uid-{name}"
                metadata["labels"] = {
                    "app.kubernetes.io/name": "ibg-hybrid-flow-generator",
                    "app.kubernetes.io/part-of": "ibg-hybrid-testbed",
                }
        item = {"metadata": metadata}
        is_control_plane = name == cluster_runner.CONTROL_PLANE_NODE_NAME
        is_worker = name == cluster_runner.WORKER_NODE_NAME
        if is_control_plane:
            metadata["labels"] = {"node-role.kubernetes.io/control-plane": ""}
        elif is_worker:
            metadata["labels"] = {
                cluster_runner.WORKLOAD_NODE_LABEL: (
                    cluster_runner.WORKLOAD_NODE_LABEL_VALUE
                )
            }
        if namespace == cluster_runner.HYBRID_NAMESPACE:
            item["spec"] = {"nodeName": cluster_runner.WORKER_NODE_NAME}
        if ready or is_control_plane or is_worker:
            item["status"] = {
                "conditions": [{"type": "Ready", "status": "True"}],
            }
            if ready:
                item["status"].update(
                    {
                        "phase": "Running",
                        "containerStatuses": [
                            {"name": "serving", "restartCount": 0}
                        ],
                    }
                )
        items.append(item)
    return {"items": items}


def _statefulset_inventory(replicas=1):
    items = []
    for stage in (1, 2, 3):
        name = f"hybrid-stage-{stage}"
        labels = {
            "app.kubernetes.io/name": "ibg-hybrid-replica",
            "app.kubernetes.io/part-of": "ibg-hybrid-testbed",
            "app.kubernetes.io/component": "replica-stage",
            "ibg-hybrid.stage": str(stage),
        }
        items.append(
            {
                "kind": "StatefulSet",
                "metadata": {
                    "name": name,
                    "namespace": cluster_runner.HYBRID_NAMESPACE,
                    "labels": labels,
                },
                "spec": {
                    "serviceName": name,
                    "replicas": replicas,
                    "selector": {
                        "matchLabels": {
                            "app.kubernetes.io/name": "ibg-hybrid-replica",
                            "ibg-hybrid.stage": str(stage),
                        }
                    },
                    "template": {
                        "metadata": {"labels": labels},
                        "spec": {
                            "nodeSelector": {
                                cluster_runner.WORKLOAD_NODE_LABEL: (
                                    cluster_runner.WORKLOAD_NODE_LABEL_VALUE
                                )
                            }
                        },
                    },
                },
            }
        )
    return {"items": items}


def test_phase4_cluster_boundary_is_dedicated_two_node_and_local_only():
    kind_config = (DEPLOY / "kind-config.yaml").read_text()
    runner_source = (
        ROOT / "scripts" / "run_hybrid_kernel_phase4.py"
    ).read_text()

    assert kind_config.count("role: control-plane") == 1
    assert kind_config.count("role: worker") == 1
    assert f'{cluster_runner.WORKLOAD_NODE_LABEL}: "true"' in kind_config
    assert cluster_runner.EXPECTED_NODE_NAMES == {
        cluster_runner.CONTROL_PLANE_NODE_NAME,
        cluster_runner.WORKER_NODE_NAME,
    }
    assert cluster_runner.CLUSTER_NAME == "ibg-hybrid"
    assert cluster_runner.KUBECTL_CONTEXT == "kind-ibg-hybrid"
    assert "kind-ibg\"" not in runner_source
    assert "ibg-control-plane" not in runner_source
    assert "docker image inspect" not in runner_source
    assert "--pull=false" in runner_source
    assert "--network=none" in runner_source


def test_phase4_cluster_inventory_rejects_shared_or_foreign_workloads():
    clean_namespaces = _inventory(
        ["default", "kube-system", "local-path-storage"]
    )
    clean_pods = _inventory(
        ["coredns-1"], namespace="kube-system", ready=True
    )

    with pytest.raises(RuntimeError, match="non-dedicated cluster nodes"):
        cluster_runner.validate_cluster_inventory(
            nodes=_inventory(["ibg-control-plane", "ibg-worker"]),
            namespaces=clean_namespaces,
            pods=clean_pods,
        )

    with pytest.raises(RuntimeError, match="foreign baseline namespaces"):
        cluster_runner.validate_cluster_inventory(
            nodes=_inventory(
                [
                    cluster_runner.CONTROL_PLANE_NODE_NAME,
                    cluster_runner.WORKER_NODE_NAME,
                ]
            ),
            namespaces=_inventory(["kube-system", "milp-testbed"]),
            pods=clean_pods,
        )

    with pytest.raises(RuntimeError, match="foreign workload Pods"):
        cluster_runner.validate_cluster_inventory(
            nodes=_inventory(
                [
                    cluster_runner.CONTROL_PLANE_NODE_NAME,
                    cluster_runner.WORKER_NODE_NAME,
                ]
            ),
            namespaces=clean_namespaces,
            pods=_inventory(["other"], namespace="default", ready=True),
        )


def test_phase4_runner_retains_dedicated_cluster_after_failed_run(monkeypatch):
    monkeypatch.setattr(
        cluster_runner, "_validate_offline_wheelhouses", lambda: None
    )
    commands = []
    cluster_exists = False

    def fake_execute(command, capture_output):
        nonlocal cluster_exists
        commands.append((command, capture_output))
        if command == ("kind", "get", "clusters"):
            return "ibg-hybrid\n" if cluster_exists else ""
        if command[:3] == ("docker", "image", "inspect"):
            return "{}"
        if command[:3] == ("kind", "create", "cluster"):
            cluster_exists = True
            return ""
        if command[:3] == ("kind", "delete", "cluster"):
            cluster_exists = False
            return ""
        if command == cluster_runner._kubectl("get", "nodes", "-o", "json"):
            return json.dumps(
                _inventory(
                    [
                        cluster_runner.CONTROL_PLANE_NODE_NAME,
                        cluster_runner.WORKER_NODE_NAME,
                    ]
                )
            )
        if command == cluster_runner._kubectl(
            "get", "namespaces", "-o", "json"
        ):
            return json.dumps(_inventory(["default", "kube-system"]))
        if command == cluster_runner._kubectl("get", "pods", "-A", "-o", "json"):
            return json.dumps(_inventory([], namespace="kube-system"))
        if command[:4] == (
            "kind",
            "load",
            "docker-image",
            "--name",
        ):
            raise RuntimeError("synthetic post-create failure")
        return ""

    with pytest.raises(RuntimeError, match="synthetic post-create failure"):
        cluster_runner.run_small(execute=fake_execute)

    assert cluster_exists
    command_values = [command for command, _capture in commands]
    create_index = next(
        index
        for index, command in enumerate(command_values)
        if command[:3] == ("kind", "create", "cluster")
    )
    worker_wait = cluster_runner._kubectl(
        "wait",
        "--for=condition=Ready",
        f"node/{cluster_runner.CONTROL_PLANE_NODE_NAME}",
        f"node/{cluster_runner.WORKER_NODE_NAME}",
        "--timeout=120s",
    )
    wait_index = command_values.index(worker_wait)
    inventory_index = command_values.index(
        cluster_runner._kubectl("get", "nodes", "-o", "json")
    )
    assert create_index < wait_index < inventory_index
    assert not any(
        command[:3] == ("kind", "delete", "cluster")
        for command, _capture in commands
    )

    commands.clear()
    with pytest.raises(RuntimeError, match="synthetic post-create failure"):
        cluster_runner.run_small(execute=fake_execute)
    assert not any(
        command[:3] == ("kind", "create", "cluster")
        for command, _capture in commands
    )
    assert not any(
        command == cluster_runner._kubectl(
            "get", "statefulsets", "-n", cluster_runner.HYBRID_NAMESPACE,
            "-o", "json"
        )
        for command, _capture in commands
    )


def test_phase4_cleanup_is_explicit_and_hybrid_only():
    commands = []

    def fake_execute(command, capture_output):
        commands.append((command, capture_output))
        if command == ("kind", "get", "clusters"):
            return "ibg\nibg-hybrid\n"
        return ""

    cluster_runner.cleanup(execute=fake_execute)

    assert commands == [
        (("kind", "get", "clusters"), True),
        (("kind", "delete", "cluster", "--name", "ibg-hybrid"), False),
    ]


def test_phase4_runner_reuses_cluster_and_recreates_only_controller_job(
    monkeypatch, capsys
):
    monkeypatch.setattr(
        cluster_runner, "_validate_offline_wheelhouses", lambda: None
    )
    monkeypatch.setattr(
        cluster_runner,
        "_reconcile_phase75_controller_sources",
        lambda execute: None,
    )
    commands = []
    serving = _inventory(
        [
            "hybrid-stage-1-0",
            "hybrid-stage-2-0",
            "hybrid-stage-3-0",
            "ibg-hybrid-flow-generator-abcde",
        ],
        namespace=cluster_runner.HYBRID_NAMESPACE,
        ready=True,
    )

    def fake_execute(command, capture_output):
        commands.append((command, capture_output))
        if command == ("kind", "get", "clusters"):
            return "ibg-hybrid\n"
        if command[:3] == ("docker", "image", "inspect"):
            return "{}"
        if command == cluster_runner._kubectl("get", "nodes", "-o", "json"):
            return json.dumps(
                _inventory(
                    [
                        cluster_runner.CONTROL_PLANE_NODE_NAME,
                        cluster_runner.WORKER_NODE_NAME,
                    ]
                )
            )
        if command == cluster_runner._kubectl(
            "get", "namespaces", "-o", "json"
        ):
            return json.dumps(
                _inventory(
                    [
                        "default",
                        "kube-system",
                        cluster_runner.HYBRID_NAMESPACE,
                    ]
                )
            )
        if command == cluster_runner._kubectl("get", "pods", "-A", "-o", "json"):
            return json.dumps(serving)
        if command == cluster_runner._kubectl(
            "get",
            "pods",
            "-n",
            cluster_runner.HYBRID_NAMESPACE,
            "-o",
            "json",
        ):
            return json.dumps(serving)
        if command == cluster_runner._kubectl(
            "get",
            "statefulsets",
            "-n",
            cluster_runner.HYBRID_NAMESPACE,
            "-o",
            "json",
        ):
            return json.dumps(_statefulset_inventory())
        if command == cluster_runner._kubectl(
            "get",
            "configmap",
            "ibg-hybrid-runtime-profiles",
            "ibg-hybrid-planning-links",
            "-n",
            cluster_runner.HYBRID_NAMESPACE,
            "-o",
            "json",
        ):
            return json.dumps(
                {
                    "items": [
                        {
                            "metadata": {
                                "name": "ibg-hybrid-runtime-profiles",
                                "namespace": cluster_runner.HYBRID_NAMESPACE,
                            },
                            "data": {
                                "runtime-profiles.json": (
                                    DEPLOY / "runtime-profiles.json"
                                ).read_text()
                            },
                        },
                        {
                            "metadata": {
                                "name": "ibg-hybrid-planning-links",
                                "namespace": cluster_runner.HYBRID_NAMESPACE,
                            },
                            "data": {
                                "controller-inputs.json": (
                                    DEPLOY / "controller-inputs.json"
                                ).read_text()
                            },
                        },
                    ]
                }
            )
        if "--dry-run=server" in command:
            return json.dumps(_statefulset_inventory())
        if "logs" in command:
            return '{"slot_id":1}\n'
        return ""

    def fake_stream(controller_job_name):
        commands.append((("stream", controller_job_name), True))
        return '{"slot_id":1}\n'

    output = cluster_runner.run_small(
        execute=fake_execute,
        stream_controller_logs=fake_stream,
    )

    command_values = [command for command, _capture in commands]
    assert not any(
        command[:3] == ("kind", "create", "cluster")
        for command in command_values
    )
    assert not any(
        command[:3] == ("kind", "delete", "cluster")
        for command in command_values
    )
    assert sum(
        command[:3] == ("docker", "image", "inspect")
        for command in command_values
    ) == 1
    restart = next(command for command in command_values if "restart" in command)
    assert "statefulset/hybrid-stage-1" in restart
    delete_job = next(
        index
        for index, command in enumerate(command_values)
        if "delete" in command and "job" in command
    )
    apply_job = next(
        index
        for index, command in enumerate(command_values)
        if "apply" in command
        and str(cluster_runner.DYNAMIC_CONTROLLER_JOB) in command
    )
    assert delete_job < apply_job
    stream_job = next(
        index
        for index, command in enumerate(command_values)
        if command == ("stream", cluster_runner.DYNAMIC_CONTROLLER_JOB_NAME)
    )
    wait_job = next(
        index
        for index, command in enumerate(command_values)
        if "wait" in command and "job" in " ".join(command)
    )
    assert apply_job < stream_job < wait_job
    assert not any("logs" in command for command in command_values)
    assert capsys.readouterr().out == (
        "Selected Hybrid topology: 2 flows x 3 stages x 1 replica per stage\n"
        "Hybrid image mode: build offline from validated local wheelhouses\n"
    )
    assert output == '{"slot_id":1}\n'


def test_phase4_log_projection_hides_machine_evidence_and_keeps_human_output():
    emitted = []
    evidence = cluster_runner._project_controller_log_output(
        "Iteration 2 (slot 9)\n"
        "  Outcome mode: physical-only-v1\n"
        "HYBRID_SLOT_EVIDENCE="
        '{"flow_order":[2,1],"observations":[{"flow_id":1}],"slot_id":9}\n',
        emit=emitted.append,
    )

    assert emitted == [
        "Iteration 2 (slot 9)",
        "  Outcome mode: physical-only-v1",
    ]
    assert "flow_order" not in "\n".join(emitted)
    assert "observations" not in "\n".join(emitted)
    assert json.loads(evidence) == {
        "flow_order": [2, 1],
        "observations": [{"flow_id": 1}],
        "slot_id": 9,
    }


def test_phase4_default_log_follower_streams_human_lines_and_returns_evidence(
    monkeypatch, capsys
):
    captured = {}

    class FakeProcess:
        stdout = io.StringIO(
            "Iteration 1 (slot 4)\n"
            "  Outcome mode: physical-only-v1\n"
            'HYBRID_SLOT_EVIDENCE={"slot_id":4}\n'
        )
        stderr = io.StringIO("")

        def wait(self):
            return 0

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr(cluster_runner.subprocess, "Popen", fake_popen)
    evidence = cluster_runner._stream_controller_job_logs("controller-job")

    assert "--follow" in captured["command"]
    assert "--pod-running-timeout=180s" in captured["command"]
    assert evidence == '{"slot_id":4}\n'
    assert capsys.readouterr().out == (
        "Iteration 1 (slot 4)\n"
        "  Outcome mode: physical-only-v1\n"
    )


def test_phase4_cluster_runner_import_is_silent_and_side_effect_free(tmp_path):
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        [sys.executable, "-c", "import scripts.run_hybrid_kernel_phase4"],
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


def test_hybrid_pod_templates_select_only_the_dedicated_worker():
    completed = subprocess.run(
        ["kubectl", "kustomize", str(DEPLOY)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    rendered = completed.stdout
    assert rendered.count("nodeSelector:") == 4
    assert rendered.count(
        f'{cluster_runner.WORKLOAD_NODE_LABEL}: "true"'
    ) == 4

    controller_jobs = (
        ROOT / "deploy" / "hybrid-kubernetes" / "controller-job.yaml",
        ROOT / "deploy" / "hybrid-kubernetes" / "dynamic-controller-job.yaml",
        DEPLOY / "controller-job.yaml",
        ROOT / "deploy" / "hybrid-kubernetes-phase6-3x3x2" / "controller-job.yaml",
        ROOT / "deploy" / "hybrid-kubernetes-phase7-3x3x2" / "controller-job.yaml",
        ROOT
        / "deploy"
        / "hybrid-kubernetes-phase7.5-3x3x2"
        / "controller-job.yaml",
        ROOT
        / "deploy"
        / "hybrid-kubernetes-phase8-gate1-4x3x2"
        / "controller-job.yaml",
    )
    for job_path in controller_jobs:
        job = job_path.read_text(encoding="utf-8")
        assert job.count("nodeSelector:") == 1
        assert (
            f'{cluster_runner.WORKLOAD_NODE_LABEL}: "true"' in job
        )


def test_cluster_inventory_requires_exact_ready_roles_and_worker_placement():
    nodes = _inventory(
        [cluster_runner.CONTROL_PLANE_NODE_NAME, cluster_runner.WORKER_NODE_NAME]
    )
    namespaces = _inventory(
        ["default", "kube-system", cluster_runner.HYBRID_NAMESPACE]
    )
    misplaced = _inventory(
        ["hybrid-stage-1-0"],
        namespace=cluster_runner.HYBRID_NAMESPACE,
        ready=True,
    )
    misplaced["items"][0]["spec"]["nodeName"] = (
        cluster_runner.CONTROL_PLANE_NODE_NAME
    )
    with pytest.raises(RuntimeError, match="outside the dedicated worker"):
        cluster_runner.validate_cluster_inventory(
            nodes=nodes,
            namespaces=namespaces,
            pods=misplaced,
        )

    invalid_nodes = json.loads(json.dumps(nodes))
    invalid_nodes["items"][1]["metadata"]["labels"].clear()
    with pytest.raises(RuntimeError, match="node roles"):
        cluster_runner.validate_cluster_inventory(
            nodes=invalid_nodes,
            namespaces=namespaces,
            pods=_inventory([], namespace="kube-system"),
        )


def test_rollout_ready_gate_rejects_a_serving_pod_off_worker():
    serving = _inventory(
        [
            "hybrid-stage-1-0",
            "hybrid-stage-2-0",
            "hybrid-stage-3-0",
            "ibg-hybrid-flow-generator-abcde",
        ],
        namespace=cluster_runner.HYBRID_NAMESPACE,
        ready=True,
    )
    serving["items"][2]["spec"]["nodeName"] = (
        cluster_runner.CONTROL_PLANE_NODE_NAME
    )
    with pytest.raises(RuntimeError, match="dedicated worker"):
        cluster_runner._validate_serving_pods(serving, replica_count=1)
