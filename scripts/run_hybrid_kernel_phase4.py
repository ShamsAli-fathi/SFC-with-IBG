#!/usr/bin/env python3
"""Run the small Hybrid Kernel gate in a persistent Hybrid-only kind cluster."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Callable, Mapping, Sequence


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
SERVICE_IMAGE = "ibg-hybrid-testbed:kernel-service-v1"
CONTROLLER_IMAGE = "ibg-hybrid-testbed:kernel-controller-v1"
EXPECTED_NODE_NAMES = frozenset({"ibg-hybrid-control-plane"})
SYSTEM_POD_NAMESPACES = frozenset({"kube-system", "local-path-storage"})
FORBIDDEN_NAMESPACES = frozenset({"ibg-testbed", "milp-testbed"})
EXPECTED_SERVING_PODS = frozenset(
    {
        "hybrid-stage-1-0",
        "hybrid-stage-2-0",
        "hybrid-stage-3-0",
    }
)

Command = tuple[str, ...]
Executor = Callable[[Command, bool], str]


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


def _require_local_images(execute: Executor, *, include_node: bool) -> None:
    images = [SERVICE_IMAGE, CONTROLLER_IMAGE]
    if include_node:
        images.insert(0, KIND_NODE_IMAGE)
    for image in images:
        execute(("docker", "image", "inspect", image), True)


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


def _validate_serving_pods(document: Mapping[str, object]) -> None:
    items = document.get("items")
    if not isinstance(items, list):
        raise RuntimeError("Hybrid serving Pod inventory has no item list")
    stage_pods = {
        item.get("metadata", {}).get("name")
        for item in items
        if isinstance(item, dict)
        and isinstance(item.get("metadata"), dict)
        and str(item["metadata"].get("name", "")).startswith("hybrid-stage-")
    }
    flow_generators = [
        item
        for item in items
        if isinstance(item, dict)
        and isinstance(item.get("metadata"), dict)
        and str(item["metadata"].get("name", "")).startswith(
            "ibg-hybrid-flow-generator-"
        )
    ]
    if stage_pods != EXPECTED_SERVING_PODS or len(flow_generators) != 1:
        raise RuntimeError(
            "refusing incomplete or unexpected Hybrid serving Pod inventory"
        )
    serving = [
        item
        for item in items
        if isinstance(item, dict)
        and isinstance(item.get("metadata"), dict)
        and (
            item["metadata"].get("name") in EXPECTED_SERVING_PODS
            or str(item["metadata"].get("name", "")).startswith(
                "ibg-hybrid-flow-generator-"
            )
        )
    ]
    if len(serving) != 4 or not all(_pod_ready(item) for item in serving):
        raise RuntimeError("Hybrid serving Pods are not all Running and Ready")


def run_small(
    *,
    execute: Executor = _execute,
) -> None:
    cluster_exists = CLUSTER_NAME in _kind_clusters(execute)
    _require_local_images(execute, include_node=not cluster_exists)
    if cluster_exists:
        preflight(execute=execute)
    else:
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
    execute(_kubectl("apply", "-k", str(OVERLAY)), False)
    execute(
        _kubectl(
            "rollout",
            "restart",
            "statefulset/hybrid-stage-1",
            "statefulset/hybrid-stage-2",
            "statefulset/hybrid-stage-3",
            "deployment/ibg-hybrid-flow-generator",
            "-n",
            HYBRID_NAMESPACE,
        ),
        False,
    )
    for resource in (
        "statefulset/hybrid-stage-1",
        "statefulset/hybrid-stage-2",
        "statefulset/hybrid-stage-3",
        "deployment/ibg-hybrid-flow-generator",
    ):
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
    _validate_serving_pods(
        _json_output(
            execute,
            _kubectl(
                "get",
                "pods",
                "-n",
                HYBRID_NAMESPACE,
                "-o",
                "json",
            ),
        )
    )
    preflight(execute=execute)
    execute(
        _kubectl(
            "delete",
            "job",
            "ibg-hybrid-controller-phase4-small",
            "-n",
            HYBRID_NAMESPACE,
            "--ignore-not-found",
            "--wait=true",
        ),
        False,
    )
    execute(_kubectl("apply", "-f", str(CONTROLLER_JOB)), False)
    execute(
        _kubectl(
            "wait",
            "-n",
            HYBRID_NAMESPACE,
            "--for=condition=complete",
            "job/ibg-hybrid-controller-phase4-small",
            "--timeout=600s",
        ),
        False,
    )
    output = execute(
        _kubectl(
            "logs",
            "-n",
            HYBRID_NAMESPACE,
            "job/ibg-hybrid-controller-phase4-small",
        ),
        True,
    )
    print(output, end="" if output.endswith("\n") else "\n")


def cleanup(*, execute: Executor = _execute) -> None:
    if CLUSTER_NAME in _kind_clusters(execute):
        execute(("kind", "delete", "cluster", "--name", CLUSTER_NAME), False)


def parse_args(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Operate only the persistent single-node Hybrid kind cluster; "
            "never starts or targets the shared ibg cluster."
        )
    )
    subparsers = parser.add_subparsers(dest="action", required=True)
    subparsers.add_parser("run-small")
    subparsers.add_parser("preflight")
    subparsers.add_parser("cleanup")
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_args(arguments)
    try:
        if args.action == "run-small":
            run_small()
        elif args.action == "preflight":
            preflight()
        else:
            cleanup()
    except (json.JSONDecodeError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Hybrid cluster isolation failure: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
