"""Greedy-owned public Kernel discovery, controller, and lifecycle contracts."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from numbers import Integral
from typing import TYPE_CHECKING, Mapping

from .contracts import GreedyConfiguration, PublicReplicaState, ReplicaIdentity

if TYPE_CHECKING:
    from .runtime_resources import GreedyControllerResourceDelta
from .slot_contracts import GreedyExperimentResult, GreedySlotResult


GREEDY_KERNEL_CONTRACT_VERSION = "greedy-kernel-controller-v1"
GREEDY_KERNEL_DISCOVERY_VERSION = "greedy-kubernetes-ready-discovery-v2"
GREEDY_KERNEL_LIFECYCLE_VERSION = "greedy-persistent-http-lifecycle-v1"
GREEDY_KERNEL_PRIVATE_PROCESSOR_PORT = 8081
GREEDY_KERNEL_PUBLIC_FORWARDER_PORT = 8080
GREEDY_KERNEL_DISCOVERY_TIMEOUT_SECONDS = 10.0
GREEDY_KERNEL_FLOW_GENERATOR_TIMEOUT_SECONDS = 30.0
GREEDY_KERNEL_ROUTE_TIMEOUT_SECONDS = 10.0
GREEDY_KERNEL_DOWNSTREAM_KEEPALIVE_SECONDS = 30.0


class GreedyKernelContractError(RuntimeError):
    """Raised when a public Kernel identity or correlation contract is invalid."""


def _integer(name: str, value: int, *, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise TypeError(f"{name} must be an integer")
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return int(value)


def _duration(name: str, value: float) -> float:
    result = float(value)
    if not isfinite(result) or result < 0:
        raise ValueError(f"{name} must be finite and nonnegative")
    return result


@dataclass(frozen=True)
class GreedyKernelOwnership:
    """Names used only by the future isolated Greedy runtime."""

    namespace: str = "greedy-testbed"
    part_of_label: str = "greedy-testbed"
    replica_name_label: str = "greedy-replica"
    stage_label_key: str = "greedy.stage"

    def __post_init__(self) -> None:
        for name in (
            "namespace",
            "part_of_label",
            "replica_name_label",
            "stage_label_key",
        ):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise ValueError(f"{name} must be a nonempty string")

    def stage_name(self, stage: int) -> str:
        return f"greedy-stage-{_integer('stage', stage)}"

    def replica_labels(self, stage: int) -> tuple[tuple[str, str], ...]:
        return tuple(
            sorted(
                {
                    "app.kubernetes.io/name": self.replica_name_label,
                    "app.kubernetes.io/part-of": self.part_of_label,
                    "app.kubernetes.io/component": "replica-stage",
                    self.stage_label_key: str(_integer("stage", stage)),
                }.items()
            )
        )


DEFAULT_GREEDY_KERNEL_OWNERSHIP = GreedyKernelOwnership()


@dataclass(frozen=True, order=True)
class GreedyKernelDiscoveredReplica:
    """Public runtime metadata; hidden state and seeds have no representation."""

    identity: ReplicaIdentity
    namespace: str
    pod_name: str
    pod_uid: str
    node_name: str
    endpoint: str
    phase: str
    ready: bool
    labels: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.identity, ReplicaIdentity):
            raise TypeError("identity must be ReplicaIdentity")
        for name in (
            "namespace",
            "pod_name",
            "pod_uid",
            "node_name",
            "endpoint",
            "phase",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise GreedyKernelContractError(f"{name} must be a nonempty string")
        if not self.endpoint.startswith(("http://", "https://")):
            raise GreedyKernelContractError("replica endpoint must be HTTP(S)")
        if not isinstance(self.ready, bool):
            raise TypeError("ready must be a boolean")
        labels = tuple((str(key), str(value)) for key, value in self.labels)
        object.__setattr__(self, "labels", labels)
        if labels != tuple(sorted(set(labels))):
            raise GreedyKernelContractError("replica labels must be unique and canonical")


@dataclass(frozen=True)
class GreedyKernelDiscoverySnapshot:
    configuration: GreedyConfiguration
    replicas: tuple[GreedyKernelDiscoveredReplica, ...]
    ownership: GreedyKernelOwnership = DEFAULT_GREEDY_KERNEL_OWNERSHIP
    contract_version: str = GREEDY_KERNEL_DISCOVERY_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.configuration, GreedyConfiguration):
            raise TypeError("configuration must be GreedyConfiguration")
        if self.contract_version != GREEDY_KERNEL_DISCOVERY_VERSION:
            raise GreedyKernelContractError("unexpected discovery contract version")
        replicas = tuple(self.replicas)
        object.__setattr__(self, "replicas", replicas)
        if not all(type(replica) is GreedyKernelDiscoveredReplica for replica in replicas):
            raise TypeError("replicas must contain discovered Greedy replicas")
        expected = tuple(
            ReplicaIdentity(stage, replica)
            for stage in self.configuration.stages
            for replica in self.configuration.replica_ids
        )
        identities = tuple(replica.identity for replica in replicas)
        if len(set(identities)) != len(identities):
            raise GreedyKernelContractError("discovery contains a duplicate replica identity")
        if identities != expected:
            raise GreedyKernelContractError(
                "discovery identity coverage mismatch or noncanonical ordering"
            )
        for replica in replicas:
            replica.identity.validate_for(self.configuration)
            if replica.namespace != self.ownership.namespace:
                raise GreedyKernelContractError("discovery contains a foreign namespace")
            expected_name = (
                f"{self.ownership.stage_name(replica.identity.stage)}-"
                f"{replica.identity.replica - 1}"
            )
            if replica.pod_name != expected_name:
                raise GreedyKernelContractError("discovery Pod identity mismatch")
            if replica.phase != "Running" or not replica.ready:
                raise GreedyKernelContractError("replica is not Running and Ready")
            labels = dict(replica.labels)
            required = dict(self.ownership.replica_labels(replica.identity.stage))
            if any(labels.get(key) != value for key, value in required.items()):
                raise GreedyKernelContractError("discovery ownership labels are malformed")

    def replica_by_identity(self) -> Mapping[ReplicaIdentity, GreedyKernelDiscoveredReplica]:
        return {replica.identity: replica for replica in self.replicas}


@dataclass(frozen=True)
class GreedyKernelControllerConfiguration:
    """Finite one-experiment inputs with no hidden runtime state."""

    configuration: GreedyConfiguration
    experiment_id: int
    root_seed: int
    profile_seed: int
    runtime_profile_fingerprint: str
    max_iterations: int
    first_slot_id: int = 1
    parity_replay_enabled: bool = False
    control_plane_footprint_enabled: bool = False
    contract_version: str = GREEDY_KERNEL_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.configuration, GreedyConfiguration):
            raise TypeError("configuration must be GreedyConfiguration")
        for name, minimum in (
            ("experiment_id", 1),
            ("root_seed", 0),
            ("profile_seed", 0),
            ("max_iterations", 1),
            ("first_slot_id", 1),
        ):
            object.__setattr__(
                self,
                name,
                _integer(name, getattr(self, name), minimum=minimum),
            )
        if (
            not isinstance(self.runtime_profile_fingerprint, str)
            or not self.runtime_profile_fingerprint
        ):
            raise ValueError("runtime_profile_fingerprint must be a nonempty string")
        for name in ("parity_replay_enabled", "control_plane_footprint_enabled"):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be boolean")
        if self.contract_version != GREEDY_KERNEL_CONTRACT_VERSION:
            raise ValueError("unexpected Greedy Kernel controller contract version")


@dataclass(frozen=True)
class GreedyKernelPhaseTimings:
    discovery_seconds: float
    admission_placement_seconds: float
    route_dispatch_seconds: float
    data_plane_wait_seconds: float
    feedback_validation_seconds: float
    total_slot_seconds: float

    def __post_init__(self) -> None:
        names = (
            "discovery_seconds",
            "admission_placement_seconds",
            "route_dispatch_seconds",
            "data_plane_wait_seconds",
            "feedback_validation_seconds",
            "total_slot_seconds",
        )
        for name in names:
            object.__setattr__(self, name, _duration(name, getattr(self, name)))
        components = sum(getattr(self, name) for name in names[:-1])
        if abs(self.total_slot_seconds - components) > 1e-9:
            raise ValueError("total slot timing must equal all five phase durations")


@dataclass(frozen=True)
class GreedyClientLifecycle:
    owner: str
    scope: str
    client_instances: int
    close_calls: int
    closed: bool
    contract_version: str = GREEDY_KERNEL_LIFECYCLE_VERSION

    def __post_init__(self) -> None:
        if not self.owner or not self.scope:
            raise ValueError("lifecycle owner and scope must be nonempty")
        object.__setattr__(
            self,
            "client_instances",
            _integer("client_instances", self.client_instances, minimum=0),
        )
        object.__setattr__(
            self,
            "close_calls",
            _integer("close_calls", self.close_calls, minimum=0),
        )
        if not isinstance(self.closed, bool):
            raise TypeError("closed must be a boolean")
        if self.close_calls > self.client_instances:
            raise ValueError("a client cannot be closed more than once")
        expected_closed = (
            self.client_instances > 0
            and self.close_calls == self.client_instances
        )
        if self.closed != expected_closed:
            raise ValueError("closed state must match exactly-once client cleanup")
        if self.contract_version != GREEDY_KERNEL_LIFECYCLE_VERSION:
            raise ValueError("unexpected lifecycle contract version")


@dataclass(frozen=True)
class GreedyKernelControllerSlotResult:
    discovery: GreedyKernelDiscoverySnapshot
    public_replicas: tuple[PublicReplicaState, ...]
    slot: GreedySlotResult
    phase_timings: GreedyKernelPhaseTimings
    controller_to_generator_requests: int
    selected_route_requests: int
    control_plane: Mapping[str, object] | None = None
    controller_resources: GreedyControllerResourceDelta | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "public_replicas", tuple(self.public_replicas))
        if not all(type(state) is PublicReplicaState for state in self.public_replicas):
            raise TypeError("public_replicas must contain PublicReplicaState values")
        if tuple(state.identity for state in self.public_replicas) != tuple(
            replica.identity for replica in self.discovery.replicas
        ):
            raise ValueError("public replicas must retain discovery identity order")
        if self.discovery.configuration != self.slot.configuration:
            raise ValueError("discovery and slot configuration must match")
        if self.controller_to_generator_requests != 1:
            raise ValueError("a complete Kernel slot requires one generator request")
        if self.selected_route_requests != self.slot.configuration.num_flows:
            raise ValueError("a complete Kernel slot requires one route request per flow")
        if self.control_plane is not None:
            from .control_plane_footprint import (
                validate_greedy_control_plane_snapshot,
            )

            validate_greedy_control_plane_snapshot(self.control_plane)
        if self.controller_resources is not None:
            from .runtime_resources import GreedyControllerResourceDelta

            if not isinstance(self.controller_resources, GreedyControllerResourceDelta):
                raise TypeError(
                    "controller_resources must use GreedyControllerResourceDelta"
                )


@dataclass(frozen=True)
class GreedyKernelControllerExperimentResult:
    controller_configuration: GreedyKernelControllerConfiguration
    pure_experiment: GreedyExperimentResult
    slots: tuple[GreedyKernelControllerSlotResult, ...]

    def __post_init__(self) -> None:
        slots = tuple(self.slots)
        object.__setattr__(self, "slots", slots)
        if tuple(item.slot for item in slots) != self.pure_experiment.slots:
            raise ValueError("Kernel and pure experiment slot sequences must agree")
        if self.pure_experiment.experiment_id != self.controller_configuration.experiment_id:
            raise ValueError("Kernel experiment identity mismatch")
