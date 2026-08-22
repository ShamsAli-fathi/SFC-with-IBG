import json
from pathlib import Path

import pytest

from scripts import run_hybrid_kernel_phase4 as runner


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_JOBS = (
    ROOT / "deploy" / "hybrid-kubernetes" / "controller-job.yaml",
    runner.DYNAMIC_CONTROLLER_JOB,
    runner.CONTROLLER_JOB,
    runner.PHASE6_CONTROLLER_JOB,
    runner.PHASE7_CONTROLLER_JOB,
    runner.PHASE75_CONTROLLER_JOB,
    runner.PHASE8_GATE1_CONTROLLER_JOB,
)


def _nodes(*, worker_cpu: str, worker_memory: str):
    return {
        "items": [
            {
                "metadata": {
                    "name": runner.CONTROL_PLANE_NODE_NAME,
                    "labels": {"node-role.kubernetes.io/control-plane": ""},
                },
                "status": {
                    "conditions": [{"type": "Ready", "status": "True"}],
                    "allocatable": {"cpu": "8", "memory": "32Gi"},
                },
            },
            {
                "metadata": {
                    "name": runner.WORKER_NODE_NAME,
                    "labels": {
                        runner.WORKLOAD_NODE_LABEL: (
                            runner.WORKLOAD_NODE_LABEL_VALUE
                        )
                    },
                },
                "status": {
                    "conditions": [{"type": "Ready", "status": "True"}],
                    "allocatable": {
                        "cpu": worker_cpu,
                        "memory": worker_memory,
                    },
                },
            },
        ]
    }


def _worker_system_pods():
    return {
        "items": [
            {
                "metadata": {
                    "name": "worker-system",
                    "namespace": "kube-system",
                },
                "spec": {
                    "nodeName": runner.WORKER_NODE_NAME,
                    "containers": [
                        {
                            "name": "worker-system",
                            "resources": {
                                "requests": {
                                    "cpu": "200m",
                                    "memory": "64Mi",
                                }
                            },
                        }
                    ],
                },
                "status": {"phase": "Running"},
            }
        ]
    }


def _capacity_executor(*, worker_cpu: str, worker_memory: str):
    def execute(command, capture_output):
        assert capture_output
        if command == runner._kubectl("get", "nodes", "-o", "json"):
            return json.dumps(
                _nodes(
                    worker_cpu=worker_cpu,
                    worker_memory=worker_memory,
                )
            )
        if command == runner._kubectl("get", "pods", "-A", "-o", "json"):
            return json.dumps(_worker_system_pods())
        raise AssertionError(command)

    return execute


def test_every_controller_job_uses_the_same_soft_cpu_request():
    assert len(CONTROLLER_JOBS) == len(set(CONTROLLER_JOBS)) == 7
    for path in CONTROLLER_JOBS:
        job = path.read_text(encoding="utf-8")
        assert job.count('requests: {cpu: "1", memory: 256Mi}') == 1
        assert job.count('limits: {cpu: "2", memory: 1Gi}') == 1
        assert "cpu: 100m" not in job
        assert job.count("nodeSelector:") == 1
        assert f'{runner.WORKLOAD_NODE_LABEL}: "true"' in job


def test_soft_priority_adds_no_exclusive_cpu_or_topology_mechanism():
    forbidden = (
        "affinity:",
        "cpuManagerPolicy",
        "cpuset",
        "exclusive",
        "hostNetwork:",
        "hostPID:",
        "nodeName:",
        "runtimeClassName:",
    )
    for path in CONTROLLER_JOBS:
        job = path.read_text(encoding="utf-8")
        assert all(field not in job for field in forbidden)

    kind = runner.KIND_CONFIG.read_text(encoding="utf-8")
    assert kind.count("role: control-plane") == 1
    assert kind.count("role: worker") == 1
    assert kind.count("role:") == 2


def test_mc_and_deterministic_lookahead_templates_share_resources():
    lookahead = runner.PHASE7_CONTROLLER_JOB.read_text(encoding="utf-8")
    manual_mc = runner.PHASE75_CONTROLLER_JOB.read_text(encoding="utf-8")
    for job in (lookahead, manual_mc):
        assert 'requests: {cpu: "1", memory: 256Mi}' in job
        assert 'limits: {cpu: "2", memory: 1Gi}' in job
    assert runner._phase75_controller_arguments("lookahead", None) == (
        "--policy",
        "lookahead",
    )
    assert runner._phase75_controller_arguments("mc", 2) == (
        "--policy",
        "mc",
        "--mc-workers",
        "2",
    )


def test_resource_preflight_accounts_for_one_cpu_and_accepts_exact_fit():
    result = runner._validate_node_resource_capacity(
        _capacity_executor(worker_cpu="1475m", worker_memory="1Gi"),
        existing_replica_count=0,
        requested_replica_count=1,
    )

    assert runner.CONTROLLER_CPU_REQUEST_MILLI == 1000
    assert runner.CONTROLLER_MEMORY_REQUEST_BYTES == 256 * 1024**2
    assert result.requested_cpu_milli == result.allocatable_cpu_milli == 1475
    assert result.requested_memory_bytes == result.allocatable_memory_bytes
    assert result.requested_memory_bytes == 1024**3
    assert result.added_stage_pods == 3


def test_resource_preflight_rejects_cpu_one_millicpu_below_request():
    with pytest.raises(RuntimeError, match=r"cpu=1475m/1474m"):
        runner._validate_node_resource_capacity(
            _capacity_executor(worker_cpu="1474m", worker_memory="1Gi"),
            existing_replica_count=0,
            requested_replica_count=1,
        )


def test_resource_preflight_rejects_memory_one_byte_below_request():
    with pytest.raises(
        RuntimeError,
        match=r"memory=1073741824/1073741823 bytes",
    ):
        runner._validate_node_resource_capacity(
            _capacity_executor(
                worker_cpu="1475m",
                worker_memory=str(1024**3 - 1),
            ),
            existing_replica_count=0,
            requested_replica_count=1,
        )
