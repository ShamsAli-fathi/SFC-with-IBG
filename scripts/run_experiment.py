#!/usr/bin/env python3
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
IMAGE = "ibg-testbed:phase6"
NAMESPACE = "ibg-testbed"
JOB_NAME = "ibg-experiment"


def command_text(command):
    return " ".join(str(part) for part in command)


def run(command, *, capture=False, input_text=None):
    print(f"$ {command_text(command)}", flush=True)
    return subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        text=True,
        input=input_text,
        capture_output=capture,
    )


def require_commands(*commands):
    missing = [command for command in commands if shutil.which(command) is None]
    if missing:
        raise RuntimeError(f"missing required command(s): {', '.join(missing)}")


def ensure_cluster(cluster_name):
    clusters = run(["kind", "get", "clusters"], capture=True).stdout.splitlines()
    if cluster_name in clusters:
        print(f"kind cluster '{cluster_name}' already exists")
        return
    run(
        [
            "kind",
            "create",
            "cluster",
            "--name",
            cluster_name,
            "--config",
            str(ROOT / "deploy/kind/cluster.yaml"),
        ]
    )


def build_and_load_image(cluster_name):
    run(
        [
            "docker",
            "build",
            "--tag",
            IMAGE,
            "--file",
            str(ROOT / "deploy/local/Dockerfile"),
            ".",
        ]
    )
    run(["kind", "load", "docker-image", "--name", cluster_name, IMAGE])


def deploy_workloads(context, timeout, restart):
    run(["kubectl", "--context", context, "apply", "-k", "deploy/kubernetes"])
    if restart:
        run(
            [
                "kubectl",
                "--context",
                context,
                "rollout",
                "restart",
                "statefulset/stage-1",
                "statefulset/stage-2",
                "statefulset/stage-3",
                "deployment/flow-generator",
                "--namespace",
                NAMESPACE,
            ]
        )
    for stateful_set in ("stage-1", "stage-2", "stage-3"):
        run(
            [
                "kubectl",
                "--context",
                context,
                "rollout",
                "status",
                f"statefulset/{stateful_set}",
                "--namespace",
                NAMESPACE,
                f"--timeout={timeout}s",
            ]
        )
    run(
        [
            "kubectl",
            "--context",
            context,
            "rollout",
            "status",
            "deployment/flow-generator",
            "--namespace",
            NAMESPACE,
            f"--timeout={timeout}s",
        ]
    )


def set_env(container, name, value):
    for item in container.setdefault("env", []):
        if item.get("name") == name:
            item.clear()
            item.update({"name": name, "value": str(value)})
            return
    container["env"].append({"name": name, "value": str(value)})


def start_experiment_job(context, seed, max_iterations, timeout):
    rendered = run(
        [
            "kubectl",
            "create",
            "--dry-run=client",
            "--filename",
            str(ROOT / "deploy/kubernetes/controller-job.yaml"),
            "--output",
            "json",
        ],
        capture=True,
    ).stdout
    job = json.loads(rendered)
    job["metadata"]["name"] = JOB_NAME
    job["spec"]["activeDeadlineSeconds"] = timeout
    container = job["spec"]["template"]["spec"]["containers"][0]
    set_env(container, "IBG_SEEDS", seed)
    set_env(container, "MAX_ITERATIONS", max_iterations)
    set_env(container, "SLOT_ID", 1)

    run(
        [
            "kubectl",
            "--context",
            context,
            "delete",
            "job",
            JOB_NAME,
            "--namespace",
            NAMESPACE,
            "--ignore-not-found",
            "--wait=true",
        ]
    )
    run(
        ["kubectl", "--context", context, "apply", "--filename", "-"],
        input_text=json.dumps(job),
    )


def belief_text(values):
    return "[" + ", ".join(f"{value:.3f}" for value in values) + "]"


def print_replicas(title, replicas):
    print(f"\n{title}")
    print("Stage  Replica  State  Capacity  Delay  Gamma  Belief")
    for replica in replicas:
        print(
            f"{replica['stage']:>5}  {replica['replica_id']:>7}  "
            f"{replica['state']:>5}  {replica['capacity']:>8}  "
            f"{replica['delay']:>5.1f}  {replica['gamma']:>5.2f}  "
            f"{belief_text(replica['belief'])}"
        )


def placement_text(summary):
    grouped = {}
    for placement in summary["placements"]:
        grouped.setdefault(placement["stage"], []).append(placement)
    return " | ".join(
        f"S{stage}: "
        + ", ".join(
            f"f{item['flow_id']}->r{item['replica_id']}"
            for item in sorted(grouped[stage], key=lambda value: value["flow_id"])
        )
        for stage in sorted(grouped)
    )


def observation_text(summary):
    return " | ".join(
        (
            f"S{item['stage']}f{item['flow_id']}:r{item['replica_id']} "
            f"load={item['congestion']} signal={item['signal']} "
            f"lat={item['measured_latency_ms']:.1f}ms"
        )
        for item in sorted(
            summary["observations"],
            key=lambda value: (value["stage"], value["flow_id"]),
        )
    )


def render_event(event):
    event_name = event.get("event")
    if event_name == "run_started":
        config = event["configuration"]
        print(
            "\nIBG experiment started: "
            f"seed={event['seed']}, stages={config['stages']}, "
            f"replicas/stage={config['replicas_per_stage']}, "
            f"flows={config['flows']}, max iterations={event['max_iterations']}"
        )
        print_replicas("Initial replica state", event["initial_replicas"])
        return
    if event_name == "iteration_completed":
        summary = event["summary"]
        metrics = summary["metrics"]
        flow_orders = ", ".join(
            f"S{stage}={order}"
            for stage, order in sorted(summary["flow_order_by_stage"].items())
        )
        print(f"\nIteration {event['iteration']} (slot {event['slot_id']})")
        print(f"  Flow order:   {flow_orders}")
        print(f"  Placements:   {placement_text(summary)}")
        print(f"  Observations: {observation_text(summary)}")
        print(
            "  Metrics:      "
            f"utility={metrics['aggregate_utility_total']:.6f}, "
            f"SLA={metrics['sla_violations']}, "
            f"fairness={metrics['jain_fairness']:.6f}, "
            f"time={metrics['elapsed_seconds']:.3f}s, "
            f"max belief delta={event['max_belief_delta']:.3f}, "
            f"equilibrium={'yes' if metrics['equilibrium'] else 'no'}"
        )
        return
    if event_name == "run_completed":
        status = "reached" if event["reached_equilibrium"] else "not reached"
        print(
            f"\nEquilibrium {status} after {event['iterations']} iteration(s)."
        )
        print_replicas("Final replica state", event["final_replicas"])


def wait_for_controller_pod(context, timeout):
    deadline = time.monotonic() + timeout
    command = [
        "kubectl",
        "--context",
        context,
        "get",
        "pods",
        "--namespace",
        NAMESPACE,
        "--selector",
        f"job-name={JOB_NAME}",
        "--output",
        "json",
    ]
    while time.monotonic() < deadline:
        response = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        if response.returncode == 0:
            pods = json.loads(response.stdout).get("items", [])
            if pods:
                pod = pods[0]
                statuses = pod.get("status", {}).get("containerStatuses", [])
                if statuses:
                    state = statuses[0].get("state", {})
                    if "running" in state or "terminated" in state:
                        return pod["metadata"]["name"]
        time.sleep(0.5)
    raise RuntimeError("controller Pod did not start before the timeout")


def follow_logs(context, trace_path, timeout):
    pod_name = wait_for_controller_pod(context, timeout)
    logs_command = [
        "kubectl",
        "--context",
        context,
        "logs",
        f"pod/{pod_name}",
        "--container",
        "controller",
        "--namespace",
        NAMESPACE,
    ]
    pod_command = [
        "kubectl",
        "--context",
        context,
        "get",
        f"pod/{pod_name}",
        "--namespace",
        NAMESPACE,
        "--output",
        "json",
    ]
    print(f"$ {command_text(logs_command)}  # polled live", flush=True)
    deadline = time.monotonic() + timeout
    seen_lines = 0
    exit_code = None
    with trace_path.open("w", encoding="utf-8") as trace:
        while time.monotonic() < deadline:
            log_response = subprocess.run(
                logs_command,
                cwd=ROOT,
                text=True,
                capture_output=True,
            )
            if log_response.returncode == 0:
                lines = log_response.stdout.splitlines()
                for line in lines[seen_lines:]:
                    if line.startswith("IBG_EVENT="):
                        event = json.loads(line.removeprefix("IBG_EVENT="))
                        trace.write(json.dumps(event, sort_keys=True) + "\n")
                        trace.flush()
                        render_event(event)
                    elif not line.startswith("PHASE6_RESULT="):
                        print(f"[controller] {line}")
                seen_lines = len(lines)

            pod_response = subprocess.run(
                pod_command,
                cwd=ROOT,
                text=True,
                capture_output=True,
            )
            if pod_response.returncode == 0:
                pod = json.loads(pod_response.stdout)
                statuses = pod.get("status", {}).get("containerStatuses", [])
                if statuses:
                    terminated = statuses[0].get("state", {}).get("terminated")
                    if terminated is not None:
                        exit_code = terminated.get("exitCode")
                        if seen_lines == len(log_response.stdout.splitlines()):
                            break
            time.sleep(0.5)
        else:
            raise RuntimeError("controller Job did not finish before the timeout")

    if exit_code != 0:
        raise RuntimeError(f"controller container exited with status {exit_code}")
    run(
        [
            "kubectl",
            "--context",
            context,
            "wait",
            "--for=condition=complete",
            f"job/{JOB_NAME}",
            "--namespace",
            NAMESPACE,
            "--timeout=30s",
        ]
    )
    job = json.loads(
        run(
            [
                "kubectl",
                "--context",
                context,
                "get",
                "job",
                JOB_NAME,
                "--namespace",
                NAMESPACE,
                "--output",
                "json",
            ],
            capture=True,
        ).stdout
    )
    if job.get("status", {}).get("succeeded") != 1:
        raise RuntimeError("controller Job did not complete successfully")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Start the IBG kind testbed and stream an equilibrium run."
    )
    parser.add_argument("--seed", type=int, default=2050)
    parser.add_argument("--max-iterations", type=int, default=100)
    parser.add_argument("--cluster", default="ibg")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="reuse the image already loaded in kind",
    )
    parser.add_argument(
        "--trace-dir",
        type=Path,
        default=ROOT / "runs",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if args.max_iterations < 1:
        raise ValueError("--max-iterations must be at least 1")
    require_commands("docker", "kind", "kubectl")
    ensure_cluster(args.cluster)
    if not args.skip_build:
        build_and_load_image(args.cluster)
    context = f"kind-{args.cluster}"
    deploy_workloads(context, args.timeout, restart=not args.skip_build)
    start_experiment_job(context, args.seed, args.max_iterations, args.timeout)

    args.trace_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    trace_path = args.trace_dir / f"ibg-experiment-{timestamp}.jsonl"
    follow_logs(context, trace_path, args.timeout)
    print(f"\nDetailed JSONL trace: {trace_path}")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
