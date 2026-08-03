"""SciPy/HiGHS adapter and normalized Phase 2 coupled MILP solve."""

from __future__ import annotations

from dataclasses import dataclass
from math import isclose, isfinite
from time import monotonic
from typing import Callable

from .backend import BackendAvailability, require_scipy_highs
from .contracts import MILPPlacement, MILPProblemInput, MILPSolverResult
from .model import (
    LinearConstraintRow,
    MILPLinearModel,
    build_coupled_milp_model,
)
from .phase0_contract import (
    KnownStateExpectedUtility,
    MILPContractError,
    SolverResultStatus,
    SolverRunProvenance,
    TwoStageAction,
    normalized_solver_gaps,
    reconstruct_social_welfare,
)


MILP_PHASE2_SOLVER_VERSION = "milp-coupled-phase2-solver-v1"
SCIPY_HIGHS_BACKEND_NAME = "scipy.optimize.milp/HiGHS"
SOLUTION_TOLERANCE = 1e-6


@dataclass(frozen=True)
class BackendRawResult:
    status: int
    message: str
    x: tuple[float, ...] | None = None
    objective_minimize: float | None = None
    dual_bound_minimize: float | None = None
    mip_gap: float | None = None
    node_count: int | None = None


BackendSolve = Callable[[MILPLinearModel, float], BackendRawResult]


def _backend_version(availability: BackendAvailability) -> str:
    return f"SciPy {availability.scipy_version}; HiGHS {availability.highs_version}"


def solve_scipy_highs(
    model: MILPLinearModel,
    time_limit_seconds: float,
    *,
    display: bool = False,
) -> BackendRawResult:
    """Translate one pure model and invoke SciPy's native time-limit API."""

    from numpy import asarray
    from scipy.optimize import Bounds, LinearConstraint, milp
    from scipy.sparse import csc_array

    row_indices: list[int] = []
    column_indices: list[int] = []
    data: list[float] = []
    lower: list[float] = []
    upper: list[float] = []
    for row_number, row in enumerate(model.constraints):
        lower.append(row.lower_bound)
        upper.append(row.upper_bound)
        for variable_index, coefficient in row.coefficients:
            row_indices.append(row_number)
            column_indices.append(variable_index)
            data.append(coefficient)
    matrix = csc_array(
        (data, (row_indices, column_indices)),
        shape=(model.constraint_count, model.variable_count),
    )
    result = milp(
        c=asarray(model.objective_minimize, dtype=float),
        integrality=asarray(model.integrality, dtype=int),
        bounds=Bounds(model.lower_bounds, model.upper_bounds),
        constraints=LinearConstraint(matrix, lower, upper),
        options={
            "disp": bool(display),
            "presolve": True,
            "time_limit": float(time_limit_seconds),
            "mip_rel_gap": 0.0,
        },
    )
    raw_x = getattr(result, "x", None)
    return BackendRawResult(
        status=int(result.status),
        message=str(result.message),
        x=None if raw_x is None else tuple(float(value) for value in raw_x),
        objective_minimize=(
            None if getattr(result, "fun", None) is None else float(result.fun)
        ),
        dual_bound_minimize=(
            None
            if getattr(result, "mip_dual_bound", None) is None
            else float(result.mip_dual_bound)
        ),
        mip_gap=(
            None if getattr(result, "mip_gap", None) is None else float(result.mip_gap)
        ),
        node_count=(
            None
            if getattr(result, "mip_node_count", None) is None
            else int(result.mip_node_count)
        ),
    )


def _validate_solution_vector(
    model: MILPLinearModel,
    values: tuple[float, ...],
) -> None:
    if len(values) != model.variable_count:
        raise MILPContractError("backend solution length does not match model")
    for index, value in enumerate(values):
        if not isfinite(value):
            raise MILPContractError("backend solution contains a nonfinite value")
        if value < -SOLUTION_TOLERANCE or value > 1.0 + SOLUTION_TOLERANCE:
            raise MILPContractError(f"variable {index} violates binary bounds")
        if abs(value - round(value)) > SOLUTION_TOLERANCE:
            raise MILPContractError(f"variable {index} is not integral")
    for row in model.constraints:
        activity = sum(values[index] * coefficient for index, coefficient in row.coefficients)
        if activity < row.lower_bound - SOLUTION_TOLERANCE or activity > (
            row.upper_bound + SOLUTION_TOLERANCE
        ):
            raise MILPContractError(f"solution violates constraint {row.name}")


def _extract_placement(
    model: MILPLinearModel,
    values: tuple[float, ...],
) -> MILPPlacement:
    _validate_solution_vector(model, values)
    dimensions = model.problem.configuration.dimensions
    actions: dict[int, TwoStageAction] = {}
    x_variables = model.variables_in_family("x")
    for flow in dimensions.flow_ids:
        selections = []
        for variable in x_variables:
            variable_flow, stage, replica = variable.indices
            if variable_flow == flow and values[variable.index] > 0.5:
                from .phase0_contract import ReplicaKey

                selections.append(ReplicaKey(stage, replica))
        if len(selections) != 2:
            raise MILPContractError(
                f"flow {flow} does not have exactly two selected replicas"
            )
        actions[flow] = TwoStageAction.canonical(*selections)

    # Flow identities are objective-symmetric. Sorting the selected action
    # multiset removes backend-dependent flow-label permutations without
    # changing loads, feasibility, links, or welfare.
    sorted_actions = tuple(sorted(actions.values(), key=lambda action: action.selections))
    canonical_actions = dict(zip(dimensions.flow_ids, sorted_actions, strict=True))
    placement = MILPPlacement.from_actions(dimensions, canonical_actions)
    placement.validate_for(model.problem)
    return placement


def _table_utility(model: MILPLinearModel) -> KnownStateExpectedUtility:
    table = {
        (item.key, item.final_load): item.utility for item in model.expected_utilities
    }

    def utility(key, final_load):
        return table[(key, final_load)]

    return utility


def _solution_objective(
    model: MILPLinearModel,
    placement: MILPPlacement,
):
    return reconstruct_social_welfare(
        model.problem.configuration.dimensions,
        placement.action_by_flow(),
        _table_utility(model),
        model.problem.planning_link_costs_ms(),
    )


def _add_primary_objective_equality(
    model: MILPLinearModel,
    primary_objective_minimize: float,
) -> tuple[LinearConstraintRow, ...]:
    coefficients = tuple(
        (index, value)
        for index, value in enumerate(model.objective_minimize)
        if value != 0.0
    )
    row = LinearConstraintRow(
        family="primary-objective-preservation",
        name="primary-objective-preservation",
        lower_bound=primary_objective_minimize,
        upper_bound=primary_objective_minimize,
        coefficients=coefficients,
    )
    return model.constraints + (row,)


def _canonicalize_optimal_solution(
    model: MILPLinearModel,
    primary: BackendRawResult,
    backend_solve: BackendSolve,
    solve_started: float,
) -> tuple[tuple[float, ...], bool]:
    """Lexicographically select flow actions while preserving primary welfare."""

    if primary.x is None or primary.objective_minimize is None:
        raise MILPContractError("optimal backend result has no incumbent")
    dimensions = model.problem.configuration.dimensions
    pair_variables = model.variables_in_family("p")
    pairs_per_flow = len(pair_variables) // dimensions.flow_count
    working_constraints = _add_primary_objective_equality(
        model,
        primary.objective_minimize,
    )
    current_values = primary.x
    for flow in dimensions.flow_ids:
        remaining = model.problem.configuration.cutoff_seconds - (
            monotonic() - solve_started
        )
        if remaining <= 0.0:
            return current_values, False
        secondary_objective = [0.0] * model.variable_count
        flow_pair_variables = tuple(
            variable for variable in pair_variables if variable.indices[0] == flow
        )
        for rank, variable in enumerate(flow_pair_variables, start=1):
            secondary_objective[variable.index] = float(rank)
        secondary_model = model.with_objective_and_constraints(
            objective_minimize=tuple(secondary_objective),
            constraints=working_constraints,
        )
        result = backend_solve(secondary_model, remaining)
        if result.status != 0 or result.x is None:
            return current_values, False
        _validate_solution_vector(secondary_model, result.x)
        selected = tuple(
            (rank, variable)
            for rank, variable in enumerate(flow_pair_variables, start=1)
            if result.x[variable.index] > 0.5
        )
        if len(selected) != 1:
            return current_values, False
        selected_rank, _variable = selected[0]
        rank_coefficients = tuple(
            (variable.index, float(rank))
            for rank, variable in enumerate(flow_pair_variables, start=1)
        )
        working_constraints = secondary_model.constraints + (
            LinearConstraintRow(
                family="canonical-action-fix",
                name=f"canonical-action-fix[{flow}]",
                lower_bound=float(selected_rank),
                upper_bound=float(selected_rank),
                coefficients=rank_coefficients,
            ),
        )
        current_values = result.x
    return current_values, True


def _error_result(
    problem: MILPProblemInput,
    *,
    build_seconds: float,
    solve_seconds: float,
    backend_version: str,
    reason: str,
    variable_count: int | None = None,
    constraint_count: int | None = None,
) -> MILPSolverResult:
    return MILPSolverResult(
        SolverRunProvenance(
            status=SolverResultStatus.SOLVER_OR_CONFIGURATION_ERROR,
            requested_cutoff_seconds=problem.configuration.cutoff_seconds,
            model_build_seconds=build_seconds,
            solve_seconds=solve_seconds,
            backend_name=SCIPY_HIGHS_BACKEND_NAME,
            backend_version=backend_version,
            termination_reason=reason,
            variable_count=variable_count,
            constraint_count=constraint_count,
        )
    )


def solve_coupled_milp(
    problem: MILPProblemInput,
    known_state_expected_utility: KnownStateExpectedUtility | None = None,
    *,
    backend_solve: BackendSolve = solve_scipy_highs,
    availability: BackendAvailability | None = None,
    canonicalize: bool = True,
) -> MILPSolverResult:
    """Build and solve the pure coupled MILP with normalized result semantics."""

    build_started = monotonic()
    try:
        model = build_coupled_milp_model(problem, known_state_expected_utility)
    except Exception as exc:
        build_seconds = monotonic() - build_started
        return _error_result(
            problem,
            build_seconds=build_seconds,
            solve_seconds=0.0,
            backend_version="unavailable",
            reason=f"model-build-error:{type(exc).__name__}:{exc}",
        )
    build_seconds = monotonic() - build_started
    try:
        backend = require_scipy_highs(availability)
    except Exception as exc:
        return _error_result(
            problem,
            build_seconds=build_seconds,
            solve_seconds=0.0,
            backend_version="unavailable",
            reason=f"backend-configuration-error:{type(exc).__name__}:{exc}",
            variable_count=model.variable_count,
            constraint_count=model.constraint_count,
        )
    version = _backend_version(backend)
    solve_started = monotonic()
    try:
        raw = backend_solve(model, problem.configuration.cutoff_seconds)
    except Exception as exc:
        return _error_result(
            problem,
            build_seconds=build_seconds,
            solve_seconds=monotonic() - solve_started,
            backend_version=version,
            reason=f"backend-error:{type(exc).__name__}:{exc}",
            variable_count=model.variable_count,
            constraint_count=model.constraint_count,
        )

    solution_values = raw.x
    canonicalization_complete = False
    if raw.status == 0 and canonicalize:
        try:
            solution_values, canonicalization_complete = _canonicalize_optimal_solution(
                model,
                raw,
                backend_solve,
                solve_started,
            )
        except Exception:
            solution_values = raw.x
            canonicalization_complete = False
    solve_seconds = monotonic() - solve_started
    reason = raw.message.strip() or f"scipy-status-{raw.status}"
    if raw.status == 0:
        reason += (
            ";canonicalization=complete"
            if canonicalization_complete
            else ";canonicalization=flow-label-only"
        )

    status_map = {
        0: SolverResultStatus.PROVEN_OPTIMAL,
        2: SolverResultStatus.INFEASIBLE,
        3: SolverResultStatus.UNBOUNDED,
        4: SolverResultStatus.SOLVER_OR_CONFIGURATION_ERROR,
    }
    if raw.status == 1:
        status = (
            SolverResultStatus.TIME_LIMIT_WITH_INCUMBENT
            if solution_values is not None
            else SolverResultStatus.TIME_LIMIT_WITHOUT_INCUMBENT
        )
    else:
        status = status_map.get(
            raw.status,
            SolverResultStatus.SOLVER_OR_CONFIGURATION_ERROR,
        )

    placement = None
    objective = None
    incumbent = None
    best_bound = None
    absolute_gap = None
    relative_gap = None
    if status in (
        SolverResultStatus.PROVEN_OPTIMAL,
        SolverResultStatus.TIME_LIMIT_WITH_INCUMBENT,
    ):
        if solution_values is None or raw.objective_minimize is None:
            return _error_result(
                problem,
                build_seconds=build_seconds,
                solve_seconds=solve_seconds,
                backend_version=version,
                reason="backend-result-error:incumbent status without solution/objective",
                variable_count=model.variable_count,
                constraint_count=model.constraint_count,
            )
        try:
            placement = _extract_placement(model, solution_values)
            objective = _solution_objective(model, placement)
        except Exception as exc:
            return _error_result(
                problem,
                build_seconds=build_seconds,
                solve_seconds=solve_seconds,
                backend_version=version,
                reason=f"solution-validation-error:{type(exc).__name__}:{exc}",
                variable_count=model.variable_count,
                constraint_count=model.constraint_count,
            )
        incumbent = objective.total_social_welfare_utility
        if not isclose(
            -raw.objective_minimize,
            incumbent,
            rel_tol=1e-8,
            abs_tol=1e-7,
        ):
            return _error_result(
                problem,
                build_seconds=build_seconds,
                solve_seconds=solve_seconds,
                backend_version=version,
                reason="solution-validation-error:backend objective mismatch",
                variable_count=model.variable_count,
                constraint_count=model.constraint_count,
            )
        if status is SolverResultStatus.PROVEN_OPTIMAL:
            best_bound = incumbent
            absolute_gap = relative_gap = 0.0
        else:
            if raw.dual_bound_minimize is None or not isfinite(
                raw.dual_bound_minimize
            ):
                return _error_result(
                    problem,
                    build_seconds=build_seconds,
                    solve_seconds=solve_seconds,
                    backend_version=version,
                    reason="backend-result-error:timed incumbent missing finite bound",
                    variable_count=model.variable_count,
                    constraint_count=model.constraint_count,
                )
            best_bound = -raw.dual_bound_minimize
            if best_bound < incumbent and isclose(
                best_bound,
                incumbent,
                rel_tol=1e-8,
                abs_tol=1e-7,
            ):
                best_bound = incumbent
            absolute_gap, relative_gap = normalized_solver_gaps(
                incumbent,
                best_bound,
            )
    elif status is SolverResultStatus.TIME_LIMIT_WITHOUT_INCUMBENT:
        if raw.dual_bound_minimize is not None and isfinite(raw.dual_bound_minimize):
            best_bound = -raw.dual_bound_minimize

    try:
        provenance = SolverRunProvenance(
            status=status,
            requested_cutoff_seconds=problem.configuration.cutoff_seconds,
            model_build_seconds=build_seconds,
            solve_seconds=solve_seconds,
            backend_name=SCIPY_HIGHS_BACKEND_NAME,
            backend_version=version,
            termination_reason=reason,
            incumbent_objective_utility=incumbent,
            best_bound_utility=best_bound,
            absolute_gap_utility=absolute_gap,
            relative_gap=relative_gap,
            variable_count=model.variable_count,
            constraint_count=model.constraint_count,
        )
        return MILPSolverResult(provenance, placement, objective)
    except Exception as exc:
        return _error_result(
            problem,
            build_seconds=build_seconds,
            solve_seconds=solve_seconds,
            backend_version=version,
            reason=f"result-normalization-error:{type(exc).__name__}:{exc}",
            variable_count=model.variable_count,
            constraint_count=model.constraint_count,
        )
