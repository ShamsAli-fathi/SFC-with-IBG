"""Tiny exhaustive coupled oracle for Hybrid tests and fixtures only."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations, product
from math import comb, isfinite
from typing import Callable, Iterator

from .contracts import (
    FeasibilityResult,
    GlobalLoadState,
    HybridConfiguration,
    HybridSolverResult,
    ReplicaChoice,
    TwoStageAction,
)

ActionValue = Callable[[TwoStageAction, GlobalLoadState], float]
FeasibilityCheck = Callable[
    [TwoStageAction, GlobalLoadState],
    FeasibilityResult,
]


class NoFeasibleHybridAction(RuntimeError):
    """Raised when a test fixture contains no complete feasible continuation."""


@dataclass(frozen=True)
class TinyOracleLimits:
    """Hard limits preventing accidental production use of the oracle."""

    max_flows: int = 4
    max_actions_per_state: int = 64


def enumerate_two_stage_actions(
    configuration: HybridConfiguration,
) -> Iterator[TwoStageAction]:
    """Yield every valid action in deterministic lexicographic order."""

    for stage_a, stage_b in combinations(
        range(1, configuration.num_stages + 1),
        configuration.stage_budget,
    ):
        for replica_a, replica_b in product(
            range(1, configuration.num_replicas + 1),
            repeat=configuration.stage_budget,
        ):
            yield TwoStageAction(
                (
                    ReplicaChoice(stage_a, replica_a),
                    ReplicaChoice(stage_b, replica_b),
                )
            )


def _action_count(configuration: HybridConfiguration) -> int:
    return comb(
        configuration.num_stages,
        configuration.stage_budget,
    ) * configuration.num_replicas**configuration.stage_budget


def solve_tiny_exhaustive(
    configuration: HybridConfiguration,
    state: GlobalLoadState,
    remaining_flows: int,
    action_value: ActionValue,
    feasibility_check: FeasibilityCheck | None = None,
    *,
    limits: TinyOracleLimits = TinyOracleLimits(),
) -> HybridSolverResult:
    """Exactly maximize a caller-supplied additive objective on a tiny fixture.

    This is a correctness oracle, not the production Hybrid policy. It does
    not define the future pruning, lookahead, Monte Carlo, utility, link, or
    feasibility semantics; callers inject the immediate objective and
    feasibility rule being tested.
    """

    if isinstance(remaining_flows, bool) or not isinstance(remaining_flows, int):
        raise TypeError("remaining_flows must be an integer")
    if remaining_flows < 1:
        raise ValueError("remaining_flows must be at least 1")
    if remaining_flows > limits.max_flows:
        raise ValueError(
            "the exhaustive oracle is test-only and supports at most "
            f"{limits.max_flows} flows"
        )
    actions_per_state = _action_count(configuration)
    if actions_per_state > limits.max_actions_per_state:
        raise ValueError(
            "the exhaustive oracle is test-only and supports at most "
            f"{limits.max_actions_per_state} actions per state"
        )
    state.validate_for(configuration)
    actions = tuple(enumerate_two_stage_actions(configuration))
    check = feasibility_check or (
        lambda _action, _state: FeasibilityResult.accepted()
    )

    def solve(
        current_state: GlobalLoadState,
        depth: int,
    ) -> tuple[float, tuple[TwoStageAction, ...]] | None:
        if depth == 0:
            return 0.0, ()

        best_value = -float("inf")
        best_plan: tuple[TwoStageAction, ...] | None = None
        for action in actions:
            feasibility = check(action, current_state)
            if not isinstance(feasibility, FeasibilityResult):
                raise TypeError(
                    "feasibility_check must return FeasibilityResult"
                )
            if not feasibility.feasible:
                continue
            immediate = float(action_value(action, current_state))
            if not isfinite(immediate):
                raise ValueError("action_value must return a finite number")
            next_state = current_state.apply(action, configuration)
            continuation = solve(next_state, depth - 1)
            if continuation is None:
                continue
            total = immediate + continuation[0]
            plan = (action,) + continuation[1]
            # Actions are enumerated canonically, so strict improvement retains
            # the lexicographically first plan on an exact tie.
            if best_plan is None or total > best_value:
                best_value = total
                best_plan = plan
        if best_plan is None:
            return None
        return best_value, best_plan

    solution = solve(state, remaining_flows)
    if solution is None:
        raise NoFeasibleHybridAction(
            "no complete feasible action sequence exists for this fixture"
        )

    objective_value, plan = solution
    chosen = plan[0]
    chosen_feasibility = check(chosen, state)
    root_feasible = sum(
        1 for action in actions if check(action, state).feasible
    )
    return HybridSolverResult(
        action=chosen,
        objective_value=objective_value,
        state_after=state.apply(chosen, configuration),
        feasibility=chosen_feasibility,
        evaluated_actions=len(actions),
        feasible_actions=root_feasible,
    )
