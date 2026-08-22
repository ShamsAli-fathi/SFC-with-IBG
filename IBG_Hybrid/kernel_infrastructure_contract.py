"""Versioned ownership contract for Hybrid Kernel Infrastructure Phase 0.

This module is intentionally declarative and import-safe.  It defines who
will own a future Hybrid Kubernetes runtime and which Exact runtime concepts
may be reused.  It does not create Kubernetes resources, discover live Pods,
execute routes, or change Hybrid policy behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from numbers import Integral
from typing import Iterable

from .contracts import HybridConfiguration, ReplicaChoice


HYBRID_KERNEL_INFRASTRUCTURE_CONTRACT_VERSION = (
    "ibg-hybrid-kernel-infrastructure-phase0-v1"
)
HYBRID_KERNEL_RUNTIME_PROFILE_CONTRACT_VERSION = (
    "ibg-hybrid-kernel-runtime-profile-v1"
)
HYBRID_KERNEL_DISCOVERY_CONTRACT_VERSION = "ibg-hybrid-ready-discovery-v1"
HYBRID_KERNEL_CONTROLLER_LIFECYCLE_VERSION = (
    "ibg-hybrid-kernel-controller-lifecycle-v1"
)
HYBRID_KERNEL_LOOKAHEAD_POOL_LIFECYCLE_VERSION = (
    "ibg-hybrid-controller-lookahead-pool-v1"
)
HYBRID_KERNEL_LOOKAHEAD_WORKERS = 4
HYBRID_KERNEL_IMAGE_OWNERSHIP_VERSION = "ibg-hybrid-kernel-image-ownership-v1"

HYBRID_KERNEL_NAMESPACE = "ibg-hybrid-testbed"
HYBRID_KERNEL_PART_OF_LABEL = "ibg-hybrid-testbed"
HYBRID_KERNEL_REPLICA_NAME_LABEL = "ibg-hybrid-replica"
HYBRID_KERNEL_STAGE_LABEL = "ibg-hybrid.stage"

_FORBIDDEN_SHARED_NAMESPACES = frozenset(("ibg-testbed", "milp-testbed"))


class HybridKernelContractError(ValueError):
    """Raised when a future Hybrid Kernel boundary violates Phase 0."""


def _require_nonempty(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HybridKernelContractError(f"{field} must be a nonempty string")
    return value


def _require_positive_integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 1:
        raise HybridKernelContractError(f"{field} must be a positive integer")
    return int(value)


@dataclass(frozen=True)
class HybridKernelOwnership:
    """Hybrid-owned names that must never alias Exact or MILP ownership."""

    namespace: str = HYBRID_KERNEL_NAMESPACE
    part_of_label: str = HYBRID_KERNEL_PART_OF_LABEL
    replica_name_label: str = HYBRID_KERNEL_REPLICA_NAME_LABEL
    stage_label_key: str = HYBRID_KERNEL_STAGE_LABEL
    stage_name_prefix: str = "hybrid-stage"
    controller_name: str = "ibg-hybrid-controller"
    controller_service_account: str = "ibg-hybrid-controller"
    discovery_role_name: str = "ibg-hybrid-replica-discovery"
    flow_generator_name: str = "ibg-hybrid-flow-generator"
    runtime_profile_config_map: str = "ibg-hybrid-runtime-profiles"
    planning_link_config_map: str = "ibg-hybrid-planning-links"
    service_image: str = "ibg-hybrid-testbed:kernel-service-v1"
    controller_image: str = "ibg-hybrid-testbed:kernel-controller-v1"
    contract_version: str = HYBRID_KERNEL_INFRASTRUCTURE_CONTRACT_VERSION

    def __post_init__(self) -> None:
        for field in (
            "namespace",
            "part_of_label",
            "replica_name_label",
            "stage_label_key",
            "stage_name_prefix",
            "controller_name",
            "controller_service_account",
            "discovery_role_name",
            "flow_generator_name",
            "runtime_profile_config_map",
            "planning_link_config_map",
            "service_image",
            "controller_image",
        ):
            _require_nonempty(getattr(self, field), field)
        if self.contract_version != HYBRID_KERNEL_INFRASTRUCTURE_CONTRACT_VERSION:
            raise HybridKernelContractError(
                "unexpected Hybrid Kernel infrastructure contract version"
            )
        if self.namespace in _FORBIDDEN_SHARED_NAMESPACES:
            raise HybridKernelContractError(
                "Hybrid must not share the Exact or MILP namespace"
            )
        if self.part_of_label in _FORBIDDEN_SHARED_NAMESPACES:
            raise HybridKernelContractError(
                "Hybrid must not share the Exact or MILP ownership label"
            )
        if self.service_image == self.controller_image:
            raise HybridKernelContractError(
                "Hybrid service and controller images must have separate ownership"
            )
        owned_names = (
            self.controller_name,
            self.controller_service_account,
            self.discovery_role_name,
            self.flow_generator_name,
            self.runtime_profile_config_map,
            self.planning_link_config_map,
        )
        if any(not name.startswith("ibg-hybrid-") for name in owned_names):
            raise HybridKernelContractError(
                "Hybrid Kubernetes object names must use the ibg-hybrid- prefix"
            )

    def stage_name(self, stage: int) -> str:
        return f"{self.stage_name_prefix}-{_require_positive_integer(stage, 'stage')}"

    def replica_labels(self, stage: int) -> tuple[tuple[str, str], ...]:
        stage = _require_positive_integer(stage, "stage")
        return tuple(
            sorted(
                (
                    ("app.kubernetes.io/component", "replica-stage"),
                    ("app.kubernetes.io/name", self.replica_name_label),
                    ("app.kubernetes.io/part-of", self.part_of_label),
                    (self.stage_label_key, str(stage)),
                )
            )
        )

    def replica_selector(self, stage: int) -> tuple[tuple[str, str], ...]:
        stage = _require_positive_integer(stage, "stage")
        return tuple(
            sorted(
                (
                    ("app.kubernetes.io/name", self.replica_name_label),
                    (self.stage_label_key, str(stage)),
                )
            )
        )


DEFAULT_HYBRID_KERNEL_OWNERSHIP = HybridKernelOwnership()


@dataclass(frozen=True, order=True)
class HybridKernelRuntimeReplicaProfile:
    """Processor-owned hidden state and deterministic observation seed.

    Beliefs are intentionally absent: learned beliefs belong only to the
    Hybrid controller and persist across slots.  Admission capacity and
    planning links likewise remain separate controller inputs.
    """

    choice: ReplicaChoice
    hidden_state: int
    observation_seed: int

    def __post_init__(self) -> None:
        if not isinstance(self.choice, ReplicaChoice):
            raise HybridKernelContractError("profile choice must be ReplicaChoice")
        if (
            isinstance(self.hidden_state, bool)
            or not isinstance(self.hidden_state, Integral)
            or self.hidden_state not in (1, 2, 3, 4)
        ):
            raise HybridKernelContractError(
                "profile hidden_state must be one of 1, 2, 3, or 4"
            )
        if (
            isinstance(self.observation_seed, bool)
            or not isinstance(self.observation_seed, Integral)
            or self.observation_seed < 0
        ):
            raise HybridKernelContractError(
                "profile observation_seed must be a nonnegative integer"
            )


@dataclass(frozen=True)
class HybridKernelRuntimeProfileDocument:
    """Complete, canonical runtime profile for the requested replica set."""

    configuration: HybridConfiguration
    profiles: tuple[HybridKernelRuntimeReplicaProfile, ...]
    source_identity: str
    contract_version: str = HYBRID_KERNEL_RUNTIME_PROFILE_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.configuration, HybridConfiguration):
            raise HybridKernelContractError(
                "profile configuration must be HybridConfiguration"
            )
        profiles = tuple(self.profiles)
        object.__setattr__(self, "profiles", profiles)
        _require_nonempty(self.source_identity, "source_identity")
        if self.contract_version != HYBRID_KERNEL_RUNTIME_PROFILE_CONTRACT_VERSION:
            raise HybridKernelContractError(
                "unexpected Hybrid runtime-profile contract version"
            )
        choices = tuple(profile.choice for profile in profiles)
        if len(set(choices)) != len(choices):
            raise HybridKernelContractError(
                "runtime profiles must not contain duplicate replica identities"
            )
        if profiles != tuple(sorted(profiles, key=lambda item: item.choice)):
            raise HybridKernelContractError(
                "runtime profiles must use canonical stage/replica order"
            )
        expected = {
            ReplicaChoice(stage, replica)
            for stage in range(1, self.configuration.num_stages + 1)
            for replica in range(1, self.configuration.num_replicas + 1)
        }
        actual = set(choices)
        if actual != expected:
            missing = sorted(expected - actual)
            unexpected = sorted(actual - expected)
            raise HybridKernelContractError(
                "runtime-profile coverage mismatch: "
                f"missing={missing}, unexpected={unexpected}"
            )

    def profile_by_choice(self) -> dict[ReplicaChoice, HybridKernelRuntimeReplicaProfile]:
        return {profile.choice: profile for profile in self.profiles}


@dataclass(frozen=True, order=True)
class HybridKernelDiscoveredReplica:
    """Read-only Pod information accepted by future Hybrid discovery."""

    choice: ReplicaChoice
    namespace: str
    pod_name: str
    pod_uid: str
    endpoint: str
    labels: tuple[tuple[str, str], ...]
    phase: str = "Running"
    ready: bool = True
    node_name: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.choice, ReplicaChoice):
            raise HybridKernelContractError("discovery choice must be ReplicaChoice")
        for field in ("namespace", "pod_name", "pod_uid", "endpoint", "phase"):
            _require_nonempty(getattr(self, field), field)
        if self.node_name is not None:
            _require_nonempty(self.node_name, "node_name")
        if not isinstance(self.ready, bool):
            raise HybridKernelContractError("ready must be boolean")
        labels = tuple(self.labels)
        object.__setattr__(self, "labels", labels)
        if labels != tuple(sorted(labels)) or len(dict(labels)) != len(labels):
            raise HybridKernelContractError(
                "discovery labels must be unique and canonically ordered"
            )
        if any(
            not isinstance(key, str)
            or not key
            or not isinstance(value, str)
            or not value
            for key, value in labels
        ):
            raise HybridKernelContractError(
                "discovery label keys and values must be nonempty strings"
            )


def require_complete_ready_discovery(
    discovered: Iterable[HybridKernelDiscoveredReplica],
    configuration: HybridConfiguration,
    ownership: HybridKernelOwnership = DEFAULT_HYBRID_KERNEL_OWNERSHIP,
) -> tuple[HybridKernelDiscoveredReplica, ...]:
    """Validate exact Ready ordinal coverage without contacting Kubernetes."""

    if not isinstance(configuration, HybridConfiguration):
        raise HybridKernelContractError(
            "discovery configuration must be HybridConfiguration"
        )
    if not isinstance(ownership, HybridKernelOwnership):
        raise HybridKernelContractError("ownership must be HybridKernelOwnership")
    replicas = tuple(discovered)
    if any(not isinstance(item, HybridKernelDiscoveredReplica) for item in replicas):
        raise HybridKernelContractError(
            "discovery entries must be HybridKernelDiscoveredReplica values"
        )
    expected_choices = {
        ReplicaChoice(stage, replica)
        for stage in range(1, configuration.num_stages + 1)
        for replica in range(1, configuration.num_replicas + 1)
    }
    actual_choices = {item.choice for item in replicas}
    if len(actual_choices) != len(replicas):
        raise HybridKernelContractError(
            "Ready discovery must not contain duplicate replica identities"
        )
    for field in ("pod_name", "pod_uid", "endpoint"):
        values = tuple(getattr(item, field) for item in replicas)
        if len(set(values)) != len(values):
            raise HybridKernelContractError(
                f"Ready discovery must not contain duplicate {field} values"
            )
    if actual_choices != expected_choices:
        missing = sorted(expected_choices - actual_choices)
        unexpected = sorted(actual_choices - expected_choices)
        raise HybridKernelContractError(
            "Ready discovery coverage mismatch: "
            f"missing={missing}, unexpected={unexpected}"
        )
    for item in replicas:
        if item.namespace != ownership.namespace:
            raise HybridKernelContractError(
                f"replica {item.choice} belongs to a foreign namespace"
            )
        if item.phase != "Running" or not item.ready:
            raise HybridKernelContractError(
                f"replica {item.choice} is not Running and Ready"
            )
        expected_name = (
            f"{ownership.stage_name(item.choice.stage)}-{item.choice.replica - 1}"
        )
        if item.pod_name != expected_name:
            raise HybridKernelContractError(
                f"replica {item.choice} has unexpected StatefulSet identity "
                f"{item.pod_name!r}; expected {expected_name!r}"
            )
        labels = dict(item.labels)
        required_labels = dict(ownership.replica_labels(item.choice.stage))
        if any(labels.get(key) != value for key, value in required_labels.items()):
            raise HybridKernelContractError(
                f"replica {item.choice} does not have Hybrid-owned labels"
            )
    return tuple(sorted(replicas, key=lambda item: item.choice))


@dataclass(frozen=True)
class HybridKernelDiscoverySnapshot:
    """Versioned complete Ready set retained by a future controller."""

    configuration: HybridConfiguration
    replicas: tuple[HybridKernelDiscoveredReplica, ...]
    ownership: HybridKernelOwnership = DEFAULT_HYBRID_KERNEL_OWNERSHIP
    contract_version: str = HYBRID_KERNEL_DISCOVERY_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.contract_version != HYBRID_KERNEL_DISCOVERY_CONTRACT_VERSION:
            raise HybridKernelContractError(
                "unexpected Hybrid Ready-discovery contract version"
            )
        canonical = require_complete_ready_discovery(
            self.replicas,
            self.configuration,
            self.ownership,
        )
        object.__setattr__(self, "replicas", canonical)

    def replica_by_choice(self) -> dict[ReplicaChoice, HybridKernelDiscoveredReplica]:
        return {replica.choice: replica for replica in self.replicas}


class HybridKernelControllerStep(str, Enum):
    """Required ordering for one future Hybrid Kernel slot."""

    DISCOVER_COMPLETE_READY_SET = "discover-complete-ready-set"
    PLACE_ALL_FOCAL_FLOWS = "place-all-focal-flows"
    EXECUTE_SELECTED_ROUTES = "execute-selected-routes"
    VALIDATE_COMPLETE_TELEMETRY = "validate-complete-telemetry"
    APPLY_SELECTED_ONLY_LEARNING = "apply-selected-only-learning"
    EMIT_SLOT_RESULT = "emit-slot-result"


HYBRID_KERNEL_CONTROLLER_STEPS = tuple(HybridKernelControllerStep)


@dataclass(frozen=True)
class HybridKernelControllerLifecycle:
    """Frozen sequencing/information boundary for a future controller."""

    steps: tuple[HybridKernelControllerStep, ...] = HYBRID_KERNEL_CONTROLLER_STEPS
    beliefs_owner: str = "controller-private"
    beliefs_persist_across_slots: bool = True
    traffic_starts_after_complete_placement: bool = True
    hidden_state_is_policy_input: bool = False
    automatic_monte_carlo_activation: bool = False
    contract_version: str = HYBRID_KERNEL_CONTROLLER_LIFECYCLE_VERSION

    def __post_init__(self) -> None:
        steps = tuple(self.steps)
        object.__setattr__(self, "steps", steps)
        if steps != HYBRID_KERNEL_CONTROLLER_STEPS:
            raise HybridKernelContractError(
                "Hybrid Kernel controller steps must use the Phase 0 order"
            )
        if self.beliefs_owner != "controller-private":
            raise HybridKernelContractError(
                "Hybrid beliefs must remain controller-private"
            )
        for field in (
            "beliefs_persist_across_slots",
            "traffic_starts_after_complete_placement",
        ):
            if getattr(self, field) is not True:
                raise HybridKernelContractError(f"{field} must remain enabled")
        for field in (
            "hidden_state_is_policy_input",
            "automatic_monte_carlo_activation",
        ):
            if getattr(self, field) is not False:
                raise HybridKernelContractError(f"{field} must remain disabled")
        if self.contract_version != HYBRID_KERNEL_CONTROLLER_LIFECYCLE_VERSION:
            raise HybridKernelContractError(
                "unexpected Hybrid controller-lifecycle contract version"
            )


DEFAULT_HYBRID_KERNEL_CONTROLLER_LIFECYCLE = HybridKernelControllerLifecycle()


@dataclass(frozen=True)
class HybridKernelImageOwnership:
    """Separate dependency ownership for future service/controller images."""

    service_image: str = DEFAULT_HYBRID_KERNEL_OWNERSHIP.service_image
    controller_image: str = DEFAULT_HYBRID_KERNEL_OWNERSHIP.controller_image
    service_components: tuple[str, ...] = (
        "private-processor",
        "public-forwarder",
        "flow-generator",
    )
    controller_components: tuple[str, ...] = (
        "hybrid-policy",
        "selected-only-learning",
        "slot-orchestration",
    )
    controller_only_dependencies_forbidden_in_service: tuple[str, ...] = (
        "hybrid-policy",
        "selected-only-learning",
        "slot-orchestration",
    )
    milp_solver_dependencies_forbidden: tuple[str, ...] = (
        "scipy",
        "highs",
        "ortools",
    )
    contract_version: str = HYBRID_KERNEL_IMAGE_OWNERSHIP_VERSION

    def __post_init__(self) -> None:
        _require_nonempty(self.service_image, "service_image")
        _require_nonempty(self.controller_image, "controller_image")
        if self.service_image == self.controller_image:
            raise HybridKernelContractError(
                "Hybrid service and controller image names must differ"
            )
        for field in (
            "service_components",
            "controller_components",
            "controller_only_dependencies_forbidden_in_service",
            "milp_solver_dependencies_forbidden",
        ):
            values = tuple(getattr(self, field))
            object.__setattr__(self, field, values)
            if not values or len(set(values)) != len(values):
                raise HybridKernelContractError(
                    f"{field} must be a nonempty tuple of unique values"
                )
            for value in values:
                _require_nonempty(value, field)
        if set(self.service_components) & set(self.controller_components):
            raise HybridKernelContractError(
                "service and controller component ownership must not overlap"
            )
        if self.contract_version != HYBRID_KERNEL_IMAGE_OWNERSHIP_VERSION:
            raise HybridKernelContractError(
                "unexpected Hybrid image-ownership contract version"
            )


DEFAULT_HYBRID_KERNEL_IMAGE_OWNERSHIP = HybridKernelImageOwnership()


@dataclass(frozen=True)
class HybridKernelRuntimeReuseBoundary:
    """Algorithm-neutral Exact runtime behavior preserved by future Hybrid."""

    private_processor_port: int = 8081
    private_processor_workers: int = 1
    public_forwarder_port: int = 8080
    public_forwarder_workers: int = 2
    public_forwarder_keepalive_seconds: int = 30
    separate_local_and_downstream_clients: bool = True
    route_contract_phase: int = 1
    resource_acceptance_phase: int = 7
    source_boundary: str = "frozen-exact-private-processor-public-forwarder"

    def __post_init__(self) -> None:
        for field in (
            "private_processor_port",
            "private_processor_workers",
            "public_forwarder_port",
            "public_forwarder_workers",
            "public_forwarder_keepalive_seconds",
            "route_contract_phase",
            "resource_acceptance_phase",
        ):
            _require_positive_integer(getattr(self, field), field)
        if self.private_processor_workers != 1:
            raise HybridKernelContractError(
                "the reused private processor must remain single-worker"
            )
        if self.public_forwarder_workers != 2:
            raise HybridKernelContractError(
                "the reused public forwarder must retain two workers"
            )
        if self.private_processor_port != 8081 or self.public_forwarder_port != 8080:
            raise HybridKernelContractError("the reused processor/forwarder ports changed")
        if self.public_forwarder_keepalive_seconds != 30:
            raise HybridKernelContractError(
                "the reused public-forwarder keep-alive must remain 30 seconds"
            )
        if self.separate_local_and_downstream_clients is not True:
            raise HybridKernelContractError(
                "local and downstream HTTP clients must remain separate"
            )
        if self.route_contract_phase != 1 or self.resource_acceptance_phase != 7:
            raise HybridKernelContractError(
                "route execution and resource acceptance must remain deferred"
            )
        _require_nonempty(self.source_boundary, "source_boundary")


DEFAULT_HYBRID_KERNEL_RUNTIME_REUSE = HybridKernelRuntimeReuseBoundary()
