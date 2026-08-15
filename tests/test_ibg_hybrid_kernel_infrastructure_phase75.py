import json
import os
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys

import pytest

from IBG_Hybrid import kernel_controller_cli
from IBG_Hybrid.contracts import GlobalLoadState
from IBG_Hybrid.kernel_controller import HybridKernelControllerAdapter
from IBG_Hybrid.kernel_controller_cli import (
    MAX_HYBRID_KERNEL_MC_WORKERS,
    parse_policy_arguments,
)
from IBG_Hybrid.kernel_controller_config import load_controller_input_document
from IBG_Hybrid.kernel_mc_evidence import (
    HybridKernelMcEvidenceError,
    parse_direct_child_pids,
    require_worker_count_decision_equality,
    validate_mc_slot_evidence,
)
from IBG_Hybrid.kernel_phase4_validation import _replay_kernel_semantics
from IBG_Hybrid.kernel_runtime_profiles import load_runtime_profile_document
from IBG_Hybrid.phase0_contract import DEFAULT_HYBRID_POLICY_PARAMETERS
from IBG_Hybrid.runner import run_hybrid_slot
from IBG_Hybrid.slot_contracts import HybridFlow, HybridReplica, HybridSlotInput
from scripts import run_hybrid_kernel_phase4 as runner
from scripts import run_hybrid_kernel_phase75 as phase75


ROOT = Path(__file__).resolve().parents[1]
PHASE6 = ROOT / "deploy" / "hybrid-kubernetes-phase6-3x3x2"
PHASE75 = ROOT / "deploy" / "hybrid-kubernetes-phase7.5-3x3x2"


def _phase6_input(*, slot_id=1, beliefs=None):
    inputs = load_controller_input_document(PHASE6 / "controller-inputs.json")
    profiles = load_runtime_profile_document(PHASE6 / "runtime-profiles.json")
    admission = {item.choice: item.max_assigned_flows for item in inputs.admission}
    uniform = (0.25, 0.25, 0.25, 0.25)
    return HybridSlotInput(
        configuration=inputs.configuration,
        parameters=DEFAULT_HYBRID_POLICY_PARAMETERS,
        root_seed=2050,
        slot_id=slot_id,
        flows=tuple(HybridFlow(flow) for flow in range(1, 4)),
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


def _slot_record(result, workers):
    return {
        "slot_id": result.slot_id,
        "configuration": {
            "num_flows": 3,
            "num_stages": 3,
            "num_replicas": 2,
            "stage_budget": 2,
        },
        "policy_mode": "mc",
        "mc_workers": workers,
        "explicit_policy": True,
        "placement_paths": ["monte-carlo"] * 3,
        "flow_order": list(result.flow_order),
        "placements": [
            {
                "flow_id": item.flow.flow_id,
                "selected_stages": list(item.action.stages),
                "selected_replicas": [choice.replica for choice in item.action.choices],
                "skipped_stage": item.skipped_stage,
            }
            for item in result.placements
        ],
        "final_loads": [list(row) for row in result.final_loads.loads],
        "observation_count": 6,
        "measured_pair_count": 3,
        "active_child_processes_after_slot": 0,
        "complete_placement_before_one_request": True,
        "skipped_stage_absent": True,
        "separated_jitter_valid": True,
        "seedless_kernel_provenance": True,
        "belief_retained_from_previous": True,
        "pure_kernel_replay_parity": True,
        "beliefs_before": {"value": result.slot_id},
        "beliefs_after": {"value": result.slot_id + 1},
    }


def test_phase75_cli_is_manual_only_bounded_and_defaults_to_lookahead():
    default = parse_policy_arguments([])
    assert default.policy_mode == "lookahead"
    assert default.mc_workers is None
    assert default.explicit_policy is False

    explicit = parse_policy_arguments(["--policy", "mc", "--mc-workers", "2"])
    assert explicit.policy_mode == "mc"
    assert explicit.mc_workers == 2
    assert MAX_HYBRID_KERNEL_MC_WORKERS == runner.MAX_HYBRID_KERNEL_MC_WORKERS == 2

    for arguments in (
        ["--policy", "mc"],
        ["--mc-workers", "1"],
        ["--policy", "lookahead", "--mc-workers", "1"],
        ["--policy", "mc", "--mc-workers", "0"],
        ["--policy", "mc", "--mc-workers", "3"],
    ):
        with pytest.raises(SystemExit):
            parse_policy_arguments(arguments)


def test_phase75_mc_cli_prints_each_completed_slot_before_return(
    monkeypatch, capsys
):
    result = run_hybrid_slot(_phase6_input())
    inputs = load_controller_input_document(PHASE6 / "controller-inputs.json")
    lifecycle = []

    monkeypatch.setattr(
        kernel_controller_cli,
        "_controller_from_environment",
        lambda **kwargs: (object(), inputs),
    )

    def fake_live_gate(controller, document, **kwargs):
        assert document is inputs
        assert kwargs["policy_mode"] == "mc"
        assert kwargs["mc_workers"] == 2
        lifecycle.append("gate-started")
        kwargs["on_slot_completed"](1, result, {"slot_id": result.slot_id})
        lifecycle.append("slot-printed")
        return ({"slot_id": result.slot_id},)

    monkeypatch.setattr(
        kernel_controller_cli,
        "run_small_live_gate",
        fake_live_gate,
    )
    assert kernel_controller_cli.main(["--policy", "mc", "--mc-workers", "2"]) == 0

    output = capsys.readouterr().out
    assert output.startswith("Iteration 1 (slot 1)\n")
    machine_line = output.splitlines()[-1]
    assert machine_line.startswith("HYBRID_SLOT_EVIDENCE=")
    evidence = json.loads(machine_line.split("=", 1)[1])
    assert evidence["controller_contract_version"]
    assert evidence["explicit_policy"] is True
    assert lifecycle == ["gate-started", "slot-printed"]


def test_kernel_controller_passes_explicit_mc_workers_without_hidden_state(monkeypatch):
    inputs = load_controller_input_document(PHASE6 / "controller-inputs.json")
    replicas = tuple(
        SimpleNamespace(
            choice=item.choice,
            pod_name=f"hybrid-stage-{item.choice.stage}-{item.choice.replica - 1}",
            pod_uid=f"uid-{item.choice.stage}-{item.choice.replica}",
            node_name=runner.WORKER_NODE_NAME,
            endpoint="http://example.invalid",
        )
        for item in inputs.admission
    )
    snapshot = SimpleNamespace(configuration=inputs.configuration, replicas=replicas)

    class Discovery:
        def wait_for_complete_ready(self, **kwargs):
            assert kwargs == {}
            return snapshot

    captured = {}

    def fake_run(slot_input, **kwargs):
        captured.update(kwargs)
        assert all(item.hidden_state is None for item in slot_input.replicas)
        kwargs["simulation_adapter"].requests_submitted = 1
        return SimpleNamespace(beliefs_after=slot_input.beliefs)

    monkeypatch.setattr("IBG_Hybrid.kernel_controller.run_hybrid_slot", fake_run)
    uniform = {item.choice: (0.25, 0.25, 0.25, 0.25) for item in inputs.admission}
    controller = HybridKernelControllerAdapter(
        controller_inputs=inputs,
        discovery=Discovery(),
        flow_generator=SimpleNamespace(),
        initial_beliefs=uniform,
        policy_mode="mc",
        mc_workers=2,
    )
    controller.run_slot(1)

    assert captured["policy_mode"] == "mc"
    assert captured["mc_workers"] == 2


def test_fixed_seed_pure_mc_worker_equality_and_kernel_replay_parity():
    slot_input = _phase6_input()
    one = run_hybrid_slot(slot_input, policy_mode="mc", mc_workers=1)
    multiple = run_hybrid_slot(slot_input, policy_mode="mc", mc_workers=2)
    one_record = _slot_record(one, 1)
    multi_record = _slot_record(multiple, 2)
    one_second = dict(one_record)
    one_second.update(
        slot_id=2,
        beliefs_before=one_record["beliefs_after"],
        beliefs_after={"value": 3},
    )
    multi_second = dict(multi_record)
    multi_second.update(
        slot_id=2,
        beliefs_before=multi_record["beliefs_after"],
        beliefs_after={"value": 3},
    )
    validate_mc_slot_evidence((one_record, one_second), worker_count=1)
    validate_mc_slot_evidence((multi_record, multi_second), worker_count=2)
    require_worker_count_decision_equality(
        (one_record, one_second), (multi_record, multi_second)
    )

    inputs = load_controller_input_document(PHASE6 / "controller-inputs.json")
    discovery = SimpleNamespace(
        replicas=tuple(SimpleNamespace(choice=item.choice) for item in inputs.admission)
    )
    assert _replay_kernel_semantics(
        outcome=SimpleNamespace(slot=one, discovery=discovery),
        inputs=inputs,
        policy_mode="mc",
        mc_workers=1,
    )


def test_phase75_worker_failure_closes_pool_and_never_falls_back_to_traffic(
    monkeypatch,
):
    events = []

    class FailingExecutor:
        def __init__(self, *, max_workers):
            events.append(("created", max_workers))

        def __enter__(self):
            return self

        def map(self, function, values):
            del function, values
            events.append(("map", None))
            raise RuntimeError("synthetic MC worker failure")

        def __exit__(self, kind, error, traceback):
            del kind, error, traceback
            events.append(("closed", None))

    class ForbiddenTraffic:
        def execute(self, **kwargs):
            del kwargs
            raise AssertionError("traffic ran after an MC worker failure")

    monkeypatch.setattr("IBG_Hybrid.runner.ProcessPoolExecutor", FailingExecutor)
    with pytest.raises(RuntimeError, match="synthetic MC worker failure"):
        run_hybrid_slot(
            _phase6_input(),
            policy_mode="mc",
            mc_workers=2,
            simulation_adapter=ForbiddenTraffic(),
        )

    assert events == [("created", 2), ("map", None), ("closed", None)]


def test_phase75_evidence_rejects_drift_and_parses_direct_children():
    sample = (
        "__CPU__\nusage_usec 1\nnr_periods 1\nnr_throttled 0\n"
        "throttled_usec 0\n__MEMORY_CURRENT__\n1\n__MEMORY_PEAK__\n2\n"
        "__MEMORY_EVENTS__\nlow 0\n__DIRECT_CHILDREN__\n19 7\n"
    )
    assert parse_direct_child_pids(sample) == (7, 19)
    with pytest.raises(HybridKernelMcEvidenceError, match="direct-child"):
        parse_direct_child_pids(sample.replace("19 7", "7 7"))

    first = _slot_record(run_hybrid_slot(_phase6_input(), policy_mode="mc", mc_workers=1), 1)
    second = dict(first)
    second.update(
        slot_id=2,
        beliefs_before=first["beliefs_after"],
        beliefs_after={"value": 3},
    )
    drift = dict(second)
    drift["final_loads"] = [[3, 0], [2, 0], [1, 0]]
    with pytest.raises(HybridKernelMcEvidenceError, match="differ"):
        require_worker_count_decision_equality((first, second), (first, drift))


def test_phase75_runner_rejects_invalid_selection_before_cluster_contact():
    for policy, workers in ((None, 1), ("lookahead", 1), ("mc", 0), ("mc", 3)):
        commands = []
        with pytest.raises(RuntimeError):
            runner.run_small(
                skip_build=True,
                requested_flows=3,
                requested_stages=3,
                requested_replicas=2,
                processor_memory_profile="candidate",
                controller_policy=policy,
                mc_workers=workers,
                execute=lambda command, capture: commands.append(command) or "",
            )
        assert commands == []


def test_phase75_job_and_overlay_preserve_service_resources_and_image():
    rendered = subprocess.run(
        ["kubectl", "kustomize", str(PHASE75)],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    job = (PHASE75 / "controller-job.yaml").read_text(encoding="utf-8")
    dockerfile = (
        ROOT / "deploy" / "hybrid-kubernetes" / "Dockerfile.controller"
    ).read_text(encoding="utf-8")

    assert rendered.count("memory: 64Mi") == 3
    assert rendered.count("cpu: 50m") == 4
    assert rendered.count("cpu: 25m") == 3
    assert "--workers\n        - \"2\"" in rendered
    assert "--timeout-keep-alive\n        - \"30\"" in rendered
    assert "kind: Job" not in rendered
    assert "IBG_Hybrid.kernel_controller_cli" in job
    assert "--policy" not in job and "--mc-workers" not in job
    assert "ibg-hybrid-testbed:kernel-controller-v1" in job
    assert "requests: {cpu: 100m, memory: 256Mi}" in job
    assert 'limits: {cpu: "2", memory: 1Gi}' in job
    assert "runtime-profiles" not in job
    assert "hidden_state" not in job and "belief" not in job
    assert "kernel_controller_cli.py" in dockerfile


def test_phase75_job_patch_and_source_configmap_are_controller_only():
    captured = {}

    def fake_execute(command, capture):
        if "configmap" in command and "--dry-run=client" in command:
            data = {
                source.name: source.read_text(encoding="utf-8")
                for source in runner.PHASE75_CONTROLLER_SOURCES
            }
            return json.dumps(
                {
                    "apiVersion": "v1",
                    "kind": "ConfigMap",
                    "metadata": {
                        "name": runner.PHASE75_CONTROLLER_SOURCE_CONFIGMAP,
                        "namespace": runner.HYBRID_NAMESPACE,
                    },
                    "data": data,
                }
            )
        if "--dry-run=client" in command and "controller-job.yaml" in " ".join(command):
            return json.dumps(
                {
                    "apiVersion": "batch/v1",
                    "kind": "Job",
                    "metadata": {
                        "name": runner.PHASE75_CONTROLLER_JOB_NAME,
                        "namespace": runner.HYBRID_NAMESPACE,
                    },
                    "spec": {
                        "template": {
                            "spec": {"containers": [{"name": "controller"}]}
                        }
                    },
                }
            )
        if command[3:5] == ("apply", "-f"):
            document = json.loads(Path(command[-1]).read_text(encoding="utf-8"))
            captured[document["kind"]] = document
            return ""
        raise AssertionError(command)

    runner._reconcile_phase75_controller_sources(fake_execute)
    runner._apply_controller_job(
        fake_execute,
        controller_job=runner.PHASE75_CONTROLLER_JOB,
        controller_job_name=runner.PHASE75_CONTROLLER_JOB_NAME,
        arguments=("--policy", "mc", "--mc-workers", "2"),
    )
    assert set(captured["ConfigMap"]["data"]) == {
        "console_output.py",
        "kernel_controller.py",
        "kernel_phase4_validation.py",
        "kernel_controller_cli.py",
    }
    assert captured["Job"]["spec"]["template"]["spec"]["containers"][0][
        "args"
    ] == ["--policy", "mc", "--mc-workers", "2"]


def test_phase75_imports_are_silent_rng_neutral_and_file_safe(tmp_path):
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    code = (
        "import random,numpy as np; random.seed(75); np.random.seed(57); "
        "p=random.getstate(); n=np.random.get_state(); "
        "import IBG_Hybrid.kernel_controller_cli; "
        "import IBG_Hybrid.kernel_mc_evidence; "
        "import scripts.run_hybrid_kernel_phase75; "
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
