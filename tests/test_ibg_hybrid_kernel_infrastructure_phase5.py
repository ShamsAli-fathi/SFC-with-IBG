import json
import io
import os
from pathlib import Path
import subprocess
import sys
import tarfile

import pytest

from IBG_Hybrid.kernel_infrastructure_contract import (
    DEFAULT_HYBRID_KERNEL_OWNERSHIP,
)
from IBG_Hybrid.kernel_rollout import (
    HybridKernelRolloutError,
    discover_existing_replica_state,
    plan_bounded_rollout,
    validate_ready_ordinal_coverage,
)
from scripts import run_hybrid_kernel_phase4 as runner


ROOT = Path(__file__).resolve().parents[1]
OWNERSHIP = DEFAULT_HYBRID_KERNEL_OWNERSHIP
SERVICE_ID = "a" * 64
CONTROLLER_ID = "b" * 64


def statefulset(stage, replicas=1, *, name=None, labels=None, selector=None):
    name = name or f"hybrid-stage-{stage}"
    required = dict(OWNERSHIP.replica_labels(stage))
    return {
        "apiVersion": "apps/v1",
        "kind": "StatefulSet",
        "metadata": {
            "name": name,
            "namespace": OWNERSHIP.namespace,
            "labels": required if labels is None else labels,
        },
        "spec": {
            "serviceName": name,
            "replicas": replicas,
            "selector": {
                "matchLabels": (
                    dict(OWNERSHIP.replica_selector(stage))
                    if selector is None
                    else selector
                )
            },
            "template": {
                "metadata": {"labels": required},
                "spec": {
                    "nodeSelector": {
                        runner.WORKLOAD_NODE_LABEL: runner.WORKLOAD_NODE_LABEL_VALUE
                    }
                },
            },
        },
    }


def statefulsets(replicas=1):
    return {
        "items": [statefulset(stage, replicas) for stage in range(1, 4)]
    }


def ready_pod(stage, ordinal, *, uid=None, restarts=0):
    name = f"hybrid-stage-{stage}-{ordinal}"
    return {
        "metadata": {
            "name": name,
            "namespace": OWNERSHIP.namespace,
            "uid": uid or f"uid-{name}",
            "labels": dict(OWNERSHIP.replica_labels(stage)),
        },
        "spec": {"nodeName": runner.WORKER_NODE_NAME},
        "status": {
            "phase": "Running",
            "conditions": [{"type": "Ready", "status": "True"}],
            "containerStatuses": [
                {"name": "private-processor", "restartCount": restarts},
                {"name": "public-forwarder", "restartCount": restarts},
            ],
        },
    }


def flow_generator_pod(*, uid="uid-flow-generator", restarts=0):
    return {
        "metadata": {
            "name": "ibg-hybrid-flow-generator-abcde",
            "namespace": OWNERSHIP.namespace,
            "uid": uid,
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
                {"name": "flow-generator", "restartCount": restarts}
            ],
        },
    }


def serving_pods(replicas=1):
    return {
        "items": [
            ready_pod(stage, ordinal)
            for stage in range(1, 4)
            for ordinal in range(replicas)
        ]
        + [flow_generator_pod()]
    }


def names_inventory(names, *, namespace=None):
    items = []
    for name in names:
        metadata = {
            "name": name,
            **({"namespace": namespace} if namespace else {}),
        }
        item = {"metadata": metadata}
        if name == runner.CONTROL_PLANE_NODE_NAME:
            metadata["labels"] = {"node-role.kubernetes.io/control-plane": ""}
            item["status"] = {
                "conditions": [{"type": "Ready", "status": "True"}]
            }
        elif name == runner.WORKER_NODE_NAME:
            metadata["labels"] = {
                runner.WORKLOAD_NODE_LABEL: runner.WORKLOAD_NODE_LABEL_VALUE
            }
            item["status"] = {
                "conditions": [{"type": "Ready", "status": "True"}]
            }
        items.append(item)
    return {"items": items}


class FakeCluster:
    def __init__(self, *, replicas=1, image_mismatch=False):
        self.replicas = replicas
        self.image_mismatch = image_mismatch
        self.commands = []
        self.reconciled_counts = []

    def execute(self, command, capture_output):
        self.commands.append((command, capture_output))
        if command == ("kind", "get", "clusters"):
            return "ibg-hybrid\n"
        if command == runner._kubectl("get", "nodes", "-o", "json"):
            return json.dumps(
                names_inventory(
                    [runner.CONTROL_PLANE_NODE_NAME, runner.WORKER_NODE_NAME]
                )
            )
        if command == runner._kubectl("get", "namespaces", "-o", "json"):
            return json.dumps(
                names_inventory(
                    ["default", "kube-system", runner.HYBRID_NAMESPACE]
                )
            )
        if command == runner._kubectl("get", "pods", "-A", "-o", "json"):
            return json.dumps(serving_pods(self.replicas))
        if command == runner._kubectl(
            "get", "pods", "-n", runner.HYBRID_NAMESPACE, "-o", "json"
        ):
            return json.dumps(serving_pods(self.replicas))
        if command == runner._kubectl(
            "get",
            "statefulsets",
            "-n",
            runner.HYBRID_NAMESPACE,
            "-o",
            "json",
        ):
            return json.dumps(statefulsets(self.replicas))
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
            return json.dumps(
                {
                    "items": [
                        {
                            "metadata": {
                                "name": "ibg-hybrid-runtime-profiles",
                                "namespace": runner.HYBRID_NAMESPACE,
                            },
                            "data": {
                                "runtime-profiles.json": runner.RUNTIME_PROFILES.read_text()
                            },
                        },
                        {
                            "metadata": {
                                "name": "ibg-hybrid-planning-links",
                                "namespace": runner.HYBRID_NAMESPACE,
                            },
                            "data": {
                                "controller-inputs.json": runner.CONTROLLER_INPUTS.read_text()
                            },
                        },
                    ]
                }
            )
        if command[:3] == ("docker", "image", "inspect"):
            image_id = (
                SERVICE_ID
                if command[3] == runner.SERVICE_IMAGE
                else CONTROLLER_ID
            )
            return json.dumps([{"Id": f"sha256:{image_id}"}])
        if command == ("kind", "get", "nodes", "--name", "ibg-hybrid"):
            return (
                f"{runner.CONTROL_PLANE_NODE_NAME}\n"
                f"{runner.WORKER_NODE_NAME}\n"
            )
        if (
            command[:2] == ("docker", "exec")
            and command[2] in runner.EXPECTED_NODE_NAMES
            and command[3] == "crictl"
        ):
            controller_id = "c" * 64 if self.image_mismatch else CONTROLLER_ID
            return json.dumps(
                {
                    "images": [
                        {
                            "id": f"sha256:{SERVICE_ID}",
                            "repoTags": [runner.NORMALIZED_SERVICE_IMAGE],
                        },
                        {
                            "id": f"sha256:{controller_id}",
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
            directory = command[command.index("-k") + 1]
            kustomization = Path(directory) / "kustomization.yaml"
            counts = {
                int(line.split(":", 1)[1])
                for line in kustomization.read_text().splitlines()
                if line.strip().startswith("count:")
            }
            assert len(counts) == 1
            count = counts.pop()
            if "--dry-run=server" in command:
                return json.dumps(statefulsets(count))
            self.reconciled_counts.append(count)
            self.replicas = count
            return ""
        if "scale" in command:
            replica_argument = next(
                value for value in command if value.startswith("--replicas=")
            )
            self.replicas = int(replica_argument.split("=", 1)[1])
            return ""
        if "logs" in command:
            return '{"slot_id":1}\n'
        return ""


def test_phase5_exact_three_stage_count_discovery_and_rejections():
    result = discover_existing_replica_state(statefulsets(3))
    assert result.replica_count == 3
    assert tuple(item.stage for item in result.stages) == (1, 2, 3)

    with pytest.raises(HybridKernelRolloutError, match="missing"):
        discover_existing_replica_state(
            {"items": [statefulset(1), statefulset(2)]}
        )
    with pytest.raises(HybridKernelRolloutError, match="inconsistent"):
        discover_existing_replica_state(
            {
                "items": [
                    statefulset(1, 1),
                    statefulset(2, 2),
                    statefulset(3, 1),
                ]
            }
        )
    with pytest.raises(HybridKernelRolloutError, match="foreign"):
        discover_existing_replica_state(
            {
                "items": [
                    statefulset(1),
                    statefulset(2),
                    statefulset(3),
                    statefulset(3, name="foreign-stage"),
                ]
            }
        )
    with pytest.raises(HybridKernelRolloutError, match="ownership labels"):
        discover_existing_replica_state(
            {
                "items": [
                    statefulset(1),
                    statefulset(2, labels={}),
                    statefulset(3),
                ]
            }
        )
    with pytest.raises(HybridKernelRolloutError, match="selector"):
        discover_existing_replica_state(
            {
                "items": [
                    statefulset(1),
                    statefulset(2, selector={"foreign": "selector"}),
                    statefulset(3),
                ]
            }
        )


def test_phase5_rollout_plan_is_direction_aware_and_deterministic():
    plan = plan_bounded_rollout(
        existing_count=2, requested_count=7, batch_size=2
    )
    assert tuple(batch.target_count for batch in plan.batches) == (4, 6, 7)
    assert tuple(batch.new_ordinals for batch in plan.batches) == (
        (2, 3),
        (4, 5),
        (6,),
    )
    assert plan_bounded_rollout(
        existing_count=5, requested_count=5, batch_size=2
    ).batches == ()
    up = plan_bounded_rollout(
        existing_count=5, requested_count=8, batch_size=2
    )
    assert tuple(batch.target_count for batch in up.batches) == (7, 8)
    assert up.added_ordinals == (5, 6, 7)
    assert up.removed_ordinals == ()
    down = plan_bounded_rollout(
        existing_count=8, requested_count=5, batch_size=2
    )
    assert down.direction == "down"
    assert tuple(batch.target_count for batch in down.batches) == (5,)
    assert down.added_ordinals == ()
    assert down.removed_ordinals == (5, 6, 7)


def test_phase5_ready_coverage_is_exact_at_each_target():
    validate_ready_ordinal_coverage(serving_pods(2), replica_count=2)
    missing = serving_pods(2)
    missing["items"] = [
        item
        for item in missing["items"]
        if item.get("metadata", {}).get("name") != "hybrid-stage-2-1"
    ]
    with pytest.raises(HybridKernelRolloutError, match="coverage mismatch"):
        validate_ready_ordinal_coverage(missing, replica_count=2)
    with pytest.raises(HybridKernelRolloutError, match="unexpected"):
        validate_ready_ordinal_coverage(serving_pods(2), replica_count=1)
    unready = serving_pods(1)
    unready["items"][0]["status"]["conditions"][0]["status"] = "False"
    with pytest.raises(HybridKernelRolloutError, match="not Running/Ready"):
        validate_ready_ordinal_coverage(unready, replica_count=1)


def test_phase5_node_image_validation_uses_normalized_tags_and_platform_ids(
    monkeypatch,
):
    monkeypatch.setattr(
        runner,
        "_local_platform_image_id",
        lambda execute, image: (
            SERVICE_ID if image == runner.SERVICE_IMAGE else CONTROLLER_ID
        ),
    )
    cluster = FakeCluster()
    runner.validate_node_images(cluster.execute)
    assert any("crictl" in command for command, _capture in cluster.commands)
    assert not any(
        command[:4] == ("kind", "load", "docker-image", "--name")
        for command, _capture in cluster.commands
    )

    mismatch = FakeCluster(image_mismatch=True)
    with pytest.raises(RuntimeError, match="absent or mismatched"):
        runner.validate_node_images(mismatch.execute)


def test_phase5_cluster_preflight_rejects_foreign_hybrid_namespace_pod():
    foreign = names_inventory(["foreign-workload"], namespace=runner.HYBRID_NAMESPACE)
    with pytest.raises(RuntimeError, match="foreign workload Pods"):
        runner.validate_cluster_inventory(
            nodes=names_inventory(
                [runner.CONTROL_PLANE_NODE_NAME, runner.WORKER_NODE_NAME]
            ),
            namespaces=names_inventory(
                ["default", "kube-system", runner.HYBRID_NAMESPACE]
            ),
            pods=foreign,
        )


def test_phase5_skip_build_reconciles_waits_and_replaces_only_job(
    monkeypatch, capsys
):
    monkeypatch.setattr(
        runner, "_reconcile_phase75_controller_sources", lambda execute: None
    )
    monkeypatch.setattr(
        runner,
        "_local_platform_image_id",
        lambda execute, image: (
            SERVICE_ID if image == runner.SERVICE_IMAGE else CONTROLLER_ID
        ),
    )
    cluster = FakeCluster()
    runner.run_small(skip_build=True, execute=cluster.execute)
    commands = [command for command, _capture in cluster.commands]

    assert not any(command[:2] == ("docker", "build") for command in commands)
    assert not any(
        command[:4] == ("kind", "load", "docker-image", "--name")
        for command in commands
    )
    assert not any("restart" in command for command in commands)
    assert cluster.reconciled_counts == [1]
    assert sum("status" in command for command in commands) == 4
    assert not any("scale" in command for command in commands)
    delete_job = next(
        index
        for index, command in enumerate(commands)
        if "delete" in command and "job" in command
    )
    apply_job = next(
        index
        for index, command in enumerate(commands)
        if "apply" in command and str(runner.DYNAMIC_CONTROLLER_JOB) in command
    )
    assert delete_job < apply_job
    assert capsys.readouterr().out == (
        "Selected Hybrid topology: 2 flows x 3 stages x 1 replica per stage\n"
        "Hybrid network impairment: schema=ibg-hybrid-netem-v1, "
        "enabled=false, interface=eth0, delay-ms=0, jitter-ms=0\n"
        "Hybrid image mode: --skip-build; reuse validated node-local images\n"
    )


def test_phase5_local_oci_archive_resolves_platform_config_identity(tmp_path):
    outer = "1" * 64
    platform_manifest = "2" * 64
    config = "3" * 64
    documents = {
        "index.json": {
            "manifests": [{"digest": f"sha256:{outer}"}],
        },
        f"blobs/sha256/{outer}": {
            "manifests": [
                {
                    "digest": f"sha256:{platform_manifest}",
                    "platform": {"os": "linux", "architecture": "amd64"},
                },
                {
                    "digest": f"sha256:{'4' * 64}",
                    "platform": {"os": "unknown", "architecture": "unknown"},
                },
            ]
        },
        f"blobs/sha256/{platform_manifest}": {
            "config": {"digest": f"sha256:{config}"}
        },
    }
    archive_path = tmp_path / "image.tar"
    with tarfile.open(archive_path, mode="w") as archive:
        for name, document in documents.items():
            payload = json.dumps(document).encode()
            member = tarfile.TarInfo(name)
            member.size = len(payload)
            archive.addfile(member, io.BytesIO(payload))
    with tarfile.open(archive_path, mode="r") as archive:
        assert runner._linux_amd64_config_id(archive) == config


def test_phase5_process_preservation_rejects_changes_and_allows_new_ordinals():
    before = (
        runner.ServingPodProcessSnapshot("hybrid-stage-1-0", "uid-1", (("p", 0),)),
    )
    runner._validate_process_preservation(
        before,
        before
        + (
            runner.ServingPodProcessSnapshot(
                "hybrid-stage-1-1", "uid-new", (("p", 0),)
            ),
        ),
    )
    with pytest.raises(RuntimeError, match="UID or restart count"):
        runner._validate_process_preservation(
            before,
            (
                runner.ServingPodProcessSnapshot(
                    "hybrid-stage-1-0", "uid-1", (("p", 1),)
                ),
            ),
        )


def test_phase5_scale_down_process_preservation_is_retained_subset_only():
    before = runner._serving_process_snapshot(
        serving_pods(3), replica_count=3
    )
    after = runner._serving_process_snapshot(
        serving_pods(2), replica_count=2
    )
    runner._validate_scale_down_process_preservation(
        before,
        after,
        existing_count=3,
        requested_count=2,
    )

    changed = list(after)
    retained = changed[0]
    changed[0] = runner.ServingPodProcessSnapshot(
        retained.pod_name,
        retained.pod_uid + "-changed",
        retained.container_restarts,
    )
    with pytest.raises(RuntimeError, match="retained serving Pod UID"):
        runner._validate_scale_down_process_preservation(
            before,
            tuple(changed),
            existing_count=3,
            requested_count=2,
        )

    with pytest.raises(RuntimeError, match="exact retained subset"):
        runner._validate_scale_down_process_preservation(
            before,
            after
            + (
                runner.ServingPodProcessSnapshot(
                    "hybrid-stage-1-2",
                    "uid-hybrid-stage-1-2",
                    (("private-processor", 0), ("public-forwarder", 0)),
                ),
            ),
            existing_count=3,
            requested_count=2,
        )


def test_phase5_normal_path_builds_offline_loads_and_restarts(monkeypatch, capsys):
    monkeypatch.setattr(runner, "_validate_offline_wheelhouses", lambda: None)
    monkeypatch.setattr(
        runner, "_reconcile_phase75_controller_sources", lambda execute: None
    )
    cluster = FakeCluster()
    runner.run_small(execute=cluster.execute)
    commands = [command for command, _capture in cluster.commands]
    builds = [command for command in commands if command[:2] == ("docker", "build")]

    assert len(builds) == 2
    assert all("--pull=false" in command for command in builds)
    assert all("--network=none" in command for command in builds)
    assert sum(
        command[:4] == ("kind", "load", "docker-image", "--name")
        for command in commands
    ) == 1
    assert sum("restart" in command for command in commands) == 1
    assert capsys.readouterr().out == (
        "Selected Hybrid topology: 2 flows x 3 stages x 1 replica per stage\n"
        "Hybrid network impairment: schema=ibg-hybrid-netem-v1, "
        "enabled=false, interface=eth0, delay-ms=0, jitter-ms=0\n"
        "Hybrid image mode: build offline from validated local wheelhouses\n"
    )


def test_phase5_mocked_multibatch_applies_same_target_and_waits_before_job(
    monkeypatch, capsys
):
    cluster = FakeCluster(replicas=1)
    monkeypatch.setattr(runner, "_validate_offline_wheelhouses", lambda: None)
    monkeypatch.setattr(
        runner,
        "_validate_static_profile_boundary",
        lambda count, **kwargs: runner.PHASE4_PROFILE_BOUNDARY,
    )

    runner.run_small(
        requested_replicas=5,
        rollout_batch_size=2,
        execute=cluster.execute,
    )
    commands = [command for command, _capture in cluster.commands]
    scale_commands = [command for command in commands if "scale" in command]

    assert [
        next(value for value in command if value.startswith("--replicas="))
        for command in scale_commands
    ] == ["--replicas=3", "--replicas=5"]
    assert all(
        all(resource in command for resource in runner.STATEFULSET_RESOURCES)
        for command in scale_commands
    )
    apply_job_index = next(
        index
        for index, command in enumerate(commands)
        if "apply" in command and str(runner.CONTROLLER_JOB) in command
    )
    last_ready_index = max(
        index for index, command in enumerate(commands) if "status" in command
    )
    assert last_ready_index < apply_job_index
    assert cluster.replicas == 5
    assert capsys.readouterr().out == (
        "Selected Hybrid topology: 2 flows x 3 stages x 1 replica per stage\n"
        "Hybrid network impairment: schema=ibg-hybrid-netem-v1, "
        "enabled=false, interface=eth0, delay-ms=0, jitter-ms=0\n"
        "Hybrid image mode: build offline from validated local wheelhouses\n"
    )


def test_phase5_rejects_skip_build_without_cluster_and_unapproved_scale():
    commands = []

    def no_cluster(command, capture_output):
        commands.append(command)
        if command == ("kind", "get", "clusters"):
            return ""
        return ""

    with pytest.raises(RuntimeError, match="requires the existing persistent"):
        runner.run_small(skip_build=True, execute=no_cluster)
    assert commands == [("kind", "get", "clusters")]

    commands = []
    with pytest.raises(RuntimeError, match="--flow is required"):
        runner.run_small(
            requested_replicas=3,
            execute=lambda command, capture: commands.append(command) or "",
        )
    assert commands == []


def test_phase5_cli_and_scope_keep_later_phases_absent():
    parsed = runner.parse_args(
        ["run-small", "--skip-build", "--replica", "1", "--rollout-batch-size", "2"]
    )
    assert parsed.skip_build
    assert parsed.requested_flows is None
    assert parsed.requested_stages is None
    assert parsed.requested_replicas == 1
    assert parsed.rollout_batch_size == 2
    assert parsed.policy is None
    assert parsed.mc_workers is None

    source = (ROOT / "scripts" / "run_hybrid_kernel_phase4.py").read_text()
    assert "kind-ibg-hybrid" in source
    assert "kind-ibg\"" not in source
    assert "ibg-control-plane" not in source
    assert "ibg-worker" not in source
    assert "controller_policy: str | None = None" in source
    assert "mc_workers: int | None = None" in source
    assert "64Mi" not in source


def test_phase5_dynamic_reconcile_overlay_preserves_resource_boundary():
    rendered = []

    def render_instead_of_apply(command, capture_output):
        assert command[:4] == (
            "kubectl",
            "--context",
            runner.KUBECTL_CONTEXT,
            "apply",
        )
        directory = command[command.index("-k") + 1]
        if "--dry-run=server" in command:
            return json.dumps(statefulsets(3))
        completed = subprocess.run(
            ["kubectl", "kustomize", directory],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        rendered.append(completed.stdout)
        return ""

    runner._apply_reconciled_boundary(render_instead_of_apply, replica_count=3)
    document = rendered[0]
    assert document.count("kind: StatefulSet") == 3
    assert document.count("replicas: 3") == 3
    assert document.count("replicas: 1") == 1
    assert "kind: Job" not in document
    assert "ibg-testbed" not in document
    assert "milp-testbed" not in document


def test_phase5_imports_are_silent_rng_neutral_and_file_safe(tmp_path):
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    code = (
        "import random,numpy as np; random.seed(145); np.random.seed(541); "
        "p=random.getstate(); n=np.random.get_state(); "
        "import IBG_Hybrid.kernel_rollout; "
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
