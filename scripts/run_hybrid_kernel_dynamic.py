#!/usr/bin/env python3
"""Collect the bounded 10x3x5 dynamic-topology Hybrid Kernel gate."""

from __future__ import annotations

from dataclasses import asdict
import json
import subprocess
import sys
import time
from typing import Mapping

from IBG_Hybrid.contracts import HybridConfiguration
from IBG_Hybrid.kernel_dynamic_topology_evidence import (
    HYBRID_KERNEL_DYNAMIC_TOPOLOGY_EVIDENCE_VERSION,
    HybridKernelDynamicTopologyEvidenceError,
    validate_dynamic_lookahead_slots,
)
from IBG_Hybrid.kernel_resource_evidence import (
    CANDIDATE_PROCESSOR_MEMORY,
    HybridKernelResourceEvidenceError,
    cgroup_delta,
    detect_resource_profile,
)
from scripts import run_hybrid_kernel_phase4 as runner
from scripts import run_hybrid_kernel_phase7 as phase7


ACCEPTANCE_CONFIGURATION = HybridConfiguration(10, 3, 5, 2)
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
            f"job-name={runner.DYNAMIC_CONTROLLER_JOB_NAME}",
            "-o",
            "json",
        )
    )
    items = document.get("items")
    if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
        raise RuntimeError("dynamic topology gate requires exactly one controller Pod")
    return items[0]


class DynamicTopologyCollector:
    def __init__(self) -> None:
        self.started = time.monotonic()
        self.initial_replica_count = runner.discover_existing_replica_state(
            runner._statefulset_inventory(runner._execute)
        ).replica_count
        if self.initial_replica_count not in {2, 5}:
            raise RuntimeError(
                "dynamic topology evidence must start at two replicas or resume "
                "at the completed five-replica target"
            )
        self.initial_nodes = phase7._nodes()
        self.initial_pods = phase7._pods()
        self.initial_events = phase7._events()
        self.initial_shared = phase7._shared_node_states()
        runner._validate_serving_pods(
            self.initial_pods, replica_count=self.initial_replica_count
        )
        self.before_pods: Mapping[str, object] | None = None
        self.before_events: Mapping[str, object] | None = None
        self.before_cgroups = None
        self.before_stats = ()
        self.after_pods: Mapping[str, object] | None = None
        self.after_cgroups = None
        self.after_stats = ()
        self.ready_elapsed_seconds: float | None = None
        self.sampler = phase7.ControllerSampler(runner.DYNAMIC_CONTROLLER_JOB_NAME)

    def before_job(self) -> None:
        self.ready_elapsed_seconds = time.monotonic() - self.started
        self.before_pods = phase7._pods()
        self.before_events = phase7._events()
        runner._validate_serving_pods(self.before_pods, replica_count=5)
        self.before_cgroups = phase7._serving_cgroups(
            self.before_pods, replica_count=5
        )
        self.before_stats = phase7._runtime_stats(replica_count=5)

    def job_started(self) -> None:
        self.sampler.start()

    def after_job(self) -> None:
        self.sampler.stop()
        self.after_pods = phase7._pods()
        runner._validate_serving_pods(self.after_pods, replica_count=5)
        self.after_cgroups = phase7._serving_cgroups(
            self.after_pods, replica_count=5
        )
        self.after_stats = phase7._runtime_stats(replica_count=5)

    def finish(self, output: str) -> dict[str, object]:
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
            raise RuntimeError("dynamic topology collector missed a lifecycle boundary")
        slots = tuple(json.loads(line) for line in output.splitlines() if line.strip())
        validate_dynamic_lookahead_slots(slots, ACCEPTANCE_CONFIGURATION)

        job = phase7._json(
            phase7._kubectl(
                "get",
                "job",
                runner.DYNAMIC_CONTROLLER_JOB_NAME,
                "-n",
                runner.HYBRID_NAMESPACE,
                "-o",
                "json",
            )
        )
        status = job.get("status")
        spec = job.get("spec")
        if not isinstance(status, dict) or not isinstance(spec, dict):
            raise RuntimeError("dynamic controller Job status/spec is incomplete")
        duration = phase7._iso_seconds(
            status.get("startTime"), status.get("completionTime")
        )
        deadline = spec.get("activeDeadlineSeconds")
        if isinstance(deadline, bool) or not isinstance(deadline, int):
            raise RuntimeError("dynamic controller deadline is invalid")
        if status.get("succeeded") != 1 or deadline - duration < deadline / 2:
            raise RuntimeError("dynamic controller lacks the required deadline margin")

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
            raise RuntimeError("dynamic controller did not exit cleanly")

        final_nodes = phase7._nodes()
        final_events = phase7._events()
        final_shared = phase7._shared_node_states()
        initial_node_uid = phase7._single_node_uid(self.initial_nodes)
        final_node_uid = phase7._single_node_uid(final_nodes)
        initial_processes = runner._serving_process_snapshot(
            self.initial_pods, replica_count=self.initial_replica_count
        )
        before_processes = runner._serving_process_snapshot(
            self.before_pods, replica_count=5
        )
        after_processes = runner._serving_process_snapshot(
            self.after_pods, replica_count=5
        )
        runner._validate_process_preservation(initial_processes, before_processes)
        if before_processes != after_processes or initial_node_uid != final_node_uid:
            raise RuntimeError("dynamic gate changed a Ready serving process or node")
        old_names = {item.pod_name for item in initial_processes}
        new_names = {item.pod_name for item in before_processes} - old_names
        expected_new_names = (
            {
                f"hybrid-stage-{stage}-{ordinal}"
                for stage in range(1, 4)
                for ordinal in (2, 3, 4)
            }
            if self.initial_replica_count == 2
            else set()
        )
        if new_names != expected_new_names:
            raise RuntimeError("dynamic rollout created an unexpected serving Pod set")
        if not (
            _shared_nodes_are_stopped(self.initial_shared)
            and _shared_nodes_are_stopped(final_shared)
        ):
            raise RuntimeError("historical shared ibg nodes are not stopped")
        if (
            detect_resource_profile(runner._statefulset_inventory(runner._execute))
            != CANDIDATE_PROCESSOR_MEMORY
        ):
            raise RuntimeError("dynamic topology changed accepted service resources")

        post_ready_fatal, post_ready_probes, post_ready_events = (
            phase7._new_event_summary(self.before_events, final_events)
        )
        _rollout_fatal, _rollout_probes, rollout_events = phase7._new_event_summary(
            self.initial_events, self.before_events
        )
        node = phase7._node_resource_summary(final_nodes)
        cgroup_deltas = {
            key: cgroup_delta(self.before_cgroups[key], self.after_cgroups[key])
            for key in self.before_cgroups
        }
        if set(cgroup_deltas) != set(self.after_cgroups):
            raise RuntimeError("serving cgroup identity changed during dynamic traffic")
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
            post_ready_fatal
            or post_ready_probes
            or node["pressure"]
            or serving_restarts
            or memory_event_count
            or controller_memory_peak >= 1024 * 1024 * 1024
        ):
            raise RuntimeError("dynamic 10x3x5 resource envelope is unsafe")

        samples = tuple(self.before_stats) + tuple(self.after_stats)
        return {
            "schema_version": HYBRID_KERNEL_DYNAMIC_TOPOLOGY_EVIDENCE_VERSION,
            "topology": {"flows": 10, "stages": 3, "replicas": 5},
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
                "fatal_event_count": post_ready_fatal,
                "post_ready_probe_failure_count": post_ready_probes,
                "node_pressure": node["pressure"],
                "rollout_events": list(rollout_events),
                "post_ready_events": list(post_ready_events),
            },
            "node": node,
            "lineage": {
                "node_uid": final_node_uid,
                "initial": [asdict(item) for item in initial_processes],
                "after_scale": [asdict(item) for item in before_processes],
                "after_traffic": [asdict(item) for item in after_processes],
                "new_pods": sorted(new_names),
                "shared_nodes_before": self.initial_shared,
                "shared_nodes_after": final_shared,
            },
            "slots": list(slots),
        }


def main() -> int:
    try:
        collector = DynamicTopologyCollector()
        output = runner.run_small(
            skip_build=True,
            requested_flows=10,
            requested_stages=3,
            requested_replicas=5,
            rollout_batch_size=2,
            before_controller_job=collector.before_job,
            controller_job_started=collector.job_started,
            after_controller_job=collector.after_job,
        )
        evidence = collector.finish(output)
        if collector.initial_replica_count == 5:
            evidence["unchanged_rerun"] = {
                "serving_processes_preserved": True,
                "slot_count": len(evidence["slots"]),
                "shared_nodes_after": phase7._shared_node_states(),
                "resumed_after_completed_scale_gate": True,
            }
            print(json.dumps(evidence, sort_keys=True, separators=(",", ":")))
            return 0
        before_rerun = runner._serving_process_snapshot(
            phase7._pods(), replica_count=5
        )
        rerun_output = runner.run_small(
            skip_build=True,
            requested_flows=10,
            requested_stages=3,
            requested_replicas=5,
            rollout_batch_size=2,
        )
        rerun_slots = tuple(
            json.loads(line) for line in rerun_output.splitlines() if line.strip()
        )
        validate_dynamic_lookahead_slots(rerun_slots, ACCEPTANCE_CONFIGURATION)
        after_rerun = runner._serving_process_snapshot(
            phase7._pods(), replica_count=5
        )
        if before_rerun != after_rerun:
            raise RuntimeError("unchanged dynamic rerun replaced a serving process")
        final_shared = phase7._shared_node_states()
        if not _shared_nodes_are_stopped(final_shared):
            raise RuntimeError("historical shared ibg nodes started during rerun")
        evidence["unchanged_rerun"] = {
            "serving_processes_preserved": True,
            "slot_count": len(rerun_slots),
            "shared_nodes_after": final_shared,
        }
        print(json.dumps(evidence, sort_keys=True, separators=(",", ":")))
    except (
        HybridKernelDynamicTopologyEvidenceError,
        HybridKernelResourceEvidenceError,
        RuntimeError,
        subprocess.SubprocessError,
        ValueError,
    ) as error:
        print(f"Hybrid dynamic topology evidence failure: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
