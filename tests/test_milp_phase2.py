from types import SimpleNamespace

import pytest

from IBG.latency_model import expected_state_utility
from MILP.backend import BackendAvailability
from MILP.contracts import MILPConfiguration, build_problem_input
from MILP.model import (
    MILP_PHASE2_MODEL_VERSION,
    build_coupled_milp_model,
    exact_known_state_expected_utility,
)
from MILP.oracle import solve_tiny_exhaustive
from MILP.phase0_contract import (
    DEFAULT_MILP_DIMENSIONS,
    MILPDimensions,
    ReplicaAdmission,
    ReplicaKey,
    SolverResultStatus,
    required_directed_pairs,
)
from MILP.solver import (
    MILP_PHASE2_SOLVER_VERSION,
    BackendRawResult,
    solve_coupled_milp,
    solve_scipy_highs,
)


LOCAL_BACKEND = BackendAvailability(
    family="scipy.optimize.milp/HiGHS",
    available=True,
    scipy_version="1.18.0",
    highs_version="1.12.0",
    detail="test fixture",
)


def _problem(
    dimensions: MILPDimensions,
    *,
    cutoff: float = 5.0,
    capacity: int | None = None,
    ready_overrides: dict[ReplicaKey, bool] | None = None,
    states: dict[ReplicaKey, int] | None = None,
    link_costs: dict[tuple[ReplicaKey, ReplicaKey], float] | None = None,
):
    limit = dimensions.flow_count if capacity is None else capacity
    ready_overrides = ready_overrides or {}
    admission = {
        key: ReplicaAdmission(
            ready=ready_overrides.get(key, True),
            assigned_flow_capacity=limit,
        )
        for key in dimensions.replica_keys
    }
    true_states = states or {key: 4 for key in dimensions.replica_keys}
    links = link_costs or {
        pair: 0.0 for pair in required_directed_pairs(dimensions)
    }
    return build_problem_input(
        MILPConfiguration(dimensions, cutoff),
        true_states=true_states,
        admission=admission,
        planning_link_cost_ms=links,
    )


def _utility(key: ReplicaKey, load: int) -> float:
    return 100.0 - 10.0 * load - key.stage - 0.1 * key.replica


def test_backend_neutral_model_has_exact_phase0_variable_and_constraint_families():
    dimensions = MILPDimensions(flow_count=2, replicas_per_stage=(1, 1, 1))
    model = build_coupled_milp_model(_problem(dimensions), _utility)

    assert model.version == MILP_PHASE2_MODEL_VERSION
    assert model.variable_count == 27
    assert {family: len(model.variables_in_family(family)) for family in ("x", "y", "z", "p")} == {
        "x": 6,
        "y": 6,
        "z": 9,
        "p": 6,
    }
    assert model.constraint_count == 43
    families = {row.family for row in model.constraints}
    assert families == {
        "exact-stage-cardinality",
        "one-replica-per-selected-stage",
        "ready-availability",
        "declared-assigned-flow-capacity",
        "one-final-load-indicator",
        "final-load-reconstruction",
        "directed-pair-linearization-upper-left",
        "directed-pair-linearization-upper-right",
        "directed-pair-linearization-lower",
        "one-selected-directed-pair",
    }
    assert all(value == 1 for value in model.integrality)
    assert all(value == 0.0 for value in model.lower_bounds)
    assert all(value == 1.0 for value in model.upper_bounds)


def test_model_objective_is_negative_final_load_welfare_plus_one_link_per_flow():
    dimensions = MILPDimensions(flow_count=1, replicas_per_stage=(1, 1))
    pair = required_directed_pairs(dimensions)[0]
    model = build_coupled_milp_model(
        _problem(dimensions, link_costs={pair: 7.5}),
        lambda _key, _load: 11.0,
    )

    z_left = model.variable_index("z", (1, 1, 1))
    z_right = model.variable_index("z", (2, 1, 1))
    p = model.variable_index("p", (1, 1, 1, 2, 1))
    assert model.objective_minimize[z_left] == -11.0
    assert model.objective_minimize[z_right] == -11.0
    assert model.objective_minimize[p] == 7.5
    assert all(
        model.objective_minimize[variable.index] == 0.0
        for family in ("x", "y")
        for variable in model.variables_in_family(family)
    )


def test_default_15x3x10_model_builds_expected_counts_without_solving():
    model = build_coupled_milp_model(_problem(DEFAULT_MILP_DIMENSIONS))

    assert model.variable_count == 5475
    assert model.constraint_count == 14115
    assert len(model.expected_utilities) == 30 * 15
    assert len(model.variables_in_family("p")) == 15 * 300


def test_default_expected_utility_reuses_unchanged_exact_true_state_helper():
    dimensions = MILPDimensions(flow_count=2, replicas_per_stage=(1, 1))
    states = {ReplicaKey(1, 1): 1, ReplicaKey(2, 1): 4}
    problem = _problem(dimensions, states=states)
    callback = exact_known_state_expected_utility(problem)
    model = build_coupled_milp_model(problem)

    for key in dimensions.replica_keys:
        for load in dimensions.flow_ids:
            assert callback(key, load) == expected_state_utility(states[key], load)
            assert model.expected_utility(key, load) == expected_state_utility(
                states[key], load
            )


def test_scipy_highs_optimum_matches_tiny_exhaustive_final_load_welfare():
    dimensions = MILPDimensions(flow_count=2, replicas_per_stage=(1, 1, 1))
    problem = _problem(dimensions)
    oracle = solve_tiny_exhaustive(problem, _utility)

    result = solve_coupled_milp(problem, _utility)

    assert result.provenance.status is SolverResultStatus.PROVEN_OPTIMAL
    assert result.provenance.optimality_proven
    assert result.provenance.absolute_gap_utility == 0.0
    assert result.provenance.relative_gap == 0.0
    assert result.objective.total_social_welfare_utility == pytest.approx(
        oracle.objective.total_social_welfare_utility
    )
    assert result.placement == oracle.placement
    assert "canonicalization=complete" in result.provenance.termination_reason


def test_joint_link_cost_changes_selected_two_stage_action():
    dimensions = MILPDimensions(flow_count=1, replicas_per_stage=(1, 1, 1))
    pairs = required_directed_pairs(dimensions)
    links = {pairs[0]: 100.0, pairs[1]: 20.0, pairs[2]: 1.0}
    problem = _problem(dimensions, link_costs=links)

    result = solve_coupled_milp(
        problem,
        lambda _key, _load: 100.0,
    )

    assert result.provenance.status is SolverResultStatus.PROVEN_OPTIMAL
    assert result.placement.actions[0][1].selections == (
        ReplicaKey(2, 1),
        ReplicaKey(3, 1),
    )
    assert result.objective.stage_welfare_utility == 200.0
    assert result.objective.planning_link_cost_ms == 1.0
    assert result.objective.total_social_welfare_utility == 199.0


def test_ready_and_capacity_constraints_produce_explicit_infeasibility():
    dimensions = MILPDimensions(flow_count=1, replicas_per_stage=(1, 1))
    capacity_result = solve_coupled_milp(
        _problem(dimensions, capacity=0),
        _utility,
        canonicalize=False,
    )
    readiness_result = solve_coupled_milp(
        _problem(
            dimensions,
            ready_overrides={ReplicaKey(1, 1): False},
        ),
        _utility,
        canonicalize=False,
    )

    for result in (capacity_result, readiness_result):
        assert result.provenance.status is SolverResultStatus.INFEASIBLE
        assert not result.provenance.optimality_proven
        assert result.placement is None
        assert result.objective is None


def test_nondefault_k_selects_exactly_two_and_bypasses_k_minus_two():
    dimensions = MILPDimensions(flow_count=1, replicas_per_stage=(1, 1, 1, 1))
    problem = _problem(dimensions)

    result = solve_coupled_milp(problem, lambda _key, _load: 10.0)

    action = result.placement.actions[0][1]
    assert len(action.selections) == 2
    assert len(action.bypassed_stages(dimensions)) == dimensions.stage_count - 2 == 2
    assert sum(load for _key, load in result.placement.final_loads) == 2


def test_native_scipy_adapter_receives_requested_cutoff_unchanged(monkeypatch):
    dimensions = MILPDimensions(flow_count=1, replicas_per_stage=(1, 1))
    model = build_coupled_milp_model(_problem(dimensions), _utility)
    captured = {}

    def fake_milp(*, c, integrality, bounds, constraints, options):
        captured["options"] = dict(options)
        return SimpleNamespace(
            status=2,
            message="infeasible fixture",
            x=None,
            fun=None,
            mip_dual_bound=None,
            mip_gap=None,
            mip_node_count=0,
        )

    import scipy.optimize

    monkeypatch.setattr(scipy.optimize, "milp", fake_milp)
    raw = solve_scipy_highs(model, 3.125)

    assert raw.status == 2
    assert captured["options"]["time_limit"] == 3.125
    assert captured["options"]["mip_rel_gap"] == 0.0
    assert captured["options"]["disp"] is False


def test_native_scipy_adapter_supports_explicit_verbose_progress(monkeypatch):
    dimensions = MILPDimensions(flow_count=1, replicas_per_stage=(1, 1))
    model = build_coupled_milp_model(_problem(dimensions), _utility)
    captured = {}

    def fake_milp(*, c, integrality, bounds, constraints, options):
        captured["options"] = dict(options)
        return SimpleNamespace(
            status=2,
            message="verbose fixture",
            x=None,
            fun=None,
            mip_dual_bound=None,
            mip_gap=None,
            mip_node_count=0,
        )

    import scipy.optimize

    monkeypatch.setattr(scipy.optimize, "milp", fake_milp)
    solve_scipy_highs(model, 2.0, display=True)

    assert captured["options"]["disp"] is True


def test_public_solver_passes_cutoff_unchanged_and_records_model_counts():
    dimensions = MILPDimensions(flow_count=1, replicas_per_stage=(1, 1))
    problem = _problem(dimensions, cutoff=1.234)
    seen = []

    def capture(model, cutoff):
        seen.append(cutoff)
        return solve_scipy_highs(model, cutoff)

    result = solve_coupled_milp(
        problem,
        _utility,
        backend_solve=capture,
        availability=LOCAL_BACKEND,
        canonicalize=False,
    )

    assert seen == [1.234]
    assert result.provenance.requested_cutoff_seconds == 1.234
    assert result.provenance.variable_count == 9
    assert result.provenance.constraint_count == 15


def test_timeout_with_incumbent_retains_bound_and_normalized_gap():
    dimensions = MILPDimensions(flow_count=1, replicas_per_stage=(1, 1))
    problem = _problem(dimensions)
    model = build_coupled_milp_model(problem, _utility)
    optimal = solve_scipy_highs(model, 5.0)
    assert optimal.x is not None
    assert optimal.objective_minimize is not None

    def timed(_model, _cutoff):
        return BackendRawResult(
            status=1,
            message="time limit",
            x=optimal.x,
            objective_minimize=optimal.objective_minimize,
            dual_bound_minimize=optimal.objective_minimize - 5.0,
        )

    result = solve_coupled_milp(
        problem,
        _utility,
        backend_solve=timed,
        availability=LOCAL_BACKEND,
        canonicalize=False,
    )

    assert result.provenance.status is SolverResultStatus.TIME_LIMIT_WITH_INCUMBENT
    assert not result.provenance.optimality_proven
    assert result.placement is not None
    assert result.provenance.best_bound_utility == pytest.approx(
        result.provenance.incumbent_objective_utility + 5.0
    )
    assert result.provenance.absolute_gap_utility == pytest.approx(5.0)
    assert result.provenance.relative_gap == pytest.approx(
        5.0 / abs(result.provenance.incumbent_objective_utility)
    )


def test_timeout_without_incumbent_is_distinct_and_retains_available_bound():
    problem = _problem(MILPDimensions(flow_count=1, replicas_per_stage=(1, 1)))

    def timed(_model, _cutoff):
        return BackendRawResult(
            status=1,
            message="time limit without solution",
            dual_bound_minimize=-123.0,
        )

    result = solve_coupled_milp(
        problem,
        _utility,
        backend_solve=timed,
        availability=LOCAL_BACKEND,
        canonicalize=False,
    )

    assert result.provenance.status is SolverResultStatus.TIME_LIMIT_WITHOUT_INCUMBENT
    assert result.provenance.best_bound_utility == 123.0
    assert result.provenance.incumbent_objective_utility is None
    assert result.placement is None


@pytest.mark.parametrize(
    ("raw_status", "expected"),
    [
        (2, SolverResultStatus.INFEASIBLE),
        (3, SolverResultStatus.UNBOUNDED),
        (4, SolverResultStatus.SOLVER_OR_CONFIGURATION_ERROR),
        (99, SolverResultStatus.SOLVER_OR_CONFIGURATION_ERROR),
    ],
)
def test_backend_terminal_statuses_are_normalized(raw_status, expected):
    problem = _problem(MILPDimensions(flow_count=1, replicas_per_stage=(1, 1)))

    result = solve_coupled_milp(
        problem,
        _utility,
        backend_solve=lambda _model, _cutoff: BackendRawResult(
            status=raw_status,
            message=f"raw status {raw_status}",
        ),
        availability=LOCAL_BACKEND,
        canonicalize=False,
    )

    assert result.provenance.status is expected
    assert result.placement is None
    assert result.objective is None


def test_backend_exception_and_invalid_solution_become_configuration_errors():
    problem = _problem(MILPDimensions(flow_count=1, replicas_per_stage=(1, 1)))

    def explode(_model, _cutoff):
        raise RuntimeError("backend exploded")

    exception_result = solve_coupled_milp(
        problem,
        _utility,
        backend_solve=explode,
        availability=LOCAL_BACKEND,
        canonicalize=False,
    )
    invalid_result = solve_coupled_milp(
        problem,
        _utility,
        backend_solve=lambda model, _cutoff: BackendRawResult(
            status=0,
            message="invalid fixture",
            x=(0.0,) * model.variable_count,
            objective_minimize=0.0,
            dual_bound_minimize=0.0,
        ),
        availability=LOCAL_BACKEND,
        canonicalize=False,
    )

    assert exception_result.provenance.status is SolverResultStatus.SOLVER_OR_CONFIGURATION_ERROR
    assert "backend-error" in exception_result.provenance.termination_reason
    assert invalid_result.provenance.status is SolverResultStatus.SOLVER_OR_CONFIGURATION_ERROR
    assert "solution-validation-error" in invalid_result.provenance.termination_reason


def test_repeated_symmetric_solves_are_canonical_and_deterministic():
    problem = _problem(MILPDimensions(flow_count=2, replicas_per_stage=(2, 2)))

    first = solve_coupled_milp(problem, lambda _key, _load: 10.0)
    second = solve_coupled_milp(problem, lambda _key, _load: 10.0)

    assert first.provenance.status is SolverResultStatus.PROVEN_OPTIMAL
    assert second.provenance.status is SolverResultStatus.PROVEN_OPTIMAL
    assert first.placement == second.placement
    assert first.objective.total_social_welfare_utility == 40.0
    assert first.placement.actions == (
        (1, first.placement.actions[0][1]),
        (2, first.placement.actions[1][1]),
    )
    assert "canonicalization=complete" in first.provenance.termination_reason
    assert MILP_PHASE2_SOLVER_VERSION == "milp-coupled-phase2-solver-v1"
