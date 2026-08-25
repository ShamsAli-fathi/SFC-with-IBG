"""Immutable contracts for one pure Greedy placement and learning slot."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from hashlib import blake2b
from math import isfinite
from numbers import Integral
from typing import Mapping, Sequence

from .contracts import (
    DecisionResult,
    GlobalLoadState,
    GreedyConfiguration,
    PolicyResult,
    PublicReplicaState,
    ReplicaIdentity,
)


GREEDY_SLOT_CONTRACT_VERSION = "pure-greedy-slot-v1"
GREEDY_PROFILE_FINGERPRINT_VERSION = "greedy-profile-map-blake2b-v1"
GREEDY_EXPLICIT_FLOW_ORDER_SCHEME = "explicit-flow-order-v1"
GREEDY_EXPERIMENT_STOP_EQUILIBRIUM = "equilibrium"
GREEDY_EXPERIMENT_STOP_MAX_ITERATIONS = "max-iterations"

BeliefVector = tuple[float, float, float, float]


def _integer(name: str, value: int, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise TypeError(f"{name} must be an integer")
    if value < minimum:
        comparison = "positive" if minimum == 1 else "not be negative"
        raise ValueError(f"{name} must {comparison}")
    return int(value)


def _finite(name: str, value: float, *, minimum: float | None = None) -> float:
    result = float(value)
    if not isfinite(result) or (minimum is not None and result < minimum):
        suffix = "finite" if minimum is None else f"finite and at least {minimum}"
        raise ValueError(f"{name} must be {suffix}")
    return result


def _belief(values: Sequence[float]) -> BeliefVector:
    result = tuple(float(value) for value in values)
    if len(result) != 4:
        raise ValueError("belief must contain the four IBG states")
    if any(not isfinite(value) or value < 0 for value in result):
        raise ValueError("belief entries must be finite and nonnegative")
    if sum(result) <= 0:
        raise ValueError("belief entries must have positive mass")
    return result


@dataclass(frozen=True, order=True)
class GreedyReplicaProfile:
    """Simulation-only environment values kept outside the policy input."""

    identity: ReplicaIdentity
    hidden_state: int
    observation_seed: int

    def __post_init__(self) -> None:
        if not isinstance(self.identity, ReplicaIdentity):
            raise TypeError("identity must be ReplicaIdentity")
        state = _integer("hidden_state", self.hidden_state, minimum=1)
        if state not in (1, 2, 3, 4):
            raise ValueError("hidden_state must be one of 1, 2, 3, or 4")
        object.__setattr__(self, "hidden_state", state)
        object.__setattr__(
            self,
            "observation_seed",
            _integer("observation_seed", self.observation_seed, minimum=0),
        )


def materialized_profile_fingerprint(
    profiles: Sequence[GreedyReplicaProfile],
) -> str:
    """Fingerprint the identity-aligned hidden-state/observation-seed map."""

    ordered = tuple(sorted(profiles, key=lambda profile: profile.identity))
    payload = "|".join(
        (
            GREEDY_PROFILE_FINGERPRINT_VERSION,
            *(
                f"{profile.identity.stage}:{profile.identity.replica}:"
                f"{profile.hidden_state}:{profile.observation_seed}"
                for profile in ordered
            ),
        )
    ).encode("ascii")
    return blake2b(payload, digest_size=16).hexdigest()


@dataclass(frozen=True, order=True)
class GreedyPairLatency:
    """One available raw selected-pair latency outcome in milliseconds."""

    source: ReplicaIdentity
    target: ReplicaIdentity
    latency_ms: float

    def __post_init__(self) -> None:
        if self.source.stage >= self.target.stage:
            raise ValueError("pair latency must follow increasing selected stages")
        object.__setattr__(
            self,
            "latency_ms",
            _finite("pair latency", self.latency_ms, minimum=0.0),
        )

    @property
    def pair(self) -> tuple[ReplicaIdentity, ReplicaIdentity]:
        return self.source, self.target


@dataclass(frozen=True)
class GreedySlotInput:
    """Complete immutable public/environment input for one pure slot."""

    configuration: GreedyConfiguration
    experiment_id: int
    slot_id: int
    root_seed: int
    profile_seed: int
    public_replicas: tuple[PublicReplicaState, ...]
    replica_profiles: tuple[GreedyReplicaProfile, ...]
    measured_pair_latencies: tuple[GreedyPairLatency, ...]
    flow_order: tuple[int, ...] | None = None
    profile_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.configuration, GreedyConfiguration):
            raise TypeError("configuration must be GreedyConfiguration")
        for name, minimum in (
            ("experiment_id", 1),
            ("slot_id", 1),
            ("root_seed", 0),
            ("profile_seed", 0),
        ):
            object.__setattr__(
                self,
                name,
                _integer(name, getattr(self, name), minimum=minimum),
            )
        public = tuple(self.public_replicas)
        profiles = tuple(self.replica_profiles)
        pairs = tuple(self.measured_pair_latencies)
        object.__setattr__(self, "public_replicas", public)
        object.__setattr__(self, "replica_profiles", profiles)
        object.__setattr__(self, "measured_pair_latencies", pairs)

        expected = tuple(
            ReplicaIdentity(stage, replica)
            for stage in self.configuration.stages
            for replica in self.configuration.replica_ids
        )
        if not all(type(state) is PublicReplicaState for state in public):
            raise TypeError("public_replicas must contain PublicReplicaState values")
        if tuple(sorted(state.identity for state in public)) != expected:
            raise ValueError("public replicas must cover every configured identity exactly")
        for state in public:
            state.validate_for(self.configuration)
        if not all(type(profile) is GreedyReplicaProfile for profile in profiles):
            raise TypeError("replica_profiles must contain GreedyReplicaProfile values")
        if tuple(sorted(profile.identity for profile in profiles)) != expected:
            raise ValueError("replica profiles must cover every configured identity exactly")
        for profile in profiles:
            profile.identity.validate_for(self.configuration)
        if len({pair.pair for pair in pairs}) != len(pairs):
            raise ValueError("measured pair identities must be unique")
        for pair in pairs:
            pair.source.validate_for(self.configuration)
            pair.target.validate_for(self.configuration)

        if self.flow_order is not None:
            order = tuple(self.flow_order)
            object.__setattr__(self, "flow_order", order)
            expected_flows = set(range(1, self.configuration.num_flows + 1))
            if len(order) != self.configuration.num_flows or set(order) != expected_flows:
                raise ValueError("flow_order must be a permutation of configured flows 1..N")
            if any(isinstance(flow, bool) or not isinstance(flow, Integral) for flow in order):
                raise TypeError("flow_order values must be integers")

        object.__setattr__(
            self,
            "profile_fingerprint",
            materialized_profile_fingerprint(profiles),
        )

    @property
    def public_replica_by_identity(self) -> Mapping[ReplicaIdentity, PublicReplicaState]:
        return {state.identity: state for state in self.public_replicas}

    @property
    def replica_profile_by_identity(self) -> Mapping[ReplicaIdentity, GreedyReplicaProfile]:
        return {profile.identity: profile for profile in self.replica_profiles}

    @property
    def measured_pair_latency_ms(
        self,
    ) -> Mapping[tuple[ReplicaIdentity, ReplicaIdentity], float]:
        return {pair.pair: pair.latency_ms for pair in self.measured_pair_latencies}

    @property
    def beliefs(self) -> Mapping[ReplicaIdentity, BeliefVector]:
        return {state.identity: state.belief for state in self.public_replicas}

    def with_beliefs(
        self,
        beliefs: Mapping[ReplicaIdentity, Sequence[float]],
        *,
        slot_id: int | None = None,
    ) -> GreedySlotInput:
        expected = {state.identity for state in self.public_replicas}
        if set(beliefs) != expected:
            raise ValueError("replacement beliefs must cover every replica exactly")
        public = tuple(
            replace(state, belief=_belief(beliefs[state.identity]))
            for state in self.public_replicas
        )
        return replace(
            self,
            public_replicas=public,
            slot_id=self.slot_id + 1 if slot_id is None else slot_id,
        )


@dataclass(frozen=True)
class GreedySelectedObservation:
    flow_id: int
    identity: ReplicaIdentity
    assigned_load: int
    physical_processing_latency_ms: float
    observation_jitter_ms: float
    learning_signal_ms: float
    likelihood: BeliefVector
    estimated_state: int
    physical_seed: int
    observation_seed: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "flow_id", _integer("flow_id", self.flow_id, minimum=1))
        if not isinstance(self.identity, ReplicaIdentity):
            raise TypeError("identity must be ReplicaIdentity")
        object.__setattr__(
            self,
            "assigned_load",
            _integer("assigned_load", self.assigned_load, minimum=1),
        )
        for name, minimum in (
            ("physical_processing_latency_ms", 0.0),
            ("observation_jitter_ms", 0.0),
            ("learning_signal_ms", 0.0),
        ):
            object.__setattr__(self, name, _finite(name, getattr(self, name), minimum=minimum))
        if self.physical_processing_latency_ms <= 0:
            raise ValueError("physical processing latency must be positive")
        if abs(
            self.learning_signal_ms
            - self.physical_processing_latency_ms
            - self.observation_jitter_ms
        ) > 1e-9:
            raise ValueError(
                "learning signal must equal physical latency plus observation jitter"
            )
        object.__setattr__(self, "likelihood", _belief(self.likelihood))
        state = _integer("estimated_state", self.estimated_state, minimum=1)
        if state not in (1, 2, 3, 4):
            raise ValueError("estimated_state must be one of 1, 2, 3, or 4")
        object.__setattr__(self, "estimated_state", state)
        for name in ("physical_seed", "observation_seed"):
            object.__setattr__(
                self,
                name,
                _integer(name, getattr(self, name), minimum=0),
            )

    # Attribute aliases used by the policy-neutral selected-only learner.
    @property
    def stage(self) -> int:
        return self.identity.stage

    @property
    def replica_id(self) -> int:
        return self.identity.replica

    @property
    def congestion(self) -> int:
        return self.assigned_load

    @property
    def signal(self) -> float:
        return self.learning_signal_ms


@dataclass(frozen=True)
class GreedyMeasuredPair:
    flow_id: int
    source: ReplicaIdentity
    target: ReplicaIdentity
    latency_ms: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "flow_id", _integer("flow_id", self.flow_id, minimum=1))
        if not isinstance(self.source, ReplicaIdentity) or not isinstance(
            self.target,
            ReplicaIdentity,
        ):
            raise TypeError("measured pair endpoints must be ReplicaIdentity values")
        if self.source.stage >= self.target.stage:
            raise ValueError("measured pair must follow selected stage order")
        object.__setattr__(
            self,
            "latency_ms",
            _finite("measured pair latency", self.latency_ms, minimum=0.0),
        )


@dataclass(frozen=True)
class GreedySimulationResult:
    observations: tuple[GreedySelectedObservation, ...]
    measured_pairs: tuple[GreedyMeasuredPair, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "observations", tuple(self.observations))
        object.__setattr__(self, "measured_pairs", tuple(self.measured_pairs))


@dataclass(frozen=True)
class GreedyPlacement:
    decision_position: int
    decision: DecisionResult

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "decision_position",
            _integer("decision_position", self.decision_position, minimum=1),
        )
        if not isinstance(self.decision, DecisionResult):
            raise TypeError("decision must be DecisionResult")

    @property
    def flow_id(self) -> int:
        return self.decision.flow_id

    @property
    def action(self):
        return self.decision.action

    @property
    def bypassed_stages(self) -> tuple[int, ...]:
        return self.decision.bypassed_stages


@dataclass(frozen=True)
class GreedyBeliefSnapshot:
    entries: tuple[tuple[ReplicaIdentity, BeliefVector], ...]

    def __post_init__(self) -> None:
        entries = tuple((identity, _belief(belief)) for identity, belief in self.entries)
        object.__setattr__(self, "entries", entries)
        identities = tuple(identity for identity, _belief_value in entries)
        if identities != tuple(sorted(set(identities))):
            raise ValueError("belief snapshot must use unique canonical identities")

    @classmethod
    def from_mapping(
        cls,
        beliefs: Mapping[ReplicaIdentity, Sequence[float]],
    ) -> GreedyBeliefSnapshot:
        return cls(
            tuple(
                sorted(
                    (identity, _belief(value))
                    for identity, value in beliefs.items()
                )
            )
        )

    @property
    def mapping(self) -> Mapping[ReplicaIdentity, BeliefVector]:
        return dict(self.entries)


@dataclass(frozen=True)
class GreedySlotMetrics:
    predicted_aggregate_utility: float
    predicted_utility_per_flow: tuple[tuple[int, float], ...]
    physical_realized_aggregate_utility: float
    physical_realized_utility_per_flow: tuple[tuple[int, float], ...]
    physical_processing_latency_ms_per_flow: tuple[tuple[int, float], ...]
    measured_pair_latency_ms_per_flow: tuple[tuple[int, float], ...]
    raw_end_to_end_latency_ms_per_flow: tuple[tuple[int, float], ...]
    raw_end_to_end_reference_utility: float
    raw_end_to_end_reference_utility_per_flow: tuple[tuple[int, float], ...]
    sla_latency_threshold_ms: float
    end_to_end_sla_violations: int
    end_to_end_sla_excess_ms: float
    jain_fairness: float
    maximum_belief_change: float
    equilibrium: bool


@dataclass(frozen=True)
class GreedySlotTimings:
    placement_seconds: float
    feedback_validation_seconds: float
    total_seconds: float

    def __post_init__(self) -> None:
        for name in (
            "placement_seconds",
            "feedback_validation_seconds",
            "total_seconds",
        ):
            object.__setattr__(self, name, _finite(name, getattr(self, name), minimum=0.0))
        if abs(
            self.total_seconds
            - self.placement_seconds
            - self.feedback_validation_seconds
        ) > 1e-9:
            raise ValueError("total timing must equal placement plus feedback/validation")


@dataclass(frozen=True)
class GreedySlotResult:
    contract_version: str
    configuration: GreedyConfiguration
    experiment_id: int
    slot_id: int
    root_seed: int
    profile_seed: int
    profile_fingerprint: str
    flow_order_seed_scheme: str
    flow_order_seed: int | None
    flow_order: tuple[int, ...]
    policy_result: PolicyResult
    placements: tuple[GreedyPlacement, ...]
    observations: tuple[GreedySelectedObservation, ...]
    measured_pairs: tuple[GreedyMeasuredPair, ...]
    beliefs_before: GreedyBeliefSnapshot
    beliefs_after: GreedyBeliefSnapshot
    metrics: GreedySlotMetrics
    timings: GreedySlotTimings

    def __post_init__(self) -> None:
        if self.contract_version != GREEDY_SLOT_CONTRACT_VERSION:
            raise ValueError("unexpected Greedy slot contract version")
        order = tuple(self.flow_order)
        placements = tuple(self.placements)
        observations = tuple(self.observations)
        pairs = tuple(self.measured_pairs)
        object.__setattr__(self, "flow_order", order)
        object.__setattr__(self, "placements", placements)
        object.__setattr__(self, "observations", observations)
        object.__setattr__(self, "measured_pairs", pairs)
        if self.policy_result.flow_order != order:
            raise ValueError("slot flow order must equal the unchanged policy flow order")
        if tuple(placement.decision for placement in placements) != self.policy_result.decisions:
            raise ValueError("placements must preserve the Phase 1 decision sequence")
        if len(placements) != self.configuration.num_flows:
            raise ValueError("a complete slot must contain N placements")
        expected_observations = {
            (placement.flow_id, identity)
            for placement in placements
            for identity in placement.action.choices
        }
        if len(observations) != 2 * self.configuration.num_flows or {
            (observation.flow_id, observation.identity) for observation in observations
        } != expected_observations:
            raise ValueError("slot observations must cover exactly the selected hops")
        expected_pairs = {
            (placement.flow_id, placement.action.choices)
            for placement in placements
        }
        if len(pairs) != self.configuration.num_flows or {
            (pair.flow_id, (pair.source, pair.target)) for pair in pairs
        } != expected_pairs:
            raise ValueError("slot pair records must cover every selected pair exactly")

    @property
    def final_loads(self) -> GlobalLoadState:
        return self.policy_result.final_loads


@dataclass(frozen=True)
class GreedyExperimentResult:
    experiment_id: int
    max_iterations: int
    slots: tuple[GreedySlotResult, ...]
    stop_reason: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "max_iterations",
            _integer("max_iterations", self.max_iterations, minimum=1),
        )
        slots = tuple(self.slots)
        object.__setattr__(self, "slots", slots)
        if not slots or len(slots) > self.max_iterations:
            raise ValueError("experiment must contain one through max_iterations slots")
        if any(slot.experiment_id != self.experiment_id for slot in slots):
            raise ValueError("every slot must belong to the one experiment")
        if self.stop_reason == GREEDY_EXPERIMENT_STOP_EQUILIBRIUM:
            if not slots[-1].metrics.equilibrium:
                raise ValueError("equilibrium stop requires an equilibrium final slot")
        elif self.stop_reason == GREEDY_EXPERIMENT_STOP_MAX_ITERATIONS:
            if len(slots) != self.max_iterations or slots[-1].metrics.equilibrium:
                raise ValueError("max-iteration stop requires the exact non-equilibrium limit")
        else:
            raise ValueError("unknown experiment stop reason")

    @property
    def iterations_completed(self) -> int:
        return len(self.slots)

    @property
    def reached_equilibrium(self) -> bool:
        return self.stop_reason == GREEDY_EXPERIMENT_STOP_EQUILIBRIUM
