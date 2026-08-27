"""Pure Greedy topology discovery, bounded planning, and Ready validation."""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Integral
import re
from typing import Mapping

from .contracts import GreedyConfiguration, ReplicaIdentity
from .kernel_contracts import DEFAULT_GREEDY_KERNEL_OWNERSHIP, GreedyKernelOwnership


GREEDY_KERNEL_ROLLOUT_VERSION = "greedy-kernel-rollout-v2"


class GreedyKernelRolloutError(ValueError):
    """A discovered or requested topology cannot be reconciled safely."""


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise GreedyKernelRolloutError(f"{field} must be a mapping")
    return value


def _items(document: Mapping[str, object], field: str) -> tuple[object, ...]:
    items = document.get("items")
    if not isinstance(items, list):
        raise GreedyKernelRolloutError(f"{field} must contain an items list")
    return tuple(items)


def _positive_integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 1:
        raise GreedyKernelRolloutError(f"{field} must be a positive integer")
    return int(value)


@dataclass(frozen=True, order=True)
class GreedyStageReplicaCount:
    stage: int
    name: str
    replicas: int

    def __post_init__(self) -> None:
        _positive_integer(self.stage, "stage")
        if not isinstance(self.name, str) or not self.name:
            raise GreedyKernelRolloutError("StatefulSet name must be nonempty")
        _positive_integer(self.replicas, "replicas")


@dataclass(frozen=True)
class GreedyExistingTopology:
    stages: tuple[GreedyStageReplicaCount, ...]
    contract_version: str = GREEDY_KERNEL_ROLLOUT_VERSION

    def __post_init__(self) -> None:
        stages = tuple(self.stages)
        object.__setattr__(self, "stages", stages)
        if self.contract_version != GREEDY_KERNEL_ROLLOUT_VERSION:
            raise GreedyKernelRolloutError("unexpected Greedy rollout version")
        if len(stages) < 2:
            raise GreedyKernelRolloutError(
                "Greedy topology must contain at least two stages"
            )
        stage_ids = tuple(item.stage for item in stages)
        if stage_ids != tuple(range(1, len(stages) + 1)):
            raise GreedyKernelRolloutError(
                "Greedy StatefulSet stages must be contiguous from one"
            )

    @property
    def num_stages(self) -> int:
        return len(self.stages)

    @property
    def replica_counts(self) -> tuple[int, ...]:
        return tuple(item.replicas for item in self.stages)

    @property
    def uniform_replica_count(self) -> int:
        counts = set(self.replica_counts)
        if len(counts) != 1:
            raise GreedyKernelRolloutError(
                "Greedy StatefulSets have inconsistent replica counts"
            )
        return next(iter(counts))


def discover_existing_topology(
    document: Mapping[str, object],
    *,
    ownership: GreedyKernelOwnership = DEFAULT_GREEDY_KERNEL_OWNERSHIP,
) -> GreedyExistingTopology:
    """Validate all supplied StatefulSets as a contiguous Greedy-owned prefix."""

    discovered: dict[int, GreedyStageReplicaCount] = {}
    for raw_item in _items(document, "StatefulSet inventory"):
        item = _mapping(raw_item, "StatefulSet item")
        if item.get("kind") != "StatefulSet":
            raise GreedyKernelRolloutError(
                "StatefulSet inventory contains a foreign resource kind"
            )
        metadata = _mapping(item.get("metadata"), "StatefulSet metadata")
        name = metadata.get("name")
        if not isinstance(name, str):
            raise GreedyKernelRolloutError("StatefulSet name is malformed")
        match = re.fullmatch(r"greedy-stage-(\d+)", name)
        if match is None:
            raise GreedyKernelRolloutError(
                f"foreign or unexpected StatefulSet ownership: {name!r}"
            )
        stage = _positive_integer(int(match.group(1)), "StatefulSet stage")
        if stage in discovered:
            raise GreedyKernelRolloutError(
                f"duplicate Greedy StatefulSet stage {stage}"
            )
        if name != ownership.stage_name(stage):
            raise GreedyKernelRolloutError("StatefulSet stage identity mismatch")
        if metadata.get("namespace") != ownership.namespace:
            raise GreedyKernelRolloutError(
                f"Greedy StatefulSet {name} has the wrong namespace"
            )
        labels = _mapping(metadata.get("labels"), "StatefulSet labels")
        required = {
            "app.kubernetes.io/name": ownership.replica_name_label,
            "app.kubernetes.io/part-of": ownership.part_of_label,
            "app.kubernetes.io/component": "replica-stage",
            ownership.stage_label_key: str(stage),
        }
        if any(labels.get(key) != value for key, value in required.items()):
            raise GreedyKernelRolloutError(
                f"Greedy StatefulSet {name} has invalid ownership labels"
            )
        spec = _mapping(item.get("spec"), "StatefulSet spec")
        if spec.get("serviceName") != name:
            raise GreedyKernelRolloutError(
                f"Greedy StatefulSet {name} has an identity-mismatched service"
            )
        selector = _mapping(spec.get("selector"), "StatefulSet selector")
        match_labels = _mapping(
            selector.get("matchLabels"), "StatefulSet selector labels"
        )
        expected_selector = {
            "app.kubernetes.io/name": ownership.replica_name_label,
            ownership.stage_label_key: str(stage),
        }
        if dict(match_labels) != expected_selector:
            raise GreedyKernelRolloutError(
                f"Greedy StatefulSet {name} has an invalid selector"
            )
        template = _mapping(spec.get("template"), "StatefulSet Pod template")
        template_metadata = _mapping(
            template.get("metadata"), "StatefulSet Pod-template metadata"
        )
        template_labels = _mapping(
            template_metadata.get("labels"), "StatefulSet Pod-template labels"
        )
        if any(
            template_labels.get(key) != value for key, value in required.items()
        ):
            raise GreedyKernelRolloutError(
                f"Greedy StatefulSet {name} has invalid Pod-template ownership"
            )
        replicas = _positive_integer(
            spec.get("replicas"), f"Greedy StatefulSet {name} replicas"
        )
        discovered[stage] = GreedyStageReplicaCount(stage, name, replicas)

    if not discovered:
        raise GreedyKernelRolloutError("Greedy StatefulSet inventory is empty")
    stages = tuple(discovered[stage] for stage in sorted(discovered))
    return GreedyExistingTopology(stages)


@dataclass(frozen=True)
class GreedyReplicaBatch:
    target_count: int
    new_ordinals: tuple[int, ...] = ()
    removed_ordinals: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        _positive_integer(self.target_count, "target_count")
        new = tuple(self.new_ordinals)
        removed = tuple(self.removed_ordinals)
        object.__setattr__(self, "new_ordinals", new)
        object.__setattr__(self, "removed_ordinals", removed)
        for name, values in (("new_ordinals", new), ("removed_ordinals", removed)):
            if values != tuple(sorted(set(values))) or any(
                isinstance(value, bool) or not isinstance(value, Integral) or value < 0
                for value in values
            ):
                raise GreedyKernelRolloutError(
                    f"{name} must contain unique increasing nonnegative ordinals"
                )
        if set(new) & set(removed):
            raise GreedyKernelRolloutError(
                "a replica batch cannot add and remove the same ordinal"
            )


def plan_replica_batches(
    *, existing_count: int, requested_count: int, batch_size: int
) -> tuple[GreedyReplicaBatch, ...]:
    existing = _positive_integer(existing_count, "existing_count")
    requested = _positive_integer(requested_count, "requested_count")
    bounded = _positive_integer(batch_size, "batch_size")
    if requested < existing:
        return (
            GreedyReplicaBatch(
                target_count=requested,
                removed_ordinals=tuple(range(requested, existing)),
            ),
        )
    batches = []
    current = existing
    while current < requested:
        target = min(current + bounded, requested)
        batches.append(
            GreedyReplicaBatch(
                target_count=target,
                new_ordinals=tuple(range(current, target)),
            )
        )
        current = target
    return tuple(batches)


@dataclass(frozen=True)
class GreedyTopologyPlan:
    current_stages: int
    current_replicas: int
    target: GreedyConfiguration
    removed_stages: tuple[int, ...]
    replica_batches: tuple[GreedyReplicaBatch, ...]
    added_stages: tuple[int, ...]
    contract_version: str = GREEDY_KERNEL_ROLLOUT_VERSION

    def __post_init__(self) -> None:
        _positive_integer(self.current_stages, "current_stages")
        _positive_integer(self.current_replicas, "current_replicas")
        if self.current_stages < 2 or self.target.num_stages < 2:
            raise GreedyKernelRolloutError("Greedy cannot contract below two stages")
        if self.contract_version != GREEDY_KERNEL_ROLLOUT_VERSION:
            raise GreedyKernelRolloutError("unexpected Greedy topology plan version")
        expected_removed = tuple(
            range(self.current_stages, self.target.num_stages, -1)
        )
        expected_added = tuple(
            range(self.current_stages + 1, self.target.num_stages + 1)
        )
        if self.removed_stages != expected_removed:
            raise GreedyKernelRolloutError("stage removal must use the highest suffix")
        if self.added_stages != expected_added:
            raise GreedyKernelRolloutError("stage addition must use the highest suffix")

    @property
    def is_serving_noop(self) -> bool:
        return not (self.removed_stages or self.replica_batches or self.added_stages)


def plan_topology_reconciliation(
    current: GreedyExistingTopology,
    target: GreedyConfiguration,
    *,
    rollout_batch_size: int,
) -> GreedyTopologyPlan:
    if not isinstance(current, GreedyExistingTopology):
        raise TypeError("current must be GreedyExistingTopology")
    if not isinstance(target, GreedyConfiguration):
        raise TypeError("target must be GreedyConfiguration")
    existing_replicas = current.uniform_replica_count
    return GreedyTopologyPlan(
        current_stages=current.num_stages,
        current_replicas=existing_replicas,
        target=target,
        removed_stages=tuple(
            range(current.num_stages, target.num_stages, -1)
        ),
        replica_batches=plan_replica_batches(
            existing_count=existing_replicas,
            requested_count=target.num_replicas,
            batch_size=rollout_batch_size,
        ),
        added_stages=tuple(
            range(current.num_stages + 1, target.num_stages + 1)
        ),
    )


def validate_interrupted_transition_shape(
    current: GreedyExistingTopology,
    *,
    stable: GreedyConfiguration,
    target: GreedyConfiguration,
) -> None:
    """Allow only an explicitly marked prefix/count state between endpoints."""

    if not isinstance(current, GreedyExistingTopology):
        raise TypeError("current must be GreedyExistingTopology")
    stage_low = min(stable.num_stages, target.num_stages)
    stage_high = max(stable.num_stages, target.num_stages)
    if not stage_low <= current.num_stages <= stage_high:
        raise GreedyKernelRolloutError(
            "interrupted topology stage count is outside the marked transition"
        )
    replica_low = min(stable.num_replicas, target.num_replicas)
    replica_high = max(stable.num_replicas, target.num_replicas)
    if any(
        count < replica_low or count > replica_high
        for count in current.replica_counts
    ):
        raise GreedyKernelRolloutError(
            "interrupted topology replica counts are outside the marked transition"
        )
    # Inconsistent counts are accepted only here.  Reconciliation immediately
    # drives every retained stage to the requested target before a Ready token.


def _is_ready(item: Mapping[str, object]) -> bool:
    status = item.get("status")
    if not isinstance(status, Mapping) or status.get("phase") != "Running":
        return False
    conditions = status.get("conditions")
    return isinstance(conditions, list) and any(
        isinstance(condition, Mapping)
        and condition.get("type") == "Ready"
        and condition.get("status") == "True"
        for condition in conditions
    )


def validate_ready_coverage(
    document: Mapping[str, object],
    *,
    configuration: GreedyConfiguration,
    ownership: GreedyKernelOwnership = DEFAULT_GREEDY_KERNEL_OWNERSHIP,
    require_flow_generator: bool = True,
) -> None:
    """Require exact Running/Ready replica ordinals and one Ready generator."""

    if not isinstance(configuration, GreedyConfiguration):
        raise TypeError("configuration must be GreedyConfiguration")
    expected = {
        ownership.stage_name(stage) + f"-{ordinal}"
        for stage in configuration.stages
        for ordinal in range(configuration.num_replicas)
    }
    actual: set[str] = set()
    flow_generators = []
    for raw_item in _items(document, "Pod inventory"):
        item = _mapping(raw_item, "Pod item")
        metadata = _mapping(item.get("metadata"), "Pod metadata")
        name = metadata.get("name")
        labels = _mapping(metadata.get("labels"), "Pod labels")
        if not isinstance(name, str):
            raise GreedyKernelRolloutError("Pod name is malformed")
        if name.startswith("greedy-stage-"):
            if name in actual:
                raise GreedyKernelRolloutError(f"duplicate Greedy Pod {name}")
            actual.add(name)
            if name not in expected:
                raise GreedyKernelRolloutError(
                    f"unexpected Greedy Pod ordinal identity: {name}"
                )
            match = re.fullmatch(r"greedy-stage-(\d+)-(\d+)", name)
            if match is None:
                raise GreedyKernelRolloutError(
                    f"Greedy Pod {name} has an invalid identity"
                )
            identity = ReplicaIdentity(int(match.group(1)), int(match.group(2)) + 1)
            required = dict(ownership.replica_labels(identity.stage))
            if (
                metadata.get("namespace") != ownership.namespace
                or any(labels.get(key) != value for key, value in required.items())
                or not _is_ready(item)
            ):
                raise GreedyKernelRolloutError(
                    f"Greedy Pod {name} is not owned, Running, and Ready"
                )
        elif name.startswith("greedy-flow-generator-"):
            flow_generators.append(item)
    if actual != expected:
        raise GreedyKernelRolloutError(
            "Greedy Ready ordinal coverage mismatch: "
            f"missing={sorted(expected - actual)}, "
            f"unexpected={sorted(actual - expected)}"
        )
    if require_flow_generator:
        if len(flow_generators) != 1:
            raise GreedyKernelRolloutError(
                "Greedy readiness requires exactly one flow generator"
            )
        flow = flow_generators[0]
        metadata = _mapping(flow.get("metadata"), "flow-generator metadata")
        labels = _mapping(metadata.get("labels"), "flow-generator labels")
        if (
            metadata.get("namespace") != ownership.namespace
            or labels.get("app.kubernetes.io/name") != "greedy-flow-generator"
            or labels.get("app.kubernetes.io/part-of") != ownership.part_of_label
            or not _is_ready(flow)
        ):
            raise GreedyKernelRolloutError(
                "Greedy flow generator is not owned, Running, and Ready"
            )
