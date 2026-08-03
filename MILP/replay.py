"""Solver-independent mathematical and outcome replay for MILP Phase 6."""

from __future__ import annotations

from dataclasses import dataclass
from math import isclose
from types import SimpleNamespace
from typing import Callable

from IBG import latency_model as exact_latency

from .contracts import MILPProblemInput, MILPSolverResult
from .kernel_contracts import (
    MILP_PHASE5_KERNEL_CONTRACT_VERSION,
    MILP_TWO_HOP_ROUTE_CONTRACT_VERSION,
)
from .model import exact_known_state_expected_utility
from .phase0_contract import (
    MILPContractError,
    SolverResultStatus,
    reconstruct_social_welfare,
)
from .runner import _compute_metrics, _validate_simulation_result
from .solver import solve_coupled_milp
from .trace_contracts import (
    MILP_PHASE6_TRACE_CONTRACT_VERSION,
    MILPSelectedPlanningLink,
    MILPTrace,
    MILPTraceSource,
    MILPTraceVersions,
)


MILP_PHASE6_REPLAY_VERSION = "milp-coupled-phase6-replay-v1"
REPLAY_REL_TOL = 1e-12
REPLAY_ABS_TOL = 1e-9


class MILPReplayError(MILPContractError):
    def __init__(self, category: str, detail: str) -> None:
        self.category = category
        self.detail = detail
        super().__init__(f"{category}-drift: {detail}")


@dataclass(frozen=True)
class MILPReplayReport:
    replay_version: str
    source: MILPTraceSource
    slot_id: int
    checks: tuple[str, ...]
    reconstructed_stage_welfare_utility: float
    reconstructed_planning_link_cost_ms: float
    reconstructed_total_social_welfare_utility: float
    reconstructed_physical_realized_utility: float
    reconstructed_physical_only_sla_violations: int
    reconstructed_jain_fairness: float


@dataclass(frozen=True)
class MILPSolverReplayReport:
    replay_version: str
    original_status: SolverResultStatus
    replay_status: SolverResultStatus | None
    canonical_comparison_required: bool
    objective_matches: bool | None
    placement_matches: bool | None
    note: str


def _close(actual: float, expected: float) -> bool:
    return isclose(
        float(actual),
        float(expected),
        rel_tol=REPLAY_REL_TOL,
        abs_tol=REPLAY_ABS_TOL,
    )


def _require_close(category: str, field: str, actual: float, expected: float) -> None:
    if not _close(actual, expected):
        raise MILPReplayError(category, f"{field}: recorded={actual}, replayed={expected}")


def _require_equal(category: str, field: str, actual: object, expected: object) -> None:
    if actual != expected:
        raise MILPReplayError(category, f"{field} does not match replay")


def _canonical_http_endpoint(value: str) -> str:
    """Normalize the representation-only root slash added by AnyHttpUrl."""

    return value.rstrip("/")


def _validate_versions(trace: MILPTrace) -> None:
    if trace.contract_version != MILP_PHASE6_TRACE_CONTRACT_VERSION:
        raise MILPReplayError("contract", "unexpected trace version")
    if trace.versions.phase6_trace != MILP_PHASE6_TRACE_CONTRACT_VERSION:
        raise MILPReplayError("contract", "version manifest does not match trace")
    expected = (
        MILPTraceVersions()
        if trace.source is MILPTraceSource.PURE
        else MILPTraceVersions(
            phase5_kernel=MILP_PHASE5_KERNEL_CONTRACT_VERSION,
            route=MILP_TWO_HOP_ROUTE_CONTRACT_VERSION,
        )
    )
    if trace.versions != expected:
        raise MILPReplayError("contract", "phase-version manifest does not match source")


def _validate_kernel_identities(trace: MILPTrace) -> None:
    dimensions = trace.private_planner_input.configuration.dimensions
    if trace.source is MILPTraceSource.PURE:
        if trace.kernel_endpoints:
            raise MILPReplayError("identity", "pure trace carries Kernel endpoints")
        return
    endpoint_by_key = {item.key: item for item in trace.kernel_endpoints}
    if len(endpoint_by_key) != len(trace.kernel_endpoints) or set(endpoint_by_key) != set(dimensions.replica_keys):
        raise MILPReplayError("identity", "Kernel endpoint coverage is incomplete")
    for observation in trace.observations:
        endpoint = endpoint_by_key.get(observation.key)
        if (
            endpoint is None
            or observation.pod_name != endpoint.pod_name
            or _canonical_http_endpoint(observation.endpoint)
            != _canonical_http_endpoint(endpoint.endpoint)
        ):
            raise MILPReplayError("identity", f"observation identity differs for {observation.key}")
    actions = trace.placement.action_by_flow()
    for pair in trace.measured_pairs:
        action = actions.get(pair.flow_id)
        if action is None or pair.source != action.directed_pair[0] or pair.target != action.directed_pair[1]:
            raise MILPReplayError("identity", f"measured pair differs for flow {pair.flow_id}")
        source = endpoint_by_key[pair.source]
        target = endpoint_by_key[pair.target]
        if (
            pair.source_pod_name != source.pod_name
            or pair.target_pod_name != target.pod_name
            or _canonical_http_endpoint(pair.target_endpoint)
            != _canonical_http_endpoint(target.endpoint)
        ):
            raise MILPReplayError("identity", f"measured-pair endpoint differs for flow {pair.flow_id}")


def _validate_placement(trace: MILPTrace) -> None:
    problem = trace.private_planner_input
    dimensions = problem.configuration.dimensions
    try:
        trace.placement.validate_for(problem)
    except (MILPContractError, KeyError) as error:
        raise MILPReplayError("placement", str(error)) from error
    _require_equal(
        "placement",
        "solver incumbent placement",
        trace.placement,
        trace.solver_result.placement,
    )
    _require_equal(
        "load",
        "final replica loads",
        trace.final_replica_loads,
        trace.placement.final_loads,
    )
    actions = trace.placement.action_by_flow()
    expected_bypasses = tuple(
        (flow_id, actions[flow_id].bypassed_stages(dimensions))
        for flow_id in dimensions.flow_ids
    )
    _require_equal(
        "placement",
        "bypassed stages",
        trace.bypassed_stages_by_flow,
        expected_bypasses,
    )


def _validate_selected_links(trace: MILPTrace) -> None:
    problem = trace.private_planner_input
    link_by_pair = {link.pair: link for link in problem.planning_links}
    expected = tuple(
        MILPSelectedPlanningLink(flow_id, link_by_pair[action.directed_pair])
        for flow_id, action in trace.placement.actions
    )
    _require_equal(
        "coefficient",
        "selected configured planning links",
        trace.selected_planning_links,
        expected,
    )


def _validate_solver_status(trace: MILPTrace) -> None:
    provenance = trace.solver_result.provenance
    configuration = trace.private_planner_input.configuration
    if provenance.status not in (
        SolverResultStatus.PROVEN_OPTIMAL,
        SolverResultStatus.TIME_LIMIT_WITH_INCUMBENT,
    ):
        raise MILPReplayError("solver-status", "executed trace has no feasible incumbent")
    _require_close(
        "solver-status",
        "requested cutoff",
        provenance.requested_cutoff_seconds,
        configuration.cutoff_seconds,
    )
    _require_equal(
        "solver-status", "metric status", trace.metrics.solver_status, provenance.status
    )
    if provenance.incumbent_objective_utility is None:
        raise MILPReplayError("solver-status", "incumbent objective is absent")
    _require_close(
        "solver-status",
        "metric incumbent",
        trace.metrics.incumbent_objective_utility,
        provenance.incumbent_objective_utility,
    )
    for field in (
        "best_bound_utility",
        "absolute_gap_utility",
        "relative_gap",
        "model_build_seconds",
        "solve_seconds",
    ):
        expected = getattr(provenance, field)
        metric_field = "solver_seconds" if field == "solve_seconds" else field
        metric_field = "model_build_seconds" if field == "model_build_seconds" else metric_field
        actual = getattr(trace.metrics, metric_field)
        if expected is None:
            raise MILPReplayError("solver-status", f"{field} is absent")
        _require_close("solver-status", field, actual, expected)


def _reconstruct_objective(trace: MILPTrace):
    problem = trace.private_planner_input
    reconstructed = reconstruct_social_welfare(
        problem.configuration.dimensions,
        trace.placement.action_by_flow(),
        exact_known_state_expected_utility(problem),
        problem.planning_link_costs_ms(),
    )
    recorded = trace.solver_result.objective
    if recorded is None:
        raise MILPReplayError("objective", "solver objective is absent")
    _require_equal("objective", "objective final loads", recorded.final_loads, reconstructed.final_loads)
    if len(recorded.flows) != len(reconstructed.flows):
        raise MILPReplayError("objective", "per-flow objective count differs")
    for actual, expected in zip(recorded.flows, reconstructed.flows, strict=True):
        _require_equal("objective", "flow/action", (actual.flow_id, actual.action), (expected.flow_id, expected.action))
        _require_close("objective", f"flow {actual.flow_id} stage utility", actual.stage_utility, expected.stage_utility)
        _require_close("coefficient", f"flow {actual.flow_id} planning link", actual.planning_link_cost_ms, expected.planning_link_cost_ms)
        _require_close("objective", f"flow {actual.flow_id} total", actual.total_utility, expected.total_utility)
    for field in (
        "stage_welfare_utility",
        "planning_link_cost_ms",
        "total_social_welfare_utility",
    ):
        _require_close("objective", field, getattr(recorded, field), getattr(reconstructed, field))
    _require_close(
        "objective",
        "incumbent objective",
        trace.solver_result.provenance.incumbent_objective_utility,
        reconstructed.total_social_welfare_utility,
    )
    _require_close("objective", "metric expected stage welfare", trace.metrics.solver_expected_stage_welfare_utility, reconstructed.stage_welfare_utility)
    _require_close("coefficient", "metric configured planning-link cost", trace.metrics.solver_configured_planning_link_cost_ms, reconstructed.planning_link_cost_ms)
    _require_close("objective", "metric social welfare", trace.metrics.solver_total_social_welfare_utility, reconstructed.total_social_welfare_utility)
    return reconstructed


_REPLAYED_METRIC_FIELDS = (
    "solver_expected_stage_welfare_utility",
    "solver_configured_planning_link_cost_ms",
    "solver_configured_planning_link_deduction_utility",
    "solver_total_social_welfare_utility",
    "physical_realized_utility",
    "physical_realized_utility_per_flow",
    "physical_processing_latency_ms",
    "physical_processing_latency_ms_per_flow",
    "measured_pair_latency_ms",
    "measured_pair_latency_ms_per_flow",
    "raw_end_to_end_latency_ms",
    "raw_end_to_end_latency_ms_per_flow",
    "physical_plus_pair_reference_utility",
    "physical_plus_pair_reference_utility_per_flow",
    "physical_only_sla_violations",
    "jain_fairness",
)


def _compare_metric_value(field: str, actual: object, expected: object) -> None:
    category = "sla" if field == "physical_only_sla_violations" else "fairness" if field == "jain_fairness" else "metric"
    if isinstance(actual, tuple) and isinstance(expected, tuple):
        if len(actual) != len(expected):
            raise MILPReplayError(category, f"{field} length differs")
        for recorded, replayed in zip(actual, expected, strict=True):
            if recorded[0] != replayed[0]:
                raise MILPReplayError(category, f"{field} flow IDs differ")
            _require_close(category, f"{field}[{recorded[0]}]", recorded[1], replayed[1])
    elif isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        _require_close(category, field, actual, expected)
    else:
        _require_equal(category, field, actual, expected)


def _reconstruct_outcomes(trace: MILPTrace):
    shim = SimpleNamespace(problem=trace.private_planner_input)
    simulation = SimpleNamespace(
        observations=trace.observations,
        measured_pairs=trace.measured_pairs,
    )
    try:
        _validate_simulation_result(shim, trace.solver_result, simulation)
    except (MILPContractError, RuntimeError, KeyError) as error:
        message = str(error)
        category = "observation-count" if "observation" in message else "pair-count" if "pair" in message else "outcome"
        raise MILPReplayError(category, message) from error
    replayed = _compute_metrics(
        slot_input=shim,
        solver_result=trace.solver_result,
        simulation=simulation,
        simulation_seconds=trace.metrics.simulation_seconds,
        total_slot_seconds=trace.metrics.total_slot_seconds,
    )
    for field in _REPLAYED_METRIC_FIELDS:
        _compare_metric_value(field, getattr(trace.metrics, field), getattr(replayed, field))
    return replayed


def replay_milp_trace(trace: MILPTrace) -> MILPReplayReport:
    """Replay one trace without building or solving a MILP model."""

    if not isinstance(trace, MILPTrace):
        raise MILPContractError("trace must be MILPTrace")
    _validate_versions(trace)
    _validate_placement(trace)
    _validate_kernel_identities(trace)
    _validate_selected_links(trace)
    _validate_solver_status(trace)
    objective = _reconstruct_objective(trace)
    metrics = _reconstruct_outcomes(trace)
    return MILPReplayReport(
        replay_version=MILP_PHASE6_REPLAY_VERSION,
        source=trace.source,
        slot_id=trace.slot_id,
        checks=(
            "contracts",
            "placement-feasibility",
            "final-loads",
            "configured-planning-links",
            "solver-status",
            "social-welfare-objective",
            "selected-observations",
            "measured-pairs",
            "physical-only-utility-and-sla",
            "raw-reference-utility",
            "jain-fairness",
        ),
        reconstructed_stage_welfare_utility=objective.stage_welfare_utility,
        reconstructed_planning_link_cost_ms=objective.planning_link_cost_ms,
        reconstructed_total_social_welfare_utility=objective.total_social_welfare_utility,
        reconstructed_physical_realized_utility=metrics.physical_realized_utility,
        reconstructed_physical_only_sla_violations=metrics.physical_only_sla_violations,
        reconstructed_jain_fairness=metrics.jain_fairness,
    )


MILPSolver = Callable[[MILPProblemInput], MILPSolverResult]


def replay_milp_solver(
    trace: MILPTrace,
    *,
    solver: MILPSolver = solve_coupled_milp,
) -> MILPSolverReplayReport:
    """Optionally rerun the solver after deterministic mathematical replay.

    Only a recorded proven optimum requires canonical placement/objective
    equality.  A timed incumbent remains unproven and is never treated as a
    deterministic canonical-result contract.
    """

    replay_milp_trace(trace)
    original_status = trace.solver_result.provenance.status
    rerun = solver(trace.private_planner_input)
    if original_status is SolverResultStatus.PROVEN_OPTIMAL:
        if rerun.provenance.status is not SolverResultStatus.PROVEN_OPTIMAL:
            raise MILPReplayError("solver-status", "proven optimum was not reproved")
        if rerun.objective is None or rerun.placement is None:
            raise MILPReplayError("solver-status", "replay optimum has no incumbent")
        expected_objective = trace.solver_result.objective
        if expected_objective is None:
            raise MILPReplayError("objective", "recorded optimum has no objective")
        objective_matches = _close(
            rerun.objective.total_social_welfare_utility,
            expected_objective.total_social_welfare_utility,
        )
        placement_matches = rerun.placement == trace.placement
        if not objective_matches:
            raise MILPReplayError("objective", "solver replay optimum differs")
        if not placement_matches:
            raise MILPReplayError("placement", "solver replay canonical optimum differs")
        return MILPSolverReplayReport(
            MILP_PHASE6_REPLAY_VERSION,
            original_status,
            rerun.provenance.status,
            True,
            True,
            True,
            "proven canonical optimum reproduced",
        )
    return MILPSolverReplayReport(
        MILP_PHASE6_REPLAY_VERSION,
        original_status,
        rerun.provenance.status,
        False,
        None,
        None,
        "timed incumbent remains unproven; placement/objective identity not required",
    )
