"""Pure direction-aware rollout/count validation for Hybrid Kernel.

The module understands only Hybrid-owned Kubernetes identity, desired replica
counts, deterministic batch targets, and Ready ordinal coverage.  It contains
no placement, policy, learning, traffic, or Kubernetes client implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Integral
from typing import Mapping

from .kernel_infrastructure_contract import (
    DEFAULT_HYBRID_KERNEL_OWNERSHIP,
    HybridKernelOwnership,
)


HYBRID_KERNEL_ROLLOUT_CONTRACT_VERSION = "ibg-hybrid-kernel-rollout-v2"
HYBRID_KERNEL_STAGE_COUNT = 3


class HybridKernelRolloutError(ValueError):
    """Raised when StatefulSet ownership, counts, or readiness are unsafe."""


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise HybridKernelRolloutError(f"{field} must be a mapping")
    return value


def _items(document: Mapping[str, object], field: str) -> tuple[object, ...]:
    items = document.get("items")
    if not isinstance(items, list):
        raise HybridKernelRolloutError(f"{field} must contain an items list")
    return tuple(items)


def _positive_integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 1:
        raise HybridKernelRolloutError(f"{field} must be a positive integer")
    return int(value)


@dataclass(frozen=True, order=True)
class HybridStageReplicaCount:
    stage: int
    name: str
    replicas: int

    def __post_init__(self) -> None:
        _positive_integer(self.stage, "stage")
        if not isinstance(self.name, str) or not self.name:
            raise HybridKernelRolloutError("StatefulSet name must be nonempty")
        _positive_integer(self.replicas, "replicas")


@dataclass(frozen=True)
class HybridExistingReplicaState:
    stages: tuple[HybridStageReplicaCount, ...]
    replica_count: int
    contract_version: str = HYBRID_KERNEL_ROLLOUT_CONTRACT_VERSION

    def __post_init__(self) -> None:
        stages = tuple(self.stages)
        object.__setattr__(self, "stages", stages)
        if self.contract_version != HYBRID_KERNEL_ROLLOUT_CONTRACT_VERSION:
            raise HybridKernelRolloutError("unexpected rollout contract version")
        if tuple(item.stage for item in stages) != (1, 2, 3):
            raise HybridKernelRolloutError(
                "Hybrid rollout requires exact stages 1, 2, and 3"
            )
        count = _positive_integer(self.replica_count, "replica_count")
        if any(item.replicas != count for item in stages):
            raise HybridKernelRolloutError(
                "Hybrid StatefulSets must have one consistent replica count"
            )


@dataclass(frozen=True)
class HybridRolloutBatch:
    target_count: int
    new_ordinals: tuple[int, ...] = ()
    removed_ordinals: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        _positive_integer(self.target_count, "target_count")
        ordinals = tuple(self.new_ordinals)
        object.__setattr__(self, "new_ordinals", ordinals)
        removed = tuple(self.removed_ordinals)
        object.__setattr__(self, "removed_ordinals", removed)
        if any(
            isinstance(value, bool) or not isinstance(value, Integral) or value < 0
            for value in (*ordinals, *removed)
        ):
            raise HybridKernelRolloutError(
                "rollout ordinals must be nonnegative integers"
            )
        if tuple(sorted(set(ordinals))) != ordinals:
            raise HybridKernelRolloutError(
                "new_ordinals must be unique and increasing"
            )
        if tuple(sorted(set(removed))) != removed:
            raise HybridKernelRolloutError(
                "removed_ordinals must be unique and increasing"
            )
        if set(ordinals) & set(removed):
            raise HybridKernelRolloutError(
                "a rollout batch cannot add and remove the same ordinal"
            )


@dataclass(frozen=True)
class HybridRolloutPlan:
    existing_count: int
    requested_count: int
    batch_size: int
    batches: tuple[HybridRolloutBatch, ...]
    contract_version: str = HYBRID_KERNEL_ROLLOUT_CONTRACT_VERSION

    def __post_init__(self) -> None:
        existing = _positive_integer(self.existing_count, "existing_count")
        requested = _positive_integer(self.requested_count, "requested_count")
        _positive_integer(self.batch_size, "batch_size")
        batches = tuple(self.batches)
        object.__setattr__(self, "batches", batches)
        if self.contract_version != HYBRID_KERNEL_ROLLOUT_CONTRACT_VERSION:
            raise HybridKernelRolloutError("unexpected rollout contract version")
        targets = tuple(batch.target_count for batch in batches)
        if requested == existing and targets:
            raise HybridKernelRolloutError("equal-count rollout must be a no-op")
        if requested > existing:
            if not targets or targets[-1] != requested:
                raise HybridKernelRolloutError(
                    "rollout batches must finish at the requested count"
                )
            if any(left >= right for left, right in zip(targets, targets[1:])):
                raise HybridKernelRolloutError(
                    "rollout batch targets must increase strictly"
                )
            previous = existing
            for batch in batches:
                if batch.removed_ordinals:
                    raise HybridKernelRolloutError(
                        "scale-up batches cannot remove ordinals"
                    )
                if batch.new_ordinals != tuple(
                    range(previous, batch.target_count)
                ):
                    raise HybridKernelRolloutError(
                        "scale-up batches must add only missing ordinals"
                    )
                previous = batch.target_count
        if requested < existing:
            if len(batches) != 1 or targets != (requested,):
                raise HybridKernelRolloutError(
                    "scale-down must contain one deliberate final target"
                )
            batch = batches[0]
            if batch.new_ordinals:
                raise HybridKernelRolloutError(
                    "scale-down cannot add ordinals"
                )
            if batch.removed_ordinals != tuple(range(requested, existing)):
                raise HybridKernelRolloutError(
                    "scale-down must remove only ordinals above the target"
                )

    @property
    def direction(self) -> str:
        if self.requested_count > self.existing_count:
            return "up"
        if self.requested_count < self.existing_count:
            return "down"
        return "unchanged"

    @property
    def added_ordinals(self) -> tuple[int, ...]:
        return tuple(
            ordinal for batch in self.batches for ordinal in batch.new_ordinals
        )

    @property
    def removed_ordinals(self) -> tuple[int, ...]:
        return tuple(
            ordinal
            for batch in self.batches
            for ordinal in batch.removed_ordinals
        )


def discover_existing_replica_state(
    document: Mapping[str, object],
    *,
    ownership: HybridKernelOwnership = DEFAULT_HYBRID_KERNEL_OWNERSHIP,
) -> HybridExistingReplicaState:
    """Validate exact Hybrid StatefulSet ownership and consistent counts."""

    expected_names = {
        ownership.stage_name(stage): stage
        for stage in range(1, HYBRID_KERNEL_STAGE_COUNT + 1)
    }
    discovered: dict[int, HybridStageReplicaCount] = {}
    for raw_item in _items(document, "StatefulSet inventory"):
        item = _mapping(raw_item, "StatefulSet item")
        if item.get("kind") != "StatefulSet":
            raise HybridKernelRolloutError(
                "StatefulSet inventory contains a foreign resource kind"
            )
        metadata = _mapping(item.get("metadata"), "StatefulSet metadata")
        name = metadata.get("name")
        if name not in expected_names:
            raise HybridKernelRolloutError(
                f"foreign or unexpected StatefulSet ownership: {name!r}"
            )
        stage = expected_names[str(name)]
        if stage in discovered:
            raise HybridKernelRolloutError(
                f"duplicate Hybrid StatefulSet stage {stage}"
            )
        if metadata.get("namespace") != ownership.namespace:
            raise HybridKernelRolloutError(
                f"Hybrid StatefulSet {name} has the wrong namespace"
            )
        labels = _mapping(metadata.get("labels"), "StatefulSet labels")
        required_labels = dict(ownership.replica_labels(stage))
        if any(labels.get(key) != value for key, value in required_labels.items()):
            raise HybridKernelRolloutError(
                f"Hybrid StatefulSet {name} has invalid ownership labels"
            )
        spec = _mapping(item.get("spec"), "StatefulSet spec")
        if spec.get("serviceName") != name:
            raise HybridKernelRolloutError(
                f"Hybrid StatefulSet {name} has an identity-mismatched service"
            )
        selector = _mapping(spec.get("selector"), "StatefulSet selector")
        match_labels = _mapping(
            selector.get("matchLabels"), "StatefulSet selector labels"
        )
        if dict(match_labels) != dict(ownership.replica_selector(stage)):
            raise HybridKernelRolloutError(
                f"Hybrid StatefulSet {name} has an invalid selector"
            )
        template = _mapping(spec.get("template"), "StatefulSet Pod template")
        template_metadata = _mapping(
            template.get("metadata"), "StatefulSet Pod-template metadata"
        )
        template_labels = _mapping(
            template_metadata.get("labels"), "StatefulSet Pod-template labels"
        )
        if any(
            template_labels.get(key) != value
            for key, value in required_labels.items()
        ):
            raise HybridKernelRolloutError(
                f"Hybrid StatefulSet {name} has invalid Pod-template labels"
            )
        replicas = _positive_integer(
            spec.get("replicas"), f"Hybrid StatefulSet {name} replicas"
        )
        discovered[stage] = HybridStageReplicaCount(stage, str(name), replicas)

    missing = sorted(
        set(range(1, HYBRID_KERNEL_STAGE_COUNT + 1)) - set(discovered)
    )
    if missing:
        raise HybridKernelRolloutError(
            f"missing Hybrid StatefulSet stages: {missing}"
        )
    stages = tuple(discovered[stage] for stage in sorted(discovered))
    counts = {item.replicas for item in stages}
    if len(counts) != 1:
        raise HybridKernelRolloutError(
            "Hybrid StatefulSets have inconsistent replica counts"
        )
    return HybridExistingReplicaState(stages, counts.pop())


def plan_bounded_rollout(
    *,
    existing_count: int,
    requested_count: int,
    batch_size: int,
) -> HybridRolloutPlan:
    """Return deterministic bounded additions or one explicit lower target."""

    existing = _positive_integer(existing_count, "existing_count")
    requested = _positive_integer(requested_count, "requested_count")
    bounded = _positive_integer(batch_size, "batch_size")
    batches = []
    if requested < existing:
        batches.append(
            HybridRolloutBatch(
                target_count=requested,
                removed_ordinals=tuple(range(requested, existing)),
            )
        )
    current = existing
    while current < requested:
        target = min(current + bounded, requested)
        batches.append(
            HybridRolloutBatch(
                target_count=target,
                new_ordinals=tuple(range(current, target)),
            )
        )
        current = target
    return HybridRolloutPlan(
        existing_count=existing,
        requested_count=requested,
        batch_size=bounded,
        batches=tuple(batches),
    )


def validate_ready_ordinal_coverage(
    document: Mapping[str, object],
    *,
    replica_count: int,
    ownership: HybridKernelOwnership = DEFAULT_HYBRID_KERNEL_OWNERSHIP,
) -> None:
    """Require exact Running/Ready ordinal coverage at one rollout target."""

    count = _positive_integer(replica_count, "replica_count")
    expected = {
        ownership.stage_name(stage) + f"-{ordinal}"
        for stage in range(1, HYBRID_KERNEL_STAGE_COUNT + 1)
        for ordinal in range(count)
    }
    actual: set[str] = set()
    for raw_item in _items(document, "Pod inventory"):
        item = _mapping(raw_item, "Pod item")
        metadata = _mapping(item.get("metadata"), "Pod metadata")
        name = metadata.get("name")
        if not isinstance(name, str) or not name.startswith("hybrid-stage-"):
            continue
        if name in actual:
            raise HybridKernelRolloutError(f"duplicate Hybrid Pod {name}")
        actual.add(name)
        if name not in expected:
            raise HybridKernelRolloutError(
                f"unexpected Hybrid Pod ordinal identity: {name}"
            )
        stage_text = name.removeprefix("hybrid-stage-").split("-", 1)[0]
        try:
            stage_value = int(stage_text)
        except ValueError as error:
            raise HybridKernelRolloutError(
                f"Hybrid Pod {name} has an invalid stage identity"
            ) from error
        stage = _positive_integer(stage_value, "Pod stage")
        if metadata.get("namespace") != ownership.namespace:
            raise HybridKernelRolloutError(f"Hybrid Pod {name} has wrong namespace")
        labels = _mapping(metadata.get("labels"), "Pod labels")
        required = dict(ownership.replica_labels(stage))
        if any(labels.get(key) != value for key, value in required.items()):
            raise HybridKernelRolloutError(
                f"Hybrid Pod {name} has invalid ownership labels"
            )
        status = _mapping(item.get("status"), "Pod status")
        conditions = status.get("conditions")
        ready = isinstance(conditions, list) and any(
            isinstance(condition, Mapping)
            and condition.get("type") == "Ready"
            and condition.get("status") == "True"
            for condition in conditions
        )
        if status.get("phase") != "Running" or not ready:
            raise HybridKernelRolloutError(f"Hybrid Pod {name} is not Running/Ready")
    if actual != expected:
        raise HybridKernelRolloutError(
            "Hybrid Ready ordinal coverage mismatch: "
            f"missing={sorted(expected - actual)}, "
            f"unexpected={sorted(actual - expected)}"
        )
