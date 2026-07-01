import hashlib
import json

from testbed.profiles import profiles_document


def _labels(stage):
    return {
        "app.kubernetes.io/name": "ibg-replica",
        "app.kubernetes.io/part-of": "ibg-testbed",
        "app.kubernetes.io/component": "replica-stage",
        "ibg.stage": str(stage),
    }


def _stage_service(stage, namespace):
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
                "app.kubernetes.io/name": "ibg-replica",
                "ibg.stage": str(stage),
            },
            "ports": [{"name": "http", "port": 8080, "targetPort": "http"}],
        },
    }


def _stage_stateful_set(
    stage,
    replicas,
    namespace,
    image,
    profile_hash,
):
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
                    "app.kubernetes.io/name": "ibg-replica",
                    "ibg.stage": str(stage),
                }
            },
            "template": {
                "metadata": {
                    "labels": labels,
                    "annotations": {"ibg.profile-hash": profile_hash},
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
                                                "app.kubernetes.io/name": "ibg-replica",
                                                "ibg.stage": str(stage),
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
                            "ports": [{"name": "http", "containerPort": 8080}],
                            "env": [
                                {"name": "STAGE", "value": str(stage)},
                                {
                                    "name": "POD_NAME",
                                    "valueFrom": {
                                        "fieldRef": {"fieldPath": "metadata.name"}
                                    },
                                },
                                {
                                    "name": "REPLICA_PROFILES_PATH",
                                    "value": "/etc/ibg/profiles.json",
                                },
                            ],
                            "volumeMounts": [
                                {
                                    "name": "profiles",
                                    "mountPath": "/etc/ibg",
                                    "readOnly": True,
                                }
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
                            "resources": {
                                "requests": {"cpu": "50m", "memory": "128Mi"},
                                "limits": {"cpu": "1", "memory": "768Mi"},
                            },
                        }
                    ],
                    "volumes": [
                        {
                            "name": "profiles",
                            "configMap": {"name": "replica-profiles"},
                        }
                    ],
                },
            },
        },
    }


def build_runtime_resources(
    profiles,
    *,
    num_of_stages,
    num_of_replicas,
    namespace="ibg-testbed",
    image="ibg-testbed:phase6",
):
    document = profiles_document(profiles)
    profile_json = json.dumps(document, sort_keys=True, separators=(",", ":"))
    profile_hash = hashlib.sha256(profile_json.encode("utf-8")).hexdigest()[:16]
    items = [
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": "replica-profiles", "namespace": namespace},
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
                profile_hash,
            )
        )
    return {"apiVersion": "v1", "kind": "List", "items": items}
