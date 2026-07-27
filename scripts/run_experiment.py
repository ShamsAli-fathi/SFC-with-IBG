#!/usr/bin/env python3
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from testbed.kubernetes_resources import build_runtime_resources
from testbed.dpdk_vpp_preflight import (
    collect_dpdk_vpp_preflight,
    format_dpdk_vpp_preflight,
    require_dpdk_vpp_preflight,
)
from testbed.network_impairment import NetworkImpairment
from testbed.profiles import expand_profiles, load_profiles
from IBG.datapath import (
    DPDK_VPP_DATAPATH_MODE,
    KERNEL_DATAPATH_MODE,
    require_datapath_mode,
)
from IBG.learning_mode import (
    LEARNING_SIGNAL_MODES,
    SEPARATED_LEARNING_SIGNAL_MODE,
)
from IBG.outcome_latency import (
    DEFAULT_OUTCOME_LATENCY_MODE,
    OUTCOME_LATENCY_MODES,
)


IMAGE = "ibg-testbed:kernel-phase3"
NAMESPACE = "ibg-testbed"
JOB_NAME = "ibg-experiment"
CSV_OUTPUT_DIR = ROOT / "figures"
CSV_METRICS = {
    "time.csv": "elapsed_seconds",
    "sla_violations.csv": "sla_violations",
    "aggregate_utility.csv": "aggregate_utility_total",
    "realized_end_to_end_utility.csv": "realized_utility_total",
    "jain_index.csv": "jain_fairness",
}
OUTCOME_CSV_METRICS = {
    "realized_utility.csv": "realized_utility_total",
    "physical_processing_utility.csv": "physical_utility_total",
    "realized_end_to_end_utility.csv": "end_to_end_utility_total",
}
LEARNING_SIGNAL_CSV = "logical_learning_footprint.csv"


def csv_run_hash(timestamp, seed, num_of_flows, num_of_stages, num_of_replicas):
    provenance = (
        f"{timestamp}-seed{seed}-f{num_of_flows}"
        f"-s{num_of_stages}-r{num_of_replicas}"
    )
    return hashlib.sha256(provenance.encode("utf-8")).hexdigest()[:6]


def run_identifier(timestamp, run_number, num_of_runs):
    if num_of_runs == 1:
        return timestamp
    return f"{timestamp}-run{run_number:03d}"


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


def remove_stale_stage_resources(context, num_of_stages):
    response = run(
        [
            "kubectl",
            "--context",
            context,
            "get",
            "statefulsets,services",
            "--namespace",
            NAMESPACE,
            "--output",
            "json",
        ],
        capture=True,
    )
    stale = []
    for item in json.loads(response.stdout).get("items", []):
        name = item.get("metadata", {}).get("name", "")
        if not name.startswith("stage-"):
            continue
        try:
            stage = int(name.removeprefix("stage-"))
        except ValueError:
            continue
        if stage <= num_of_stages:
            continue
        resource = {
            "Service": "service",
            "StatefulSet": "statefulset",
        }.get(item.get("kind"))
        if resource is not None:
            stale.append(f"{resource}/{name}")
    if stale:
        run(
            [
                "kubectl",
                "--context",
                context,
                "delete",
                *sorted(stale),
                "--namespace",
                NAMESPACE,
                "--wait=true",
            ]
        )


def deploy_workloads(
    context,
    timeout,
    restart,
    *,
    num_of_stages,
    num_of_replicas,
    profiles,
    network_impairment=None,
):
    for manifest in ("namespace.yaml", "rbac.yaml", "flow-generator.yaml"):
        run(
            [
                "kubectl",
                "--context",
                context,
                "apply",
                "--filename",
                str(ROOT / "deploy/kubernetes" / manifest),
            ]
        )
    resources = build_runtime_resources(
        profiles,
        num_of_stages=num_of_stages,
        num_of_replicas=num_of_replicas,
        namespace=NAMESPACE,
        image=IMAGE,
        network_impairment=network_impairment,
    )
    run(
        ["kubectl", "--context", context, "apply", "--filename", "-"],
        input_text=json.dumps(resources),
    )
    remove_stale_stage_resources(context, num_of_stages)
    stage_resources = [
        f"statefulset/stage-{stage}"
        for stage in range(1, num_of_stages + 1)
    ]
    if restart:
        run(
            [
                "kubectl",
                "--context",
                context,
                "rollout",
                "restart",
                *stage_resources,
                "deployment/flow-generator",
                "--namespace",
                NAMESPACE,
            ]
        )
    for stage in range(1, num_of_stages + 1):
        run(
            [
                "kubectl",
                "--context",
                context,
                "rollout",
                "status",
                f"statefulset/stage-{stage}",
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


def start_experiment_job(
    context,
    seed,
    max_iterations,
    timeout,
    *,
    num_of_stages,
    num_of_replicas,
    num_of_flows,
    datapath_mode=KERNEL_DATAPATH_MODE,
    environment_metadata=None,
    learning_signal_mode=SEPARATED_LEARNING_SIGNAL_MODE,
    outcome_latency_mode=DEFAULT_OUTCOME_LATENCY_MODE,
    forwarder_cgroup_diagnostics=False,
    forwarding_path_diagnostics=False,
    memory_diagnostics=False,
    network_impairment=None,
):
    datapath_mode = require_datapath_mode(datapath_mode, runtime=True)
    if network_impairment is None:
        network_impairment = NetworkImpairment.disabled()
    if not isinstance(network_impairment, NetworkImpairment):
        raise ValueError(
            "network_impairment must be a NetworkImpairment instance"
        )
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
    set_env(container, "NUM_STAGES", num_of_stages)
    set_env(container, "EXPECTED_REPLICAS", num_of_replicas)
    set_env(container, "NUM_FLOWS", num_of_flows)
    set_env(container, "DATAPATH_MODE", datapath_mode)
    set_env(container, "LEARNING_SIGNAL_MODE", learning_signal_mode)
    set_env(container, "OUTCOME_LATENCY_MODE", outcome_latency_mode)
    set_env(
        container,
        "FORWARDER_CGROUP_DIAGNOSTICS",
        str(bool(forwarder_cgroup_diagnostics)).lower(),
    )
    set_env(
        container,
        "FORWARDING_PATH_DIAGNOSTICS",
        str(bool(forwarding_path_diagnostics)).lower(),
    )
    set_env(
        container,
        "SOLVER_RESOURCE_DIAGNOSTICS",
        str(bool(memory_diagnostics)).lower(),
    )
    set_env(container, "NETWORK_IMPAIRMENT", network_impairment.to_json())
    set_env(container, "RUNTIME_IMAGE", IMAGE)
    set_env(
        container,
        "EXPERIMENT_ENVIRONMENT",
        json.dumps(environment_metadata or {}, sort_keys=True),
    )

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


def collect_environment_metadata(context):
    kubernetes = json.loads(
        run(
            ["kubectl", "--context", context, "version", "--output", "json"],
            capture=True,
        ).stdout
    )
    return {
        "host_platform": platform.platform(),
        "docker_server": run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            capture=True,
        ).stdout.strip(),
        "kind": run(["kind", "version"], capture=True).stdout.strip(),
        "kubernetes_server": kubernetes["serverVersion"]["gitVersion"],
        "cluster_context": context,
    }


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
            f"mode={event['datapath_mode']}, seed={event['seed']}, "
            f"stages={config['stages']}, "
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


def _read_csv_rows(path):
    if not path.exists():
        return [], []
    with path.open(newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        return list(reader.fieldnames or []), list(reader)


def _write_csv_rows(path, fieldnames, rows):
    with path.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _append_metric_column(path, run_id, values):
    fieldnames, rows = _read_csv_rows(path)
    if run_id in fieldnames:
        raise ValueError(f"CSV run identifier already exists in {path}: {run_id}")
    fieldnames.append(run_id)
    while len(rows) < len(values):
        rows.append({name: "" for name in fieldnames})
    for row in rows:
        row.setdefault(run_id, "")
    for index, value in enumerate(values):
        rows[index][run_id] = value
    _write_csv_rows(path, fieldnames, rows)


def _snapshot_beliefs(event):
    return {
        str((replica["stage"], replica["replica_id"])): replica["belief"]
        for replica in event["initial_replicas"]
    }


def _summary_beliefs(event):
    beliefs = {}
    for identity, values in event["summary"]["beliefs"].items():
        stage, replica_id = (int(value) for value in identity.split(":", 1))
        beliefs[str((stage, replica_id))] = values
    return beliefs


def _append_belief_rows(path, snapshots):
    fieldnames, rows = _read_csv_rows(path)
    for snapshot in snapshots:
        for name in snapshot:
            if name not in fieldnames:
                fieldnames.append(name)
    for snapshot in snapshots:
        rows.append(
            {
                name: json.dumps(snapshot[name]) if name in snapshot else ""
                for name in fieldnames
            }
        )
    for row in rows:
        for name in fieldnames:
            row.setdefault(name, "")
    _write_csv_rows(path, fieldnames, rows)


def _learning_signal_values(iterations):
    snapshots = [event["summary"].get("learning_signal") for event in iterations]
    if not any(snapshot is not None for snapshot in snapshots):
        return None
    if any(snapshot is None for snapshot in snapshots):
        raise ValueError("trace mixes learning-signal schemas across iterations")
    try:
        return [snapshot["logical_payload_bytes"] for snapshot in snapshots]
    except KeyError as error:
        raise ValueError("learning-signal record lacks logical payload bytes") from error


def export_legacy_csv(trace_path, output_dir, run_id):
    with trace_path.open(encoding="utf-8") as trace:
        events = [json.loads(line) for line in trace if line.strip()]
    run_started = next(
        (event for event in events if event.get("event") == "run_started"),
        None,
    )
    iterations = [
        event for event in events if event.get("event") == "iteration_completed"
    ]
    run_completed = next(
        (event for event in events if event.get("event") == "run_completed"),
        None,
    )
    if run_started is None or not iterations or run_completed is None:
        raise ValueError("trace does not contain a complete experiment run")

    metrics = dict(CSV_METRICS)
    if all(
        all(metric_name in event["summary"]["metrics"] for event in iterations)
        for metric_name in OUTCOME_CSV_METRICS.values()
    ):
        metrics.update(OUTCOME_CSV_METRICS)

    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, metric_name in metrics.items():
        _append_metric_column(
            output_dir / filename,
            run_id,
            [event["summary"]["metrics"][metric_name] for event in iterations],
        )
    learning_signal_values = _learning_signal_values(iterations)
    if learning_signal_values is not None:
        _append_metric_column(
            output_dir / LEARNING_SIGNAL_CSV,
            run_id,
            learning_signal_values,
        )
    _append_belief_rows(
        output_dir / "replica_results.csv",
        [_snapshot_beliefs(run_started)]
        + [_summary_beliefs(event) for event in iterations],
    )
    filenames = [
        output_dir / filename
        for filename in (*metrics, "replica_results.csv")
    ]
    if learning_signal_values is not None:
        filenames.append(output_dir / LEARNING_SIGNAL_CSV)
    return filenames


def run_experiment_series(args, context, environment_metadata):
    args.trace_dir.mkdir(parents=True, exist_ok=True)
    trace_paths = []
    network_impairment = network_impairment_from_args(args)
    for run_number in range(1, args.num_of_runs + 1):
        if args.num_of_runs > 1:
            print(f"\nExperiment run {run_number}/{args.num_of_runs}")
        start_experiment_job(
            context,
            args.seed,
            args.max_iterations,
            args.timeout,
            num_of_stages=args.num_of_stages,
            num_of_replicas=args.num_of_replicas,
            num_of_flows=args.num_of_flows,
            datapath_mode=args.datapath_mode,
            environment_metadata=environment_metadata,
            learning_signal_mode=args.learning_signal_mode,
            outcome_latency_mode=args.outcome_latency_mode,
            forwarder_cgroup_diagnostics=args.forwarder_cgroup_diagnostics,
            forwarding_path_diagnostics=args.forwarding_path_diagnostics,
            memory_diagnostics=bool(args.memory),
            network_impairment=network_impairment,
        )
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        identifier = run_identifier(timestamp, run_number, args.num_of_runs)
        trace_path = args.trace_dir / f"ibg-experiment-{identifier}.jsonl"
        follow_logs(context, trace_path, args.timeout)
        trace_paths.append(trace_path)
        print(f"\nDetailed JSONL trace: {trace_path}")
        if args.csv == 1:
            csv_paths = export_legacy_csv(
                trace_path,
                CSV_OUTPUT_DIR,
                csv_run_hash(
                    identifier,
                    args.seed,
                    args.num_of_flows,
                    args.num_of_stages,
                    args.num_of_replicas,
                ),
            )
            print(f"CSV reports: {CSV_OUTPUT_DIR}")
            for csv_path in csv_paths:
                print(f"  {csv_path.name}")
    return trace_paths


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Start the IBG kind testbed and stream an equilibrium run."
    )
    parser.add_argument("--seed", type=int, default=2050)
    parser.add_argument(
        "--datapath",
        dest="datapath_mode",
        choices=(KERNEL_DATAPATH_MODE, DPDK_VPP_DATAPATH_MODE),
        default=KERNEL_DATAPATH_MODE,
        help=(
            "selected datapath; dpdk-vpp currently performs the Phase 5 host "
            "gate and cannot deploy until its Phase 6 runtime exists"
        ),
    )
    parser.add_argument(
        "--dpdk-preflight-only",
        action="store_true",
        help=(
            "run the read-only DPDK/VPP host preflight and exit before any "
            "Docker, kind, or Kubernetes action"
        ),
    )
    parser.add_argument(
        "--flow",
        "--flows",
        dest="num_of_flows",
        type=int,
        default=3,
        help="number of logical flows",
    )
    parser.add_argument(
        "--stage",
        "--stages",
        dest="num_of_stages",
        type=int,
        default=3,
        help="number of ordered SFC stages",
    )
    parser.add_argument(
        "--replica",
        "--replicas",
        dest="num_of_replicas",
        type=int,
        default=5,
        help="number of replicas in every stage",
    )
    parser.add_argument("--max-iterations", type=int, default=100)
    parser.add_argument(
        "--learning-signal-mode",
        choices=sorted(LEARNING_SIGNAL_MODES),
        default=SEPARATED_LEARNING_SIGNAL_MODE,
        help=(
            "controller learning-observation mode; the physical-only mode is "
            "an explicit same-deployment diagnostic"
        ),
    )
    parser.add_argument(
        "--forwarder-cgroup-diagnostics",
        action="store_true",
        help=(
            "record selected-forwarder cgroup-v2 CPU deltas before/after each "
            "route slot"
        ),
    )
    parser.add_argument(
        "--outcome-latency-mode",
        choices=sorted(OUTCOME_LATENCY_MODES),
        default=DEFAULT_OUTCOME_LATENCY_MODE,
        help=(
            "latency basis for reported realized utility and SLA; raw physical "
            "and end-to-end values remain in the trace"
        ),
    )
    parser.add_argument(
        "--forwarding-path-diagnostics",
        action="store_true",
        help=(
            "record shared-clock timings around each selected "
            "forwarder-to-forwarder RPC"
        ),
    )
    parser.add_argument(
        "--runs",
        dest="num_of_runs",
        type=int,
        default=1,
        help="number of independent experiment runs to execute",
    )
    parser.add_argument(
        "--memory",
        type=int,
        choices=(0, 1),
        default=0,
        help=(
            "record solver_resource_v1 controller RSS and exact memo-cache "
            "measurements (1=enabled, 0=disabled)"
        ),
    )
    parser.add_argument(
        "--netem",
        type=int,
        choices=(0, 1),
        default=0,
        help=(
            "apply opt-in tc/netem delay and jitter to replica-Pod egress "
            "(1=enabled, 0=disabled)"
        ),
    )
    parser.add_argument(
        "--netem-delay-ms",
        type=float,
        default=10.0,
        help="base replica-Pod egress delay in milliseconds when --netem 1",
    )
    parser.add_argument(
        "--netem-jitter-ms",
        type=float,
        default=3.0,
        help=(
            "normally distributed replica-Pod egress jitter in milliseconds "
            "when --netem 1"
        ),
    )
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
    parser.add_argument(
        "--csv",
        type=int,
        choices=(0, 1),
        default=0,
        help=(
            "write the five legacy CSV reports, active realized utility, "
            "physical and raw end-to-end utility references, and (when "
            "recorded) logical learning footprint report to "
            f"{CSV_OUTPUT_DIR} (1=enabled, 0=disabled)"
        ),
    )
    return parser.parse_args(argv)


def network_impairment_from_args(args):
    if args.netem == 0:
        return NetworkImpairment.disabled()
    return NetworkImpairment.enabled_with(
        delay_ms=args.netem_delay_ms,
        jitter_ms=args.netem_jitter_ms,
    )


def main():
    args = parse_args()
    if min(
        args.max_iterations,
        args.num_of_runs,
        args.num_of_flows,
        args.num_of_stages,
        args.num_of_replicas,
    ) < 1:
        raise ValueError(
            "--flow, --stage, --replica, --max-iterations, and --runs must be positive"
        )
    args.datapath_mode = require_datapath_mode(args.datapath_mode)
    network_impairment = network_impairment_from_args(args)
    if args.dpdk_preflight_only and args.datapath_mode != DPDK_VPP_DATAPATH_MODE:
        raise ValueError("--dpdk-preflight-only requires --datapath dpdk-vpp")
    if args.datapath_mode == DPDK_VPP_DATAPATH_MODE:
        preflight = collect_dpdk_vpp_preflight()
        print(format_dpdk_vpp_preflight(preflight))
        require_dpdk_vpp_preflight(preflight)
        if args.dpdk_preflight_only:
            return
        raise RuntimeError(
            "DPDK/VPP Phase 6 runtime is not implemented; Kernel remains the "
            "only deployable datapath"
        )
    require_commands("docker", "kind", "kubectl")
    print(
        "Requested configuration: "
        f"datapath={args.datapath_mode}, flows={args.num_of_flows}, "
        f"stages={args.num_of_stages}, "
        f"replicas/stage={args.num_of_replicas}, runs={args.num_of_runs}, "
        f"learning-signal={args.learning_signal_mode}, "
        f"outcome-latency={args.outcome_latency_mode}, "
        f"forwarder-cgroup-diagnostics={args.forwarder_cgroup_diagnostics}, "
        f"forwarding-path-diagnostics={args.forwarding_path_diagnostics}"
        f", memory={args.memory}, "
        f"netem={network_impairment.enabled}, "
        f"netem-delay-ms={network_impairment.delay_ms:g}, "
        f"netem-jitter-ms={network_impairment.jitter_ms:g}"
    )
    base_profiles = load_profiles(ROOT / "deploy/kubernetes/profiles.json")
    profiles = expand_profiles(
        base_profiles,
        args.num_of_stages,
        args.num_of_replicas,
    )
    ensure_cluster(args.cluster)
    if not args.skip_build:
        build_and_load_image(args.cluster)
    context = f"kind-{args.cluster}"
    deploy_workloads(
        context,
        args.timeout,
        restart=not args.skip_build,
        num_of_stages=args.num_of_stages,
        num_of_replicas=args.num_of_replicas,
        profiles=profiles,
        network_impairment=network_impairment,
    )
    run_experiment_series(
        args,
        context,
        collect_environment_metadata(context),
    )


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
