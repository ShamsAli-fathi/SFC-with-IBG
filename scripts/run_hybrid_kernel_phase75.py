#!/usr/bin/env python3
"""Run bounded one/multi-worker Hybrid Kernel MC evidence at exactly 3x3x2."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import subprocess
import sys
import threading
from typing import Mapping, Sequence

from IBG_Hybrid.kernel_mc_evidence import (
    HYBRID_KERNEL_MC_EVIDENCE_VERSION,
    HybridKernelMcEvidenceError,
    parse_direct_child_pids,
    require_worker_count_decision_equality,
    validate_mc_slot_evidence,
)
from IBG_Hybrid.kernel_resource_evidence import (
    CANDIDATE_PROCESSOR_MEMORY,
    HybridKernelResourceEvidenceError,
    detect_resource_profile,
    parse_cgroup_snapshot,
)
from scripts import run_hybrid_kernel_phase4 as runner
from scripts import run_hybrid_kernel_phase7 as phase7


CONTROLLER_SAMPLE_SCRIPT = phase7.CONTROLLER_CGROUP_SCRIPT + (
    "; printf '__DIRECT_CHILDREN__\\n'; "
    "cat /proc/1/task/1/children; printf '\\n'"
)
SHARED_NODE_NAMES = (
    "ibg-control-plane",
    "ibg-worker",
    "ibg-worker2",
)


def _shared_nodes_are_stopped(states: Mapping[str, str]) -> bool:
    return all(
        name in states and states[name].startswith("Exited")
        for name in SHARED_NODE_NAMES
    )


class ControllerMcSampler:
    def __init__(self, job_name: str) -> None:
        self.job_name = job_name
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.samples: list[tuple[object, tuple[int, ...]]] = []
        self.errors: list[str] = []

    def start(self) -> None:
        self._thread = threading.Thread(target=self._sample, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=10.0)
            if self._thread.is_alive():
                raise RuntimeError("Phase 7.5 controller sampler did not stop")
        if not self.samples:
            detail = f": {self.errors[-1]}" if self.errors else ""
            raise RuntimeError(
                "Phase 7.5 controller sampler captured no sample" + detail
            )

    def _sample(self) -> None:
        while not self._stop.is_set():
            try:
                pods = phase7._json(
                    phase7._kubectl(
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
                    pod_name = (
                        metadata.get("name") if isinstance(metadata, dict) else None
                    )
                    if isinstance(pod_name, str):
                        output = phase7._run(
                            phase7._kubectl(
                                "exec",
                                "-n",
                                runner.HYBRID_NAMESPACE,
                                pod_name,
                                "-c",
                                "controller",
                                "--",
                                "/bin/sh",
                                "-c",
                                CONTROLLER_SAMPLE_SCRIPT,
                            ),
                            timeout=5.0,
                        )
                        self.samples.append(
                            (
                                parse_cgroup_snapshot(output),
                                parse_direct_child_pids(output),
                            )
                        )
            except (
                HybridKernelMcEvidenceError,
                HybridKernelResourceEvidenceError,
                OSError,
                RuntimeError,
                ValueError,
                subprocess.SubprocessError,
            ) as error:
                self.errors.append(str(error))
            self._stop.wait(0.05)


class Phase75Collector:
    def __init__(self, worker_count: int) -> None:
        self.worker_count = worker_count
        self.initial_nodes = phase7._nodes()
        self.initial_pods = phase7._pods()
        self.initial_events = phase7._events()
        self.initial_shared = phase7._shared_node_states()
        self.before_pods: Mapping[str, object] | None = None
        self.before_events: Mapping[str, object] | None = None
        self.after_pods: Mapping[str, object] | None = None
        self.sampler = ControllerMcSampler(runner.PHASE75_CONTROLLER_JOB_NAME)

    def before_job(self) -> None:
        self.before_pods = phase7._pods()
        self.before_events = phase7._events()
        runner._validate_serving_pods(self.before_pods, replica_count=2)

    def job_started(self) -> None:
        self.sampler.start()

    def after_job(self) -> None:
        self.sampler.stop()
        self.after_pods = phase7._pods()
        runner._validate_serving_pods(self.after_pods, replica_count=2)

    def finish(self, controller_output: str) -> Mapping[str, object]:
        if self.before_pods is None or self.before_events is None or self.after_pods is None:
            raise RuntimeError("Phase 7.5 collector missed a lifecycle boundary")
        slots = tuple(
            json.loads(line)
            for line in controller_output.splitlines()
            if line.strip()
        )
        if not all(isinstance(slot, dict) for slot in slots):
            raise RuntimeError("Phase 7.5 controller output is not JSON objects")
        validate_mc_slot_evidence(slots, worker_count=self.worker_count)

        job = phase7._json(
            phase7._kubectl(
                "get",
                "job",
                runner.PHASE75_CONTROLLER_JOB_NAME,
                "-n",
                runner.HYBRID_NAMESPACE,
                "-o",
                "json",
            )
        )
        status = job.get("status")
        spec = job.get("spec")
        if not isinstance(status, dict) or not isinstance(spec, dict):
            raise RuntimeError("Phase 7.5 controller Job status/spec is incomplete")
        duration = phase7._iso_seconds(
            status.get("startTime"), status.get("completionTime")
        )
        deadline = spec.get("activeDeadlineSeconds")
        if isinstance(deadline, bool) or not isinstance(deadline, int):
            raise RuntimeError("Phase 7.5 controller deadline is invalid")
        if status.get("succeeded") != 1 or deadline - duration < deadline / 2:
            raise RuntimeError(
                "Phase 7.5 controller did not complete with half-deadline margin"
            )

        controller_pods = phase7._json(
            phase7._kubectl(
                "get",
                "pods",
                "-n",
                runner.HYBRID_NAMESPACE,
                "-l",
                f"job-name={runner.PHASE75_CONTROLLER_JOB_NAME}",
                "-o",
                "json",
            )
        )
        controller_items = controller_pods.get("items")
        if not isinstance(controller_items, list) or len(controller_items) != 1:
            raise RuntimeError("Phase 7.5 requires one controller Pod")
        controller_status = controller_items[0].get("status")
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
            raise RuntimeError("Phase 7.5 controller Pod did not exit cleanly")

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
            raise RuntimeError("Phase 7.5 changed node or serving process identity")
        if not (
            _shared_nodes_are_stopped(self.initial_shared)
            and _shared_nodes_are_stopped(final_shared)
        ):
            raise RuntimeError("historical shared ibg nodes are not stopped")
        if (
            detect_resource_profile(runner._statefulset_inventory(runner._execute))
            != CANDIDATE_PROCESSOR_MEMORY
        ):
            raise RuntimeError("Phase 7.5 changed the accepted processor resources")
        fatal, probes, events = phase7._new_event_summary(
            self.before_events, final_events
        )
        node = phase7._node_resource_summary(final_nodes)
        if fatal or probes or node["pressure"]:
            raise RuntimeError("Phase 7.5 produced unhealthy runtime evidence")

        cgroups = [sample for sample, _children in self.sampler.samples]
        maximum_children = max(
            len(children) for _sample, children in self.sampler.samples
        )
        if maximum_children != self.worker_count:
            raise RuntimeError(
                "Phase 7.5 did not observe the requested bounded worker pool: "
                f"expected={self.worker_count}, observed={maximum_children}"
            )
        return {
            "schema_version": HYBRID_KERNEL_MC_EVIDENCE_VERSION,
            "topology": {"flows": 3, "stages": 3, "replicas": 2},
            "policy": "mc",
            "mc_workers": self.worker_count,
            "controller": {
                "completed": True,
                "restart_count": 0,
                "duration_seconds": duration,
                "deadline_seconds": deadline,
                "deadline_margin_seconds": deadline - duration,
                "max_process_rss_bytes": max(
                    sample.process_rss_bytes or 0 for sample in cgroups
                ),
                "max_cgroup_memory_bytes": max(
                    sample.memory_current_bytes for sample in cgroups
                ),
                "max_cgroup_memory_peak_bytes": max(
                    sample.memory_peak_bytes for sample in cgroups
                ),
                "cpu_usage_usec": max(sample.cpu_usage_usec for sample in cgroups),
                "throttled_usec": max(
                    sample.cpu_throttled_usec for sample in cgroups
                ),
                "maximum_direct_children": maximum_children,
                "sample_count": len(cgroups),
                "pool_cleanup_before_each_next_boundary": all(
                    slot["active_child_processes_after_slot"] == 0 for slot in slots
                ),
            },
            "lineage": {
                "node_uid": final_node_uid,
                "before": [asdict(item) for item in before_processes],
                "after": [asdict(item) for item in after_processes],
                "shared_nodes_before": self.initial_shared,
                "shared_nodes_after": final_shared,
            },
            "health": {
                "fatal_event_count": fatal,
                "post_ready_probe_failure_count": probes,
                "node_pressure": node["pressure"],
                "new_events": list(events),
            },
            "slots": list(slots),
        }


def _multi_worker_count(value: str) -> int:
    parsed = int(value)
    if parsed < 2 or parsed > runner.MAX_HYBRID_KERNEL_MC_WORKERS:
        raise argparse.ArgumentTypeError(
            "multi-worker count must be between 2 and "
            f"{runner.MAX_HYBRID_KERNEL_MC_WORKERS}"
        )
    return parsed


def parse_args(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run one-worker then bounded multi-worker manual MC on the "
            "persistent Hybrid 3x3x2 cluster."
        )
    )
    parser.add_argument("--multi-workers", type=_multi_worker_count, default=2)
    return parser.parse_args(arguments)


def _run_gate(worker_count: int) -> Mapping[str, object]:
    collector = Phase75Collector(worker_count)
    output = runner.run_small(
        skip_build=True,
        requested_flows=3,
        requested_stages=3,
        requested_replicas=2,
        rollout_batch_size=1,
        processor_memory_profile="candidate",
        controller_policy="mc",
        mc_workers=worker_count,
        before_controller_job=collector.before_job,
        controller_job_started=collector.job_started,
        after_controller_job=collector.after_job,
    )
    return collector.finish(output)


def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_args(arguments)
    try:
        one = _run_gate(1)
        multiple = _run_gate(args.multi_workers)
        require_worker_count_decision_equality(one["slots"], multiple["slots"])
        if one["lineage"] != multiple["lineage"]:
            raise RuntimeError("Phase 7.5 changed serving lineage between MC gates")
        summary = {
            "schema_version": HYBRID_KERNEL_MC_EVIDENCE_VERSION,
            "one_worker": one,
            "multi_worker": multiple,
            "worker_count_decision_equality": True,
            "pure_kernel_parity": all(
                slot["pure_kernel_replay_parity"]
                for evidence in (one, multiple)
                for slot in evidence["slots"]
            ),
        }
        print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    except (
        HybridKernelMcEvidenceError,
        HybridKernelResourceEvidenceError,
        RuntimeError,
        subprocess.SubprocessError,
        ValueError,
    ) as error:
        print(f"Hybrid Phase 7.5 evidence failure: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
