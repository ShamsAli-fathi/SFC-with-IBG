#!/usr/bin/env python3
"""Build/deploy the isolated MILP Kernel path and run one controller Job."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
from math import isfinite


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from MILP.cli import _positive_finite_cutoff, _positive_integer, _stage_count
from MILP.contracts import MILPConfiguration
from MILP.experiment_profile import (
    build_experiment_profile_from_runtime_states,
    experiment_profile_json,
)
from MILP.kernel_resources import build_milp_kernel_runtime_resources
from testbed.profiles import expand_profiles, load_profiles


IMAGE = "milp-testbed:kernel-phase5"
NAMESPACE = "milp-testbed"
FORWARDER_WORKERS_PER_REPLICA = 2


def _announce(message):
    print(f"MILP Kernel | {message}", flush=True)


def _preflight_lines(args):
    replica_pods = args.stage * args.replica
    serving_processes = replica_pods * (1 + FORWARDER_WORKERS_PER_REPLICA)
    planning_description = (
        f"planning-link={args.planning_link_ms:g}ms"
        if args.planning_link_ms is not None
        else f"planning-links={args.planning_links}"
    )
    lines = [
        (
            f"requested scale={args.flow} flows x {args.stage} stages x "
            f"{args.replica} replicas/stage; L=2"
        ),
        (
            f"topology={replica_pods} replica Pods / {replica_pods * 2} containers / "
            f"about {serving_processes} serving Uvicorn workers"
        ),
        f"solver cutoff={args.cutoff:g}s {planning_description} slot={args.slot_id}",
        (
            "admission="
            f"{args.assigned_flow_capacity or args.flow} assigned-flows/slot/replica "
            "(MILP-specific; legacy Exact capacity ignored)"
        ),
    ]
    if replica_pods > 6:
        lines.append(
            "capacity notice: this exceeds the live-validated 2x3x2 boundary; "
            "the solver will not start until every requested replica Pod is Ready"
        )
    return tuple(lines)


def _planning_link_document(args):
    if args.planning_links is not None:
        return json.loads(Path(args.planning_links).read_text(encoding="utf-8"))
    return {
        "contract_version": "milp-planning-links-v1",
        "uniform_cost_ms": args.planning_link_ms,
    }


def build_launcher_experiment_profile(args):
    configuration = MILPConfiguration.uniform(
        flow_count=args.flow,
        stage_count=args.stage,
        replicas_per_stage=args.replica,
        cutoff_seconds=args.cutoff,
    )
    base_profiles = load_profiles(ROOT / "deploy/kubernetes/profiles.json")
    runtime_profiles = expand_profiles(base_profiles, args.stage, args.replica)
    profile = build_experiment_profile_from_runtime_states(
        configuration,
        runtime_profiles=runtime_profiles,
        assigned_flow_capacity_per_replica=args.assigned_flow_capacity,
        planning_link_document=_planning_link_document(args),
        source_identity="deploy/kubernetes/profiles.json:state-only-v1",
    )
    return profile, runtime_profiles


def _run(command, *, input_text=None, capture=True):
    return subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        text=True,
        input=input_text,
        capture_output=capture,
    )


def _require_commands(*commands):
    missing = [command for command in commands if shutil.which(command) is None]
    if missing:
        raise RuntimeError(f"missing required command(s): {', '.join(missing)}")


def build_parser():
    parser = argparse.ArgumentParser(
        description="Run one coupled MILP slot in the isolated Kernel testbed."
    )
    parser.add_argument("--flow", type=_positive_integer, default=15)
    parser.add_argument("--stage", type=_stage_count, default=3)
    parser.add_argument("--replica", type=_positive_integer, default=10)
    parser.add_argument("--cutoff", type=_positive_finite_cutoff, required=True)
    planning = parser.add_mutually_exclusive_group(required=True)
    planning.add_argument(
        "--planning-link-ms",
        type=float,
        help=(
            "uniform nonnegative planning coefficient; with exact L=2 its "
            "per-flow objective deduction is constant"
        ),
    )
    planning.add_argument(
        "--planning-links",
        type=Path,
        help="complete versioned explicit directed planning-link JSON document",
    )
    parser.add_argument(
        "--assigned-flow-capacity",
        type=_positive_integer,
        default=None,
        metavar="FLOWS",
        help="MILP admission limit per replica in assigned flows per slot (default: --flow)",
    )
    parser.add_argument("--slot-id", type=_positive_integer, default=1)
    parser.add_argument("--cluster", default="ibg")
    parser.add_argument("--timeout", type=_positive_integer, default=900)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser


def _ensure_cluster(cluster):
    existing = _run(["kind", "get", "clusters"]).stdout.splitlines()
    if cluster not in existing:
        _announce(f"cluster kind-{cluster} is absent; creating it")
        _run(
            [
                "kind",
                "create",
                "cluster",
                "--name",
                cluster,
                "--config",
                str(ROOT / "deploy/kind/cluster.yaml"),
            ]
        )
    else:
        _announce(f"cluster kind-{cluster} already exists")


def _build_and_load(cluster):
    _announce(f"building isolated image {IMAGE}")
    _run(
        [
            "docker",
            "build",
            "--tag",
            IMAGE,
            "--file",
            str(ROOT / "deploy/milp-kubernetes/Dockerfile"),
            ".",
        ]
    )
    _announce(f"loading {IMAGE} into kind-{cluster}")
    _run(["kind", "load", "docker-image", "--name", cluster, IMAGE])


def _print_cluster_nodes(context):
    nodes = _run(
        [
            "kubectl",
            "--context",
            context,
            "get",
            "nodes",
            "-o",
            "custom-columns=NAME:.metadata.name,READY:.status.conditions[?(@.type=='Ready')].status,INTERNAL-IP:.status.addresses[?(@.type=='InternalIP')].address",
        ]
    ).stdout.rstrip()
    _announce("cluster nodes:")
    for line in nodes.splitlines():
        print(f"  {line}", flush=True)


def _print_runtime_status(context):
    statefulsets = _run(
        [
            "kubectl",
            "--context",
            context,
            "get",
            "statefulsets",
            "--namespace",
            NAMESPACE,
            "-o",
            "custom-columns=NAME:.metadata.name,READY:.status.readyReplicas,DESIRED:.spec.replicas",
        ]
    ).stdout.rstrip()
    _announce("replica rollout snapshot:")
    for line in statefulsets.splitlines():
        print(f"  {line}", flush=True)


def _apply_long_running(context, args, experiment_profile, runtime_profiles):
    deploy = ROOT / "deploy/milp-kubernetes"
    _announce(f"applying isolated namespace, RBAC, and flow generator in {NAMESPACE}")
    for name in ("namespace.yaml", "rbac.yaml", "flow-generator.yaml"):
        _run(["kubectl", "--context", context, "apply", "--filename", str(deploy / name)])
    experiment_document = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": "milp-experiment-profile", "namespace": NAMESPACE},
        "data": {
            "experiment.json": experiment_profile_json(experiment_profile)
        },
    }
    _run(
        ["kubectl", "--context", context, "apply", "--filename", "-"],
        input_text=json.dumps(experiment_document),
    )
    resources = build_milp_kernel_runtime_resources(
        runtime_profiles,
        num_of_stages=args.stage,
        num_of_replicas=args.replica,
        namespace=NAMESPACE,
        image=IMAGE,
    )
    _run(
        ["kubectl", "--context", context, "apply", "--filename", "-"],
        input_text=json.dumps(resources),
    )
    for stage in range(1, args.stage + 1):
        _announce(
            f"waiting for stage-{stage}: {args.replica} replica Pods to become Ready "
            f"(timeout={args.timeout}s; MILP has not started)"
        )
        _run(
            [
                "kubectl",
                "--context",
                context,
                "rollout",
                "status",
                f"statefulset/stage-{stage}",
                "--namespace",
                NAMESPACE,
                f"--timeout={args.timeout}s",
            ],
            capture=False,
        )
    _announce("waiting for MILP flow-generator Deployment to become Ready")
    _run(
        [
            "kubectl",
            "--context",
            context,
            "rollout",
            "status",
            "deployment/milp-flow-generator",
            "--namespace",
            NAMESPACE,
            f"--timeout={args.timeout}s",
        ],
        capture=False,
    )
    _print_runtime_status(context)


def _controller_job(args, name):
    controller_args = [
        "--flow",
        str(args.flow),
        "--stage",
        str(args.stage),
        "--replica",
        str(args.replica),
        "--cutoff",
        str(args.cutoff),
        "--slot-id",
        str(args.slot_id),
    ]
    if args.verbose:
        controller_args.append("--verbose")
    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": name, "namespace": NAMESPACE},
        "spec": {
            "backoffLimit": 0,
            "activeDeadlineSeconds": max(args.timeout, int(args.cutoff) + 300),
            "template": {
                "metadata": {
                    "labels": {
                        "app.kubernetes.io/name": "milp-controller",
                        "app.kubernetes.io/part-of": "milp-testbed",
                    }
                },
                "spec": {
                    "restartPolicy": "Never",
                    "serviceAccountName": "milp-controller",
                    "containers": [
                        {
                            "name": "controller",
                            "image": IMAGE,
                            "imagePullPolicy": "Never",
                            "command": ["python3", "-m", "MILP.kernel_controller"],
                            "args": controller_args,
                            "env": [
                                {
                                    "name": "POD_NAMESPACE",
                                    "valueFrom": {"fieldRef": {"fieldPath": "metadata.namespace"}},
                                },
                                {
                                    "name": "MILP_EXPERIMENT_PROFILE_PATH",
                                    "value": "/etc/milp/experiment.json",
                                },
                            ],
                            "volumeMounts": [
                                {
                                    "name": "experiment-profile",
                                    "mountPath": "/etc/milp",
                                    "readOnly": True,
                                },
                            ],
                            "resources": {
                                "requests": {"cpu": "100m", "memory": "256Mi"},
                                "limits": {"cpu": "2", "memory": "1Gi"},
                            },
                        }
                    ],
                    "volumes": [
                        {
                            "name": "experiment-profile",
                            "configMap": {"name": "milp-experiment-profile"},
                        },
                    ],
                },
            },
        },
    }


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.planning_link_ms is not None and (
        not isfinite(args.planning_link_ms) or args.planning_link_ms < 0.0
    ):
        raise ValueError("planning-link-ms must be finite and nonnegative")
    experiment_profile, runtime_profiles = build_launcher_experiment_profile(args)
    _require_commands("docker", "kind", "kubectl")
    for line in _preflight_lines(args):
        _announce(line)
    _announce(
        f"profile={experiment_profile.source} "
        f"fingerprint={experiment_profile.fingerprint} "
        f"link-mode={experiment_profile.planning_link_mode}"
    )
    if experiment_profile.uniform_planning_link_is_objective_constant:
        _announce(
            "uniform planning link is objective-constant: exact L=2 deducts "
            "the same configured value once per flow"
        )
    _ensure_cluster(args.cluster)
    if not args.skip_build:
        _build_and_load(args.cluster)
    else:
        _announce(f"skipping image build; using the image already loaded in kind-{args.cluster}")
    context = f"kind-{args.cluster}"
    _print_cluster_nodes(context)
    _apply_long_running(
        context,
        args,
        experiment_profile,
        runtime_profiles,
    )
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    job_name = f"milp-controller-{timestamp}"
    _announce(f"creating controller Job {job_name}; solver starts only after this point")
    _run(
        ["kubectl", "--context", context, "apply", "--filename", "-"],
        input_text=json.dumps(_controller_job(args, job_name)),
    )
    _announce(f"waiting for controller Job completion (timeout={max(args.timeout, int(args.cutoff) + 300)}s)")
    completed = _run(
        [
            "kubectl",
            "--context",
            context,
            "wait",
            "--for=condition=complete",
            f"job/{job_name}",
            "--namespace",
            NAMESPACE,
            f"--timeout={max(args.timeout, int(args.cutoff) + 300)}s",
        ],
        capture=False,
    )
    del completed
    logs = _run(
        [
            "kubectl",
            "--context",
            context,
            "logs",
            f"job/{job_name}",
            "--namespace",
            NAMESPACE,
        ]
    )
    print(logs.stdout, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
