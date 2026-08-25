"""Deterministic Greedy runtime-profile materialization and transition checks.

This module is deliberately pure.  It owns the processor-private environment
allocation used by the Phase 5 launcher, but performs no file, subprocess,
Docker, kind, or Kubernetes operation.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import blake2b
from numbers import Integral
import re

from .contracts import GreedyConfiguration, ReplicaIdentity
from .kernel_runtime_profiles import GreedyKernelRuntimeProfileDocument
from .slot_contracts import GreedyReplicaProfile


GREEDY_PROFILE_RECONCILIATION_VERSION = "greedy-kernel-profile-reconciliation-v1"
# The state allocator and its domain separator intentionally match the active
# Hybrid environment allocator.  Greedy owns this implementation and imports no
# Hybrid namespace.
GREEDY_MATCHED_PROFILE_ALLOCATION_VERSION = (
    "ibg-hybrid-profile-state-allocation-v1"
)
GREEDY_PROFILE_STATE_ORDER = (4, 3, 2, 1)
GREEDY_PROFILE_STATE_WEIGHT_UNITS = (3, 3, 2, 2)
GREEDY_PROFILE_STATE_WEIGHT_TOTAL = sum(GREEDY_PROFILE_STATE_WEIGHT_UNITS)


class GreedyProfileReconciliationError(ValueError):
    """The deployed profile map is malformed, drifted, or unsafe to change."""


def _integer(name: str, value: int, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise TypeError(f"{name} must be an integer")
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return int(value)


def profile_source_identity(profile_seed: int) -> str:
    seed = _integer("profile_seed", profile_seed, minimum=0)
    return (
        f"{GREEDY_PROFILE_RECONCILIATION_VERSION}:"
        f"{GREEDY_MATCHED_PROFILE_ALLOCATION_VERSION}:profile-seed={seed}"
    )


def profile_seed_from_source_identity(source_identity: str) -> int:
    if not isinstance(source_identity, str) or not source_identity:
        raise GreedyProfileReconciliationError(
            "runtime profile has no seeded source identity"
        )
    match = re.fullmatch(
        re.escape(GREEDY_PROFILE_RECONCILIATION_VERSION)
        + ":"
        + re.escape(GREEDY_MATCHED_PROFILE_ALLOCATION_VERSION)
        + r":profile-seed=(\d+)",
        source_identity,
    )
    if match is None:
        raise GreedyProfileReconciliationError(
            "runtime profile has malformed seeded-allocation provenance"
        )
    return _integer("profile_seed", int(match.group(1)), minimum=0)


def seeded_hidden_state_sequence(
    *,
    stage: int,
    replica_count: int,
    profile_seed: int,
) -> tuple[int, ...]:
    """Return the active Hybrid-compatible append-only state sequence.

    Independent ten-replica strata use exact 3/3/2/2 state quotas.  Prefixes
    stay within one assignment of their ideal quota.  All ranking is local and
    BLAKE2b-keyed; neither Python nor NumPy global RNG state is consumed.
    """

    resolved_stage = _integer("stage", stage, minimum=1)
    count = _integer("replica_count", replica_count, minimum=1)
    seed = _integer("profile_seed", profile_seed, minimum=0)
    weights = dict(
        zip(GREEDY_PROFILE_STATE_ORDER, GREEDY_PROFILE_STATE_WEIGHT_UNITS)
    )

    def ranked_states(block: int, position: int) -> tuple[int, ...]:
        def rank(state: int) -> int:
            payload = (
                f"{GREEDY_MATCHED_PROFILE_ALLOCATION_VERSION}|{seed}|"
                f"{resolved_stage}|{block}|{position}|{state}"
            ).encode("ascii")
            return int.from_bytes(blake2b(payload, digest_size=16).digest(), "big")

        return tuple(sorted(GREEDY_PROFILE_STATE_ORDER, key=rank, reverse=True))

    def allocate_block(block: int) -> tuple[int, ...]:
        assigned = {state: 0 for state in GREEDY_PROFILE_STATE_ORDER}
        selected: list[int] = []

        def fill(position: int) -> bool:
            if position > GREEDY_PROFILE_STATE_WEIGHT_TOTAL:
                return all(
                    assigned[state] == weights[state]
                    for state in GREEDY_PROFILE_STATE_ORDER
                )
            for state in ranked_states(block, position):
                if assigned[state] >= weights[state]:
                    continue
                assigned[state] += 1
                within_prefix_bound = all(
                    abs(
                        assigned[candidate] * GREEDY_PROFILE_STATE_WEIGHT_TOTAL
                        - position * weights[candidate]
                    )
                    <= GREEDY_PROFILE_STATE_WEIGHT_TOTAL
                    for candidate in GREEDY_PROFILE_STATE_ORDER
                )
                if within_prefix_bound:
                    selected.append(state)
                    if fill(position + 1):
                        return True
                    selected.pop()
                assigned[state] -= 1
            return False

        if not fill(1):
            raise GreedyProfileReconciliationError(
                "seeded state allocator could not satisfy the quota boundary"
            )
        return tuple(selected)

    result: list[int] = []
    block = 0
    while len(result) < count:
        result.extend(allocate_block(block))
        block += 1
    return tuple(result[:count])


def _extension_observation_seed(stage: int, replica: int) -> int:
    total = stage + replica
    pairing = (total * (total + 1) // 2) + replica
    return 1_000_000_000 + pairing


def matched_observation_seed(identity: ReplicaIdentity) -> int:
    """Return the identity-stable observation seed used by matched profiles.

    Hybrid's active canonical three-stage/two-replica prefix uses 4101--4302.
    Identities beyond that template use its Cantor-pair extension unchanged.
    """

    if not isinstance(identity, ReplicaIdentity):
        raise TypeError("identity must be ReplicaIdentity")
    if identity.stage <= 3 and identity.replica <= 2:
        return 4_000 + identity.stage * 100 + identity.replica
    return _extension_observation_seed(identity.stage, identity.replica)


def materialize_runtime_profiles(
    configuration: GreedyConfiguration,
    *,
    profile_seed: int,
) -> GreedyKernelRuntimeProfileDocument:
    if not isinstance(configuration, GreedyConfiguration):
        raise TypeError("configuration must be GreedyConfiguration")
    seed = _integer("profile_seed", profile_seed, minimum=0)
    profiles = []
    for stage in configuration.stages:
        states = seeded_hidden_state_sequence(
            stage=stage,
            replica_count=configuration.num_replicas,
            profile_seed=seed,
        )
        for replica, hidden_state in enumerate(states, start=1):
            identity = ReplicaIdentity(stage, replica)
            profiles.append(
                GreedyReplicaProfile(
                    identity=identity,
                    hidden_state=hidden_state,
                    observation_seed=matched_observation_seed(identity),
                )
            )
    return GreedyKernelRuntimeProfileDocument(
        configuration=configuration,
        profiles=tuple(profiles),
        source_identity=profile_source_identity(seed),
    )


@dataclass(frozen=True)
class GreedyProfileTransition:
    deployed_configuration: GreedyConfiguration
    target_configuration: GreedyConfiguration
    retained_identities: tuple[ReplicaIdentity, ...]
    added_identities: tuple[ReplicaIdentity, ...]
    removed_identities: tuple[ReplicaIdentity, ...]
    fingerprint_changed: bool
    contract_version: str = GREEDY_PROFILE_RECONCILIATION_VERSION

    def __post_init__(self) -> None:
        if self.contract_version != GREEDY_PROFILE_RECONCILIATION_VERSION:
            raise GreedyProfileReconciliationError(
                "unexpected Greedy profile-transition version"
            )


def validate_profile_transition(
    *,
    deployed: GreedyKernelRuntimeProfileDocument,
    proposed: GreedyKernelRuntimeProfileDocument,
    profile_seed: int,
) -> GreedyProfileTransition:
    """Require deterministic documents and exact retained-prefix equality."""

    if not isinstance(deployed, GreedyKernelRuntimeProfileDocument):
        raise TypeError("deployed must be GreedyKernelRuntimeProfileDocument")
    if not isinstance(proposed, GreedyKernelRuntimeProfileDocument):
        raise TypeError("proposed must be GreedyKernelRuntimeProfileDocument")
    seed = _integer("profile_seed", profile_seed, minimum=0)
    deployed_seed = profile_seed_from_source_identity(deployed.source_identity)
    expected_deployed = materialize_runtime_profiles(
        deployed.configuration,
        profile_seed=deployed_seed,
    )
    if deployed != expected_deployed:
        raise GreedyProfileReconciliationError(
            "deployed runtime profile drifted from the versioned rule"
        )
    expected_target = materialize_runtime_profiles(
        proposed.configuration,
        profile_seed=seed,
    )
    if proposed != expected_target:
        raise GreedyProfileReconciliationError(
            "proposed runtime profile is not the deterministic target document"
        )
    if deployed_seed != seed:
        raise GreedyProfileReconciliationError(
            "retained runtime profiles cannot change profile seed"
        )

    old = deployed.profile_by_identity()
    new = proposed.profile_by_identity()
    retained = tuple(sorted(set(old) & set(new)))
    drifted = tuple(identity for identity in retained if old[identity] != new[identity])
    if drifted:
        raise GreedyProfileReconciliationError(
            f"retained runtime profile drift: {drifted}"
        )
    return GreedyProfileTransition(
        deployed_configuration=deployed.configuration,
        target_configuration=proposed.configuration,
        retained_identities=retained,
        added_identities=tuple(sorted(set(new) - set(old))),
        removed_identities=tuple(sorted(set(old) - set(new))),
        fingerprint_changed=deployed.fingerprint != proposed.fingerprint,
    )
