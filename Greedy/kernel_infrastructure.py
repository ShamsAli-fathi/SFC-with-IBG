"""Deterministic, offline-only Greedy Kubernetes resource construction.

The module creates no files and executes no cluster or container command.  JSON
is emitted because it is also valid Kubernetes YAML and can be parsed without
adding a deployment-time YAML dependency to the controller or service images.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from numbers import Integral
from typing import Mapping, Sequence

from .contracts import GreedyConfiguration, ReplicaIdentity
from .kernel_contracts import (
    DEFAULT_GREEDY_KERNEL_OWNERSHIP,
    GreedyKernelControllerConfiguration,
)
from .kernel_controller_config import (
    GREEDY_KERNEL_CONTROLLER_INPUT_VERSION,
    GreedyKernelControllerInputDocument,
    controller_input_document_to_mapping,
)
from .kernel_runtime_profiles import (
    GREEDY_KERNEL_RUNTIME_PROFILE_VERSION,
    GreedyKernelRuntimeProfileDocument,
    runtime_profile_document_from_mapping,
    runtime_profile_document_to_mapping,
)


GREEDY_STATIC_DEPLOYMENT_VERSION = "greedy-static-kubernetes-v1"
GREEDY_STATIC_INPUT_VERSION = "greedy-static-deployment-input-v1"
GREEDY_STATIC_RENDER_VERSION = "greedy-json-yaml-render-v1"

GREEDY_NAMESPACE = "greedy-testbed"
GREEDY_PART_OF = "greedy-testbed"
GREEDY_WORKLOAD_NODE_LABEL = "greedy.workload-node"
GREEDY_SERVICE_ACCOUNT = "greedy-controller"
GREEDY_DISCOVERY_ROLE = "greedy-replica-discovery"
GREEDY_FLOW_GENERATOR = "greedy-flow-generator"
GREEDY_RUNTIME_PROFILE_CONFIG_MAP = "greedy-runtime-profiles"
GREEDY_CONTROLLER_INPUT_CONFIG_MAP = "greedy-controller-inputs"
GREEDY_CONTROLLER_JOB = "greedy-controller"
GREEDY_SERVICE_IMAGE = "greedy-testbed:kernel-service-v1"
GREEDY_CONTROLLER_IMAGE = "greedy-testbed:kernel-controller-v1"


class GreedyInfrastructureError(ValueError):
    """Static image, resource, readiness, or resource-preflight drift."""


def _integer(name: str, value: int, *, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise TypeError(f"{name} must be an integer")
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return int(value)


@dataclass(frozen=True)
class ContainerResources:
    cpu_request: str
    memory_request: str
    cpu_limit: str
    memory_limit: str

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str) and value
            for value in (
                self.cpu_request,
                self.memory_request,
                self.cpu_limit,
                self.memory_limit,
            )
        ):
            raise GreedyInfrastructureError("resource values must be nonempty strings")

    def kubernetes(self) -> dict[str, dict[str, str]]:
        return {
            "requests": {"cpu": self.cpu_request, "memory": self.memory_request},
            "limits": {"cpu": self.cpu_limit, "memory": self.memory_limit},
        }


PRIVATE_PROCESSOR_RESOURCES = ContainerResources("50m", "128Mi", "1", "768Mi")
PUBLIC_FORWARDER_RESOURCES = ContainerResources("25m", "128Mi", "1", "256Mi")
FLOW_GENERATOR_RESOURCES = ContainerResources("50m", "128Mi", "1", "768Mi")
CONTROLLER_RESOURCES = ContainerResources("2", "256Mi", "4", "1Gi")


@dataclass(frozen=True)
class GreedyStaticDeploymentInput:
    runtime_profiles: GreedyKernelRuntimeProfileDocument
    experiment_id: int
    root_seed: int
    profile_seed: int
    max_iterations: int
    first_slot_id: int
    source_identity: str
    contract_version: str = GREEDY_STATIC_INPUT_VERSION

    def __post_init__(self) -> None:
        if not isinstance(
            self.runtime_profiles, GreedyKernelRuntimeProfileDocument
        ):
            raise TypeError(
                "runtime_profiles must be GreedyKernelRuntimeProfileDocument"
            )
        for name, minimum in (
            ("experiment_id", 1),
            ("root_seed", 0),
            ("profile_seed", 0),
            ("max_iterations", 1),
            ("first_slot_id", 1),
        ):
            object.__setattr__(
                self, name, _integer(name, getattr(self, name), minimum=minimum)
            )
        if not isinstance(self.source_identity, str) or not self.source_identity:
            raise ValueError("source_identity must be a nonempty string")
        if self.contract_version != GREEDY_STATIC_INPUT_VERSION:
            raise GreedyInfrastructureError(
                "unexpected Greedy static-deployment input version"
            )

    @property
    def configuration(self) -> GreedyConfiguration:
        return self.runtime_profiles.configuration

    @property
    def controller_document(self) -> GreedyKernelControllerInputDocument:
        return GreedyKernelControllerInputDocument(
            controller=GreedyKernelControllerConfiguration(
                configuration=self.configuration,
                experiment_id=self.experiment_id,
                root_seed=self.root_seed,
                profile_seed=self.profile_seed,
                runtime_profile_fingerprint=self.runtime_profiles.fingerprint,
                max_iterations=self.max_iterations,
                first_slot_id=self.first_slot_id,
            ),
            source_identity=f"{self.source_identity}:controller-inputs",
        )


def static_deployment_input_from_mapping(
    value: Mapping[str, object],
) -> GreedyStaticDeploymentInput:
    if not isinstance(value, Mapping):
        raise ValueError("static deployment input must be a mapping")
    required = {
        "contract_version",
        "source_identity",
        "configuration",
        "profiles",
        "experiment_id",
        "root_seed",
        "profile_seed",
        "max_iterations",
        "first_slot_id",
    }
    if set(value) != required:
        raise ValueError("static deployment input fields are incomplete or unexpected")
    runtime = runtime_profile_document_from_mapping(
        {
            "contract_version": GREEDY_KERNEL_RUNTIME_PROFILE_VERSION,
            "source_identity": f"{value['source_identity']}:runtime-profiles",
            "configuration": value["configuration"],
            "profiles": value["profiles"],
        }
    )
    return GreedyStaticDeploymentInput(
        runtime_profiles=runtime,
        experiment_id=value["experiment_id"],
        root_seed=value["root_seed"],
        profile_seed=value["profile_seed"],
        max_iterations=value["max_iterations"],
        first_slot_id=value["first_slot_id"],
        source_identity=value["source_identity"],
        contract_version=value["contract_version"],
    )


@dataclass(frozen=True)
class GreedyServingReadiness:
    """Exact Ready identity token required before rendering a controller Job."""

    configuration: GreedyConfiguration
    ready_identities: tuple[ReplicaIdentity, ...]
    flow_generator_ready: bool

    def __post_init__(self) -> None:
        if not isinstance(self.configuration, GreedyConfiguration):
            raise TypeError("configuration must be GreedyConfiguration")
        identities = tuple(self.ready_identities)
        object.__setattr__(self, "ready_identities", identities)
        expected = tuple(
            ReplicaIdentity(stage, replica)
            for stage in self.configuration.stages
            for replica in self.configuration.replica_ids
        )
        if identities != expected:
            raise GreedyInfrastructureError(
                "controller Job requires exact canonical Ready replica coverage"
            )
        if self.flow_generator_ready is not True:
            raise GreedyInfrastructureError(
                "controller Job requires a Ready flow generator"
            )


@dataclass(frozen=True)
class GreedyWorkerAllocatable:
    cpu_millicores: int
    memory_mib: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "cpu_millicores",
            _integer("cpu_millicores", self.cpu_millicores),
        )
        object.__setattr__(
            self, "memory_mib", _integer("memory_mib", self.memory_mib)
        )


@dataclass(frozen=True)
class GreedyWorkerRequests:
    cpu_millicores: int
    memory_mib: int
    serving_pods: int


def required_worker_requests(
    configuration: GreedyConfiguration,
) -> GreedyWorkerRequests:
    if not isinstance(configuration, GreedyConfiguration):
        raise TypeError("configuration must be GreedyConfiguration")
    serving_pods = configuration.num_stages * configuration.num_replicas
    return GreedyWorkerRequests(
        # Each replica Pod is 50m + 25m; flow generator is 50m; controller is 2 CPU.
        cpu_millicores=(serving_pods * 75) + 50 + 2000,
        # Each replica Pod is 128Mi + 128Mi; generator 128Mi; controller 256Mi.
        memory_mib=(serving_pods * 256) + 128 + 256,
        serving_pods=serving_pods,
    )


def require_worker_resources(
    configuration: GreedyConfiguration,
    allocatable: GreedyWorkerAllocatable,
) -> GreedyWorkerRequests:
    required = required_worker_requests(configuration)
    if allocatable.cpu_millicores < required.cpu_millicores:
        raise GreedyInfrastructureError(
            "worker allocatable CPU is below Greedy serving plus controller requests"
        )
    if allocatable.memory_mib < required.memory_mib:
        raise GreedyInfrastructureError(
            "worker allocatable memory is below Greedy serving plus controller requests"
        )
    return required


def _labels(name: str, component: str) -> dict[str, str]:
    return {
        "app.kubernetes.io/name": name,
        "app.kubernetes.io/part-of": GREEDY_PART_OF,
        "app.kubernetes.io/component": component,
    }


def _pod_security_context() -> dict[str, object]:
    return {
        "runAsNonRoot": True,
        "runAsUser": 10001,
        "runAsGroup": 10001,
        "seccompProfile": {"type": "RuntimeDefault"},
    }


def _container_security_context() -> dict[str, object]:
    return {
        "allowPrivilegeEscalation": False,
        "readOnlyRootFilesystem": True,
        "capabilities": {"drop": ["ALL"]},
    }


def _runtime_config_map(deployment: GreedyStaticDeploymentInput) -> dict[str, object]:
    return {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": GREEDY_RUNTIME_PROFILE_CONFIG_MAP,
            "namespace": GREEDY_NAMESPACE,
            "labels": _labels(GREEDY_RUNTIME_PROFILE_CONFIG_MAP, "runtime-profile"),
        },
        "data": {
            "runtime-profiles.json": json.dumps(
                runtime_profile_document_to_mapping(deployment.runtime_profiles),
                sort_keys=True,
                separators=(",", ":"),
            )
        },
    }


def _controller_config_map(
    deployment: GreedyStaticDeploymentInput,
) -> dict[str, object]:
    return {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": GREEDY_CONTROLLER_INPUT_CONFIG_MAP,
            "namespace": GREEDY_NAMESPACE,
            "labels": _labels(GREEDY_CONTROLLER_INPUT_CONFIG_MAP, "controller-input"),
        },
        "data": {
            "controller-inputs.json": json.dumps(
                controller_input_document_to_mapping(
                    deployment.controller_document
                ),
                sort_keys=True,
                separators=(",", ":"),
            )
        },
    }


def _flow_generator_resources() -> tuple[dict[str, object], ...]:
    labels = _labels(GREEDY_FLOW_GENERATOR, "flow-generator")
    service = {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {
            "name": GREEDY_FLOW_GENERATOR,
            "namespace": GREEDY_NAMESPACE,
            "labels": labels,
        },
        "spec": {
            "selector": {"app.kubernetes.io/name": GREEDY_FLOW_GENERATOR},
            "ports": [{"name": "http", "port": 8080, "targetPort": "http"}],
        },
    }
    deployment = {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": GREEDY_FLOW_GENERATOR,
            "namespace": GREEDY_NAMESPACE,
            "labels": labels,
        },
        "spec": {
            "replicas": 1,
            "selector": {
                "matchLabels": {"app.kubernetes.io/name": GREEDY_FLOW_GENERATOR}
            },
            "template": {
                "metadata": {"labels": labels},
                "spec": {
                    "automountServiceAccountToken": False,
                    "nodeSelector": {GREEDY_WORKLOAD_NODE_LABEL: "true"},
                    "securityContext": _pod_security_context(),
                    "containers": [
                        {
                            "name": "flow-generator",
                            "image": GREEDY_SERVICE_IMAGE,
                            "imagePullPolicy": "Never",
                            "command": [
                                "python3",
                                "-m",
                                "uvicorn",
                                "Greedy.kernel_flow_generator:app",
                                "--host",
                                "0.0.0.0",
                                "--port",
                                "8080",
                            ],
                            "ports": [{"name": "http", "containerPort": 8080}],
                            "readinessProbe": {
                                "httpGet": {"path": "/health", "port": "http"},
                                "periodSeconds": 2,
                                "failureThreshold": 30,
                            },
                            "livenessProbe": {
                                "httpGet": {"path": "/health", "port": "http"},
                                "initialDelaySeconds": 10,
                                "periodSeconds": 10,
                            },
                            "resources": FLOW_GENERATOR_RESOURCES.kubernetes(),
                            "securityContext": _container_security_context(),
                        }
                    ],
                },
            },
        },
    }
    return service, deployment


def _stage_resources(
    deployment: GreedyStaticDeploymentInput,
    stage: int,
) -> tuple[dict[str, object], ...]:
    configuration = deployment.configuration
    ownership = DEFAULT_GREEDY_KERNEL_OWNERSHIP
    name = ownership.stage_name(stage)
    labels = dict(
        ownership.replica_labels(
            stage, configuration.admission_capacity_per_replica
        )
    )
    selector = {
        "app.kubernetes.io/name": ownership.replica_name_label,
        ownership.stage_label_key: str(stage),
    }
    service = {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {
            "name": name,
            "namespace": GREEDY_NAMESPACE,
            "labels": labels,
        },
        "spec": {
            "clusterIP": "None",
            "selector": selector,
            "ports": [{"name": "http", "port": 8080, "targetPort": "http"}],
        },
    }
    pod_spec = {
        "automountServiceAccountToken": False,
        "nodeSelector": {GREEDY_WORKLOAD_NODE_LABEL: "true"},
        "securityContext": _pod_security_context(),
        "containers": [
            {
                "name": "private-processor",
                "image": GREEDY_SERVICE_IMAGE,
                "imagePullPolicy": "Never",
                "command": [
                    "python3",
                    "-m",
                    "uvicorn",
                    "Greedy.kernel_processor_service:app",
                    "--host",
                    "0.0.0.0",
                    "--port",
                    "8081",
                ],
                "ports": [{"name": "processor", "containerPort": 8081}],
                "env": [
                    {"name": "STAGE", "value": str(stage)},
                    {
                        "name": "POD_NAME",
                        "valueFrom": {"fieldRef": {"fieldPath": "metadata.name"}},
                    },
                    {
                        "name": "GREEDY_RUNTIME_PROFILES_PATH",
                        "value": "/etc/greedy/runtime-profiles.json",
                    },
                ],
                "volumeMounts": [
                    {
                        "name": "runtime-profiles",
                        "mountPath": "/etc/greedy",
                        "readOnly": True,
                    }
                ],
                "readinessProbe": {
                    "httpGet": {"path": "/warmup", "port": "processor"},
                    "periodSeconds": 2,
                    "failureThreshold": 30,
                },
                "livenessProbe": {
                    "httpGet": {"path": "/health", "port": "processor"},
                    "initialDelaySeconds": 10,
                    "periodSeconds": 10,
                },
                "resources": PRIVATE_PROCESSOR_RESOURCES.kubernetes(),
                "securityContext": _container_security_context(),
            },
            {
                "name": "public-forwarder",
                "image": GREEDY_SERVICE_IMAGE,
                "imagePullPolicy": "Never",
                "command": [
                    "python3",
                    "-m",
                    "uvicorn",
                    "Greedy.kernel_route_forwarder_service:app",
                    "--host",
                    "0.0.0.0",
                    "--port",
                    "8080",
                    "--workers",
                    "2",
                    "--timeout-keep-alive",
                    "30",
                ],
                "ports": [{"name": "http", "containerPort": 8080}],
                "env": [
                    {"name": "STAGE", "value": str(stage)},
                    {
                        "name": "POD_NAME",
                        "valueFrom": {"fieldRef": {"fieldPath": "metadata.name"}},
                    },
                    {"name": "PROCESSOR_URL", "value": "http://127.0.0.1:8081"},
                    {"name": "FORWARDER_KEEPALIVE_SECONDS", "value": "30"},
                ],
                "readinessProbe": {
                    "httpGet": {"path": "/health", "port": "http"},
                    "periodSeconds": 2,
                    "failureThreshold": 30,
                },
                "livenessProbe": {
                    "httpGet": {"path": "/health", "port": "http"},
                    "initialDelaySeconds": 10,
                    "periodSeconds": 10,
                },
                "resources": PUBLIC_FORWARDER_RESOURCES.kubernetes(),
                "securityContext": _container_security_context(),
            },
        ],
        "volumes": [
            {
                "name": "runtime-profiles",
                "configMap": {"name": GREEDY_RUNTIME_PROFILE_CONFIG_MAP},
            }
        ],
    }
    stateful_set = {
        "apiVersion": "apps/v1",
        "kind": "StatefulSet",
        "metadata": {
            "name": name,
            "namespace": GREEDY_NAMESPACE,
            "labels": labels,
        },
        "spec": {
            "serviceName": name,
            "replicas": configuration.num_replicas,
            "podManagementPolicy": "Parallel",
            "selector": {"matchLabels": selector},
            "template": {"metadata": {"labels": labels}, "spec": pod_spec},
        },
    }
    return service, stateful_set


def _build_long_running_resources(
    deployment: GreedyStaticDeploymentInput,
) -> tuple[dict[str, object], ...]:
    namespace = {
        "apiVersion": "v1",
        "kind": "Namespace",
        "metadata": {
            "name": GREEDY_NAMESPACE,
            "labels": {"app.kubernetes.io/part-of": GREEDY_PART_OF},
        },
    }
    service_account = {
        "apiVersion": "v1",
        "kind": "ServiceAccount",
        "metadata": {
            "name": GREEDY_SERVICE_ACCOUNT,
            "namespace": GREEDY_NAMESPACE,
            "labels": _labels(GREEDY_SERVICE_ACCOUNT, "controller-rbac"),
        },
        "automountServiceAccountToken": True,
    }
    role = {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "Role",
        "metadata": {
            "name": GREEDY_DISCOVERY_ROLE,
            "namespace": GREEDY_NAMESPACE,
            "labels": _labels(GREEDY_DISCOVERY_ROLE, "controller-rbac"),
        },
        "rules": [{"apiGroups": [""], "resources": ["pods"], "verbs": ["get", "list"]}],
    }
    role_binding = {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "RoleBinding",
        "metadata": {
            "name": "greedy-controller-discovers-replicas",
            "namespace": GREEDY_NAMESPACE,
            "labels": _labels(
                "greedy-controller-discovers-replicas", "controller-rbac"
            ),
        },
        "subjects": [
            {
                "kind": "ServiceAccount",
                "name": GREEDY_SERVICE_ACCOUNT,
                "namespace": GREEDY_NAMESPACE,
            }
        ],
        "roleRef": {
            "apiGroup": "rbac.authorization.k8s.io",
            "kind": "Role",
            "name": GREEDY_DISCOVERY_ROLE,
        },
    }
    resources = [
        namespace,
        service_account,
        role,
        role_binding,
        _runtime_config_map(deployment),
        _controller_config_map(deployment),
        *_flow_generator_resources(),
    ]
    for stage in deployment.configuration.stages:
        resources.extend(_stage_resources(deployment, stage))
    return tuple(resources)


def render_long_running_resources(
    deployment: GreedyStaticDeploymentInput,
) -> tuple[dict[str, object], ...]:
    if not isinstance(deployment, GreedyStaticDeploymentInput):
        raise TypeError("deployment must be GreedyStaticDeploymentInput")
    resources = _build_long_running_resources(deployment)
    validate_long_running_resources(deployment, resources)
    return resources


def validate_long_running_resources(
    deployment: GreedyStaticDeploymentInput,
    resources: Sequence[Mapping[str, object]],
) -> None:
    actual = tuple(resources)
    expected = _build_long_running_resources(deployment)
    if actual != expected:
        raise GreedyInfrastructureError(
            "long-running resources differ from the canonical Greedy render"
        )
    if any(resource.get("kind") == "Job" for resource in actual):
        raise GreedyInfrastructureError(
            "the controller Job must not be in long-running resources"
        )


def render_controller_job(
    deployment: GreedyStaticDeploymentInput,
    readiness: GreedyServingReadiness | None,
) -> dict[str, object]:
    if readiness is None:
        raise GreedyInfrastructureError(
            "controller Job rendering requires completed serving readiness"
        )
    if readiness.configuration != deployment.configuration:
        raise GreedyInfrastructureError(
            "controller Job readiness topology does not match deployment"
        )
    labels = _labels(GREEDY_CONTROLLER_JOB, "controller")
    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "name": GREEDY_CONTROLLER_JOB,
            "namespace": GREEDY_NAMESPACE,
            "labels": labels,
        },
        "spec": {
            "backoffLimit": 0,
            "activeDeadlineSeconds": 600,
            "template": {
                "metadata": {"labels": labels},
                "spec": {
                    "restartPolicy": "Never",
                    "serviceAccountName": GREEDY_SERVICE_ACCOUNT,
                    "automountServiceAccountToken": True,
                    "nodeSelector": {GREEDY_WORKLOAD_NODE_LABEL: "true"},
                    "securityContext": _pod_security_context(),
                    "containers": [
                        {
                            "name": "controller",
                            "image": GREEDY_CONTROLLER_IMAGE,
                            "imagePullPolicy": "Never",
                            "command": [
                                "python3",
                                "-m",
                                "Greedy.kernel_controller_service",
                            ],
                            "env": [
                                {
                                    "name": "GREEDY_CONTROLLER_INPUTS_PATH",
                                    "value": "/etc/greedy-controller/controller-inputs.json",
                                },
                                {
                                    "name": "FLOW_GENERATOR_URL",
                                    "value": (
                                        "http://greedy-flow-generator.greedy-testbed."
                                        "svc.cluster.local.:8080"
                                    ),
                                },
                            ],
                            "volumeMounts": [
                                {
                                    "name": "controller-inputs",
                                    "mountPath": "/etc/greedy-controller",
                                    "readOnly": True,
                                }
                            ],
                            "resources": CONTROLLER_RESOURCES.kubernetes(),
                            "securityContext": _container_security_context(),
                        }
                    ],
                    "volumes": [
                        {
                            "name": "controller-inputs",
                            "configMap": {
                                "name": GREEDY_CONTROLLER_INPUT_CONFIG_MAP
                            },
                        }
                    ],
                },
            },
        },
    }


def render_kind_configuration() -> dict[str, object]:
    return {
        "kind": "Cluster",
        "apiVersion": "kind.x-k8s.io/v1alpha4",
        "nodes": [
            {"role": "control-plane"},
            {
                "role": "worker",
                "labels": {GREEDY_WORKLOAD_NODE_LABEL: "true"},
            },
        ],
    }


def render_resource_documents(resources: Sequence[Mapping[str, object]]) -> str:
    documents = tuple(resources)
    if not documents:
        raise GreedyInfrastructureError("at least one resource is required")
    return "\n---\n".join(
        json.dumps(document, indent=2, sort_keys=True) for document in documents
    ) + "\n"


def parse_resource_documents(text: str) -> tuple[dict[str, object], ...]:
    if not isinstance(text, str) or not text.strip():
        raise GreedyInfrastructureError("rendered resources must not be empty")
    try:
        documents = tuple(
            json.loads(part) for part in text.strip().split("\n---\n")
        )
    except json.JSONDecodeError as error:
        raise GreedyInfrastructureError("rendered resources are invalid JSON/YAML") from error
    if not all(isinstance(document, dict) for document in documents):
        raise GreedyInfrastructureError("each rendered resource must be an object")
    return documents


def assert_phase4_contract_versions() -> None:
    if GREEDY_NAMESPACE != DEFAULT_GREEDY_KERNEL_OWNERSHIP.namespace:
        raise GreedyInfrastructureError("Phase 3 and Phase 4 namespaces drifted")
    if GREEDY_PART_OF != DEFAULT_GREEDY_KERNEL_OWNERSHIP.part_of_label:
        raise GreedyInfrastructureError("Phase 3 and Phase 4 ownership labels drifted")
    if GREEDY_KERNEL_CONTROLLER_INPUT_VERSION != "greedy-kernel-controller-inputs-v1":
        raise GreedyInfrastructureError("controller input version drifted")


assert_phase4_contract_versions()
