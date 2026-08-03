"""Pure controller-side orchestration for one MILP Kernel slot."""

from __future__ import annotations

from dataclasses import replace
from time import monotonic
from typing import Callable, Protocol

from .contracts import MILPProblemInput, MILPSolverResult
from .kernel_contracts import (
    MILPKernelSlotInput,
    MILPKernelSlotMetrics,
    MILPKernelSlotResult,
    MILPKernelTrafficResult,
)
from .runner import (
    MILPSlotExecutionError,
    _compute_metrics,
    _require_executable_incumbent,
    _validate_simulation_result,
)
from .solver import solve_coupled_milp


MILPKernelSolver = Callable[[MILPProblemInput], MILPSolverResult]


class MILPKernelTrafficAdapter(Protocol):
    def execute(self, slot_input, placement) -> MILPKernelTrafficResult: ...


def run_milp_kernel_slot(
    slot_input: MILPKernelSlotInput,
    *,
    solver: MILPKernelSolver = solve_coupled_milp,
    traffic_adapter: MILPKernelTrafficAdapter,
) -> MILPKernelSlotResult:
    """Solve exactly once, then execute only the complete validated incumbent."""

    if not isinstance(slot_input, MILPKernelSlotInput):
        raise TypeError("slot_input must be MILPKernelSlotInput")
    slot_started = monotonic()
    solver_result = solver(slot_input.problem)
    # Reuse the frozen Phase 3 cutoff/status/placement gate unchanged.
    _require_executable_incumbent(slot_input, solver_result)
    placement = solver_result.placement
    if placement is None:
        raise MILPSlotExecutionError("validated result unexpectedly lacks placement")

    traffic_started = monotonic()
    traffic = traffic_adapter.execute(slot_input, placement)
    traffic_seconds = monotonic() - traffic_started
    # These frozen validators and metric helpers are structural/algorithm-neutral
    # and intentionally accept the Phase 5 observation objects by their fields.
    _validate_simulation_result(slot_input, solver_result, traffic)
    common_metrics = _compute_metrics(
        slot_input=slot_input,
        solver_result=solver_result,
        simulation=traffic,
        simulation_seconds=traffic_seconds,
        total_slot_seconds=0.0,
    )
    total_seconds = monotonic() - slot_started
    common_metrics = replace(common_metrics, total_slot_seconds=total_seconds)
    dimensions = slot_input.problem.configuration.dimensions
    actions = placement.action_by_flow()
    return MILPKernelSlotResult(
        configuration=slot_input.problem.configuration,
        slot_id=slot_input.slot_id,
        solver_result=solver_result,
        placement=placement,
        bypassed_stages_by_flow=tuple(
            (flow_id, actions[flow_id].bypassed_stages(dimensions))
            for flow_id in dimensions.flow_ids
        ),
        final_replica_loads=placement.final_loads,
        endpoints=slot_input.endpoints,
        observations=traffic.observations,
        measured_pairs=traffic.measured_pairs,
        metrics=MILPKernelSlotMetrics(
            common=common_metrics,
            traffic_seconds=traffic_seconds,
            total_slot_seconds=total_seconds,
        ),
    )


def format_milp_kernel_metrics(result: MILPKernelSlotResult) -> str:
    metrics = result.metrics.common
    dimensions = result.configuration.dimensions
    return (
        f"MILP-Kernel scale={dimensions.flow_count}x{dimensions.stage_count}x"
        f"{dimensions.replicas_per_stage[0]} slot={result.slot_id} "
        f"cutoff={result.configuration.cutoff_seconds:g}s "
        f"status={metrics.solver_status.value} "
        f"optimal={int(result.solver_result.provenance.optimality_proven)} "
        f"incumbent={metrics.incumbent_objective_utility:.6g} "
        f"bound={metrics.best_bound_utility:.6g} gap={metrics.relative_gap:.6g} "
        f"routes={len(result.placement.actions)} "
        f"observations={len(result.observations)} "
        f"pairs={len(result.measured_pairs)} "
        f"expected-stage={metrics.solver_expected_stage_welfare_utility:.3f} "
        f"planning={metrics.solver_configured_planning_link_cost_ms:.3f} "
        f"social={metrics.solver_total_social_welfare_utility:.3f} "
        f"realized={metrics.physical_realized_utility:.3f} "
        f"physical-ms={metrics.physical_processing_latency_ms:.3f} "
        f"measured-pair-ms={metrics.measured_pair_latency_ms:.3f} "
        f"raw-ms={metrics.raw_end_to_end_latency_ms:.3f} "
        f"reference={metrics.physical_plus_pair_reference_utility:.3f} "
        f"sla={metrics.physical_only_sla_violations} "
        f"jain={metrics.jain_fairness:.6f} "
        f"solve={metrics.solver_seconds:.6f}s "
        f"traffic={result.metrics.traffic_seconds:.6f}s "
        f"total={result.metrics.total_slot_seconds:.6f}s"
    )


def run_and_print_milp_kernel_slot(
    slot_input: MILPKernelSlotInput,
    *,
    solver: MILPKernelSolver = solve_coupled_milp,
    traffic_adapter: MILPKernelTrafficAdapter,
) -> MILPKernelSlotResult:
    result = run_milp_kernel_slot(
        slot_input,
        solver=solver,
        traffic_adapter=traffic_adapter,
    )
    print(format_milp_kernel_metrics(result), flush=True)
    return result
