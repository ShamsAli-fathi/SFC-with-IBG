#!/usr/bin/env python3
"""Run Hybrid Kernel experiments or historical gates in its persistent cluster."""

from __future__ import annotations

import argparse
import copy
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from math import isfinite
from pathlib import Path
import secrets
import subprocess
import sys
import tarfile
import tempfile
from typing import Callable, Mapping, Sequence

from scripts.hybrid_offline_wheelhouse import validate_all_wheelhouses

from IBG_Hybrid.contracts import HybridConfiguration, ReplicaChoice
from IBG_Hybrid.console_output import HYBRID_SLOT_EVIDENCE_PREFIX
from IBG_Hybrid.control_plane_footprint import (
    HYBRID_CONTROL_PLANE_DATA_ENV,
    validate_hybrid_control_plane_data_snapshot,
)
from IBG_Hybrid.kernel_profile_expansion import (
    HYBRID_PROFILE_STATE_ALLOCATION_VERSION,
    HYBRID_PROFILE_STATE_ORDER,
    HybridKernelDynamicTopologyTransition,
    HybridKernelProfileExpansionError,
    generate_dynamic_topology_documents,
    profile_seed_from_runtime_source_identity,
    seeded_profile_state_counts,
    validate_dynamic_topology_transition,
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
from IBG_Hybrid.network_impairment import (
    HYBRID_NETEM_INIT_CONTAINER_NAME,
    HYBRID_NETWORK_IMPAIRMENT_ANNOTATION,
    HybridNetworkImpairment,
    validate_hybrid_network_impairment_events,
)


ROOT = Path(__file__).resolve().parents[1]
CLUSTER_NAME = "ibg-hybrid"
KUBECTL_CONTEXT = "kind-ibg-hybrid"
HYBRID_NAMESPACE = "ibg-hybrid-testbed"
HYBRID_TRACE_CONTRACT_VERSION = "ibg-hybrid-experiment-jsonl-v3"
DEFAULT_HYBRID_TRACE_DIR = ROOT / "runs"
HYBRID_CSV_OUTPUT_DIR = ROOT / "figures" / "IBG_hybrid"
HYBRID_CSV_FILENAMES = (
    "time.csv",
    "end_to_end_sla_violations.csv",
    "aggregate_utility.csv",
    "jain_index.csv",
    "replica_results.csv",
    "end_to_end_sla_excess_ms.csv",
)
HYBRID_FOOTPRINT_CSV_OUTPUT_DIR = HYBRID_CSV_OUTPUT_DIR / "footprint"
HYBRID_FOOTPRINT_CSV_FIELDS = (
    ("discovery_time_ms.csv", "timing_ms", "discovery"),
    ("admission_time_ms.csv", "timing_ms", "admission"),
    ("feedback_time_ms.csv", "timing_ms", "feedback"),
    ("active_control_time_ms.csv", "timing_ms", "active"),
    ("data_plane_wait_ms.csv", "timing_ms", "data_plane_wait"),
    ("kubernetes_discovery_tx_bytes.csv", "payload_bytes", "kubernetes_discovery_tx"),
    ("kubernetes_discovery_rx_bytes.csv", "payload_bytes", "kubernetes_discovery_rx"),
    ("route_command_tx_bytes.csv", "payload_bytes", "route_command_tx"),
    ("selected_telemetry_rx_bytes.csv", "payload_bytes", "selected_telemetry_rx"),
    ("belief_tx_bytes.csv", "payload_bytes", "belief_tx"),
    ("belief_rx_bytes.csv", "payload_bytes", "belief_rx"),
    ("belief_exchange_total_bytes.csv", "payload_bytes", "belief_exchange_total"),
    ("control_plane_payload_total_bytes.csv", "payload_bytes", "total"),
    ("kubernetes_discovery_tx_messages.csv", "messages", "kubernetes_discovery_tx"),
    ("kubernetes_discovery_rx_messages.csv", "messages", "kubernetes_discovery_rx"),
    ("route_command_tx_messages.csv", "messages", "route_command_tx"),
    ("selected_telemetry_rx_messages.csv", "messages", "selected_telemetry_rx"),
    ("belief_tx_messages.csv", "messages", "belief_tx"),
    ("belief_rx_messages.csv", "messages", "belief_rx"),
    ("belief_exchange_total_messages.csv", "messages", "belief_exchange_total"),
    ("control_plane_messages_total.csv", "messages", "total"),
)
HYBRID_RANDOM_SERIES_SEED_BITS = 63
HYBRID_POLICY_ROOT_SEED_ENV = "HYBRID_POLICY_ROOT_SEED"
HYBRID_PARITY_REPLAY_ENV = "HYBRID_PARITY_REPLAY"
KIND_NODE_IMAGE = (
    "kindest/node:v1.36.1@"
    "sha256:3489c7674813ba5d8b1a9977baea8a6e553784dab7b84759d1014dbd78f7ebd5"
)
KIND_CONFIG = (
    ROOT / "deploy" / "hybrid-kubernetes-phase4-small" / "kind-config.yaml"
)
OVERLAY = ROOT / "deploy" / "hybrid-kubernetes-phase4-small"
HYBRID_NAMESPACE_MANIFEST = (
    ROOT / "deploy" / "hybrid-kubernetes" / "namespace.yaml"
)
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
DYNAMIC_CONTROLLER_JOB = (
    ROOT / "deploy" / "hybrid-kubernetes" / "dynamic-controller-job.yaml"
)
DYNAMIC_CONTROLLER_JOB_NAME = "ibg-hybrid-controller-dynamic"
PHASE75_CONTROLLER_SOURCE_CONFIGMAP = (
    "ibg-hybrid-controller-phase75-source"
)
PHASE75_CONTROLLER_SOURCES = (
    ROOT / "IBG_Hybrid" / "control_plane_footprint.py",
    ROOT / "IBG_Hybrid" / "kernel_controller.py",
    ROOT / "IBG_Hybrid" / "kernel_kubernetes_discovery.py",
    ROOT / "IBG_Hybrid" / "kernel_phase4_validation.py",
    ROOT / "IBG_Hybrid" / "kernel_controller_cli.py",
    ROOT / "IBG_Hybrid" / "console_output.py",
)
MAX_HYBRID_KERNEL_MC_WORKERS = 2
SERVICE_IMAGE = "ibg-hybrid-testbed:kernel-service-v1"
CONTROLLER_IMAGE = "ibg-hybrid-testbed:kernel-controller-v1"
NETEM_IMAGE = "ibg-hybrid-testbed:netem-v1"
NETEM_BASE_IMAGE = KIND_NODE_IMAGE
NORMALIZED_SERVICE_IMAGE = (
    "docker.io/library/ibg-hybrid-testbed:kernel-service-v1"
)
NORMALIZED_CONTROLLER_IMAGE = (
    "docker.io/library/ibg-hybrid-testbed:kernel-controller-v1"
)
NORMALIZED_NETEM_IMAGE = "docker.io/library/ibg-hybrid-testbed:netem-v1"
PYTHON_BASE_IMAGE = "mcr.microsoft.com/azurelinux/base/python:3.12"
CONTROL_PLANE_NODE_NAME = "ibg-hybrid-control-plane"
WORKER_NODE_NAME = "ibg-hybrid-worker"
WORKLOAD_NODE_LABEL = "ibg-hybrid.workload-node"
WORKLOAD_NODE_LABEL_VALUE = "true"
EXPECTED_NODE_NAMES = frozenset({CONTROL_PLANE_NODE_NAME, WORKER_NODE_NAME})
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
NETEM_DOCKERFILE = (
    ROOT / "deploy" / "hybrid-kubernetes" / "Dockerfile.netem"
)
CONTROLLER_CPU_REQUEST_MILLI = 2000
CONTROLLER_MEMORY_REQUEST_BYTES = 256 * 1024**2

Command = tuple[str, ...]
Executor = Callable[[Command, bool], str]
RunHook = Callable[[], None]
ControllerLogStreamer = Callable[[str], str]


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
class HybridNodeResourcePreflight:
    requested_cpu_milli: int
    allocatable_cpu_milli: int
    requested_memory_bytes: int
    allocatable_memory_bytes: int
    added_stage_pods: int


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
    runtime_document: Mapping[str, object] | None = None
    controller_document: Mapping[str, object] | None = None
    profile_seed: int | None = None


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


def _node_items_by_name(
    document: Mapping[str, object],
) -> Mapping[str, Mapping[str, object]]:
    items = document.get("items")
    if not isinstance(items, list):
        raise RuntimeError("Kubernetes node inventory has no item list")
    by_name: dict[str, Mapping[str, object]] = {}
    for item in items:
        if not isinstance(item, Mapping):
            raise RuntimeError("Kubernetes node inventory item is not an object")
        metadata = item.get("metadata")
        name = metadata.get("name") if isinstance(metadata, Mapping) else None
        if not isinstance(name, str) or not name or name in by_name:
            raise RuntimeError("Kubernetes node inventory has invalid identities")
        by_name[name] = item
    return by_name


def _node_ready(item: Mapping[str, object]) -> bool:
    status = item.get("status")
    conditions = status.get("conditions") if isinstance(status, Mapping) else None
    return isinstance(conditions, list) and any(
        isinstance(condition, Mapping)
        and condition.get("type") == "Ready"
        and condition.get("status") == "True"
        for condition in conditions
    )


def _validate_node_topology(
    nodes: Mapping[str, object],
) -> Mapping[str, Mapping[str, object]]:
    by_name = _node_items_by_name(nodes)
    if frozenset(by_name) != EXPECTED_NODE_NAMES:
        raise RuntimeError(
            "refusing non-dedicated cluster nodes: "
            f"expected {sorted(EXPECTED_NODE_NAMES)}, got {sorted(by_name)}"
        )
    control_plane = by_name[CONTROL_PLANE_NODE_NAME]
    worker = by_name[WORKER_NODE_NAME]
    control_metadata = control_plane.get("metadata")
    worker_metadata = worker.get("metadata")
    control_labels = (
        control_metadata.get("labels")
        if isinstance(control_metadata, Mapping)
        else None
    )
    worker_labels = (
        worker_metadata.get("labels")
        if isinstance(worker_metadata, Mapping)
        else None
    )
    control_plane_label = "node-role.kubernetes.io/control-plane"
    if (
        not isinstance(control_labels, Mapping)
        or control_plane_label not in control_labels
        or WORKLOAD_NODE_LABEL in control_labels
        or not isinstance(worker_labels, Mapping)
        or worker_labels.get(WORKLOAD_NODE_LABEL) != WORKLOAD_NODE_LABEL_VALUE
        or control_plane_label in worker_labels
        or not _node_ready(control_plane)
        or not _node_ready(worker)
    ):
        raise RuntimeError(
            "Hybrid node roles, workload label, or Ready state are invalid"
        )
    return by_name


def _pod_node_name(item: Mapping[str, object]) -> str | None:
    spec = item.get("spec")
    value = spec.get("nodeName") if isinstance(spec, Mapping) else None
    return value if isinstance(value, str) and value else None


def validate_cluster_inventory(
    *,
    nodes: Mapping[str, object],
    namespaces: Mapping[str, object],
    pods: Mapping[str, object],
) -> None:
    _validate_node_topology(nodes)

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
    misplaced_workloads = []
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
                    "ibg-hybrid-controller-dynamic-",
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
            elif _pod_node_name(item) != WORKER_NODE_NAME:
                misplaced_workloads.append(f"{namespace}/{name}")
    if foreign_pods:
        raise RuntimeError(
            "refusing cluster with foreign workload Pods: "
            + ", ".join(sorted(foreign_pods))
        )
    if misplaced_workloads:
        raise RuntimeError(
            "refusing Hybrid workloads outside the dedicated worker: "
            + ", ".join(sorted(misplaced_workloads))
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


def _validate_offline_wheelhouses() -> None:
    """Fail before Docker if either Hybrid image lacks its local wheel set."""

    validate_all_wheelhouses(root=ROOT)


def _build_images_offline(
    execute: Executor,
    *,
    wheelhouses_validated: bool = False,
    network_impairment: HybridNetworkImpairment | None = None,
) -> None:
    """Build required images without pulls or build-step network access."""

    if network_impairment is None:
        network_impairment = HybridNetworkImpairment.disabled()
    if not isinstance(network_impairment, HybridNetworkImpairment):
        raise RuntimeError("Hybrid network impairment setting is invalid")
    if not wheelhouses_validated:
        _validate_offline_wheelhouses()
    _require_local_image(execute, PYTHON_BASE_IMAGE)
    images = [
        (SERVICE_DOCKERFILE, SERVICE_IMAGE),
        (CONTROLLER_DOCKERFILE, CONTROLLER_IMAGE),
    ]
    if network_impairment.enabled:
        _require_local_image(execute, NETEM_BASE_IMAGE)
        images.append((NETEM_DOCKERFILE, NETEM_IMAGE))
    for dockerfile, image in images:
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


def validate_node_images(
    execute: Executor,
    *,
    network_impairment: HybridNetworkImpairment | None = None,
) -> None:
    """Match normalized node tags to the locally selected platform images."""

    if network_impairment is None:
        network_impairment = HybridNetworkImpairment.disabled()
    if not isinstance(network_impairment, HybridNetworkImpairment):
        raise RuntimeError("Hybrid network impairment setting is invalid")
    expected = {
        NORMALIZED_SERVICE_IMAGE: _local_platform_image_id(execute, SERVICE_IMAGE),
        NORMALIZED_CONTROLLER_IMAGE: _local_platform_image_id(
            execute, CONTROLLER_IMAGE
        ),
    }
    if network_impairment.enabled:
        expected[NORMALIZED_NETEM_IMAGE] = _local_platform_image_id(
            execute, NETEM_IMAGE
        )
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
    misplaced = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        item_metadata = item.get("metadata")
        name = (
            item_metadata.get("name")
            if isinstance(item_metadata, Mapping)
            else None
        )
        if isinstance(name, str) and (
            name.startswith("hybrid-stage-")
            or name.startswith("ibg-hybrid-flow-generator-")
        ) and _pod_node_name(item) != WORKER_NODE_NAME:
            misplaced.append(name)
    if misplaced:
        raise RuntimeError(
            "Hybrid serving Pods are not all placed on the dedicated worker: "
            + ", ".join(sorted(misplaced))
        )


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


def _validate_scale_down_process_preservation(
    before: tuple[ServingPodProcessSnapshot, ...],
    after: tuple[ServingPodProcessSnapshot, ...],
    *,
    existing_count: int,
    requested_count: int,
) -> None:
    """Preserve retained processes and require only high ordinals to disappear."""

    if requested_count >= existing_count:
        raise RuntimeError("scale-down process validation requires a lower target")
    before_by_name = {item.pod_name: item for item in before}
    after_by_name = {item.pod_name: item for item in after}
    flow_generators = {
        name for name in before_by_name if name.startswith("ibg-hybrid-flow-generator-")
    }
    if len(flow_generators) != 1:
        raise RuntimeError("scale-down process snapshot has no unique flow generator")
    retained_names = flow_generators | {
        f"hybrid-stage-{stage}-{ordinal}"
        for stage in range(1, 4)
        for ordinal in range(requested_count)
    }
    removed_names = {
        f"hybrid-stage-{stage}-{ordinal}"
        for stage in range(1, 4)
        for ordinal in range(requested_count, existing_count)
    }
    if set(before_by_name) != retained_names | removed_names:
        raise RuntimeError("scale-down pre-snapshot has unexpected serving Pods")
    if set(after_by_name) != retained_names:
        lingering = sorted(set(after_by_name) & removed_names)
        raise RuntimeError(
            "scale-down serving Pod set is not the exact retained subset"
            + (f"; removed Pods still present: {lingering}" if lingering else "")
        )
    changed = sorted(
        name for name in retained_names if before_by_name[name] != after_by_name[name]
    )
    if changed:
        raise RuntimeError(
            "scale-down changed a retained serving Pod UID or restart count: "
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


def _validate_network_impairment_rollout(
    before: tuple[ServingPodProcessSnapshot, ...],
    after: tuple[ServingPodProcessSnapshot, ...],
    *,
    requested_count: int,
) -> None:
    """Require a netem template transition to replace replicas, not traffic."""

    before_by_name = {item.pod_name: item for item in before}
    after_by_name = {item.pod_name: item for item in after}
    flow_generators = {
        name
        for name in before_by_name
        if name.startswith("ibg-hybrid-flow-generator-")
    }
    if len(flow_generators) != 1:
        raise RuntimeError(
            "network-impairment rollout has no unique flow generator"
        )
    flow_generator_name = next(iter(flow_generators))
    if after_by_name.get(flow_generator_name) != before_by_name[flow_generator_name]:
        raise RuntimeError(
            "network-impairment rollout changed the flow generator"
        )
    expected_replicas = {
        f"hybrid-stage-{stage}-{ordinal}"
        for stage in range(1, 4)
        for ordinal in range(requested_count)
    }
    if set(after_by_name) != expected_replicas | {flow_generator_name}:
        raise RuntimeError(
            "network-impairment rollout changed the requested serving Pod set"
        )
    for name in sorted(expected_replicas):
        new = after_by_name[name]
        old = before_by_name.get(name)
        if old is not None and new.pod_uid == old.pod_uid:
            raise RuntimeError(
                f"network-impairment rollout did not replace {name}"
            )
        if any(restarts for _container, restarts in new.container_restarts):
            raise RuntimeError(
                f"network-impairment rollout produced restarts in {name}"
            )


def _runtime_profile_refresh_pod_names(
    choices: Sequence[ReplicaChoice],
) -> tuple[str, ...]:
    return tuple(
        f"hybrid-stage-{choice.stage}-{choice.replica - 1}"
        for choice in sorted(choices)
    )


def _validate_runtime_profile_refresh_processes(
    before: tuple[ServingPodProcessSnapshot, ...],
    after: tuple[ServingPodProcessSnapshot, ...],
    *,
    changed_identities: Sequence[ReplicaChoice],
) -> None:
    """Require only explicitly changed runtime identities to receive new Pods."""

    before_by_name = {item.pod_name: item for item in before}
    after_by_name = {item.pod_name: item for item in after}
    if set(before_by_name) != set(after_by_name):
        raise RuntimeError("runtime-profile refresh changed the serving Pod set")
    changed_names = set(_runtime_profile_refresh_pod_names(changed_identities))
    unknown = changed_names - set(before_by_name)
    if unknown:
        raise RuntimeError(
            "runtime-profile refresh names an absent serving Pod: "
            + ", ".join(sorted(unknown))
        )
    for name in sorted(before_by_name):
        old = before_by_name[name]
        new = after_by_name[name]
        if name in changed_names:
            if new.pod_uid == old.pod_uid:
                raise RuntimeError(
                    f"runtime-profile refresh did not replace affected Pod {name}"
                )
            if any(restarts for _container, restarts in new.container_restarts):
                raise RuntimeError(
                    f"runtime-profile refresh produced restarts in {name}"
                )
        elif new != old:
            raise RuntimeError(
                f"runtime-profile refresh changed unaffected Pod {name}"
            )


def _refresh_runtime_profile_pods(
    execute: Executor,
    *,
    changed_identities: Sequence[ReplicaChoice],
    replica_count: int,
) -> None:
    """Replace affected StatefulSet Pods stage by stage with a Ready gate."""

    by_stage = {
        stage: tuple(
            choice
            for choice in sorted(changed_identities)
            if choice.stage == stage
        )
        for stage in range(1, 4)
    }
    for stage in range(1, 4):
        choices = by_stage[stage]
        if not choices:
            continue
        execute(
            _kubectl(
                "delete",
                *(f"pod/{name}" for name in _runtime_profile_refresh_pod_names(choices)),
                "-n",
                HYBRID_NAMESPACE,
                "--wait=true",
            ),
            False,
        )
        _wait_for_target(execute, replica_count=replica_count)


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


def _cpu_milli(value: object) -> int:
    if not isinstance(value, str) or not value:
        raise RuntimeError("Kubernetes CPU quantity must be a nonempty string")
    multipliers = {"m": Decimal(1), "u": Decimal("0.001"), "n": Decimal("0.000001")}
    suffix = value[-1]
    try:
        if suffix in multipliers:
            amount = Decimal(value[:-1]) * multipliers[suffix]
        else:
            amount = Decimal(value) * Decimal(1000)
    except InvalidOperation as error:
        raise RuntimeError(f"invalid Kubernetes CPU quantity: {value}") from error
    if amount < 0 or amount != amount.to_integral_value():
        raise RuntimeError(f"unsupported Kubernetes CPU quantity: {value}")
    return int(amount)


def _memory_bytes(value: object) -> int:
    if not isinstance(value, str) or not value:
        raise RuntimeError("Kubernetes memory quantity must be a nonempty string")
    binary = {
        "Ki": 1024,
        "Mi": 1024**2,
        "Gi": 1024**3,
        "Ti": 1024**4,
    }
    decimal = {"K": 1000, "M": 1000**2, "G": 1000**3, "T": 1000**4}
    multiplier = 1
    number = value
    for suffix, candidate in (*binary.items(), *decimal.items()):
        if value.endswith(suffix):
            multiplier = candidate
            number = value[: -len(suffix)]
            break
    try:
        amount = Decimal(number) * multiplier
    except InvalidOperation as error:
        raise RuntimeError(f"invalid Kubernetes memory quantity: {value}") from error
    if amount < 0 or amount != amount.to_integral_value():
        raise RuntimeError(f"unsupported Kubernetes memory quantity: {value}")
    return int(amount)


def _container_request(container: Mapping[str, object]) -> tuple[int, int]:
    resources = container.get("resources")
    requests = resources.get("requests") if isinstance(resources, Mapping) else None
    if not isinstance(requests, Mapping):
        return 0, 0
    return (
        _cpu_milli(requests.get("cpu", "0")),
        _memory_bytes(requests.get("memory", "0")),
    )


def _pod_request(pod: Mapping[str, object]) -> tuple[int, int]:
    spec = pod.get("spec")
    if not isinstance(spec, Mapping):
        raise RuntimeError("Kubernetes Pod has no resource spec")
    containers = spec.get("containers")
    if not isinstance(containers, list):
        raise RuntimeError("Kubernetes Pod has no container list")
    regular = [_container_request(item) for item in containers if isinstance(item, Mapping)]
    if len(regular) != len(containers):
        raise RuntimeError("Kubernetes Pod container resource entry is invalid")
    cpu = sum(item[0] for item in regular)
    memory = sum(item[1] for item in regular)
    init_containers = spec.get("initContainers", [])
    if not isinstance(init_containers, list):
        raise RuntimeError("Kubernetes Pod init-container list is invalid")
    init = [
        _container_request(item)
        for item in init_containers
        if isinstance(item, Mapping)
    ]
    if len(init) != len(init_containers):
        raise RuntimeError("Kubernetes Pod init-container resource entry is invalid")
    if init:
        cpu = max(cpu, max(item[0] for item in init))
        memory = max(memory, max(item[1] for item in init))
    overhead = spec.get("overhead")
    if isinstance(overhead, Mapping):
        cpu += _cpu_milli(overhead.get("cpu", "0"))
        memory += _memory_bytes(overhead.get("memory", "0"))
    return cpu, memory


def _validate_node_resource_capacity(
    execute: Executor,
    *,
    existing_replica_count: int,
    requested_replica_count: int,
) -> HybridNodeResourcePreflight:
    """Fail before mutation when the worker scheduler envelope is too small."""

    nodes = _json_output(execute, _kubectl("get", "nodes", "-o", "json"))
    worker = _validate_node_topology(nodes)[WORKER_NODE_NAME]
    status = worker.get("status")
    allocatable = status.get("allocatable") if isinstance(status, Mapping) else None
    if not isinstance(allocatable, Mapping):
        raise RuntimeError("Hybrid worker has no allocatable resource inventory")
    allocatable_cpu = _cpu_milli(allocatable.get("cpu"))
    allocatable_memory = _memory_bytes(allocatable.get("memory"))

    pods = _json_output(execute, _kubectl("get", "pods", "-A", "-o", "json"))
    pod_items = pods.get("items")
    if not isinstance(pod_items, list):
        raise RuntimeError("Hybrid resource preflight has no Pod inventory")
    requested_cpu = 0
    requested_memory = 0
    for pod in pod_items:
        if not isinstance(pod, Mapping):
            raise RuntimeError("Hybrid resource preflight Pod is invalid")
        status = pod.get("status")
        if isinstance(status, Mapping) and status.get("phase") in {
            "Succeeded",
            "Failed",
        }:
            continue
        if _pod_node_name(pod) != WORKER_NODE_NAME:
            continue
        pod_cpu, pod_memory = _pod_request(pod)
        requested_cpu += pod_cpu
        requested_memory += pod_memory

    added_stage_pods = 3 * max(
        0, requested_replica_count - existing_replica_count
    )
    # Accepted Phase 7 candidate requests: processor 50m with 64 binary MiB,
    # plus forwarder 25m with 128 binary MiB. A fresh cluster also adds the
    # flow generator at 50m/128 binary MiB. The finite controller adds
    # 2000m/256 binary MiB after old Jobs are deleted. Current Running Pods are
    # already included above.
    added_flow_generators = 1 if existing_replica_count == 0 else 0
    requested_cpu += (
        added_stage_pods * 75
        + added_flow_generators * 50
        + CONTROLLER_CPU_REQUEST_MILLI
    )
    requested_memory += (
        added_stage_pods * (64 + 128) * 1024**2
        + added_flow_generators * 128 * 1024**2
        + CONTROLLER_MEMORY_REQUEST_BYTES
    )
    result = HybridNodeResourcePreflight(
        requested_cpu_milli=requested_cpu,
        allocatable_cpu_milli=allocatable_cpu,
        requested_memory_bytes=requested_memory,
        allocatable_memory_bytes=allocatable_memory,
        added_stage_pods=added_stage_pods,
    )
    if requested_cpu > allocatable_cpu or requested_memory > allocatable_memory:
        raise RuntimeError(
            "requested Hybrid topology exceeds worker allocatable resources: "
            f"cpu={requested_cpu}m/{allocatable_cpu}m, "
            f"memory={requested_memory}/{allocatable_memory} bytes"
        )
    return result


def _profile_boundary(
    requested_replicas: int,
    *,
    requested_flows: int | None = None,
    requested_stages: int | None = None,
    profile_seed: int | None = None,
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
    resolved_stages = 3 if requested_stages is None else requested_stages
    if resolved_stages != 3:
        raise RuntimeError(
            "the frozen Hybrid L=2 model requires exactly three stages"
        )
    if requested_flows is None:
        historical_flows = {1: 2, 2: 3}
        if requested_replicas not in historical_flows:
            raise RuntimeError(
                "--flow is required when requesting more than two replicas"
            )
        requested_flows = historical_flows[requested_replicas]
    configuration = HybridConfiguration(
        requested_flows,
        resolved_stages,
        requested_replicas,
        2,
    )
    runtime, controller = generate_dynamic_topology_documents(
        canonical_runtime=_load_json_mapping(
            PHASE6_PROFILE_BOUNDARY.runtime_profiles
        ),
        canonical_controller=_load_json_mapping(
            PHASE6_PROFILE_BOUNDARY.controller_inputs
        ),
        configuration=configuration,
        profile_seed=profile_seed,
    )
    source_identity = str(controller["source_identity"])
    return HybridProfileBoundary(
        configuration=configuration,
        source_identity=source_identity,
        overlay=PHASE7_CANDIDATE_OVERLAY,
        runtime_profiles=PHASE6_PROFILE_BOUNDARY.runtime_profiles,
        controller_inputs=PHASE6_PROFILE_BOUNDARY.controller_inputs,
        controller_job=DYNAMIC_CONTROLLER_JOB,
        controller_job_name=DYNAMIC_CONTROLLER_JOB_NAME,
        replaced_job_names=(
            *PHASE8_GATE1_PROFILE_BOUNDARY.replaced_job_names,
            DYNAMIC_CONTROLLER_JOB_NAME,
        ),
        runtime_document=runtime,
        controller_document=controller,
        profile_seed=profile_seed,
    )


def _load_json_mapping(path: Path) -> Mapping[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Hybrid profile document is not an object: {path}")
    return payload


def _boundary_runtime_document(
    boundary: HybridProfileBoundary,
) -> Mapping[str, object]:
    return (
        boundary.runtime_document
        if boundary.runtime_document is not None
        else _load_json_mapping(boundary.runtime_profiles)
    )


def _boundary_controller_document(
    boundary: HybridProfileBoundary,
) -> Mapping[str, object]:
    return (
        boundary.controller_document
        if boundary.controller_document is not None
        else _load_json_mapping(boundary.controller_inputs)
    )


def _validate_static_profile_boundary(
    requested_replicas: int,
    *,
    requested_flows: int | None = None,
    requested_stages: int | None = None,
    profile_seed: int | None = None,
) -> HybridProfileBoundary:
    boundary = _profile_boundary(
        requested_replicas,
        requested_flows=requested_flows,
        requested_stages=requested_stages,
        profile_seed=profile_seed,
    )
    runtime = _boundary_runtime_document(boundary)
    controller = _boundary_controller_document(boundary)
    # Generation parses and validates both complete canonical documents.  Keep
    # one explicit parse here so callers cannot substitute a malformed boundary.
    generate_dynamic_topology_documents(
        canonical_runtime=_load_json_mapping(
            PHASE6_PROFILE_BOUNDARY.runtime_profiles
        ),
        canonical_controller=_load_json_mapping(
            PHASE6_PROFILE_BOUNDARY.controller_inputs
        ),
        configuration=boundary.configuration,
        profile_seed=profile_seed,
    )
    if runtime != boundary.runtime_document or controller != boundary.controller_document:
        raise RuntimeError("dynamic Hybrid topology documents are inconsistent")
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
    refresh_runtime_profiles: bool = False,
) -> HybridKernelDynamicTopologyTransition | None:
    deployed_runtime, deployed_controller = _deployed_profile_documents(execute)
    if boundary.runtime_document is None:
        validate_append_only_profile_expansion(
            deployed_runtime=deployed_runtime,
            deployed_controller=deployed_controller,
            proposed_runtime=_boundary_runtime_document(boundary),
            proposed_controller=_boundary_controller_document(boundary),
            existing_replica_count=existing_replica_count,
            expected_configuration=boundary.configuration,
            expected_source_identity=boundary.source_identity,
        )
        return None
    return validate_dynamic_topology_transition(
        deployed_runtime=deployed_runtime,
        deployed_controller=deployed_controller,
        proposed_runtime=_boundary_runtime_document(boundary),
        proposed_controller=_boundary_controller_document(boundary),
        canonical_runtime=_load_json_mapping(
            PHASE6_PROFILE_BOUNDARY.runtime_profiles
        ),
        canonical_controller=_load_json_mapping(
            PHASE6_PROFILE_BOUNDARY.controller_inputs
        ),
        existing_replica_count=existing_replica_count,
        target_configuration=boundary.configuration,
        profile_seed=boundary.profile_seed,
        allow_runtime_profile_refresh=refresh_runtime_profiles,
        allow_interrupted_scale_down=True,
    )


def _validate_reconciled_profiles(
    execute: Executor, *, boundary: HybridProfileBoundary
) -> None:
    runtime, controller = _deployed_profile_documents(execute)
    if runtime != _boundary_runtime_document(boundary):
        raise RuntimeError("reconciled runtime profile does not match target")
    if controller != _boundary_controller_document(boundary):
        raise RuntimeError("reconciled controller input does not match target")


def _statefulset_network_impairment(
    document: Mapping[str, object],
) -> HybridNetworkImpairment:
    """Read one strict, stage-consistent netem template configuration."""

    items = document.get("items")
    if not isinstance(items, list):
        raise RuntimeError("StatefulSet impairment inventory has no item list")
    statefulsets = {
        "items": [
            item
            for item in items
            if isinstance(item, dict) and item.get("kind") == "StatefulSet"
        ]
    }
    discover_existing_replica_state(statefulsets)
    resolved = []
    for item in statefulsets["items"]:
        spec = item.get("spec")
        template = spec.get("template") if isinstance(spec, Mapping) else None
        template_metadata = (
            template.get("metadata") if isinstance(template, Mapping) else None
        )
        pod_spec = template.get("spec") if isinstance(template, Mapping) else None
        if not isinstance(template_metadata, Mapping) or not isinstance(
            pod_spec, Mapping
        ):
            raise RuntimeError(
                "Hybrid StatefulSet has no network-impairment template boundary"
            )
        annotations = template_metadata.get("annotations", {})
        if annotations is None:
            annotations = {}
        if not isinstance(annotations, Mapping):
            raise RuntimeError("Hybrid StatefulSet template annotations are invalid")
        annotation = annotations.get(HYBRID_NETWORK_IMPAIRMENT_ANNOTATION)
        init_containers = pod_spec.get("initContainers", [])
        if not isinstance(init_containers, list) or any(
            not isinstance(container, Mapping) for container in init_containers
        ):
            raise RuntimeError("Hybrid StatefulSet init containers are invalid")
        netem_containers = [
            container
            for container in init_containers
            if container.get("name") == HYBRID_NETEM_INIT_CONTAINER_NAME
        ]
        if annotation is None:
            if init_containers:
                raise RuntimeError(
                    "disabled Hybrid StatefulSet must not retain init containers"
                )
            impairment = HybridNetworkImpairment.disabled()
        else:
            if not isinstance(annotation, str):
                raise RuntimeError(
                    "Hybrid StatefulSet impairment annotation is not JSON text"
                )
            try:
                impairment = HybridNetworkImpairment.from_json(annotation)
            except ValueError as error:
                raise RuntimeError(
                    f"Hybrid StatefulSet impairment annotation is invalid: {error}"
                ) from error
            if not impairment.enabled:
                raise RuntimeError(
                    "disabled Hybrid StatefulSet must not retain netem provenance"
                )
            if len(init_containers) != 1 or len(netem_containers) != 1:
                raise RuntimeError(
                    "enabled Hybrid StatefulSet must have exactly one netem init "
                    "container"
                )
            actual = copy.deepcopy(dict(netem_containers[0]))
            # Kubernetes defaults these presentation-only fields after apply.
            actual.pop("terminationMessagePath", None)
            actual.pop("terminationMessagePolicy", None)
            expected = impairment.init_container(image=NETEM_IMAGE)
            if actual != expected:
                raise RuntimeError(
                    "Hybrid StatefulSet netem init container drifted from its "
                    "versioned configuration"
                )
        resolved.append(impairment)
    if not resolved or any(item != resolved[0] for item in resolved[1:]):
        raise RuntimeError(
            "Hybrid StatefulSets have mixed network-impairment configurations"
        )
    return resolved[0]


def _without_network_impairment(
    document: Mapping[str, object],
) -> Mapping[str, object]:
    """Remove only the bounded netem fields for unrelated-drift comparison."""

    stripped = copy.deepcopy(document)
    items = stripped.get("items")
    if not isinstance(items, list):
        raise RuntimeError("StatefulSet template inventory has no item list")
    for item in items:
        if not isinstance(item, dict) or item.get("kind") != "StatefulSet":
            continue
        spec = item.get("spec")
        template = spec.get("template") if isinstance(spec, dict) else None
        metadata = template.get("metadata") if isinstance(template, dict) else None
        pod_spec = template.get("spec") if isinstance(template, dict) else None
        if not isinstance(metadata, dict) or not isinstance(pod_spec, dict):
            raise RuntimeError("StatefulSet has no stable Pod template")
        annotations = metadata.get("annotations")
        if annotations is not None:
            if not isinstance(annotations, dict):
                raise RuntimeError("StatefulSet template annotations are invalid")
            annotations.pop(HYBRID_NETWORK_IMPAIRMENT_ANNOTATION, None)
            if not annotations:
                metadata.pop("annotations", None)
        init_containers = pod_spec.get("initContainers")
        if init_containers is not None:
            if not isinstance(init_containers, list) or any(
                not isinstance(container, dict) for container in init_containers
            ):
                raise RuntimeError("StatefulSet init containers are invalid")
            retained = [
                container
                for container in init_containers
                if container.get("name") != HYBRID_NETEM_INIT_CONTAINER_NAME
            ]
            if retained:
                pod_spec["initContainers"] = retained
            else:
                pod_spec.pop("initContainers", None)
    return stripped


def _network_impairment_patch_document(
    *, stage: int, network_impairment: HybridNetworkImpairment
) -> Mapping[str, object]:
    if not network_impairment.enabled:
        raise RuntimeError("disabled Hybrid network impairment has no manifest patch")
    return {
        "apiVersion": "apps/v1",
        "kind": "StatefulSet",
        "metadata": {
            "name": f"hybrid-stage-{stage}",
            "namespace": HYBRID_NAMESPACE,
        },
        "spec": {
            "template": {
                "metadata": {
                    "annotations": {
                        HYBRID_NETWORK_IMPAIRMENT_ANNOTATION: (
                            network_impairment.to_json()
                        )
                    }
                },
                "spec": {
                    "initContainers": [
                        network_impairment.init_container(image=NETEM_IMAGE)
                    ]
                },
            }
        },
    }


def _write_network_impairment_patches(
    root: Path, network_impairment: HybridNetworkImpairment
) -> str:
    if not network_impairment.enabled:
        return ""
    patch_lines = []
    for stage in range(1, 4):
        name = f"netem-stage-{stage}.json"
        (root / name).write_text(
            json.dumps(
                _network_impairment_patch_document(
                    stage=stage,
                    network_impairment=network_impairment,
                ),
                sort_keys=True,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        patch_lines.append(f"  - path: {name}")
    return "patches:\n" + "\n".join(patch_lines) + "\n"


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
    network_impairment: HybridNetworkImpairment | None = None,
    boundary: HybridProfileBoundary = PHASE4_PROFILE_BOUNDARY,
    deployment_overlay: Path | None = None,
    expected_templates: tuple[StatefulSetPodTemplateSnapshot, ...] | None = None,
    existing_statefulsets: Mapping[str, object] | None = None,
    processor_memory_profile: ProcessorMemoryProfile | None = None,
    apply_resources: bool = True,
    bootstrap_namespace: bool = False,
) -> None:
    if network_impairment is None:
        network_impairment = HybridNetworkImpairment.disabled()
    if not isinstance(network_impairment, HybridNetworkImpairment):
        raise RuntimeError("Hybrid network impairment setting is invalid")
    deploy_root = ROOT / "deploy"
    with tempfile.TemporaryDirectory(
        prefix=".ibg-hybrid-phase5-", dir=deploy_root
    ) as directory:
        temporary_root = Path(directory)
        kustomization = temporary_root / "kustomization.yaml"
        replica_lines = "\n".join(
            f"  - name: hybrid-stage-{stage}\n    count: {replica_count}"
            for stage in range(1, 4)
        )
        dynamic_config_maps = ""
        if boundary.runtime_document is not None:
            (temporary_root / "runtime-profiles.json").write_text(
                json.dumps(
                    _boundary_runtime_document(boundary),
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                encoding="utf-8",
            )
            (temporary_root / "controller-inputs.json").write_text(
                json.dumps(
                    _boundary_controller_document(boundary),
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                encoding="utf-8",
            )
            dynamic_config_maps = (
                "configMapGenerator:\n"
                "  - name: ibg-hybrid-runtime-profiles\n"
                "    namespace: ibg-hybrid-testbed\n"
                "    behavior: replace\n"
                "    files:\n"
                "      - runtime-profiles.json\n"
                "  - name: ibg-hybrid-planning-links\n"
                "    namespace: ibg-hybrid-testbed\n"
                "    behavior: replace\n"
                "    files:\n"
                "      - controller-inputs.json\n"
                "generatorOptions:\n"
                "  disableNameSuffixHash: true\n"
            )
        network_patches = _write_network_impairment_patches(
            temporary_root, network_impairment
        )
        kustomization.write_text(
            "apiVersion: kustomize.config.k8s.io/v1beta1\n"
            "kind: Kustomization\n"
            "resources:\n"
            f"  - ../{(deployment_overlay or boundary.overlay).relative_to(deploy_root)}\n"
            "replicas:\n"
            f"{replica_lines}\n"
            f"{dynamic_config_maps}"
            f"{network_patches}",
            encoding="utf-8",
        )
        if bootstrap_namespace:
            execute(
                _kubectl("apply", "-f", str(HYBRID_NAMESPACE_MANIFEST)),
                False,
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
        rendered_network_impairment = _statefulset_network_impairment(dry_run)
        if rendered_network_impairment != network_impairment:
            raise RuntimeError(
                "rendered Hybrid StatefulSets do not match the requested "
                "network impairment"
            )
        dry_run_without_network = _without_network_impairment(dry_run)
        existing_without_network = (
            None
            if existing_statefulsets is None
            else _without_network_impairment(existing_statefulsets)
        )
        if (
            processor_memory_profile is not None
            and existing_without_network is not None
        ):
            validate_processor_only_transition(
                existing_without_network,
                dry_run_without_network,
                processor_memory_profile,
            )
        elif (
            expected_templates is not None
            and _statefulset_template_snapshot(dry_run_without_network)
            != expected_templates
        ):
            raise RuntimeError(
                "refusing reconciliation that changes a StatefulSet Pod template "
                "outside the requested network impairment"
            )
        if apply_resources:
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


def _wait_for_removed_ordinals(
    execute: Executor, *, removed_ordinals: tuple[int, ...]
) -> None:
    if not removed_ordinals:
        return
    resources = tuple(
        f"pod/hybrid-stage-{stage}-{ordinal}"
        for stage in range(1, 4)
        for ordinal in removed_ordinals
    )
    execute(
        _kubectl(
            "wait",
            "-n",
            HYBRID_NAMESPACE,
            "--for=delete",
            *resources,
            "--timeout=180s",
        ),
        False,
    )


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
    environment: Mapping[str, str] | None = None,
    remove_active_deadline: bool = False,
) -> None:
    if arguments is None and environment is None and not remove_active_deadline:
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
    if arguments is not None:
        containers[0]["args"] = list(arguments)
    if environment is not None:
        env = containers[0].setdefault("env", [])
        if not isinstance(env, list) or any(not isinstance(item, dict) for item in env):
            raise RuntimeError("Hybrid controller Job environment is invalid")
        by_name = {
            item.get("name"): item
            for item in env
            if isinstance(item.get("name"), str)
        }
        for name, value in environment.items():
            if not isinstance(name, str) or not name or not isinstance(value, str):
                raise RuntimeError("Hybrid controller environment override is invalid")
            item = by_name.get(name)
            if item is None:
                item = {"name": name}
                env.append(item)
                by_name[name] = item
            item.clear()
            item.update({"name": name, "value": value})
    if remove_active_deadline:
        spec.pop("activeDeadlineSeconds", None)
    with tempfile.TemporaryDirectory(
        prefix=".ibg-hybrid-phase75-job-", dir=ROOT / "deploy"
    ) as directory:
        manifest = Path(directory) / "controller-job.json"
        manifest.write_text(
            json.dumps(document, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        execute(_kubectl("apply", "-f", str(manifest)), False)


def _project_controller_log_output(
    output: str,
    *,
    emit: Callable[[str], None],
) -> str:
    """Show human lines and retain full machine evidence without displaying it."""

    evidence = []
    for line in output.splitlines():
        if line.startswith(HYBRID_SLOT_EVIDENCE_PREFIX):
            payload = line.removeprefix(HYBRID_SLOT_EVIDENCE_PREFIX)
        elif line.startswith("{"):
            # Backward-compatible ingestion for older controller images. Raw
            # evidence remains hidden from the human-facing console.
            payload = line
        else:
            emit(line)
            continue
        document = json.loads(payload)
        if not isinstance(document, dict):
            raise RuntimeError("Hybrid controller evidence line is not an object")
        evidence.append(
            json.dumps(document, sort_keys=True, separators=(",", ":"))
        )
    return "" if not evidence else "\n".join(evidence) + "\n"


def _persist_hybrid_experiment_trace(
    output: str,
    *,
    trace_dir: Path,
    requested_flows: int,
    requested_stages: int,
    requested_replicas: int,
    max_iterations: int,
    expected_experiment_seed: int | None = None,
    series_run_index: int = 1,
    series_run_count: int = 1,
    series_id: str | None = None,
    control_plane_footprint_enabled: bool = False,
    parity_replay_enabled: bool = False,
    network_impairment: HybridNetworkImpairment | None = None,
) -> Path:
    """Validate and persist completed-slot evidence as a host-side JSONL run."""

    if network_impairment is None:
        network_impairment = HybridNetworkImpairment.disabled()
    if not isinstance(network_impairment, HybridNetworkImpairment):
        raise RuntimeError("Hybrid network impairment setting is invalid")
    documents = []
    for line in output.splitlines():
        if not line.strip():
            continue
        document = json.loads(line)
        if not isinstance(document, dict):
            raise RuntimeError("Hybrid trace evidence line is not an object")
        if "network_impairment" in document:
            raise RuntimeError(
                "Hybrid controller evidence must not supply host impairment "
                "provenance"
            )
        documents.append(document)
    if not documents:
        raise RuntimeError("Hybrid production run emitted no slot evidence")
    if len(documents) > max_iterations:
        raise RuntimeError("Hybrid trace exceeds the configured iteration limit")
    if not 1 <= series_run_index <= series_run_count:
        raise RuntimeError("Hybrid trace has invalid series-run provenance")
    if not isinstance(control_plane_footprint_enabled, bool):
        raise RuntimeError("Hybrid control-plane footprint setting must be boolean")
    if not isinstance(parity_replay_enabled, bool):
        raise RuntimeError("Hybrid parity-replay setting must be boolean")

    expected_configuration = {
        "num_flows": requested_flows,
        "num_stages": requested_stages,
        "num_replicas": requested_replicas,
        "stage_budget": 2,
    }
    previous_slot = None
    for document in documents:
        if document.get("configuration") != expected_configuration:
            raise RuntimeError("Hybrid trace configuration is inconsistent")
        slot_id = document.get("slot_id")
        root_seed = document.get("root_seed")
        if expected_experiment_seed is not None and root_seed != (
            expected_experiment_seed
        ):
            raise RuntimeError("Hybrid trace experiment seed is inconsistent")
        if (
            isinstance(slot_id, bool)
            or not isinstance(slot_id, int)
            or slot_id < 1
            or (previous_slot is not None and slot_id != previous_slot + 1)
        ):
            raise RuntimeError("Hybrid trace slot identities are not contiguous")
        previous_slot = slot_id
        replay_performed = document.get("pure_kernel_replay_performed")
        if replay_performed is not parity_replay_enabled:
            raise RuntimeError(
                "Hybrid trace parity-replay provenance is inconsistent"
            )
        if parity_replay_enabled:
            if document.get("pure_kernel_replay_parity") is not True:
                raise RuntimeError("Hybrid trace parity replay did not pass")
        elif "pure_kernel_replay_parity" in document:
            raise RuntimeError(
                "Hybrid trace contains a disabled parity-replay result"
            )
        placements = document.get("placements")
        if not isinstance(placements, list) or len(placements) != requested_flows:
            raise RuntimeError("Hybrid trace has incomplete per-flow placements")
        flow_ids = set()
        for placement in placements:
            if not isinstance(placement, dict):
                raise RuntimeError("Hybrid trace placement is not an object")
            flow_id = placement.get("flow_id")
            measured_pair_ms = placement.get("measured_pair_ms")
            if (
                isinstance(flow_id, bool)
                or not isinstance(flow_id, int)
                or flow_id < 1
                or flow_id in flow_ids
                or isinstance(measured_pair_ms, bool)
                or not isinstance(measured_pair_ms, (int, float))
                or measured_pair_ms < 0
            ):
                raise RuntimeError(
                    "Hybrid trace has invalid per-flow measured-pair evidence"
                )
            flow_ids.add(flow_id)
        if flow_ids != set(range(1, requested_flows + 1)):
            raise RuntimeError("Hybrid trace does not cover every configured flow")
        observations = document.get("observations")
        if not isinstance(observations, list) or len(observations) != (
            2 * requested_flows
        ):
            raise RuntimeError("Hybrid trace has incomplete selected observations")
        metrics = document.get("metrics")
        violations = (
            metrics.get("end_to_end_sla_violations")
            if isinstance(metrics, dict)
            else None
        )
        excess_ms = (
            metrics.get("end_to_end_sla_excess_ms")
            if isinstance(metrics, dict)
            else None
        )
        threshold = (
            metrics.get("sla_latency_threshold_ms")
            if isinstance(metrics, dict)
            else None
        )
        raw_end_to_end = (
            metrics.get("raw_end_to_end_latency_ms_per_flow")
            if isinstance(metrics, dict)
            else None
        )
        if (
            not isinstance(metrics, dict)
            or not isinstance(metrics.get("equilibrium"), bool)
            or "physical_only_sla_violations" in metrics
            or isinstance(violations, bool)
            or not isinstance(violations, int)
            or violations < 0
            or isinstance(excess_ms, bool)
            or not isinstance(excess_ms, (int, float))
            or not isfinite(float(excess_ms))
            or excess_ms < 0
            or isinstance(threshold, bool)
            or not isinstance(threshold, (int, float))
            or float(threshold) != 80.0
            or not isinstance(raw_end_to_end, list)
            or len(raw_end_to_end) != requested_flows
        ):
            raise RuntimeError("Hybrid trace has invalid slot metrics")
        raw_by_flow = {}
        for pair in raw_end_to_end:
            if (
                not isinstance(pair, list)
                or len(pair) != 2
                or isinstance(pair[0], bool)
                or not isinstance(pair[0], int)
                or pair[0] < 1
                or pair[0] in raw_by_flow
                or isinstance(pair[1], bool)
                or not isinstance(pair[1], (int, float))
                or not isfinite(float(pair[1]))
                or pair[1] < 0
            ):
                raise RuntimeError("Hybrid trace has invalid slot metrics")
            raw_by_flow[pair[0]] = float(pair[1])
        expected_flow_ids = set(range(1, requested_flows + 1))
        if set(raw_by_flow) != expected_flow_ids:
            raise RuntimeError("Hybrid trace has invalid slot metrics")
        expected_violations = sum(
            raw_by_flow[flow_id] > float(threshold)
            for flow_id in sorted(raw_by_flow)
        )
        if violations != expected_violations:
            raise RuntimeError("Hybrid trace has invalid end-to-end SLA count")
        expected_excess_ms = sum(
            max(0.0, raw_by_flow[flow_id] - float(threshold))
            for flow_id in sorted(raw_by_flow)
        )
        if float(excess_ms) != expected_excess_ms:
            raise RuntimeError("Hybrid trace has invalid end-to-end SLA excess")
        control_plane = document.get("control_plane")
        if control_plane_footprint_enabled:
            if control_plane is None:
                raise RuntimeError(
                    "Hybrid trace lacks enabled control-plane footprint data"
                )
            try:
                validate_hybrid_control_plane_data_snapshot(control_plane)
            except ValueError as error:
                raise RuntimeError(
                    f"Hybrid trace has invalid control-plane footprint: {error}"
                ) from error
        elif "control_plane" in document:
            raise RuntimeError(
                "Hybrid trace contains disabled control-plane footprint data"
            )
    if (
        expected_experiment_seed is not None
        and documents[0]["slot_id"] != expected_experiment_seed
    ):
        raise RuntimeError("Hybrid trace first slot does not match its experiment seed")

    recorded_at = datetime.now(timezone.utc)
    timestamp = recorded_at.strftime("%Y%m%dT%H%M%S.%fZ")
    resolved_series_id = timestamp if series_id is None else series_id
    if not resolved_series_id or "/" in resolved_series_id:
        raise RuntimeError("Hybrid trace has invalid series identity")
    trace_dir.mkdir(parents=True, exist_ok=True)
    run_suffix = (
        ""
        if series_run_count == 1
        else f"-run{series_run_index:03d}"
    )
    trace_path = trace_dir / (
        f"ibg-hybrid-experiment-{resolved_series_id}{run_suffix}.jsonl"
    )
    started = {
        "event": "run_started",
        "trace_contract_version": HYBRID_TRACE_CONTRACT_VERSION,
        "recorded_at_utc": recorded_at.isoformat(),
        "configuration": expected_configuration,
        "max_iterations": max_iterations,
        "policy_mode": documents[0].get("policy_mode"),
        "mc_workers": documents[0].get("mc_workers"),
        "experiment_seed": documents[0].get("root_seed"),
        "series_run_index": series_run_index,
        "series_run_count": series_run_count,
        "series_id": resolved_series_id,
        "parity_replay_enabled": parity_replay_enabled,
    }
    completed_slots = [
        {
            **document,
            "event": "iteration_completed",
            "trace_contract_version": HYBRID_TRACE_CONTRACT_VERSION,
            "iteration": iteration,
            "parity_replay_enabled": parity_replay_enabled,
        }
        for iteration, document in enumerate(documents, start=1)
    ]
    last = documents[-1]
    completed = {
        "event": "run_completed",
        "trace_contract_version": HYBRID_TRACE_CONTRACT_VERSION,
        "iterations": len(documents),
        "first_slot_id": documents[0]["slot_id"],
        "last_slot_id": last["slot_id"],
        "reached_equilibrium": last["metrics"]["equilibrium"],
        "final_beliefs": last.get("beliefs_after"),
        "experiment_seed": last.get("root_seed"),
        "series_run_index": series_run_index,
        "series_run_count": series_run_count,
        "series_id": resolved_series_id,
        "parity_replay_enabled": parity_replay_enabled,
    }
    impairment_provenance = network_impairment.to_dict()
    events = [
        {**event, "network_impairment": impairment_provenance}
        for event in (started, *completed_slots, completed)
    ]
    try:
        validate_hybrid_network_impairment_events(
            events, expected=network_impairment
        )
    except ValueError as error:
        raise RuntimeError(
            f"Hybrid trace has invalid network-impairment provenance: {error}"
        ) from error
    with trace_path.open("x", encoding="utf-8") as trace:
        for event in events:
            trace.write(json.dumps(event, sort_keys=True, separators=(",", ":")))
            trace.write("\n")
        trace.flush()
    return trace_path


def _hybrid_csv_run_hash(run_started: Mapping[str, object]) -> str:
    configuration = run_started.get("configuration")
    if not isinstance(configuration, Mapping):
        raise ValueError("Hybrid CSV trace has no run configuration")
    required = ("num_flows", "num_stages", "num_replicas")
    if any(
        isinstance(configuration.get(name), bool)
        or not isinstance(configuration.get(name), int)
        or configuration[name] < 1
        for name in required
    ):
        raise ValueError("Hybrid CSV trace configuration is invalid")
    series_id = run_started.get("series_id")
    run_index = run_started.get("series_run_index")
    experiment_seed = run_started.get("experiment_seed")
    if (
        not isinstance(series_id, str)
        or not series_id
        or isinstance(run_index, bool)
        or not isinstance(run_index, int)
        or run_index < 1
        or isinstance(experiment_seed, bool)
        or not isinstance(experiment_seed, int)
        or experiment_seed < 1
    ):
        raise ValueError("Hybrid CSV trace run provenance is invalid")
    provenance = (
        f"{series_id}-run{run_index}-seed{experiment_seed}"
        f"-f{configuration['num_flows']}-s{configuration['num_stages']}"
        f"-r{configuration['num_replicas']}"
    )
    return hashlib.sha256(provenance.encode("utf-8")).hexdigest()[:6]


def _hybrid_csv_belief_snapshot(value: object) -> dict[tuple[int, int], list[float]]:
    if not isinstance(value, Mapping) or not value:
        raise ValueError("Hybrid CSV belief snapshot is missing or empty")
    snapshot = {}
    for raw_identity, raw_belief in value.items():
        if not isinstance(raw_identity, str) or raw_identity.count(":") != 1:
            raise ValueError("Hybrid CSV belief identity is invalid")
        try:
            identity = tuple(int(item) for item in raw_identity.split(":"))
        except ValueError as error:
            raise ValueError("Hybrid CSV belief identity is invalid") from error
        if any(item < 1 for item in identity) or identity in snapshot:
            raise ValueError("Hybrid CSV belief identity is invalid")
        if (
            not isinstance(raw_belief, list)
            or len(raw_belief) != 4
            or any(
                isinstance(probability, bool)
                or not isinstance(probability, (int, float))
                or not isfinite(float(probability))
                or probability < 0
                for probability in raw_belief
            )
        ):
            raise ValueError("Hybrid CSV belief vector is invalid")
        snapshot[identity] = [float(item) for item in raw_belief]
    return dict(sorted(snapshot.items()))


def _hybrid_footprint_csv_rows(
    iterations: Sequence[Mapping[str, object]],
) -> list[dict[str, dict[str, int | float]]] | None:
    present = ["control_plane" in event for event in iterations]
    if any(present) and not all(present):
        raise ValueError(
            "Hybrid CSV trace mixes enabled and disabled control-plane footprint"
        )
    if not any(present):
        return None

    rows = []
    for event in iterations:
        snapshot = event["control_plane"]
        validate_hybrid_control_plane_data_snapshot(snapshot)
        timing = dict(snapshot["timing_ms"])
        payload = dict(snapshot["payload_bytes"])
        messages = dict(snapshot["messages"])
        payload["belief_exchange_total"] = payload["belief_tx"] + payload["belief_rx"]
        messages["belief_exchange_total"] = (
            messages["belief_tx"] + messages["belief_rx"]
        )
        rows.append(
            {
                "timing_ms": timing,
                "payload_bytes": payload,
                "messages": messages,
            }
        )
    return rows


def export_hybrid_csv(
    trace_path: Path,
    output_dir: Path = HYBRID_CSV_OUTPUT_DIR,
) -> tuple[Path, ...]:
    """Export one completed Hybrid trace into the retained CSV layouts."""

    from IBG_Hybrid.csv_storage import append_metric_value, read_csv_table
    from IBG_Hybrid.header import create_belief_csv
    from IBG_Hybrid.report import (
        csv_gen_SLA,
        csv_gen_jain,
        csv_gen_time,
        csv_gen_util,
    )

    with trace_path.open(encoding="utf-8") as trace:
        events = [json.loads(line) for line in trace if line.strip()]
    started = [event for event in events if event.get("event") == "run_started"]
    iterations = [
        event for event in events if event.get("event") == "iteration_completed"
    ]
    completed = [event for event in events if event.get("event") == "run_completed"]
    if len(started) != 1 or not iterations or len(completed) != 1:
        raise ValueError("Hybrid CSV export requires one complete experiment trace")
    if any(
        event.get("trace_contract_version") != HYBRID_TRACE_CONTRACT_VERSION
        for event in events
    ):
        raise ValueError("Hybrid CSV export requires an active v3 experiment trace")
    if completed[0].get("iterations") != len(iterations):
        raise ValueError("Hybrid CSV trace completion count is inconsistent")

    metric_rows = []
    required_metrics = (
        "elapsed_seconds",
        "end_to_end_sla_violations",
        "end_to_end_sla_excess_ms",
        "raw_end_to_end_reference_utility",
        "jain_fairness",
    )
    for expected_iteration, event in enumerate(iterations, start=1):
        if event.get("iteration") != expected_iteration:
            raise ValueError("Hybrid CSV trace iterations are not contiguous")
        metrics = event.get("metrics")
        if not isinstance(metrics, Mapping) or any(
            name not in metrics for name in required_metrics
        ) or "physical_only_sla_violations" in metrics:
            raise ValueError("Hybrid CSV trace lacks required metrics")
        elapsed = metrics["elapsed_seconds"]
        violations = metrics["end_to_end_sla_violations"]
        excess_ms = metrics["end_to_end_sla_excess_ms"]
        end_to_end_utility = metrics["raw_end_to_end_reference_utility"]
        fairness = metrics["jain_fairness"]
        if (
            isinstance(elapsed, bool)
            or not isinstance(elapsed, (int, float))
            or not isfinite(float(elapsed))
            or elapsed < 0
            or isinstance(violations, bool)
            or not isinstance(violations, int)
            or violations < 0
            or isinstance(excess_ms, bool)
            or not isinstance(excess_ms, (int, float))
            or not isfinite(float(excess_ms))
            or excess_ms < 0
            or isinstance(end_to_end_utility, bool)
            or not isinstance(end_to_end_utility, (int, float))
            or not isfinite(float(end_to_end_utility))
            or isinstance(fairness, bool)
            or not isinstance(fairness, (int, float))
            or not isfinite(float(fairness))
            or not 0 <= fairness <= 1
        ):
            raise ValueError("Hybrid CSV trace contains an invalid metric value")
        metric_rows.append(
            (elapsed, violations, excess_ms, end_to_end_utility, fairness)
        )

    belief_snapshots = [
        _hybrid_csv_belief_snapshot(iterations[0].get("beliefs_before"))
    ] + [
        _hybrid_csv_belief_snapshot(event.get("beliefs_after"))
        for event in iterations
    ]
    expected_belief_identities = set(belief_snapshots[0])
    if any(set(snapshot) != expected_belief_identities for snapshot in belief_snapshots):
        raise ValueError("Hybrid CSV belief identities change within one run")
    footprint_rows = _hybrid_footprint_csv_rows(iterations)

    run_id = _hybrid_csv_run_hash(started[0])
    metric_paths = tuple(output_dir / name for name in HYBRID_CSV_FILENAMES[:4])
    for path in metric_paths:
        fieldnames, _rows = read_csv_table(path)
        if run_id in fieldnames:
            raise ValueError(f"Hybrid CSV run identifier already exists in {path}: {run_id}")
    belief_path = output_dir / HYBRID_CSV_FILENAMES[4]
    read_csv_table(belief_path)
    excess_path = output_dir / HYBRID_CSV_FILENAMES[5]
    excess_fieldnames, _excess_rows = read_csv_table(excess_path)
    if run_id in excess_fieldnames:
        raise ValueError(
            f"Hybrid CSV run identifier already exists in {excess_path}: {run_id}"
        )
    footprint_paths: tuple[Path, ...] = ()
    if footprint_rows is not None:
        footprint_dir = output_dir / "footprint"
        footprint_paths = tuple(
            footprint_dir / filename
            for filename, _section, _field in HYBRID_FOOTPRINT_CSV_FIELDS
        )
        for path in footprint_paths:
            fieldnames, _rows = read_csv_table(path)
            if run_id in fieldnames:
                raise ValueError(
                    f"Hybrid CSV run identifier already exists in {path}: {run_id}"
                )

    output_dir.mkdir(parents=True, exist_ok=True)
    for elapsed, violations, excess_ms, end_to_end_utility, fairness in metric_rows:
        csv_gen_time(elapsed, run_id, metric_paths[0], announce=False)
        csv_gen_SLA(violations, run_id, metric_paths[1], announce=False)
        csv_gen_util(
            end_to_end_utility, run_id, metric_paths[2], announce=False
        )
        csv_gen_jain(fairness, run_id, metric_paths[3], announce=False)
        append_metric_value(excess_path, run_id, float(excess_ms))
    for snapshot in belief_snapshots:
        create_belief_csv(snapshot, belief_path)
    if footprint_rows is not None:
        for row in footprint_rows:
            for path, (_filename, section, field) in zip(
                footprint_paths,
                HYBRID_FOOTPRINT_CSV_FIELDS,
                strict=True,
            ):
                append_metric_value(path, run_id, row[section][field])
    return (*metric_paths, belief_path, excess_path, *footprint_paths)


def _report_hybrid_csv(paths: Sequence[Path]) -> None:
    print(f"Hybrid CSV reports: {paths[0].parent}")
    for path in paths:
        print(f"  {path.name}")


def _stream_controller_job_logs(controller_job_name: str) -> str:
    """Stream completed-slot presentation while privately collecting evidence."""

    command = _kubectl(
        "logs",
        "-n",
        HYBRID_NAMESPACE,
        f"job/{controller_job_name}",
        "--container=controller",
        "--follow",
        "--pod-running-timeout=180s",
    )
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=1,
    )
    if process.stdout is None or process.stderr is None:
        process.kill()
        raise RuntimeError("unable to capture Hybrid controller logs")
    evidence = []
    for raw_line in process.stdout:
        projected = _project_controller_log_output(
            raw_line,
            emit=lambda line: print(line, flush=True),
        )
        if projected:
            evidence.extend(projected.splitlines())
    stderr = process.stderr.read()
    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError(
            "Hybrid controller log stream failed"
            + (f": {stderr.strip()}" if stderr.strip() else "")
        )
    return "" if not evidence else "\n".join(evidence) + "\n"


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
    stream_controller_logs: ControllerLogStreamer | None = None,
    production_experiment: bool = False,
    max_iterations: int | None = None,
    profile_seed: int | None = None,
    refresh_runtime_profiles: bool = False,
    policy_root_seed: int | None = None,
    first_slot_id: int | None = None,
    control_plane_footprint_enabled: bool = False,
    parity_replay_enabled: bool = False,
    network_impairment: HybridNetworkImpairment | None = None,
    execute: Executor = _execute,
) -> str:
    if network_impairment is None:
        network_impairment = HybridNetworkImpairment.disabled()
    if not isinstance(network_impairment, HybridNetworkImpairment):
        raise RuntimeError("Hybrid network impairment setting is invalid")
    if not isinstance(control_plane_footprint_enabled, bool):
        raise RuntimeError("Hybrid control-plane footprint setting must be boolean")
    if not isinstance(parity_replay_enabled, bool):
        raise RuntimeError("Hybrid parity-replay setting must be boolean")
    if parity_replay_enabled and not production_experiment:
        raise RuntimeError("parity replay belongs to the production run command")
    if production_experiment:
        if (
            isinstance(max_iterations, bool)
            or not isinstance(max_iterations, int)
            or max_iterations < 1
        ):
            raise RuntimeError("--max-iterations must be a positive integer")
    elif max_iterations is not None:
        raise RuntimeError("max iterations belong to the production run command")
    for value, field in (
        (policy_root_seed, "policy root seed"),
        (first_slot_id, "first slot ID"),
    ):
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < 1
        ):
            raise RuntimeError(f"{field} must be a positive integer")
    if not production_experiment and (
        policy_root_seed is not None or first_slot_id is not None
    ):
        raise RuntimeError(
            "random experiment seeds belong to the production run command"
        )
    if not production_experiment and (
        profile_seed is not None or refresh_runtime_profiles
    ):
        raise RuntimeError(
            "seeded runtime profiles belong to the production run command"
        )
    if refresh_runtime_profiles and not skip_build:
        raise RuntimeError(
            "--refresh-runtime-profiles requires --skip-build so only affected "
            "runtime Pods are replaced"
        )
    controller_arguments = _phase75_controller_arguments(
        controller_policy,
        mc_workers,
    )
    if production_experiment:
        print(
            "Hybrid Pure/Kernel parity replay: "
            + ("enabled" if parity_replay_enabled else "disabled")
        )
    boundary = _validate_static_profile_boundary(
        requested_replicas,
        requested_flows=requested_flows,
        requested_stages=requested_stages,
        profile_seed=profile_seed,
    )
    configuration = boundary.configuration
    resource_profile = None
    deployment_overlay = boundary.overlay
    controller_job = boundary.controller_job
    controller_job_name = boundary.controller_job_name
    replaced_job_names = boundary.replaced_job_names
    if processor_memory_profile is not None:
        if configuration != PHASE6_PROFILE_BOUNDARY.configuration or not skip_build:
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
        if controller_policy == "mc" and (
            configuration != PHASE6_PROFILE_BOUNDARY.configuration
            or not skip_build
            or resource_profile is None
            or resource_profile.name != "candidate"
        ):
            raise RuntimeError(
                "manual Kubernetes MC remains limited to --skip-build, "
                "the approved 3x3x2 topology, and the accepted candidate "
                "processor memory profile"
            )
        if controller_policy == "mc":
            deployment_overlay = PHASE75_OVERLAY
            controller_job = PHASE75_CONTROLLER_JOB
            controller_job_name = PHASE75_CONTROLLER_JOB_NAME
            replaced_job_names = (
                *PHASE6_PROFILE_BOUNDARY.replaced_job_names,
                "ibg-hybrid-controller-phase7",
                PHASE75_CONTROLLER_JOB_NAME,
                DYNAMIC_CONTROLLER_JOB_NAME,
            )
    replica_unit = "replica" if configuration.num_replicas == 1 else "replicas"
    print(
        "Selected Hybrid topology: "
        f"{configuration.num_flows} flows x {configuration.num_stages} stages "
        f"x {configuration.num_replicas} {replica_unit} per stage"
    )
    if profile_seed is not None:
        counts = seeded_profile_state_counts(
            replica_count=configuration.num_replicas,
            profile_seed=profile_seed,
        )
        state_names = {4: "Very Good", 3: "Good", 2: "Bad", 1: "Very Bad"}
        stage_counts = "; ".join(
            f"stage{stage}("
            + ", ".join(
                f"{state_names[state]}={counts[stage][state]}"
                for state in HYBRID_PROFILE_STATE_ORDER
            )
            + ")"
            for stage in range(1, 4)
        )
        print(
            "Hybrid runtime profile allocation: "
            f"version={HYBRID_PROFILE_STATE_ALLOCATION_VERSION}, "
            f"profile-seed={profile_seed}, per-stage={stage_counts}"
        )
    print(
        "Hybrid network impairment: "
        f"schema={network_impairment.to_dict()['schema']}, "
        f"enabled={str(network_impairment.enabled).lower()}, "
        f"interface={network_impairment.to_dict()['interface']}, "
        f"delay-ms={network_impairment.delay_ms:g}, "
        f"jitter-ms={network_impairment.jitter_ms:g}"
    )
    if skip_build:
        print(
            "Hybrid image mode: --skip-build; reuse validated node-local images"
        )
    else:
        print(
            "Hybrid image mode: build offline from validated local wheelhouses"
        )
        # Validate image inputs before even inspecting/creating a cluster. A
        # normal run must never build one image and discover later that another
        # required image cannot be reproduced offline.
        _validate_offline_wheelhouses()
        if network_impairment.enabled:
            # The Hybrid-owned init image is rebased offline from Exact's
            # already-local tc-capable runtime.  Fail before cluster creation.
            _require_local_image(execute, NETEM_BASE_IMAGE)
    plan_bounded_rollout(
        existing_count=requested_replicas,
        requested_count=requested_replicas,
        batch_size=rollout_batch_size,
    )
    cluster_exists = CLUSTER_NAME in _kind_clusters(execute)
    if refresh_runtime_profiles and not cluster_exists:
        raise RuntimeError(
            "--refresh-runtime-profiles requires an existing validated Hybrid cluster"
        )
    if skip_build and not cluster_exists:
        raise RuntimeError(
            "--skip-build requires the existing persistent ibg-hybrid cluster"
        )
    existing_count = None
    existing_templates = None
    existing_statefulsets = None
    bootstrap_namespace = False
    deliberate_resource_rollout = False
    deliberate_network_rollout = False
    rollout = None
    profile_transition = None
    if cluster_exists:
        preflight(execute=execute)
        namespace_names = _item_names(
            _json_output(
                execute,
                _kubectl("get", "namespaces", "-o", "json"),
            )
        )
        if HYBRID_NAMESPACE not in namespace_names:
            # A fail-closed post-create check may leave the dedicated cluster
            # healthy but pristine. Resume it through the normal namespace
            # bootstrap instead of requiring destructive recreation.
            bootstrap_namespace = True
        else:
            statefulsets = _statefulset_inventory(execute)
            existing = discover_existing_replica_state(statefulsets)
            existing_count = existing.replica_count
            deployed_network_impairment = _statefulset_network_impairment(
                statefulsets
            )
            deliberate_network_rollout = (
                deployed_network_impairment != network_impairment
            )
            existing_templates = _statefulset_template_snapshot(
                _without_network_impairment(statefulsets)
            )
            existing_statefulsets = statefulsets
            if resource_profile is not None:
                deliberate_resource_rollout = (
                    detect_resource_profile(statefulsets) != resource_profile
                )
            rollout = plan_bounded_rollout(
                existing_count=existing_count,
                requested_count=requested_replicas,
                batch_size=rollout_batch_size,
            )
            profile_transition = _validate_live_profile_expansion(
                execute,
                existing_replica_count=existing_count,
                boundary=boundary,
                refresh_runtime_profiles=refresh_runtime_profiles,
            )
            deployed_profile_replicas = (
                profile_transition.deployed_configuration.num_replicas
                if profile_transition is not None
                else existing_count
            )
            if deployed_profile_replicas > existing_count:
                print(
                    "Hybrid interrupted scale-down recovery: "
                    f"StatefulSets={existing_count}, "
                    f"deployed-profile-replicas={deployed_profile_replicas}; "
                    "reconciling the retained ordinal prefix"
                )
        if configuration.num_flows > 4 or configuration.num_replicas > 2:
            resource_preflight = _validate_node_resource_capacity(
                execute,
                existing_replica_count=existing_count or 0,
                requested_replica_count=requested_replicas,
            )
            print(
                "Hybrid resource preflight: "
                f"cpu={resource_preflight.requested_cpu_milli}m/"
                f"{resource_preflight.allocatable_cpu_milli}m, memory="
                f"{resource_preflight.requested_memory_bytes}/"
                f"{resource_preflight.allocatable_memory_bytes} bytes, "
                f"new-stage-pods={resource_preflight.added_stage_pods}"
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
        # kind's create --wait gate reports control-plane readiness.  The
        # dedicated worker may still be joining, while the Hybrid topology
        # preflight intentionally requires both nodes to be Ready.
        execute(
            _kubectl(
                "wait",
                "--for=condition=Ready",
                f"node/{CONTROL_PLANE_NODE_NAME}",
                f"node/{WORKER_NODE_NAME}",
                "--timeout=120s",
            ),
            False,
        )
        preflight(execute=execute)
        bootstrap_namespace = True
        if configuration.num_flows > 4 or configuration.num_replicas > 2:
            resource_preflight = _validate_node_resource_capacity(
                execute,
                existing_replica_count=0,
                requested_replica_count=requested_replicas,
            )
            print(
                "Hybrid resource preflight: "
                f"cpu={resource_preflight.requested_cpu_milli}m/"
                f"{resource_preflight.allocatable_cpu_milli}m, memory="
                f"{resource_preflight.requested_memory_bytes}/"
                f"{resource_preflight.allocatable_memory_bytes} bytes, "
                f"new-stage-pods={resource_preflight.added_stage_pods}"
            )

    scale_down = (
        existing_count is not None and requested_replicas < existing_count
    )
    profile_refresh = bool(
        profile_transition is not None
        and profile_transition.profile_refresh_required
    )
    if refresh_runtime_profiles and not profile_refresh:
        raise RuntimeError(
            "--refresh-runtime-profiles was supplied but the deployed profile "
            "already uses the requested allocation"
        )
    if profile_refresh and (
        existing_count != requested_replicas or deliberate_resource_rollout
    ):
        raise RuntimeError(
            "runtime-profile refresh requires an unchanged replica count and "
            "cannot be combined with a resource-template rollout"
        )
    if scale_down and deliberate_resource_rollout:
        raise RuntimeError(
            "intentional replica scale-down cannot be combined with a processor "
            "resource-template rollout"
        )

    before_processes = None
    if skip_build:
        validate_node_images(
            execute, network_impairment=network_impairment
        )
        before_processes = _serving_process_snapshot(
            _pod_inventory(execute), replica_count=existing_count
        )
    else:
        _build_images_offline(
            execute,
            wheelhouses_validated=True,
            network_impairment=network_impairment,
        )
        loaded_images = [SERVICE_IMAGE, CONTROLLER_IMAGE]
        if network_impairment.enabled:
            loaded_images.append(NETEM_IMAGE)
        execute(
            (
                "kind",
                "load",
                "docker-image",
                "--name",
                CLUSTER_NAME,
                *loaded_images,
            ),
            False,
        )
    if existing_count is None:
        initial_count = min(requested_replicas, rollout_batch_size)
        _apply_reconciled_boundary(
            execute,
            replica_count=initial_count,
            network_impairment=network_impairment,
            boundary=boundary,
            deployment_overlay=deployment_overlay,
            expected_templates=None,
            existing_statefulsets=None,
            processor_memory_profile=resource_profile,
            bootstrap_namespace=bootstrap_namespace,
        )
        existing_count = initial_count
    elif scale_down:
        # Validate the exact lower projection and unchanged Pod templates, but
        # keep the complete deployed ConfigMaps until the high-ordinal Pods are
        # gone.  Applying the reduced profiles first would create a restart race.
        _apply_reconciled_boundary(
            execute,
            replica_count=requested_replicas,
            network_impairment=network_impairment,
            boundary=boundary,
            deployment_overlay=deployment_overlay,
            expected_templates=existing_templates,
            existing_statefulsets=existing_statefulsets,
            processor_memory_profile=resource_profile,
            apply_resources=False,
        )
    else:
        _apply_reconciled_boundary(
            execute,
            replica_count=existing_count,
            network_impairment=network_impairment,
            boundary=boundary,
            deployment_overlay=deployment_overlay,
            expected_templates=existing_templates,
            existing_statefulsets=existing_statefulsets,
            processor_memory_profile=resource_profile,
        )

    if not scale_down:
        _validate_reconciled_profiles(execute, boundary=boundary)

    refreshed_processes = None
    if profile_refresh and not deliberate_network_rollout:
        changed_identities = profile_transition.changed_runtime_identities
        print(
            "Hybrid runtime profile refresh: affected serving Pods="
            + (
                ", ".join(_runtime_profile_refresh_pod_names(changed_identities))
                if changed_identities
                else "none"
            )
        )
        _refresh_runtime_profile_pods(
            execute,
            changed_identities=changed_identities,
            replica_count=requested_replicas,
        )
        refreshed_processes = _serving_process_snapshot(
            _pod_inventory(execute), replica_count=requested_replicas
        )
        if before_processes is not None:
            _validate_runtime_profile_refresh_processes(
                before_processes,
                refreshed_processes,
                changed_identities=changed_identities,
            )
    elif profile_refresh:
        print(
            "Hybrid runtime profile refresh: covered by the requested all-replica "
            "network-impairment rollout"
        )

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

    if rollout is None:
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
        _wait_for_removed_ordinals(
            execute, removed_ordinals=batch.removed_ordinals
        )
        _wait_for_target(execute, replica_count=batch.target_count)

    if scale_down:
        scaled_processes = _serving_process_snapshot(
            _pod_inventory(execute), replica_count=requested_replicas
        )
        if before_processes is not None:
            _validate_scale_down_process_preservation(
                before_processes,
                scaled_processes,
                existing_count=existing_count,
                requested_count=requested_replicas,
            )
        _apply_reconciled_boundary(
            execute,
            replica_count=requested_replicas,
            network_impairment=network_impairment,
            boundary=boundary,
            deployment_overlay=deployment_overlay,
            expected_templates=existing_templates,
            existing_statefulsets=existing_statefulsets,
            processor_memory_profile=resource_profile,
        )
        _validate_reconciled_profiles(execute, boundary=boundary)
        _wait_for_target(execute, replica_count=requested_replicas)

    deployed_network_impairment = _statefulset_network_impairment(
        _statefulset_inventory(execute)
    )
    if deployed_network_impairment != network_impairment:
        raise RuntimeError(
            "reconciled Hybrid StatefulSets do not match the requested network "
            "impairment"
        )

    preflight(execute=execute)
    if boundary.runtime_document is not None or controller_arguments is not None:
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
        environment=(
            {
                "HYBRID_CONTROLLER_LIFECYCLE": "experiment",
                "MAX_ITERATIONS": str(max_iterations),
                HYBRID_CONTROL_PLANE_DATA_ENV: (
                    "1" if control_plane_footprint_enabled else "0"
                ),
                HYBRID_PARITY_REPLAY_ENV: (
                    "1" if parity_replay_enabled else "0"
                ),
                **(
                    {}
                    if policy_root_seed is None
                    else {HYBRID_POLICY_ROOT_SEED_ENV: str(policy_root_seed)}
                ),
                **(
                    {}
                    if first_slot_id is None
                    else {"SLOT_ID": str(first_slot_id)}
                ),
            }
            if production_experiment
            else None
        ),
        # The positive iteration bound makes the production Job finite.  Do
        # not let a historical 600-second gate deadline truncate that bound.
        remove_active_deadline=production_experiment,
    )
    if controller_job_started is not None:
        controller_job_started()
    output = None
    if stream_controller_logs is not None:
        output = stream_controller_logs(controller_job_name)
    elif execute is _execute:
        output = _stream_controller_job_logs(controller_job_name)
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
    if output is None:
        output = _project_controller_log_output(
            execute(
                _kubectl(
                    "logs",
                    "-n",
                    HYBRID_NAMESPACE,
                    f"job/{controller_job_name}",
                ),
                True,
            ),
            emit=lambda line: print(line, flush=True),
        )
    if before_processes is not None:
        after_processes = _serving_process_snapshot(
            _pod_inventory(execute), replica_count=requested_replicas
        )
        if deliberate_network_rollout:
            _validate_network_impairment_rollout(
                before_processes,
                after_processes,
                requested_count=requested_replicas,
            )
        elif scale_down:
            _validate_scale_down_process_preservation(
                before_processes,
                after_processes,
                existing_count=existing_count,
                requested_count=requested_replicas,
            )
        elif profile_refresh:
            _validate_runtime_profile_refresh_processes(
                before_processes,
                after_processes,
                changed_identities=profile_transition.changed_runtime_identities,
            )
        elif deliberate_resource_rollout:
            _validate_deliberate_processor_rollout(
                before_processes, after_processes
            )
        else:
            _validate_process_preservation(before_processes, after_processes)
    return output


def run_experiment(
    *,
    skip_build: bool = False,
    requested_flows: int,
    requested_stages: int,
    requested_replicas: int,
    rollout_batch_size: int = 1,
    max_iterations: int,
    profile_seed: int | None = None,
    refresh_runtime_profiles: bool = False,
    processor_memory_profile: str | None = None,
    controller_policy: str | None = None,
    mc_workers: int | None = None,
    policy_root_seed: int | None = None,
    first_slot_id: int | None = None,
    control_plane_footprint_enabled: bool = False,
    parity_replay_enabled: bool = False,
    network_impairment: HybridNetworkImpairment | None = None,
    before_controller_job: RunHook | None = None,
    controller_job_started: RunHook | None = None,
    after_controller_job: RunHook | None = None,
    stream_controller_logs: ControllerLogStreamer | None = None,
    execute: Executor = _execute,
) -> str:
    """Run the normal equilibrium-aware lifecycle through the shared launcher."""

    if (
        isinstance(max_iterations, bool)
        or not isinstance(max_iterations, int)
        or max_iterations < 1
    ):
        raise RuntimeError("--max-iterations must be a positive integer")
    return run_small(
        skip_build=skip_build,
        requested_flows=requested_flows,
        requested_stages=requested_stages,
        requested_replicas=requested_replicas,
        rollout_batch_size=rollout_batch_size,
        processor_memory_profile=processor_memory_profile,
        controller_policy=controller_policy,
        mc_workers=mc_workers,
        before_controller_job=before_controller_job,
        controller_job_started=controller_job_started,
        after_controller_job=after_controller_job,
        stream_controller_logs=stream_controller_logs,
        production_experiment=True,
        max_iterations=max_iterations,
        profile_seed=profile_seed,
        refresh_runtime_profiles=refresh_runtime_profiles,
        policy_root_seed=policy_root_seed,
        first_slot_id=first_slot_id,
        control_plane_footprint_enabled=control_plane_footprint_enabled,
        parity_replay_enabled=parity_replay_enabled,
        network_impairment=network_impairment,
        execute=execute,
    )


def _random_positive_seed(*, excluded: set[int] | None = None) -> int:
    blocked = set() if excluded is None else excluded
    while True:
        value = secrets.randbits(HYBRID_RANDOM_SERIES_SEED_BITS)
        if value > 0 and value not in blocked:
            return value


def _resolve_random_series_profile_seed(execute: Executor) -> int:
    """Reuse an existing seeded environment or create one random fresh seed."""

    if CLUSTER_NAME not in _kind_clusters(execute):
        return _random_positive_seed()
    preflight(execute=execute)
    namespaces = _item_names(
        _json_output(execute, _kubectl("get", "namespaces", "-o", "json"))
    )
    if HYBRID_NAMESPACE not in namespaces:
        return _random_positive_seed()
    runtime, _controller = _deployed_profile_documents(execute)
    source_identity = runtime.get("source_identity")
    if not isinstance(source_identity, str) or not source_identity:
        raise RuntimeError("Hybrid runtime profile has no source identity")
    profile_seed = profile_seed_from_runtime_source_identity(source_identity)
    if profile_seed is None:
        raise RuntimeError(
            "--runs requires an existing seeded Hybrid environment or a fresh "
            "cluster"
        )
    return profile_seed


def run_experiment_series(
    *,
    runs: int,
    trace_dir: Path,
    skip_build: bool,
    requested_flows: int,
    requested_stages: int,
    requested_replicas: int,
    rollout_batch_size: int,
    max_iterations: int,
    processor_memory_profile: str | None = None,
    controller_policy: str | None = None,
    mc_workers: int | None = None,
    csv_enabled: bool = False,
    parity_replay_enabled: bool = False,
    network_impairment: HybridNetworkImpairment | None = None,
    csv_output_dir: Path = HYBRID_CSV_OUTPUT_DIR,
    execute: Executor = _execute,
    stream_controller_logs: ControllerLogStreamer | None = None,
) -> tuple[Path, ...]:
    """Run independent random-seed Jobs in one fixed runtime environment."""

    if network_impairment is None:
        network_impairment = HybridNetworkImpairment.disabled()
    if not isinstance(network_impairment, HybridNetworkImpairment):
        raise RuntimeError("Hybrid network impairment setting is invalid")
    if isinstance(runs, bool) or not isinstance(runs, int) or runs < 1:
        raise RuntimeError("--runs must be a positive integer")
    profile_seed = _resolve_random_series_profile_seed(execute)
    experiment_seeds = []
    used_seeds: set[int] = set()
    for _index in range(runs):
        seed = _random_positive_seed(excluded=used_seeds)
        used_seeds.add(seed)
        experiment_seeds.append(seed)
    print(
        "Hybrid random series: "
        f"runs={runs}, fixed-profile-seed={profile_seed}, "
        "experiment-seeds=automatic-system-random"
    )

    trace_paths = []
    series_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    for run_index, experiment_seed in enumerate(experiment_seeds, start=1):
        print(
            f"Hybrid experiment run {run_index}/{runs}: "
            f"experiment-seed={experiment_seed}"
        )
        output = run_experiment(
            skip_build=skip_build if run_index == 1 else True,
            requested_flows=requested_flows,
            requested_stages=requested_stages,
            requested_replicas=requested_replicas,
            rollout_batch_size=rollout_batch_size,
            max_iterations=max_iterations,
            profile_seed=profile_seed,
            refresh_runtime_profiles=False,
            processor_memory_profile=processor_memory_profile,
            controller_policy=controller_policy,
            mc_workers=mc_workers,
            policy_root_seed=experiment_seed,
            first_slot_id=experiment_seed,
            control_plane_footprint_enabled=csv_enabled,
            parity_replay_enabled=parity_replay_enabled,
            network_impairment=network_impairment,
            stream_controller_logs=stream_controller_logs,
            execute=execute,
        )
        trace_path = _persist_hybrid_experiment_trace(
            output,
            trace_dir=trace_dir,
            requested_flows=requested_flows,
            requested_stages=requested_stages,
            requested_replicas=requested_replicas,
            max_iterations=max_iterations,
            expected_experiment_seed=experiment_seed,
            series_run_index=run_index,
            series_run_count=runs,
            series_id=series_id,
            control_plane_footprint_enabled=csv_enabled,
            parity_replay_enabled=parity_replay_enabled,
            network_impairment=network_impairment,
        )
        trace_paths.append(trace_path)
        print(f"Detailed Hybrid JSONL trace: {trace_path}")
        if csv_enabled:
            _report_hybrid_csv(export_hybrid_csv(trace_path, csv_output_dir))
    return tuple(trace_paths)


def cleanup(*, execute: Executor = _execute) -> None:
    if CLUSTER_NAME in _kind_clusters(execute):
        execute(("kind", "delete", "cluster", "--name", CLUSTER_NAME), False)


def _positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def _nonnegative_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be a nonnegative integer")
    return parsed


def _nonnegative_finite_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "value must be a finite nonnegative number"
        ) from error
    if not isfinite(parsed) or parsed < 0:
        raise argparse.ArgumentTypeError(
            "value must be a finite nonnegative number"
        )
    return parsed


def network_impairment_from_args(
    args: argparse.Namespace,
) -> HybridNetworkImpairment:
    enabled = getattr(args, "netem", 0)
    delay_ms = getattr(args, "netem_delay_ms", None)
    jitter_ms = getattr(args, "netem_jitter_ms", None)
    if isinstance(enabled, bool) or enabled not in (0, 1):
        raise ValueError("--netem must be 0 or 1")
    if enabled == 0:
        if delay_ms is not None or jitter_ms is not None:
            raise ValueError(
                "--netem-delay-ms and --netem-jitter-ms require --netem 1"
            )
        return HybridNetworkImpairment.disabled()
    return HybridNetworkImpairment.enabled_with(
        delay_ms=10.0 if delay_ms is None else delay_ms,
        jitter_ms=3.0 if jitter_ms is None else jitter_ms,
    )


def _add_run_arguments(
    parser: argparse.ArgumentParser,
    *,
    production: bool,
) -> None:
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help=(
            "reuse matching node-local Hybrid images without building, "
            "loading, or restarting serving workloads"
        ),
    )
    parser.add_argument(
        "--flow",
        "--flows",
        dest="requested_flows",
        type=_positive_integer,
        required=production,
        default=None,
        help=(
            "positive logical-flow count"
            if production
            else "positive logical-flow count; omitted only for the historical "
            "one- or two-replica defaults"
        ),
    )
    parser.add_argument(
        "--stage",
        "--stages",
        dest="requested_stages",
        type=_positive_integer,
        required=production,
        default=None,
        help="stage count; the frozen Hybrid model requires exactly three",
    )
    parser.add_argument(
        "--replica",
        "--replicas",
        dest="requested_replicas",
        type=_positive_integer,
        required=production,
        default=None if production else 1,
        help="explicit final replica count for each of the three stages",
    )
    parser.add_argument(
        "--rollout-batch-size",
        type=_positive_integer,
        default=1,
        help="maximum missing ordinals added to every stage per Ready gate",
    )
    parser.add_argument(
        "--processor-memory-profile",
        choices=tuple(PROCESSOR_MEMORY_PROFILES),
        default=None,
        help=(
            "historical Phase 7 resource profile; ordinary production "
            "lookahead uses the currently reconciled resource boundary"
        ),
    )
    parser.add_argument(
        "--policy",
        choices=("lookahead", "mc"),
        default=None,
        help=(
            "select the controller policy; omission retains deterministic "
            "lookahead and MC remains explicitly restricted"
        ),
    )
    parser.add_argument(
        "--mc-workers",
        type=int,
        default=None,
        help="explicit bounded controller workers for --policy mc",
    )
    if production:
        parser.add_argument(
            "--profile-seed",
            type=_nonnegative_integer,
            required=False,
            help=(
                "single-run nonnegative hidden-state profile seed; omitted and "
                "forbidden when --runs generates/reuses a fixed environment"
            ),
        )
        parser.add_argument(
            "--runs",
            type=_positive_integer,
            default=None,
            help=(
                "run N independent Jobs with automatic unique system-random "
                "experiment seeds and one fixed environment"
            ),
        )
        parser.add_argument(
            "--refresh-runtime-profiles",
            action="store_true",
            help=(
                "explicitly confirm controlled replacement of Pods whose true "
                "runtime state changes"
            ),
        )
        parser.add_argument(
            "--max-iterations",
            type=_positive_integer,
            required=True,
            help="positive slot limit when equilibrium is not reached earlier",
        )
        parser.add_argument(
            "--trace-dir",
            type=Path,
            default=DEFAULT_HYBRID_TRACE_DIR,
            help="host directory for the detailed Hybrid JSONL trace",
        )
        parser.add_argument(
            "--csv",
            type=int,
            choices=(0, 1),
            default=0,
            help=(
                "write time, SLA, raw end-to-end utility, Jain fairness, and "
                "replica-belief CSV reports plus controller payload/message "
                f"footprint CSVs under {HYBRID_CSV_OUTPUT_DIR} "
                "(1=enabled, 0=disabled)"
            ),
        )
        parser.add_argument(
            "--parity-replay",
            type=int,
            choices=(0, 1),
            default=0,
            help=(
                "recompute each completed scheduling decision serially and "
                "require Pure/Kernel equality (1=enabled, 0=disabled)"
            ),
        )
        parser.add_argument(
            "--netem",
            type=int,
            choices=(0, 1),
            default=0,
            help=(
                "apply opt-in tc/netem delay and jitter to replica-Pod eth0 "
                "egress (1=enabled, 0=disabled)"
            ),
        )
        parser.add_argument(
            "--netem-delay-ms",
            type=_nonnegative_finite_float,
            default=None,
            help=(
                "base replica-Pod egress delay in milliseconds; requires "
                "--netem 1 (default when enabled: 10)"
            ),
        )
        parser.add_argument(
            "--netem-jitter-ms",
            type=_nonnegative_finite_float,
            default=None,
            help=(
                "normal replica-Pod egress jitter in milliseconds; requires "
                "--netem 1 (default when enabled: 3)"
            ),
        )


def parse_args(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Operate only the persistent two-node Hybrid kind cluster; "
            "never starts or targets the shared ibg cluster."
        )
    )
    subparsers = parser.add_subparsers(dest="action", required=True)
    production_parser = subparsers.add_parser(
        "run",
        help="run sequential slots until equilibrium or the explicit limit",
    )
    _add_run_arguments(production_parser, production=True)
    validation_parser = subparsers.add_parser(
        "run-small",
        help="run the historical bounded infrastructure validation gate",
    )
    _add_run_arguments(validation_parser, production=False)
    subparsers.add_parser("preflight")
    subparsers.add_parser("cleanup")
    parsed = parser.parse_args(arguments)
    if parsed.action == "run":
        if parsed.runs is None and parsed.profile_seed is None:
            parser.error("single run requires --profile-seed; use --runs N for automatic seeds")
        if parsed.runs is not None and parsed.profile_seed is not None:
            parser.error("--runs generates seeds automatically; do not pass --profile-seed")
        if parsed.runs is not None and parsed.refresh_runtime_profiles:
            parser.error("--runs cannot be combined with --refresh-runtime-profiles")
        try:
            parsed.network_impairment = network_impairment_from_args(parsed)
        except ValueError as error:
            parser.error(str(error))
    return parsed


def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_args(arguments)
    try:
        if args.action == "run":
            if args.runs is not None:
                run_experiment_series(
                    runs=args.runs,
                    trace_dir=args.trace_dir,
                    skip_build=args.skip_build,
                    requested_flows=args.requested_flows,
                    requested_stages=args.requested_stages,
                    requested_replicas=args.requested_replicas,
                    rollout_batch_size=args.rollout_batch_size,
                    max_iterations=args.max_iterations,
                    processor_memory_profile=args.processor_memory_profile,
                    controller_policy=args.policy,
                    mc_workers=args.mc_workers,
                    csv_enabled=bool(args.csv),
                    parity_replay_enabled=bool(args.parity_replay),
                    network_impairment=args.network_impairment,
                )
            else:
                output = run_experiment(
                    skip_build=args.skip_build,
                    requested_flows=args.requested_flows,
                    requested_stages=args.requested_stages,
                    requested_replicas=args.requested_replicas,
                    rollout_batch_size=args.rollout_batch_size,
                    max_iterations=args.max_iterations,
                    profile_seed=args.profile_seed,
                    refresh_runtime_profiles=args.refresh_runtime_profiles,
                    processor_memory_profile=args.processor_memory_profile,
                    controller_policy=args.policy,
                    mc_workers=args.mc_workers,
                    control_plane_footprint_enabled=bool(args.csv),
                    parity_replay_enabled=bool(args.parity_replay),
                    network_impairment=args.network_impairment,
                )
                trace_path = _persist_hybrid_experiment_trace(
                    output,
                    trace_dir=args.trace_dir,
                    requested_flows=args.requested_flows,
                    requested_stages=args.requested_stages,
                    requested_replicas=args.requested_replicas,
                    max_iterations=args.max_iterations,
                    control_plane_footprint_enabled=bool(args.csv),
                    parity_replay_enabled=bool(args.parity_replay),
                    network_impairment=args.network_impairment,
                )
                print(f"Detailed Hybrid JSONL trace: {trace_path}")
                if args.csv == 1:
                    _report_hybrid_csv(export_hybrid_csv(trace_path))
        elif args.action == "run-small":
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
