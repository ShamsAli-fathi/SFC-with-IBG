"""Fail-closed persistent lifecycle for the isolated Greedy kind cluster.

All command execution is injected.  Importing this module is silent and
side-effect free; tests use fake executors and never invoke Docker, kind, or
kubectl.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
from hashlib import blake2b
import json
from numbers import Integral
from pathlib import Path
import secrets
import subprocess
import tarfile
import tempfile
import time
from typing import Callable, Mapping, Sequence

from .contracts import GreedyConfiguration, ReplicaIdentity
from .kernel_infrastructure import (
    GREEDY_CONTROLLER_IMAGE,
    GREEDY_CONTROLLER_INPUT_CONFIG_MAP,
    GREEDY_CONTROLLER_JOB,
    GREEDY_FLOW_GENERATOR,
    GREEDY_NAMESPACE,
    GREEDY_PART_OF,
    GREEDY_RUNTIME_PROFILE_CONFIG_MAP,
    GREEDY_SERVICE_ACCOUNT,
    GREEDY_DISCOVERY_ROLE,
    GREEDY_SERVICE_IMAGE,
    GREEDY_WORKLOAD_NODE_LABEL,
    GreedyServingReadiness,
    GreedyStaticDeploymentInput,
    GreedyWorkerAllocatable,
    render_controller_job,
    render_long_running_resources,
    render_resource_documents,
    require_worker_resources,
)
from .kernel_controller_config import controller_input_document_from_mapping
from .kernel_profile_reconciliation import (
    GreedyProfileReconciliationError,
    materialize_runtime_profiles,
    validate_profile_transition,
)
from .kernel_rollout import (
    GreedyExistingTopology,
    GreedyKernelRolloutError,
    discover_existing_topology,
    plan_replica_batches,
    validate_interrupted_transition_shape,
    validate_ready_coverage,
)
from .kernel_runtime_profiles import (
    GreedyKernelRuntimeProfileDocument,
    runtime_profile_document_from_mapping,
)


GREEDY_LAUNCH_VERSION = "greedy-kernel-launch-v2"
GREEDY_LAUNCHER_STATE_VERSION = "greedy-kernel-launcher-state-v1"
GREEDY_CLUSTER_NAME = "greedy"
GREEDY_CONTEXT = "kind-greedy"
GREEDY_CONTROL_PLANE_NODE = "greedy-control-plane"
GREEDY_WORKER_NODE = "greedy-worker"
GREEDY_LAUNCHER_STATE_CONFIG_MAP = "greedy-launcher-state"
GREEDY_KIND_NODE_IMAGE = (
    "kindest/node:v1.36.1@"
    "sha256:3489c7674813ba5d8b1a9977baea8a6e553784dab7b84759d1014dbd78f7ebd5"
)
GREEDY_PYTHON_BASE_IMAGE = "mcr.microsoft.com/azurelinux/base/python:3.12"
GREEDY_NORMALIZED_SERVICE_IMAGE = (
    "docker.io/library/greedy-testbed:kernel-service-v1"
)
GREEDY_NORMALIZED_CONTROLLER_IMAGE = (
    "docker.io/library/greedy-testbed:kernel-controller-v1"
)
GREEDY_SYSTEM_NAMESPACES = frozenset(
    {
        "default",
        "kube-system",
        "kube-public",
        "kube-node-lease",
        "local-path-storage",
    }
)
GREEDY_FORBIDDEN_BASELINE_NAMESPACES = frozenset(
    {"ibg-testbed", "ibg-hybrid-testbed", "milp-testbed"}
)
GREEDY_ROLLOUT_STALL_TIMEOUT_SECONDS = 120.0
GREEDY_ROLLOUT_POLL_SECONDS = 1.0
GREEDY_SERVICE_IMAGE_ID_ANNOTATION = (
    "greedy.sfc-with-ibg/service-image-id"
)
GREEDY_SERVICE_SOURCE_FINGERPRINT_ANNOTATION = (
    "greedy.sfc-with-ibg/service-source-fingerprint"
)
GREEDY_LEGACY_CAPACITY_LABEL = "greedy.max-assigned-flows"


ROOT = Path(__file__).resolve().parents[1]
GREEDY_DEPLOYMENT_ROOT = ROOT / "deploy" / "greedy-kubernetes"
GREEDY_KIND_CONFIG = GREEDY_DEPLOYMENT_ROOT / "kind-config.yaml"
GREEDY_SERVICE_DOCKERFILE = GREEDY_DEPLOYMENT_ROOT / "Dockerfile.service"
GREEDY_CONTROLLER_DOCKERFILE = GREEDY_DEPLOYMENT_ROOT / "Dockerfile.controller"

Command = tuple[str, ...]
Executor = Callable[[Command, bool], str]
WheelhouseValidator = Callable[[Sequence[str]], object]
RootSeedSource = Callable[[int], int]
ProgressEmitter = Callable[[str], None]


class GreedyLifecycleError(RuntimeError):
    """The dedicated lifecycle cannot prove a safe next action."""


def _integer(name: str, value: int, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise TypeError(f"{name} must be an integer")
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return int(value)


@dataclass(frozen=True)
class GreedyLaunchConfiguration:
    """Validated one-run host inputs for lifecycle and host-side reporting."""

    configuration: GreedyConfiguration
    max_iterations: int
    profile_seed: int
    root_seed: int
    rollout_batch_size: int = 1
    skip_build: bool = False
    csv: int = 0
    parity_replay: int = 0
    experiment_id: int = 1
    first_slot_id: int = 1
    contract_version: str = GREEDY_LAUNCH_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.configuration, GreedyConfiguration):
            raise TypeError("configuration must be GreedyConfiguration")
        for name, minimum in (
            ("max_iterations", 1),
            ("profile_seed", 0),
            ("root_seed", 0),
            ("rollout_batch_size", 1),
            ("experiment_id", 1),
            ("first_slot_id", 1),
        ):
            object.__setattr__(
                self, name, _integer(name, getattr(self, name), minimum=minimum)
            )
        if not isinstance(self.skip_build, bool):
            raise TypeError("skip_build must be boolean")
        for name in ("csv", "parity_replay"):
            value = getattr(self, name)
            if isinstance(value, bool) or value not in (0, 1):
                raise ValueError(f"{name} must be 0 or 1")
        if self.contract_version != GREEDY_LAUNCH_VERSION:
            raise ValueError("unexpected Greedy launch version")

    @property
    def runtime_profiles(self) -> GreedyKernelRuntimeProfileDocument:
        return materialize_runtime_profiles(
            self.configuration,
            profile_seed=self.profile_seed,
        )

    @property
    def deployment(self) -> GreedyStaticDeploymentInput:
        shape = self.configuration
        return GreedyStaticDeploymentInput(
            runtime_profiles=self.runtime_profiles,
            experiment_id=self.experiment_id,
            root_seed=self.root_seed,
            profile_seed=self.profile_seed,
            max_iterations=self.max_iterations,
            first_slot_id=self.first_slot_id,
            source_identity=(
                f"{GREEDY_LAUNCH_VERSION}:"
                f"{shape.num_flows}x{shape.num_stages}x{shape.num_replicas}"
            ),
            parity_replay_enabled=bool(self.parity_replay),
            control_plane_footprint_enabled=bool(self.csv),
        )


def resolve_root_seed(
    source: RootSeedSource = secrets.randbits,
) -> int:
    """Resolve one positive 63-bit experiment seed independently of profiles."""

    for _attempt in range(128):
        value = source(63)
        if isinstance(value, bool) or not isinstance(value, Integral):
            raise GreedyLifecycleError("root-seed source returned a non-integer")
        if 0 < value < 2**63:
            return int(value)
    raise GreedyLifecycleError("root-seed source did not return a positive seed")


def _configuration_mapping(configuration: GreedyConfiguration) -> dict[str, int]:
    return {
        "num_flows": configuration.num_flows,
        "num_stages": configuration.num_stages,
        "num_replicas": configuration.num_replicas,
    }


def _configuration_from_mapping(value: object, field: str) -> GreedyConfiguration:
    if not isinstance(value, Mapping) or set(value) != {
        "num_flows",
        "num_stages",
        "num_replicas",
    }:
        raise GreedyLifecycleError(f"{field} is incomplete or malformed")
    try:
        return GreedyConfiguration(
            value["num_flows"], value["num_stages"], value["num_replicas"]
        )
    except (TypeError, ValueError) as error:
        raise GreedyLifecycleError(f"{field} is invalid: {error}") from error


@dataclass(frozen=True)
class GreedyLauncherState:
    stable_configuration: GreedyConfiguration
    target_configuration: GreedyConfiguration
    profile_seed: int
    profile_fingerprint: str
    service_source_fingerprint: str
    controller_source_fingerprint: str
    service_image_id: str
    controller_image_id: str
    transition_active: bool
    service_restart_required: bool = False
    contract_version: str = GREEDY_LAUNCHER_STATE_VERSION

    def __post_init__(self) -> None:
        for name in ("stable_configuration", "target_configuration"):
            if not isinstance(getattr(self, name), GreedyConfiguration):
                raise TypeError(f"{name} must be GreedyConfiguration")
        object.__setattr__(
            self,
            "profile_seed",
            _integer("profile_seed", self.profile_seed, minimum=0),
        )
        for name in (
            "profile_fingerprint",
            "service_source_fingerprint",
            "controller_source_fingerprint",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise GreedyLifecycleError(f"{name} must be nonempty")
        for name in ("service_image_id", "controller_image_id"):
            _image_id("sha256:" + getattr(self, name), name)
        if not isinstance(self.transition_active, bool) or not isinstance(
            self.service_restart_required, bool
        ):
            raise TypeError("launcher transition flags must be boolean")
        if not self.transition_active and (
            self.stable_configuration != self.target_configuration
            or self.service_restart_required
        ):
            raise GreedyLifecycleError("stable launcher state is internally inconsistent")
        if self.contract_version != GREEDY_LAUNCHER_STATE_VERSION:
            raise GreedyLifecycleError("unexpected Greedy launcher-state version")


def launcher_state_to_mapping(state: GreedyLauncherState) -> dict[str, object]:
    return {
        "contract_version": state.contract_version,
        "stable_configuration": _configuration_mapping(state.stable_configuration),
        "target_configuration": _configuration_mapping(state.target_configuration),
        "profile_seed": state.profile_seed,
        "profile_fingerprint": state.profile_fingerprint,
        "service_source_fingerprint": state.service_source_fingerprint,
        "controller_source_fingerprint": state.controller_source_fingerprint,
        "service_image_id": state.service_image_id,
        "controller_image_id": state.controller_image_id,
        "transition_active": state.transition_active,
        "service_restart_required": state.service_restart_required,
    }


def launcher_state_from_mapping(value: Mapping[str, object]) -> GreedyLauncherState:
    required = {
        "contract_version",
        "stable_configuration",
        "target_configuration",
        "profile_seed",
        "profile_fingerprint",
        "service_source_fingerprint",
        "controller_source_fingerprint",
        "service_image_id",
        "controller_image_id",
        "transition_active",
        "service_restart_required",
    }
    if not isinstance(value, Mapping) or set(value) != required:
        raise GreedyLifecycleError("launcher state fields are incomplete or unexpected")
    try:
        return GreedyLauncherState(
            stable_configuration=_configuration_from_mapping(
                value["stable_configuration"], "stable configuration"
            ),
            target_configuration=_configuration_from_mapping(
                value["target_configuration"], "target configuration"
            ),
            profile_seed=value["profile_seed"],
            profile_fingerprint=value["profile_fingerprint"],
            service_source_fingerprint=value["service_source_fingerprint"],
            controller_source_fingerprint=value["controller_source_fingerprint"],
            service_image_id=value["service_image_id"],
            controller_image_id=value["controller_image_id"],
            transition_active=value["transition_active"],
            service_restart_required=value["service_restart_required"],
            contract_version=value["contract_version"],
        )
    except (TypeError, ValueError) as error:
        if isinstance(error, GreedyLifecycleError):
            raise
        raise GreedyLifecycleError(f"invalid launcher state: {error}") from error


@dataclass(frozen=True, order=True)
class GreedyServingProcessSnapshot:
    pod_name: str
    pod_uid: str
    container_restarts: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class GreedyLifecycleResult:
    configuration: GreedyConfiguration
    profile_fingerprint: str
    root_seed: int
    cluster_created: bool
    built_images: tuple[str, ...]
    loaded_images: tuple[str, ...]
    serving_changed: bool
    controller_jobs_created: int
    service_source_fingerprint: str
    controller_source_fingerprint: str
    service_image_id: str
    controller_image_id: str
    worker_allocatable_cpu_millicores: int
    worker_allocatable_memory_mib: int


def _execute(command: Command, capture_output: bool = False) -> str:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=capture_output,
    )
    return completed.stdout if capture_output else ""


def _kubectl(*arguments: str) -> Command:
    return ("kubectl", "--context", GREEDY_CONTEXT, *arguments)


def _json_output(execute: Executor, command: Command) -> Mapping[str, object]:
    try:
        value = json.loads(execute(command, True))
    except json.JSONDecodeError as error:
        raise GreedyLifecycleError(
            f"command returned malformed JSON: {' '.join(command)}"
        ) from error
    if not isinstance(value, Mapping):
        raise GreedyLifecycleError(
            f"command did not return an object: {' '.join(command)}"
        )
    return value


def _items(document: Mapping[str, object], field: str) -> tuple[Mapping[str, object], ...]:
    values = document.get("items")
    if not isinstance(values, list) or not all(isinstance(item, Mapping) for item in values):
        raise GreedyLifecycleError(f"{field} must contain an object item list")
    return tuple(values)


def _name(item: Mapping[str, object], field: str) -> str:
    metadata = item.get("metadata")
    value = metadata.get("name") if isinstance(metadata, Mapping) else None
    if not isinstance(value, str) or not value:
        raise GreedyLifecycleError(f"{field} has no name")
    return value


def _kind_clusters(execute: Executor) -> frozenset[str]:
    return frozenset(
        line.strip()
        for line in execute(("kind", "get", "clusters"), True).splitlines()
        if line.strip()
    )


def _node_ready(item: Mapping[str, object]) -> bool:
    status = item.get("status")
    conditions = status.get("conditions") if isinstance(status, Mapping) else None
    return isinstance(conditions, list) and any(
        isinstance(condition, Mapping)
        and condition.get("type") == "Ready"
        and condition.get("status") == "True"
        for condition in conditions
    )


def _node_items(nodes: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    result = {}
    for item in _items(nodes, "node inventory"):
        name = _name(item, "node")
        if name in result:
            raise GreedyLifecycleError("node inventory has duplicate identities")
        result[name] = item
    return result


def validate_context_identity(document: Mapping[str, object]) -> None:
    contexts = document.get("contexts")
    current = document.get("current-context")
    clusters = document.get("clusters")
    if (
        current != GREEDY_CONTEXT
        or not isinstance(contexts, list)
        or len(contexts) != 1
        or not isinstance(clusters, list)
        or len(clusters) != 1
    ):
        raise GreedyLifecycleError("kubectl context is not the dedicated Greedy context")
    context = contexts[0]
    cluster = clusters[0]
    context_value = context.get("context") if isinstance(context, Mapping) else None
    if (
        not isinstance(context, Mapping)
        or context.get("name") != GREEDY_CONTEXT
        or not isinstance(context_value, Mapping)
        or context_value.get("cluster") != GREEDY_CONTEXT
        or not isinstance(cluster, Mapping)
        or cluster.get("name") != GREEDY_CONTEXT
    ):
        raise GreedyLifecycleError("kubectl context/cluster identity is inconsistent")


def validate_node_topology(
    nodes: Mapping[str, object],
) -> Mapping[str, Mapping[str, object]]:
    by_name = _node_items(nodes)
    expected = {GREEDY_CONTROL_PLANE_NODE, GREEDY_WORKER_NODE}
    if set(by_name) != expected:
        raise GreedyLifecycleError(
            "refusing non-dedicated Greedy nodes: "
            f"expected={sorted(expected)}, got={sorted(by_name)}"
        )
    control_metadata = by_name[GREEDY_CONTROL_PLANE_NODE].get("metadata")
    worker_metadata = by_name[GREEDY_WORKER_NODE].get("metadata")
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
    control_role = "node-role.kubernetes.io/control-plane"
    if (
        not isinstance(control_labels, Mapping)
        or control_role not in control_labels
        or GREEDY_WORKLOAD_NODE_LABEL in control_labels
        or not isinstance(worker_labels, Mapping)
        or worker_labels.get(GREEDY_WORKLOAD_NODE_LABEL) != "true"
        or control_role in worker_labels
        or not _node_ready(by_name[GREEDY_CONTROL_PLANE_NODE])
        or not _node_ready(by_name[GREEDY_WORKER_NODE])
    ):
        raise GreedyLifecycleError(
            "Greedy node roles, worker-only label, or Ready state are invalid"
        )
    return by_name


def _pod_node(item: Mapping[str, object]) -> str | None:
    spec = item.get("spec")
    node = spec.get("nodeName") if isinstance(spec, Mapping) else None
    return node if isinstance(node, str) and node else None


def validate_cluster_inventory(
    *,
    nodes: Mapping[str, object],
    namespaces: Mapping[str, object],
    pods: Mapping[str, object],
) -> None:
    validate_node_topology(nodes)
    namespace_items = _items(namespaces, "namespace inventory")
    namespace_names = {_name(item, "namespace") for item in namespace_items}
    forbidden = namespace_names & GREEDY_FORBIDDEN_BASELINE_NAMESPACES
    if forbidden:
        raise GreedyLifecycleError(
            "refusing cluster with foreign baseline namespaces: "
            + ", ".join(sorted(forbidden))
        )
    foreign_namespaces = namespace_names - GREEDY_SYSTEM_NAMESPACES - {GREEDY_NAMESPACE}
    if foreign_namespaces:
        raise GreedyLifecycleError(
            "refusing cluster with foreign namespaces: "
            + ", ".join(sorted(foreign_namespaces))
        )
    greedy_namespace = [
        item for item in namespace_items if _name(item, "namespace") == GREEDY_NAMESPACE
    ]
    if greedy_namespace:
        metadata = greedy_namespace[0].get("metadata")
        labels = metadata.get("labels") if isinstance(metadata, Mapping) else None
        if not isinstance(labels, Mapping) or labels.get(
            "app.kubernetes.io/part-of"
        ) != GREEDY_PART_OF:
            raise GreedyLifecycleError("Greedy namespace ownership label is invalid")

    foreign = []
    misplaced = []
    for item in _items(pods, "Pod inventory"):
        metadata = item.get("metadata")
        if not isinstance(metadata, Mapping):
            raise GreedyLifecycleError("Pod metadata is invalid")
        namespace = metadata.get("namespace")
        name = metadata.get("name")
        if namespace in GREEDY_SYSTEM_NAMESPACES:
            continue
        if namespace != GREEDY_NAMESPACE or not isinstance(name, str):
            foreign.append(f"{namespace}/{name}")
            continue
        labels = metadata.get("labels")
        if not isinstance(labels, Mapping) or labels.get(
            "app.kubernetes.io/part-of"
        ) != GREEDY_PART_OF:
            foreign.append(f"{namespace}/{name}")
            continue
        valid_name = name.startswith(
            ("greedy-stage-", "greedy-flow-generator-", "greedy-controller-")
        )
        if not valid_name:
            foreign.append(f"{namespace}/{name}")
        elif _pod_node(item) != GREEDY_WORKER_NODE:
            misplaced.append(f"{namespace}/{name}")
    if foreign:
        raise GreedyLifecycleError(
            "refusing cluster with foreign workload Pods: "
            + ", ".join(sorted(foreign))
        )
    if misplaced:
        raise GreedyLifecycleError(
            "refusing Greedy workloads outside the dedicated worker: "
            + ", ".join(sorted(misplaced))
        )


def validate_owned_resource_inventory(document: Mapping[str, object]) -> None:
    """Reject any non-system object in the namespace outside Greedy ownership."""

    allowed_exact = {
        ("Service", GREEDY_FLOW_GENERATOR),
        ("Deployment", GREEDY_FLOW_GENERATOR),
        ("Job", GREEDY_CONTROLLER_JOB),
        ("ConfigMap", GREEDY_RUNTIME_PROFILE_CONFIG_MAP),
        ("ConfigMap", GREEDY_CONTROLLER_INPUT_CONFIG_MAP),
        ("ConfigMap", GREEDY_LAUNCHER_STATE_CONFIG_MAP),
        ("ServiceAccount", GREEDY_SERVICE_ACCOUNT),
        ("Role", GREEDY_DISCOVERY_ROLE),
        ("RoleBinding", "greedy-controller-discovers-replicas"),
    }
    system_exact = {
        ("ConfigMap", "kube-root-ca.crt"),
        ("ServiceAccount", "default"),
    }
    stage_services = set()
    stage_sets = set()
    jobs = 0
    for item in _items(document, "owned resource inventory"):
        kind = item.get("kind")
        name = _name(item, "owned resource")
        metadata = item.get("metadata")
        if not isinstance(kind, str) or not isinstance(metadata, Mapping):
            raise GreedyLifecycleError("owned resource entry is malformed")
        identity = (kind, name)
        if identity in system_exact:
            continue
        stage_match = None
        if kind in {"Service", "StatefulSet"} and name.startswith("greedy-stage-"):
            suffix = name.removeprefix("greedy-stage-")
            if suffix.isdecimal() and int(suffix) >= 1:
                stage_match = int(suffix)
        if identity not in allowed_exact and stage_match is None:
            raise GreedyLifecycleError(
                f"foreign or unexpected Greedy namespace resource: {kind}/{name}"
            )
        labels = metadata.get("labels")
        if (
            metadata.get("namespace") != GREEDY_NAMESPACE
            or not isinstance(labels, Mapping)
            or labels.get("app.kubernetes.io/part-of") != GREEDY_PART_OF
        ):
            raise GreedyLifecycleError(
                f"Greedy resource ownership labels are invalid: {kind}/{name}"
            )
        if kind == "Service" and stage_match is not None:
            stage_services.add(stage_match)
        elif kind == "StatefulSet" and stage_match is not None:
            stage_sets.add(stage_match)
        elif kind == "Job":
            jobs += 1
    if stage_services != stage_sets:
        raise GreedyLifecycleError(
            "Greedy stage Service/StatefulSet ownership coverage is inconsistent"
        )
    if stage_sets and stage_sets != set(range(1, len(stage_sets) + 1)):
        raise GreedyLifecycleError("Greedy owned stage resources are noncontiguous")
    if jobs > 1:
        raise GreedyLifecycleError("more than one Greedy controller Job is present")


def _owned_resource_inventory(execute: Executor) -> Mapping[str, object]:
    return _json_output(
        execute,
        _kubectl(
            "get",
            "services,deployments,statefulsets,jobs,configmaps,serviceaccounts,roles,rolebindings",
            "-n",
            GREEDY_NAMESPACE,
            "-o",
            "json",
        ),
    )


def preflight(*, execute: Executor = _execute) -> None:
    if GREEDY_CLUSTER_NAME not in _kind_clusters(execute):
        raise GreedyLifecycleError("the dedicated Greedy cluster does not exist")
    validate_context_identity(
        _json_output(
            execute,
            (
                "kubectl",
                "config",
                "view",
                "--context",
                GREEDY_CONTEXT,
                "--minify",
                "-o",
                "json",
            ),
        )
    )
    namespaces = _json_output(
        execute, _kubectl("get", "namespaces", "-o", "json")
    )
    validate_cluster_inventory(
        nodes=_json_output(execute, _kubectl("get", "nodes", "-o", "json")),
        namespaces=namespaces,
        pods=_json_output(execute, _kubectl("get", "pods", "-A", "-o", "json")),
    )
    if GREEDY_NAMESPACE in _namespace_names(namespaces):
        validate_owned_resource_inventory(_owned_resource_inventory(execute))


def _cpu_millicores(value: object) -> int:
    if not isinstance(value, str) or not value:
        raise GreedyLifecycleError("worker CPU quantity is malformed")
    try:
        amount = (
            Decimal(value[:-1]) if value.endswith("m") else Decimal(value) * 1000
        )
    except InvalidOperation as error:
        raise GreedyLifecycleError("worker CPU quantity is malformed") from error
    if amount < 0 or amount != amount.to_integral_value():
        raise GreedyLifecycleError("worker CPU quantity is unsupported")
    return int(amount)


def _memory_mib(value: object) -> int:
    if not isinstance(value, str) or not value:
        raise GreedyLifecycleError("worker memory quantity is malformed")
    suffixes = {"Ki": Decimal(1) / 1024, "Mi": Decimal(1), "Gi": Decimal(1024)}
    for suffix, multiplier in suffixes.items():
        if value.endswith(suffix):
            try:
                amount = Decimal(value[: -len(suffix)]) * multiplier
            except InvalidOperation as error:
                raise GreedyLifecycleError("worker memory quantity is malformed") from error
            if amount < 0:
                raise GreedyLifecycleError("worker memory quantity is unsupported")
            # Kubernetes commonly reports node allocatable memory in Ki with
            # a remainder smaller than one MiB.  The public lifecycle contract
            # stores whole MiB, so round down rather than overstating capacity.
            return int(amount.to_integral_value(rounding=ROUND_FLOOR))
    raise GreedyLifecycleError("worker memory quantity must use Ki, Mi, or Gi")


def worker_resource_preflight(
    configuration: GreedyConfiguration,
    nodes: Mapping[str, object],
) -> GreedyWorkerAllocatable:
    worker = validate_node_topology(nodes)[GREEDY_WORKER_NODE]
    status = worker.get("status")
    allocatable = status.get("allocatable") if isinstance(status, Mapping) else None
    if not isinstance(allocatable, Mapping):
        raise GreedyLifecycleError("Greedy worker has no allocatable inventory")
    try:
        parsed = GreedyWorkerAllocatable(
            cpu_millicores=_cpu_millicores(allocatable.get("cpu")),
            memory_mib=_memory_mib(allocatable.get("memory")),
        )
        require_worker_resources(
            configuration,
            parsed,
        )
        return parsed
    except (TypeError, ValueError) as error:
        raise GreedyLifecycleError(f"Greedy worker resource preflight failed: {error}") from error


SERVICE_SOURCE_FILES = (
    "deploy/greedy-kubernetes/Dockerfile.service",
    "deploy/greedy-kubernetes/requirements-service.txt",
    "deploy/greedy-kubernetes/wheel-manifests/requirements-service.lock",
    "deploy/greedy-kubernetes/wheel-manifests/service.json",
    "deploy/greedy-kubernetes/service-package-init.py",
    "IBG/datapath.py",
    "IBG/latency_model.py",
    "testbed/__init__.py",
    "testbed/profiles.py",
    "testbed/cnf_service.py",
    "testbed/route_forwarder.py",
    "Greedy/contracts.py",
    "Greedy/slot_contracts.py",
    "Greedy/kernel_contracts.py",
    "Greedy/kernel_runtime_profiles.py",
    "Greedy/kernel_route_contracts.py",
    "Greedy/kernel_route_execution.py",
    "Greedy/kernel_route_forwarder.py",
    "Greedy/kernel_processor_service.py",
    "Greedy/kernel_route_forwarder_service.py",
    "Greedy/kernel_flow_generator.py",
)
CONTROLLER_SOURCE_FILES = (
    "deploy/greedy-kubernetes/Dockerfile.controller",
    "deploy/greedy-kubernetes/requirements-controller.txt",
    "deploy/greedy-kubernetes/wheel-manifests/requirements-controller.lock",
    "deploy/greedy-kubernetes/wheel-manifests/controller.json",
    "deploy/greedy-kubernetes/controller-exact-report.py",
    "deploy/greedy-kubernetes/controller-package-init.py",
    "IBG/datapath.py",
    "IBG/latency_model.py",
    "IBG/learning.py",
    "Greedy/contracts.py",
    "Greedy/expected_utility.py",
    "Greedy/phase0_contract.py",
    "Greedy/policy.py",
    "Greedy/slot_contracts.py",
    "Greedy/simulation.py",
    "Greedy/learning.py",
    "Greedy/metrics.py",
    "Greedy/kernel_contracts.py",
    "Greedy/kernel_route_contracts.py",
    "Greedy/kernel_kubernetes_discovery.py",
    "Greedy/kernel_controller_config.py",
    "Greedy/kernel_controller.py",
    "Greedy/kernel_controller_service.py",
    "Greedy/console_output.py",
    "Greedy/control_plane_footprint.py",
    "Greedy/runtime_resources.py",
    "Greedy/evidence_replay.py",
    "Greedy/evidence.py",
)


def source_fingerprint(paths: Sequence[str], *, root: Path = ROOT) -> str:
    resolved = tuple(paths)
    if not resolved or len(set(resolved)) != len(resolved):
        raise GreedyLifecycleError("image source inventory is empty or duplicated")
    # Phase 6 trace provenance stores full 256-bit source fingerprints.  Keep
    # the lifecycle producer identical to that validated persistence schema.
    digest = blake2b(digest_size=32)
    for relative in sorted(resolved):
        path = root / relative
        if not path.is_file():
            raise GreedyLifecycleError(f"image source is missing: {relative}")
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def image_source_fingerprints(*, root: Path = ROOT) -> dict[str, str]:
    return {
        "service": source_fingerprint(SERVICE_SOURCE_FILES, root=root),
        "controller": source_fingerprint(CONTROLLER_SOURCE_FILES, root=root),
    }


def _image_id(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise GreedyLifecycleError(f"{field} has no full sha256 image ID")
    stripped = value.strip()
    if not stripped.startswith("sha256:"):
        raise GreedyLifecycleError(f"{field} has no full sha256 image ID")
    digest = stripped.removeprefix("sha256:")
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise GreedyLifecycleError(f"{field} has an invalid sha256 image ID")
    return digest


def _local_image_id(execute: Executor, image: str) -> str:
    # Keep the explicit local-tag existence check, then resolve the selected
    # linux/amd64 OCI config digest.  Docker's image ID and the ID exposed by
    # containerd/crictl after ``kind load`` are not interchangeable on current
    # Docker versions.
    _image_id(
        execute(
            ("docker", "image", "inspect", "--format", "{{.Id}}", image), True
        ),
        f"local image {image}",
    )
    with tempfile.TemporaryDirectory(prefix="greedy-image-inspect-") as directory:
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
        try:
            with tarfile.open(archive_path, mode="r") as archive:
                return _linux_amd64_config_id(archive)
        except (tarfile.TarError, OSError, json.JSONDecodeError) as error:
            raise GreedyLifecycleError(
                f"local image archive is invalid for {image}"
            ) from error


def _archive_json(
    archive: tarfile.TarFile,
    member_name: str,
) -> Mapping[str, object]:
    member = archive.extractfile(member_name)
    if member is None:
        raise GreedyLifecycleError(f"local image archive lacks {member_name}")
    payload = json.loads(member.read())
    if not isinstance(payload, dict):
        raise GreedyLifecycleError(
            f"local image archive member is invalid: {member_name}"
        )
    return payload


def _descriptor_document(
    archive: tarfile.TarFile,
    descriptor: Mapping[str, object],
) -> Mapping[str, object]:
    digest = _image_id(descriptor.get("digest"), "OCI descriptor")
    return _archive_json(archive, f"blobs/sha256/{digest}")


def _linux_amd64_config_id(archive: tarfile.TarFile) -> str:
    index = _archive_json(archive, "index.json")
    manifests = index.get("manifests")
    if not isinstance(manifests, list) or len(manifests) != 1:
        raise GreedyLifecycleError(
            "local image archive has ambiguous top-level manifests"
        )
    descriptor = manifests[0]
    if not isinstance(descriptor, dict):
        raise GreedyLifecycleError(
            "local image archive has an invalid top-level descriptor"
        )
    document = _descriptor_document(archive, descriptor)
    while "config" not in document:
        candidates = document.get("manifests")
        if not isinstance(candidates, list):
            raise GreedyLifecycleError("local image archive has no platform manifest")
        selected = []
        for candidate in candidates:
            if not isinstance(candidate, dict):
                raise GreedyLifecycleError("local image archive has an invalid manifest")
            platform = candidate.get("platform")
            if isinstance(platform, dict) and (
                platform.get("os"), platform.get("architecture")
            ) == ("linux", "amd64"):
                selected.append(candidate)
        if len(selected) != 1:
            raise GreedyLifecycleError(
                "local image archive must contain exactly one linux/amd64 manifest"
            )
        document = _descriptor_document(archive, selected[0])
    config = document.get("config")
    if not isinstance(config, dict):
        raise GreedyLifecycleError(
            "local linux/amd64 manifest has no config descriptor"
        )
    return _image_id(config.get("digest"), "local linux/amd64 image config")


def _build_images(
    execute: Executor,
    images: Sequence[str],
) -> tuple[str, ...]:
    dockerfiles = {
        "service": (GREEDY_SERVICE_DOCKERFILE, GREEDY_SERVICE_IMAGE),
        "controller": (GREEDY_CONTROLLER_DOCKERFILE, GREEDY_CONTROLLER_IMAGE),
    }
    built = []
    for name in images:
        if name not in dockerfiles:
            raise GreedyLifecycleError(f"unknown Greedy image role: {name}")
        dockerfile, image = dockerfiles[name]
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
        built.append(name)
    return tuple(built)


def _load_images(execute: Executor, roles: Sequence[str]) -> tuple[str, ...]:
    images = {
        "service": GREEDY_SERVICE_IMAGE,
        "controller": GREEDY_CONTROLLER_IMAGE,
    }
    selected = tuple(images[role] for role in roles)
    if selected:
        execute(
            (
                "kind",
                "load",
                "docker-image",
                "--name",
                GREEDY_CLUSTER_NAME,
                *selected,
            ),
            False,
        )
    return tuple(roles)


def validate_node_images(
    execute: Executor,
    *,
    service_image_id: str,
    controller_image_id: str,
) -> None:
    expected_nodes = {GREEDY_CONTROL_PLANE_NODE, GREEDY_WORKER_NODE}
    actual_nodes = {
        line.strip()
        for line in execute(
            ("kind", "get", "nodes", "--name", GREEDY_CLUSTER_NAME), True
        ).splitlines()
        if line.strip()
    }
    if actual_nodes != expected_nodes:
        raise GreedyLifecycleError("node-image validation has ambiguous cluster nodes")
    expected = {
        GREEDY_NORMALIZED_SERVICE_IMAGE: service_image_id,
        GREEDY_NORMALIZED_CONTROLLER_IMAGE: controller_image_id,
    }
    for node in sorted(actual_nodes):
        inventory = _json_output(
            execute,
            ("docker", "exec", node, "crictl", "images", "-o", "json"),
        )
        images = inventory.get("images")
        if not isinstance(images, list):
            raise GreedyLifecycleError(f"node image inventory is invalid for {node}")
        found = {tag: set() for tag in expected}
        for item in images:
            if not isinstance(item, Mapping):
                raise GreedyLifecycleError(f"node image entry is invalid for {node}")
            tags = item.get("repoTags")
            if not isinstance(tags, list):
                continue
            for tag in set(tags) & set(expected):
                found[tag].add(_image_id(item.get("id"), f"node image on {node}"))
        for tag, identity in expected.items():
            if found[tag] != {identity}:
                raise GreedyLifecycleError(
                    "Greedy node image is absent or mismatched: "
                    f"node={node}, tag={tag}, expected={identity}, "
                    f"found={sorted(found[tag])}"
                )


def _apply_documents(execute: Executor, resources: Sequence[Mapping[str, object]]) -> None:
    documents = tuple(resources)
    if not documents:
        return
    with tempfile.TemporaryDirectory(prefix="greedy-phase5-") as directory:
        manifest = Path(directory) / "resources.json.yaml"
        manifest.write_text(render_resource_documents(documents), encoding="utf-8")
        execute(_kubectl("apply", "-f", str(manifest)), False)


def _service_rollout_resources(
    resources: Sequence[Mapping[str, object]],
    *,
    service_source_fingerprint: str,
    service_image_id: str,
) -> tuple[dict[str, object], ...]:
    """Return canonical resources carrying public service-rollout provenance.

    The annotation binds a Pod-template revision to the exact source and OCI
    config identities already persisted in launcher state.  It replaces the
    old unprovable ``rollout restart`` side effect and also removes the retired
    v1 flow-capacity label without mutating caller-owned resources.
    """

    if (
        not isinstance(service_source_fingerprint, str)
        or len(service_source_fingerprint) != 64
        or any(
            character not in "0123456789abcdef"
            for character in service_source_fingerprint
        )
    ):
        raise GreedyLifecycleError("service source fingerprint is invalid")
    _image_id("sha256:" + service_image_id, "service rollout image ID")
    prepared = tuple(deepcopy(tuple(resources)))
    for resource in prepared:
        metadata = resource.get("metadata")
        if isinstance(metadata, dict):
            labels = metadata.get("labels")
            if isinstance(labels, dict):
                labels.pop(GREEDY_LEGACY_CAPACITY_LABEL, None)
        kind = resource.get("kind")
        name = metadata.get("name") if isinstance(metadata, Mapping) else None
        if kind != "StatefulSet" and not (
            kind == "Deployment" and name == GREEDY_FLOW_GENERATOR
        ):
            continue
        spec = resource.get("spec")
        template = spec.get("template") if isinstance(spec, Mapping) else None
        template_metadata = (
            template.get("metadata") if isinstance(template, Mapping) else None
        )
        if not isinstance(template_metadata, dict):
            raise GreedyLifecycleError(
                f"canonical serving template is malformed: {kind}/{name}"
            )
        labels = template_metadata.get("labels")
        if not isinstance(labels, dict):
            raise GreedyLifecycleError(
                f"canonical serving template labels are malformed: {kind}/{name}"
            )
        labels.pop(GREEDY_LEGACY_CAPACITY_LABEL, None)
        annotations = template_metadata.setdefault("annotations", {})
        if not isinstance(annotations, dict):
            raise GreedyLifecycleError(
                f"canonical serving template annotations are malformed: {kind}/{name}"
            )
        annotations[GREEDY_SERVICE_IMAGE_ID_ANNOTATION] = service_image_id
        annotations[GREEDY_SERVICE_SOURCE_FINGERPRINT_ANNOTATION] = (
            service_source_fingerprint
        )
    return prepared


def _launcher_state_resource(state: GreedyLauncherState) -> dict[str, object]:
    return {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": GREEDY_LAUNCHER_STATE_CONFIG_MAP,
            "namespace": GREEDY_NAMESPACE,
            "labels": {
                "app.kubernetes.io/name": GREEDY_LAUNCHER_STATE_CONFIG_MAP,
                "app.kubernetes.io/part-of": GREEDY_PART_OF,
                "app.kubernetes.io/component": "launcher-state",
            },
        },
        "data": {
            "launcher-state.json": json.dumps(
                launcher_state_to_mapping(state), sort_keys=True, separators=(",", ":")
            )
        },
    }


def _configmap_documents(
    resources: Sequence[Mapping[str, object]],
) -> tuple[Mapping[str, object], ...]:
    names = {GREEDY_RUNTIME_PROFILE_CONFIG_MAP, GREEDY_CONTROLLER_INPUT_CONFIG_MAP}
    selected = tuple(
        resource
        for resource in resources
        if resource.get("kind") == "ConfigMap"
        and isinstance(resource.get("metadata"), Mapping)
        and resource["metadata"].get("name") in names
    )
    if len(selected) != 2:
        raise GreedyLifecycleError("canonical Greedy ConfigMaps are incomplete")
    return selected


def _deployment_resource(
    resources: Sequence[Mapping[str, object]], name: str
) -> Mapping[str, object]:
    selected = [
        resource
        for resource in resources
        if resource.get("kind") == "Deployment"
        and isinstance(resource.get("metadata"), Mapping)
        and resource["metadata"].get("name") == name
    ]
    if len(selected) != 1:
        raise GreedyLifecycleError(f"canonical Deployment {name} is incomplete")
    return selected[0]


def _serving_workload_inventory(execute: Executor) -> Mapping[str, object]:
    return _json_output(
        execute,
        _kubectl(
            "get",
            "statefulsets,deployments",
            "-n",
            GREEDY_NAMESPACE,
            "-o",
            "json",
        ),
    )


def _retained_serving_documents(
    resources: Sequence[Mapping[str, object]],
    replica_counts: Sequence[int],
) -> tuple[Mapping[str, object], ...]:
    """Select canonical retained serving resources at their observed widths."""

    counts = tuple(replica_counts)
    if len(counts) < 2 or any(
        isinstance(count, bool) or not isinstance(count, Integral) or count < 1
        for count in counts
    ):
        raise GreedyLifecycleError("retained serving replica counts are invalid")
    selected: list[Mapping[str, object]] = []
    expected = {
        ("Service", GREEDY_FLOW_GENERATOR),
        ("Deployment", GREEDY_FLOW_GENERATOR),
    } | {
        (kind, f"greedy-stage-{stage}")
        for stage in range(1, len(counts) + 1)
        for kind in ("Service", "StatefulSet")
    }
    found: set[tuple[str, str]] = set()
    for original in resources:
        metadata = original.get("metadata")
        kind = original.get("kind")
        name = metadata.get("name") if isinstance(metadata, Mapping) else None
        identity = (kind, name)
        if identity not in expected:
            continue
        if identity in found:
            raise GreedyLifecycleError(
                f"canonical retained serving resource is duplicated: {kind}/{name}"
            )
        found.add(identity)
        resource = deepcopy(original)
        if kind == "StatefulSet":
            stage = int(str(name).removeprefix("greedy-stage-"))
            resource["spec"]["replicas"] = counts[stage - 1]
        selected.append(resource)
    if found != expected:
        raise GreedyLifecycleError("canonical retained serving resources are incomplete")
    return tuple(selected)


def _nonnegative_rollout_count(
    status: Mapping[str, object], field: str, resource_name: str
) -> int:
    value = status.get(field, 0)
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 0:
        raise GreedyLifecycleError(
            f"rollout resource {resource_name} has invalid {field}"
        )
    return int(value)


def _rollout_resource_complete(
    item: Mapping[str, object], *, desired: int, statefulset: bool
) -> bool:
    metadata = item.get("metadata")
    spec = item.get("spec")
    status = item.get("status")
    if not all(isinstance(value, Mapping) for value in (metadata, spec, status)):
        raise GreedyLifecycleError("rollout resource is incomplete")
    name = metadata.get("name")
    generation = metadata.get("generation")
    observed = status.get("observedGeneration", 0)
    if (
        not isinstance(name, str)
        or isinstance(generation, bool)
        or not isinstance(generation, Integral)
        or generation < 1
        or isinstance(observed, bool)
        or not isinstance(observed, Integral)
        or observed < 0
    ):
        raise GreedyLifecycleError("rollout resource generation is invalid")
    revision_converged = True
    if statefulset:
        current_revision = status.get("currentRevision")
        update_revision = status.get("updateRevision")
        revision_converged = (
            isinstance(current_revision, str)
            and bool(current_revision)
            and current_revision == update_revision
        )
    return (
        spec.get("replicas") == desired
        and observed >= generation
        and _nonnegative_rollout_count(status, "updatedReplicas", name) == desired
        and _nonnegative_rollout_count(status, "readyReplicas", name) == desired
        and _nonnegative_rollout_count(status, "availableReplicas", name) == desired
        and revision_converged
    )


def _classify_service_rollout(
    document: Mapping[str, object],
    *,
    replica_counts: Sequence[int],
    service_source_fingerprint: str,
    service_image_id: str,
    rebuild_pending: bool = False,
) -> str:
    """Classify one exact target rollout as update-required/progressing/converged.

    Missing provenance is the legacy or not-started state.  When the launcher
    record says a service rebuild is committed but not yet rolled out, a
    uniform non-target pair is simply the pre-rebuild template rather than an
    ambiguity, so it is an update to apply.  That covers both a clean rebuild
    and a run interrupted after the transition marker was persisted, where the
    superseded pair is no longer recoverable from the record.  Callers that
    must observe a settled rollout leave ``rebuild_pending`` false so only
    exact provenance can pass.  Every mode must still agree across all four
    serving resources, and a partial or unexplained pair fails closed.
    """

    counts = tuple(replica_counts)
    expected_names = {
        f"greedy-stage-{stage}" for stage in range(1, len(counts) + 1)
    } | {GREEDY_FLOW_GENERATOR}
    resources: dict[str, Mapping[str, object]] = {}
    provenance_modes: set[str] = set()
    correction_required = False
    complete = True
    for raw_item in _items(document, "serving rollout inventory"):
        if not isinstance(raw_item, Mapping):
            raise GreedyLifecycleError("serving rollout item is malformed")
        metadata = raw_item.get("metadata")
        spec = raw_item.get("spec")
        if not isinstance(metadata, Mapping) or not isinstance(spec, Mapping):
            raise GreedyLifecycleError("serving rollout resource is incomplete")
        name = metadata.get("name")
        kind = raw_item.get("kind")
        if name not in expected_names or kind not in {"StatefulSet", "Deployment"}:
            raise GreedyLifecycleError(
                f"unexpected serving rollout resource: {kind}/{name}"
            )
        if name in resources:
            raise GreedyLifecycleError(f"duplicate serving rollout resource: {name}")
        if (
            metadata.get("namespace") != GREEDY_NAMESPACE
            or (name == GREEDY_FLOW_GENERATOR and kind != "Deployment")
            or (name != GREEDY_FLOW_GENERATOR and kind != "StatefulSet")
        ):
            raise GreedyLifecycleError(
                f"serving rollout identity is malformed: {kind}/{name}"
            )
        resources[name] = raw_item
        labels = metadata.get("labels")
        if isinstance(labels, Mapping) and GREEDY_LEGACY_CAPACITY_LABEL in labels:
            correction_required = True
        template = spec.get("template")
        template_metadata = (
            template.get("metadata") if isinstance(template, Mapping) else None
        )
        template_spec = template.get("spec") if isinstance(template, Mapping) else None
        if not isinstance(template_metadata, Mapping) or not isinstance(
            template_spec, Mapping
        ):
            raise GreedyLifecycleError(
                f"serving Pod template is malformed: {kind}/{name}"
            )
        template_labels = template_metadata.get("labels")
        if not isinstance(template_labels, Mapping):
            raise GreedyLifecycleError(
                f"serving Pod-template labels are malformed: {kind}/{name}"
            )
        if GREEDY_LEGACY_CAPACITY_LABEL in template_labels:
            correction_required = True
        annotations = template_metadata.get("annotations", {})
        if not isinstance(annotations, Mapping):
            raise GreedyLifecycleError(
                f"serving Pod-template annotations are malformed: {kind}/{name}"
            )
        image_marker = annotations.get(GREEDY_SERVICE_IMAGE_ID_ANNOTATION)
        source_marker = annotations.get(
            GREEDY_SERVICE_SOURCE_FINGERPRINT_ANNOTATION
        )
        if image_marker is None and source_marker is None:
            provenance_modes.add("absent")
        elif (
            image_marker == service_image_id
            and source_marker == service_source_fingerprint
        ):
            provenance_modes.add("exact")
        elif (
            rebuild_pending
            and isinstance(image_marker, str)
            and isinstance(source_marker, str)
        ):
            provenance_modes.add("superseded")
        else:
            raise GreedyLifecycleError(
                f"serving rollout provenance is mismatched: {kind}/{name}"
            )
        containers = template_spec.get("containers")
        if not isinstance(containers, list):
            raise GreedyLifecycleError(
                f"serving Pod-template containers are malformed: {kind}/{name}"
            )
        expected_containers = (
            {"flow-generator"}
            if name == GREEDY_FLOW_GENERATOR
            else {"private-processor", "public-forwarder"}
        )
        actual_containers = {
            container.get("name")
            for container in containers
            if isinstance(container, Mapping)
        }
        if actual_containers != expected_containers or any(
            not isinstance(container, Mapping)
            or container.get("image") != GREEDY_SERVICE_IMAGE
            or container.get("imagePullPolicy") != "Never"
            for container in containers
        ):
            raise GreedyLifecycleError(
                f"serving Pod-template image contract is mismatched: {kind}/{name}"
            )
        desired = 1 if name == GREEDY_FLOW_GENERATOR else counts[
            int(str(name).removeprefix("greedy-stage-")) - 1
        ]
        complete = complete and _rollout_resource_complete(
            raw_item,
            desired=desired,
            statefulset=kind == "StatefulSet",
        )
    if set(resources) != expected_names:
        raise GreedyLifecycleError("serving rollout resource coverage is incomplete")
    if len(provenance_modes) != 1:
        raise GreedyLifecycleError("serving rollout provenance is partial or ambiguous")
    if (
        provenance_modes == {"absent"}
        or provenance_modes == {"superseded"}
        or correction_required
    ):
        return "template-update-required"
    return "converged" if complete else "progressing"


def _validate_running_service_images(
    execute: Executor,
    *,
    configuration: GreedyConfiguration,
    service_image_id: str,
) -> None:
    """Bind every running serving container to the exact target OCI config."""

    expected = {
        (f"greedy-stage-{stage}-{ordinal}", container)
        for stage in configuration.stages
        for ordinal in range(configuration.num_replicas)
        for container in ("private-processor", "public-forwarder")
    }
    expected.add(("greedy-flow-generator", "flow-generator"))
    inventory = _json_output(
        execute,
        (
            "docker",
            "exec",
            GREEDY_WORKER_NODE,
            "crictl",
            "ps",
            "--label",
            f"io.kubernetes.pod.namespace={GREEDY_NAMESPACE}",
            "-o",
            "json",
        ),
    )
    containers = inventory.get("containers")
    if not isinstance(containers, list):
        raise GreedyLifecycleError("worker CRI container inventory is malformed")
    actual: set[tuple[str, str]] = set()
    for raw_container in containers:
        if not isinstance(raw_container, Mapping):
            raise GreedyLifecycleError("worker CRI container entry is malformed")
        labels = raw_container.get("labels")
        metadata = raw_container.get("metadata")
        image = raw_container.get("image")
        if not all(isinstance(value, Mapping) for value in (labels, metadata, image)):
            raise GreedyLifecycleError("worker CRI serving metadata is malformed")
        if labels.get("io.kubernetes.pod.namespace") != GREEDY_NAMESPACE:
            raise GreedyLifecycleError("worker CRI namespace filter returned foreign data")
        pod_name = labels.get("io.kubernetes.pod.name")
        container_name = labels.get("io.kubernetes.container.name")
        if not isinstance(pod_name, str) or not isinstance(container_name, str):
            raise GreedyLifecycleError("worker CRI serving identity is malformed")
        normalized_pod_name = (
            "greedy-flow-generator"
            if pod_name.startswith("greedy-flow-generator-")
            else pod_name
        )
        identity = (normalized_pod_name, container_name)
        if identity not in expected or identity in actual:
            raise GreedyLifecycleError(
                f"worker CRI serving identity is unexpected or duplicated: {identity}"
            )
        actual.add(identity)
        if (
            raw_container.get("state") != "CONTAINER_RUNNING"
            or metadata.get("name") != container_name
            or image.get("userSpecifiedImage") != GREEDY_SERVICE_IMAGE
            or _image_id(
                raw_container.get("imageId"),
                f"running service image for {normalized_pod_name}/{container_name}",
            )
            != service_image_id
        ):
            raise GreedyLifecycleError(
                "running service image provenance is mismatched: "
                f"{normalized_pod_name}/{container_name}"
            )
    if actual != expected:
        raise GreedyLifecycleError(
            "running service container coverage is incomplete: "
            f"missing={sorted(expected - actual)}, "
            f"unexpected={sorted(actual - expected)}"
        )


def _stage_resources(
    resources: Sequence[Mapping[str, object]], stage: int
) -> tuple[Mapping[str, object], Mapping[str, object]]:
    name = f"greedy-stage-{stage}"
    selected = [
        resource
        for resource in resources
        if resource.get("kind") in {"Service", "StatefulSet"}
        and isinstance(resource.get("metadata"), Mapping)
        and resource["metadata"].get("name") == name
    ]
    by_kind = {resource["kind"]: resource for resource in selected}
    if set(by_kind) != {"Service", "StatefulSet"}:
        raise GreedyLifecycleError(f"canonical stage resources are incomplete: {stage}")
    return by_kind["Service"], by_kind["StatefulSet"]


def _pod_inventory(execute: Executor) -> Mapping[str, object]:
    return _json_output(
        execute,
        _kubectl("get", "pods", "-n", GREEDY_NAMESPACE, "-o", "json"),
    )


def _statefulset_inventory(execute: Executor) -> Mapping[str, object]:
    return _json_output(
        execute,
        _kubectl("get", "statefulsets", "-n", GREEDY_NAMESPACE, "-o", "json"),
    )


def _configmap_inventory(execute: Executor) -> Mapping[str, object]:
    return _json_output(
        execute,
        _kubectl("get", "configmaps", "-n", GREEDY_NAMESPACE, "-o", "json"),
    )


def _deployed_launcher_state(
    configmaps: Mapping[str, object],
) -> GreedyLauncherState | None:
    matches = [
        item
        for item in _items(configmaps, "ConfigMap inventory")
        if _name(item, "ConfigMap") == GREEDY_LAUNCHER_STATE_CONFIG_MAP
    ]
    if not matches:
        return None
    if len(matches) != 1:
        raise GreedyLifecycleError("launcher-state ConfigMap is duplicated")
    item = matches[0]
    metadata = item.get("metadata")
    data = item.get("data")
    labels = metadata.get("labels") if isinstance(metadata, Mapping) else None
    if (
        not isinstance(metadata, Mapping)
        or metadata.get("namespace") != GREEDY_NAMESPACE
        or not isinstance(labels, Mapping)
        or labels.get("app.kubernetes.io/part-of") != GREEDY_PART_OF
        or not isinstance(data, Mapping)
        or set(data) != {"launcher-state.json"}
    ):
        raise GreedyLifecycleError("launcher-state ConfigMap ownership/data is invalid")
    try:
        value = json.loads(data["launcher-state.json"])
    except (TypeError, json.JSONDecodeError) as error:
        raise GreedyLifecycleError("launcher-state ConfigMap JSON is malformed") from error
    return launcher_state_from_mapping(value)


def _deployed_runtime_profile(
    configmaps: Mapping[str, object],
) -> GreedyKernelRuntimeProfileDocument:
    matches = [
        item
        for item in _items(configmaps, "ConfigMap inventory")
        if _name(item, "ConfigMap") == GREEDY_RUNTIME_PROFILE_CONFIG_MAP
    ]
    if len(matches) != 1:
        raise GreedyLifecycleError("runtime-profile ConfigMap is incomplete or duplicated")
    item = matches[0]
    metadata = item.get("metadata")
    data = item.get("data")
    labels = metadata.get("labels") if isinstance(metadata, Mapping) else None
    if (
        not isinstance(metadata, Mapping)
        or metadata.get("namespace") != GREEDY_NAMESPACE
        or not isinstance(labels, Mapping)
        or labels.get("app.kubernetes.io/part-of") != GREEDY_PART_OF
        or not isinstance(data, Mapping)
        or set(data) != {"runtime-profiles.json"}
    ):
        raise GreedyLifecycleError("runtime-profile ConfigMap ownership/data is invalid")
    try:
        value = json.loads(data["runtime-profiles.json"])
        return runtime_profile_document_from_mapping(value)
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise GreedyLifecycleError("deployed runtime-profile document is invalid") from error


def _deployed_controller_document(configmaps: Mapping[str, object]):
    matches = [
        item
        for item in _items(configmaps, "ConfigMap inventory")
        if _name(item, "ConfigMap") == GREEDY_CONTROLLER_INPUT_CONFIG_MAP
    ]
    if len(matches) != 1:
        raise GreedyLifecycleError("controller-input ConfigMap is incomplete or duplicated")
    item = matches[0]
    metadata = item.get("metadata")
    data = item.get("data")
    labels = metadata.get("labels") if isinstance(metadata, Mapping) else None
    if (
        not isinstance(metadata, Mapping)
        or metadata.get("namespace") != GREEDY_NAMESPACE
        or not isinstance(labels, Mapping)
        or labels.get("app.kubernetes.io/part-of") != GREEDY_PART_OF
        or not isinstance(data, Mapping)
        or set(data) != {"controller-inputs.json"}
    ):
        raise GreedyLifecycleError("controller-input ConfigMap ownership/data is invalid")
    try:
        value = json.loads(data["controller-inputs.json"])
        return controller_input_document_from_mapping(value)
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise GreedyLifecycleError("deployed controller-input document is invalid") from error


def _serving_snapshot(
    pods: Mapping[str, object],
) -> tuple[GreedyServingProcessSnapshot, ...]:
    snapshots = []
    for item in _items(pods, "Pod inventory"):
        name = _name(item, "Pod")
        if not name.startswith(("greedy-stage-", "greedy-flow-generator-")):
            continue
        metadata = item.get("metadata")
        status = item.get("status")
        uid = metadata.get("uid") if isinstance(metadata, Mapping) else None
        statuses = status.get("containerStatuses") if isinstance(status, Mapping) else None
        if not isinstance(uid, str) or not uid or not isinstance(statuses, list) or not statuses:
            raise GreedyLifecycleError(f"serving Pod {name} lacks process identity")
        restarts = []
        for container in statuses:
            if not isinstance(container, Mapping):
                raise GreedyLifecycleError(f"serving Pod {name} status is malformed")
            container_name = container.get("name")
            restart_count = container.get("restartCount")
            if (
                not isinstance(container_name, str)
                or isinstance(restart_count, bool)
                or not isinstance(restart_count, Integral)
                or restart_count < 0
            ):
                raise GreedyLifecycleError(f"serving Pod {name} restart data is invalid")
            restarts.append((container_name, int(restart_count)))
        snapshots.append(
            GreedyServingProcessSnapshot(name, uid, tuple(sorted(restarts)))
        )
    return tuple(sorted(snapshots))


def validate_retained_processes(
    before: Sequence[GreedyServingProcessSnapshot],
    after: Sequence[GreedyServingProcessSnapshot],
) -> None:
    old = {item.pod_name: item for item in before}
    new = {item.pod_name: item for item in after}
    changed = sorted(name for name in set(old) & set(new) if old[name] != new[name])
    if changed:
        raise GreedyLifecycleError(
            "reconciliation changed retained serving Pod UIDs or restart counts: "
            + ", ".join(changed)
        )


def _wait_ready(
    execute: Executor,
    *,
    num_flows: int,
    num_stages: int,
    num_replicas: int,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    stall_timeout_seconds: float = GREEDY_ROLLOUT_STALL_TIMEOUT_SECONDS,
    poll_seconds: float = GREEDY_ROLLOUT_POLL_SECONDS,
    total_timeout_seconds: float | None = None,
) -> None:
    """Wait for exact serving readiness with a progress-reset stall timeout.

    A StatefulSet rollout replaces ordered Pods one at a time, so a fixed
    wall-clock deadline can reject a healthy large rollout.  Verified
    generation/revision progress or a newly observed/Ready Pod UID resets the
    stall clock.  A separate topology-bounded total deadline prevents endless
    Pod replacement churn from keeping the launcher alive forever.
    """

    configuration = GreedyConfiguration(num_flows, num_stages, num_replicas)
    if (
        stall_timeout_seconds <= 0
        or poll_seconds <= 0
        or (
            total_timeout_seconds is not None
            and total_timeout_seconds <= 0
        )
    ):
        raise ValueError("Greedy rollout wait durations must be positive")
    expected_statefulsets = {
        f"greedy-stage-{stage}" for stage in range(1, num_stages + 1)
    }
    expected_resources = expected_statefulsets | {GREEDY_FLOW_GENERATOR}
    best_frontier: dict[str, tuple[int, int, int, int]] = {}
    observed_pod_uids: set[tuple[str, str]] = set()
    ready_pod_uids: set[tuple[str, str]] = set()
    started = last_progress = clock()
    total_timeout = (
        max(600.0, stall_timeout_seconds * (num_replicas + 2))
        if total_timeout_seconds is None
        else total_timeout_seconds
    )

    while True:
        rollout = _serving_workload_inventory(execute)
        raw_items = rollout.get("items")
        if not isinstance(raw_items, list):
            raise GreedyLifecycleError("rollout inventory lacks an items list")
        resources: dict[str, Mapping[str, object]] = {}
        progress = False
        complete = True
        for raw_item in raw_items:
            if not isinstance(raw_item, Mapping):
                raise GreedyLifecycleError("rollout inventory item is malformed")
            metadata = raw_item.get("metadata")
            spec = raw_item.get("spec")
            status = raw_item.get("status")
            if not all(isinstance(value, Mapping) for value in (metadata, spec, status)):
                raise GreedyLifecycleError("rollout resource is incomplete")
            name = metadata.get("name")
            if name not in expected_resources:
                raise GreedyLifecycleError(
                    f"unexpected rollout resource identity: {name!r}"
                )
            if name in resources:
                raise GreedyLifecycleError(f"duplicate rollout resource: {name}")
            resources[name] = raw_item
            desired = num_replicas if name in expected_statefulsets else 1

            def count(field: str) -> int:
                value = status.get(field, 0)
                if isinstance(value, bool) or not isinstance(value, Integral) or value < 0:
                    raise GreedyLifecycleError(
                        f"rollout resource {name} has invalid {field}"
                    )
                return int(value)

            generation = metadata.get("generation")
            observed_generation = status.get("observedGeneration", 0)
            if (
                isinstance(generation, bool)
                or not isinstance(generation, Integral)
                or generation < 1
                or isinstance(observed_generation, bool)
                or not isinstance(observed_generation, Integral)
                or observed_generation < 0
            ):
                raise GreedyLifecycleError(
                    f"rollout resource {name} has invalid generation status"
                )
            updated = count("updatedReplicas")
            ready = count("readyReplicas")
            available = count("availableReplicas")
            revision_converged = 1
            if name in expected_statefulsets:
                current_revision = status.get("currentRevision")
                update_revision = status.get("updateRevision")
                revision_converged = int(
                    isinstance(current_revision, str)
                    and current_revision
                    and current_revision == update_revision
                )
            frontier = (
                int(observed_generation),
                updated,
                ready,
                revision_converged,
            )
            previous = best_frontier.get(name)
            if previous is None or frontier > previous:
                best_frontier[name] = frontier
                progress = True
            desired_spec = spec.get("replicas")
            complete = complete and (
                desired_spec == desired
                and observed_generation >= generation
                and updated == desired
                and ready == desired
                and available == desired
                and revision_converged == 1
            )
        if set(resources) != expected_resources:
            complete = False

        pods = _pod_inventory(execute)
        pod_items = pods.get("items")
        if not isinstance(pod_items, list):
            raise GreedyLifecycleError("Pod inventory lacks an items list")
        for raw_pod in pod_items:
            if not isinstance(raw_pod, Mapping):
                raise GreedyLifecycleError("Pod inventory item is malformed")
            metadata = raw_pod.get("metadata")
            if not isinstance(metadata, Mapping):
                raise GreedyLifecycleError("Pod metadata is malformed")
            name = metadata.get("name")
            uid = metadata.get("uid")
            if not isinstance(name, str) or not isinstance(uid, str) or not uid:
                continue
            if not (
                name.startswith("greedy-stage-")
                or name.startswith("greedy-flow-generator-")
            ):
                continue
            identity = (name, uid)
            if identity not in observed_pod_uids:
                observed_pod_uids.add(identity)
                progress = True
            status = raw_pod.get("status")
            conditions = status.get("conditions") if isinstance(status, Mapping) else None
            is_ready = isinstance(conditions, list) and any(
                isinstance(condition, Mapping)
                and condition.get("type") == "Ready"
                and condition.get("status") == "True"
                for condition in conditions
            )
            if is_ready and identity not in ready_pod_uids:
                ready_pod_uids.add(identity)
                progress = True

        now = clock()
        if progress:
            last_progress = now
        if complete:
            validate_ready_coverage(pods, configuration=configuration)
            return
        if now - last_progress >= stall_timeout_seconds:
            raise GreedyLifecycleError(
                "Greedy rollout made no verified progress for "
                f"{stall_timeout_seconds:g} seconds"
            )
        if now - started >= total_timeout:
            raise GreedyLifecycleError(
                "Greedy rollout exceeded its topology-bounded total deadline"
            )
        sleep(poll_seconds)


def _wait_removed_pods(execute: Executor, names: Sequence[str]) -> None:
    targets = tuple(names)
    if targets:
        execute(
            _kubectl(
                "wait",
                "-n",
                GREEDY_NAMESPACE,
                "--for=delete",
                *(f"pod/{name}" for name in targets),
                "--timeout=120s",
            ),
            False,
        )


def _current_context_and_inventory(execute: Executor) -> tuple[
    Mapping[str, object], Mapping[str, object], Mapping[str, object]
]:
    validate_context_identity(
        _json_output(
            execute,
            (
                "kubectl",
                "config",
                "view",
                "--context",
                GREEDY_CONTEXT,
                "--minify",
                "-o",
                "json",
            ),
        )
    )
    nodes = _json_output(execute, _kubectl("get", "nodes", "-o", "json"))
    namespaces = _json_output(
        execute, _kubectl("get", "namespaces", "-o", "json")
    )
    pods = _json_output(execute, _kubectl("get", "pods", "-A", "-o", "json"))
    validate_cluster_inventory(nodes=nodes, namespaces=namespaces, pods=pods)
    return nodes, namespaces, pods


def _namespace_names(document: Mapping[str, object]) -> set[str]:
    return {_name(item, "namespace") for item in _items(document, "namespace inventory")}


def _validate_local_images_against_state(
    execute: Executor, state: GreedyLauncherState
) -> None:
    if _local_image_id(execute, GREEDY_SERVICE_IMAGE) != state.service_image_id:
        raise GreedyLifecycleError("local service image identity differs from provenance")
    if _local_image_id(execute, GREEDY_CONTROLLER_IMAGE) != state.controller_image_id:
        raise GreedyLifecycleError("local controller image identity differs from provenance")


def _transition_state(
    *,
    current: GreedyLauncherState,
    target: GreedyLaunchConfiguration,
    source_fingerprints: Mapping[str, str],
    image_ids: Mapping[str, str],
    service_restart_required: bool,
) -> GreedyLauncherState:
    stable = (
        current.stable_configuration
        if current.transition_active
        else current.target_configuration
    )
    return GreedyLauncherState(
        stable_configuration=stable,
        target_configuration=target.configuration,
        profile_seed=target.profile_seed,
        profile_fingerprint=target.runtime_profiles.fingerprint,
        service_source_fingerprint=source_fingerprints["service"],
        controller_source_fingerprint=source_fingerprints["controller"],
        service_image_id=image_ids["service"],
        controller_image_id=image_ids["controller"],
        transition_active=True,
        service_restart_required=service_restart_required,
    )


def _stable_state(
    transition: GreedyLauncherState,
) -> GreedyLauncherState:
    return GreedyLauncherState(
        stable_configuration=transition.target_configuration,
        target_configuration=transition.target_configuration,
        profile_seed=transition.profile_seed,
        profile_fingerprint=transition.profile_fingerprint,
        service_source_fingerprint=transition.service_source_fingerprint,
        controller_source_fingerprint=transition.controller_source_fingerprint,
        service_image_id=transition.service_image_id,
        controller_image_id=transition.controller_image_id,
        transition_active=False,
        service_restart_required=False,
    )


def _bootstrap_state(
    launch: GreedyLaunchConfiguration,
    source_fingerprints: Mapping[str, str],
    image_ids: Mapping[str, str],
) -> GreedyLauncherState:
    return GreedyLauncherState(
        stable_configuration=launch.configuration,
        target_configuration=launch.configuration,
        profile_seed=launch.profile_seed,
        profile_fingerprint=launch.runtime_profiles.fingerprint,
        service_source_fingerprint=source_fingerprints["service"],
        controller_source_fingerprint=source_fingerprints["controller"],
        service_image_id=image_ids["service"],
        controller_image_id=image_ids["controller"],
        transition_active=True,
        service_restart_required=False,
    )


def _reconcile_existing(
    execute: Executor,
    *,
    launch: GreedyLaunchConfiguration,
    resources: Sequence[Mapping[str, object]],
    current: GreedyExistingTopology,
    deployed_profile: GreedyKernelRuntimeProfileDocument,
    transition: GreedyLauncherState,
    rebuild_pending: bool,
    emit: ProgressEmitter | None = None,
) -> tuple[bool, bool]:
    target = launch.configuration
    validate_profile_transition(
        deployed=deployed_profile,
        proposed=launch.runtime_profiles,
        profile_seed=launch.profile_seed,
    )
    if transition.transition_active:
        validate_interrupted_transition_shape(
            current,
            stable=transition.stable_configuration,
            target=transition.target_configuration,
        )
        if transition.target_configuration != target:
            raise GreedyLifecycleError(
                "an interrupted transition must resume to its recorded target"
            )
    else:
        # Ordinary stable topology must have one exact stage-consistent count.
        if (
            current.num_stages != transition.stable_configuration.num_stages
            or current.uniform_replica_count
            != transition.stable_configuration.num_replicas
        ):
            raise GreedyLifecycleError(
                "unmarked partial topology transition is unsafe"
            )

    serving_changed = False
    retained_process_change_expected = False
    current_stage_count = current.num_stages
    current_counts = list(current.replica_counts)

    # Contraction occurs while the old complete processor profile remains
    # mounted.  This prevents a removed profile from racing a terminating Pod.
    for stage in range(current_stage_count, target.num_stages, -1):
        if emit is not None:
            emit(f"Greedy rollout: removing highest stage {stage}")
        removed_names = [
            f"greedy-stage-{stage}-{ordinal}"
            for ordinal in range(current_counts[stage - 1])
        ]
        execute(
            _kubectl(
                "delete",
                f"statefulset/greedy-stage-{stage}",
                f"service/greedy-stage-{stage}",
                "-n",
                GREEDY_NAMESPACE,
                "--wait=true",
            ),
            False,
        )
        _wait_removed_pods(execute, removed_names)
        current_counts.pop()
        current_stage_count -= 1
        serving_changed = True
        if len(set(current_counts)) == 1:
            _wait_ready(
                execute,
                num_flows=target.num_flows,
                num_stages=current_stage_count,
                num_replicas=current_counts[0],
            )

    if any(count > target.num_replicas for count in current_counts):
        if emit is not None:
            emit(
                "Greedy rollout: scaling retained stages down to "
                f"{target.num_replicas} replicas"
            )
        removed_names = [
            f"greedy-stage-{stage}-{ordinal}"
            for stage, count in enumerate(current_counts, start=1)
            for ordinal in range(target.num_replicas, count)
        ]
        execute(
            _kubectl(
                "scale",
                *(
                    f"statefulset/greedy-stage-{stage}"
                    for stage in range(1, current_stage_count + 1)
                ),
                f"--replicas={target.num_replicas}",
                "-n",
                GREEDY_NAMESPACE,
            ),
            False,
        )
        _wait_removed_pods(execute, removed_names)
        current_counts = [target.num_replicas] * current_stage_count
        _wait_ready(
            execute,
            num_flows=target.num_flows,
            num_stages=current_stage_count,
            num_replicas=target.num_replicas,
        )
        serving_changed = True

    # Profiles/configuration now project exactly to the retained target prefix,
    # so subsequent newly created Pods can resolve their private identities.
    _apply_documents(execute, _configmap_documents(resources))

    rollout_state = _classify_service_rollout(
        _serving_workload_inventory(execute),
        replica_counts=current_counts,
        service_source_fingerprint=transition.service_source_fingerprint,
        service_image_id=transition.service_image_id,
        rebuild_pending=rebuild_pending,
    )
    if rollout_state == "template-update-required":
        if launch.skip_build:
            raise GreedyLifecycleError(
                "--skip-build cannot reconcile service Pod-template provenance drift"
            )
        if emit is not None:
            emit("Greedy rollout: applying canonical service template")
        _apply_documents(
            execute,
            _retained_serving_documents(resources, current_counts),
        )
        _wait_ready(
            execute,
            num_flows=target.num_flows,
            num_stages=current_stage_count,
            num_replicas=current_counts[0],
        )
        serving_changed = True
        retained_process_change_expected = True
    elif rollout_state == "progressing":
        if emit is not None:
            emit("Greedy rollout: continuing recorded service template rollout")
        _wait_ready(
            execute,
            num_flows=target.num_flows,
            num_stages=current_stage_count,
            num_replicas=current_counts[0],
        )
        serving_changed = True
        retained_process_change_expected = transition.service_restart_required

    if current_counts:
        minimum_count = min(current_counts)
        maximum_count = max(current_counts)
        if minimum_count < target.num_replicas:
            for batch in plan_replica_batches(
                existing_count=minimum_count,
                requested_count=target.num_replicas,
                batch_size=launch.rollout_batch_size,
            ):
                batch_target = max(batch.target_count, maximum_count)
                if emit is not None:
                    emit(
                        "Greedy rollout: scaling retained stages to "
                        f"{batch_target} replicas"
                    )
                if batch_target > target.num_replicas:
                    raise GreedyLifecycleError(
                        "interrupted replica expansion exceeds the target"
                    )
                execute(
                    _kubectl(
                        "scale",
                        *(
                            f"statefulset/greedy-stage-{stage}"
                            for stage in range(1, current_stage_count + 1)
                        ),
                        f"--replicas={batch_target}",
                        "-n",
                        GREEDY_NAMESPACE,
                    ),
                    False,
                )
                current_counts = [batch_target] * current_stage_count
                minimum_count = batch_target
                maximum_count = batch_target
                _wait_ready(
                    execute,
                    num_flows=target.num_flows,
                    num_stages=current_stage_count,
                    num_replicas=batch_target,
                )
                serving_changed = True
                if batch_target == target.num_replicas:
                    break
        elif maximum_count != minimum_count:
            raise GreedyLifecycleError(
                "interrupted replica counts cannot be normalized safely"
            )

    for stage in range(current_stage_count + 1, target.num_stages + 1):
        if emit is not None:
            emit(f"Greedy rollout: adding highest stage {stage}")
        service, statefulset = _stage_resources(resources, stage)
        _apply_documents(execute, (service, statefulset))
        current_stage_count = stage
        current_counts.append(target.num_replicas)
        _wait_ready(
            execute,
            num_flows=target.num_flows,
            num_stages=current_stage_count,
            num_replicas=target.num_replicas,
        )
        serving_changed = True

    _wait_ready(
        execute,
        num_flows=target.num_flows,
        num_stages=target.num_stages,
        num_replicas=target.num_replicas,
    )
    return serving_changed, retained_process_change_expected


def _bootstrap_serving(
    execute: Executor,
    *,
    launch: GreedyLaunchConfiguration,
    resources: Sequence[Mapping[str, object]],
    emit: ProgressEmitter | None = None,
) -> bool:
    target = launch.configuration
    initial_count = min(target.num_replicas, launch.rollout_batch_size)
    if emit is not None:
        emit(
            "Greedy rollout: bootstrapping all stages at "
            f"{initial_count} replica(s)"
        )
    initial = deepcopy(tuple(resources))
    for resource in initial:
        if resource.get("kind") == "StatefulSet":
            resource["spec"]["replicas"] = initial_count
    _apply_documents(execute, initial)
    _wait_ready(
        execute,
        num_flows=target.num_flows,
        num_stages=target.num_stages,
        num_replicas=initial_count,
    )
    for batch in plan_replica_batches(
        existing_count=initial_count,
        requested_count=target.num_replicas,
        batch_size=launch.rollout_batch_size,
    ):
        if emit is not None:
            emit(
                "Greedy rollout: scaling all stages to "
                f"{batch.target_count} replicas"
            )
        execute(
            _kubectl(
                "scale",
                *(
                    f"statefulset/greedy-stage-{stage}" for stage in target.stages
                ),
                f"--replicas={batch.target_count}",
                "-n",
                GREEDY_NAMESPACE,
            ),
            False,
        )
        _wait_ready(
            execute,
            num_flows=target.num_flows,
            num_stages=target.num_stages,
            num_replicas=batch.target_count,
        )
    return True


def _controller_readiness(configuration: GreedyConfiguration) -> GreedyServingReadiness:
    return GreedyServingReadiness(
        configuration=configuration,
        ready_identities=tuple(
            ReplicaIdentity(stage, replica)
            for stage in configuration.stages
            for replica in configuration.replica_ids
        ),
        flow_generator_ready=True,
    )


def run_greedy_lifecycle(
    launch: GreedyLaunchConfiguration,
    *,
    execute: Executor = _execute,
    validate_wheelhouses: WheelhouseValidator | None = None,
    emit: ProgressEmitter | None = None,
    stream_logs: Callable[[], None] | None = None,
) -> GreedyLifecycleResult:
    """Reconcile one environment and create exactly one finite controller Job.

    ``stream_logs`` is an optional display-only hook invoked once the finite Job
    exists.  It must block until that Job stops producing output.  Completion is
    still decided by the ``kubectl wait`` condition below, and the authoritative
    evidence text is still read afterwards, so a caller that omits the hook --
    every test does -- keeps the exact previous behaviour.
    """

    if not isinstance(launch, GreedyLaunchConfiguration):
        raise TypeError("launch must be GreedyLaunchConfiguration")
    if validate_wheelhouses is None:
        from scripts.greedy_offline_wheelhouse import validate_wheelhouse

        def validate_wheelhouses(roles: Sequence[str]) -> object:
            return tuple(validate_wheelhouse(role, root=ROOT) for role in roles)

    target = launch.configuration
    if emit is not None:
        emit(
            "Selected Greedy topology: "
            f"{target.num_flows} flows x {target.num_stages} stages x "
            f"{target.num_replicas} replicas per stage"
        )
        emit(
            "Greedy profile: "
            f"seed={launch.profile_seed}, fingerprint={launch.runtime_profiles.fingerprint}"
        )
        emit(
            "Greedy image mode: "
            + ("validated skip-build reuse" if launch.skip_build else "change-scoped offline build")
        )
    deployment = launch.deployment
    resources = render_long_running_resources(deployment)
    source_fingerprints = image_source_fingerprints()

    # Normal mode validates both reproducible inputs before any Docker command
    # or cluster inspection.  --skip-build deliberately skips this boundary.
    if not launch.skip_build:
        validate_wheelhouses(("service", "controller"))

    cluster_exists = GREEDY_CLUSTER_NAME in _kind_clusters(execute)
    if launch.skip_build and not cluster_exists:
        raise GreedyLifecycleError("--skip-build cannot bootstrap a fresh cluster")

    built: tuple[str, ...] = ()
    loaded: tuple[str, ...] = ()
    cluster_created = False
    current_state: GreedyLauncherState | None = None
    deployed_profile_before: GreedyKernelRuntimeProfileDocument | None = None
    discovered_before_transition: GreedyExistingTopology | None = None
    before_processes: tuple[GreedyServingProcessSnapshot, ...] = ()
    worker_allocatable: GreedyWorkerAllocatable | None = None

    if not cluster_exists:
        # Fresh bootstrap is the only path that builds both images unconditionally.
        execute(("docker", "image", "inspect", GREEDY_PYTHON_BASE_IMAGE), True)
        execute(("docker", "image", "inspect", GREEDY_KIND_NODE_IMAGE), True)
        built = _build_images(execute, ("service", "controller"))
        image_ids = {
            "service": _local_image_id(execute, GREEDY_SERVICE_IMAGE),
            "controller": _local_image_id(execute, GREEDY_CONTROLLER_IMAGE),
        }
        execute(
            (
                "kind",
                "create",
                "cluster",
                "--name",
                GREEDY_CLUSTER_NAME,
                "--image",
                GREEDY_KIND_NODE_IMAGE,
                "--config",
                str(GREEDY_KIND_CONFIG),
                "--wait",
                "120s",
            ),
            False,
        )
        execute(
            _kubectl(
                "wait",
                "--for=condition=Ready",
                f"node/{GREEDY_CONTROL_PLANE_NODE}",
                f"node/{GREEDY_WORKER_NODE}",
                "--timeout=120s",
            ),
            False,
        )
        execute(
            _kubectl(
                "label",
                "node",
                GREEDY_WORKER_NODE,
                f"{GREEDY_WORKLOAD_NODE_LABEL}=true",
                "--overwrite",
            ),
            False,
        )
        nodes, namespaces, _pods = _current_context_and_inventory(execute)
        worker_allocatable = worker_resource_preflight(target, nodes)
        if emit is not None:
            emit("Greedy worker-resource preflight: passed")
        loaded = _load_images(execute, built)
        validate_node_images(
            execute,
            service_image_id=image_ids["service"],
            controller_image_id=image_ids["controller"],
        )
        namespace = next(
            resource for resource in resources if resource.get("kind") == "Namespace"
        )
        _apply_documents(execute, (namespace,))
        current_state = _bootstrap_state(launch, source_fingerprints, image_ids)
        _apply_documents(execute, (_launcher_state_resource(current_state),))
        cluster_created = True
    else:
        nodes, namespaces, _pods = _current_context_and_inventory(execute)
        worker_allocatable = worker_resource_preflight(target, nodes)
        if emit is not None:
            emit("Greedy worker-resource preflight: passed")
        if GREEDY_NAMESPACE not in _namespace_names(namespaces):
            raise GreedyLifecycleError(
                "existing Greedy cluster has no owned namespace provenance"
            )
        validate_owned_resource_inventory(_owned_resource_inventory(execute))
        configmaps = _configmap_inventory(execute)
        current_state = _deployed_launcher_state(configmaps)
        if current_state is None:
            raise GreedyLifecycleError(
                "existing Greedy namespace has no complete launcher provenance"
            )
        if current_state.transition_active and current_state.target_configuration != target:
            raise GreedyLifecycleError(
                "requested topology differs from the interrupted transition target"
            )
        if current_state.profile_seed != launch.profile_seed:
            raise GreedyLifecycleError("retained runtime profiles cannot change profile seed")
        deployed_profile_before = _deployed_runtime_profile(configmaps)
        validate_profile_transition(
            deployed=deployed_profile_before,
            proposed=launch.runtime_profiles,
            profile_seed=launch.profile_seed,
        )
        expected_state_profile_fingerprint = (
            launch.runtime_profiles.fingerprint
            if current_state.transition_active
            else deployed_profile_before.fingerprint
        )
        if current_state.profile_fingerprint != expected_state_profile_fingerprint:
            raise GreedyLifecycleError(
                "launcher profile fingerprint does not match its declared state"
            )
        deployed_controller = _deployed_controller_document(configmaps).controller
        if (
            deployed_controller.configuration != deployed_profile_before.configuration
            or deployed_controller.runtime_profile_fingerprint
            != deployed_profile_before.fingerprint
        ):
            raise GreedyLifecycleError(
                "deployed controller inputs do not match the runtime profile"
            )
        discovered_before_transition = discover_existing_topology(
            _statefulset_inventory(execute)
        )
        if current_state.transition_active:
            validate_interrupted_transition_shape(
                discovered_before_transition,
                stable=current_state.stable_configuration,
                target=current_state.target_configuration,
            )
        else:
            try:
                stable_replica_count = (
                    discovered_before_transition.uniform_replica_count
                )
            except GreedyKernelRolloutError as error:
                raise GreedyLifecycleError(
                    "unmarked partial topology transition is unsafe"
                ) from error
            if (
                discovered_before_transition.num_stages
                != current_state.stable_configuration.num_stages
                or stable_replica_count
                != current_state.stable_configuration.num_replicas
            ):
                raise GreedyLifecycleError(
                    "unmarked partial topology transition is unsafe"
                )
        if launch.skip_build:
            if (
                current_state.service_source_fingerprint
                != source_fingerprints["service"]
                or current_state.controller_source_fingerprint
                != source_fingerprints["controller"]
            ):
                raise GreedyLifecycleError(
                    "--skip-build cannot reuse images after source provenance changed"
                )
            _validate_local_images_against_state(execute, current_state)
            image_ids = {
                "service": current_state.service_image_id,
                "controller": current_state.controller_image_id,
            }
        else:
            if current_state.transition_active and (
                current_state.service_source_fingerprint
                != source_fingerprints["service"]
                or current_state.controller_source_fingerprint
                != source_fingerprints["controller"]
            ):
                raise GreedyLifecycleError(
                    "source changes cannot be mixed with an interrupted transition"
                )
            changed_roles = tuple(
                role
                for role in ("service", "controller")
                if getattr(current_state, f"{role}_source_fingerprint")
                != source_fingerprints[role]
            )
            unchanged_roles = tuple(
                role for role in ("service", "controller") if role not in changed_roles
            )
            for role in unchanged_roles:
                image = (
                    GREEDY_SERVICE_IMAGE if role == "service" else GREEDY_CONTROLLER_IMAGE
                )
                if _local_image_id(execute, image) != getattr(
                    current_state, f"{role}_image_id"
                ):
                    raise GreedyLifecycleError(
                        f"unchanged {role} image provenance is incomplete"
                    )
            built = _build_images(execute, changed_roles)
            image_ids = {
                "service": (
                    _local_image_id(execute, GREEDY_SERVICE_IMAGE)
                    if "service" in changed_roles
                    else current_state.service_image_id
                ),
                "controller": (
                    _local_image_id(execute, GREEDY_CONTROLLER_IMAGE)
                    if "controller" in changed_roles
                    else current_state.controller_image_id
                ),
            }
            loaded = _load_images(execute, built)
        validate_node_images(
            execute,
            service_image_id=image_ids["service"],
            controller_image_id=image_ids["controller"],
        )
        before_processes = _serving_snapshot(_pod_inventory(execute))

    if current_state is None:
        raise GreedyLifecycleError("launcher state construction failed")
    resources = _service_rollout_resources(
        resources,
        service_source_fingerprint=source_fingerprints["service"],
        service_image_id=image_ids["service"],
    )
    if current_state.service_restart_required:
        if discovered_before_transition is None:
            raise GreedyLifecycleError(
                "pending service rollout has no discovered topology"
            )
        pending_rollout_state = _classify_service_rollout(
            _serving_workload_inventory(execute),
            replica_counts=discovered_before_transition.replica_counts,
            service_source_fingerprint=current_state.service_source_fingerprint,
            service_image_id=current_state.service_image_id,
            # The marker is persisted before the canonical apply, so a run
            # interrupted in between leaves the templates on the superseded
            # pair.  That is an unstarted rollout to resume, not a foreign one.
            rebuild_pending=True,
        )
        if launch.skip_build and pending_rollout_state != "converged":
            raise GreedyLifecycleError(
                "--skip-build cannot resume an incomplete pending service rollout"
            )
        if pending_rollout_state == "converged":
            _validate_running_service_images(
                execute,
                configuration=current_state.target_configuration,
                service_image_id=current_state.service_image_id,
            )
    service_restart_required = (
        current_state.service_restart_required or "service" in built
    )
    transition = (
        current_state
        if current_state.transition_active
        else _transition_state(
            current=current_state,
            target=launch,
            source_fingerprints=source_fingerprints,
            image_ids=image_ids,
            service_restart_required=service_restart_required,
        )
    )
    if not transition.transition_active:
        raise GreedyLifecycleError("launcher transition marker was not activated")
    if transition.target_configuration != target:
        raise GreedyLifecycleError("launcher transition target drifted")
    _apply_documents(execute, (_launcher_state_resource(transition),))

    # No previous finite controller is allowed to overlap any topology change.
    execute(
        _kubectl(
            "delete",
            "job",
            GREEDY_CONTROLLER_JOB,
            "-n",
            GREEDY_NAMESPACE,
            "--ignore-not-found",
            "--wait=true",
        ),
        False,
    )

    if cluster_created:
        serving_changed = _bootstrap_serving(
            execute, launch=launch, resources=resources, emit=emit
        )
        retained_process_change_expected = True
    else:
        if deployed_profile_before is None:
            raise GreedyLifecycleError("deployed runtime profile was not prevalidated")
        current_topology = discover_existing_topology(_statefulset_inventory(execute))
        serving_changed, retained_process_change_expected = _reconcile_existing(
            execute,
            launch=launch,
            resources=resources,
            current=current_topology,
            deployed_profile=deployed_profile_before,
            transition=transition,
            rebuild_pending=service_restart_required,
            emit=emit,
        )

    _wait_ready(
        execute,
        num_flows=target.num_flows,
        num_stages=target.num_stages,
        num_replicas=target.num_replicas,
    )
    final_topology = discover_existing_topology(_statefulset_inventory(execute))
    if (
        final_topology.num_stages != target.num_stages
        or final_topology.uniform_replica_count != target.num_replicas
    ):
        raise GreedyLifecycleError("final Greedy topology is not exact")
    validate_owned_resource_inventory(_owned_resource_inventory(execute))
    final_profile = _deployed_runtime_profile(_configmap_inventory(execute))
    if final_profile != launch.runtime_profiles:
        raise GreedyLifecycleError("final Greedy runtime profile is not exact")
    final_rollout_state = _classify_service_rollout(
        _serving_workload_inventory(execute),
        replica_counts=(target.num_replicas,) * target.num_stages,
        service_source_fingerprint=transition.service_source_fingerprint,
        service_image_id=transition.service_image_id,
    )
    if final_rollout_state != "converged":
        raise GreedyLifecycleError(
            "final Greedy service rollout provenance is not converged"
        )
    _validate_running_service_images(
        execute,
        configuration=target,
        service_image_id=transition.service_image_id,
    )

    after_processes = _serving_snapshot(_pod_inventory(execute))
    if before_processes and not retained_process_change_expected:
        validate_retained_processes(before_processes, after_processes)

    stable = _stable_state(transition)
    _apply_documents(execute, (_launcher_state_resource(stable),))

    job = render_controller_job(deployment, _controller_readiness(target))
    if emit is not None:
        emit("Greedy serving readiness: exact coverage passed")
        emit("Greedy controller Job: starting")
    _apply_documents(execute, (job,))
    if stream_logs is not None:
        stream_logs()
    execute(
        _kubectl(
            "wait",
            "-n",
            GREEDY_NAMESPACE,
            "--for=condition=complete",
            f"job/{GREEDY_CONTROLLER_JOB}",
            "--timeout=600s",
        ),
        False,
    )
    if emit is not None:
        emit("Greedy controller Job: completed")
    if worker_allocatable is None:
        raise GreedyLifecycleError("worker allocatable provenance is unavailable")
    return GreedyLifecycleResult(
        configuration=target,
        profile_fingerprint=launch.runtime_profiles.fingerprint,
        root_seed=launch.root_seed,
        cluster_created=cluster_created,
        built_images=built,
        loaded_images=loaded,
        serving_changed=serving_changed,
        controller_jobs_created=1,
        service_source_fingerprint=source_fingerprints["service"],
        controller_source_fingerprint=source_fingerprints["controller"],
        service_image_id=image_ids["service"],
        controller_image_id=image_ids["controller"],
        worker_allocatable_cpu_millicores=(
            worker_allocatable.cpu_millicores
        ),
        worker_allocatable_memory_mib=worker_allocatable.memory_mib,
    )


def cleanup(*, execute: Executor = _execute) -> None:
    clusters = _kind_clusters(execute)
    if GREEDY_CLUSTER_NAME not in clusters:
        return
    preflight(execute=execute)
    # The preflight proves exact nodes, context, namespaces, Pod ownership, and
    # worker placement before the only destructive operation is issued.
    execute(("kind", "delete", "cluster", "--name", GREEDY_CLUSTER_NAME), False)
