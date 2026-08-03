"""Pure backend-neutral Phase 2 coupled MILP construction."""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite
from typing import Callable

from IBG.latency_model import expected_state_utility

from .contracts import MILPProblemInput
from .phase0_contract import (
    KnownStateExpectedUtility,
    MILP_ACTION_CARDINALITY,
    MILPContractError,
    ReplicaKey,
)


MILP_PHASE2_MODEL_VERSION = "milp-coupled-phase2-model-v1"


@dataclass(frozen=True, order=True)
class VariableReference:
    index: int
    family: str
    indices: tuple[int, ...]
    name: str


@dataclass(frozen=True)
class LinearConstraintRow:
    family: str
    name: str
    lower_bound: float
    upper_bound: float
    coefficients: tuple[tuple[int, float], ...]

    def __post_init__(self) -> None:
        if not self.family or not self.name:
            raise MILPContractError("constraint family and name must be nonempty")
        if self.lower_bound > self.upper_bound:
            raise MILPContractError("constraint lower bound exceeds upper bound")
        indices = tuple(index for index, _value in self.coefficients)
        if indices != tuple(sorted(indices)) or len(indices) != len(set(indices)):
            raise MILPContractError(
                "constraint coefficients must have unique sorted variable indices"
            )
        if any(not isfinite(value) or value == 0.0 for _, value in self.coefficients):
            raise MILPContractError(
                "constraint coefficients must be finite and nonzero"
            )


@dataclass(frozen=True, order=True)
class ExpectedUtilityCoefficient:
    key: ReplicaKey
    final_load: int
    utility: float


@dataclass(frozen=True)
class MILPLinearModel:
    """Solver-independent binary linear model in canonical record order."""

    problem: MILPProblemInput
    variables: tuple[VariableReference, ...]
    objective_minimize: tuple[float, ...]
    lower_bounds: tuple[float, ...]
    upper_bounds: tuple[float, ...]
    integrality: tuple[int, ...]
    constraints: tuple[LinearConstraintRow, ...]
    expected_utilities: tuple[ExpectedUtilityCoefficient, ...]
    version: str = MILP_PHASE2_MODEL_VERSION

    def __post_init__(self) -> None:
        size = len(self.variables)
        if tuple(variable.index for variable in self.variables) != tuple(range(size)):
            raise MILPContractError("variable indices must be contiguous and canonical")
        for values, field in (
            (self.objective_minimize, "objective"),
            (self.lower_bounds, "lower bounds"),
            (self.upper_bounds, "upper bounds"),
            (self.integrality, "integrality"),
        ):
            if len(values) != size:
                raise MILPContractError(f"{field} length does not match variables")
        if any(not isfinite(value) for value in self.objective_minimize):
            raise MILPContractError("objective coefficients must be finite")
        if any(value != 1 for value in self.integrality):
            raise MILPContractError("Phase 2 variables must all be binary/integer")
        if any(lower != 0.0 for lower in self.lower_bounds) or any(
            upper != 1.0 for upper in self.upper_bounds
        ):
            raise MILPContractError("Phase 2 variables must all have bounds [0,1]")
        if any(
            index < 0 or index >= size
            for row in self.constraints
            for index, _value in row.coefficients
        ):
            raise MILPContractError("constraint references an unknown variable")

    @property
    def variable_count(self) -> int:
        return len(self.variables)

    @property
    def constraint_count(self) -> int:
        return len(self.constraints)

    def variable_index(self, family: str, indices: tuple[int, ...]) -> int:
        for variable in self.variables:
            if variable.family == family and variable.indices == indices:
                return variable.index
        raise MILPContractError(f"unknown variable {family}{indices}")

    def variables_in_family(self, family: str) -> tuple[VariableReference, ...]:
        return tuple(variable for variable in self.variables if variable.family == family)

    def expected_utility(self, key: ReplicaKey, final_load: int) -> float:
        for coefficient in self.expected_utilities:
            if coefficient.key == key and coefficient.final_load == final_load:
                return coefficient.utility
        raise MILPContractError(
            f"missing expected utility for {key} at load {final_load}"
        )

    def with_objective_and_constraints(
        self,
        *,
        objective_minimize: tuple[float, ...],
        constraints: tuple[LinearConstraintRow, ...],
    ) -> MILPLinearModel:
        return replace(
            self,
            objective_minimize=objective_minimize,
            constraints=constraints,
        )


def exact_known_state_expected_utility(
    problem: MILPProblemInput,
) -> KnownStateExpectedUtility:
    """Bind the unchanged Exact state/load expected-utility helper."""

    true_states = problem.true_state_by_replica()

    def utility(key: ReplicaKey, final_load: int) -> float:
        return expected_state_utility(true_states[key], final_load)

    return utility


def _finite_utility(value: object, key: ReplicaKey, load: int) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise MILPContractError(
            f"expected utility for {key} at load {load} must be finite"
        ) from exc
    if not isfinite(result):
        raise MILPContractError(
            f"expected utility for {key} at load {load} must be finite"
        )
    return result


def _canonical_coefficients(
    values: tuple[tuple[int, float], ...],
) -> tuple[tuple[int, float], ...]:
    combined: dict[int, float] = {}
    for index, value in values:
        combined[index] = combined.get(index, 0.0) + float(value)
    return tuple(
        (index, combined[index])
        for index in sorted(combined)
        if combined[index] != 0.0
    )


def build_coupled_milp_model(
    problem: MILPProblemInput,
    known_state_expected_utility: KnownStateExpectedUtility | None = None,
) -> MILPLinearModel:
    """Construct the exact Phase 0 ``x/y/z/p`` formulation without solving."""

    if not isinstance(problem, MILPProblemInput):
        raise MILPContractError("problem must be MILPProblemInput")
    dimensions = problem.configuration.dimensions
    utility = known_state_expected_utility or exact_known_state_expected_utility(problem)
    pairs = tuple(link.pair for link in problem.planning_links)
    link_costs = problem.planning_link_costs_ms()
    admission = problem.admission_by_replica()

    variables: list[VariableReference] = []

    def add_variable(family: str, indices: tuple[int, ...], name: str) -> int:
        index = len(variables)
        variables.append(VariableReference(index, family, indices, name))
        return index

    x: dict[tuple[int, ReplicaKey], int] = {}
    y: dict[tuple[int, int], int] = {}
    z: dict[tuple[ReplicaKey, int], int] = {}
    p: dict[tuple[int, tuple[ReplicaKey, ReplicaKey]], int] = {}

    for flow in dimensions.flow_ids:
        for key in dimensions.replica_keys:
            x[(flow, key)] = add_variable(
                "x",
                (flow, key.stage, key.replica),
                f"x[{flow},{key.stage},{key.replica}]",
            )
    for flow in dimensions.flow_ids:
        for stage in dimensions.stage_ids:
            y[(flow, stage)] = add_variable(
                "y",
                (flow, stage),
                f"y[{flow},{stage}]",
            )
    for key in dimensions.replica_keys:
        for load in range(0, dimensions.flow_count + 1):
            z[(key, load)] = add_variable(
                "z",
                (key.stage, key.replica, load),
                f"z[{key.stage},{key.replica},{load}]",
            )
    for flow in dimensions.flow_ids:
        for source, target in pairs:
            p[(flow, (source, target))] = add_variable(
                "p",
                (
                    flow,
                    source.stage,
                    source.replica,
                    target.stage,
                    target.replica,
                ),
                (
                    f"p[{flow},{source.stage},{source.replica},"
                    f"{target.stage},{target.replica}]"
                ),
            )

    expected_utilities = tuple(
        ExpectedUtilityCoefficient(
            key,
            load,
            _finite_utility(utility(key, load), key, load),
        )
        for key in dimensions.replica_keys
        for load in range(1, dimensions.flow_count + 1)
    )
    expected_by_key_load = {
        (item.key, item.final_load): item.utility for item in expected_utilities
    }

    objective = [0.0] * len(variables)
    for key in dimensions.replica_keys:
        for load in range(1, dimensions.flow_count + 1):
            # SciPy minimizes, so negate the maximized replica welfare term.
            objective[z[(key, load)]] = -(
                load * expected_by_key_load[(key, load)]
            )
    for flow in dimensions.flow_ids:
        for pair in pairs:
            objective[p[(flow, pair)]] = link_costs[pair]

    rows: list[LinearConstraintRow] = []

    def add_row(
        family: str,
        name: str,
        lower: float,
        upper: float,
        coefficients: tuple[tuple[int, float], ...],
    ) -> None:
        rows.append(
            LinearConstraintRow(
                family,
                name,
                float(lower),
                float(upper),
                _canonical_coefficients(coefficients),
            )
        )

    for flow in dimensions.flow_ids:
        add_row(
            "exact-stage-cardinality",
            f"exact-stage-cardinality[{flow}]",
            MILP_ACTION_CARDINALITY,
            MILP_ACTION_CARDINALITY,
            tuple((y[(flow, stage)], 1.0) for stage in dimensions.stage_ids),
        )

    for flow in dimensions.flow_ids:
        for stage in dimensions.stage_ids:
            stage_keys = tuple(
                key for key in dimensions.replica_keys if key.stage == stage
            )
            add_row(
                "one-replica-per-selected-stage",
                f"one-replica-per-selected-stage[{flow},{stage}]",
                0.0,
                0.0,
                tuple((x[(flow, key)], 1.0) for key in stage_keys)
                + ((y[(flow, stage)], -1.0),),
            )

    for flow in dimensions.flow_ids:
        for key in dimensions.replica_keys:
            ready_upper = 1.0 if admission[key].ready else 0.0
            add_row(
                "ready-availability",
                f"ready-availability[{flow},{key.stage},{key.replica}]",
                float("-inf"),
                ready_upper,
                ((x[(flow, key)], 1.0),),
            )

    for key in dimensions.replica_keys:
        add_row(
            "declared-assigned-flow-capacity",
            f"declared-assigned-flow-capacity[{key.stage},{key.replica}]",
            float("-inf"),
            admission[key].assigned_flow_capacity,
            tuple((x[(flow, key)], 1.0) for flow in dimensions.flow_ids),
        )

    for key in dimensions.replica_keys:
        add_row(
            "one-final-load-indicator",
            f"one-final-load-indicator[{key.stage},{key.replica}]",
            1.0,
            1.0,
            tuple(
                (z[(key, load)], 1.0)
                for load in range(0, dimensions.flow_count + 1)
            ),
        )
        add_row(
            "final-load-reconstruction",
            f"final-load-reconstruction[{key.stage},{key.replica}]",
            0.0,
            0.0,
            tuple((x[(flow, key)], 1.0) for flow in dimensions.flow_ids)
            + tuple(
                (z[(key, load)], -float(load))
                for load in range(1, dimensions.flow_count + 1)
            ),
        )

    for flow in dimensions.flow_ids:
        for source, target in pairs:
            pair = (source, target)
            p_index = p[(flow, pair)]
            left = x[(flow, source)]
            right = x[(flow, target)]
            suffix = (
                f"{flow},{source.stage},{source.replica},"
                f"{target.stage},{target.replica}"
            )
            add_row(
                "directed-pair-linearization-upper-left",
                f"directed-pair-upper-left[{suffix}]",
                float("-inf"),
                0.0,
                ((p_index, 1.0), (left, -1.0)),
            )
            add_row(
                "directed-pair-linearization-upper-right",
                f"directed-pair-upper-right[{suffix}]",
                float("-inf"),
                0.0,
                ((p_index, 1.0), (right, -1.0)),
            )
            add_row(
                "directed-pair-linearization-lower",
                f"directed-pair-lower[{suffix}]",
                float("-inf"),
                1.0,
                ((left, 1.0), (right, 1.0), (p_index, -1.0)),
            )

    for flow in dimensions.flow_ids:
        add_row(
            "one-selected-directed-pair",
            f"one-selected-directed-pair[{flow}]",
            1.0,
            1.0,
            tuple((p[(flow, pair)], 1.0) for pair in pairs),
        )

    variable_count = len(variables)
    return MILPLinearModel(
        problem=problem,
        variables=tuple(variables),
        objective_minimize=tuple(objective),
        lower_bounds=(0.0,) * variable_count,
        upper_bounds=(1.0,) * variable_count,
        integrality=(1,) * variable_count,
        constraints=tuple(rows),
        expected_utilities=expected_utilities,
    )
