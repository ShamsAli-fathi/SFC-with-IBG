import ast
import inspect
import os
from pathlib import Path
import subprocess
import sys

import pytest

from MILP.phase0_contract import (
    ASSIGNED_FLOW_CAPACITY_UNIT,
    CUTOFF_UNIT,
    DEFAULT_MILP_DIMENSIONS,
    DEVELOPMENT_BACKEND_FAMILY,
    GAP_UNIT,
    LEGACY_PROTOTYPE_MISMATCHES,
    MILLISECONDS_UNIT,
    MILP_ACTION_CARDINALITY,
    MILP_CONSTRAINT_FAMILIES,
    MILPContractError,
    MILP_DETERMINISM_CONTRACT,
    MILP_DIMENSION_CLI_OPTIONS,
    MILP_DIMENSION_CONFIGURATION_MODE,
    MILPDimensions,
    MILP_GAP_NORMALIZATION,
    MILP_INFORMATION_BOUNDARY,
    MILP_OBJECTIVE_CONTRACT,
    MILP_PHASE0_CONTRACT_VERSION,
    MILP_VARIABLE_FAMILIES,
    PAPER_MILP_BACKEND,
    PAPER_MILP_BACKEND_VERSION,
    ReplicaAdmission,
    ReplicaKey,
    SolverResultStatus,
    SolverRunProvenance,
    TwoStageAction,
    UTILITY_UNIT,
    evaluate_placement_feasibility,
    reconstruct_social_welfare,
    normalized_solver_gaps,
    required_directed_pairs,
    validate_cutoff_seconds,
    validate_planning_link_metadata,
)


ROOT = Path(__file__).resolve().parents[1]
MILP_DIR = ROOT / "MILP"


def _source(name: str) -> str:
    return (MILP_DIR / name).read_text(encoding="utf-8")


def _tree(name: str) -> ast.Module:
    return ast.parse(_source(name), filename=str(MILP_DIR / name))


def _function(name: str, function_name: str) -> ast.FunctionDef:
    for node in _tree(name).body:
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            return node
    raise AssertionError(f"missing {function_name} in {name}")


def _literal_assignment(name: str, variable: str):
    for node in _tree(name).body:
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == variable for target in node.targets)
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"missing literal assignment {variable} in {name}")


def _links(dimensions: MILPDimensions, value: float = 0.0):
    return {pair: value for pair in required_directed_pairs(dimensions)}


def _admission(dimensions: MILPDimensions, capacity: int | None = None):
    limit = dimensions.flow_count if capacity is None else capacity
    return {
        key: ReplicaAdmission(ready=True, assigned_flow_capacity=limit)
        for key in dimensions.replica_keys
    }


def _solver_provenance(status: SolverResultStatus, **overrides):
    values = {
        "status": status,
        "requested_cutoff_seconds": 12.5,
        "model_build_seconds": 0.2,
        "solve_seconds": 3.4,
        "backend_name": "test-backend",
        "backend_version": "1.0",
        "termination_reason": status.value,
        "variable_count": 10,
        "constraint_count": 20,
    }
    values.update(overrides)
    return SolverRunProvenance(**values)


def test_phase0_contract_import_is_silent_and_has_no_result_file_side_effect(tmp_path):
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT)
    before = tuple(tmp_path.iterdir())

    completed = subprocess.run(
        [sys.executable, "-c", "import MILP.phase0_contract"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert completed.stderr == ""
    assert tuple(tmp_path.iterdir()) == before


def test_default_dimensions_are_an_initial_profile_with_frozen_units_and_backend_boundary():
    dimensions = DEFAULT_MILP_DIMENSIONS

    assert MILP_PHASE0_CONTRACT_VERSION == "milp-coupled-phase0-contract-v1"
    assert dimensions.flow_count == 15
    assert dimensions.flow_ids == tuple(range(1, 16))
    assert dimensions.stage_count == 3
    assert dimensions.stage_ids == (1, 2, 3)
    assert dimensions.replicas_per_stage == (10, 10, 10)
    assert dimensions.total_replica_count == 30
    assert len(dimensions.replica_keys) == 30
    assert MILP_ACTION_CARDINALITY == dimensions.selected_stage_count == 2
    assert MILP_DIMENSION_CONFIGURATION_MODE == "runtime-configurable-dimensions-v1"
    assert MILP_DIMENSION_CLI_OPTIONS == ("--flow", "--stage", "--replica")
    assert MILLISECONDS_UNIT == "milliseconds"
    assert UTILITY_UNIT == "utility-units"
    assert ASSIGNED_FLOW_CAPACITY_UNIT == "assigned-flows-per-slot"
    assert CUTOFF_UNIT == "wall-clock-seconds"
    assert GAP_UNIT == "dimensionless"
    assert MILP_GAP_NORMALIZATION.startswith("absolute=abs")
    assert (PAPER_MILP_BACKEND, PAPER_MILP_BACKEND_VERSION) == ("Gurobi", "10.0")
    assert DEVELOPMENT_BACKEND_FAMILY == "scipy.optimize.milp/HiGHS"


def test_flow_stage_and_replica_dimensions_are_runtime_configurable():
    dimensions = MILPDimensions(
        flow_count=7,
        replicas_per_stage=(2, 4, 6, 8),
    )

    assert dimensions.flow_ids == tuple(range(1, 8))
    assert dimensions.stage_count == 4
    assert dimensions.stage_ids == (1, 2, 3, 4)
    assert dimensions.replicas_per_stage == (2, 4, 6, 8)
    assert dimensions.total_replica_count == 20
    assert dimensions.selected_stage_count == 2
    assert TwoStageAction.canonical(
        ReplicaKey(1, 1),
        ReplicaKey(3, 1),
    ).bypassed_stages(dimensions) == (2, 4)


def test_action_is_exactly_two_distinct_stages_with_canonical_ids_and_one_bypass():
    action = TwoStageAction.canonical(ReplicaKey(3, 7), ReplicaKey(1, 2))

    assert action.selections == (ReplicaKey(1, 2), ReplicaKey(3, 7))
    assert action.directed_pair == action.selections
    assert action.bypassed_stages(DEFAULT_MILP_DIMENSIONS) == (2,)

    with pytest.raises(MILPContractError, match="distinct"):
        TwoStageAction((ReplicaKey(1, 1), ReplicaKey(1, 2)))
    with pytest.raises(MILPContractError, match="canonical"):
        TwoStageAction((ReplicaKey(3, 1), ReplicaKey(1, 1)))
    with pytest.raises(MILPContractError, match="out of range"):
        TwoStageAction.canonical(ReplicaKey(1, 11), ReplicaKey(2, 1)).validate(
            DEFAULT_MILP_DIMENSIONS
        )
    with pytest.raises(MILPContractError, match="only exact L=2"):
        MILPDimensions(selected_stage_count=3)


def test_whole_slot_feasibility_enforces_ready_capacity_and_complete_links():
    dimensions = MILPDimensions(flow_count=2, replicas_per_stage=(1, 1, 1))
    actions = {
        1: TwoStageAction.canonical(ReplicaKey(1, 1), ReplicaKey(3, 1)),
        2: TwoStageAction.canonical(ReplicaKey(1, 1), ReplicaKey(2, 1)),
    }
    links = _links(dimensions, 1.0)
    admission = _admission(dimensions, capacity=2)

    accepted = evaluate_placement_feasibility(dimensions, actions, admission, links)

    assert accepted.feasible
    assert dict(accepted.final_loads) == {
        ReplicaKey(1, 1): 2,
        ReplicaKey(2, 1): 1,
        ReplicaKey(3, 1): 1,
    }

    rejected_admission = dict(admission)
    rejected_admission[ReplicaKey(1, 1)] = ReplicaAdmission(
        ready=False,
        assigned_flow_capacity=1,
    )
    rejected = evaluate_placement_feasibility(
        dimensions,
        actions,
        rejected_admission,
        links,
    )
    assert not rejected.feasible
    assert rejected.reasons == (
        "not-ready:1:1",
        "assigned-flow-capacity:1:1",
    )

    incomplete_links = dict(links)
    incomplete_links.pop(next(iter(incomplete_links)))
    with pytest.raises(MILPContractError, match="planning-link metadata mismatch"):
        validate_planning_link_metadata(dimensions, incomplete_links)

    negative_links = dict(links)
    negative_links[next(iter(negative_links))] = -0.1
    with pytest.raises(MILPContractError, match="must be nonnegative"):
        validate_planning_link_metadata(dimensions, negative_links)


def test_default_topology_requires_all_300_directed_pair_coefficients():
    pairs = required_directed_pairs(DEFAULT_MILP_DIMENSIONS)

    assert len(pairs) == 3 * 10 * 10 == 300
    assert pairs == tuple(sorted(pairs))
    assert all(source.stage < target.stage for source, target in pairs)


def test_final_load_social_welfare_is_centralized_and_deducts_one_planning_link_per_flow():
    dimensions = MILPDimensions(flow_count=2, replicas_per_stage=(1, 1, 1))
    actions = {
        1: TwoStageAction.canonical(ReplicaKey(1, 1), ReplicaKey(3, 1)),
        2: TwoStageAction.canonical(ReplicaKey(1, 1), ReplicaKey(2, 1)),
    }
    links = {
        (ReplicaKey(1, 1), ReplicaKey(2, 1)): 2.0,
        (ReplicaKey(1, 1), ReplicaKey(3, 1)): 5.0,
        (ReplicaKey(2, 1), ReplicaKey(3, 1)): 3.0,
    }
    calls = []

    def known_state_utility(key: ReplicaKey, final_load: int) -> float:
        calls.append((key, final_load))
        return 100.0 - 10.0 * final_load - key.stage

    result = reconstruct_social_welfare(
        dimensions,
        actions,
        known_state_utility,
        links,
    )

    assert calls.count((ReplicaKey(1, 1), 2)) == 2
    assert (ReplicaKey(2, 1), 1) in calls
    assert (ReplicaKey(3, 1), 1) in calls
    assert result.stage_welfare_utility == pytest.approx(333.0)
    assert result.planning_link_cost_ms == pytest.approx(7.0)
    assert result.total_social_welfare_utility == pytest.approx(326.0)
    assert tuple(flow.flow_id for flow in result.flows) == (1, 2)
    assert "measured" not in inspect.signature(reconstruct_social_welfare).parameters


def test_perfect_state_information_boundary_excludes_learning_and_outcome_telemetry():
    boundary = MILP_INFORMATION_BOUNDARY

    assert "replica-true-performance-state" in boundary.planner_inputs
    assert "state-load-conditioned-expected-physical-utility" in boundary.planner_inputs
    assert "belief-vectors" in boundary.prohibited_planner_inputs
    assert "private-learning-signals" in boundary.prohibited_planner_inputs
    assert "sequential-flow-order" in boundary.prohibited_planner_inputs
    assert "observation-only-jitter" in boundary.prohibited_planner_inputs
    assert "measured-pair-latency" in boundary.prohibited_planner_inputs
    assert "measured-selected-pair-latency" in boundary.outcome_only_values


def test_variable_constraint_and_determinism_contracts_are_complete():
    assert tuple(family.symbol for family in MILP_VARIABLE_FAMILIES) == (
        "x[i,k,j]",
        "y[i,k]",
        "z[k,j,n]",
        "p[i,k,j,k2,j2]",
    )
    assert {family.name for family in MILP_CONSTRAINT_FAMILIES} == {
        "exact-stage-cardinality",
        "one-replica-per-selected-stage",
        "ready-availability",
        "declared-assigned-flow-capacity",
        "one-final-load-indicator",
        "final-load-reconstruction",
        "directed-pair-linearization",
        "one-selected-directed-pair",
        "planning-link-input-completeness",
    }
    assert "n*U_true_state" in MILP_OBJECTIVE_CONTRACT
    assert "link_ms" in MILP_OBJECTIVE_CONTRACT
    assert "symmetric optimal placements" in MILP_DETERMINISM_CONTRACT
    assert "epsilon perturbation" in MILP_DETERMINISM_CONTRACT


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), -float("inf")])
def test_cutoff_rejects_nonpositive_and_nonfinite_values(value):
    with pytest.raises(MILPContractError):
        validate_cutoff_seconds(value)


@pytest.mark.parametrize("value", [0.001, 1, 12.5, 600.0])
def test_cutoff_accepts_positive_finite_seconds_without_rounding(value):
    assert validate_cutoff_seconds(value) == float(value)


def test_solver_status_schema_distinguishes_proof_timeout_and_failures():
    assert normalized_solver_gaps(90.0, 100.0) == pytest.approx((10.0, 10.0 / 90.0))
    optimal = _solver_provenance(
        SolverResultStatus.PROVEN_OPTIMAL,
        incumbent_objective_utility=100.0,
        best_bound_utility=100.0,
        absolute_gap_utility=0.0,
        relative_gap=0.0,
    )
    timed_incumbent = _solver_provenance(
        SolverResultStatus.TIME_LIMIT_WITH_INCUMBENT,
        incumbent_objective_utility=90.0,
        best_bound_utility=100.0,
        absolute_gap_utility=10.0,
        relative_gap=10.0 / 90.0,
    )
    timed_without = _solver_provenance(
        SolverResultStatus.TIME_LIMIT_WITHOUT_INCUMBENT,
        best_bound_utility=100.0,
    )
    failures = (
        _solver_provenance(SolverResultStatus.INFEASIBLE),
        _solver_provenance(SolverResultStatus.UNBOUNDED),
        _solver_provenance(SolverResultStatus.SOLVER_OR_CONFIGURATION_ERROR),
    )

    assert optimal.optimality_proven
    assert not timed_incumbent.optimality_proven
    assert not timed_without.optimality_proven
    assert all(not result.optimality_proven for result in failures)
    assert timed_incumbent.requested_cutoff_seconds == 12.5
    assert timed_incumbent.model_build_seconds == 0.2
    assert timed_incumbent.solve_seconds == 3.4
    assert timed_incumbent.variable_count == 10
    assert timed_incumbent.constraint_count == 20

    with pytest.raises(MILPContractError, match="proven optimal requires"):
        _solver_provenance(SolverResultStatus.PROVEN_OPTIMAL)
    with pytest.raises(MILPContractError, match="cannot report incumbent"):
        _solver_provenance(
            SolverResultStatus.TIME_LIMIT_WITHOUT_INCUMBENT,
            incumbent_objective_utility=1.0,
        )


def test_legacy_mismatch_catalog_has_one_entry_for_every_phase0_characterization():
    identifiers = tuple(item.identifier for item in LEGACY_PROTOTYPE_MISMATCHES)

    assert len(identifiers) == len(set(identifiers)) == 12
    assert set(identifiers) == {
        "import-time-side-effects",
        "default-decoupled-path",
        "replica-dimension",
        "ignored-budget-hard-coded-b20",
        "random-cost-budget",
        "arbitrary-stage-skipping",
        "missing-admission-and-link-constraints",
        "obsolete-utility-and-learning",
        "global-rng-mutation",
        "incomplete-solver-provenance",
        "broken-budgeted-result-shape",
        "undeclared-ortools-dependency",
    }


def test_historical_legacy_entry_point_side_effect_mismatch_remains_recorded():
    mismatch = {item.identifier: item for item in LEGACY_PROTOTYPE_MISMATCHES}[
        "import-time-side-effects"
    ]

    assert "executes experiments" in mismatch.summary
    assert "prints" in mismatch.summary
    assert "file writers" in mismatch.summary
    assert mismatch.evidence_files == ("MILP/milp_main.py", "MILP/report.py")


def test_historical_decoupled_and_replica_dimension_mismatches_remain_recorded():
    mismatches = {item.identifier: item for item in LEGACY_PROTOTYPE_MISMATCHES}

    assert "is_budgeted=0" in mismatches["default-decoupled-path"].summary
    assert "90 total" in mismatches["replica-dimension"].summary
    assert "30 total" in mismatches["replica-dimension"].replacement_contract


def test_historical_budget_mismatches_remain_recorded():
    mismatches = {item.identifier: item for item in LEGACY_PROTOTYPE_MISMATCHES}

    assert "hard-codes B=20" in mismatches["ignored-budget-hard-coded-b20"].summary
    assert "random replica costs" in mismatches["random-cost-budget"].summary
    assert "exact L=2" in mismatches["random-cost-budget"].replacement_contract


def test_historical_skipping_and_constraint_mismatches_remain_recorded():
    mismatches = {item.identifier: item for item in LEGACY_PROTOTYPE_MISMATCHES}

    assert "allow_skip" in mismatches["arbitrary-stage-skipping"].summary
    assert "exactly two" in mismatches["arbitrary-stage-skipping"].replacement_contract
    assert "Ready status" in mismatches["missing-admission-and-link-constraints"].summary
    assert "directed planning links" in mismatches[
        "missing-admission-and-link-constraints"
    ].summary


def test_historical_obsolete_utility_and_learning_mismatch_remains_recorded():
    mismatch = {item.identifier: item for item in LEGACY_PROTOTYPE_MISMATCHES}[
        "obsolete-utility-and-learning"
    ]

    assert "two states" in mismatch.summary
    assert "inverse utility" in mismatch.summary
    assert "retention 0.7" in mismatch.summary
    assert "known true state" in mismatch.replacement_contract


def test_legacy_mutates_global_rng_and_accepts_feasible_without_bound_gap_provenance():
    combined = "\n".join(
        _source(name) for name in ("milp_header.py", "milp_header_b.py", "milp_main.py")
    )

    assert "random.shuffle" in combined
    assert "random.seed" in combined
    assert "solver.FEASIBLE" in combined or "pywraplp.Solver.FEASIBLE" in combined
    assert "BestBound" not in combined
    assert "best_bound" not in combined
    assert "relative_gap" not in combined


def test_historical_broken_budgeted_result_shape_remains_recorded():
    mismatch = {item.identifier: item for item in LEGACY_PROTOTYPE_MISMATCHES}[
        "broken-budgeted-result-shape"
    ]

    assert "returns (assignment, counts)" in mismatch.summary
    assert "passes the tuple" in mismatch.summary
    assert "immutable coupled result contract" in mismatch.replacement_contract


def test_legacy_ortools_dependency_is_imported_but_not_declared():
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()

    assert "from ortools.linear_solver import pywraplp" in _source("milp_header.py")
    assert "ortools" not in requirements
