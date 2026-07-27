#!/usr/bin/env python3
"""Capture controlled warmed fixed-route public-forwarder diagnostics.

This helper is intentionally outside the controller experiment path.  It
executes inside the already-running flow-generator Pod, sends only an
already-selected two-hop route, and stores diagnostic evidence under ``runs/``.
It does not alter deployment resources, route selection, or any IBG metric.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import threading
import time


ROOT = Path(__file__).resolve().parents[1]
NAMESPACE = "ibg-testbed"
FLOW_GENERATOR_LABEL = "app.kubernetes.io/name=flow-generator"
DEFAULT_SOURCE_URL = (
    "http://stage-1-0.stage-1.ibg-testbed.svc.cluster.local.:8080"
)
DEFAULT_TARGET_URL = (
    "http://stage-2-0.stage-2.ibg-testbed.svc.cluster.local.:8080"
)


# This program runs within the flow-generator container.  Keeping it there
# preserves the real source-to-stage-1 ingress context while avoiding a new
# application endpoint or controller Job solely for diagnostics.
REMOTE_PROBE = r'''
import asyncio
from collections import Counter
from datetime import datetime, timezone
import json
import sys
import time

import httpx


config = json.loads(sys.argv[1])


def _request_payload(slot_id, flow_id):
    return {
        "datapath_mode": "kernel",
        "slot_id": slot_id,
        "flow_id": flow_id,
        "assigned_load": 1,
        "remaining_hops": [
            {
                "stage": 2,
                "replica_id": config["target_replica_id"],
                "url": config["target_url"],
                "assigned_load": 1,
            }
        ],
        "forwarding_path_diagnostics": True,
    }


def _require_worker_identity(link, response):
    timing = link.get("forwarding_path")
    handler = (response.get("handler_timing") or {})
    if not isinstance(timing, dict) or timing.get("schema_version") != "forwarding_path_v3":
        raise RuntimeError("fixed-route response omitted forwarding_path_v3")
    source_worker = timing.get("source_worker_process_id")
    target_worker = timing.get("target_worker_process_id")
    handler_worker = (timing.get("target_handler_timing") or {}).get(
        "worker_process_id"
    )
    if not all(isinstance(value, int) and value > 0 for value in (
        source_worker, target_worker, handler_worker
    )):
        raise RuntimeError("fixed-route response omitted worker identity")
    if target_worker != handler_worker:
        raise RuntimeError("fixed-route target worker identity is inconsistent")
    if not isinstance(handler.get("worker_process_id"), int):
        raise RuntimeError("fixed-route source handler omitted worker identity")
    if handler["worker_process_id"] != source_worker:
        raise RuntimeError("fixed-route source worker identity is inconsistent")
    runtime = timing.get("forwarder_runtime")
    target_handler = timing.get("target_handler_timing") or {}
    if (
        not isinstance(runtime, dict)
        or runtime.get("schema_version") != "forwarder_runtime_v1"
        or not isinstance(runtime.get("source_client"), dict)
        or not isinstance(runtime.get("target_handler"), dict)
        or runtime["target_handler"] != target_handler.get("forwarder_runtime")
    ):
        raise RuntimeError("fixed-route response omitted complete forwarder runtime")
    return source_worker, target_worker


async def _request_once(client, slot_id, flow_id):
    started = time.perf_counter_ns()
    response = await client.post(
        config["source_url"] + "/process-route",
        json=_request_payload(slot_id, flow_id),
    )
    elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
    response.raise_for_status()
    body = response.json()
    links = body.get("links")
    if not isinstance(links, list) or len(links) != 1:
        raise RuntimeError("fixed-route response did not contain exactly one link")
    source_worker, target_worker = _require_worker_identity(links[0], body)
    return {
        "flow_id": flow_id,
        "source_handler_worker_process_id": body["handler_timing"][
            "worker_process_id"
        ],
        "source_worker_process_id": source_worker,
        "target_worker_process_id": target_worker,
        "ingress_request_elapsed_ms": elapsed_ms,
        "link": links[0],
    }


async def _warm_source_workers():
    source_counts = Counter()
    target_counts = Counter()
    responses = []
    for attempt in range(1, config["warm_max_attempts"] + 1):
        # A fresh ingress connection gives the Uvicorn parent another chance to
        # dispatch to either public worker.  The source worker's own downstream
        # HTTPX client remains alive and is what this warm-up is intended to seed.
        limits = httpx.Limits(max_connections=1, max_keepalive_connections=0)
        async with httpx.AsyncClient(timeout=30.0, limits=limits) as client:
            item = await _request_once(
                client,
                config["slot_id_base"] + attempt,
                attempt,
            )
        source_counts[item["source_worker_process_id"]] += 1
        target_counts[item["target_worker_process_id"]] += 1
        responses.append(item)
        source_ready = (
            len(source_counts) >= config["expected_source_workers"]
            and min(source_counts.values()) >= config["warm_per_worker"]
        )
        if source_ready:
            break
    if len(source_counts) != config["expected_source_workers"]:
        raise RuntimeError(
            "warm-up did not observe the expected number of source workers: "
            f"expected {config['expected_source_workers']}, got {sorted(source_counts)}"
        )
    if min(source_counts.values()) < config["warm_per_worker"]:
        raise RuntimeError("warm-up did not seed every observed source worker")
    return {
        "attempts": len(responses),
        "source_worker_requests": dict(sorted(source_counts.items())),
        "target_worker_requests": dict(sorted(target_counts.items())),
        "responses": responses,
    }


def _distribution(values):
    values = sorted(float(value) for value in values)
    if not values:
        return {"count": 0, "mean": None, "p50": None, "p95": None, "max": None}
    return {
        "count": len(values),
        "mean": sum(values) / len(values),
        "p50": values[round((len(values) - 1) * 0.50)],
        "p95": values[round((len(values) - 1) * 0.95)],
        "max": values[-1],
    }


async def _run_wave(index, size):
    slot_id = config["slot_id_base"] + 10_000 + index
    limits = httpx.Limits(max_connections=size, max_keepalive_connections=size)
    started_unix_ns = time.time_ns()
    async with httpx.AsyncClient(timeout=30.0, limits=limits) as client:
        responses = await asyncio.gather(
            *(
                _request_once(client, slot_id, flow_id)
                for flow_id in range(1, size + 1)
            )
        )
    finished_unix_ns = time.time_ns()
    link_costs = [item["link"]["link_cost_ms"] for item in responses]
    source_workers = Counter(
        item["source_worker_process_id"] for item in responses
    )
    target_workers = Counter(
        item["target_worker_process_id"] for item in responses
    )
    reused = sum(
        item["link"]["forwarding_path"]["source_http_client_timing"][
            "connection_reused"
        ]
        for item in responses
    )
    return {
        "wave": index,
        "slot_id": slot_id,
        "concurrency": size,
        "started_unix_ns": started_unix_ns,
        "finished_unix_ns": finished_unix_ns,
        "link_cost_ms": _distribution(link_costs),
        "downstream_connection_reuse": {
            "reused": reused,
            "new": size - reused,
        },
        "source_worker_requests": dict(sorted(source_workers.items())),
        "target_worker_requests": dict(sorted(target_workers.items())),
        "responses": responses,
    }


async def main():
    warmup = await _warm_source_workers()
    # Two HTTP/1.1 workers need more than one idle downstream connection to
    # service a high-concurrency wave without connection creation.  Discard
    # this first maximum-concurrency wave so the measured waves distinguish
    # residual scheduling from this pool-capacity cold-start effect.
    discarded_concurrency_prime = await _run_wave(
        0, config["prime_concurrency"]
    )
    waves = []
    for index, size in enumerate(config["wave_sizes"], start=1):
        waves.append(await _run_wave(index, size))
    print(json.dumps({
        "schema_version": "forwarding_fixed_route_probe_v1",
        "diagnostic_kind": "warmed-fixed-route-concurrent-wave",
        "executed_from": "flow-generator-pod",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "configuration": config,
        "warmup": warmup,
        "discarded_concurrency_prime": discarded_concurrency_prime,
        "waves": waves,
    }, sort_keys=True))


asyncio.run(main())
'''


def _run(command, *, capture_output=True):
    return subprocess.run(
        command,
        check=True,
        text=True,
        capture_output=capture_output,
    )


def _kubectl(context, *args, capture_output=True):
    return _run(
        ["kubectl", "--context", context, *args],
        capture_output=capture_output,
    )


def _require_no_active_experiment(context, namespace):
    jobs = json.loads(
        _kubectl(context, "get", "jobs", "-n", namespace, "-o", "json").stdout
    )
    active = [
        item["metadata"]["name"]
        for item in jobs.get("items", [])
        if (item.get("status") or {}).get("active", 0) > 0
    ]
    if active:
        raise RuntimeError(
            "refusing to probe while experiment Job(s) are active: "
            + ", ".join(sorted(active))
        )


def _ready_flow_generator_pod(context, namespace):
    pods = json.loads(
        _kubectl(
            context,
            "get",
            "pods",
            "-n",
            namespace,
            "-l",
            FLOW_GENERATOR_LABEL,
            "-o",
            "json",
        ).stdout
    )
    ready = []
    for item in pods.get("items", []):
        conditions = {
            condition.get("type"): condition.get("status")
            for condition in (item.get("status") or {}).get("conditions", [])
        }
        if (
            (item.get("status") or {}).get("phase") == "Running"
            and conditions.get("Ready") == "True"
        ):
            ready.append(item["metadata"]["name"])
    if len(ready) != 1:
        raise RuntimeError(
            "expected exactly one Ready flow-generator Pod, found "
            + repr(sorted(ready))
        )
    return ready[0]


def _parse_wave_sizes(value):
    try:
        sizes = [int(part.strip()) for part in value.split(",")]
    except ValueError as error:
        raise argparse.ArgumentTypeError("wave sizes must be comma-separated integers") from error
    if not sizes or any(size < 1 for size in sizes):
        raise argparse.ArgumentTypeError("wave sizes must be positive")
    return sizes


def _read_optional_text(path):
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError as error:
        return {"unavailable": f"{type(error).__name__}: {error!r}"}


def _read_optional_integer(path):
    value = _read_optional_text(path)
    if isinstance(value, dict):
        return value
    try:
        return int(value)
    except ValueError:
        return {"unavailable": f"invalid integer: {value!r}"}


def _host_light_snapshot():
    """Read only host-wide scheduler/load and conntrack state."""
    return {
        "captured_unix_ns": time.time_ns(),
        "loadavg": _read_optional_text("/proc/loadavg"),
        "cpu_pressure": _read_optional_text("/proc/pressure/cpu"),
        "io_pressure": _read_optional_text("/proc/pressure/io"),
        "conntrack_count": _read_optional_integer(
            "/proc/sys/net/netfilter/nf_conntrack_count"
        ),
        "conntrack_max": _read_optional_integer(
            "/proc/sys/net/netfilter/nf_conntrack_max"
        ),
    }


class _HostRuntimeObserver:
    def __init__(self, interval_seconds):
        self.interval_seconds = interval_seconds
        self.samples = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _capture(self):
        self.samples.append(_host_light_snapshot())

    def _run(self):
        while not self._stop.wait(self.interval_seconds):
            self._capture()

    def start(self):
        self._capture()
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join()
        self._capture()


def _docker_kind_stats(cluster):
    """Read Docker's point-in-time kind-node accounting without retuning it."""
    identifiers = subprocess.run(
        [
            "docker",
            "ps",
            "--filter",
            f"label=io.x-k8s.kind.cluster={cluster}",
            "--quiet",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if identifiers.returncode != 0:
        return {"unavailable": identifiers.stderr.strip()}
    container_ids = identifiers.stdout.split()
    if not container_ids:
        return {"containers": []}
    stats = subprocess.run(
        [
            "docker",
            "stats",
            "--no-stream",
            "--format",
            "{{json .}}",
            *container_ids,
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if stats.returncode != 0:
        return {"unavailable": stats.stderr.strip()}
    try:
        return {
            "captured_unix_ns": time.time_ns(),
            "containers": [
                json.loads(line) for line in stats.stdout.splitlines() if line
            ],
        }
    except json.JSONDecodeError as error:
        return {"unavailable": f"invalid docker stats JSON: {error!r}"}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Capture diagnostic-only warmed fixed-route public-forwarder waves "
            "from the live flow-generator Pod."
        )
    )
    parser.add_argument("--cluster", default="ibg")
    parser.add_argument("--namespace", default=NAMESPACE)
    parser.add_argument("--source-url", default=DEFAULT_SOURCE_URL)
    parser.add_argument("--target-url", default=DEFAULT_TARGET_URL)
    parser.add_argument("--target-replica-id", type=int, default=1)
    parser.add_argument("--expected-source-workers", type=int, default=2)
    parser.add_argument("--warm-per-worker", type=int, default=3)
    parser.add_argument("--warm-max-attempts", type=int, default=60)
    parser.add_argument("--wave-sizes", type=_parse_wave_sizes, default=[6, 15, 15])
    parser.add_argument(
        "--prime-concurrency",
        type=int,
        help=(
            "discarded post-warm-up HTTP/1.1 pool-prime wave; defaults to "
            "the largest measured wave"
        ),
    )
    parser.add_argument("--slot-id-base", type=int, default=900_000)
    parser.add_argument(
        "--host-runtime-observations",
        action="store_true",
        help=(
            "record read-only host pressure/load/conntrack samples plus kind "
            "Docker stats during this diagnostic probe"
        ),
    )
    parser.add_argument(
        "--host-sample-interval-ms",
        type=int,
        default=100,
        help="read-only host observation interval while the probe runs",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if min(
        args.expected_source_workers,
        args.warm_per_worker,
        args.warm_max_attempts,
        args.slot_id_base,
        args.host_sample_interval_ms,
        args.target_replica_id,
    ) < 1:
        parser.error("worker, warm-up, and slot values must be positive")
    if args.prime_concurrency is not None and args.prime_concurrency < 1:
        parser.error("--prime-concurrency must be positive")
    return args


def main(argv=None):
    args = parse_args(argv)
    context = f"kind-{args.cluster}"
    _require_no_active_experiment(context, args.namespace)
    pod_name = _ready_flow_generator_pod(context, args.namespace)
    configuration = {
        "context": context,
        "namespace": args.namespace,
        "source_url": args.source_url.rstrip("/"),
        "target_url": args.target_url.rstrip("/"),
        "target_replica_id": args.target_replica_id,
        "expected_source_workers": args.expected_source_workers,
        "warm_per_worker": args.warm_per_worker,
        "warm_max_attempts": args.warm_max_attempts,
        "wave_sizes": args.wave_sizes,
        "prime_concurrency": args.prime_concurrency or max(args.wave_sizes),
        "slot_id_base": args.slot_id_base,
    }
    observer = None
    docker_before = None
    if args.host_runtime_observations:
        docker_before = _docker_kind_stats(args.cluster)
        observer = _HostRuntimeObserver(args.host_sample_interval_ms / 1000)
        observer.start()
    try:
        result = _kubectl(
            context,
            "exec",
            "-n",
            args.namespace,
            pod_name,
            "-c",
            "flow-generator",
            "--",
            "python3",
            "-c",
            REMOTE_PROBE,
            json.dumps(configuration, sort_keys=True),
        )
    finally:
        if observer is not None:
            observer.stop()
    try:
        probe = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            "flow-generator probe did not emit one JSON result: "
            f"stdout={result.stdout!r}; stderr={result.stderr!r}"
        ) from error
    probe["flow_generator_pod"] = pod_name
    if observer is not None:
        probe["host_runtime_observations"] = {
            "schema_version": "forwarding_host_runtime_v1",
            "scope": (
                "read-only host pressure/load/conntrack samples and kind-node "
                "Docker accounting; not host preflight or a runtime change"
            ),
            "sample_interval_ms": args.host_sample_interval_ms,
            "light_samples": observer.samples,
            "kind_docker_stats_before": docker_before,
            "kind_docker_stats_after": _docker_kind_stats(args.cluster),
        }
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output or (
        ROOT / "runs" / f"forwarding-fixed-route-probe-{timestamp}.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(probe, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    compact = {
        "trace": str(output),
        "warm_source_workers": probe["warmup"]["source_worker_requests"],
        "discarded_pool_prime": {
            "concurrency": probe["discarded_concurrency_prime"]["concurrency"],
            "downstream_connection_reuse": probe["discarded_concurrency_prime"][
                "downstream_connection_reuse"
            ],
        },
        "waves": [
            {
                "concurrency": wave["concurrency"],
                "pair_mean_ms": wave["link_cost_ms"]["mean"],
                "pair_max_ms": wave["link_cost_ms"]["max"],
                "downstream_connection_reuse": wave[
                    "downstream_connection_reuse"
                ],
                "source_workers": wave["source_worker_requests"],
                "target_workers": wave["target_worker_requests"],
            }
            for wave in probe["waves"]
        ],
    }
    print(f"FORWARDING_FIXED_ROUTE_PROBE={json.dumps(compact, sort_keys=True)}")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
