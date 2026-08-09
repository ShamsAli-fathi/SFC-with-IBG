#!/usr/bin/env python3
"""Run the first bounded Hybrid Kernel Phase 8 lookahead scale gate."""

from __future__ import annotations

from dataclasses import asdict
import json
import subprocess
import sys
import time
from typing import Mapping

from IBG_Hybrid.kernel_phase8_evidence import (
    HYBRID_KERNEL_PHASE8_GATE1_EVIDENCE_VERSION,
    HybridKernelPhase8EvidenceError,
    validate_phase8_gate1_slots,
)
from IBG_Hybrid.kernel_resource_evidence import (
    CANDIDATE_PROCESSOR_MEMORY,
    HybridKernelResourceEvidenceError,
    cgroup_delta,
    detect_resource_profile,
)
from scripts import run_hybrid_kernel_phase4 as runner
from scripts import run_hybrid_kernel_phase7 as phase7


SHARED_NODE_NAMES = ("ibg-control-plane", "ibg-worker", "ibg-worker2")


def _shared_nodes_are_stopped(states: Mapping[str, str]) -> bool:
    return all(
        name in states and states[name].startswith("Exited")
        for name in SHARED_NODE_NAMES
    )


def _controller_pod() -> Mapping[str, object]:
    document = phase7._json(
        phase7._kubectl(
            "get",
            "pods",
            "-n",
            runner.HYBRID_NAMESPACE,
            "-l",
            f"job-name={runner.PHASE8_GATE1_CONTROLLER_JOB_NAME}",
            "-o",
            "json",
        )
    )
    items = document.get("items")
    if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
        raise RuntimeError("Phase 8 Gate 1 requires exactly one controller Pod")
    return items[0]


class Phase8Gate1Collector:
    def __init__(self) -> None:
        self.started = time.monotonic()
        self.initial_nodes = phase7._nodes()
        self.initial_pods = phase7._pods()
        self.initial_events = phase7._events()
        self.initial_shared = phase7._shared_node_states()
        self.before_pods: Mapping[str, object] | None = None
        self.before_events: Mapping[str, object] | None = None
        self.before_cgroups = None
        self.before_stats = ()
        self.after_pods: Mapping[str, object] | None = None
        self.after_cgroups = None
        self.after_stats = ()
        self.ready_elapsed_seconds: float | None = None
        self.sampler = phase7.ControllerSampler(
            runner.PHASE8_GATE1_CONTROLLER_JOB_NAME
        )

    def before_job(self) -> None:
        self.ready_elapsed_seconds = time.monotonic() - self.started
        self.before_pods = phase7._pods()
        self.before_events = phase7._events()
        runner._validate_serving_pods(self.before_pods, replica_count=2)
        self.before_cgroups = phase7._serving_cgroups(self.before_pods)
        self.before_stats = phase7._runtime_stats()

    def job_started(self) -> None:
        self.sampler.start()

    def after_job(self) -> None:
        self.sampler.stop()
        self.after_pods = phase7._pods()
        runner._validate_serving_pods(self.after_pods, replica_count=2)
        self.after_cgroups = phase7._serving_cgroups(self.after_pods)
        self.after_stats = phase7._runtime_stats()

    def finish(self, output: str) -> Mapping[str, object]:
        if any(
            value is None
            for value in (
                self.before_pods,
                self.before_events,
                self.before_cgroups,
                self.after_pods,
                self.after_cgroups,
                self.ready_elapsed_seconds,
            )
        ):
            raise RuntimeError("Phase 8 Gate 1 collector missed a lifecycle boundary")
        slots = tuple(
            json.loads(line) for line in output.splitlines() if line.strip()
        )
        validate_phase8_gate1_slots(slots)

        job = phase7._json(
            phase7._kubectl(
                "get",
                "job",
                runner.PHASE8_GATE1_CONTROLLER_JOB_NAME,
                "-n",
                runner.HYBRID_NAMESPACE,
                "-o",
                "json",
            )
        )
        status = job.get("status")
        spec = job.get("spec")
        if not isinstance(status, dict) or not isinstance(spec, dict):
            raise RuntimeError("Phase 8 Gate 1 controller Job is incomplete")
        duration = phase7._iso_seconds(
            status.get("startTime"), status.get("completionTime")
        )
        deadline = spec.get("activeDeadlineSeconds")
        if isinstance(deadline, bool) or not isinstance(deadline, int):
            raise RuntimeError("Phase 8 Gate 1 controller deadline is invalid")
        if status.get("succeeded") != 1 or deadline - duration < deadline / 2:
            raise RuntimeError(
                "Phase 8 Gate 1 controller lacks the required deadline margin"
            )

        controller_pod = _controller_pod()
        controller_status = controller_pod.get("status")
        statuses = (
            controller_status.get("containerStatuses")
            if isinstance(controller_status, dict)
            else None
        )
        if (
            not isinstance(controller_status, dict)
            or controller_status.get("phase") != "Succeeded"
            or not isinstance(statuses, list)
            or len(statuses) != 1
            or statuses[0].get("restartCount") != 0
        ):
            raise RuntimeError("Phase 8 Gate 1 controller did not exit cleanly")

        final_nodes = phase7._nodes()
        final_events = phase7._events()
        final_shared = phase7._shared_node_states()
        initial_node_uid = phase7._single_node_uid(self.initial_nodes)
        final_node_uid = phase7._single_node_uid(final_nodes)
        before_processes = runner._serving_process_snapshot(
            self.before_pods, replica_count=2
        )
        after_processes = runner._serving_process_snapshot(
            self.after_pods, replica_count=2
        )
        if initial_node_uid != final_node_uid or before_processes != after_processes:
            raise RuntimeError("Phase 8 Gate 1 changed node or serving process identity")
        if not (
            _shared_nodes_are_stopped(self.initial_shared)
            and _shared_nodes_are_stopped(final_shared)
        ):
            raise RuntimeError("historical shared ibg nodes are not stopped")
        if (
            detect_resource_profile(runner._statefulset_inventory(runner._execute))
            != CANDIDATE_PROCESSOR_MEMORY
        ):
            raise RuntimeError("Phase 8 Gate 1 changed accepted service resources")

        fatal, probes, events = phase7._new_event_summary(
            self.before_events, final_events
        )
        node = phase7._node_resource_summary(final_nodes)
        cgroup_deltas = {
            key: cgroup_delta(self.before_cgroups[key], self.after_cgroups[key])
            for key in self.before_cgroups
        }
        if set(cgroup_deltas) != set(self.after_cgroups):
            raise RuntimeError("serving cgroup identity changed during Phase 8 traffic")
        serving_restarts = sum(
            count
            for item in after_processes
            for _container, count in item.container_restarts
        )
        memory_event_count = sum(
            value
            for delta in cgroup_deltas.values()
            for field, value in delta.memory_events
            if field in {"high", "max", "oom", "oom_kill", "oom_group_kill"}
        )
        controller_memory_peak = max(
            sample.memory_peak_bytes for sample in self.sampler.samples
        )
        if (
            fatal
            or probes
            or node["pressure"]
            or serving_restarts
            or memory_event_count
            or controller_memory_peak >= 1024 * 1024 * 1024
        ):
            raise RuntimeError("Phase 8 Gate 1 resource envelope is unsafe")

        samples = tuple(self.before_stats) + tuple(self.after_stats)
        return {
            "schema_version": HYBRID_KERNEL_PHASE8_GATE1_EVIDENCE_VERSION,
            "topology": {"flows": 4, "stages": 3, "replicas": 2},
            "policy": "lookahead",
            "ready_elapsed_seconds": self.ready_elapsed_seconds,
            "controller": {
                "completed": True,
                "restart_count": 0,
                "duration_seconds": duration,
                "deadline_seconds": deadline,
                "deadline_margin_seconds": deadline - duration,
                "max_process_rss_bytes": max(
                    sample.process_rss_bytes or 0 for sample in self.sampler.samples
                ),
                "max_cgroup_memory_bytes": max(
                    sample.memory_current_bytes for sample in self.sampler.samples
                ),
                "max_cgroup_memory_peak_bytes": controller_memory_peak,
                "cpu_usage_usec": max(
                    sample.cpu_usage_usec for sample in self.sampler.samples
                ),
                "throttled_usec": max(
                    sample.cpu_throttled_usec for sample in self.sampler.samples
                ),
                "sample_count": len(self.sampler.samples),
            },
            "containers": phase7._container_summary(samples, cgroup_deltas),
            "health": {
                "serving_restart_count": serving_restarts,
                "memory_event_count": memory_event_count,
                "fatal_event_count": fatal,
                "post_ready_probe_failure_count": probes,
                "node_pressure": node["pressure"],
                "new_events": list(events),
            },
            "node": node,
            "lineage": {
                "node_uid": final_node_uid,
                "before": [asdict(item) for item in before_processes],
                "after": [asdict(item) for item in after_processes],
                "shared_nodes_before": self.initial_shared,
                "shared_nodes_after": final_shared,
            },
            "slots": list(slots),
        }


def main() -> int:
    try:
        collector = Phase8Gate1Collector()
        output = runner.run_small(
            skip_build=True,
            requested_flows=4,
            requested_stages=3,
            requested_replicas=2,
            rollout_batch_size=1,
            before_controller_job=collector.before_job,
            controller_job_started=collector.job_started,
            after_controller_job=collector.after_job,
        )
        print(
            json.dumps(
                collector.finish(output), sort_keys=True, separators=(",", ":")
            )
        )
    except (
        HybridKernelPhase8EvidenceError,
        HybridKernelResourceEvidenceError,
        RuntimeError,
        subprocess.SubprocessError,
        ValueError,
    ) as error:
        print(f"Hybrid Phase 8 Gate 1 evidence failure: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
