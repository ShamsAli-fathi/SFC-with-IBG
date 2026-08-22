import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from IBG_Hybrid.kernel_infrastructure_contract import (
    DEFAULT_HYBRID_KERNEL_OWNERSHIP,
)
from IBG_Hybrid.kernel_resource_evidence import (
    BASELINE_PROCESSOR_MEMORY,
    CANDIDATE_PROCESSOR_MEMORY,
    HybridKernelResourceEvidenceError,
    cgroup_delta,
    detect_resource_profile,
    evaluate_processor_candidate,
    parse_cgroup_snapshot,
    parse_crictl_stats,
    validate_processor_only_transition,
)
from scripts import run_hybrid_kernel_phase4 as runner
from scripts import run_hybrid_kernel_phase7 as phase7


ROOT = Path(__file__).resolve().parents[1]
OWNERSHIP = DEFAULT_HYBRID_KERNEL_OWNERSHIP


def _resources(request_memory, limit_memory, *, processor=True):
    return {
        "requests": {
            "cpu": "50m" if processor else "25m",
            "memory": request_memory,
        },
        "limits": {
            "cpu": "1",
            "memory": limit_memory,
        },
    }


def _statefulsets(profile=BASELINE_PROCESSOR_MEMORY):
    items = []
    for stage in range(1, 4):
        labels = dict(OWNERSHIP.replica_labels(stage))
        items.append(
            {
                "apiVersion": "apps/v1",
                "kind": "StatefulSet",
                "metadata": {
                    "name": f"hybrid-stage-{stage}",
                    "namespace": OWNERSHIP.namespace,
                    "labels": labels,
                },
                "spec": {
                    "serviceName": f"hybrid-stage-{stage}",
                    "replicas": 2,
                    "selector": {
                        "matchLabels": dict(OWNERSHIP.replica_selector(stage))
                    },
                    "template": {
                        "metadata": {"labels": labels},
                        "spec": {
                            "containers": [
                                {
                                    "name": "private-processor",
                                    "command": ["python3", "-m", "uvicorn"],
                                    "resources": _resources(
                                        profile.request, profile.limit
                                    ),
                                },
                                {
                                    "name": "public-forwarder",
                                    "command": [
                                        "python3",
                                        "-m",
                                        "uvicorn",
                                        "--workers",
                                        "2",
                                        "--timeout-keep-alive",
                                        "30",
                                    ],
                                    "resources": _resources(
                                        "128Mi", "256Mi", processor=False
                                    ),
                                },
                            ]
                        },
                    },
                },
            }
        )
    return {"items": items}


def _cgroup(*, usage=100, throttled=2, peak=48 * 1024 * 1024, oom=0, rss=False):
    process = "\n__PROCESS_STATUS__\nVmRSS:\t42000 kB\n" if rss else ""
    return parse_cgroup_snapshot(
        "__CPU__\n"
        f"usage_usec {usage}\n"
        "nr_periods 10\n"
        "nr_throttled 1\n"
        f"throttled_usec {throttled}\n"
        "__MEMORY_CURRENT__\n"
        "44000000\n"
        "__MEMORY_PEAK__\n"
        f"{peak}\n"
        "__MEMORY_EVENTS__\n"
        "low 0\nhigh 0\nmax 0\n"
        f"oom {oom}\n"
        "oom_kill 0\noom_group_kill 0\n"
        f"{process}"
    )


def _stats(container_name="private-processor", working_set=44 * 1024 * 1024):
    return {
        "stats": [
            {
                "attributes": {
                    "id": "a" * 64,
                    "labels": {
                        "io.kubernetes.container.name": container_name,
                        "io.kubernetes.pod.name": "hybrid-stage-1-0",
                        "io.kubernetes.pod.namespace": OWNERSHIP.namespace,
                        "io.kubernetes.pod.uid": "pod-uid",
                    },
                },
                "cpu": {
                    "timestamp": "1000",
                    "usageCoreNanoSeconds": {"value": "500"},
                    "usageNanoCores": {"value": "50"},
                },
                "memory": {
                    "timestamp": "1000",
                    "workingSetBytes": {"value": str(working_set)},
                    "rssBytes": {"value": str(working_set - 1024)},
                },
            }
        ]
    }


def test_phase7_candidate_overlay_changes_processor_memory_only():
    baseline = _statefulsets(BASELINE_PROCESSOR_MEMORY)
    candidate = _statefulsets(CANDIDATE_PROCESSOR_MEMORY)
    validate_processor_only_transition(
        baseline, candidate, CANDIDATE_PROCESSOR_MEMORY
    )
    assert detect_resource_profile(baseline) == BASELINE_PROCESSOR_MEMORY
    assert detect_resource_profile(candidate) == CANDIDATE_PROCESSOR_MEMORY

    drift = copy.deepcopy(candidate)
    drift["items"][0]["spec"]["template"]["spec"]["containers"][1][
        "command"
    ].append("--changed")
    with pytest.raises(HybridKernelResourceEvidenceError, match="non-processor"):
        validate_processor_only_transition(
            baseline, drift, CANDIDATE_PROCESSOR_MEMORY
        )

    scaled = copy.deepcopy(candidate)
    for item in scaled["items"]:
        item["spec"]["replicas"] = 3
    with pytest.raises(HybridKernelResourceEvidenceError, match="replica count"):
        validate_processor_only_transition(
            baseline, scaled, CANDIDATE_PROCESSOR_MEMORY
        )


def test_phase7_deliberate_rollout_requires_new_stage_uids_only():
    before = tuple(
        runner.ServingPodProcessSnapshot(
            f"hybrid-stage-{stage}-{ordinal}",
            f"old-{stage}-{ordinal}",
            (("private-processor", 0), ("public-forwarder", 0)),
        )
        for stage in range(1, 4)
        for ordinal in range(2)
    ) + (
        runner.ServingPodProcessSnapshot(
            "ibg-hybrid-flow-generator-hash",
            "flow-uid",
            (("flow-generator", 0),),
        ),
    )
    after = tuple(
        runner.ServingPodProcessSnapshot(
            item.pod_name,
            item.pod_uid if item.pod_name.startswith("ibg-") else "new-" + item.pod_uid,
            item.container_restarts,
        )
        for item in before
    )
    runner._validate_deliberate_processor_rollout(before, after)

    unchanged_stage = list(after)
    unchanged_stage[0] = before[0]
    with pytest.raises(RuntimeError, match="did not replace"):
        runner._validate_deliberate_processor_rollout(before, tuple(unchanged_stage))


def test_phase7_runtime_and_cgroup_parsers_preserve_units_and_identity():
    samples = parse_crictl_stats(_stats())
    assert len(samples) == 1
    assert samples[0].memory_working_set_bytes == 44 * 1024 * 1024
    assert samples[0].cpu_usage_ns == 500

    before = _cgroup(usage=100, throttled=2, rss=True)
    after = _cgroup(usage=300, throttled=7, rss=True)
    delta = cgroup_delta(before, after)
    assert delta.cpu_usage_usec == 200
    assert delta.cpu_throttled_usec == 5
    assert before.process_rss_bytes == 42_000 * 1024

    malformed = _stats()
    malformed["stats"][0]["memory"]["timestamp"] = "999"
    with pytest.raises(HybridKernelResourceEvidenceError, match="correlated"):
        parse_crictl_stats(malformed)

    exited_controller = _stats(container_name="controller")
    del exited_controller["stats"][0]["cpu"]
    del exited_controller["stats"][0]["memory"]
    assert parse_crictl_stats(exited_controller) == ()

    exited_processor = _stats(container_name="private-processor")
    del exited_processor["stats"][0]["cpu"]
    del exited_processor["stats"][0]["memory"]
    assert parse_crictl_stats(exited_processor) == ()


def test_phase7_candidate_decision_requires_headroom_and_clean_health():
    sample = parse_crictl_stats(_stats())[0]
    clean_delta = cgroup_delta(_cgroup(usage=100), _cgroup(usage=300))
    accepted = evaluate_processor_candidate(
        samples=[sample],
        processor_deltas=[clean_delta],
        serving_restarts=0,
        fatal_event_count=0,
        post_ready_probe_failure_count=0,
        node_pressure=False,
        all_ready=True,
        controller_completed=True,
        controller_duration_seconds=20,
        controller_deadline_seconds=600,
    )
    assert accepted.accepted is True
    assert accepted.minimum_limit_headroom_bytes > 128 * 1024 * 1024

    rejected = evaluate_processor_candidate(
        samples=parse_crictl_stats(_stats(working_set=140 * 1024 * 1024)),
        processor_deltas=[
            cgroup_delta(_cgroup(usage=100), _cgroup(usage=300, oom=1))
        ],
        serving_restarts=1,
        fatal_event_count=1,
        post_ready_probe_failure_count=1,
        node_pressure=True,
        all_ready=False,
        controller_completed=False,
        controller_duration_seconds=400,
        controller_deadline_seconds=600,
    )
    assert rejected.accepted is False
    assert len(rejected.reasons) >= 6


def test_phase7_cli_is_explicit_and_fails_before_cluster_for_wrong_boundary():
    parsed = runner.parse_args(
        [
            "run-small",
            "--skip-build",
            "--flow",
            "3",
            "--stage",
            "3",
            "--replica",
            "2",
            "--processor-memory-profile",
            "candidate",
        ]
    )
    assert parsed.processor_memory_profile == "candidate"
    assert phase7.parse_args(
        ["--processor-memory-profile", "baseline"]
    ).processor_memory_profile == "baseline"

    commands = []
    with pytest.raises(RuntimeError, match="Phase 7 resource evidence"):
        runner.run_small(
            skip_build=True,
            requested_flows=2,
            requested_stages=3,
            requested_replicas=1,
            processor_memory_profile="candidate",
            execute=lambda command, capture: commands.append(command) or "",
        )
    assert commands == []


def test_phase7_manifests_preserve_job_and_runtime_boundaries():
    baseline = subprocess.run(
        ["kubectl", "kustomize", str(runner.PHASE7_OVERLAY)],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    candidate = subprocess.run(
        ["kubectl", "kustomize", str(runner.PHASE7_CANDIDATE_OVERLAY)],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    job = runner.PHASE7_CONTROLLER_JOB.read_text(encoding="utf-8")

    assert baseline.count("memory: 128Mi") >= 7
    assert baseline.count("memory: 768Mi") >= 4
    assert candidate.count("memory: 64Mi") == 3
    assert candidate.count("memory: 256Mi") >= 6
    assert candidate.count("cpu: 50m") == 4
    assert candidate.count("cpu: 25m") == 3
    assert "--workers\n        - \"2\"" in candidate
    assert "--timeout-keep-alive\n        - \"30\"" in candidate
    assert "containerPort: 8081" in candidate
    assert "containerPort: 8080" in candidate
    assert "MAX_ITERATIONS" in job and 'value: "5"' in job
    assert 'requests: {cpu: "1", memory: 256Mi}' in job
    assert 'limits: {cpu: "2", memory: 1Gi}' in job
    assert "--policy" not in job and "--mc-workers" not in job


def test_phase7_imports_are_silent_rng_neutral_and_file_safe(tmp_path):
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    code = (
        "import random,numpy as np; random.seed(71); np.random.seed(17); "
        "p=random.getstate(); n=np.random.get_state(); "
        "import IBG_Hybrid.kernel_resource_evidence; "
        "import scripts.run_hybrid_kernel_phase7; "
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
