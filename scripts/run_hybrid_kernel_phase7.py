#!/usr/bin/env python3
"""Collect bounded live resource evidence for Hybrid Kernel Phase 7."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import Mapping, Sequence

from IBG_Hybrid.kernel_resource_evidence import (
    HYBRID_KERNEL_RESOURCE_EVIDENCE_VERSION,
    PROCESSOR_MEMORY_PROFILES,
    CgroupSnapshot,
    HybridKernelResourceEvidenceError,
    cgroup_delta,
    evaluate_processor_candidate,
    parse_cgroup_snapshot,
    parse_crictl_stats,
)
from scripts import run_hybrid_kernel_phase4 as runner


ROOT = Path(__file__).resolve().parents[1]
CGROUP_SCRIPT = (
    "printf '__CPU__\\n'; cat /sys/fs/cgroup/cpu.stat; "
    "printf '__MEMORY_CURRENT__\\n'; cat /sys/fs/cgroup/memory.current; "
    "printf '__MEMORY_PEAK__\\n'; cat /sys/fs/cgroup/memory.peak; "
    "printf '__MEMORY_EVENTS__\\n'; cat /sys/fs/cgroup/memory.events"
)
CONTROLLER_CGROUP_SCRIPT = CGROUP_SCRIPT + (
    "; printf '__PROCESS_STATUS__\\n'; cat /proc/1/status"
)
FATAL_EVENT_REASONS = frozenset(
    {
        "BackOff",
        "Evicted",
        "Failed",
        "FailedScheduling",
        "Killing",
        "OOMKilling",
    }
)


def _run(
    command: Sequence[str], *, timeout: float = 30.0
) -> str:
    completed = subprocess.run(
        tuple(command),
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    return completed.stdout


def _json(command: Sequence[str], *, timeout: float = 30.0) -> Mapping[str, object]:
    value = json.loads(_run(command, timeout=timeout))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object from {' '.join(command)}")
    return value


def _kubectl(*arguments: str) -> tuple[str, ...]:
    return (
        "kubectl",
        "--context",
        runner.KUBECTL_CONTEXT,
        *arguments,
    )


def _pods() -> Mapping[str, object]:
    return _json(
        _kubectl(
            "get",
            "pods",
            "-n",
            runner.HYBRID_NAMESPACE,
            "-o",
            "json",
        )
    )


def _events() -> Mapping[str, object]:
    return _json(
        _kubectl(
            "get",
            "events",
            "-n",
            runner.HYBRID_NAMESPACE,
            "-o",
            "json",
        )
    )


def _nodes() -> Mapping[str, object]:
    return _json(_kubectl("get", "nodes", "-o", "json"))


def _shared_node_states() -> Mapping[str, str]:
    output = _run(
        (
            "docker",
            "ps",
            "-a",
            "--filter",
            "name=^/ibg",
            "--format",
            "{{.Names}}\\t{{.Status}}",
        )
    )
    states = {}
    for line in output.splitlines():
        if not line.strip():
            continue
        name, status = line.split("\t", 1)
        states[name] = status
    return states


def _runtime_stats(replica_count: int = 2) -> tuple:
    document = _json(
        (
            "docker",
            "exec",
            runner.WORKER_NODE_NAME,
            "crictl",
            "stats",
            "--label",
            f"io.kubernetes.pod.namespace={runner.HYBRID_NAMESPACE}",
            "--seconds",
            "0",
            "-o",
            "json",
        ),
        timeout=30.0,
    )
    samples = parse_crictl_stats(document)
    counts = {
        name: sum(sample.container_name == name for sample in samples)
        for name in ("private-processor", "public-forwarder", "flow-generator")
    }
    expected = {
        "private-processor": 3 * replica_count,
        "public-forwarder": 3 * replica_count,
        "flow-generator": 1,
    }
    if counts != expected:
        raise RuntimeError(
            f"runtime stats lack exact live serving coverage: {counts}"
        )
    return samples


def _serving_identities(
    document: Mapping[str, object],
    replica_count: int = 2,
) -> tuple[tuple[str, str, str], ...]:
    items = document.get("items")
    if not isinstance(items, list):
        raise RuntimeError("Pod inventory has no items")
    identities = []
    for item in items:
        if not isinstance(item, dict):
            continue
        metadata = item.get("metadata")
        spec = item.get("spec")
        if not isinstance(metadata, dict) or not isinstance(spec, dict):
            continue
        pod_name = metadata.get("name")
        pod_uid = metadata.get("uid")
        if not isinstance(pod_name, str) or not isinstance(pod_uid, str):
            continue
        if not (
            pod_name.startswith("hybrid-stage-")
            or pod_name.startswith("ibg-hybrid-flow-generator-")
        ):
            continue
        containers = spec.get("containers")
        if not isinstance(containers, list):
            raise RuntimeError(f"Pod {pod_name} has no containers")
        for container in containers:
            if not isinstance(container, dict) or not isinstance(
                container.get("name"), str
            ):
                raise RuntimeError(f"Pod {pod_name} has invalid containers")
            identities.append((pod_name, pod_uid, container["name"]))
    expected = 6 * replica_count + 1
    if len(identities) != expected:
        raise RuntimeError(
            "resource gate requires exact serving-container coverage: "
            f"expected {expected}, got {len(identities)}"
        )
    return tuple(sorted(identities))


def _one_cgroup(identity: tuple[str, str, str]) -> tuple[tuple[str, str], CgroupSnapshot]:
    pod_name, pod_uid, container_name = identity
    output = _run(
        _kubectl(
            "exec",
            "-n",
            runner.HYBRID_NAMESPACE,
            pod_name,
            "-c",
            container_name,
            "--",
            "/bin/sh",
            "-c",
            CGROUP_SCRIPT,
        ),
        timeout=15.0,
    )
    return (pod_uid, container_name), parse_cgroup_snapshot(output)


def _serving_cgroups(
    document: Mapping[str, object],
    replica_count: int = 2,
) -> Mapping[tuple[str, str], CgroupSnapshot]:
    identities = _serving_identities(document, replica_count)
    with ThreadPoolExecutor(max_workers=4) as pool:
        values = tuple(pool.map(_one_cgroup, identities))
    result = dict(values)
    if len(result) != len(values):
        raise RuntimeError("serving cgroup evidence contains duplicate identities")
    return result


def _event_counts(document: Mapping[str, object]) -> Mapping[str, int]:
    items = document.get("items")
    if not isinstance(items, list):
        raise RuntimeError("event inventory has no items")
    result = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        metadata = item.get("metadata")
        if not isinstance(metadata, dict) or not isinstance(metadata.get("uid"), str):
            continue
        count = item.get("count", 1)
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise RuntimeError("event inventory has an invalid count")
        result[metadata["uid"]] = count
    return result


def _new_event_summary(
    before: Mapping[str, object], after: Mapping[str, object]
) -> tuple[int, int, tuple[Mapping[str, object], ...]]:
    old_counts = _event_counts(before)
    items = after.get("items")
    if not isinstance(items, list):
        raise RuntimeError("event inventory has no items")
    fatal = 0
    probes = 0
    records = []
    for item in items:
        if not isinstance(item, dict):
            continue
        metadata = item.get("metadata")
        if not isinstance(metadata, dict) or not isinstance(metadata.get("uid"), str):
            continue
        count = item.get("count", 1)
        delta = count - old_counts.get(metadata["uid"], 0)
        if delta <= 0:
            continue
        reason = item.get("reason")
        event_type = item.get("type")
        if event_type == "Warning" and reason in FATAL_EVENT_REASONS:
            fatal += delta
        if event_type == "Warning" and reason == "Unhealthy":
            probes += delta
        involved = item.get("involvedObject")
        records.append(
            {
                "type": event_type,
                "reason": reason,
                "count_delta": delta,
                "object": involved.get("name") if isinstance(involved, dict) else None,
                "message": item.get("message"),
            }
        )
    return fatal, probes, tuple(records)


def _iso_seconds(start: object, end: object) -> float:
    if not isinstance(start, str) or not isinstance(end, str):
        raise RuntimeError("controller Job lacks start/completion timestamps")
    return (
        datetime.fromisoformat(end.replace("Z", "+00:00"))
        - datetime.fromisoformat(start.replace("Z", "+00:00"))
    ).total_seconds()


class ControllerSampler:
    def __init__(self, job_name: str = "ibg-hybrid-controller-phase7") -> None:
        self.job_name = job_name
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.samples: list[CgroupSnapshot] = []
        self.errors: list[str] = []

    def start(self) -> None:
        self._thread = threading.Thread(target=self._sample, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=10.0)
            if self._thread.is_alive():
                raise RuntimeError("controller resource sampler did not stop")
        if not self.samples:
            detail = f": {self.errors[-1]}" if self.errors else ""
            raise RuntimeError("controller resource sampler captured no sample" + detail)

    def _sample(self) -> None:
        while not self._stop.is_set():
            try:
                pods = _json(
                    _kubectl(
                        "get",
                        "pods",
                        "-n",
                        runner.HYBRID_NAMESPACE,
                        "-l",
                        f"job-name={self.job_name}",
                        "-o",
                        "json",
                    ),
                    timeout=5.0,
                )
                items = pods.get("items")
                running = [] if not isinstance(items, list) else [
                    item
                    for item in items
                    if isinstance(item, dict)
                    and isinstance(item.get("status"), dict)
                    and item["status"].get("phase") == "Running"
                ]
                if len(running) == 1:
                    metadata = running[0].get("metadata")
                    if isinstance(metadata, dict) and isinstance(
                        metadata.get("name"), str
                    ):
                        output = _run(
                            _kubectl(
                                "exec",
                                "-n",
                                runner.HYBRID_NAMESPACE,
                                metadata["name"],
                                "-c",
                                "controller",
                                "--",
                                "/bin/sh",
                                "-c",
                                CONTROLLER_CGROUP_SCRIPT,
                            ),
                            timeout=5.0,
                        )
                        self.samples.append(parse_cgroup_snapshot(output))
            except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
                self.errors.append(str(error))
            self._stop.wait(0.1)


class Phase7Collector:
    def __init__(self) -> None:
        self.started = time.monotonic()
        self.initial_nodes = _nodes()
        self.initial_pods = _pods()
        self.initial_events = _events()
        self.initial_shared = _shared_node_states()
        self.ready_elapsed_seconds: float | None = None
        self.before_traffic_pods: Mapping[str, object] | None = None
        self.before_traffic_events: Mapping[str, object] | None = None
        self.before_cgroups: Mapping[tuple[str, str], CgroupSnapshot] | None = None
        self.before_stats = ()
        self.after_pods: Mapping[str, object] | None = None
        self.after_cgroups: Mapping[tuple[str, str], CgroupSnapshot] | None = None
        self.after_stats = ()
        self.sampler = ControllerSampler()

    def before_job(self) -> None:
        self.ready_elapsed_seconds = time.monotonic() - self.started
        self.before_traffic_pods = _pods()
        self.before_traffic_events = _events()
        runner._validate_serving_pods(self.before_traffic_pods, replica_count=2)
        self.before_cgroups = _serving_cgroups(self.before_traffic_pods)
        self.before_stats = _runtime_stats()

    def job_started(self) -> None:
        self.sampler.start()

    def after_job(self) -> None:
        self.sampler.stop()
        self.after_pods = _pods()
        runner._validate_serving_pods(self.after_pods, replica_count=2)
        self.after_cgroups = _serving_cgroups(self.after_pods)
        self.after_stats = _runtime_stats()

    def finish(self, *, profile: str, controller_output: str) -> Mapping[str, object]:
        if any(
            value is None
            for value in (
                self.ready_elapsed_seconds,
                self.before_traffic_pods,
                self.before_traffic_events,
                self.before_cgroups,
                self.after_pods,
                self.after_cgroups,
            )
        ):
            raise RuntimeError("Phase 7 collector did not complete all boundaries")
        final_nodes = _nodes()
        final_events = _events()
        final_shared = _shared_node_states()
        job = _json(
            _kubectl(
                "get",
                "job",
                "ibg-hybrid-controller-phase7",
                "-n",
                runner.HYBRID_NAMESPACE,
                "-o",
                "json",
            )
        )
        status = job.get("status")
        spec = job.get("spec")
        if not isinstance(status, dict) or not isinstance(spec, dict):
            raise RuntimeError("Phase 7 controller Job status/spec is incomplete")
        duration = _iso_seconds(status.get("startTime"), status.get("completionTime"))
        deadline = spec.get("activeDeadlineSeconds")
        if isinstance(deadline, bool) or not isinstance(deadline, int):
            raise RuntimeError("Phase 7 controller deadline is invalid")
        controller_completed = status.get("succeeded") == 1
        slots = [json.loads(line) for line in controller_output.splitlines() if line]
        if len(slots) != 5:
            raise RuntimeError("Phase 7 gate must emit exactly five slot records")
        for slot in slots:
            if (
                slot.get("configuration")
                != {"num_flows": 3, "num_stages": 3, "num_replicas": 2, "stage_budget": 2}
                or slot.get("observation_count") != 6
                or slot.get("measured_pair_count") != 3
                or not all(
                    slot.get(field) is True
                    for field in (
                        "complete_placement_before_one_request",
                        "skipped_stage_absent",
                        "separated_jitter_valid",
                        "seedless_kernel_provenance",
                        "belief_retained_from_previous",
                        "pure_kernel_replay_parity",
                    )
                )
            ):
                raise RuntimeError("Phase 7 semantic slot evidence is incomplete")
        before_processes = runner._serving_process_snapshot(
            self.before_traffic_pods, replica_count=2
        )
        after_processes = runner._serving_process_snapshot(
            self.after_pods, replica_count=2
        )
        restarts = sum(
            count for item in after_processes for _name, count in item.container_restarts
        )
        cgroup_deltas = {
            key: cgroup_delta(self.before_cgroups[key], self.after_cgroups[key])
            for key in self.before_cgroups
        }
        if set(cgroup_deltas) != set(self.after_cgroups):
            raise RuntimeError("serving cgroup identities changed during traffic")
        rollout_fatal, rollout_probe_failures, rollout_events = _new_event_summary(
            self.initial_events, self.before_traffic_events
        )
        post_fatal, post_ready_probe_failures, post_events = _new_event_summary(
            self.before_traffic_events, final_events
        )
        new_fatal = rollout_fatal + post_fatal
        node_summary = _node_resource_summary(final_nodes)
        all_samples = tuple(self.before_stats) + tuple(self.after_stats)
        processor_deltas = [
            delta
            for (_uid, container), delta in cgroup_deltas.items()
            if container == "private-processor"
        ]
        decision = None
        if profile == "candidate":
            decision = evaluate_processor_candidate(
                samples=all_samples,
                processor_deltas=processor_deltas,
                serving_restarts=restarts,
                fatal_event_count=new_fatal,
                post_ready_probe_failure_count=post_ready_probe_failures,
                node_pressure=node_summary["pressure"],
                all_ready=True,
                controller_completed=controller_completed,
                controller_duration_seconds=duration,
                controller_deadline_seconds=deadline,
            )
        initial_node_uid = _single_node_uid(self.initial_nodes)
        final_node_uid = _single_node_uid(final_nodes)
        if initial_node_uid != final_node_uid:
            raise RuntimeError("Phase 7 changed the dedicated Kubernetes node UID")
        for states in (self.initial_shared, final_shared):
            for name in ("ibg-control-plane", "ibg-worker", "ibg-worker2"):
                if not states.get(name, "").startswith("Exited"):
                    raise RuntimeError(f"shared node {name} did not remain stopped")
        return {
            "schema_version": HYBRID_KERNEL_RESOURCE_EVIDENCE_VERSION,
            "processor_memory_profile": profile,
            "topology": {"flows": 3, "stages": 3, "replicas": 2},
            "ready_elapsed_seconds": self.ready_elapsed_seconds,
            "controller": {
                "completed": controller_completed,
                "duration_seconds": duration,
                "deadline_seconds": deadline,
                "deadline_margin_seconds": deadline - duration,
                "max_memory_current_bytes": max(
                    sample.memory_current_bytes for sample in self.sampler.samples
                ),
                "max_process_rss_bytes": max(
                    sample.process_rss_bytes or 0 for sample in self.sampler.samples
                ),
                "cpu_usage_usec": max(
                    sample.cpu_usage_usec for sample in self.sampler.samples
                ),
                "throttled_usec": max(
                    sample.cpu_throttled_usec for sample in self.sampler.samples
                ),
                "sample_count": len(self.sampler.samples),
            },
            "containers": _container_summary(all_samples, cgroup_deltas),
            "health": {
                "serving_restart_count": restarts,
                "fatal_event_count": new_fatal,
                "rollout_probe_failure_count": rollout_probe_failures,
                "post_ready_probe_failure_count": post_ready_probe_failures,
                "new_events": list(rollout_events + post_events),
                "complete_ready_coverage": True,
            },
            "node": node_summary,
            "lineage": {
                "node_uid": final_node_uid,
                "before_traffic": [asdict(item) for item in before_processes],
                "after_traffic": [asdict(item) for item in after_processes],
                "shared_nodes_before": self.initial_shared,
                "shared_nodes_after": final_shared,
            },
            "semantics": {
                "slot_count": len(slots),
                "observations_per_slot": [item["observation_count"] for item in slots],
                "measured_pairs_per_slot": [item["measured_pair_count"] for item in slots],
                "all_parity": all(item["pure_kernel_replay_parity"] for item in slots),
            },
            "candidate_decision": asdict(decision) if decision is not None else None,
        }


def _single_node_uid(document: Mapping[str, object]) -> str:
    items = document.get("items")
    if not isinstance(items, list) or len(items) != 1:
        raise RuntimeError("Phase 7 requires exactly one dedicated node")
    metadata = items[0].get("metadata") if isinstance(items[0], dict) else None
    if not isinstance(metadata, dict) or not isinstance(metadata.get("uid"), str):
        raise RuntimeError("dedicated node lacks a UID")
    return metadata["uid"]


def _node_resource_summary(document: Mapping[str, object]) -> Mapping[str, object]:
    items = document.get("items")
    if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
        raise RuntimeError("Phase 7 requires one node resource record")
    status = items[0].get("status")
    if not isinstance(status, dict):
        raise RuntimeError("Phase 7 node status is incomplete")
    conditions = status.get("conditions")
    if not isinstance(conditions, list):
        raise RuntimeError("Phase 7 node conditions are incomplete")
    condition_map = {
        item.get("type"): item.get("status")
        for item in conditions
        if isinstance(item, dict) and isinstance(item.get("type"), str)
    }
    required = {"Ready", "MemoryPressure", "DiskPressure", "PIDPressure"}
    if not required.issubset(condition_map):
        raise RuntimeError("Phase 7 node lacks required pressure conditions")
    pressure = any(
        condition_map[name] == "True"
        for name in ("MemoryPressure", "DiskPressure", "PIDPressure")
    )
    return {
        "capacity": status.get("capacity"),
        "allocatable": status.get("allocatable"),
        "conditions": condition_map,
        "pressure": pressure,
    }


def _container_summary(samples, deltas) -> Mapping[str, object]:
    result = {}
    for container_name in ("private-processor", "public-forwarder", "flow-generator"):
        selected_samples = [
            sample for sample in samples if sample.container_name == container_name
        ]
        selected_deltas = [
            delta
            for (_uid, name), delta in deltas.items()
            if name == container_name
        ]
        if not selected_samples or not selected_deltas:
            raise RuntimeError(f"resource evidence lacks {container_name}")
        memory_events = {}
        for delta in selected_deltas:
            for field, value in delta.memory_events:
                memory_events[field] = memory_events.get(field, 0) + value
        result[container_name] = {
            "container_count": len(selected_deltas),
            "max_working_set_bytes": max(
                item.memory_working_set_bytes for item in selected_samples
            ),
            "max_rss_bytes": max(item.memory_rss_bytes for item in selected_samples),
            "max_memory_peak_bytes": max(item.memory_peak_bytes for item in selected_deltas),
            "cpu_usage_usec": sum(item.cpu_usage_usec for item in selected_deltas),
            "nr_throttled": sum(item.cpu_nr_throttled for item in selected_deltas),
            "throttled_usec": sum(item.cpu_throttled_usec for item in selected_deltas),
            "memory_events": memory_events,
        }
    return result


def parse_args(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one bounded Hybrid 3x3x2 Phase 7 resource-evidence gate."
    )
    parser.add_argument(
        "--processor-memory-profile",
        choices=tuple(PROCESSOR_MEMORY_PROFILES),
        required=True,
    )
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_args(arguments)
    try:
        collector = Phase7Collector()
        output = runner.run_small(
            skip_build=True,
            requested_flows=3,
            requested_stages=3,
            requested_replicas=2,
            rollout_batch_size=1,
            processor_memory_profile=args.processor_memory_profile,
            before_controller_job=collector.before_job,
            controller_job_started=collector.job_started,
            after_controller_job=collector.after_job,
        )
        evidence = collector.finish(
            profile=args.processor_memory_profile,
            controller_output=output,
        )
        print(json.dumps(evidence, sort_keys=True, separators=(",", ":")))
        if args.processor_memory_profile == "candidate" and not evidence[
            "candidate_decision"
        ]["accepted"]:
            return 2
    except (
        HybridKernelResourceEvidenceError,
        RuntimeError,
        subprocess.SubprocessError,
        ValueError,
    ) as error:
        print(f"Hybrid Phase 7 evidence failure: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
