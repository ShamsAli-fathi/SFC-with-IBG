import copy
import json
import os
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys

import pytest

from IBG_Hybrid.contracts import GlobalLoadState, ReplicaChoice
from IBG_Hybrid.kernel_controller_config import load_controller_input_document
from IBG_Hybrid.kernel_infrastructure_contract import (
    DEFAULT_HYBRID_KERNEL_OWNERSHIP,
)
from IBG_Hybrid.kernel_phase4_validation import run_small_live_gate
from IBG_Hybrid.kernel_profile_expansion import (
    HybridKernelProfileExpansionError,
    validate_append_only_profile_expansion,
)
from IBG_Hybrid.kernel_runtime_profiles import load_runtime_profile_document
from IBG_Hybrid.phase0_contract import DEFAULT_HYBRID_POLICY_PARAMETERS
from IBG_Hybrid.runner import run_hybrid_slot
from IBG_Hybrid.slot_contracts import (
    HybridFlow,
    HybridReplica,
    HybridSlotInput,
)
from scripts import run_hybrid_kernel_phase4 as runner


ROOT = Path(__file__).resolve().parents[1]
PHASE4 = ROOT / "deploy" / "hybrid-kubernetes-phase4-small"
PHASE6 = ROOT / "deploy" / "hybrid-kubernetes-phase6-3x3x2"
SERVICE_ID = "a" * 64
CONTROLLER_ID = "b" * 64


def _mapping(path):
    return json.loads(path.read_text())


def _statefulset(stage, replicas=1, *, template_marker=None):
    ownership = DEFAULT_HYBRID_KERNEL_OWNERSHIP
    name = f"hybrid-stage-{stage}"
    labels = dict(ownership.replica_labels(stage))
    template = {
        "metadata": {
            "labels": labels,
            **(
                {"annotations": {"marker": template_marker}}
                if template_marker is not None
                else {}
            ),
        },
        "spec": {"containers": [{"name": "serving", "image": "service"}]},
    }
    return {
        "apiVersion": "apps/v1",
        "kind": "StatefulSet",
        "metadata": {
            "name": name,
            "namespace": runner.HYBRID_NAMESPACE,
            "labels": labels,
        },
        "spec": {
            "serviceName": name,
            "replicas": replicas,
            "selector": {
                "matchLabels": dict(ownership.replica_selector(stage))
            },
            "template": template,
        },
    }


def _statefulsets(replicas=1, *, template_marker=None):
    return {
        "items": [
            _statefulset(stage, replicas, template_marker=template_marker)
            for stage in range(1, 4)
        ]
    }


def _ready_pod(stage, ordinal):
    ownership = DEFAULT_HYBRID_KERNEL_OWNERSHIP
    name = f"hybrid-stage-{stage}-{ordinal}"
    return {
        "metadata": {
            "name": name,
            "namespace": runner.HYBRID_NAMESPACE,
            "uid": f"uid-{name}",
            "labels": dict(ownership.replica_labels(stage)),
        },
        "status": {
            "phase": "Running",
            "conditions": [{"type": "Ready", "status": "True"}],
            "containerStatuses": [
                {"name": "private-processor", "restartCount": 0},
                {"name": "public-forwarder", "restartCount": 0},
            ],
        },
    }


def _serving_pods(replicas=1):
    return {
        "items": [
            _ready_pod(stage, ordinal)
            for stage in range(1, 4)
            for ordinal in range(replicas)
        ]
        + [
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
                "status": {
                    "phase": "Running",
                    "conditions": [{"type": "Ready", "status": "True"}],
                    "containerStatuses": [
                        {"name": "flow-generator", "restartCount": 0}
                    ],
                },
            }
        ]
    }


def _names(names, *, namespace=None):
    return {
        "items": [
            {
                "metadata": {
                    "name": name,
                    **({"namespace": namespace} if namespace else {}),
                }
            }
            for name in names
        ]
    }


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


def _pure_input(*, slot_id=1, beliefs=None):
    inputs = load_controller_input_document(PHASE6 / "controller-inputs.json")
    profiles = load_runtime_profile_document(PHASE6 / "runtime-profiles.json")
    admission = {item.choice: item for item in inputs.admission}
    uniform = (0.25, 0.25, 0.25, 0.25)
    return HybridSlotInput(
        configuration=inputs.configuration,
        parameters=DEFAULT_HYBRID_POLICY_PARAMETERS,
        root_seed=2050,
        slot_id=slot_id,
        flows=tuple(HybridFlow(flow_id) for flow_id in range(1, 4)),
        replicas=tuple(
            HybridReplica(
                choice=profile.choice,
                belief=uniform if beliefs is None else beliefs[profile.choice],
                ready=True,
                max_assigned_flows=admission[
                    profile.choice
                ].max_assigned_flows,
                hidden_state=profile.hidden_state,
            )
            for profile in profiles.profiles
        ),
        planning_pair_links=inputs.planning_pair_links,
        simulated_pair_outcomes=inputs.planning_pair_links,
        initial_loads=GlobalLoadState.empty(inputs.configuration),
    )


def _kernelized(result):
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
                pod_name=(
                    f"hybrid-stage-{item.choice.stage}-{item.choice.replica - 1}"
                ),
                pod_uid=f"uid-{item.choice.stage}-{item.choice.replica}",
                endpoint="http://selected",
            ),
        )
        for item in result.observations
    )
    slot = SimpleNamespace(**vars(result))
    slot.observations = observations
    discovery = SimpleNamespace(
        replicas=tuple(
            SimpleNamespace(
                choice=ReplicaChoice(stage, replica),
                pod_name=f"hybrid-stage-{stage}-{replica - 1}",
                pod_uid=f"uid-{stage}-{replica}",
                node_name="ibg-hybrid-control-plane",
            )
            for stage in range(1, 4)
            for replica in range(1, 3)
        )
    )
    return SimpleNamespace(slot=slot, discovery=discovery)


def test_phase6_documents_are_complete_append_only_and_belief_free():
    old_runtime = _mapping(PHASE4 / "runtime-profiles.json")
    old_controller = _mapping(PHASE4 / "controller-inputs.json")
    new_runtime = _mapping(PHASE6 / "runtime-profiles.json")
    new_controller = _mapping(PHASE6 / "controller-inputs.json")

    expansion = validate_append_only_profile_expansion(
        deployed_runtime=old_runtime,
        deployed_controller=old_controller,
        proposed_runtime=new_runtime,
        proposed_controller=new_controller,
        existing_replica_count=1,
        expected_configuration=runner.PHASE6_PROFILE_BOUNDARY.configuration,
        expected_source_identity=runner.PHASE6_PROFILE_BOUNDARY.source_identity,
    )

    assert expansion.added_runtime_identities == tuple(
        ReplicaChoice(stage, 2) for stage in range(1, 4)
    )
    assert expansion.added_admission_identities == expansion.added_runtime_identities
    assert len(expansion.added_planning_pairs) == 9
    assert "belief" not in json.dumps(new_runtime).lower()
    assert "belief" not in json.dumps(new_controller).lower()
    assert "hidden_state" not in json.dumps(new_controller)
    assert "observation_seed" not in json.dumps(new_controller)


@pytest.mark.parametrize(
    ("document", "path", "value", "message"),
    (
        ("runtime", ("profiles", 0, "hidden_state"), 1, "identity/state/seed"),
        ("runtime", ("profiles", 0, "observation_seed"), 999, "identity/state/seed"),
        ("controller", ("admission", 0, "max_assigned_flows"), 3, "capacity"),
        ("controller", ("planning_pair_links", 0, "latency_ms"), 4.0, "planning link"),
    ),
)
def test_phase6_rejects_existing_profile_drift(document, path, value, message):
    old_runtime = _mapping(PHASE4 / "runtime-profiles.json")
    old_controller = _mapping(PHASE4 / "controller-inputs.json")
    new_runtime = _mapping(PHASE6 / "runtime-profiles.json")
    new_controller = _mapping(PHASE6 / "controller-inputs.json")
    target = new_runtime if document == "runtime" else new_controller
    target[path[0]][path[1]][path[2]] = value

    with pytest.raises(HybridKernelProfileExpansionError, match=message):
        validate_append_only_profile_expansion(
            deployed_runtime=old_runtime,
            deployed_controller=old_controller,
            proposed_runtime=new_runtime,
            proposed_controller=new_controller,
            existing_replica_count=1,
            expected_configuration=runner.PHASE6_PROFILE_BOUNDARY.configuration,
            expected_source_identity=runner.PHASE6_PROFILE_BOUNDARY.source_identity,
        )


def test_phase6_rejects_partial_duplicate_unexpected_and_forbidden_fields():
    old_runtime = _mapping(PHASE4 / "runtime-profiles.json")
    old_controller = _mapping(PHASE4 / "controller-inputs.json")

    mutations = []
    partial = _mapping(PHASE6 / "runtime-profiles.json")
    partial["profiles"].pop()
    mutations.append((partial, _mapping(PHASE6 / "controller-inputs.json")))
    duplicate = _mapping(PHASE6 / "runtime-profiles.json")
    duplicate["profiles"][-1] = copy.deepcopy(duplicate["profiles"][0])
    mutations.append((duplicate, _mapping(PHASE6 / "controller-inputs.json")))
    forbidden = _mapping(PHASE6 / "runtime-profiles.json")
    forbidden["profiles"][0]["belief"] = [0.25] * 4
    mutations.append((forbidden, _mapping(PHASE6 / "controller-inputs.json")))
    incomplete_links = _mapping(PHASE6 / "controller-inputs.json")
    incomplete_links["planning_pair_links"].pop()
    mutations.append((_mapping(PHASE6 / "runtime-profiles.json"), incomplete_links))

    for runtime, controller in mutations:
        with pytest.raises(HybridKernelProfileExpansionError):
            validate_append_only_profile_expansion(
                deployed_runtime=old_runtime,
                deployed_controller=old_controller,
                proposed_runtime=runtime,
                proposed_controller=controller,
                existing_replica_count=1,
                expected_configuration=runner.PHASE6_PROFILE_BOUNDARY.configuration,
                expected_source_identity=runner.PHASE6_PROFILE_BOUNDARY.source_identity,
            )


def test_phase6_pure_gate_has_complete_routes_telemetry_loads_and_retention():
    inputs = load_controller_input_document(PHASE6 / "controller-inputs.json")
    first = run_hybrid_slot(_pure_input())
    second = run_hybrid_slot(
        _pure_input(slot_id=2, beliefs=first.beliefs_after_mapping)
    )

    class FakeController:
        outcomes = [_kernelized(first), _kernelized(second)]

        def run_slot(self, slot_id):
            outcome = self.outcomes.pop(0)
            assert outcome.slot.slot_id == slot_id
            return outcome

    evidence = run_small_live_gate(FakeController(), inputs)
    first_routes = {
        tuple(item["selected_stages"]) for item in evidence[0]["placements"]
    }
    assert {(1, 3), (2, 3)}.issubset(first_routes)
    assert all(item["observation_count"] == 6 for item in evidence)
    assert all(item["measured_pair_count"] == 3 for item in evidence)
    assert all(item["skipped_stage_absent"] for item in evidence)
    assert all(item["pure_kernel_replay_parity"] for item in evidence)
    assert evidence[1]["beliefs_before"] == evidence[0]["beliefs_after"]
    assert first.final_loads.loads == ((1, 1), (1, 1), (1, 1))


class FakePhase6Cluster:
    def __init__(self, *, template_drift=False):
        self.replicas = 1
        self.runtime = _mapping(PHASE4 / "runtime-profiles.json")
        self.controller = _mapping(PHASE4 / "controller-inputs.json")
        self.commands = []
        self.template_drift = template_drift

    def execute(self, command, capture_output):
        self.commands.append((command, capture_output))
        if command == ("kind", "get", "clusters"):
            return "ibg-hybrid\n"
        if command == runner._kubectl("get", "nodes", "-o", "json"):
            return json.dumps(_names(["ibg-hybrid-control-plane"]))
        if command == runner._kubectl("get", "namespaces", "-o", "json"):
            return json.dumps(
                _names(["default", "kube-system", runner.HYBRID_NAMESPACE])
            )
        if command == runner._kubectl("get", "pods", "-A", "-o", "json"):
            return json.dumps(_serving_pods(self.replicas))
        if command == runner._kubectl(
            "get", "pods", "-n", runner.HYBRID_NAMESPACE, "-o", "json"
        ):
            return json.dumps(_serving_pods(self.replicas))
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
        if command == ("kind", "get", "nodes", "--name", "ibg-hybrid"):
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
        if command[:4] == (
            "kubectl",
            "--context",
            runner.KUBECTL_CONTEXT,
            "apply",
        ) and "-k" in command:
            directory = Path(command[command.index("-k") + 1])
            kustomization = (directory / "kustomization.yaml").read_text()
            count = {
                int(line.split(":", 1)[1])
                for line in kustomization.splitlines()
                if line.strip().startswith("count:")
            }.pop()
            if "--dry-run=server" in command:
                marker = "drift" if self.template_drift else None
                return json.dumps(_statefulsets(count, template_marker=marker))
            self.runtime = _mapping(PHASE6 / "runtime-profiles.json")
            self.controller = _mapping(PHASE6 / "controller-inputs.json")
            return ""
        if "scale" in command:
            count = int(
                next(item for item in command if item.startswith("--replicas="))
                .split("=", 1)[1]
            )
            self.replicas = count
            return ""
        if "logs" in command:
            return '{"configuration":{"num_flows":3,"num_replicas":2}}\n'
        return ""


def test_phase6_runner_reconciles_profiles_before_only_missing_ordinals(
    monkeypatch, capsys
):
    cluster = FakePhase6Cluster()
    monkeypatch.setattr(
        runner,
        "_local_platform_image_id",
        lambda execute, image: (
            SERVICE_ID if image == runner.SERVICE_IMAGE else CONTROLLER_ID
        ),
    )
    monkeypatch.setattr(
        runner, "_reconcile_phase75_controller_sources", lambda execute: None
    )

    runner.run_small(
        skip_build=True,
        requested_flows=3,
        requested_stages=3,
        requested_replicas=2,
        rollout_batch_size=1,
        execute=cluster.execute,
    )
    commands = [command for command, _capture in cluster.commands]
    actual_apply = next(
        index
        for index, command in enumerate(commands)
        if "apply" in command and "-k" in command and "--dry-run=server" not in command
    )
    scale = next(index for index, command in enumerate(commands) if "scale" in command)
    job = next(
        index
        for index, command in enumerate(commands)
        if "apply" in command and str(runner.DYNAMIC_CONTROLLER_JOB) in command
    )

    assert actual_apply < scale < job
    assert cluster.replicas == 2
    assert not any(command[:2] == ("docker", "build") for command in commands)
    assert not any("restart" in command for command in commands)
    assert not any(command[:3] == ("kind", "load", "docker-image") for command in commands)
    output = capsys.readouterr().out
    assert output.startswith(
        "Selected Hybrid topology: 3 flows x 3 stages x 2 replicas per stage\n"
    )
    assert output.endswith("\n")


def test_phase6_template_drift_fails_before_configmap_apply_or_scale(monkeypatch):
    cluster = FakePhase6Cluster(template_drift=True)
    monkeypatch.setattr(
        runner,
        "_local_platform_image_id",
        lambda execute, image: (
            SERVICE_ID if image == runner.SERVICE_IMAGE else CONTROLLER_ID
        ),
    )
    monkeypatch.setattr(
        runner, "_reconcile_phase75_controller_sources", lambda execute: None
    )

    with pytest.raises(RuntimeError, match="changes a StatefulSet Pod template"):
        runner.run_small(
            skip_build=True,
            requested_replicas=2,
            execute=cluster.execute,
        )
    commands = [command for command, _capture in cluster.commands]
    assert not any(
        "apply" in command and "-k" in command and "--dry-run=server" not in command
        for command in commands
    )
    assert not any("scale" in command for command in commands)


def test_phase6_overlay_and_job_preserve_runtime_resource_boundaries():
    rendered = subprocess.run(
        ["kubectl", "kustomize", str(PHASE6)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert rendered.returncode == 0, rendered.stderr
    assert rendered.stdout.count("kind: StatefulSet") == 3
    assert rendered.stdout.count("replicas: 2") == 3
    assert "kind: Job" not in rendered.stdout
    assert "64Mi" not in rendered.stdout
    assert "memory: 768Mi" in rendered.stdout
    assert "memory: 256Mi" in rendered.stdout
    assert "--workers" in rendered.stdout
    assert '"2"' in rendered.stdout
    assert "--timeout-keep-alive" in rendered.stdout
    assert '"30"' in rendered.stdout
    kustomization = (PHASE6 / "kustomization.yaml").read_text()
    assert "disableNameSuffixHash: true" in kustomization
    assert "checksum" not in kustomization
    assert "annotation" not in kustomization

    job = (PHASE6 / "controller-job.yaml").read_text()
    assert "ibg-hybrid-controller-phase6" in job
    assert "ibg-hybrid-testbed:kernel-controller-v1" in job
    assert "ibg-hybrid-runtime-profiles" not in job
    assert "hidden_state" not in job
    assert "belief" not in job
    assert "--policy" not in job


def test_phase6_requires_explicit_flow_for_later_replica_counts():
    boundary = runner._profile_boundary(
        3, requested_flows=5, requested_stages=3
    )
    assert boundary.configuration.num_flows == 5
    assert boundary.configuration.num_replicas == 3
    with pytest.raises(RuntimeError, match="--flow is required"):
        runner._profile_boundary(3)


def test_phase6_dimension_cli_matches_exact_and_milp_and_preserves_profiles():
    parsed = runner.parse_args(
        [
            "run-small",
            "--skip-build",
            "--flows",
            "3",
            "--stages",
            "3",
            "--replicas",
            "2",
        ]
    )
    assert parsed.requested_flows == 3
    assert parsed.requested_stages == 3
    assert parsed.requested_replicas == 2
    phase6 = runner._profile_boundary(
        2, requested_flows=3, requested_stages=3
    )
    phase4 = runner._profile_boundary(1)
    assert phase6.configuration == runner.PHASE6_PROFILE_BOUNDARY.configuration
    assert phase4.configuration == runner.PHASE4_PROFILE_BOUNDARY.configuration
    assert phase6.runtime_document == _mapping(PHASE6 / "runtime-profiles.json")
    assert phase6.controller_document == _mapping(PHASE6 / "controller-inputs.json")
    assert phase4.runtime_document == _mapping(PHASE4 / "runtime-profiles.json")
    assert phase4.controller_document == _mapping(PHASE4 / "controller-inputs.json")


@pytest.mark.parametrize(
    ("flows", "stages", "replicas", "message"),
    (
        (0, 3, 2, "flow count must be a positive integer"),
        (3, 3, 0, "replica count must be a positive integer"),
        (3, 4, 2, "exactly three stages"),
    ),
)
def test_phase6_invalid_dimensions_fail_before_cluster_access(
    flows, stages, replicas, message
):
    commands = []

    with pytest.raises(RuntimeError, match=message):
        runner.run_small(
            requested_flows=flows,
            requested_stages=stages,
            requested_replicas=replicas,
            execute=lambda command, capture: commands.append(command) or "",
        )

    assert commands == []


def test_phase6_imports_are_silent_rng_neutral_and_file_safe(tmp_path):
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    code = (
        "import random,numpy as np; random.seed(61); np.random.seed(16); "
        "p=random.getstate(); n=np.random.get_state(); "
        "import IBG_Hybrid.kernel_profile_expansion; "
        "import scripts.run_hybrid_kernel_phase4; "
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
