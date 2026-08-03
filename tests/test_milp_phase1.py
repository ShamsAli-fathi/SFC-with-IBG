from dataclasses import FrozenInstanceError
import os
from pathlib import Path
import subprocess
import sys

import pytest

from MILP.backend import (
    BackendAvailability,
    MILPBackendUnavailable,
    detect_scipy_highs,
    require_scipy_highs,
)
from MILP.cli import main, parse_configuration
from MILP.contracts import (
    MILP_PHASE1_CONTRACT_VERSION,
    DirectedPlanningLink,
    MILPConfiguration,
    MILPPlacement,
    MILPProblemInput,
    MILPSolverResult,
    ReplicaPlanningInput,
    build_problem_input,
)
from MILP.milp_header_b import RetiredMILPPrototypeError
from MILP.oracle import (
    NoFeasibleMILPPlacement,
    TinyOracleScopeError,
    solve_tiny_exhaustive,
)
from MILP.phase0_contract import (
    DEFAULT_MILP_DIMENSIONS,
    DEVELOPMENT_BACKEND_FAMILY,
    MILP_ACTION_CARDINALITY,
    MILPContractError,
    MILPDimensions,
    ReplicaAdmission,
    ReplicaKey,
    SocialWelfareBreakdown,
    SolverResultStatus,
    SolverRunProvenance,
    TwoStageAction,
    required_directed_pairs,
)


ROOT = Path(__file__).resolve().parents[1]
SUPPORTED_MODULES = (
    "MILP",
    "MILP.phase0_contract",
    "MILP.contracts",
    "MILP.backend",
    "MILP.model",
    "MILP.solver",
    "MILP.oracle",
    "MILP.cli",
    "MILP.__main__",
    "MILP.milp_main",
    "MILP.milp_header",
    "MILP.milp_header_b",
    "MILP.report",
)


def _problem(
    dimensions: MILPDimensions,
    *,
    capacity: int | None = None,
    link_cost: float = 0.0,
    cutoff: float = 5.0,
) -> MILPProblemInput:
    limit = dimensions.flow_count if capacity is None else capacity
    admission = {
        key: ReplicaAdmission(ready=True, assigned_flow_capacity=limit)
        for key in dimensions.replica_keys
    }
    true_states = {key: 4 for key in dimensions.replica_keys}
    links = {pair: link_cost for pair in required_directed_pairs(dimensions)}
    return build_problem_input(
        MILPConfiguration(dimensions=dimensions, cutoff_seconds=cutoff),
        true_states=true_states,
        admission=admission,
        planning_link_cost_ms=links,
    )


def test_all_supported_milp_imports_are_silent_rng_neutral_and_file_safe(tmp_path):
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT)
    modules = repr(SUPPORTED_MODULES)
    code = (
        "import importlib, random, numpy as np; "
        "random.seed(917); np.random.seed(918); "
        "before=random.getstate(); np_before=np.random.get_state(); "
        f"[importlib.import_module(name) for name in {modules}]; "
        "assert random.getstate() == before; "
        "np_after=np.random.get_state(); "
        "assert np_after[0] == np_before[0] and "
        "np.array_equal(np_after[1], np_before[1]) and "
        "np_after[2:] == np_before[2:]"
    )

    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert completed.stderr == ""
    assert tuple(tmp_path.iterdir()) == ()


def test_cli_defaults_dimensions_but_requires_explicit_cutoff():
    configuration = parse_configuration(["--cutoff", "12.5"])

    assert configuration.dimensions == DEFAULT_MILP_DIMENSIONS
    assert configuration.cutoff_seconds == 12.5
    assert configuration.action_cardinality == MILP_ACTION_CARDINALITY == 2

    with pytest.raises(SystemExit):
        parse_configuration([])


def test_cli_accepts_runtime_dimensions_and_preserves_cutoff_exactly():
    configuration = parse_configuration(
        [
            "--flow",
            "7",
            "--stage",
            "5",
            "--replica",
            "4",
            "--cutoff",
            "3.125",
        ]
    )

    assert configuration.dimensions.flow_count == 7
    assert configuration.dimensions.stage_count == 5
    assert configuration.dimensions.replicas_per_stage == (4, 4, 4, 4, 4)
    assert configuration.dimensions.total_replica_count == 20
    assert configuration.cutoff_seconds == 3.125
    action = TwoStageAction.canonical(ReplicaKey(2, 1), ReplicaKey(5, 4))
    assert action.bypassed_stages(configuration.dimensions) == (1, 3, 4)


@pytest.mark.parametrize(
    "arguments",
    [
        ["--flow", "0", "--cutoff", "1"],
        ["--flow", "-1", "--cutoff", "1"],
        ["--flow", "1.5", "--cutoff", "1"],
        ["--stage", "0", "--cutoff", "1"],
        ["--stage", "1", "--cutoff", "1"],
        ["--stage", "2.5", "--cutoff", "1"],
        ["--replica", "0", "--cutoff", "1"],
        ["--replica", "-2", "--cutoff", "1"],
        ["--replica", "3.5", "--cutoff", "1"],
        ["--cutoff", "0"],
        ["--cutoff", "-1"],
        ["--cutoff", "nan"],
        ["--cutoff", "inf"],
    ],
)
def test_cli_rejects_invalid_dimensions_and_cutoffs(arguments):
    with pytest.raises(SystemExit):
        parse_configuration(arguments)


def test_exact_l2_cannot_be_changed_for_any_runtime_dimensions():
    configuration = MILPConfiguration.uniform(
        flow_count=1,
        stage_count=8,
        replicas_per_stage=1,
        cutoff_seconds=2.0,
    )

    assert configuration.action_cardinality == 2
    with pytest.raises(MILPContractError, match="only exact L=2"):
        MILPConfiguration(
            dimensions=configuration.dimensions,
            cutoff_seconds=2.0,
            action_cardinality=3,
        )


def test_phase1_contracts_are_immutable_and_reuse_phase0_types():
    problem = _problem(MILPDimensions(flow_count=1, replicas_per_stage=(1, 1)))

    assert MILP_PHASE1_CONTRACT_VERSION == "milp-coupled-phase1-boundary-v1"
    assert isinstance(problem.configuration.dimensions, MILPDimensions)
    assert all(isinstance(item.key, ReplicaKey) for item in problem.replicas)
    assert all(isinstance(item.admission, ReplicaAdmission) for item in problem.replicas)
    assert all(isinstance(item, DirectedPlanningLink) for item in problem.planning_links)
    with pytest.raises(FrozenInstanceError):
        problem.configuration.cutoff_seconds = 9.0
    with pytest.raises(FrozenInstanceError):
        problem.replicas[0].true_state = 1


def test_problem_input_rejects_incomplete_true_state_admission_and_link_metadata():
    dimensions = MILPDimensions(flow_count=1, replicas_per_stage=(1, 1))
    configuration = MILPConfiguration(dimensions, 1.0)
    keys = dimensions.replica_keys
    admission = {key: ReplicaAdmission(True, 1) for key in keys}
    links = {pair: 0.0 for pair in required_directed_pairs(dimensions)}

    with pytest.raises(MILPContractError, match="true-state metadata"):
        build_problem_input(
            configuration,
            true_states={keys[0]: 4},
            admission=admission,
            planning_link_cost_ms=links,
        )
    with pytest.raises(MILPContractError, match="admission metadata mismatch"):
        build_problem_input(
            configuration,
            true_states={key: 4 for key in keys},
            admission={keys[0]: admission[keys[0]]},
            planning_link_cost_ms=links,
        )
    with pytest.raises(MILPContractError, match="planning-link metadata mismatch"):
        build_problem_input(
            configuration,
            true_states={key: 4 for key in keys},
            admission=admission,
            planning_link_cost_ms={},
        )


def test_backend_gate_reports_local_scipy_and_embedded_highs_without_solving():
    availability = detect_scipy_highs()

    assert availability.available
    assert availability.family == DEVELOPMENT_BACKEND_FAMILY
    assert availability.scipy_version == "1.18.0"
    assert availability.highs_version == "1.12.0"
    assert require_scipy_highs(availability) is availability


def test_backend_gate_has_explicit_helpful_missing_backend_error():
    availability = detect_scipy_highs(module_finder=lambda _name: None)

    assert not availability.available
    assert availability.scipy_version is None
    assert "SciPy scipy.optimize.milp" in availability.detail
    with pytest.raises(MILPBackendUnavailable, match="Phase 2"):
        require_scipy_highs(availability)


def test_tiny_oracle_uses_final_load_welfare_and_canonical_ties():
    problem = _problem(MILPDimensions(flow_count=2, replicas_per_stage=(1, 1, 1)))

    result = solve_tiny_exhaustive(
        problem,
        lambda key, load: 100.0 - 10.0 * load - key.stage,
    )

    assert result.complete_placements_considered == 9
    assert result.feasible_placements == 9
    assert isinstance(result.objective, SocialWelfareBreakdown)
    assert result.objective.total_social_welfare_utility == pytest.approx(333.0)
    # Spreading load wins; among equal optima enumeration keeps the first
    # complete canonical action tuple.
    assert result.placement.actions == (
        (1, TwoStageAction.canonical(ReplicaKey(1, 1), ReplicaKey(2, 1))),
        (2, TwoStageAction.canonical(ReplicaKey(1, 1), ReplicaKey(3, 1))),
    )
    result.placement.validate_for(problem)


def test_tiny_oracle_rejects_infeasibility_without_partial_placement():
    problem = _problem(
        MILPDimensions(flow_count=1, replicas_per_stage=(1, 1, 1)),
        capacity=0,
    )

    with pytest.raises(NoFeasibleMILPPlacement, match="no feasible complete L=2"):
        solve_tiny_exhaustive(problem, lambda _key, _load: 1.0)


def test_tiny_oracle_explicitly_refuses_default_production_boundary():
    problem = _problem(DEFAULT_MILP_DIMENSIONS)

    with pytest.raises(TinyOracleScopeError, match="15x3x10"):
        solve_tiny_exhaustive(problem, lambda _key, _load: 1.0)


def test_solver_result_wraps_phase0_status_and_objective_without_redefining_them():
    problem = _problem(MILPDimensions(flow_count=1, replicas_per_stage=(1, 1)))
    oracle = solve_tiny_exhaustive(problem, lambda _key, _load: 10.0)
    value = oracle.objective.total_social_welfare_utility
    provenance = SolverRunProvenance(
        status=SolverResultStatus.PROVEN_OPTIMAL,
        requested_cutoff_seconds=problem.configuration.cutoff_seconds,
        model_build_seconds=0.0,
        solve_seconds=0.0,
        backend_name="test-oracle",
        backend_version="phase1",
        termination_reason="exhaustive-test-only",
        incumbent_objective_utility=value,
        best_bound_utility=value,
        absolute_gap_utility=0.0,
        relative_gap=0.0,
    )

    result = MILPSolverResult(provenance, oracle.placement, oracle.objective)

    assert result.provenance.optimality_proven
    assert result.objective is oracle.objective


def test_guarded_cli_reports_configuration_only_and_does_not_fabricate_result(capsys):
    exit_code = main(["--cutoff", "2.75"])

    output = capsys.readouterr().out.strip()
    assert exit_code == 0
    assert "flows=15 stages=3 replicas-per-stage=10 L=2 cutoff=2.75s" in output
    assert "solver API ready" in output
    assert "Phase 3 slot API ready for a fully supplied MILPSlotInput" in output
    assert "does not fabricate planner or simulation profiles" in output


def test_retired_budgeted_solver_fails_explicitly_instead_of_loading_ortools():
    from MILP.milp_header_b import MILP_solver_budgeted

    with pytest.raises(RetiredMILPPrototypeError, match="solve_coupled_milp"):
        MILP_solver_budgeted()
