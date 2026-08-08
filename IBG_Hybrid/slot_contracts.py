"""Immutable contracts for one complete IBG-Hybrid simulation slot."""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite
from numbers import Integral
from typing import Mapping, Sequence

from .contracts import (
    GlobalLoadState,
    HybridConfiguration,
    ReplicaChoice,
    TwoStageAction,
)
from .phase0_contract import (
    HYBRID_FLOW_ORDER_SEED_SCHEME,
    HYBRID_POLICY_CONTRACT_VERSION,
    HybridActivationContext,
    HybridPolicyParameters,
    PipelinePath,
)
from .policy import CandidateAccounting


BeliefVector = tuple[float, float, float, float]
PairIdentity = tuple[ReplicaChoice, ReplicaChoice]


def _normalize_belief(values: Sequence[float]) -> BeliefVector:
    belief = tuple(float(value) for value in values)
    if len(belief) != 4:
        raise ValueError("belief must contain the four IBG states")
    if any(not isfinite(value) or value < 0 for value in belief):
        raise ValueError("belief entries must be finite and nonnegative")
    total = sum(belief)
    if total <= 0:
        raise ValueError("belief entries must have positive mass")
    return belief


@dataclass(frozen=True, order=True)
class HybridFlow:
    """One logical flow and its explicit policy priority."""

    flow_id: int
    high_priority: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.flow_id, bool) or not isinstance(self.flow_id, Integral):
            raise TypeError("flow_id must be an integer")
        if self.flow_id < 1:
            raise ValueError("flow_id must be positive")
        if not isinstance(self.high_priority, bool):
            raise TypeError("high_priority must be a boolean")


@dataclass(frozen=True)
class HybridReplica:
    """Known metadata, current belief, and optional simulation-only state.

    Kernel controller inputs leave ``hidden_state`` unset.  The field exists
    only for the in-process simulation adapter and is never part of the policy
    maps constructed by the slot runner.
    """

    choice: ReplicaChoice
    belief: BeliefVector
    ready: bool
    max_assigned_flows: int
    hidden_state: int | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "belief", _normalize_belief(self.belief))
        if not isinstance(self.ready, bool):
            raise TypeError("ready must be a boolean")
        if (
            isinstance(self.max_assigned_flows, bool)
            or not isinstance(self.max_assigned_flows, Integral)
        ):
            raise TypeError("max_assigned_flows must be an integer")
        if self.max_assigned_flows < 1:
            raise ValueError("max_assigned_flows must be positive")
        if self.hidden_state is not None:
            if (
                isinstance(self.hidden_state, bool)
                or not isinstance(self.hidden_state, Integral)
            ):
                raise TypeError("hidden_state must be an integer or None")
            if self.hidden_state not in (1, 2, 3, 4):
                raise ValueError("hidden_state must be one of 1, 2, 3, or 4")


@dataclass(frozen=True, order=True)
class HybridPairValue:
    """One directed selected-pair latency value in milliseconds."""

    source: ReplicaChoice
    target: ReplicaChoice
    latency_ms: float

    def __post_init__(self) -> None:
        if self.source.stage >= self.target.stage:
            raise ValueError("pair values must follow increasing selected stages")
        value = float(self.latency_ms)
        if not isfinite(value) or value < 0:
            raise ValueError("pair latency must be finite and nonnegative")
        object.__setattr__(self, "latency_ms", value)

    @property
    def pair(self) -> PairIdentity:
        return self.source, self.target


@dataclass(frozen=True)
class HybridSlotInput:
    """Complete immutable input for one Hybrid placement/learning slot."""

    configuration: HybridConfiguration
    parameters: HybridPolicyParameters
    root_seed: int
    slot_id: int
    flows: tuple[HybridFlow, ...]
    replicas: tuple[HybridReplica, ...]
    planning_pair_links: tuple[HybridPairValue, ...]
    simulated_pair_outcomes: tuple[HybridPairValue, ...]
    initial_loads: GlobalLoadState
    contract_version: str = HYBRID_POLICY_CONTRACT_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "flows", tuple(self.flows))
        object.__setattr__(self, "replicas", tuple(self.replicas))
        object.__setattr__(
            self,
            "planning_pair_links",
            tuple(self.planning_pair_links),
        )
        object.__setattr__(
            self,
            "simulated_pair_outcomes",
            tuple(self.simulated_pair_outcomes),
        )
        if not isinstance(self.configuration, HybridConfiguration):
            raise TypeError("configuration must be HybridConfiguration")
        if not isinstance(self.parameters, HybridPolicyParameters):
            raise TypeError("parameters must be HybridPolicyParameters")
        for name in ("root_seed", "slot_id"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, Integral):
                raise TypeError(f"{name} must be an integer")
        if self.root_seed < 0:
            raise ValueError("root_seed must not be negative")
        if self.slot_id < 1:
            raise ValueError("slot_id must be positive")
        if self.contract_version != HYBRID_POLICY_CONTRACT_VERSION:
            raise ValueError("unexpected Hybrid policy contract version")
        if len(self.flows) != self.configuration.num_flows:
            raise ValueError("flows must match the configured flow count")
        if len({flow.flow_id for flow in self.flows}) != len(self.flows):
            raise ValueError("flow IDs must be unique")
        if len({replica.choice for replica in self.replicas}) != len(self.replicas):
            raise ValueError("replica identities must be unique")
        for replica in self.replicas:
            if replica.choice.stage > self.configuration.num_stages:
                raise ValueError("replica stage exceeds configuration")
            if replica.choice.replica > self.configuration.num_replicas:
                raise ValueError("replica ID exceeds configuration")
        self.initial_loads.validate_for(self.configuration)
        if self.initial_loads.total_assignments != 0:
            raise ValueError(
                "a complete Hybrid slot must begin from an empty global load state"
            )
        self._validate_unique_pairs(
            self.planning_pair_links,
            "planning pair-link",
        )
        self._validate_unique_pairs(
            self.simulated_pair_outcomes,
            "simulated pair-outcome",
        )

    @staticmethod
    def _validate_unique_pairs(
        values: tuple[HybridPairValue, ...],
        label: str,
    ) -> None:
        if len({value.pair for value in values}) != len(values):
            raise ValueError(f"{label} identities must be unique")

    @property
    def flow_by_id(self) -> Mapping[int, HybridFlow]:
        return {flow.flow_id: flow for flow in self.flows}

    @property
    def replica_by_choice(self) -> Mapping[ReplicaChoice, HybridReplica]:
        return {replica.choice: replica for replica in self.replicas}

    @property
    def planning_pair_link_costs(self) -> Mapping[PairIdentity, float]:
        return {value.pair: value.latency_ms for value in self.planning_pair_links}

    @property
    def simulated_pair_latency_ms(self) -> Mapping[PairIdentity, float]:
        return {
            value.pair: value.latency_ms
            for value in self.simulated_pair_outcomes
        }

    @property
    def beliefs(self) -> Mapping[ReplicaChoice, BeliefVector]:
        return {
            replica.choice: replica.belief
            for replica in self.replicas
        }

    def with_beliefs(
        self,
        beliefs: Mapping[ReplicaChoice, Sequence[float]],
        *,
        slot_id: int | None = None,
    ) -> HybridSlotInput:
        """Return the next immutable slot input with retained learned beliefs."""

        expected = {replica.choice for replica in self.replicas}
        if set(beliefs) != expected:
            raise ValueError("replacement beliefs must cover every replica exactly")
        updated = tuple(
            replace(replica, belief=_normalize_belief(beliefs[replica.choice]))
            for replica in self.replicas
        )
        return replace(
            self,
            replicas=updated,
            slot_id=self.slot_id + 1 if slot_id is None else slot_id,
            initial_loads=GlobalLoadState.empty(self.configuration),
        )


@dataclass(frozen=True)
class HybridSelectedObservation:
    """One selected physical sample and its separate noisy learning signal."""

    flow_id: int
    choice: ReplicaChoice
    assigned_load: int
    physical_processing_latency_ms: float
    observation_jitter_ms: float
    learning_signal_ms: float
    likelihood: BeliefVector
    estimated_state: int
    physical_seed: int
    observation_seed: int

    def __post_init__(self) -> None:
        if self.flow_id < 1:
            raise ValueError("observation flow_id must be positive")
        if self.assigned_load < 1:
            raise ValueError("assigned_load must be positive")
        for name in (
            "physical_processing_latency_ms",
            "observation_jitter_ms",
            "learning_signal_ms",
        ):
            value = float(getattr(self, name))
            if not isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
            object.__setattr__(self, name, value)
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
        object.__setattr__(self, "likelihood", _normalize_belief(self.likelihood))
        if self.estimated_state not in (1, 2, 3, 4):
            raise ValueError("estimated_state must be one of 1, 2, 3, or 4")
        if self.physical_seed < 0 or self.observation_seed < 0:
            raise ValueError("observation seeds must not be negative")

    # Exact's unchanged selected-only learner consumes these attribute names.
    @property
    def stage(self) -> int:
        return self.choice.stage

    @property
    def replica_id(self) -> int:
        return self.choice.replica

    @property
    def congestion(self) -> int:
        return self.assigned_load

    @property
    def signal(self) -> float:
        return self.learning_signal_ms

    @property
    def measured_latency_ms(self) -> float:
        return self.physical_processing_latency_ms


@dataclass(frozen=True)
class HybridMeasuredPair:
    """One simulated/measured pair outcome, separate from planning metadata."""

    flow_id: int
    source: ReplicaChoice
    target: ReplicaChoice
    latency_ms: float

    def __post_init__(self) -> None:
        if self.flow_id < 1:
            raise ValueError("pair flow_id must be positive")
        if self.source.stage >= self.target.stage:
            raise ValueError("measured pair must follow selected stage order")
        value = float(self.latency_ms)
        if not isfinite(value) or value < 0:
            raise ValueError("measured pair latency must be finite and nonnegative")
        object.__setattr__(self, "latency_ms", value)


@dataclass(frozen=True)
class HybridSimulationResult:
    observations: tuple[HybridSelectedObservation, ...]
    measured_pairs: tuple[HybridMeasuredPair, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "observations", tuple(self.observations))
        object.__setattr__(self, "measured_pairs", tuple(self.measured_pairs))


@dataclass(frozen=True)
class HybridPlacement:
    """One real focal commit and its complete activation/policy provenance."""

    decision_position: int
    flow: HybridFlow
    activation: HybridActivationContext
    path: PipelinePath
    activation_reason: str
    action: TwoStageAction
    skipped_stage: int
    state_before: GlobalLoadState
    state_after: GlobalLoadState
    objective_value: float
    candidate_accounting: CandidateAccounting
    policy_detail: object

    def __post_init__(self) -> None:
        if self.decision_position < 1:
            raise ValueError("decision_position must be positive")
        if not isinstance(self.path, PipelinePath):
            raise TypeError("path must be PipelinePath")
        if not self.activation_reason:
            raise ValueError("activation_reason must not be empty")
        if self.skipped_stage in self.action.stages:
            raise ValueError("skipped stage cannot be present in the action")
        if not isfinite(float(self.objective_value)):
            raise ValueError("objective value must be finite")


@dataclass(frozen=True)
class HybridSlotMetrics:
    aggregate_expected_utility: float
    aggregate_expected_utility_per_flow: tuple[tuple[int, float], ...]
    physical_realized_utility: float
    physical_realized_utility_per_flow: tuple[tuple[int, float], ...]
    physical_processing_latency_ms_per_flow: tuple[tuple[int, float], ...]
    measured_pair_latency_ms_per_flow: tuple[tuple[int, float], ...]
    raw_end_to_end_latency_ms_per_flow: tuple[tuple[int, float], ...]
    raw_end_to_end_reference_utility: float
    raw_end_to_end_reference_utility_per_flow: tuple[tuple[int, float], ...]
    sla_latency_threshold_ms: float
    physical_only_sla_violations: int
    jain_fairness: float
    elapsed_seconds: float
    maximum_belief_change: float
    equilibrium: bool


@dataclass(frozen=True)
class HybridSlotResult:
    contract_version: str
    configuration: HybridConfiguration
    parameters: HybridPolicyParameters
    root_seed: int
    slot_id: int
    flow_order_seed_scheme: str
    flow_order_seed: int
    flow_order: tuple[int, ...]
    placements: tuple[HybridPlacement, ...]
    final_loads: GlobalLoadState
    observations: tuple[HybridSelectedObservation, ...]
    measured_pairs: tuple[HybridMeasuredPair, ...]
    beliefs_before: tuple[tuple[ReplicaChoice, BeliefVector], ...]
    beliefs_after: tuple[tuple[ReplicaChoice, BeliefVector], ...]
    metrics: HybridSlotMetrics

    def __post_init__(self) -> None:
        object.__setattr__(self, "flow_order", tuple(self.flow_order))
        object.__setattr__(self, "placements", tuple(self.placements))
        object.__setattr__(self, "observations", tuple(self.observations))
        object.__setattr__(self, "measured_pairs", tuple(self.measured_pairs))
        object.__setattr__(self, "beliefs_before", tuple(self.beliefs_before))
        object.__setattr__(self, "beliefs_after", tuple(self.beliefs_after))
        if self.contract_version != HYBRID_POLICY_CONTRACT_VERSION:
            raise ValueError("unexpected Hybrid policy contract version")
        if self.flow_order_seed_scheme != HYBRID_FLOW_ORDER_SEED_SCHEME:
            raise ValueError("unexpected Hybrid flow-order seed scheme")
        if self.slot_id < 1:
            raise ValueError("slot_id must be positive")

    @property
    def beliefs_after_mapping(self) -> Mapping[ReplicaChoice, BeliefVector]:
        return dict(self.beliefs_after)
