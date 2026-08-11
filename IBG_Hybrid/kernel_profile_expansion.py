"""Append-only Hybrid Kernel profile validation for Infrastructure Phase 6."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Mapping

from .contracts import HybridConfiguration, ReplicaChoice
from .kernel_controller_config import (
    HybridKernelControllerInputDocument,
    controller_input_document_from_mapping,
)
from .kernel_infrastructure_contract import (
    HybridKernelRuntimeProfileDocument,
)
from .kernel_runtime_profiles import runtime_profile_document_from_mapping


HYBRID_KERNEL_PROFILE_EXPANSION_VERSION = (
    "ibg-hybrid-kernel-profile-expansion-v1"
)
HYBRID_KERNEL_FLOW_ONLY_EXPANSION_VERSION = (
    "ibg-hybrid-kernel-flow-only-expansion-v1"
)
HYBRID_KERNEL_DYNAMIC_TOPOLOGY_VERSION = (
    "ibg-hybrid-kernel-dynamic-topology-v1"
)
HYBRID_PROFILE_STATE_ALLOCATION_VERSION = (
    "ibg-hybrid-profile-state-allocation-v1"
)
# Public order and exact integer weights: Very Good, Good, Bad, Very Bad.
HYBRID_PROFILE_STATE_ORDER = (4, 3, 2, 1)
HYBRID_PROFILE_STATE_WEIGHT_UNITS = (3, 3, 2, 2)
HYBRID_PROFILE_STATE_WEIGHT_TOTAL = sum(HYBRID_PROFILE_STATE_WEIGHT_UNITS)


class HybridKernelProfileExpansionError(ValueError):
    """Raised before mutation when a profile expansion is not append-only."""


@dataclass(frozen=True)
class HybridKernelProfileExpansion:
    """Validated additions between deployed and proposed complete documents."""

    existing_replica_count: int
    deployed_profile_count: int
    target_replica_count: int
    added_runtime_identities: tuple[ReplicaChoice, ...]
    added_admission_identities: tuple[ReplicaChoice, ...]
    added_planning_pairs: tuple[tuple[ReplicaChoice, ReplicaChoice], ...]
    contract_version: str = HYBRID_KERNEL_PROFILE_EXPANSION_VERSION


@dataclass(frozen=True)
class HybridKernelFlowOnlyExpansion:
    """Validated topology-only transition with no replica-owned data change."""

    deployed_configuration: HybridConfiguration
    target_configuration: HybridConfiguration
    runtime_profile_count: int
    admission_count: int
    planning_pair_count: int
    contract_version: str = HYBRID_KERNEL_FLOW_ONLY_EXPANSION_VERSION


@dataclass(frozen=True)
class HybridKernelDynamicTopologyTransition:
    """Validated dimension-driven transition before Kubernetes mutation."""

    deployed_configuration: HybridConfiguration
    target_configuration: HybridConfiguration
    retained_runtime_identities: tuple[ReplicaChoice, ...]
    added_runtime_identities: tuple[ReplicaChoice, ...]
    changed_runtime_identities: tuple[ReplicaChoice, ...]
    removed_runtime_identities: tuple[ReplicaChoice, ...]
    retained_admission_identities: tuple[ReplicaChoice, ...]
    added_admission_identities: tuple[ReplicaChoice, ...]
    changed_admission_identities: tuple[ReplicaChoice, ...]
    removed_admission_identities: tuple[ReplicaChoice, ...]
    retained_planning_pairs: tuple[tuple[ReplicaChoice, ReplicaChoice], ...]
    added_planning_pairs: tuple[tuple[ReplicaChoice, ReplicaChoice], ...]
    removed_planning_pairs: tuple[tuple[ReplicaChoice, ReplicaChoice], ...]
    profile_refresh_required: bool = False
    deployed_profile_seed: int | None = None
    target_profile_seed: int | None = None
    contract_version: str = HYBRID_KERNEL_DYNAMIC_TOPOLOGY_VERSION


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise HybridKernelProfileExpansionError(f"{field} must be a mapping")
    return value


def _list(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise HybridKernelProfileExpansionError(f"{field} must be a list")
    return value


def _exact_keys(
    value: Mapping[str, object], expected: frozenset[str], field: str
) -> None:
    actual = frozenset(value)
    if actual != expected:
        raise HybridKernelProfileExpansionError(
            f"{field} fields differ: expected={sorted(expected)}, "
            f"actual={sorted(actual)}"
        )


def _validate_runtime_shape(value: Mapping[str, object]) -> None:
    _exact_keys(
        value,
        frozenset(("contract_version", "source_identity", "configuration", "profiles")),
        "runtime-profile document",
    )
    configuration = _mapping(value.get("configuration"), "runtime configuration")
    _exact_keys(
        configuration,
        frozenset(("num_flows", "num_stages", "num_replicas", "stage_budget")),
        "runtime configuration",
    )
    for index, item in enumerate(_list(value.get("profiles"), "runtime profiles")):
        profile = _mapping(item, f"runtime profile {index}")
        _exact_keys(
            profile,
            frozenset(("stage", "replica", "hidden_state", "observation_seed")),
            f"runtime profile {index}",
        )


def _validate_controller_shape(value: Mapping[str, object]) -> None:
    _exact_keys(
        value,
        frozenset(
            (
                "contract_version",
                "source_identity",
                "configuration",
                "admission",
                "planning_pair_links",
            )
        ),
        "controller-input document",
    )
    configuration = _mapping(value.get("configuration"), "controller configuration")
    _exact_keys(
        configuration,
        frozenset(("num_flows", "num_stages", "num_replicas", "stage_budget")),
        "controller configuration",
    )
    for index, item in enumerate(_list(value.get("admission"), "controller admission")):
        admission = _mapping(item, f"controller admission {index}")
        _exact_keys(
            admission,
            frozenset(("stage", "replica", "max_assigned_flows")),
            f"controller admission {index}",
        )
    for index, item in enumerate(
        _list(value.get("planning_pair_links"), "controller planning links")
    ):
        link = _mapping(item, f"controller planning link {index}")
        _exact_keys(
            link,
            frozenset(
                (
                    "source_stage",
                    "source_replica",
                    "target_stage",
                    "target_replica",
                    "latency_ms",
                )
            ),
            f"controller planning link {index}",
        )


def _runtime_document(
    value: Mapping[str, object], field: str
) -> HybridKernelRuntimeProfileDocument:
    try:
        _validate_runtime_shape(value)
        return runtime_profile_document_from_mapping(value)
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, HybridKernelProfileExpansionError):
            raise
        raise HybridKernelProfileExpansionError(f"invalid {field}: {error}") from error


def _controller_document(
    value: Mapping[str, object], field: str
) -> HybridKernelControllerInputDocument:
    try:
        _validate_controller_shape(value)
        return controller_input_document_from_mapping(value)
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, HybridKernelProfileExpansionError):
            raise
        raise HybridKernelProfileExpansionError(f"invalid {field}: {error}") from error


def _require_preserved(old: Mapping[object, object], new: Mapping[object, object], field: str) -> None:
    missing = sorted(set(old) - set(new))
    drifted = sorted(key for key, value in old.items() if new.get(key) != value)
    if missing:
        raise HybridKernelProfileExpansionError(
            f"{field} dropped existing entries: {missing}"
        )
    if drifted:
        raise HybridKernelProfileExpansionError(
            f"{field} drifted for existing entries: {drifted}"
        )


def validate_append_only_profile_expansion(
    *,
    deployed_runtime: Mapping[str, object],
    deployed_controller: Mapping[str, object],
    proposed_runtime: Mapping[str, object],
    proposed_controller: Mapping[str, object],
    existing_replica_count: int,
    expected_configuration: HybridConfiguration,
    expected_source_identity: str,
) -> HybridKernelProfileExpansion:
    """Validate complete proposed documents before either ConfigMap is changed."""

    if existing_replica_count < 1:
        raise HybridKernelProfileExpansionError(
            "existing_replica_count must be positive"
        )
    if not isinstance(expected_configuration, HybridConfiguration):
        raise TypeError("expected_configuration must be HybridConfiguration")
    if not isinstance(expected_source_identity, str) or not expected_source_identity:
        raise HybridKernelProfileExpansionError(
            "expected_source_identity must be nonempty"
        )

    current_runtime = _runtime_document(deployed_runtime, "deployed runtime profile")
    current_controller = _controller_document(
        deployed_controller, "deployed controller input"
    )
    target_runtime = _runtime_document(proposed_runtime, "proposed runtime profile")
    target_controller = _controller_document(
        proposed_controller, "proposed controller input"
    )

    if current_runtime.configuration != current_controller.configuration:
        raise HybridKernelProfileExpansionError(
            "deployed runtime/controller configurations differ"
        )
    if target_runtime.configuration != target_controller.configuration:
        raise HybridKernelProfileExpansionError(
            "proposed runtime/controller configurations differ"
        )
    if target_runtime.configuration != expected_configuration:
        raise HybridKernelProfileExpansionError(
            "proposed documents do not match the exact target configuration"
        )
    if (
        target_runtime.source_identity != expected_source_identity
        or target_controller.source_identity != expected_source_identity
    ):
        raise HybridKernelProfileExpansionError(
            "proposed documents do not use the approved target source identity"
        )

    current_configuration = current_runtime.configuration
    if (
        current_configuration.num_stages != expected_configuration.num_stages
        or current_configuration.stage_budget != expected_configuration.stage_budget
        or current_configuration.num_flows > expected_configuration.num_flows
        or not (
            existing_replica_count
            <= current_configuration.num_replicas
            <= expected_configuration.num_replicas
        )
    ):
        raise HybridKernelProfileExpansionError(
            "deployed profile configuration is outside the append-only boundary"
        )

    old_runtime = {item.choice: item for item in current_runtime.profiles}
    new_runtime = {item.choice: item for item in target_runtime.profiles}
    _require_preserved(old_runtime, new_runtime, "runtime identity/state/seed")

    old_admission = {item.choice: item for item in current_controller.admission}
    new_admission = {item.choice: item for item in target_controller.admission}
    _require_preserved(old_admission, new_admission, "admission capacity")

    old_links = {item.pair: item for item in current_controller.planning_pair_links}
    new_links = {item.pair: item for item in target_controller.planning_pair_links}
    _require_preserved(old_links, new_links, "planning link")

    return HybridKernelProfileExpansion(
        existing_replica_count=existing_replica_count,
        deployed_profile_count=current_configuration.num_replicas,
        target_replica_count=expected_configuration.num_replicas,
        added_runtime_identities=tuple(sorted(set(new_runtime) - set(old_runtime))),
        added_admission_identities=tuple(
            sorted(set(new_admission) - set(old_admission))
        ),
        added_planning_pairs=tuple(sorted(set(new_links) - set(old_links))),
    )


def validate_flow_only_profile_expansion(
    *,
    deployed_runtime: Mapping[str, object],
    deployed_controller: Mapping[str, object],
    proposed_runtime: Mapping[str, object],
    proposed_controller: Mapping[str, object],
    deployed_configuration: HybridConfiguration,
    target_configuration: HybridConfiguration,
    deployed_source_identity: str,
    target_source_identity: str,
) -> HybridKernelFlowOnlyExpansion:
    """Require a flow-count/source transition and otherwise identical documents."""

    for value, field in (
        (deployed_configuration, "deployed_configuration"),
        (target_configuration, "target_configuration"),
    ):
        if not isinstance(value, HybridConfiguration):
            raise TypeError(f"{field} must be HybridConfiguration")
    for value, field in (
        (deployed_source_identity, "deployed_source_identity"),
        (target_source_identity, "target_source_identity"),
    ):
        if not isinstance(value, str) or not value:
            raise HybridKernelProfileExpansionError(f"{field} must be nonempty")
    if (
        target_configuration.num_flows <= deployed_configuration.num_flows
        or target_configuration.num_stages != deployed_configuration.num_stages
        or target_configuration.num_replicas
        != deployed_configuration.num_replicas
        or target_configuration.stage_budget != deployed_configuration.stage_budget
    ):
        raise HybridKernelProfileExpansionError(
            "flow-only expansion may increase only num_flows"
        )

    current_runtime = _runtime_document(deployed_runtime, "deployed runtime profile")
    current_controller = _controller_document(
        deployed_controller, "deployed controller input"
    )
    target_runtime = _runtime_document(proposed_runtime, "proposed runtime profile")
    target_controller = _controller_document(
        proposed_controller, "proposed controller input"
    )

    if (
        current_runtime.configuration != deployed_configuration
        or current_controller.configuration != deployed_configuration
    ):
        raise HybridKernelProfileExpansionError(
            "deployed documents do not match the approved source configuration"
        )
    if (
        target_runtime.configuration != target_configuration
        or target_controller.configuration != target_configuration
    ):
        raise HybridKernelProfileExpansionError(
            "proposed documents do not match the exact flow-only target"
        )
    if (
        current_runtime.source_identity != deployed_source_identity
        or current_controller.source_identity != deployed_source_identity
    ):
        raise HybridKernelProfileExpansionError(
            "deployed documents do not use the approved source identity"
        )
    if (
        target_runtime.source_identity != target_source_identity
        or target_controller.source_identity != target_source_identity
    ):
        raise HybridKernelProfileExpansionError(
            "proposed documents do not use the approved target source identity"
        )

    if target_runtime.profiles != current_runtime.profiles:
        raise HybridKernelProfileExpansionError(
            "flow-only expansion drifted runtime identity/state/seed"
        )
    if target_controller.admission != current_controller.admission:
        raise HybridKernelProfileExpansionError(
            "flow-only expansion drifted admission capacity"
        )
    if (
        target_controller.planning_pair_links
        != current_controller.planning_pair_links
    ):
        raise HybridKernelProfileExpansionError(
            "flow-only expansion drifted planning links"
        )

    return HybridKernelFlowOnlyExpansion(
        deployed_configuration=deployed_configuration,
        target_configuration=target_configuration,
        runtime_profile_count=len(target_runtime.profiles),
        admission_count=len(target_controller.admission),
        planning_pair_count=len(target_controller.planning_pair_links),
    )


def dynamic_topology_source_identity(
    configuration: HybridConfiguration,
) -> str:
    """Return the stable source identity for one generated Hybrid topology."""

    if not isinstance(configuration, HybridConfiguration):
        raise TypeError("configuration must be HybridConfiguration")
    historical = {
        (2, 3, 1): "ibg-hybrid-infrastructure-phase4-small-live-v1",
        (3, 3, 2): "ibg-hybrid-infrastructure-phase6-3x3x2-v1",
        (4, 3, 2): "ibg-hybrid-infrastructure-phase8-gate1-4x3x2-v1",
    }
    dimensions = (
        configuration.num_flows,
        configuration.num_stages,
        configuration.num_replicas,
    )
    if dimensions in historical:
        return historical[dimensions]
    return (
        f"{HYBRID_KERNEL_DYNAMIC_TOPOLOGY_VERSION}:"
        f"{configuration.num_flows}x{configuration.num_stages}x"
        f"{configuration.num_replicas}"
    )


def _validate_profile_seed(profile_seed: int) -> int:
    if (
        isinstance(profile_seed, bool)
        or not isinstance(profile_seed, int)
        or profile_seed < 0
    ):
        raise HybridKernelProfileExpansionError(
            "profile_seed must be a nonnegative integer"
        )
    return profile_seed


def seeded_runtime_source_identity(
    configuration: HybridConfiguration,
    profile_seed: int,
) -> str:
    """Identify a seeded processor profile without exposing it to controller input."""

    seed = _validate_profile_seed(profile_seed)
    return (
        f"{dynamic_topology_source_identity(configuration)}:"
        f"{HYBRID_PROFILE_STATE_ALLOCATION_VERSION}:profile-seed={seed}"
    )


def _profile_seed_from_runtime_source_identity(source_identity: str) -> int | None:
    marker = f":{HYBRID_PROFILE_STATE_ALLOCATION_VERSION}:profile-seed="
    if marker not in source_identity:
        return None
    prefix, value = source_identity.rsplit(marker, 1)
    if not prefix or not value.isdecimal():
        raise HybridKernelProfileExpansionError(
            "runtime profile has malformed seeded-allocation provenance"
        )
    return _validate_profile_seed(int(value))


def seeded_hidden_state_sequence(
    *,
    stage: int,
    replica_count: int,
    profile_seed: int,
) -> tuple[int, ...]:
    """Return an append-only, low-discrepancy seeded state sequence.

    The sequence is built from independent ten-replica strata with exact
    3/3/2/2 quotas.  Inside each stratum, deterministic BLAKE2b ranks order the
    still-feasible state choices at each ordinal; a bounded backtrack rejects a
    choice when any prefix would differ from its ideal quota by more than one.
    Every completed stratum returns to the exact weighted quota, so concatenated
    prefixes retain the same bound.  The seed, stage, stratum, ordinal, and state
    are domain-separated and no process-global RNG is used.
    """

    if isinstance(stage, bool) or not isinstance(stage, int) or stage not in (1, 2, 3):
        raise HybridKernelProfileExpansionError("stage must be one of 1, 2, or 3")
    if (
        isinstance(replica_count, bool)
        or not isinstance(replica_count, int)
        or replica_count < 1
    ):
        raise HybridKernelProfileExpansionError(
            "replica_count must be a positive integer"
        )
    seed = _validate_profile_seed(profile_seed)
    weights = dict(
        zip(HYBRID_PROFILE_STATE_ORDER, HYBRID_PROFILE_STATE_WEIGHT_UNITS)
    )

    def ranked_states(block: int, position: int) -> tuple[int, ...]:
        def rank(state: int) -> int:
            key = (
                f"{HYBRID_PROFILE_STATE_ALLOCATION_VERSION}|{seed}|{stage}|"
                f"{block}|{position}|{state}"
            ).encode("ascii")
            return int.from_bytes(
                hashlib.blake2b(key, digest_size=16).digest(), "big"
            )

        return tuple(sorted(HYBRID_PROFILE_STATE_ORDER, key=rank, reverse=True))

    def allocate_block(block: int) -> tuple[int, ...]:
        assigned = {state: 0 for state in HYBRID_PROFILE_STATE_ORDER}
        selected: list[int] = []

        def fill(position: int) -> bool:
            if position > HYBRID_PROFILE_STATE_WEIGHT_TOTAL:
                return all(
                    assigned[state] == weights[state]
                    for state in HYBRID_PROFILE_STATE_ORDER
                )
            for state in ranked_states(block, position):
                if assigned[state] >= weights[state]:
                    continue
                assigned[state] += 1
                within_prefix_bound = all(
                    abs(
                        assigned[candidate] * HYBRID_PROFILE_STATE_WEIGHT_TOTAL
                        - position * weights[candidate]
                    )
                    <= HYBRID_PROFILE_STATE_WEIGHT_TOTAL
                    for candidate in HYBRID_PROFILE_STATE_ORDER
                )
                if within_prefix_bound:
                    selected.append(state)
                    if fill(position + 1):
                        return True
                    selected.pop()
                assigned[state] -= 1
            return False

        if not fill(1):  # Defensive: the fixed rational mix always has a solution.
            raise HybridKernelProfileExpansionError(
                "seeded state allocator could not satisfy the quota boundary"
            )
        return tuple(selected)

    sequence: list[int] = []
    block = 0
    while len(sequence) < replica_count:
        sequence.extend(allocate_block(block))
        block += 1
    return tuple(sequence[:replica_count])


def seeded_profile_state_counts(
    *,
    replica_count: int,
    profile_seed: int,
) -> dict[int, dict[int, int]]:
    """Return non-sensitive per-stage state counts for launcher provenance."""

    return {
        stage: {
            state: sequence.count(state)
            for state in HYBRID_PROFILE_STATE_ORDER
        }
        for stage in range(1, 4)
        for sequence in (
            seeded_hidden_state_sequence(
                stage=stage,
                replica_count=replica_count,
                profile_seed=profile_seed,
            ),
        )
    }


def assigned_flow_capacity(configuration: HybridConfiguration) -> int:
    """Capacity every replica needs so one complete stage can carry all flows.

    Each of the three stages has ``R`` replicas.  Assigning
    ``ceil(num_flows / R)`` to every replica gives every stage aggregate
    capacity of at least ``num_flows``.  Consequently any two-stage Hybrid
    route family remains admission-feasible without using hidden state.
    """

    if not isinstance(configuration, HybridConfiguration):
        raise TypeError("configuration must be HybridConfiguration")
    return (
        configuration.num_flows + configuration.num_replicas - 1
    ) // configuration.num_replicas


def _extension_observation_seed(stage: int, replica: int) -> int:
    """Derive a stable, unique seed for identities absent from the template."""

    total = stage + replica
    pairing = (total * (total + 1) // 2) + replica
    return 1_000_000_000 + pairing


def generate_dynamic_topology_documents(
    *,
    canonical_runtime: Mapping[str, object],
    canonical_controller: Mapping[str, object],
    configuration: HybridConfiguration,
    profile_seed: int | None = None,
) -> tuple[dict[str, object], dict[str, object]]:
    """Generate complete byte-stable Hybrid runtime and controller documents.

    ``profile_seed=None`` retains the historical fixed-layout projection for
    compatibility fixtures.  A nonnegative seed selects the versioned balanced
    append-only allocator for every hidden state.  Canonical observation seeds
    are preserved and later seeds remain identity-derived.  Controller input is
    independent of the profile seed and contains no state-allocation provenance.
    """

    if not isinstance(configuration, HybridConfiguration):
        raise TypeError("configuration must be HybridConfiguration")
    template_runtime = _runtime_document(
        canonical_runtime, "canonical runtime template"
    )
    template_controller = _controller_document(
        canonical_controller, "canonical controller template"
    )
    if (
        template_runtime.configuration != template_controller.configuration
        or template_runtime.configuration.num_stages != 3
    ):
        raise HybridKernelProfileExpansionError(
            "canonical runtime/controller templates must describe three stages"
        )

    runtime_by_stage: dict[int, list[object]] = {stage: [] for stage in range(1, 4)}
    canonical_runtime_by_choice = {}
    for profile in template_runtime.profiles:
        runtime_by_stage[profile.choice.stage].append(profile)
        canonical_runtime_by_choice[profile.choice] = profile
    if any(not runtime_by_stage[stage] for stage in range(1, 4)):
        raise HybridKernelProfileExpansionError(
            "canonical runtime template must cover every Hybrid stage"
        )

    controller_source_identity = dynamic_topology_source_identity(configuration)
    runtime_source_identity = (
        controller_source_identity
        if profile_seed is None
        else seeded_runtime_source_identity(configuration, profile_seed)
    )
    runtime_profiles = []
    for stage in range(1, 4):
        templates = tuple(runtime_by_stage[stage])
        seeded_states = (
            None
            if profile_seed is None
            else seeded_hidden_state_sequence(
                stage=stage,
                replica_count=configuration.num_replicas,
                profile_seed=profile_seed,
            )
        )
        for replica in range(1, configuration.num_replicas + 1):
            choice = ReplicaChoice(stage, replica)
            existing = canonical_runtime_by_choice.get(choice)
            template = templates[(replica - 1) % len(templates)]
            runtime_profiles.append(
                {
                    "stage": stage,
                    "replica": replica,
                    "hidden_state": (
                        (
                            existing.hidden_state
                            if existing is not None
                            else template.hidden_state
                        )
                        if seeded_states is None
                        else seeded_states[replica - 1]
                    ),
                    "observation_seed": (
                        existing.observation_seed
                        if existing is not None
                        else _extension_observation_seed(stage, replica)
                    ),
                }
            )

    stage_pair_values: dict[tuple[int, int], set[float]] = {}
    canonical_links = {}
    for link in template_controller.planning_pair_links:
        pair = (link.source.stage, link.target.stage)
        stage_pair_values.setdefault(pair, set()).add(link.latency_ms)
        canonical_links[link.pair] = link
    expected_stage_pairs = {(1, 2), (1, 3), (2, 3)}
    if set(stage_pair_values) != expected_stage_pairs or any(
        len(values) != 1 for values in stage_pair_values.values()
    ):
        raise HybridKernelProfileExpansionError(
            "canonical planning links must define one deterministic value "
            "for each increasing Hybrid stage pair"
        )
    stage_pair_rule = {
        pair: next(iter(values)) for pair, values in stage_pair_values.items()
    }

    capacity = assigned_flow_capacity(configuration)
    admission = [
        {
            "stage": stage,
            "replica": replica,
            "max_assigned_flows": capacity,
        }
        for stage in range(1, 4)
        for replica in range(1, configuration.num_replicas + 1)
    ]
    planning_links = []
    for source_stage in range(1, 4):
        for source_replica in range(1, configuration.num_replicas + 1):
            for target_stage in range(source_stage + 1, 4):
                for target_replica in range(1, configuration.num_replicas + 1):
                    source = ReplicaChoice(source_stage, source_replica)
                    target = ReplicaChoice(target_stage, target_replica)
                    existing = canonical_links.get((source, target))
                    planning_links.append(
                        {
                            "source_stage": source_stage,
                            "source_replica": source_replica,
                            "target_stage": target_stage,
                            "target_replica": target_replica,
                            "latency_ms": (
                                existing.latency_ms
                                if existing is not None
                                else stage_pair_rule[(source_stage, target_stage)]
                            ),
                        }
                    )

    configuration_mapping = {
        "num_flows": configuration.num_flows,
        "num_stages": configuration.num_stages,
        "num_replicas": configuration.num_replicas,
        "stage_budget": configuration.stage_budget,
    }
    runtime = {
        "contract_version": template_runtime.contract_version,
        "source_identity": runtime_source_identity,
        "configuration": dict(configuration_mapping),
        "profiles": runtime_profiles,
    }
    controller = {
        "contract_version": template_controller.contract_version,
        "source_identity": controller_source_identity,
        "configuration": dict(configuration_mapping),
        "admission": admission,
        "planning_pair_links": planning_links,
    }
    # Parse the generated shape here so malformed templates fail before any
    # caller can use the documents for a ConfigMap reconciliation.
    _runtime_document(runtime, "generated runtime profile")
    _controller_document(controller, "generated controller input")
    return runtime, controller


def validate_dynamic_topology_transition(
    *,
    deployed_runtime: Mapping[str, object],
    deployed_controller: Mapping[str, object],
    proposed_runtime: Mapping[str, object],
    proposed_controller: Mapping[str, object],
    canonical_runtime: Mapping[str, object],
    canonical_controller: Mapping[str, object],
    existing_replica_count: int,
    target_configuration: HybridConfiguration,
    profile_seed: int | None = None,
    allow_runtime_profile_refresh: bool = False,
) -> HybridKernelDynamicTopologyTransition:
    """Reject drift and permit only deterministic dimension-driven changes."""

    if (
        isinstance(existing_replica_count, bool)
        or not isinstance(existing_replica_count, int)
        or existing_replica_count < 1
    ):
        raise HybridKernelProfileExpansionError(
            "existing_replica_count must be positive"
        )
    if not isinstance(target_configuration, HybridConfiguration):
        raise TypeError("target_configuration must be HybridConfiguration")
    current_runtime = _runtime_document(
        deployed_runtime, "deployed runtime profile"
    )
    current_controller = _controller_document(
        deployed_controller, "deployed controller input"
    )
    if current_runtime.configuration != current_controller.configuration:
        raise HybridKernelProfileExpansionError(
            "deployed runtime/controller configurations differ"
        )
    deployed_configuration = current_runtime.configuration
    if deployed_configuration.num_replicas != existing_replica_count:
        raise HybridKernelProfileExpansionError(
            "deployed profile replica count differs from StatefulSet count"
        )
    if profile_seed is not None:
        _validate_profile_seed(profile_seed)
    deployed_profile_seed = _profile_seed_from_runtime_source_identity(
        current_runtime.source_identity
    )
    expected_current_runtime, expected_current_controller = generate_dynamic_topology_documents(
        canonical_runtime=canonical_runtime,
        canonical_controller=canonical_controller,
        configuration=deployed_configuration,
        profile_seed=deployed_profile_seed,
    )
    expected_target_runtime, expected_target_controller = (
        generate_dynamic_topology_documents(
            canonical_runtime=canonical_runtime,
            canonical_controller=canonical_controller,
            configuration=target_configuration,
            profile_seed=profile_seed,
        )
    )
    if deployed_runtime != expected_current_runtime:
        raise HybridKernelProfileExpansionError(
            "deployed runtime document drifted from the versioned rule"
        )
    if deployed_controller != expected_current_controller:
        raise HybridKernelProfileExpansionError(
            "deployed controller document drifted from the versioned rule"
        )
    if proposed_runtime != expected_target_runtime:
        raise HybridKernelProfileExpansionError(
            "proposed runtime profile is not the deterministic target document"
        )
    if proposed_controller != expected_target_controller:
        raise HybridKernelProfileExpansionError(
            "proposed controller input is not the deterministic target document"
        )

    profile_refresh_required = deployed_profile_seed != profile_seed
    if profile_refresh_required and not allow_runtime_profile_refresh:
        raise HybridKernelProfileExpansionError(
            "changing the runtime profile seed/allocation requires explicit "
            "--refresh-runtime-profiles confirmation"
        )

    target_runtime = _runtime_document(proposed_runtime, "proposed runtime profile")
    target_controller = _controller_document(
        proposed_controller, "proposed controller input"
    )
    old_runtime = {item.choice: item for item in current_runtime.profiles}
    new_runtime = {item.choice: item for item in target_runtime.profiles}
    old_links = {item.pair: item for item in current_controller.planning_pair_links}
    new_links = {item.pair: item for item in target_controller.planning_pair_links}
    old_admission = {item.choice: item for item in current_controller.admission}
    new_admission = {item.choice: item for item in target_controller.admission}

    retained_runtime = set(old_runtime) & set(new_runtime)
    added_runtime = set(new_runtime) - set(old_runtime)
    removed_runtime = set(old_runtime) - set(new_runtime)
    drifted_runtime = sorted(
        choice
        for choice in retained_runtime
        if old_runtime[choice] != new_runtime[choice]
    )
    observation_seed_drift = sorted(
        choice
        for choice in retained_runtime
        if old_runtime[choice].observation_seed
        != new_runtime[choice].observation_seed
    )
    if observation_seed_drift:
        raise HybridKernelProfileExpansionError(
            "observation seed drifted for retained entries: "
            f"{observation_seed_drift}"
        )
    changed_hidden_states = tuple(
        choice
        for choice in drifted_runtime
        if old_runtime[choice].hidden_state != new_runtime[choice].hidden_state
    )
    if drifted_runtime and not profile_refresh_required:
        raise HybridKernelProfileExpansionError(
            "runtime identity/state/seed drifted for retained entries: "
            f"{drifted_runtime}"
        )
    if any(
        choice.replica <= target_configuration.num_replicas
        for choice in removed_runtime
    ):
        raise HybridKernelProfileExpansionError(
            "runtime profile removal is not restricted to replicas above target"
        )
    if any(choice.replica <= existing_replica_count for choice in added_runtime):
        raise HybridKernelProfileExpansionError(
            "runtime profile additions are not restricted to missing ordinals"
        )

    retained_admission = set(old_admission) & set(new_admission)
    added_admission = set(new_admission) - set(old_admission)
    removed_admission = set(old_admission) - set(new_admission)
    if any(
        choice.replica <= target_configuration.num_replicas
        for choice in removed_admission
    ):
        raise HybridKernelProfileExpansionError(
            "admission removal is not restricted to replicas above target"
        )
    if any(choice.replica <= existing_replica_count for choice in added_admission):
        raise HybridKernelProfileExpansionError(
            "admission additions are not restricted to missing ordinals"
        )
    target_capacity = assigned_flow_capacity(target_configuration)
    unauthorized_admission = sorted(
        choice
        for choice in retained_admission
        if new_admission[choice].max_assigned_flows != target_capacity
    )
    if unauthorized_admission:
        raise HybridKernelProfileExpansionError(
            "retained admission changes do not match the deterministic formula: "
            f"{unauthorized_admission}"
        )

    retained_links = set(old_links) & set(new_links)
    added_links = set(new_links) - set(old_links)
    removed_links = set(old_links) - set(new_links)
    drifted_links = sorted(
        pair for pair in retained_links if old_links[pair] != new_links[pair]
    )
    if drifted_links:
        raise HybridKernelProfileExpansionError(
            f"planning links drifted for retained pairs: {drifted_links}"
        )
    if any(
        source.replica <= target_configuration.num_replicas
        and target.replica <= target_configuration.num_replicas
        for source, target in removed_links
    ):
        raise HybridKernelProfileExpansionError(
            "planning-link removal lacks a removed replica endpoint"
        )
    if any(
        source.replica <= existing_replica_count
        and target.replica <= existing_replica_count
        for source, target in added_links
    ):
        raise HybridKernelProfileExpansionError(
            "planning-link addition lacks a newly added replica endpoint"
        )

    return HybridKernelDynamicTopologyTransition(
        deployed_configuration=deployed_configuration,
        target_configuration=target_configuration,
        retained_runtime_identities=tuple(sorted(retained_runtime)),
        added_runtime_identities=tuple(sorted(added_runtime)),
        changed_runtime_identities=tuple(sorted(changed_hidden_states)),
        removed_runtime_identities=tuple(sorted(removed_runtime)),
        retained_admission_identities=tuple(sorted(retained_admission)),
        added_admission_identities=tuple(sorted(added_admission)),
        changed_admission_identities=tuple(
            sorted(
                choice
                for choice in retained_admission
                if old_admission[choice] != new_admission[choice]
            )
        ),
        removed_admission_identities=tuple(sorted(removed_admission)),
        retained_planning_pairs=tuple(sorted(retained_links)),
        added_planning_pairs=tuple(sorted(added_links)),
        removed_planning_pairs=tuple(sorted(removed_links)),
        profile_refresh_required=profile_refresh_required,
        deployed_profile_seed=deployed_profile_seed,
        target_profile_seed=profile_seed,
    )
