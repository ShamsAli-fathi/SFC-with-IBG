"""Phase 3 pure in-memory orchestration for one coupled-MILP slot."""

from __future__ import annotations

import importlib
import sys
from dataclasses import replace
from math import isclose
from pathlib import Path
from time import monotonic
from typing import Callable

from IBG import latency_model as exact_latency
from IBG.outcome_latency import (
    DEFAULT_OUTCOME_LATENCY_MODE,
    outcome_latency_ms_per_flow,
)
from IBG.report import SLA_v

from .contracts import MILPProblemInput, MILPSolverResult
from .phase0_contract import (
    MILP_PLANNING_LINK_WEIGHT_UTILITY_PER_MS,
    MILPContractError,
    SolverResultStatus,
)
from .simulation import InProcessMILPSimulationAdapter, MILPSlotSimulationAdapter
from .slot_contracts import (
    MILPSimulationResult,
    MILPSlotInput,
    MILPSlotMetrics,
    MILPSlotResult,
)
from .solver import solve_coupled_milp


class MILPSlotExecutionError(RuntimeError):
    """Raised when a slot cannot execute a complete validated incumbent."""


MILPSolver = Callable[[MILPProblemInput], MILPSolverResult]


def _load_exact_header():
    """Load the frozen flat-import Exact metric module only during a run."""

    try:
        return importlib.import_module("header")
    except ModuleNotFoundError as error:
        if error.name != "header":
            raise
    exact_directory = str(Path(__file__).resolve().parents[1] / "IBG")
    sys.path.insert(0, exact_directory)
    try:
        return importlib.import_module("header")
    finally:
        if sys.path and sys.path[0] == exact_directory:
            del sys.path[0]


def _require_executable_incumbent(
    slot_input: MILPSlotInput,
    result: MILPSolverResult,
) -> None:
    if not isinstance(result, MILPSolverResult):
        raise MILPSlotExecutionError("solver returned an invalid result contract")
    accepted = {
        SolverResultStatus.PROVEN_OPTIMAL,
        SolverResultStatus.TIME_LIMIT_WITH_INCUMBENT,
    }
    if result.provenance.status not in accepted:
        raise MILPSlotExecutionError(
            "MILP slot requires a validated complete incumbent; "
            f"solver status={result.provenance.status.value}"
        )
    if result.placement is None or result.objective is None:
        raise MILPSlotExecutionError("incumbent status has no complete placement")
    if result.provenance.requested_cutoff_seconds != (
        slot_input.problem.configuration.cutoff_seconds
    ):
        raise MILPSlotExecutionError("solver cutoff provenance does not match slot input")
    try:
        result.placement.validate_for(slot_input.problem)
    except MILPContractError as error:
        raise MILPSlotExecutionError(f"invalid solver placement: {error}") from error


def _validate_simulation_result(
    slot_input: MILPSlotInput,
    solver_result: MILPSolverResult,
    simulation: MILPSimulationResult,
) -> None:
    placement = solver_result.placement
    if placement is None:
        raise MILPSlotExecutionError("simulation validation requires a placement")
    actions = placement.action_by_flow()
    final_loads = dict(placement.final_loads)
    expected_observations = {
        (flow_id, key)
        for flow_id, action in actions.items()
        for key in action.selections
    }
    actual_observations = {
        (observation.flow_id, observation.key)
        for observation in simulation.observations
    }
    if len(simulation.observations) != len(expected_observations) or (
        actual_observations != expected_observations
    ):
        raise MILPSlotExecutionError(
            "simulation observations do not exactly cover selected replicas"
        )
    for observation in simulation.observations:
        if observation.assigned_load != final_loads[observation.key]:
            raise MILPSlotExecutionError(
                "selected observation is not conditioned on final assigned load"
            )
        expected_likelihood = exact_latency.learning_signal_likelihood(
            observation.noisy_signal_ms,
            observation.assigned_load,
        )
        if any(
            not isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12)
            for actual, expected in zip(
                observation.likelihood,
                expected_likelihood,
                strict=True,
            )
        ):
            raise MILPSlotExecutionError(
                "selected likelihood is not conditioned on final assigned load"
            )
        if observation.estimated_state != exact_latency.estimate_state(
            observation.likelihood
        ):
            raise MILPSlotExecutionError(
                "selected estimated state does not match its likelihood"
            )

    expected_pairs = {
        (flow_id, *action.directed_pair)
        for flow_id, action in actions.items()
    }
    actual_pairs = {
        (outcome.flow_id, outcome.source, outcome.target)
        for outcome in simulation.measured_pairs
    }
    if len(simulation.measured_pairs) != len(actions) or actual_pairs != expected_pairs:
        raise MILPSlotExecutionError(
            "simulation must return exactly one selected-pair outcome per flow"
        )

    dimensions = slot_input.problem.configuration.dimensions
    if sum(load for _key, load in placement.final_loads) != (
        dimensions.flow_count * dimensions.selected_stage_count
    ):
        raise MILPSlotExecutionError("placement assignment count is incomplete")


def _pairs(values: dict[int, float]) -> tuple[tuple[int, float], ...]:
    return tuple((flow_id, float(values[flow_id])) for flow_id in sorted(values))


def _compute_metrics(
    *,
    slot_input: MILPSlotInput,
    solver_result: MILPSolverResult,
    simulation: MILPSimulationResult,
    simulation_seconds: float,
    total_slot_seconds: float,
) -> MILPSlotMetrics:
    objective = solver_result.objective
    if objective is None:
        raise MILPSlotExecutionError("metrics require a solver objective")
    dimensions = slot_input.problem.configuration.dimensions
    physical_latency = {flow_id: 0.0 for flow_id in dimensions.flow_ids}
    physical_utility = {flow_id: 0.0 for flow_id in dimensions.flow_ids}
    for observation in simulation.observations:
        physical_latency[observation.flow_id] += (
            observation.physical_processing_latency_ms
        )
        physical_utility[observation.flow_id] += (
            exact_latency.DEFAULT_REWARD
            - exact_latency.DEFAULT_LATENCY_WEIGHT
            * observation.physical_processing_latency_ms
            - exact_latency.DEFAULT_COST
        )

    measured_pair_latency = {
        outcome.flow_id: outcome.latency_ms
        for outcome in simulation.measured_pairs
    }
    raw_end_to_end_latency = {
        flow_id: physical_latency[flow_id] + measured_pair_latency[flow_id]
        for flow_id in dimensions.flow_ids
    }
    reference_utility = {
        flow_id: physical_utility[flow_id]
        - exact_latency.DEFAULT_LINK_LATENCY_WEIGHT
        * measured_pair_latency[flow_id]
        for flow_id in dimensions.flow_ids
    }
    physical_only_outcome = outcome_latency_ms_per_flow(
        physical_latency,
        measured_pair_latency,
        DEFAULT_OUTCOME_LATENCY_MODE,
    )
    sla_violations = SLA_v(
        physical_only_outcome,
        exact_latency.DEFAULT_SLA_LATENCY_MS,
    )

    # Exact and Hybrid report Jain fairness over the planner's expected
    # per-flow aggregate utility. Preserve that common comparison basis while
    # retaining realized per-flow utility separately.
    expected_per_flow = {
        item.flow_id: item.total_utility for item in objective.flows
    }
    exact_header = _load_exact_header()
    fairness_input = {
        flow_id: [expected_per_flow[flow_id]]
        for flow_id in dimensions.flow_ids
    }
    fairness = exact_header.jain_index(
        fairness_input,
        objective.total_social_welfare_utility,
    )

    provenance = solver_result.provenance
    if any(
        value is None
        for value in (
            provenance.incumbent_objective_utility,
            provenance.best_bound_utility,
            provenance.absolute_gap_utility,
            provenance.relative_gap,
        )
    ):
        raise MILPSlotExecutionError("executable incumbent lacks bound/gap provenance")
    planning_deduction = (
        MILP_PLANNING_LINK_WEIGHT_UTILITY_PER_MS
        * objective.planning_link_cost_ms
    )
    if not isclose(
        objective.stage_welfare_utility - planning_deduction,
        objective.total_social_welfare_utility,
        rel_tol=1e-12,
        abs_tol=1e-9,
    ):
        raise MILPSlotExecutionError("solver objective components do not reconstruct")

    return MILPSlotMetrics(
        solver_expected_stage_welfare_utility=objective.stage_welfare_utility,
        solver_configured_planning_link_cost_ms=objective.planning_link_cost_ms,
        solver_configured_planning_link_deduction_utility=planning_deduction,
        solver_total_social_welfare_utility=objective.total_social_welfare_utility,
        physical_realized_utility=sum(physical_utility.values()),
        physical_realized_utility_per_flow=_pairs(physical_utility),
        physical_processing_latency_ms=sum(physical_latency.values()),
        physical_processing_latency_ms_per_flow=_pairs(physical_latency),
        measured_pair_latency_ms=sum(measured_pair_latency.values()),
        measured_pair_latency_ms_per_flow=_pairs(measured_pair_latency),
        raw_end_to_end_latency_ms=sum(raw_end_to_end_latency.values()),
        raw_end_to_end_latency_ms_per_flow=_pairs(raw_end_to_end_latency),
        physical_plus_pair_reference_utility=sum(reference_utility.values()),
        physical_plus_pair_reference_utility_per_flow=_pairs(reference_utility),
        physical_only_sla_violations=sla_violations,
        jain_fairness=float(fairness),
        model_build_seconds=provenance.model_build_seconds,
        solver_seconds=provenance.solve_seconds,
        simulation_seconds=simulation_seconds,
        total_slot_seconds=total_slot_seconds,
        solver_status=provenance.status,
        incumbent_objective_utility=float(provenance.incumbent_objective_utility),
        best_bound_utility=float(provenance.best_bound_utility),
        absolute_gap_utility=float(provenance.absolute_gap_utility),
        relative_gap=float(provenance.relative_gap),
    )


def run_milp_slot(
    slot_input: MILPSlotInput,
    *,
    solver: MILPSolver = solve_coupled_milp,
    simulation_adapter: MILPSlotSimulationAdapter | None = None,
) -> MILPSlotResult:
    """Solve one whole slot and execute only a validated complete incumbent."""

    if not isinstance(slot_input, MILPSlotInput):
        raise MILPContractError("slot_input must be MILPSlotInput")
    if simulation_adapter is None:
        simulation_adapter = InProcessMILPSimulationAdapter()
    slot_started = monotonic()
    solver_result = solver(slot_input.problem)
    _require_executable_incumbent(slot_input, solver_result)
    placement = solver_result.placement
    if placement is None:
        raise MILPSlotExecutionError("validated result unexpectedly lacks placement")

    simulation_started = monotonic()
    simulation = simulation_adapter.execute(slot_input, placement)
    simulation_seconds = monotonic() - simulation_started
    _validate_simulation_result(slot_input, solver_result, simulation)
    metrics = _compute_metrics(
        slot_input=slot_input,
        solver_result=solver_result,
        simulation=simulation,
        simulation_seconds=simulation_seconds,
        total_slot_seconds=0.0,
    )
    metrics = replace(metrics, total_slot_seconds=monotonic() - slot_started)
    dimensions = slot_input.problem.configuration.dimensions
    actions = placement.action_by_flow()
    return MILPSlotResult(
        configuration=slot_input.problem.configuration,
        root_seed=slot_input.root_seed,
        slot_id=slot_input.slot_id,
        solver_result=solver_result,
        placement=placement,
        bypassed_stages_by_flow=tuple(
            (flow_id, actions[flow_id].bypassed_stages(dimensions))
            for flow_id in dimensions.flow_ids
        ),
        final_replica_loads=placement.final_loads,
        observations=simulation.observations,
        measured_pairs=simulation.measured_pairs,
        metrics=metrics,
    )


def format_milp_slot_metrics(result: MILPSlotResult) -> str:
    metrics = result.metrics
    return (
        f"MILP slot={result.slot_id} status={metrics.solver_status.value} "
        f"expected={metrics.solver_total_social_welfare_utility:.3f} "
        f"realized={metrics.physical_realized_utility:.3f} "
        f"sla={metrics.physical_only_sla_violations} "
        f"jain={metrics.jain_fairness:.6f} "
        f"gap={metrics.relative_gap:.6g} "
        f"runtime={metrics.total_slot_seconds:.6f}s"
    )


def run_and_print_milp_slot(
    slot_input: MILPSlotInput,
    *,
    solver: MILPSolver = solve_coupled_milp,
    simulation_adapter: MILPSlotSimulationAdapter | None = None,
) -> MILPSlotResult:
    """Explicit wrapper that prints exactly one line after successful completion."""

    result = run_milp_slot(
        slot_input,
        solver=solver,
        simulation_adapter=simulation_adapter,
    )
    print(format_milp_slot_metrics(result))
    return result
