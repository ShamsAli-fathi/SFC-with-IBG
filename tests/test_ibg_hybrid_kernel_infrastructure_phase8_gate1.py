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
    HYBRID_KERNEL_LOOKAHEAD_POOL_LIFECYCLE_VERSION,
    HYBRID_KERNEL_LOOKAHEAD_WORKERS,
)
from IBG_Hybrid.kernel_phase4_validation import run_small_live_gate
from IBG_Hybrid.kernel_phase8_evidence import (
    HybridKernelPhase8EvidenceError,
    validate_phase8_gate1_slots,
)
from IBG_Hybrid.kernel_profile_expansion import (
    HybridKernelProfileExpansionError,
    validate_flow_only_profile_expansion,
)
from IBG_Hybrid.kernel_runtime_profiles import load_runtime_profile_document
from IBG_Hybrid.phase0_contract import DEFAULT_HYBRID_POLICY_PARAMETERS
from IBG_Hybrid.runner import run_hybrid_slot
from IBG_Hybrid.slot_contracts import (
    HybridFlow,
    HybridReplica,
    HybridSimulationResult,
    HybridSlotInput,
)
from scripts import run_hybrid_kernel_phase4 as runner


ROOT = Path(__file__).resolve().parents[1]
PHASE6 = ROOT / "deploy" / "hybrid-kubernetes-phase6-3x3x2"
PHASE8 = ROOT / "deploy" / "hybrid-kubernetes-phase8-gate1-4x3x2"


def _mapping(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _pure_input(*, slot_id=1, beliefs=None):
    inputs = load_controller_input_document(PHASE8 / "controller-inputs.json")
    profiles = load_runtime_profile_document(PHASE8 / "runtime-profiles.json")
    admission = {item.choice: item.max_assigned_flows for item in inputs.admission}
    uniform = (0.25, 0.25, 0.25, 0.25)
    return HybridSlotInput(
        configuration=inputs.configuration,
        parameters=DEFAULT_HYBRID_POLICY_PARAMETERS,
        root_seed=2050,
        slot_id=slot_id,
        flows=tuple(HybridFlow(flow) for flow in range(1, 5)),
        replicas=tuple(
            HybridReplica(
                choice=profile.choice,
                belief=uniform if beliefs is None else beliefs[profile.choice],
                ready=True,
                max_assigned_flows=admission[profile.choice],
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
                    node_name=runner.WORKER_NODE_NAME,
                )
                for stage in range(1, 4)
                for replica in range(1, 3)
            )
        ),
    )


def _statefulsets():
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
                    "replicas": 2,
                    "selector": {
                        "matchLabels": dict(ownership.replica_selector(stage))
                    },
                    "template": {
                        "metadata": {"labels": labels},
                        "spec": {
                            "nodeSelector": {
                                runner.WORKLOAD_NODE_LABEL: (
                                    runner.WORKLOAD_NODE_LABEL_VALUE
                                )
                            },
                            "containers": [{"name": "serving"}],
                        },
                    },
                },
            }
        )
    return {"items": items}


def _serving_pods():
    ownership = DEFAULT_HYBRID_KERNEL_OWNERSHIP
    items = []
    for stage in range(1, 4):
        for ordinal in range(2):
            name = f"hybrid-stage-{stage}-{ordinal}"
            items.append(
                {
                    "metadata": {
                        "name": name,
                        "namespace": runner.HYBRID_NAMESPACE,
                        "uid": f"uid-{name}",
                        "labels": dict(ownership.replica_labels(stage)),
                    },
                    "spec": {"nodeName": runner.WORKER_NODE_NAME},
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
            "spec": {"nodeName": runner.WORKER_NODE_NAME},
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


def test_phase8_gate1_is_an_exact_flow_only_profile_transition():
    old_runtime = _mapping(PHASE6 / "runtime-profiles.json")
    old_controller = _mapping(PHASE6 / "controller-inputs.json")
    new_runtime = _mapping(PHASE8 / "runtime-profiles.json")
    new_controller = _mapping(PHASE8 / "controller-inputs.json")

    transition = validate_flow_only_profile_expansion(
        deployed_runtime=old_runtime,
        deployed_controller=old_controller,
        proposed_runtime=new_runtime,
        proposed_controller=new_controller,
        deployed_configuration=runner.PHASE6_PROFILE_BOUNDARY.configuration,
        target_configuration=runner.PHASE8_GATE1_PROFILE_BOUNDARY.configuration,
        deployed_source_identity=runner.PHASE6_PROFILE_BOUNDARY.source_identity,
        target_source_identity=runner.PHASE8_GATE1_PROFILE_BOUNDARY.source_identity,
    )

    assert transition.runtime_profile_count == 6
    assert transition.admission_count == 6
    assert transition.planning_pair_count == 12
    assert new_runtime["profiles"] == old_runtime["profiles"]
    assert new_controller["admission"] == old_controller["admission"]
    assert new_controller["planning_pair_links"] == old_controller["planning_pair_links"]
    assert "belief" not in json.dumps(new_runtime).lower()
    assert "belief" not in json.dumps(new_controller).lower()
    assert "hidden_state" not in json.dumps(new_controller)


@pytest.mark.parametrize(
    ("document", "section", "index", "field", "value", "message"),
    (
        ("runtime", "profiles", 0, "hidden_state", 1, "identity/state/seed"),
        ("runtime", "profiles", 0, "observation_seed", 999, "identity/state/seed"),
        ("controller", "admission", 0, "max_assigned_flows", 3, "capacity"),
        ("controller", "planning_pair_links", 0, "latency_ms", 4.0, "planning"),
    ),
)
def test_phase8_gate1_rejects_every_existing_profile_drift(
    document, section, index, field, value, message
):
    old_runtime = _mapping(PHASE6 / "runtime-profiles.json")
    old_controller = _mapping(PHASE6 / "controller-inputs.json")
    new_runtime = _mapping(PHASE8 / "runtime-profiles.json")
    new_controller = _mapping(PHASE8 / "controller-inputs.json")
    target = new_runtime if document == "runtime" else new_controller
    target[section][index][field] = value
    with pytest.raises(HybridKernelProfileExpansionError, match=message):
        validate_flow_only_profile_expansion(
            deployed_runtime=old_runtime,
            deployed_controller=old_controller,
            proposed_runtime=new_runtime,
            proposed_controller=new_controller,
            deployed_configuration=runner.PHASE6_PROFILE_BOUNDARY.configuration,
            target_configuration=runner.PHASE8_GATE1_PROFILE_BOUNDARY.configuration,
            deployed_source_identity=runner.PHASE6_PROFILE_BOUNDARY.source_identity,
            target_source_identity=runner.PHASE8_GATE1_PROFILE_BOUNDARY.source_identity,
        )


@pytest.mark.parametrize(
    ("document", "section"),
    (
        ("runtime", "profiles"),
        ("controller", "admission"),
        ("controller", "planning_pair_links"),
    ),
)
def test_phase8_gate1_rejects_incomplete_replica_owned_coverage(document, section):
    old_runtime = _mapping(PHASE6 / "runtime-profiles.json")
    old_controller = _mapping(PHASE6 / "controller-inputs.json")
    new_runtime = _mapping(PHASE8 / "runtime-profiles.json")
    new_controller = _mapping(PHASE8 / "controller-inputs.json")
    target = new_runtime if document == "runtime" else new_controller
    target[section].pop()
    with pytest.raises(HybridKernelProfileExpansionError):
        validate_flow_only_profile_expansion(
            deployed_runtime=old_runtime,
            deployed_controller=old_controller,
            proposed_runtime=new_runtime,
            proposed_controller=new_controller,
            deployed_configuration=runner.PHASE6_PROFILE_BOUNDARY.configuration,
            target_configuration=runner.PHASE8_GATE1_PROFILE_BOUNDARY.configuration,
            deployed_source_identity=runner.PHASE6_PROFILE_BOUNDARY.source_identity,
            target_source_identity=runner.PHASE8_GATE1_PROFILE_BOUNDARY.source_identity,
        )


def test_phase8_gate1_lookahead_has_complete_routes_telemetry_and_parity():
    inputs = load_controller_input_document(PHASE8 / "controller-inputs.json")
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
    validate_phase8_gate1_slots(evidence)
    assert evidence[1]["beliefs_before"] == evidence[0]["beliefs_after"]
    assert all(item["observation_count"] == 8 for item in evidence)
    assert all(item["measured_pair_count"] == 4 for item in evidence)
    assert all(item["policy_mode"] == "lookahead" for item in evidence)
    assert first.final_loads.loads == ((2, 1), (1, 1), (2, 1))

    persistent_pool_evidence = copy.deepcopy(evidence)
    for item in persistent_pool_evidence:
        item["lookahead_process_workers"] = HYBRID_KERNEL_LOOKAHEAD_WORKERS
        item["lookahead_pool_lifecycle_version"] = (
            HYBRID_KERNEL_LOOKAHEAD_POOL_LIFECYCLE_VERSION
        )
        item["active_child_processes_after_slot"] = (
            HYBRID_KERNEL_LOOKAHEAD_WORKERS
        )
    validate_phase8_gate1_slots(persistent_pool_evidence)


def test_phase8_gate1_evidence_rejects_mc_or_incomplete_telemetry():
    inputs = load_controller_input_document(PHASE8 / "controller-inputs.json")
    first = run_hybrid_slot(_pure_input())
    second = run_hybrid_slot(
        _pure_input(slot_id=2, beliefs=first.beliefs_after_mapping)
    )

    class FakeController:
        outcomes = [_kernelized(first), _kernelized(second)]

        def run_slot(self, slot_id):
            return self.outcomes.pop(0)

    evidence = list(run_small_live_gate(FakeController(), inputs))
    invalid = copy.deepcopy(evidence)
    invalid[0]["policy_mode"] = "mc"
    with pytest.raises(HybridKernelPhase8EvidenceError, match="lookahead"):
        validate_phase8_gate1_slots(invalid)
    invalid = copy.deepcopy(evidence)
    invalid[0]["observation_count"] = 7
    with pytest.raises(HybridKernelPhase8EvidenceError, match="eight"):
        validate_phase8_gate1_slots(invalid)
    invalid = copy.deepcopy(evidence)
    invalid[0]["lookahead_process_workers"] = HYBRID_KERNEL_LOOKAHEAD_WORKERS
    invalid[0]["active_child_processes_after_slot"] = (
        HYBRID_KERNEL_LOOKAHEAD_WORKERS
    )
    with pytest.raises(HybridKernelPhase8EvidenceError, match="pool lifecycle"):
        validate_phase8_gate1_slots(invalid)


def test_phase8_gate1_profiles_remain_compatible_without_a_tuple_whitelist():
    expected = (
        (2, 3, 1, runner.PHASE4_PROFILE_BOUNDARY),
        (3, 3, 2, runner.PHASE6_PROFILE_BOUNDARY),
        (4, 3, 2, runner.PHASE8_GATE1_PROFILE_BOUNDARY),
    )
    for flows, stages, replicas, historical in expected:
        generated = runner._profile_boundary(
            replicas, requested_flows=flows, requested_stages=stages
        )
        assert generated.configuration == historical.configuration
        assert generated.source_identity == historical.source_identity
        assert generated.runtime_document == _mapping(historical.runtime_profiles)
        assert generated.controller_document == _mapping(historical.controller_inputs)

    arbitrary = runner._profile_boundary(
        5, requested_flows=10, requested_stages=3
    )
    assert arbitrary.configuration.num_flows == 10
    assert arbitrary.configuration.num_replicas == 5

    for flows, stages, replicas in ((5, 4, 2), (0, 3, 2), (4, 3, 0)):
        commands = []
        with pytest.raises(RuntimeError):
            runner.run_small(
                skip_build=True,
                requested_flows=flows,
                requested_stages=stages,
                requested_replicas=replicas,
                execute=lambda command, capture: commands.append(command) or "",
            )
        assert commands == []

    commands = []
    with pytest.raises(RuntimeError, match="manual Kubernetes MC"):
        runner.run_small(
            skip_build=True,
            requested_flows=4,
            requested_stages=3,
            requested_replicas=2,
            controller_policy="mc",
            mc_workers=1,
            execute=lambda command, capture: commands.append(command) or "",
        )
    assert commands == []


def test_phase8_gate1_runner_reconciles_without_scale_restart_or_process_change(monkeypatch):
    calls = []
    pods = _serving_pods()
    monkeypatch.setattr(runner, "_kind_clusters", lambda execute: {runner.CLUSTER_NAME})
    monkeypatch.setattr(runner, "preflight", lambda execute: calls.append("preflight"))
    monkeypatch.setattr(runner, "_statefulset_inventory", lambda execute: _statefulsets())
    monkeypatch.setattr(
        runner,
        "_validate_live_profile_expansion",
        lambda execute, **kwargs: calls.append(("profile", kwargs["boundary"])),
    )
    monkeypatch.setattr(runner, "validate_node_images", lambda execute: calls.append("images"))
    monkeypatch.setattr(runner, "_pod_inventory", lambda execute: pods)
    monkeypatch.setattr(
        runner,
        "_apply_reconciled_boundary",
        lambda execute, **kwargs: calls.append(("apply", kwargs)),
    )
    monkeypatch.setattr(
        runner,
        "_validate_reconciled_profiles",
        lambda execute, **kwargs: calls.append(("reconciled", kwargs["boundary"])),
    )
    monkeypatch.setattr(
        runner,
        "_wait_for_target",
        lambda execute, **kwargs: calls.append(("ready", kwargs["replica_count"])),
    )
    monkeypatch.setattr(
        runner,
        "_reconcile_phase75_controller_sources",
        lambda execute: calls.append("controller-source"),
    )
    monkeypatch.setattr(
        runner,
        "_apply_controller_job",
        lambda execute, **kwargs: calls.append(("job", kwargs)),
    )
    commands = []

    def execute(command, capture):
        commands.append(command)
        if command == runner._kubectl("get", "namespaces", "-o", "json"):
            return json.dumps(
                {"items": [{"metadata": {"name": runner.HYBRID_NAMESPACE}}]}
            )
        return "{}\n" if "logs" in command else ""

    runner.run_small(
        skip_build=True,
        requested_flows=4,
        requested_stages=3,
        requested_replicas=2,
        execute=execute,
    )

    profile = next(item[1] for item in calls if isinstance(item, tuple) and item[0] == "profile")
    assert profile.configuration == runner.PHASE8_GATE1_PROFILE_BOUNDARY.configuration
    apply = next(item[1] for item in calls if isinstance(item, tuple) and item[0] == "apply")
    assert apply["replica_count"] == 2
    assert apply["expected_templates"] is not None
    job = next(item[1] for item in calls if isinstance(item, tuple) and item[0] == "job")
    assert job["controller_job"] == runner.DYNAMIC_CONTROLLER_JOB
    assert job["arguments"] is None
    assert "controller-source" in calls
    assert not any("scale" in command or "restart" in command for command in commands)
    assert not any(command[:2] == ("docker", "build") for command in commands)
    assert not any(command[:3] == ("kind", "load", "docker-image") for command in commands)


def test_phase8_gate1_overlay_preserves_candidate_resources_and_job_boundary():
    rendered = subprocess.run(
        ["kubectl", "kustomize", str(PHASE8)],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    job = (PHASE8 / "controller-job.yaml").read_text(encoding="utf-8")
    assert rendered.count("kind: StatefulSet") == 3
    assert rendered.count("replicas: 2") == 3
    assert rendered.count("memory: 64Mi") == 3
    assert rendered.count("cpu: 50m") == 4
    assert rendered.count("cpu: 25m") == 3
    assert "kind: Job" not in rendered
    assert "--workers\n        - \"2\"" in rendered
    assert "--timeout-keep-alive\n        - \"30\"" in rendered
    assert "ibg-hybrid-controller-phase8-gate1" in job
    assert "MAX_ITERATIONS" in job and 'value: "2"' in job
    assert "--policy" not in job and "--mc-workers" not in job
    assert "requests: {cpu: 100m, memory: 256Mi}" in job
    assert 'limits: {cpu: "2", memory: 1Gi}' in job
    assert "runtime-profiles" not in job
    assert "hidden_state" not in job and "belief" not in job


def test_phase8_gate1_imports_are_silent_rng_neutral_and_file_safe(tmp_path):
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    code = (
        "import random,numpy as np; random.seed(8); np.random.seed(81); "
        "p=random.getstate(); n=np.random.get_state(); "
        "import IBG_Hybrid.kernel_phase8_evidence; "
        "import scripts.run_hybrid_kernel_phase8; "
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
