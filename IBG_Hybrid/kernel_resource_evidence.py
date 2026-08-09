"""Policy-free resource evidence contracts for Hybrid Kernel Phase 7."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Mapping, Sequence

from .kernel_rollout import discover_existing_replica_state


HYBRID_KERNEL_RESOURCE_EVIDENCE_VERSION = (
    "ibg-hybrid-kernel-resource-evidence-v1"
)
MIB = 1024 * 1024


class HybridKernelResourceEvidenceError(ValueError):
    """Raised when resource evidence is incomplete or crosses ownership."""


@dataclass(frozen=True)
class ProcessorMemoryProfile:
    name: str
    request: str
    limit: str
    request_bytes: int
    limit_bytes: int


BASELINE_PROCESSOR_MEMORY = ProcessorMemoryProfile(
    "baseline", "128Mi", "768Mi", 128 * MIB, 768 * MIB
)
CANDIDATE_PROCESSOR_MEMORY = ProcessorMemoryProfile(
    "candidate", "64Mi", "256Mi", 64 * MIB, 256 * MIB
)
PROCESSOR_MEMORY_PROFILES = {
    item.name: item
    for item in (BASELINE_PROCESSOR_MEMORY, CANDIDATE_PROCESSOR_MEMORY)
}


@dataclass(frozen=True, order=True)
class ContainerResourceSample:
    container_id: str
    pod_name: str
    pod_uid: str
    container_name: str
    timestamp_ns: int
    cpu_usage_ns: int
    cpu_usage_nanocores: int
    memory_working_set_bytes: int
    memory_rss_bytes: int


@dataclass(frozen=True)
class CgroupSnapshot:
    cpu_usage_usec: int
    cpu_nr_periods: int
    cpu_nr_throttled: int
    cpu_throttled_usec: int
    memory_current_bytes: int
    memory_peak_bytes: int
    memory_events: tuple[tuple[str, int], ...]
    process_rss_bytes: int | None = None


@dataclass(frozen=True)
class CgroupDelta:
    cpu_usage_usec: int
    cpu_nr_periods: int
    cpu_nr_throttled: int
    cpu_throttled_usec: int
    memory_peak_bytes: int
    memory_events: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class ProcessorCandidateDecision:
    accepted: bool
    reasons: tuple[str, ...]
    max_working_set_bytes: int
    max_memory_peak_bytes: int
    minimum_limit_headroom_bytes: int
    total_throttled_usec: int


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise HybridKernelResourceEvidenceError(f"{field} must be an object")
    return value


def _list(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise HybridKernelResourceEvidenceError(f"{field} must be a list")
    return value


def _nonnegative_integer(value: object, field: str) -> int:
    if isinstance(value, bool):
        raise HybridKernelResourceEvidenceError(
            f"{field} must be a nonnegative integer"
        )
    if isinstance(value, str):
        try:
            value = int(value)
        except ValueError as error:
            raise HybridKernelResourceEvidenceError(
                f"{field} must be a nonnegative integer"
            ) from error
    if not isinstance(value, int) or value < 0:
        raise HybridKernelResourceEvidenceError(
            f"{field} must be a nonnegative integer"
        )
    return value


def _quantity(container: Mapping[str, object], path: Sequence[str]) -> int:
    value: object = container
    for field in path:
        value = _mapping(value, ".".join(path)).get(field)
    return _nonnegative_integer(value, ".".join(path))


def parse_crictl_stats(
    document: Mapping[str, object],
    *,
    namespace: str = "ibg-hybrid-testbed",
) -> tuple[ContainerResourceSample, ...]:
    """Parse only named Hybrid application containers from crictl JSON."""

    accepted_names = {
        "private-processor",
        "public-forwarder",
        "flow-generator",
        "controller",
    }
    samples = []
    identities = set()
    for raw in _list(document.get("stats"), "stats"):
        item = _mapping(raw, "stats entry")
        attributes = _mapping(item.get("attributes"), "stats.attributes")
        labels = _mapping(attributes.get("labels"), "stats.attributes.labels")
        if labels.get("io.kubernetes.pod.namespace") != namespace:
            continue
        container_name = labels.get("io.kubernetes.container.name")
        pod_name = labels.get("io.kubernetes.pod.name")
        pod_uid = labels.get("io.kubernetes.pod.uid")
        container_id = attributes.get("id")
        if container_name not in accepted_names:
            raise HybridKernelResourceEvidenceError(
                f"unexpected Hybrid container in runtime stats: {container_name}"
            )
        if not all(
            isinstance(value, str) and value
            for value in (container_id, pod_name, pod_uid)
        ):
            raise HybridKernelResourceEvidenceError(
                "runtime stats lack a stable container/Pod identity"
            )
        identity = (pod_uid, container_name)
        if identity in identities:
            raise HybridKernelResourceEvidenceError(
                "runtime stats contain duplicate Hybrid container identity"
            )
        identities.add(identity)
        if not isinstance(item.get("cpu"), dict) or not isinstance(
            item.get("memory"), dict
        ):
            # containerd may retain completed Jobs and recently replaced
            # serving containers in the scoped stats inventory without values.
            # The live collector separately requires the exact current
            # application-container count after this parser returns.
            identities.remove(identity)
            continue
        cpu = _mapping(item.get("cpu"), "stats.cpu")
        memory = _mapping(item.get("memory"), "stats.memory")
        cpu_timestamp = _nonnegative_integer(cpu.get("timestamp"), "cpu.timestamp")
        memory_timestamp = _nonnegative_integer(
            memory.get("timestamp"), "memory.timestamp"
        )
        if cpu_timestamp != memory_timestamp:
            raise HybridKernelResourceEvidenceError(
                "runtime CPU and memory timestamps are not correlated"
            )
        samples.append(
            ContainerResourceSample(
                container_id=container_id,
                pod_name=pod_name,
                pod_uid=pod_uid,
                container_name=container_name,
                timestamp_ns=cpu_timestamp,
                cpu_usage_ns=_quantity(
                    cpu, ("usageCoreNanoSeconds", "value")
                ),
                cpu_usage_nanocores=_quantity(
                    cpu, ("usageNanoCores", "value")
                ),
                memory_working_set_bytes=_quantity(
                    memory, ("workingSetBytes", "value")
                ),
                memory_rss_bytes=_quantity(memory, ("rssBytes", "value")),
            )
        )
    return tuple(sorted(samples))


def parse_cgroup_snapshot(text: str) -> CgroupSnapshot:
    """Parse the explicit cgroup-v2/proc sections emitted by the live sampler."""

    sections: dict[str, list[str]] = {}
    current = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("__") and line.endswith("__"):
            current = line.strip("_")
            if current in sections:
                raise HybridKernelResourceEvidenceError(
                    f"duplicate cgroup section: {current}"
                )
            sections[current] = []
        elif current is None:
            raise HybridKernelResourceEvidenceError(
                "cgroup evidence precedes its section marker"
            )
        else:
            sections[current].append(line)
    required = {"CPU", "MEMORY_CURRENT", "MEMORY_PEAK", "MEMORY_EVENTS"}
    if not required.issubset(sections):
        raise HybridKernelResourceEvidenceError(
            "cgroup evidence is missing required sections"
        )

    def pairs(name: str) -> dict[str, int]:
        result = {}
        for line in sections[name]:
            fields = line.split()
            if len(fields) != 2 or fields[0] in result:
                raise HybridKernelResourceEvidenceError(
                    f"invalid {name} cgroup entry"
                )
            result[fields[0]] = _nonnegative_integer(fields[1], name)
        return result

    cpu = pairs("CPU")
    events = pairs("MEMORY_EVENTS")
    for field in ("usage_usec", "nr_periods", "nr_throttled", "throttled_usec"):
        if field not in cpu:
            raise HybridKernelResourceEvidenceError(
                f"cgroup CPU evidence lacks {field}"
            )
    memory_current_lines = sections["MEMORY_CURRENT"]
    memory_peak_lines = sections["MEMORY_PEAK"]
    if len(memory_current_lines) != 1 or len(memory_peak_lines) != 1:
        raise HybridKernelResourceEvidenceError(
            "cgroup memory evidence must contain one current and peak value"
        )
    process_rss = None
    if "PROCESS_STATUS" in sections:
        rss = [
            line.split()
            for line in sections["PROCESS_STATUS"]
            if line.startswith("VmRSS:")
        ]
        if len(rss) != 1 or len(rss[0]) != 3 or rss[0][2] != "kB":
            raise HybridKernelResourceEvidenceError(
                "process status lacks one VmRSS value in kB"
            )
        process_rss = _nonnegative_integer(rss[0][1], "VmRSS") * 1024
    return CgroupSnapshot(
        cpu_usage_usec=cpu["usage_usec"],
        cpu_nr_periods=cpu["nr_periods"],
        cpu_nr_throttled=cpu["nr_throttled"],
        cpu_throttled_usec=cpu["throttled_usec"],
        memory_current_bytes=_nonnegative_integer(
            memory_current_lines[0], "memory.current"
        ),
        memory_peak_bytes=_nonnegative_integer(
            memory_peak_lines[0], "memory.peak"
        ),
        memory_events=tuple(sorted(events.items())),
        process_rss_bytes=process_rss,
    )


def cgroup_delta(before: CgroupSnapshot, after: CgroupSnapshot) -> CgroupDelta:
    before_events = dict(before.memory_events)
    after_events = dict(after.memory_events)
    if set(before_events) != set(after_events):
        raise HybridKernelResourceEvidenceError(
            "cgroup memory event fields changed during the gate"
        )

    def delta(first: int, second: int, field: str) -> int:
        if second < first:
            raise HybridKernelResourceEvidenceError(
                f"cgroup {field} counter decreased during the gate"
            )
        return second - first

    return CgroupDelta(
        cpu_usage_usec=delta(
            before.cpu_usage_usec, after.cpu_usage_usec, "usage"
        ),
        cpu_nr_periods=delta(
            before.cpu_nr_periods, after.cpu_nr_periods, "period"
        ),
        cpu_nr_throttled=delta(
            before.cpu_nr_throttled, after.cpu_nr_throttled, "throttled period"
        ),
        cpu_throttled_usec=delta(
            before.cpu_throttled_usec,
            after.cpu_throttled_usec,
            "throttled time",
        ),
        memory_peak_bytes=after.memory_peak_bytes,
        memory_events=tuple(
            sorted(
                (
                    field,
                    delta(before_events[field], after_events[field], field),
                )
                for field in before_events
            )
        ),
    )


def _statefulsets(document: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    items = [
        _mapping(item, "StatefulSet item")
        for item in _list(document.get("items"), "StatefulSet items")
        if isinstance(item, dict) and item.get("kind") == "StatefulSet"
    ]
    discover_existing_replica_state({"items": items})
    result = {}
    for item in items:
        metadata = _mapping(item.get("metadata"), "StatefulSet metadata")
        name = metadata.get("name")
        if not isinstance(name, str) or name in result:
            raise HybridKernelResourceEvidenceError(
                "StatefulSet resource evidence has invalid names"
            )
        result[name] = item
    return result


def _container_resources(
    item: Mapping[str, object], container_name: str
) -> Mapping[str, object]:
    spec = _mapping(item.get("spec"), "StatefulSet spec")
    template = _mapping(spec.get("template"), "StatefulSet template")
    pod_spec = _mapping(template.get("spec"), "StatefulSet Pod spec")
    containers = _list(pod_spec.get("containers"), "StatefulSet containers")
    matches = [
        _mapping(container, "container")
        for container in containers
        if isinstance(container, dict) and container.get("name") == container_name
    ]
    if len(matches) != 1:
        raise HybridKernelResourceEvidenceError(
            f"StatefulSet must contain one {container_name} container"
        )
    return _mapping(matches[0].get("resources"), f"{container_name} resources")


def _expected_resources(
    *, request_cpu: str, request_memory: str, limit_cpu: str, limit_memory: str
) -> Mapping[str, object]:
    return {
        "requests": {"cpu": request_cpu, "memory": request_memory},
        "limits": {"cpu": limit_cpu, "memory": limit_memory},
    }


def validate_resource_profile(
    document: Mapping[str, object], profile: ProcessorMemoryProfile
) -> None:
    for item in _statefulsets(document).values():
        if _container_resources(item, "private-processor") != _expected_resources(
            request_cpu="50m",
            request_memory=profile.request,
            limit_cpu="1",
            limit_memory=profile.limit,
        ):
            raise HybridKernelResourceEvidenceError(
                f"processor resources do not match {profile.name} profile"
            )
        if _container_resources(item, "public-forwarder") != _expected_resources(
            request_cpu="25m",
            request_memory="128Mi",
            limit_cpu="1",
            limit_memory="256Mi",
        ):
            raise HybridKernelResourceEvidenceError(
                "forwarder resources changed outside Phase 7"
            )


def detect_resource_profile(
    document: Mapping[str, object],
) -> ProcessorMemoryProfile:
    matches = []
    for profile in PROCESSOR_MEMORY_PROFILES.values():
        try:
            validate_resource_profile(document, profile)
        except HybridKernelResourceEvidenceError:
            continue
        matches.append(profile)
    if len(matches) != 1:
        raise HybridKernelResourceEvidenceError(
            "StatefulSets do not have one recognized processor resource profile"
        )
    return matches[0]


def validate_processor_only_transition(
    existing: Mapping[str, object],
    proposed: Mapping[str, object],
    target: ProcessorMemoryProfile,
) -> None:
    """Allow only the declared private-processor memory transition."""

    existing_sets = _statefulsets(existing)
    proposed_sets = _statefulsets(proposed)
    if set(existing_sets) != set(proposed_sets):
        raise HybridKernelResourceEvidenceError(
            "Phase 7 resource transition changed StatefulSet ownership"
        )
    existing_count = discover_existing_replica_state(
        {"items": list(existing_sets.values())}
    ).replica_count
    proposed_count = discover_existing_replica_state(
        {"items": list(proposed_sets.values())}
    ).replica_count
    if existing_count != proposed_count:
        raise HybridKernelResourceEvidenceError(
            "Phase 7 resource transition changed the replica count"
        )
    if not any(
        all(
            _container_resources(item, "private-processor")
            == _expected_resources(
                request_cpu="50m",
                request_memory=profile.request,
                limit_cpu="1",
                limit_memory=profile.limit,
            )
            for item in existing_sets.values()
        )
        for profile in PROCESSOR_MEMORY_PROFILES.values()
    ):
        raise HybridKernelResourceEvidenceError(
            "existing processor resources are neither baseline nor candidate"
        )
    validate_resource_profile(proposed, target)
    for name in sorted(existing_sets):
        old = json.loads(json.dumps(existing_sets[name].get("spec")))
        new = json.loads(json.dumps(proposed_sets[name].get("spec")))
        for spec in (old, new):
            containers = spec["template"]["spec"]["containers"]
            processor = next(
                item for item in containers if item.get("name") == "private-processor"
            )
            processor["resources"] = "__PHASE7_PROCESSOR_RESOURCES__"
        if old != new:
            raise HybridKernelResourceEvidenceError(
                f"Phase 7 changed non-processor Pod-template fields in {name}"
            )


def evaluate_processor_candidate(
    *,
    samples: Sequence[ContainerResourceSample],
    processor_deltas: Sequence[CgroupDelta],
    serving_restarts: int,
    fatal_event_count: int,
    post_ready_probe_failure_count: int,
    node_pressure: bool,
    all_ready: bool,
    controller_completed: bool,
    controller_duration_seconds: float,
    controller_deadline_seconds: int,
) -> ProcessorCandidateDecision:
    """Apply the explicit conservative Phase 7 candidate acceptance gates."""

    processor_samples = [
        sample for sample in samples if sample.container_name == "private-processor"
    ]
    if not processor_samples or not processor_deltas:
        raise HybridKernelResourceEvidenceError(
            "candidate decision requires processor runtime and cgroup evidence"
        )
    max_working_set = max(
        sample.memory_working_set_bytes for sample in processor_samples
    )
    max_peak = max(delta.memory_peak_bytes for delta in processor_deltas)
    total_throttled = sum(delta.cpu_throttled_usec for delta in processor_deltas)
    memory_events = {
        field: sum(dict(delta.memory_events).get(field, 0) for delta in processor_deltas)
        for field in {field for delta in processor_deltas for field, _ in delta.memory_events}
    }
    reasons = []
    conservative_ceiling = CANDIDATE_PROCESSOR_MEMORY.limit_bytes // 2
    if max(max_working_set, max_peak) > conservative_ceiling:
        reasons.append("processor memory exceeded 50 percent of the candidate limit")
    for field in ("high", "max", "oom", "oom_kill", "oom_group_kill"):
        if memory_events.get(field, 0):
            reasons.append(f"processor cgroup recorded memory event {field}")
    total_usage = sum(delta.cpu_usage_usec for delta in processor_deltas)
    if total_throttled > max(50_000, total_usage // 10):
        reasons.append("processor CPU throttling exceeded the Phase 7 bound")
    if serving_restarts:
        reasons.append("serving containers restarted during candidate evidence")
    if fatal_event_count:
        reasons.append("Kubernetes reported fatal resource/probe events")
    if post_ready_probe_failure_count:
        reasons.append("readiness or liveness probes failed after Ready coverage")
    if node_pressure:
        reasons.append("the dedicated node reported resource pressure")
    if not all_ready:
        reasons.append("complete Ready coverage was not preserved")
    if not controller_completed:
        reasons.append("controller Job did not complete")
    if (
        controller_duration_seconds < 0
        or controller_duration_seconds >= controller_deadline_seconds / 2
    ):
        reasons.append("controller Job lacks at least 50 percent deadline margin")
    peak = max(max_working_set, max_peak)
    return ProcessorCandidateDecision(
        accepted=not reasons,
        reasons=tuple(reasons),
        max_working_set_bytes=max_working_set,
        max_memory_peak_bytes=max_peak,
        minimum_limit_headroom_bytes=(
            CANDIDATE_PROCESSOR_MEMORY.limit_bytes - peak
        ),
        total_throttled_usec=total_throttled,
    )
