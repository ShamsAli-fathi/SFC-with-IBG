"""MILP-owned Kubernetes resource definitions.

The current values intentionally match the established testbed footprint, but
they live here so future MILP rollout/resource work cannot change IBG-Exact.
"""

from __future__ import annotations

import json

from .kernel_contracts import MILP_TWO_HOP_ROUTE_CONTRACT_VERSION
from .kubernetes_api import MILP_REPLICA_APP_LABEL
from .runtime_profiles import (
    MILPRuntimeReplicaProfile,
    milp_runtime_profiles_document,
)


MILP_FORWARDER_APP = "MILP.kernel_route_forwarder:app"
MILP_PROCESSOR_APP = "testbed.cnf_service:app"
MILP_PROFILE_CONFIG_MAP = "milp-replica-profiles"
MILP_PROFILE_PATH = "/etc/milp/profiles.json"

# These are deliberately MILP-owned deployment values.  They describe one
# replica Pod regardless of the requested number of replicas per stage.
MILP_PROCESSOR_RESOURCES = {
    "requests": {"cpu": "50m", "memory": "64Mi"},
    "limits": {"cpu": "1", "memory": "256Mi"},
}
MILP_FORWARDER_RESOURCES = {
    "requests": {"cpu": "25m", "memory": "128Mi"},
    "limits": {"cpu": "1", "memory": "256Mi"},
}


def _labels(stage: int) -> dict[str, str]:
    return {
        "app.kubernetes.io/name": MILP_REPLICA_APP_LABEL,
        "app.kubernetes.io/part-of": "milp-testbed",
        "app.kubernetes.io/component": "replica-stage",
        "milp.stage": str(stage),
    }


def _stage_service(stage: int, namespace: str) -> dict[str, object]:
    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {
            "name": f"stage-{stage}",
            "namespace": namespace,
            "labels": _labels(stage),
        },
        "spec": {
            "clusterIP": "None",
            "selector": {
                "app.kubernetes.io/name": MILP_REPLICA_APP_LABEL,
                "milp.stage": str(stage),
            },
            "ports": [{"name": "http", "port": 8080, "targetPort": "http"}],
        },
    }


def _stage_stateful_set(
    stage: int,
    replicas: int,
    namespace: str,
    image: str,
) -> dict[str, object]:
    labels = _labels(stage)
    return {
        "apiVersion": "apps/v1",
        "kind": "StatefulSet",
        "metadata": {
            "name": f"stage-{stage}",
            "namespace": namespace,
            "labels": labels,
        },
        "spec": {
            "serviceName": f"stage-{stage}",
            "replicas": replicas,
            "podManagementPolicy": "Parallel",
            "selector": {
                "matchLabels": {
                    "app.kubernetes.io/name": MILP_REPLICA_APP_LABEL,
                    "milp.stage": str(stage),
                }
            },
            "template": {
                "metadata": {
                    "labels": labels,
                    "annotations": {
                        "milp.route-contract-version": MILP_TWO_HOP_ROUTE_CONTRACT_VERSION,
                    },
                },
                "spec": {
                    "automountServiceAccountToken": False,
                    "affinity": {
                        "podAntiAffinity": {
                            "preferredDuringSchedulingIgnoredDuringExecution": [
                                {
                                    "weight": 100,
                                    "podAffinityTerm": {
                                        "topologyKey": "kubernetes.io/hostname",
                                        "labelSelector": {
                                            "matchLabels": {
                                                "app.kubernetes.io/name": MILP_REPLICA_APP_LABEL,
                                                "milp.stage": str(stage),
                                            }
                                        },
                                    },
                                }
                            ]
                        }
                    },
                    "containers": [
                        {
                            "name": "replica",
                            "image": image,
                            "imagePullPolicy": "Never",
                            "command": [
                                "python3", "-m", "uvicorn", MILP_PROCESSOR_APP,
                                "--host", "0.0.0.0", "--port", "8081",
                            ],
                            "ports": [{"name": "processor", "containerPort": 8081}],
                            "env": [
                                {"name": "STAGE", "value": str(stage)},
                                {
                                    "name": "POD_NAME",
                                    "valueFrom": {"fieldRef": {"fieldPath": "metadata.name"}},
                                },
                                {"name": "REPLICA_PROFILES_PATH", "value": MILP_PROFILE_PATH},
                            ],
                            "volumeMounts": [
                                {"name": "profiles", "mountPath": "/etc/milp", "readOnly": True}
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
                            "resources": MILP_PROCESSOR_RESOURCES,
                        },
                        {
                            "name": "forwarder",
                            "image": image,
                            "imagePullPolicy": "Never",
                            "command": [
                                "python3", "-m", "uvicorn", MILP_FORWARDER_APP,
                                "--host", "0.0.0.0", "--port", "8080", "--workers", "2",
                                "--timeout-keep-alive", "30",
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
                            "resources": MILP_FORWARDER_RESOURCES,
                        },
                    ],
                    "volumes": [
                        {"name": "profiles", "configMap": {"name": MILP_PROFILE_CONFIG_MAP}}
                    ],
                },
            },
        },
    }


def build_milp_kernel_runtime_resources(
    profiles: dict[tuple[int, int], MILPRuntimeReplicaProfile],
    *,
    num_of_stages: int,
    num_of_replicas: int,
    namespace: str,
    image: str,
) -> dict[str, object]:
    """Build an isolated MILP-only replica deployment manifest."""

    profile_document = milp_runtime_profiles_document(profiles)
    profile_json = json.dumps(profile_document, sort_keys=True, separators=(",", ":"))
    items: list[dict[str, object]] = [
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": MILP_PROFILE_CONFIG_MAP, "namespace": namespace},
            "data": {"profiles.json": profile_json},
        }
    ]
    for stage in range(1, num_of_stages + 1):
        items.append(_stage_service(stage, namespace))
        items.append(
            _stage_stateful_set(
                stage,
                num_of_replicas,
                namespace,
                image,
            )
        )
    return {"apiVersion": "v1", "kind": "List", "items": items}
