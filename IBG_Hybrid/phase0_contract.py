"""Final Phase 0 policy contract for the future IBG-Hybrid implementation.

This module fixes meanings and deterministic fixtures. It does not implement
the production pruning/lookahead/Monte Carlo policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import blake2b
from math import comb, isfinite, log
from numbers import Integral
from typing import Callable, Mapping, Sequence

from .contracts import (
    FeasibilityResult,
    GlobalLoadState,
    HybridConfiguration,
    ReplicaChoice,
    TwoStageAction,
)


HYBRID_POLICY_CONTRACT_VERSION = "ibg-hybrid-policy-contract-v4"
HYBRID_BUDGET_MODE = "exact-stage-cardinality-v1"
HYBRID_REPLICA_CAPACITY_UNIT = "assigned-flows-per-slot"
HYBRID_NODE_RESOURCE_MODE = "deferred-versioned-per-flow-demands"
HYBRID_PLANNING_LINK_UNIT = "milliseconds"
HYBRID_LINK_WEIGHT_UTILITY_PER_MS = 1.0
HYBRID_FLOW_ORDER_SEED_SCHEME = "blake2b-hybrid-flow-order-v1"
HYBRID_ROLLOUT_SEED_SCHEME = "blake2b-hybrid-rollout-v1"
HYBRID_PRUNING_SCORE_MODE = "belief-load-aware-stage-utility-v1"
HYBRID_COMPLETE_ACTION_MODE = "enumerate-all-pruned-l2-actions-v1"
HYBRID_LOOKAHEAD_VALUE_MODE = "focal-final-load-once-v1"
HYBRID_ROLLOUT_KERNEL = "epsilon-greedy-pruned-joint-v1"
HYBRID_PAIR_LINK_MODE = "known-directed-selected-pair-v1"


class PipelinePath(str, Enum):
    """One internal path of the single public Hybrid policy."""

    GREEDY = "greedy-pruned"
    LOOKAHEAD = "deterministic-lookahead"
    MONTE_CARLO = "monte-carlo"


@dataclass(frozen=True)
class HybridPolicyParameters:
    """Paper-derived defaults with project-defined activation thresholds."""

    candidates_per_stage: int = 5
    lookahead_future_flows: int = 2
    monte_carlo_samples: int = 50
    rollout_epsilon: float = 0.10
    lookahead_contention_threshold: float = 0.70
    monte_carlo_entropy_threshold: float = 0.75

    def __post_init__(self) -> None:
        for name in (
            "candidates_per_stage",
            "lookahead_future_flows",
            "monte_carlo_samples",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, Integral):
                raise TypeError(f"{name} must be an integer")
        if self.candidates_per_stage < 1:
            raise ValueError("candidates_per_stage must be positive")
        if self.lookahead_future_flows < 0:
            raise ValueError("lookahead_future_flows must not be negative")
        if self.monte_carlo_samples < 1:
            raise ValueError("monte_carlo_samples must be positive")
        for name in (
            "rollout_epsilon",
            "lookahead_contention_threshold",
            "monte_carlo_entropy_threshold",
        ):
            value = float(getattr(self, name))
            if not isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be finite and within [0, 1]")


DEFAULT_HYBRID_POLICY_PARAMETERS = HybridPolicyParameters()


@dataclass(frozen=True)
class HybridActivationContext:
    """Known, normalized inputs used only to select an internal policy path."""

    contention_ratio: float
    maximum_normalized_belief_entropy: float
    high_priority: bool = False

    def __post_init__(self) -> None:
        for name in (
            "contention_ratio",
            "maximum_normalized_belief_entropy",
        ):
            value = float(getattr(self, name))
            if not isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be finite and within [0, 1]")
        if not isinstance(self.high_priority, bool):
            raise TypeError("high_priority must be a boolean")


def select_pipeline_path(
    context: HybridActivationContext,
    parameters: HybridPolicyParameters = DEFAULT_HYBRID_POLICY_PARAMETERS,
) -> PipelinePath:
    """Select the paper-aligned core Hybrid path.

    Phase 5 originally treated entropy/contention/priority as automatic
    switches between Monte Carlo, lookahead, and greedy.  The active Hybrid
    contract is instead pruning followed by deterministic lookahead for every
    focal decision.  The context and thresholds remain recorded diagnostics;
    Monte Carlo is unavailable to automatic slot orchestration until its
    separately deferred production redesign.
    """

    if not isinstance(context, HybridActivationContext):
        raise TypeError("context must be HybridActivationContext")
    if not isinstance(parameters, HybridPolicyParameters):
        raise TypeError("parameters must be HybridPolicyParameters")
    return PipelinePath.LOOKAHEAD


def pruned_action_count(
    configuration: HybridConfiguration,
    parameters: HybridPolicyParameters = DEFAULT_HYBRID_POLICY_PARAMETERS,
) -> int:
    """Return the maximum complete L=2 actions after per-stage pruning."""

    retained = min(
        parameters.candidates_per_stage,
        configuration.num_replicas,
    )
    return (
        comb(configuration.num_stages, configuration.stage_budget)
        * retained**configuration.stage_budget
    )


def prune_stage_candidates(
    stage: int,
    scores: Mapping[ReplicaChoice, float],
    parameters: HybridPolicyParameters = DEFAULT_HYBRID_POLICY_PARAMETERS,
) -> tuple[ReplicaChoice, ...]:
    """Apply the Phase 0 per-stage meaning of ``C`` deterministically.

    Callers supply belief-driven expected stage utility at the candidate's
    projected post-selection load. Pair link cost is intentionally excluded
    here and enters only when complete two-stage actions are scored.
    """

    candidates = []
    for choice, score in scores.items():
        if choice.stage != stage:
            raise ValueError("all pruning candidates must belong to the stage")
        numeric_score = float(score)
        if not isfinite(numeric_score):
            raise ValueError("candidate scores must be finite")
        candidates.append((choice, numeric_score))
    if not candidates:
        raise ValueError("pruning requires at least one feasible candidate")
    candidates.sort(key=lambda item: (-item[1], item[0].replica))
    return tuple(
        choice
        for choice, _score in candidates[: parameters.candidates_per_stage]
    )


def future_flows_to_simulate(
    remaining_flows_after_focal: int,
    parameters: HybridPolicyParameters = DEFAULT_HYBRID_POLICY_PARAMETERS,
) -> int:
    """Clamp ``D`` to the number of later flows still present in the slot."""

    if (
        isinstance(remaining_flows_after_focal, bool)
        or not isinstance(remaining_flows_after_focal, Integral)
    ):
        raise TypeError("remaining_flows_after_focal must be an integer")
    if remaining_flows_after_focal < 0:
        raise ValueError("remaining_flows_after_focal must not be negative")
    return min(
        remaining_flows_after_focal,
        parameters.lookahead_future_flows,
    )


@dataclass(frozen=True)
class ReplicaAdmission:
    """Known admission metadata, separate from a replica's hidden state."""

    choice: ReplicaChoice
    ready: bool
    max_assigned_flows: int

    def __post_init__(self) -> None:
        if not isinstance(self.ready, bool):
            raise TypeError("ready must be a boolean")
        if (
            isinstance(self.max_assigned_flows, bool)
            or not isinstance(self.max_assigned_flows, Integral)
        ):
            raise TypeError("max_assigned_flows must be an integer")
        if self.max_assigned_flows < 1:
            raise ValueError("max_assigned_flows must be positive")


def evaluate_replica_admission_feasibility(
    choice: ReplicaChoice,
    state: GlobalLoadState,
    configuration: HybridConfiguration,
    admission: Mapping[ReplicaChoice, ReplicaAdmission],
) -> FeasibilityResult:
    """Evaluate the replica-local part of the Phase 0 feasibility contract.

    Phase 2 uses this helper before per-stage pruning. Directed pair-link
    feasibility remains a complete-action decision in
    :func:`evaluate_phase0_feasibility`.
    """

    state.validate_for(configuration)
    if choice.stage > configuration.num_stages:
        raise ValueError("replica choice stage exceeds configuration")
    if choice.replica > configuration.num_replicas:
        raise ValueError("replica choice ID exceeds configuration")

    identity = f"{choice.stage}:{choice.replica}"
    metadata = admission.get(choice)
    if metadata is None:
        return FeasibilityResult.rejected(
            f"missing-admission-metadata:{identity}"
        )
    if metadata.choice != choice:
        return FeasibilityResult.rejected(
            f"mismatched-admission-metadata:{identity}"
        )

    reasons = []
    if not metadata.ready:
        reasons.append(f"not-ready:{identity}")
    if state.load_for(choice) + 1 > metadata.max_assigned_flows:
        reasons.append(f"replica-flow-capacity:{identity}")
    if reasons:
        return FeasibilityResult.rejected(*reasons)
    return FeasibilityResult.accepted()


def maximum_contention_ratio(
    state: GlobalLoadState,
    configuration: HybridConfiguration,
    admission: Mapping[ReplicaChoice, ReplicaAdmission],
) -> float:
    """Return max Ready-replica load/admission-capacity, clipped to one."""

    state.validate_for(configuration)
    ratios = []
    for choice, metadata in admission.items():
        if metadata.choice != choice:
            raise ValueError("admission metadata identity mismatch")
        if choice.stage > configuration.num_stages:
            raise ValueError("admission metadata stage exceeds configuration")
        if choice.replica > configuration.num_replicas:
            raise ValueError("admission metadata replica exceeds configuration")
        if metadata.ready:
            ratios.append(
                min(
                    1.0,
                    state.load_for(choice) / metadata.max_assigned_flows,
                )
            )
    if not ratios:
        raise ValueError("contention requires at least one Ready replica")
    return max(ratios)


def maximum_normalized_belief_entropy(
    beliefs: Mapping[ReplicaChoice, Sequence[float]],
) -> float:
    """Return maximum four-state Shannon entropy normalized to ``[0, 1]``.

    Production callers pass the feasible pruned replica pool, so an uncertain
    discarded or unavailable replica cannot activate Monte Carlo.
    """

    entropies = []
    for probabilities in beliefs.values():
        values = tuple(float(value) for value in probabilities)
        if len(values) != 4:
            raise ValueError("beliefs must contain the four IBG states")
        if any(not isfinite(value) or value < 0 for value in values):
            raise ValueError("belief probabilities must be finite and nonnegative")
        total = sum(values)
        if total <= 0:
            raise ValueError("belief probabilities must have positive mass")
        normalized = tuple(value / total for value in values)
        entropy = -sum(
            value * log(value)
            for value in normalized
            if value > 0
        ) / log(4.0)
        entropies.append(entropy)
    if not entropies:
        raise ValueError("entropy requires at least one feasible pruned replica")
    return max(entropies)


def evaluate_phase0_feasibility(
    action: TwoStageAction,
    state: GlobalLoadState,
    configuration: HybridConfiguration,
    admission: Mapping[ReplicaChoice, ReplicaAdmission],
    known_pair_link_costs: Mapping[
        tuple[ReplicaChoice, ReplicaChoice],
        float,
    ],
) -> FeasibilityResult:
    """Reference cardinality/Ready/flow-capacity/link-data feasibility."""

    action.validate_for(configuration)
    state.validate_for(configuration)
    reasons = []
    for choice in action.choices:
        replica_feasibility = evaluate_replica_admission_feasibility(
            choice,
            state,
            configuration,
            admission,
        )
        reasons.extend(replica_feasibility.reasons)
    pair = (action.choices[0], action.choices[1])
    pair_identity = (
        f"{pair[0].stage}:{pair[0].replica}->"
        f"{pair[1].stage}:{pair[1].replica}"
    )
    if pair not in known_pair_link_costs:
        reasons.append(f"missing-pair-link-cost:{pair_identity}")
    else:
        pair_cost = float(known_pair_link_costs[pair])
        if not isfinite(pair_cost) or pair_cost < 0:
            reasons.append(f"invalid-pair-link-cost:{pair_identity}")
    if reasons:
        return FeasibilityResult.rejected(*reasons)
    return FeasibilityResult.accepted()


StageExpectedUtility = Callable[[ReplicaChoice, int], float]
KnownPairLinkCost = Callable[[ReplicaChoice, ReplicaChoice], float]


def focal_utility_at_projected_loads(
    action: TwoStageAction,
    projected_state: GlobalLoadState,
    configuration: HybridConfiguration,
    stage_expected_utility: StageExpectedUtility,
    known_pair_link_cost: KnownPairLinkCost,
    *,
    link_weight: float = HYBRID_LINK_WEIGHT_UTILITY_PER_MS,
) -> float:
    """Evaluate the focal action once at predicted post-continuation loads."""

    action.validate_for(configuration)
    projected_state.validate_for(configuration)
    numeric_link_weight = float(link_weight)
    if not isfinite(numeric_link_weight) or numeric_link_weight < 0:
        raise ValueError("link_weight must be finite and nonnegative")

    stage_total = 0.0
    for choice in action.choices:
        final_load = projected_state.load_for(choice)
        if final_load < 1:
            raise ValueError(
                "projected state must already contain the focal action"
            )
        value = float(stage_expected_utility(choice, final_load))
        if not isfinite(value):
            raise ValueError("stage expected utility must be finite")
        stage_total += value

    pair_cost = float(
        known_pair_link_cost(action.choices[0], action.choices[1])
    )
    if not isfinite(pair_cost) or pair_cost < 0:
        raise ValueError("known pair link cost must be finite and nonnegative")
    return stage_total - numeric_link_weight * pair_cost


def project_focal_and_continuation(
    focal_action: TwoStageAction,
    continuation_actions: Sequence[TwoStageAction],
    initial_state: GlobalLoadState,
    configuration: HybridConfiguration,
) -> GlobalLoadState:
    """Commit the focal action once, then the ordered future actions."""

    projected = initial_state.apply(focal_action, configuration)
    for continuation_action in continuation_actions:
        projected = projected.apply(continuation_action, configuration)
    return projected


@dataclass(frozen=True)
class RolloutSeedKey:
    """Complete provenance key for one candidate-specific MC sample."""

    root_seed: int
    slot_id: int
    decision_position: int
    flow_id: int
    action: TwoStageAction
    sample_index: int

    def __post_init__(self) -> None:
        for name in (
            "root_seed",
            "slot_id",
            "decision_position",
            "flow_id",
            "sample_index",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, Integral):
                raise TypeError(f"{name} must be an integer")
        if self.root_seed < 0:
            raise ValueError("root_seed must not be negative")
        if self.slot_id < 1:
            raise ValueError("slot_id must be positive")
        if self.decision_position < 1:
            raise ValueError("decision_position must be positive")
        if self.flow_id < 1:
            raise ValueError("flow_id must be positive")
        if self.sample_index < 0:
            raise ValueError("sample_index must not be negative")


def derive_rollout_seed(key: RolloutSeedKey) -> int:
    """Derive a stable local seed without consuming a shared RNG stream."""

    choice_values = ",".join(
        f"{choice.stage}:{choice.replica}" for choice in key.action.choices
    )
    payload = (
        f"{HYBRID_ROLLOUT_SEED_SCHEME}|{key.root_seed}|{key.slot_id}|"
        f"{key.decision_position}|{key.flow_id}|{choice_values}|"
        f"{key.sample_index}"
    ).encode("ascii")
    return int.from_bytes(blake2b(payload, digest_size=8).digest(), "big")


def derive_flow_order_seed(root_seed: int, slot_id: int) -> int:
    """Derive the slot-wide flow-order seed independently from rollouts."""

    for name, value in (("root_seed", root_seed), ("slot_id", slot_id)):
        if isinstance(value, bool) or not isinstance(value, Integral):
            raise TypeError(f"{name} must be an integer")
    if root_seed < 0:
        raise ValueError("root_seed must not be negative")
    if slot_id < 1:
        raise ValueError("slot_id must be positive")
    payload = (
        f"{HYBRID_FLOW_ORDER_SEED_SCHEME}|{root_seed}|{slot_id}"
    ).encode("ascii")
    return int.from_bytes(blake2b(payload, digest_size=8).digest(), "big")
