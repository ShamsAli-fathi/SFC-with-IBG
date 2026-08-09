#!/usr/bin/env python3
"""Run the small Hybrid Kernel gate in a persistent Hybrid-only kind cluster."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
from typing import Callable, Mapping, Sequence

from IBG_Hybrid.contracts import HybridConfiguration
from IBG_Hybrid.kernel_profile_expansion import (
    HybridKernelProfileExpansionError,
    validate_append_only_profile_expansion,
    validate_flow_only_profile_expansion,
)
from IBG_Hybrid.kernel_rollout import (
    HybridKernelRolloutError,
    discover_existing_replica_state,
    plan_bounded_rollout,
    validate_ready_ordinal_coverage,
)
from IBG_Hybrid.kernel_resource_evidence import (
    HybridKernelResourceEvidenceError,
    PROCESSOR_MEMORY_PROFILES,
    ProcessorMemoryProfile,
    detect_resource_profile,
    validate_processor_only_transition,
)


ROOT = Path(__file__).resolve().parents[1]
CLUSTER_NAME = "ibg-hybrid"
KUBECTL_CONTEXT = "kind-ibg-hybrid"
HYBRID_NAMESPACE = "ibg-hybrid-testbed"
KIND_NODE_IMAGE = (
    "kindest/node:v1.36.1@"
    "sha256:3489c7674813ba5d8b1a9977baea8a6e553784dab7b84759d1014dbd78f7ebd5"
)
KIND_CONFIG = (
    ROOT / "deploy" / "hybrid-kubernetes-phase4-small" / "kind-config.yaml"
)
OVERLAY = ROOT / "deploy" / "hybrid-kubernetes-phase4-small"
CONTROLLER_JOB = OVERLAY / "controller-job.yaml"
PHASE6_OVERLAY = ROOT / "deploy" / "hybrid-kubernetes-phase6-3x3x2"
PHASE6_CONTROLLER_JOB = PHASE6_OVERLAY / "controller-job.yaml"
PHASE7_OVERLAY = ROOT / "deploy" / "hybrid-kubernetes-phase7-3x3x2"
PHASE7_CANDIDATE_OVERLAY = (
    ROOT / "deploy" / "hybrid-kubernetes-phase7-3x3x2-candidate"
)
PHASE7_CONTROLLER_JOB = PHASE7_OVERLAY / "controller-job.yaml"
PHASE75_OVERLAY = ROOT / "deploy" / "hybrid-kubernetes-phase7.5-3x3x2"
PHASE75_CONTROLLER_JOB = PHASE75_OVERLAY / "controller-job.yaml"
PHASE75_CONTROLLER_JOB_NAME = "ibg-hybrid-controller-phase75"
PHASE8_GATE1_OVERLAY = (
    ROOT / "deploy" / "hybrid-kubernetes-phase8-gate1-4x3x2"
)
PHASE8_GATE1_CONTROLLER_JOB = PHASE8_GATE1_OVERLAY / "controller-job.yaml"
PHASE8_GATE1_CONTROLLER_JOB_NAME = "ibg-hybrid-controller-phase8-gate1"
PHASE75_CONTROLLER_SOURCE_CONFIGMAP = (
    "ibg-hybrid-controller-phase75-source"
)
PHASE75_CONTROLLER_SOURCES = (
    ROOT / "IBG_Hybrid" / "kernel_controller.py",
    ROOT / "IBG_Hybrid" / "kernel_phase4_validation.py",
    ROOT / "IBG_Hybrid" / "kernel_controller_cli.py",
)
MAX_HYBRID_KERNEL_MC_WORKERS = 2
SERVICE_IMAGE = "ibg-hybrid-testbed:kernel-service-v1"
CONTROLLER_IMAGE = "ibg-hybrid-testbed:kernel-controller-v1"
NORMALIZED_SERVICE_IMAGE = (
    "docker.io/library/ibg-hybrid-testbed:kernel-service-v1"
)
NORMALIZED_CONTROLLER_IMAGE = (
    "docker.io/library/ibg-hybrid-testbed:kernel-controller-v1"
)
PYTHON_BASE_IMAGE = "mcr.microsoft.com/azurelinux/base/python:3.12"
EXPECTED_NODE_NAMES = frozenset({"ibg-hybrid-control-plane"})
SYSTEM_POD_NAMESPACES = frozenset({"kube-system", "local-path-storage"})
FORBIDDEN_NAMESPACES = frozenset({"ibg-testbed", "milp-testbed"})
STATEFULSET_RESOURCES = tuple(
    f"statefulset/hybrid-stage-{stage}" for stage in range(1, 4)
)
FLOW_GENERATOR_RESOURCE = "deployment/ibg-hybrid-flow-generator"
RUNTIME_PROFILES = OVERLAY / "runtime-profiles.json"
CONTROLLER_INPUTS = OVERLAY / "controller-inputs.json"
SERVICE_DOCKERFILE = (
    ROOT / "deploy" / "hybrid-kubernetes" / "Dockerfile.service"
)
CONTROLLER_DOCKERFILE = (
    ROOT / "deploy" / "hybrid-kubernetes" / "Dockerfile.controller"
)

Command = tuple[str, ...]
Executor = Callable[[Command, bool], str]
RunHook = Callable[[], None]


@dataclass(frozen=True, order=True)
class ServingPodProcessSnapshot:
    pod_name: str
    pod_uid: str
    container_restarts: tuple[tuple[str, int], ...]


@dataclass(frozen=True, order=True)
class StatefulSetPodTemplateSnapshot:
    statefulset_name: str
    canonical_template: str


@dataclass(frozen=True)
class HybridProfileBoundary:
    configuration: HybridConfiguration
    source_identity: str
    overlay: Path
    runtime_profiles: Path
    controller_inputs: Path
    controller_job: Path
    controller_job_name: str
    replaced_job_names: tuple[str, ...]


PHASE4_PROFILE_BOUNDARY = HybridProfileBoundary(
    configuration=HybridConfiguration(2, 3, 1, 2),
    source_identity="ibg-hybrid-infrastructure-phase4-small-live-v1",
    overlay=OVERLAY,
    runtime_profiles=RUNTIME_PROFILES,
    controller_inputs=CONTROLLER_INPUTS,
    controller_job=CONTROLLER_JOB,
    controller_job_name="ibg-hybrid-controller-phase4-small",
    replaced_job_names=("ibg-hybrid-controller-phase4-small",),
)
PHASE6_PROFILE_BOUNDARY = HybridProfileBoundary(
    configuration=HybridConfiguration(3, 3, 2, 2),
    source_identity="ibg-hybrid-infrastructure-phase6-3x3x2-v1",
    overlay=PHASE6_OVERLAY,
    runtime_profiles=PHASE6_OVERLAY / "runtime-profiles.json",
    controller_inputs=PHASE6_OVERLAY / "controller-inputs.json",
    controller_job=PHASE6_CONTROLLER_JOB,
    controller_job_name="ibg-hybrid-controller-phase6",
    replaced_job_names=(
        "ibg-hybrid-controller-phase4-small",
        "ibg-hybrid-controller-phase6",
    ),
)
PHASE8_GATE1_PROFILE_BOUNDARY = HybridProfileBoundary(
    configuration=HybridConfiguration(4, 3, 2, 2),
    source_identity="ibg-hybrid-infrastructure-phase8-gate1-4x3x2-v1",
    overlay=PHASE8_GATE1_OVERLAY,
    runtime_profiles=PHASE8_GATE1_OVERLAY / "runtime-profiles.json",
    controller_inputs=PHASE8_GATE1_OVERLAY / "controller-inputs.json",
    controller_job=PHASE8_GATE1_CONTROLLER_JOB,
    controller_job_name=PHASE8_GATE1_CONTROLLER_JOB_NAME,
    replaced_job_names=(
        *PHASE6_PROFILE_BOUNDARY.replaced_job_names,
        "ibg-hybrid-controller-phase7",
        PHASE75_CONTROLLER_JOB_NAME,
        PHASE8_GATE1_CONTROLLER_JOB_NAME,
    ),
)


def _execute(command: Command, capture_output: bool = False) -> str:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=capture_output,
    )
    return completed.stdout if capture_output else ""


def _kind_clusters(execute: Executor) -> frozenset[str]:
    output = execute(("kind", "get", "clusters"), True)
    return frozenset(line.strip() for line in output.splitlines() if line.strip())


def _kubectl(*arguments: str) -> Command:
    return ("kubectl", "--context", KUBECTL_CONTEXT, *arguments)


def _json_output(execute: Executor, command: Command) -> Mapping[str, object]:
    value = json.loads(execute(command, True))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected an object from: {' '.join(command)}")
    return value


def _item_names(document: Mapping[str, object]) -> frozenset[str]:
    items = document.get("items")
    if not isinstance(items, list):
        raise RuntimeError("Kubernetes inventory has no item list")
    names = set()
    for item in items:
        if not isinstance(item, dict):
            raise RuntimeError("Kubernetes inventory item is not an object")
        metadata = item.get("metadata")
        if not isinstance(metadata, dict) or not isinstance(
            metadata.get("name"), str
        ):
            raise RuntimeError("Kubernetes inventory item has no name")
        names.add(metadata["name"])
    return frozenset(names)


def validate_cluster_inventory(
    *,
    nodes: Mapping[str, object],
    namespaces: Mapping[str, object],
    pods: Mapping[str, object],
) -> None:
    node_names = _item_names(nodes)
    if node_names != EXPECTED_NODE_NAMES:
        raise RuntimeError(
            "refusing non-dedicated cluster nodes: "
            f"expected {sorted(EXPECTED_NODE_NAMES)}, got {sorted(node_names)}"
        )

    namespace_names = _item_names(namespaces)
    forbidden = namespace_names & FORBIDDEN_NAMESPACES
    if forbidden:
        raise RuntimeError(
            "refusing cluster with foreign baseline namespaces: "
            + ", ".join(sorted(forbidden))
        )

    items = pods.get("items")
    if not isinstance(items, list):
        raise RuntimeError("Kubernetes Pod inventory has no item list")
    foreign_pods = []
    for item in items:
        if not isinstance(item, dict):
            raise RuntimeError("Kubernetes Pod inventory item is not an object")
        metadata = item.get("metadata")
        if not isinstance(metadata, dict):
            raise RuntimeError("Kubernetes Pod inventory item has no metadata")
        namespace = metadata.get("namespace")
        name = metadata.get("name")
        if namespace not in SYSTEM_POD_NAMESPACES | {HYBRID_NAMESPACE}:
            foreign_pods.append(f"{namespace}/{name}")
        elif namespace == HYBRID_NAMESPACE:
            labels = metadata.get("labels")
            if not isinstance(name, str) or not isinstance(labels, dict):
                foreign_pods.append(f"{namespace}/{name}")
                continue
            part_of = labels.get("app.kubernetes.io/part-of")
            if name.startswith("hybrid-stage-"):
                owned = (
                    part_of == "ibg-hybrid-testbed"
                    and labels.get("app.kubernetes.io/name")
                    == "ibg-hybrid-replica"
                    and labels.get("app.kubernetes.io/component")
                    == "replica-stage"
                    and isinstance(labels.get("ibg-hybrid.stage"), str)
                )
            elif name.startswith("ibg-hybrid-flow-generator-"):
                owned = (
                    part_of == "ibg-hybrid-testbed"
                    and labels.get("app.kubernetes.io/name")
                    == "ibg-hybrid-flow-generator"
                )
            elif name.startswith(
                (
                    "ibg-hybrid-controller-phase4-small-",
                    "ibg-hybrid-controller-phase6-",
                    "ibg-hybrid-controller-phase7-",
                    "ibg-hybrid-controller-phase75-",
                    "ibg-hybrid-controller-phase8-gate1-",
                )
            ):
                owned = (
                    part_of == "ibg-hybrid-testbed"
                    and labels.get("app.kubernetes.io/name")
                    == "ibg-hybrid-controller"
                )
            else:
                owned = False
            if not owned:
                foreign_pods.append(f"{namespace}/{name}")
    if foreign_pods:
        raise RuntimeError(
            "refusing cluster with foreign workload Pods: "
            + ", ".join(sorted(foreign_pods))
        )


def preflight(*, execute: Executor = _execute) -> None:
    validate_cluster_inventory(
        nodes=_json_output(execute, _kubectl("get", "nodes", "-o", "json")),
        namespaces=_json_output(
            execute, _kubectl("get", "namespaces", "-o", "json")
        ),
        pods=_json_output(execute, _kubectl("get", "pods", "-A", "-o", "json")),
    )


def _require_local_image(execute: Executor, image: str) -> None:
    execute(("docker", "image", "inspect", image), True)


def _build_images_offline(execute: Executor) -> None:
    """Build both images without pulls or build-step network access."""

    _require_local_image(execute, PYTHON_BASE_IMAGE)
    for dockerfile, image in (
        (SERVICE_DOCKERFILE, SERVICE_IMAGE),
        (CONTROLLER_DOCKERFILE, CONTROLLER_IMAGE),
    ):
        if not dockerfile.is_file():
            raise RuntimeError(f"missing Hybrid Dockerfile: {dockerfile}")
        execute(
            (
                "docker",
                "build",
                "--pull=false",
                "--network=none",
                "--file",
                str(dockerfile),
                "--tag",
                image,
                ".",
            ),
            False,
        )


def _image_id(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        raise RuntimeError(f"{field} has no full sha256 platform image ID")
    digest = value.removeprefix("sha256:")
    if len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise RuntimeError(f"{field} has an invalid sha256 platform image ID")
    return digest


def _archive_json(
    archive: tarfile.TarFile, member_name: str
) -> Mapping[str, object]:
    member = archive.extractfile(member_name)
    if member is None:
        raise RuntimeError(f"local image archive lacks {member_name}")
    payload = json.loads(member.read())
    if not isinstance(payload, dict):
        raise RuntimeError(f"local image archive member is invalid: {member_name}")
    return payload


def _descriptor_document(
    archive: tarfile.TarFile, descriptor: Mapping[str, object]
) -> Mapping[str, object]:
    digest = _image_id(descriptor.get("digest"), "OCI descriptor")
    return _archive_json(archive, f"blobs/sha256/{digest}")


def _linux_amd64_config_id(archive: tarfile.TarFile) -> str:
    index = _archive_json(archive, "index.json")
    manifests = index.get("manifests")
    if not isinstance(manifests, list) or len(manifests) != 1:
        raise RuntimeError("local image archive has ambiguous top-level manifests")
    descriptor = manifests[0]
    if not isinstance(descriptor, dict):
        raise RuntimeError("local image archive has an invalid top-level descriptor")
    document = _descriptor_document(archive, descriptor)
    while "config" not in document:
        candidates = document.get("manifests")
        if not isinstance(candidates, list):
            raise RuntimeError("local image archive has no platform manifest")
        selected = []
        for candidate in candidates:
            if not isinstance(candidate, dict):
                raise RuntimeError("local image archive has an invalid manifest")
            platform = candidate.get("platform")
            if isinstance(platform, dict) and (
                platform.get("os"), platform.get("architecture")
            ) == ("linux", "amd64"):
                selected.append(candidate)
        if len(selected) != 1:
            raise RuntimeError(
                "local image archive must contain exactly one linux/amd64 manifest"
            )
        document = _descriptor_document(archive, selected[0])
    config = document.get("config")
    if not isinstance(config, dict):
        raise RuntimeError("local linux/amd64 manifest has no config descriptor")
    return _image_id(config.get("digest"), "local linux/amd64 image config")


def _local_platform_image_id(execute: Executor, image: str) -> str:
    with tempfile.TemporaryDirectory(prefix="ibg-hybrid-image-inspect-") as directory:
        archive_path = Path(directory) / "image.tar"
        execute(
            (
                "docker",
                "image",
                "save",
                "--output",
                str(archive_path),
                image,
            ),
            False,
        )
        with tarfile.open(archive_path, mode="r") as archive:
            return _linux_amd64_config_id(archive)


def validate_node_images(execute: Executor) -> None:
    """Match normalized node tags to the locally selected platform images."""

    expected = {
        NORMALIZED_SERVICE_IMAGE: _local_platform_image_id(execute, SERVICE_IMAGE),
        NORMALIZED_CONTROLLER_IMAGE: _local_platform_image_id(
            execute, CONTROLLER_IMAGE
        ),
    }
    node_names = frozenset(
        line.strip()
        for line in execute(
            ("kind", "get", "nodes", "--name", CLUSTER_NAME), True
        ).splitlines()
        if line.strip()
    )
    if node_names != EXPECTED_NODE_NAMES:
        raise RuntimeError(
            "refusing node-image validation outside the dedicated Hybrid node: "
            f"expected={sorted(EXPECTED_NODE_NAMES)}, got={sorted(node_names)}"
        )
    for node_name in sorted(node_names):
        payload = json.loads(
            execute(
                (
                    "docker",
                    "exec",
                    node_name,
                    "crictl",
                    "images",
                    "-o",
                    "json",
                ),
                True,
            )
        )
        if not isinstance(payload, dict) or not isinstance(
            payload.get("images"), list
        ):
            raise RuntimeError(f"node image inventory is invalid for {node_name}")
        tagged_ids: dict[str, set[str]] = {tag: set() for tag in expected}
        for raw_item in payload["images"]:
            if not isinstance(raw_item, dict):
                raise RuntimeError(f"node image entry is invalid for {node_name}")
            tags = raw_item.get("repoTags")
            if not isinstance(tags, list):
                continue
            matching = set(tags) & set(expected)
            if not matching:
                continue
            runtime_id = _image_id(
                raw_item.get("id"), f"node image on {node_name}"
            )
            for tag in matching:
                tagged_ids[tag].add(runtime_id)
        for tag, expected_id in expected.items():
            if tagged_ids[tag] != {expected_id}:
                raise RuntimeError(
                    "Hybrid node image is absent or mismatched: "
                    f"node={node_name}, tag={tag}, expected={expected_id}, "
                    f"found={sorted(tagged_ids[tag])}"
                )


def _pod_ready(item: Mapping[str, object]) -> bool:
    status = item.get("status")
    if not isinstance(status, dict) or status.get("phase") != "Running":
        return False
    conditions = status.get("conditions")
    return isinstance(conditions, list) and any(
        isinstance(condition, dict)
        and condition.get("type") == "Ready"
        and condition.get("status") == "True"
        for condition in conditions
    )


def _validate_serving_pods(
    document: Mapping[str, object], *, replica_count: int = 1
) -> None:
    validate_ready_ordinal_coverage(document, replica_count=replica_count)
    items = document.get("items")
    if not isinstance(items, list):
        raise RuntimeError("Hybrid serving Pod inventory has no item list")
    flow_generators = [
        item
        for item in items
        if isinstance(item, dict)
        and isinstance(item.get("metadata"), dict)
        and str(item["metadata"].get("name", "")).startswith(
            "ibg-hybrid-flow-generator-"
        )
    ]
    if len(flow_generators) != 1:
        raise RuntimeError(
            "refusing incomplete or unexpected Hybrid serving Pod inventory"
        )
    flow_generator = flow_generators[0]
    metadata = flow_generator["metadata"]
    labels = metadata.get("labels")
    if (
        metadata.get("namespace") != HYBRID_NAMESPACE
        or not isinstance(labels, dict)
        or labels.get("app.kubernetes.io/name")
        != "ibg-hybrid-flow-generator"
        or labels.get("app.kubernetes.io/part-of") != "ibg-hybrid-testbed"
        or not _pod_ready(flow_generator)
    ):
        raise RuntimeError("Hybrid serving Pods are not all Running and Ready")


def _serving_process_snapshot(
    document: Mapping[str, object], *, replica_count: int
) -> tuple[ServingPodProcessSnapshot, ...]:
    _validate_serving_pods(document, replica_count=replica_count)
    items = document.get("items")
    if not isinstance(items, list):
        raise RuntimeError("Hybrid serving Pod inventory has no item list")
    snapshots = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("metadata"), dict):
            continue
        metadata = item["metadata"]
        name = metadata.get("name")
        if not isinstance(name, str) or not (
            name.startswith("hybrid-stage-")
            or name.startswith("ibg-hybrid-flow-generator-")
        ):
            continue
        uid = metadata.get("uid")
        status = item.get("status")
        if not isinstance(uid, str) or not uid or not isinstance(status, dict):
            raise RuntimeError(f"Hybrid serving Pod {name} has no stable identity")
        container_statuses = status.get("containerStatuses")
        if not isinstance(container_statuses, list) or not container_statuses:
            raise RuntimeError(f"Hybrid serving Pod {name} has no restart snapshot")
        restarts = []
        for container in container_statuses:
            if not isinstance(container, dict):
                raise RuntimeError(f"Hybrid serving Pod {name} has invalid status")
            container_name = container.get("name")
            restart_count = container.get("restartCount")
            if (
                not isinstance(container_name, str)
                or not container_name
                or isinstance(restart_count, bool)
                or not isinstance(restart_count, int)
                or restart_count < 0
            ):
                raise RuntimeError(f"Hybrid serving Pod {name} has invalid restarts")
            restarts.append((container_name, restart_count))
        snapshots.append(
            ServingPodProcessSnapshot(name, uid, tuple(sorted(restarts)))
        )
    return tuple(sorted(snapshots))


def _validate_process_preservation(
    before: tuple[ServingPodProcessSnapshot, ...],
    after: tuple[ServingPodProcessSnapshot, ...],
) -> None:
    after_by_name = {item.pod_name: item for item in after}
    changed = [
        item.pod_name
        for item in before
        if after_by_name.get(item.pod_name) != item
    ]
    if changed:
        raise RuntimeError(
            "--skip-build changed an existing serving Pod UID or restart count: "
            + ", ".join(changed)
        )


def _validate_deliberate_processor_rollout(
    before: tuple[ServingPodProcessSnapshot, ...],
    after: tuple[ServingPodProcessSnapshot, ...],
) -> None:
    before_by_name = {item.pod_name: item for item in before}
    after_by_name = {item.pod_name: item for item in after}
    if set(before_by_name) != set(after_by_name):
        raise RuntimeError("processor resource rollout changed serving Pod names")
    for name in sorted(before_by_name):
        old = before_by_name[name]
        new = after_by_name[name]
        if name.startswith("ibg-hybrid-flow-generator-"):
            if new != old:
                raise RuntimeError(
                    "processor resource rollout changed the flow generator"
                )
            continue
        if new.pod_uid == old.pod_uid:
            raise RuntimeError(
                f"processor resource rollout did not replace {name}"
            )
        if any(restarts for _container, restarts in new.container_restarts):
            raise RuntimeError(
                f"processor resource rollout produced restarts in {name}"
            )


def _pod_inventory(execute: Executor) -> Mapping[str, object]:
    return _json_output(
        execute,
        _kubectl("get", "pods", "-n", HYBRID_NAMESPACE, "-o", "json"),
    )


def _statefulset_inventory(execute: Executor) -> Mapping[str, object]:
    return _json_output(
        execute,
        _kubectl(
            "get", "statefulsets", "-n", HYBRID_NAMESPACE, "-o", "json"
        ),
    )


APPROVED_PROFILE_BOUNDARIES = {
    (
        boundary.configuration.num_flows,
        boundary.configuration.num_stages,
        boundary.configuration.num_replicas,
    ): boundary
    for boundary in (
        PHASE4_PROFILE_BOUNDARY,
        PHASE6_PROFILE_BOUNDARY,
        PHASE8_GATE1_PROFILE_BOUNDARY,
    )
}


def _profile_boundary(
    requested_replicas: int,
    *,
    requested_flows: int | None = None,
    requested_stages: int | None = None,
) -> HybridProfileBoundary:
    for value, field in (
        (requested_replicas, "replica count"),
        (requested_flows, "flow count"),
        (requested_stages, "stage count"),
    ):
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value < 1
        ):
            raise RuntimeError(f"{field} must be a positive integer")
    if requested_stages is not None and requested_stages != 3:
        raise RuntimeError(
            "the frozen Hybrid L=2 model requires exactly three stages"
        )
    candidates = [
        boundary
        for (flows, stages, replicas), boundary in APPROVED_PROFILE_BOUNDARIES.items()
        if replicas == requested_replicas
        and (requested_flows is None or flows == requested_flows)
        and (requested_stages is None or stages == requested_stages)
    ]
    if (
        requested_flows is None
        and requested_stages is None
        and requested_replicas == 2
    ):
        return PHASE6_PROFILE_BOUNDARY
    if len(candidates) == 1:
        return candidates[0]
    requested = (
        "inferred" if requested_flows is None else str(requested_flows),
        "inferred" if requested_stages is None else str(requested_stages),
        str(requested_replicas),
    )
    raise RuntimeError(
        "requested Hybrid topology has no approved complete profile: "
        f"flow={requested[0]}, stage={requested[1]}, replica={requested[2]}; "
        "approved tuples are 2x3x1, 3x3x2, and Phase 8 Gate 1 4x3x2; "
        "all additional scale is deferred to Infrastructure Phase 8"
    )


def _load_json_mapping(path: Path) -> Mapping[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Hybrid profile document is not an object: {path}")
    return payload


def _validate_static_profile_boundary(
    requested_replicas: int,
    *,
    requested_flows: int | None = None,
    requested_stages: int | None = None,
) -> HybridProfileBoundary:
    boundary = _profile_boundary(
        requested_replicas,
        requested_flows=requested_flows,
        requested_stages=requested_stages,
    )
    runtime = _load_json_mapping(boundary.runtime_profiles)
    controller = _load_json_mapping(boundary.controller_inputs)
    if boundary == PHASE8_GATE1_PROFILE_BOUNDARY:
        validate_flow_only_profile_expansion(
            deployed_runtime=_load_json_mapping(
                PHASE6_PROFILE_BOUNDARY.runtime_profiles
            ),
            deployed_controller=_load_json_mapping(
                PHASE6_PROFILE_BOUNDARY.controller_inputs
            ),
            proposed_runtime=runtime,
            proposed_controller=controller,
            deployed_configuration=PHASE6_PROFILE_BOUNDARY.configuration,
            target_configuration=boundary.configuration,
            deployed_source_identity=PHASE6_PROFILE_BOUNDARY.source_identity,
            target_source_identity=boundary.source_identity,
        )
    else:
        validate_append_only_profile_expansion(
            deployed_runtime=runtime,
            deployed_controller=controller,
            proposed_runtime=runtime,
            proposed_controller=controller,
            existing_replica_count=requested_replicas,
            expected_configuration=boundary.configuration,
            expected_source_identity=boundary.source_identity,
        )
    return boundary


def _deployed_profile_documents(
    execute: Executor,
) -> tuple[Mapping[str, object], Mapping[str, object]]:
    inventory = _json_output(
        execute,
        _kubectl(
            "get",
            "configmap",
            "ibg-hybrid-runtime-profiles",
            "ibg-hybrid-planning-links",
            "-n",
            HYBRID_NAMESPACE,
            "-o",
            "json",
        ),
    )
    items = inventory.get("items")
    if not isinstance(items, list) or len(items) != 2:
        raise RuntimeError("Hybrid profile ConfigMap inventory is incomplete")
    documents: dict[str, Mapping[str, object]] = {}
    expected_keys = {
        "ibg-hybrid-runtime-profiles": "runtime-profiles.json",
        "ibg-hybrid-planning-links": "controller-inputs.json",
    }
    for item in items:
        if not isinstance(item, dict):
            raise RuntimeError("Hybrid profile ConfigMap item is invalid")
        metadata = item.get("metadata")
        data = item.get("data")
        if not isinstance(metadata, dict) or not isinstance(data, dict):
            raise RuntimeError("Hybrid profile ConfigMap has no metadata/data")
        name = metadata.get("name")
        if (
            not isinstance(name, str)
            or metadata.get("namespace") != HYBRID_NAMESPACE
            or name not in expected_keys
            or set(data) != {expected_keys[name]}
        ):
            raise RuntimeError("Hybrid profile ConfigMap ownership/data is invalid")
        value = json.loads(data[expected_keys[name]])
        if not isinstance(value, dict):
            raise RuntimeError(f"Hybrid ConfigMap {name} document is invalid")
        documents[name] = value
    if set(documents) != set(expected_keys):
        raise RuntimeError("Hybrid profile ConfigMap names are incomplete")
    return (
        documents["ibg-hybrid-runtime-profiles"],
        documents["ibg-hybrid-planning-links"],
    )


def _validate_live_profile_expansion(
    execute: Executor,
    *,
    existing_replica_count: int,
    boundary: HybridProfileBoundary,
) -> None:
    deployed_runtime, deployed_controller = _deployed_profile_documents(execute)
    if boundary == PHASE8_GATE1_PROFILE_BOUNDARY:
        if existing_replica_count != boundary.configuration.num_replicas:
            raise RuntimeError(
                "Phase 8 Gate 1 requires the existing exact two-replica topology"
            )
        proposed_runtime = _load_json_mapping(boundary.runtime_profiles)
        proposed_controller = _load_json_mapping(boundary.controller_inputs)
        if (
            deployed_runtime == proposed_runtime
            and deployed_controller == proposed_controller
        ):
            validate_append_only_profile_expansion(
                deployed_runtime=deployed_runtime,
                deployed_controller=deployed_controller,
                proposed_runtime=proposed_runtime,
                proposed_controller=proposed_controller,
                existing_replica_count=existing_replica_count,
                expected_configuration=boundary.configuration,
                expected_source_identity=boundary.source_identity,
            )
        else:
            validate_flow_only_profile_expansion(
                deployed_runtime=deployed_runtime,
                deployed_controller=deployed_controller,
                proposed_runtime=proposed_runtime,
                proposed_controller=proposed_controller,
                deployed_configuration=PHASE6_PROFILE_BOUNDARY.configuration,
                target_configuration=boundary.configuration,
                deployed_source_identity=PHASE6_PROFILE_BOUNDARY.source_identity,
                target_source_identity=boundary.source_identity,
            )
    else:
        validate_append_only_profile_expansion(
            deployed_runtime=deployed_runtime,
            deployed_controller=deployed_controller,
            proposed_runtime=_load_json_mapping(boundary.runtime_profiles),
            proposed_controller=_load_json_mapping(boundary.controller_inputs),
            existing_replica_count=existing_replica_count,
            expected_configuration=boundary.configuration,
            expected_source_identity=boundary.source_identity,
        )


def _validate_reconciled_profiles(
    execute: Executor, *, boundary: HybridProfileBoundary
) -> None:
    runtime, controller = _deployed_profile_documents(execute)
    if runtime != _load_json_mapping(boundary.runtime_profiles):
        raise RuntimeError("reconciled runtime profile does not match Phase target")
    if controller != _load_json_mapping(boundary.controller_inputs):
        raise RuntimeError("reconciled controller input does not match Phase target")


def _statefulset_template_snapshot(
    document: Mapping[str, object],
) -> tuple[StatefulSetPodTemplateSnapshot, ...]:
    items = document.get("items")
    if not isinstance(items, list):
        raise RuntimeError("StatefulSet template inventory has no item list")
    statefulsets = {
        "items": [
            item
            for item in items
            if isinstance(item, dict) and item.get("kind") == "StatefulSet"
        ]
    }
    discover_existing_replica_state(statefulsets)
    snapshots = []
    for item in statefulsets["items"]:
        metadata = item.get("metadata")
        spec = item.get("spec")
        if not isinstance(metadata, dict) or not isinstance(spec, dict):
            raise RuntimeError("StatefulSet template item is invalid")
        name = metadata.get("name")
        template = spec.get("template")
        if not isinstance(name, str) or not isinstance(template, dict):
            raise RuntimeError("StatefulSet has no stable Pod template")
        snapshots.append(
            StatefulSetPodTemplateSnapshot(
                name,
                json.dumps(template, sort_keys=True, separators=(",", ":")),
            )
        )
    return tuple(sorted(snapshots))


def _apply_reconciled_boundary(
    execute: Executor,
    *,
    replica_count: int,
    boundary: HybridProfileBoundary = PHASE4_PROFILE_BOUNDARY,
    deployment_overlay: Path | None = None,
    expected_templates: tuple[StatefulSetPodTemplateSnapshot, ...] | None = None,
    existing_statefulsets: Mapping[str, object] | None = None,
    processor_memory_profile: ProcessorMemoryProfile | None = None,
) -> None:
    deploy_root = ROOT / "deploy"
    with tempfile.TemporaryDirectory(
        prefix=".ibg-hybrid-phase5-", dir=deploy_root
    ) as directory:
        kustomization = Path(directory) / "kustomization.yaml"
        replica_lines = "\n".join(
            f"  - name: hybrid-stage-{stage}\n    count: {replica_count}"
            for stage in range(1, 4)
        )
        kustomization.write_text(
            "apiVersion: kustomize.config.k8s.io/v1beta1\n"
            "kind: Kustomization\n"
            "resources:\n"
            f"  - ../{(deployment_overlay or boundary.overlay).relative_to(deploy_root)}\n"
            "replicas:\n"
            f"{replica_lines}\n",
            encoding="utf-8",
        )
        dry_run = _json_output(
            execute,
            _kubectl(
                "apply",
                "--dry-run=server",
                "-k",
                str(Path(directory)),
                "-o",
                "json",
            ),
        )
        if (
            processor_memory_profile is not None
            and existing_statefulsets is not None
        ):
            validate_processor_only_transition(
                existing_statefulsets,
                dry_run,
                processor_memory_profile,
            )
        elif (
            expected_templates is not None
            and _statefulset_template_snapshot(dry_run) != expected_templates
        ):
            raise RuntimeError(
                "refusing ConfigMap reconciliation that changes a StatefulSet "
                "Pod template"
            )
        execute(_kubectl("apply", "-k", str(Path(directory))), False)


def _wait_for_target(execute: Executor, *, replica_count: int) -> None:
    for resource in (*STATEFULSET_RESOURCES, FLOW_GENERATOR_RESOURCE):
        execute(
            _kubectl(
                "rollout",
                "status",
                "-n",
                HYBRID_NAMESPACE,
                resource,
                "--timeout=180s",
            ),
            False,
        )
    discovered = discover_existing_replica_state(_statefulset_inventory(execute))
    if discovered.replica_count != replica_count:
        raise RuntimeError(
            "Hybrid StatefulSets did not retain the requested rollout target"
        )
    _validate_serving_pods(_pod_inventory(execute), replica_count=replica_count)


def _phase75_controller_arguments(
    policy: str | None,
    mc_workers: int | None,
) -> tuple[str, ...] | None:
    """Validate the manual-only controller selection before cluster contact."""

    if policy is None:
        if mc_workers is not None:
            raise RuntimeError("--mc-workers requires explicit --policy mc")
        return None
    if policy not in {"lookahead", "mc"}:
        raise RuntimeError("controller policy must be lookahead or mc")
    if policy == "lookahead":
        if mc_workers is not None:
            raise RuntimeError("--mc-workers is valid only with --policy mc")
        return ("--policy", "lookahead")
    if (
        isinstance(mc_workers, bool)
        or not isinstance(mc_workers, int)
        or mc_workers < 1
        or mc_workers > MAX_HYBRID_KERNEL_MC_WORKERS
    ):
        raise RuntimeError(
            "--policy mc requires --mc-workers between 1 and "
            f"{MAX_HYBRID_KERNEL_MC_WORKERS}"
        )
    return ("--policy", "mc", "--mc-workers", str(mc_workers))


def _reconcile_phase75_controller_sources(execute: Executor) -> None:
    for source in PHASE75_CONTROLLER_SOURCES:
        if not source.is_file():
            raise RuntimeError(f"missing Phase 7.5 controller source: {source}")
    command = [
        *_kubectl(
            "create",
            "configmap",
            PHASE75_CONTROLLER_SOURCE_CONFIGMAP,
            "-n",
            HYBRID_NAMESPACE,
        ),
    ]
    command.extend(
        f"--from-file={source.name}={source}" for source in PHASE75_CONTROLLER_SOURCES
    )
    command.extend(("--dry-run=client", "-o", "json"))
    document = _json_output(execute, tuple(command))
    metadata = document.get("metadata")
    data = document.get("data")
    if (
        document.get("kind") != "ConfigMap"
        or not isinstance(metadata, dict)
        or metadata.get("name") != PHASE75_CONTROLLER_SOURCE_CONFIGMAP
        or metadata.get("namespace") != HYBRID_NAMESPACE
        or not isinstance(data, dict)
        or set(data) != {source.name for source in PHASE75_CONTROLLER_SOURCES}
    ):
        raise RuntimeError("Phase 7.5 controller source ConfigMap is incomplete")
    with tempfile.TemporaryDirectory(
        prefix=".ibg-hybrid-phase75-source-", dir=ROOT / "deploy"
    ) as directory:
        manifest = Path(directory) / "controller-source.json"
        manifest.write_text(
            json.dumps(document, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        execute(_kubectl("apply", "-f", str(manifest)), False)


def _apply_controller_job(
    execute: Executor,
    *,
    controller_job: Path,
    controller_job_name: str,
    arguments: tuple[str, ...] | None,
) -> None:
    if arguments is None:
        execute(_kubectl("apply", "-f", str(controller_job)), False)
        return
    document = _json_output(
        execute,
        _kubectl(
            "create",
            "--dry-run=client",
            "--validate=false",
            "-f",
            str(controller_job),
            "-o",
            "json",
        ),
    )
    metadata = document.get("metadata")
    spec = document.get("spec")
    if (
        document.get("kind") != "Job"
        or not isinstance(metadata, dict)
        or metadata.get("name") != controller_job_name
        or metadata.get("namespace") != HYBRID_NAMESPACE
        or not isinstance(spec, dict)
    ):
        raise RuntimeError("Phase 7.5 controller Job template is invalid")
    template = spec.get("template")
    pod_spec = template.get("spec") if isinstance(template, dict) else None
    containers = pod_spec.get("containers") if isinstance(pod_spec, dict) else None
    if (
        not isinstance(containers, list)
        or len(containers) != 1
        or not isinstance(containers[0], dict)
        or containers[0].get("name") != "controller"
    ):
        raise RuntimeError("Phase 7.5 Job must contain one controller container")
    containers[0]["args"] = list(arguments)
    with tempfile.TemporaryDirectory(
        prefix=".ibg-hybrid-phase75-job-", dir=ROOT / "deploy"
    ) as directory:
        manifest = Path(directory) / "controller-job.json"
        manifest.write_text(
            json.dumps(document, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        execute(_kubectl("apply", "-f", str(manifest)), False)


def run_small(
    *,
    skip_build: bool = False,
    requested_flows: int | None = None,
    requested_stages: int | None = None,
    requested_replicas: int = 1,
    rollout_batch_size: int = 1,
    processor_memory_profile: str | None = None,
    controller_policy: str | None = None,
    mc_workers: int | None = None,
    before_controller_job: RunHook | None = None,
    controller_job_started: RunHook | None = None,
    after_controller_job: RunHook | None = None,
    execute: Executor = _execute,
) -> str:
    controller_arguments = _phase75_controller_arguments(
        controller_policy,
        mc_workers,
    )
    boundary = _validate_static_profile_boundary(
        requested_replicas,
        requested_flows=requested_flows,
        requested_stages=requested_stages,
    )
    configuration = boundary.configuration
    resource_profile = None
    deployment_overlay = boundary.overlay
    controller_job = boundary.controller_job
    controller_job_name = boundary.controller_job_name
    replaced_job_names = boundary.replaced_job_names
    phase8_gate1 = boundary == PHASE8_GATE1_PROFILE_BOUNDARY
    if phase8_gate1:
        if not skip_build:
            raise RuntimeError(
                "Phase 8 Gate 1 requires --skip-build to preserve every "
                "serving process"
            )
        if controller_policy == "mc" or mc_workers is not None:
            raise RuntimeError(
                "Phase 8 Gate 1 is deterministic-lookahead only; MC at 4x3x2 "
                "requires separate approval"
            )
        controller_job = PHASE8_GATE1_CONTROLLER_JOB
        controller_job_name = PHASE8_GATE1_CONTROLLER_JOB_NAME
        replaced_job_names = boundary.replaced_job_names
    if processor_memory_profile is not None:
        if boundary != PHASE6_PROFILE_BOUNDARY or not skip_build:
            raise RuntimeError(
                "Phase 7 resource evidence requires the approved 3x3x2 "
                "topology with --skip-build"
            )
        resource_profile = PROCESSOR_MEMORY_PROFILES[processor_memory_profile]
        deployment_overlay = (
            PHASE7_CANDIDATE_OVERLAY
            if resource_profile.name == "candidate"
            else PHASE7_OVERLAY
        )
        controller_job = PHASE7_CONTROLLER_JOB
        controller_job_name = "ibg-hybrid-controller-phase7"
        replaced_job_names = (
            *PHASE6_PROFILE_BOUNDARY.replaced_job_names,
            controller_job_name,
        )
    if controller_arguments is not None:
        if phase8_gate1:
            if controller_arguments != ("--policy", "lookahead"):
                raise RuntimeError(
                    "Phase 8 Gate 1 accepts only explicit --policy lookahead"
                )
        elif (
            boundary != PHASE6_PROFILE_BOUNDARY
            or not skip_build
            or resource_profile is None
            or resource_profile.name != "candidate"
        ):
            raise RuntimeError(
                "Phase 7.5 controller policy selection requires --skip-build, "
                "the approved 3x3x2 topology, and the accepted candidate "
                "processor memory profile"
            )
        deployment_overlay = PHASE75_OVERLAY
        controller_job = PHASE75_CONTROLLER_JOB
        controller_job_name = PHASE75_CONTROLLER_JOB_NAME
        replaced_job_names = (
            *PHASE6_PROFILE_BOUNDARY.replaced_job_names,
            "ibg-hybrid-controller-phase7",
            PHASE75_CONTROLLER_JOB_NAME,
        )
    replica_unit = "replica" if configuration.num_replicas == 1 else "replicas"
    print(
        "Selected Hybrid topology: "
        f"{configuration.num_flows} flows x {configuration.num_stages} stages "
        f"x {configuration.num_replicas} {replica_unit} per stage"
    )
    cluster_exists = CLUSTER_NAME in _kind_clusters(execute)
    if skip_build and not cluster_exists:
        raise RuntimeError(
            "--skip-build requires the existing persistent ibg-hybrid cluster"
        )
    if boundary in (PHASE6_PROFILE_BOUNDARY, PHASE8_GATE1_PROFILE_BOUNDARY) and not skip_build:
        raise RuntimeError(
            "profile reconciliation requires --skip-build to preserve "
            "existing serving processes"
        )
    existing_count = None
    existing_templates = None
    existing_statefulsets = None
    deliberate_resource_rollout = False
    if cluster_exists:
        preflight(execute=execute)
        statefulsets = _statefulset_inventory(execute)
        existing = discover_existing_replica_state(statefulsets)
        existing_count = existing.replica_count
        existing_templates = _statefulset_template_snapshot(statefulsets)
        existing_statefulsets = statefulsets
        if resource_profile is not None:
            deliberate_resource_rollout = (
                detect_resource_profile(statefulsets) != resource_profile
            )
        plan_bounded_rollout(
            existing_count=existing_count,
            requested_count=requested_replicas,
            batch_size=rollout_batch_size,
        )
        if boundary in (PHASE6_PROFILE_BOUNDARY, PHASE8_GATE1_PROFILE_BOUNDARY):
            _validate_live_profile_expansion(
                execute,
                existing_replica_count=existing_count,
                boundary=boundary,
            )
    else:
        _require_local_image(execute, KIND_NODE_IMAGE)
        execute(
            (
                "kind",
                "create",
                "cluster",
                "--name",
                CLUSTER_NAME,
                "--image",
                KIND_NODE_IMAGE,
                "--config",
                str(KIND_CONFIG),
                "--wait",
                "120s",
            ),
            False,
        )
        preflight(execute=execute)

    before_processes = None
    if skip_build:
        validate_node_images(execute)
        before_processes = _serving_process_snapshot(
            _pod_inventory(execute), replica_count=existing_count
        )
    else:
        _build_images_offline(execute)
        execute(
            (
                "kind",
                "load",
                "docker-image",
                "--name",
                CLUSTER_NAME,
                SERVICE_IMAGE,
                CONTROLLER_IMAGE,
            ),
            False,
        )
    if existing_count is None:
        initial_count = min(requested_replicas, rollout_batch_size)
        _apply_reconciled_boundary(
            execute,
            replica_count=initial_count,
            boundary=boundary,
            deployment_overlay=deployment_overlay,
            expected_templates=None,
            existing_statefulsets=None,
            processor_memory_profile=resource_profile,
        )
        existing_count = initial_count
    else:
        _apply_reconciled_boundary(
            execute,
            replica_count=existing_count,
            boundary=boundary,
            deployment_overlay=deployment_overlay,
            expected_templates=existing_templates,
            existing_statefulsets=existing_statefulsets,
            processor_memory_profile=resource_profile,
        )

    _validate_reconciled_profiles(execute, boundary=boundary)

    if not skip_build:
        execute(
            _kubectl(
                "rollout",
                "restart",
                *STATEFULSET_RESOURCES,
                FLOW_GENERATOR_RESOURCE,
                "-n",
                HYBRID_NAMESPACE,
            ),
            False,
        )
    _wait_for_target(execute, replica_count=existing_count)

    rollout = plan_bounded_rollout(
        existing_count=existing_count,
        requested_count=requested_replicas,
        batch_size=rollout_batch_size,
    )
    for batch in rollout.batches:
        execute(
            _kubectl(
                "scale",
                *STATEFULSET_RESOURCES,
                f"--replicas={batch.target_count}",
                "-n",
                HYBRID_NAMESPACE,
            ),
            False,
        )
        _wait_for_target(execute, replica_count=batch.target_count)

    preflight(execute=execute)
    if controller_arguments is not None or phase8_gate1:
        _reconcile_phase75_controller_sources(execute)
    if before_controller_job is not None:
        before_controller_job()
    execute(
        _kubectl(
            "delete",
            "job",
            *replaced_job_names,
            "-n",
            HYBRID_NAMESPACE,
            "--ignore-not-found",
            "--wait=true",
        ),
        False,
    )
    _apply_controller_job(
        execute,
        controller_job=controller_job,
        controller_job_name=controller_job_name,
        arguments=controller_arguments,
    )
    if controller_job_started is not None:
        controller_job_started()
    execute(
        _kubectl(
            "wait",
            "-n",
            HYBRID_NAMESPACE,
            "--for=condition=complete",
            f"job/{controller_job_name}",
            "--timeout=600s",
        ),
        False,
    )
    if after_controller_job is not None:
        after_controller_job()
    output = execute(
        _kubectl(
            "logs",
            "-n",
            HYBRID_NAMESPACE,
            f"job/{controller_job_name}",
        ),
        True,
    )
    if before_processes is not None:
        after_processes = _serving_process_snapshot(
            _pod_inventory(execute), replica_count=requested_replicas
        )
        if deliberate_resource_rollout:
            _validate_deliberate_processor_rollout(
                before_processes, after_processes
            )
        else:
            _validate_process_preservation(before_processes, after_processes)
    print(output, end="" if output.endswith("\n") else "\n")
    return output


def cleanup(*, execute: Executor = _execute) -> None:
    if CLUSTER_NAME in _kind_clusters(execute):
        execute(("kind", "delete", "cluster", "--name", CLUSTER_NAME), False)


def _positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def parse_args(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Operate only the persistent single-node Hybrid kind cluster; "
            "never starts or targets the shared ibg cluster."
        )
    )
    subparsers = parser.add_subparsers(dest="action", required=True)
    run_parser = subparsers.add_parser("run-small")
    run_parser.add_argument(
        "--skip-build",
        action="store_true",
        help=(
            "reuse matching node-local Hybrid images without building, "
            "loading, or restarting serving workloads"
        ),
    )
    run_parser.add_argument(
        "--flow",
        "--flows",
        dest="requested_flows",
        type=_positive_integer,
        default=None,
        help=(
            "logical flows in the approved topology; inferred from --replica "
            "when omitted"
        ),
    )
    run_parser.add_argument(
        "--stage",
        "--stages",
        dest="requested_stages",
        type=_positive_integer,
        default=None,
        help=(
            "stages in the approved topology; currently must be exactly three"
        ),
    )
    run_parser.add_argument(
        "--replica",
        "--replicas",
        dest="requested_replicas",
        type=_positive_integer,
        default=1,
        help="explicit final replica count for each of the three stages",
    )
    run_parser.add_argument(
        "--rollout-batch-size",
        type=int,
        default=1,
        help="maximum missing ordinals added to every stage per Ready gate",
    )
    run_parser.add_argument(
        "--processor-memory-profile",
        choices=tuple(PROCESSOR_MEMORY_PROFILES),
        default=None,
        help=(
            "Phase 7 only: run the baseline or processor-only candidate "
            "resource gate at the approved 3x3x2 topology"
        ),
    )
    run_parser.add_argument(
        "--policy",
        choices=("lookahead", "mc"),
        default=None,
        help=(
            "Phase 7.5 only: select the finite controller policy; omission "
            "retains deterministic lookahead"
        ),
    )
    run_parser.add_argument(
        "--mc-workers",
        type=int,
        default=None,
        help=(
            "Phase 7.5 only: explicit bounded controller workers for "
            "--policy mc"
        ),
    )
    subparsers.add_parser("preflight")
    subparsers.add_parser("cleanup")
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_args(arguments)
    try:
        if args.action == "run-small":
            run_small(
                skip_build=args.skip_build,
                requested_flows=args.requested_flows,
                requested_stages=args.requested_stages,
                requested_replicas=args.requested_replicas,
                rollout_batch_size=args.rollout_batch_size,
                processor_memory_profile=args.processor_memory_profile,
                controller_policy=args.policy,
                mc_workers=args.mc_workers,
            )
        elif args.action == "preflight":
            preflight()
        else:
            cleanup()
    except (
        json.JSONDecodeError,
        HybridKernelProfileExpansionError,
        HybridKernelResourceEvidenceError,
        HybridKernelRolloutError,
        RuntimeError,
        subprocess.CalledProcessError,
        ValueError,
    ) as error:
        print(f"Hybrid cluster isolation failure: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
