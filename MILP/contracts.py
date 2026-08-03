"""Immutable Phase 1 contracts built on the authoritative Phase 0 model."""

from __future__ import annotations

from dataclasses import dataclass
from math import isclose
from numbers import Integral

from .phase0_contract import (
    DEFAULT_MILP_DIMENSIONS,
    MILP_ACTION_CARDINALITY,
    MILPContractError,
    MILPDimensions,
    ReplicaAdmission,
    ReplicaKey,
    SocialWelfareBreakdown,
    SolverResultStatus,
    SolverRunProvenance,
    TwoStageAction,
    evaluate_placement_feasibility,
    final_replica_loads,
    required_directed_pairs,
    validate_admission_metadata,
    validate_cutoff_seconds,
    validate_planning_link_metadata,
)


MILP_PHASE1_CONTRACT_VERSION = "milp-coupled-phase1-boundary-v1"
SUPPORTED_TRUE_STATES = (1, 2, 3, 4)


@dataclass(frozen=True)
class MILPConfiguration:
    """Per-run dimensions and exact solver time limit.

    Dimension values are runtime inputs.  Only the action cardinality remains
    fixed by the mathematical contract.
    """

    dimensions: MILPDimensions
    cutoff_seconds: float
    action_cardinality: int = MILP_ACTION_CARDINALITY

    def __post_init__(self) -> None:
        if not isinstance(self.dimensions, MILPDimensions):
            raise MILPContractError("dimensions must be MILPDimensions")
        if (
            isinstance(self.action_cardinality, bool)
            or not isinstance(self.action_cardinality, Integral)
            or int(self.action_cardinality) != MILP_ACTION_CARDINALITY
        ):
            raise MILPContractError(
                f"only exact L={MILP_ACTION_CARDINALITY} is supported"
            )
        object.__setattr__(self, "action_cardinality", MILP_ACTION_CARDINALITY)
        object.__setattr__(
            self,
            "cutoff_seconds",
            validate_cutoff_seconds(self.cutoff_seconds),
        )

    @classmethod
    def uniform(
        cls,
        *,
        flow_count: int = DEFAULT_MILP_DIMENSIONS.flow_count,
        stage_count: int = DEFAULT_MILP_DIMENSIONS.stage_count,
        replicas_per_stage: int = DEFAULT_MILP_DIMENSIONS.replicas_per_stage[0],
        cutoff_seconds: float,
    ) -> MILPConfiguration:
        if isinstance(stage_count, bool) or not isinstance(stage_count, Integral):
            raise MILPContractError("stage_count must be a positive integer")
        if int(stage_count) < MILP_ACTION_CARDINALITY:
            raise MILPContractError(
                f"stage_count must be at least L={MILP_ACTION_CARDINALITY}"
            )
        if (
            isinstance(replicas_per_stage, bool)
            or not isinstance(replicas_per_stage, Integral)
            or replicas_per_stage <= 0
        ):
            raise MILPContractError("replicas_per_stage must be a positive integer")
        dimensions = MILPDimensions(
            flow_count=flow_count,
            replicas_per_stage=(int(replicas_per_stage),) * int(stage_count),
        )
        return cls(dimensions=dimensions, cutoff_seconds=cutoff_seconds)


@dataclass(frozen=True, order=True)
class ReplicaPlanningInput:
    """Clairvoyant MILP input for one replica."""

    key: ReplicaKey
    true_state: int
    admission: ReplicaAdmission

    def __post_init__(self) -> None:
        if not isinstance(self.key, ReplicaKey):
            raise MILPContractError("replica key must be ReplicaKey")
        if (
            isinstance(self.true_state, bool)
            or not isinstance(self.true_state, Integral)
            or int(self.true_state) not in SUPPORTED_TRUE_STATES
        ):
            raise MILPContractError("true_state must be one of 1, 2, 3, or 4")
        if not isinstance(self.admission, ReplicaAdmission):
            raise MILPContractError("admission must be ReplicaAdmission")
        object.__setattr__(self, "true_state", int(self.true_state))


@dataclass(frozen=True, order=True)
class DirectedPlanningLink:
    """One configured lower-stage to higher-stage planning coefficient."""

    source: ReplicaKey
    target: ReplicaKey
    cost_ms: float

    def __post_init__(self) -> None:
        if not isinstance(self.source, ReplicaKey) or not isinstance(
            self.target, ReplicaKey
        ):
            raise MILPContractError("planning-link endpoints must be ReplicaKey")
        if self.source.stage >= self.target.stage:
            raise MILPContractError(
                "planning link must point from a lower to a higher stage"
            )
        # Reuse the complete Phase 0 validator below for numeric semantics.
        from .phase0_contract import _finite_number

        value = _finite_number(self.cost_ms, "planning-link cost_ms")
        if value < 0.0:
            raise MILPContractError("planning-link cost_ms must be nonnegative")
        object.__setattr__(self, "cost_ms", value)

    @property
    def pair(self) -> tuple[ReplicaKey, ReplicaKey]:
        return self.source, self.target


@dataclass(frozen=True)
class MILPProblemInput:
    """Complete immutable whole-slot planner input."""

    configuration: MILPConfiguration
    replicas: tuple[ReplicaPlanningInput, ...]
    planning_links: tuple[DirectedPlanningLink, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.configuration, MILPConfiguration):
            raise MILPContractError("configuration must be MILPConfiguration")
        if not isinstance(self.replicas, tuple):
            raise MILPContractError("replicas must be an immutable tuple")
        if not isinstance(self.planning_links, tuple):
            raise MILPContractError("planning_links must be an immutable tuple")
        if any(not isinstance(item, ReplicaPlanningInput) for item in self.replicas):
            raise MILPContractError("invalid replica planning input")
        if any(not isinstance(item, DirectedPlanningLink) for item in self.planning_links):
            raise MILPContractError("invalid directed planning link")
        if self.replicas != tuple(sorted(self.replicas, key=lambda item: item.key)):
            raise MILPContractError("replicas must use canonical stage/replica order")
        if self.planning_links != tuple(
            sorted(self.planning_links, key=lambda item: item.pair)
        ):
            raise MILPContractError("planning_links must use canonical pair order")
        if len({item.key for item in self.replicas}) != len(self.replicas):
            raise MILPContractError("replicas must not contain duplicate keys")
        if len({item.pair for item in self.planning_links}) != len(
            self.planning_links
        ):
            raise MILPContractError("planning_links must not contain duplicate pairs")

        dimensions = self.configuration.dimensions
        admission = self.admission_by_replica()
        links = self.planning_link_costs_ms()
        validate_admission_metadata(dimensions, admission)
        validate_planning_link_metadata(dimensions, links)
        true_state_keys = {item.key for item in self.replicas}
        if true_state_keys != set(dimensions.replica_keys):
            raise MILPContractError("true-state metadata must cover every replica")

    def admission_by_replica(self) -> dict[ReplicaKey, ReplicaAdmission]:
        return {item.key: item.admission for item in self.replicas}

    def true_state_by_replica(self) -> dict[ReplicaKey, int]:
        return {item.key: item.true_state for item in self.replicas}

    def planning_link_costs_ms(
        self,
    ) -> dict[tuple[ReplicaKey, ReplicaKey], float]:
        return {item.pair: item.cost_ms for item in self.planning_links}


@dataclass(frozen=True)
class MILPPlacement:
    """Canonical complete whole-slot placement."""

    actions: tuple[tuple[int, TwoStageAction], ...]
    final_loads: tuple[tuple[ReplicaKey, int], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.actions, tuple) or not isinstance(self.final_loads, tuple):
            raise MILPContractError("placement records must be immutable tuples")
        if self.actions != tuple(sorted(self.actions, key=lambda item: item[0])):
            raise MILPContractError("actions must use canonical flow order")
        flow_ids = tuple(flow_id for flow_id, _ in self.actions)
        if any(
            isinstance(flow_id, bool)
            or not isinstance(flow_id, Integral)
            or flow_id <= 0
            for flow_id in flow_ids
        ):
            raise MILPContractError("placement flow IDs must be positive integers")
        if len(flow_ids) != len(set(flow_ids)):
            raise MILPContractError("placement contains duplicate flow IDs")
        if any(not isinstance(action, TwoStageAction) for _, action in self.actions):
            raise MILPContractError("placement contains an invalid action")

    @classmethod
    def from_actions(
        cls,
        dimensions: MILPDimensions,
        actions: dict[int, TwoStageAction],
    ) -> MILPPlacement:
        canonical_actions = tuple((flow, actions[flow]) for flow in dimensions.flow_ids)
        return cls(
            actions=canonical_actions,
            final_loads=final_replica_loads(dimensions, actions),
        )

    def action_by_flow(self) -> dict[int, TwoStageAction]:
        return dict(self.actions)

    def validate_for(self, problem: MILPProblemInput) -> None:
        dimensions = problem.configuration.dimensions
        actions = self.action_by_flow()
        expected_loads = final_replica_loads(dimensions, actions)
        if self.final_loads != expected_loads:
            raise MILPContractError("placement final loads do not reconstruct")
        feasibility = evaluate_placement_feasibility(
            dimensions,
            actions,
            problem.admission_by_replica(),
            problem.planning_link_costs_ms(),
        )
        if not feasibility.feasible:
            raise MILPContractError(
                f"placement is infeasible: {', '.join(feasibility.reasons)}"
            )


@dataclass(frozen=True)
class MILPSolverResult:
    """Normalized Phase 0 status provenance plus an optional incumbent."""

    provenance: SolverRunProvenance
    placement: MILPPlacement | None = None
    objective: SocialWelfareBreakdown | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.provenance, SolverRunProvenance):
            raise MILPContractError("provenance must be SolverRunProvenance")
        has_incumbent = self.provenance.incumbent_objective_utility is not None
        if has_incumbent != (self.placement is not None and self.objective is not None):
            raise MILPContractError(
                "incumbent provenance, placement, and objective must appear together"
            )
        if self.placement is not None and not isinstance(self.placement, MILPPlacement):
            raise MILPContractError("placement must be MILPPlacement")
        if self.objective is not None and not isinstance(
            self.objective, SocialWelfareBreakdown
        ):
            raise MILPContractError("objective must be SocialWelfareBreakdown")
        if self.objective is not None and not isclose(
            self.objective.total_social_welfare_utility,
            self.provenance.incumbent_objective_utility,
            rel_tol=1e-12,
            abs_tol=1e-9,
        ):
            raise MILPContractError("objective does not match incumbent provenance")
        if self.provenance.status in (
            SolverResultStatus.PROVEN_OPTIMAL,
            SolverResultStatus.TIME_LIMIT_WITH_INCUMBENT,
        ) and self.placement is None:
            raise MILPContractError("incumbent status requires a placement")


def build_problem_input(
    configuration: MILPConfiguration,
    *,
    true_states: dict[ReplicaKey, int],
    admission: dict[ReplicaKey, ReplicaAdmission],
    planning_link_cost_ms: dict[tuple[ReplicaKey, ReplicaKey], float],
) -> MILPProblemInput:
    """Build the immutable boundary from ordinary adapter mappings."""

    dimensions = configuration.dimensions
    expected_keys = set(dimensions.replica_keys)
    if set(true_states) != expected_keys:
        raise MILPContractError("true-state metadata must cover every replica")
    validate_admission_metadata(dimensions, admission)
    validate_planning_link_metadata(dimensions, planning_link_cost_ms)
    replicas = tuple(
        ReplicaPlanningInput(key, true_states[key], admission[key])
        for key in dimensions.replica_keys
    )
    links = tuple(
        DirectedPlanningLink(source, target, planning_link_cost_ms[(source, target)])
        for source, target in required_directed_pairs(dimensions)
    )
    return MILPProblemInput(configuration, replicas, links)
