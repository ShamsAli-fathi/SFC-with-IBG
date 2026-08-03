"""Tiny exhaustive centralized-welfare oracle for tests only."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations, product

from .contracts import MILPPlacement, MILPProblemInput
from .phase0_contract import (
    KnownStateExpectedUtility,
    MILPContractError,
    ReplicaKey,
    SocialWelfareBreakdown,
    TwoStageAction,
    evaluate_placement_feasibility,
    reconstruct_social_welfare,
)


TINY_ORACLE_MAX_FLOWS = 4
TINY_ORACLE_MAX_COMPLETE_PLACEMENTS = 100_000


class TinyOracleScopeError(MILPContractError):
    """Raised when a fixture is too large for exhaustive enumeration."""


class NoFeasibleMILPPlacement(MILPContractError):
    """Raised when no complete exact-L=2 placement is feasible."""


@dataclass(frozen=True)
class TinyOracleResult:
    placement: MILPPlacement
    objective: SocialWelfareBreakdown
    complete_placements_considered: int
    feasible_placements: int


def canonical_actions(problem: MILPProblemInput) -> tuple[TwoStageAction, ...]:
    dimensions = problem.configuration.dimensions
    by_stage = {
        stage: tuple(key for key in dimensions.replica_keys if key.stage == stage)
        for stage in dimensions.stage_ids
    }
    return tuple(
        TwoStageAction.canonical(left, right)
        for left_stage, right_stage in combinations(dimensions.stage_ids, 2)
        for left in by_stage[left_stage]
        for right in by_stage[right_stage]
    )


def solve_tiny_exhaustive(
    problem: MILPProblemInput,
    known_state_expected_utility: KnownStateExpectedUtility,
) -> TinyOracleResult:
    """Maximize Phase 0 welfare by enumeration on deliberately tiny fixtures."""

    dimensions = problem.configuration.dimensions
    if dimensions.flow_count > TINY_ORACLE_MAX_FLOWS:
        raise TinyOracleScopeError(
            f"tiny oracle supports at most {TINY_ORACLE_MAX_FLOWS} flows; "
            "the production/default 15x3x10 boundary is forbidden"
        )
    actions = canonical_actions(problem)
    placement_count = len(actions) ** dimensions.flow_count
    if placement_count > TINY_ORACLE_MAX_COMPLETE_PLACEMENTS:
        raise TinyOracleScopeError(
            f"tiny oracle would enumerate {placement_count} placements; "
            f"limit is {TINY_ORACLE_MAX_COMPLETE_PLACEMENTS}"
        )

    admission = problem.admission_by_replica()
    links = problem.planning_link_costs_ms()
    best_actions: dict[int, TwoStageAction] | None = None
    best_objective: SocialWelfareBreakdown | None = None
    feasible_count = 0
    considered = 0
    for choices in product(actions, repeat=dimensions.flow_count):
        considered += 1
        candidate = dict(zip(dimensions.flow_ids, choices, strict=True))
        feasibility = evaluate_placement_feasibility(
            dimensions,
            candidate,
            admission,
            links,
        )
        if not feasibility.feasible:
            continue
        feasible_count += 1
        objective = reconstruct_social_welfare(
            dimensions,
            candidate,
            known_state_expected_utility,
            links,
        )
        if (
            best_objective is None
            or objective.total_social_welfare_utility
            > best_objective.total_social_welfare_utility
        ):
            best_actions = candidate
            best_objective = objective

    if best_actions is None or best_objective is None:
        raise NoFeasibleMILPPlacement("no feasible complete L=2 placement")
    return TinyOracleResult(
        placement=MILPPlacement.from_actions(dimensions, best_actions),
        objective=best_objective,
        complete_placements_considered=considered,
        feasible_placements=feasible_count,
    )
