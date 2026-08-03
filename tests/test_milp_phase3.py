from dataclasses import FrozenInstanceError, replace
import os
from pathlib import Path
import random
import subprocess
import sys

import numpy as np
import pytest

from IBG import latency_model as exact_latency
from IBG.report import SLA_v
from MILP.contracts import (
    MILPConfiguration,
    MILPPlacement,
    MILPSolverResult,
    build_problem_input,
)
from MILP.model import exact_known_state_expected_utility
from MILP.phase0_contract import (
    MILPContractError,
    MILPDimensions,
    ReplicaAdmission,
    ReplicaKey,
    SolverResultStatus,
    SolverRunProvenance,
    TwoStageAction,
    reconstruct_social_welfare,
    required_directed_pairs,
)
from MILP.runner import (
    MILPSlotExecutionError,
    run_and_print_milp_slot,
    run_milp_slot,
)
from MILP.simulation import InProcessMILPSimulationAdapter
from MILP.slot_contracts import (
    MILP_MEASURED_PAIR_SEED_SCHEME,
    MILP_OBSERVATION_SEED_SCHEME,
    MILP_PHASE3_SLOT_CONTRACT_VERSION,
    MILP_PHYSICAL_SEED_SCHEME,
    MILPMeasuredPairOutcome,
    MILPSelectedObservation,
    MILPSimulationResult,
    MILPSlotInput,
    MeasuredPairLatencyProfile,
)


ROOT = Path(__file__).resolve().parents[1]


def _problem(
    dimensions: MILPDimensions,
    *,
    cutoff: float = 5.0,
    states: dict[ReplicaKey, int] | None = None,
    planning_link_ms: float = 2.0,
):
    configuration = MILPConfiguration(dimensions, cutoff)
    return build_problem_input(
        configuration,
        true_states=states or {
            key: ((key.stage + key.replica) % 4) + 1
            for key in dimensions.replica_keys
        },
        admission={
            key: ReplicaAdmission(True, dimensions.flow_count)
            for key in dimensions.replica_keys
        },
        planning_link_cost_ms={
            pair: planning_link_ms for pair in required_directed_pairs(dimensions)
        },
    )


def _slot_input(
    dimensions: MILPDimensions,
    *,
    cutoff: float = 5.0,
    root_seed: int = 12345,
    slot_id: int = 7,
    planning_link_ms: float = 2.0,
    measured_base_ms: float = 17.0,
    measured_jitter_ms: float = 1.5,
):
    problem = _problem(
        dimensions,
        cutoff=cutoff,
        planning_link_ms=planning_link_ms,
    )
    profiles = tuple(
        MeasuredPairLatencyProfile(
            source,
            target,
            base_ms=measured_base_ms,
            jitter_ms=measured_jitter_ms,
        )
        for source, target in required_directed_pairs(dimensions)
    )
    return MILPSlotInput(problem, root_seed, slot_id, profiles)


def _round_robin_actions(dimensions: MILPDimensions):
    actions = {}
    for flow_id in dimensions.flow_ids:
        replica = ((flow_id - 1) % dimensions.replicas_per_stage[0]) + 1
        right_replica = ((flow_id - 1) % dimensions.replicas_per_stage[1]) + 1
        actions[flow_id] = TwoStageAction.canonical(
            ReplicaKey(1, replica),
            ReplicaKey(2, right_replica),
        )
    return actions


def _incumbent_result(
    problem,
    *,
    status=SolverResultStatus.PROVEN_OPTIMAL,
    actions=None,
    bound_delta: float = 0.0,
):
    dimensions = problem.configuration.dimensions
    actions = actions or _round_robin_actions(dimensions)
    placement = MILPPlacement.from_actions(dimensions, actions)
    placement.validate_for(problem)
    objective = reconstruct_social_welfare(
        dimensions,
        actions,
        exact_known_state_expected_utility(problem),
        problem.planning_link_costs_ms(),
    )
    incumbent = objective.total_social_welfare_utility
    bound = incumbent + bound_delta
    absolute = abs(bound - incumbent)
    relative = absolute / max(1.0, abs(incumbent))
    provenance = SolverRunProvenance(
        status=status,
        requested_cutoff_seconds=problem.configuration.cutoff_seconds,
        model_build_seconds=0.01,
        solve_seconds=0.02,
        backend_name="phase3-test-backend",
        backend_version="1",
        termination_reason=status.value,
        incumbent_objective_utility=incumbent,
        best_bound_utility=bound,
        absolute_gap_utility=absolute,
        relative_gap=relative,
        variable_count=10,
        constraint_count=20,
    )
    return MILPSolverResult(provenance, placement, objective)


def _fake_solver(problem):
    return _incumbent_result(problem)


def _deterministic_projection(result):
    return (
        result.placement,
        result.bypassed_stages_by_flow,
        result.final_replica_loads,
        result.observations,
        result.measured_pairs,
        result.metrics.solver_total_social_welfare_utility,
        result.metrics.physical_realized_utility,
        result.metrics.physical_processing_latency_ms_per_flow,
        result.metrics.measured_pair_latency_ms_per_flow,
        result.metrics.raw_end_to_end_latency_ms_per_flow,
        result.metrics.physical_plus_pair_reference_utility_per_flow,
        result.metrics.physical_only_sla_violations,
        result.metrics.jain_fairness,
    )


def test_phase3_contract_is_immutable_and_requires_complete_outcome_pair_profiles():
    dimensions = MILPDimensions(flow_count=1, replicas_per_stage=(1, 1, 1))
    slot_input = _slot_input(dimensions)

    assert MILP_PHASE3_SLOT_CONTRACT_VERSION == "milp-coupled-phase3-slot-v1"
    assert slot_input.contract_version == MILP_PHASE3_SLOT_CONTRACT_VERSION
    assert len(slot_input.measured_pair_profiles) == 3
    with pytest.raises(FrozenInstanceError):
        slot_input.root_seed = 9
    with pytest.raises(MILPContractError, match="profile mismatch"):
        replace(slot_input, measured_pair_profiles=slot_input.measured_pair_profiles[:-1])
    with pytest.raises(MILPContractError, match="root_seed"):
        replace(slot_input, root_seed=-1)


def test_tiny_real_solver_slot_executes_two_selected_hops_without_learning(capsys):
    dimensions = MILPDimensions(flow_count=2, replicas_per_stage=(2, 2, 2))
    slot_input = _slot_input(dimensions, cutoff=5.0)

    result = run_milp_slot(slot_input)

    assert capsys.readouterr().out == ""
    assert result.metrics.solver_status is SolverResultStatus.PROVEN_OPTIMAL
    assert len(result.placement.actions) == 2
    assert len(result.observations) == 4
    assert len(result.measured_pairs) == 2
    assert sum(load for _key, load in result.final_replica_loads) == 4
    assert len(result.bypassed_stages_by_flow) == 2
    assert all(len(stages) == 1 for _flow, stages in result.bypassed_stages_by_flow)
    assert not hasattr(result, "beliefs")
    assert not hasattr(result.metrics, "equilibrium")


def test_observations_use_final_load_and_only_selected_replicas():
    dimensions = MILPDimensions(flow_count=3, replicas_per_stage=(2, 2, 2, 2))
    result = run_milp_slot(_slot_input(dimensions), solver=_fake_solver)
    actions = result.placement.action_by_flow()
    final_loads = dict(result.final_replica_loads)
    expected = {
        (flow_id, key)
        for flow_id, action in actions.items()
        for key in action.selections
    }

    assert {(item.flow_id, item.key) for item in result.observations} == expected
    assert all(
        item.assigned_load == final_loads[item.key] for item in result.observations
    )
    assert all(item.key.stage in (1, 2) for item in result.observations)
    assert all(stages == (3, 4) for _flow, stages in result.bypassed_stages_by_flow)
    assert all(key.stage in (1, 2) or load == 0 for key, load in result.final_replica_loads)


def test_exact_physical_observation_likelihood_utility_sla_and_fairness_semantics():
    import header as exact_header

    dimensions = MILPDimensions(flow_count=2, replicas_per_stage=(1, 1, 1))
    result = run_milp_slot(_slot_input(dimensions), solver=_fake_solver)
    metrics = result.metrics

    for observation in result.observations:
        assert observation.noisy_signal_ms == pytest.approx(
            observation.physical_processing_latency_ms
            + observation.observation_jitter_ms
        )
        assert observation.likelihood == pytest.approx(
            exact_latency.learning_signal_likelihood(
                observation.noisy_signal_ms,
                observation.assigned_load,
            )
        )
        assert not hasattr(observation, "true_state")

    physical_by_flow = dict(metrics.physical_processing_latency_ms_per_flow)
    expected_realized = sum(
        exact_latency.DEFAULT_REWARD
        - exact_latency.DEFAULT_LATENCY_WEIGHT
        * observation.physical_processing_latency_ms
        - exact_latency.DEFAULT_COST
        for observation in result.observations
    )
    assert metrics.physical_realized_utility == pytest.approx(expected_realized)
    assert metrics.physical_only_sla_violations == SLA_v(
        physical_by_flow,
        exact_latency.DEFAULT_SLA_LATENCY_MS,
    )
    objective = result.solver_result.objective
    expected_per_flow = {item.flow_id: [item.total_utility] for item in objective.flows}
    assert metrics.jain_fairness == exact_header.jain_index(
        expected_per_flow,
        objective.total_social_welfare_utility,
    )


def test_observation_jitter_does_not_enter_realized_utility_or_sla():
    dimensions = MILPDimensions(flow_count=1, replicas_per_stage=(1, 1))
    slot_input = _slot_input(dimensions)
    delegate = InProcessMILPSimulationAdapter()

    class HugeObservationJitterAdapter:
        def execute(self, supplied, placement):
            simulation = delegate.execute(supplied, placement)
            observations = tuple(
                replace(
                    item,
                    observation_jitter_ms=10_000.0,
                    noisy_signal_ms=item.physical_processing_latency_ms + 10_000.0,
                    likelihood=(0.25, 0.25, 0.25, 0.25),
                    estimated_state=1,
                )
                for item in simulation.observations
            )
            return MILPSimulationResult(observations, simulation.measured_pairs)

    baseline = run_milp_slot(slot_input, solver=_fake_solver)
    noisy = run_milp_slot(
        slot_input,
        solver=_fake_solver,
        simulation_adapter=HugeObservationJitterAdapter(),
    )

    assert noisy.metrics.physical_realized_utility == pytest.approx(
        baseline.metrics.physical_realized_utility
    )
    assert noisy.metrics.physical_only_sla_violations == (
        baseline.metrics.physical_only_sla_violations
    )


def test_planning_link_and_measured_pair_are_separate_metric_inputs():
    dimensions = MILPDimensions(flow_count=2, replicas_per_stage=(1, 1))
    result = run_milp_slot(
        _slot_input(
            dimensions,
            planning_link_ms=2.0,
            measured_base_ms=25.0,
            measured_jitter_ms=0.0,
        ),
        solver=_fake_solver,
    )

    assert result.metrics.solver_configured_planning_link_cost_ms == 4.0
    assert result.metrics.solver_configured_planning_link_deduction_utility == 4.0
    assert result.metrics.measured_pair_latency_ms == 50.0
    assert result.metrics.raw_end_to_end_latency_ms == pytest.approx(
        result.metrics.physical_processing_latency_ms + 50.0
    )
    assert result.metrics.physical_plus_pair_reference_utility == pytest.approx(
        result.metrics.physical_realized_utility - 50.0
    )


def test_sample_streams_are_independent_deterministic_and_global_rng_neutral():
    slot_input = _slot_input(
        MILPDimensions(flow_count=3, replicas_per_stage=(2, 2, 2)),
        root_seed=998877,
    )
    random.seed(101)
    np.random.seed(202)
    python_before = random.getstate()
    numpy_before = np.random.get_state()

    first = run_milp_slot(slot_input, solver=_fake_solver)
    second = run_milp_slot(slot_input, solver=_fake_solver)

    assert _deterministic_projection(first) == _deterministic_projection(second)
    assert random.getstate() == python_before
    numpy_after = np.random.get_state()
    assert numpy_after[0] == numpy_before[0]
    assert np.array_equal(numpy_after[1], numpy_before[1])
    assert numpy_after[2:] == numpy_before[2:]
    physical = {item.physical_seed for item in first.observations}
    observation = {item.observation_seed for item in first.observations}
    pairs = {item.pair_seed for item in first.measured_pairs}
    assert physical.isdisjoint(observation)
    assert physical.isdisjoint(pairs)
    assert observation.isdisjoint(pairs)
    assert first.physical_seed_scheme == MILP_PHYSICAL_SEED_SCHEME
    assert first.observation_seed_scheme == MILP_OBSERVATION_SEED_SCHEME
    assert first.measured_pair_seed_scheme == MILP_MEASURED_PAIR_SEED_SCHEME


def test_timed_feasible_incumbent_executes_but_remains_unproven():
    slot_input = _slot_input(MILPDimensions(flow_count=1, replicas_per_stage=(1, 1)))

    result = run_milp_slot(
        slot_input,
        solver=lambda problem: _incumbent_result(
            problem,
            status=SolverResultStatus.TIME_LIMIT_WITH_INCUMBENT,
            bound_delta=7.0,
        ),
    )

    assert result.metrics.solver_status is SolverResultStatus.TIME_LIMIT_WITH_INCUMBENT
    assert not result.solver_result.provenance.optimality_proven
    assert result.metrics.absolute_gap_utility == 7.0
    assert result.metrics.best_bound_utility > result.metrics.incumbent_objective_utility


@pytest.mark.parametrize(
    "status",
    [
        SolverResultStatus.TIME_LIMIT_WITHOUT_INCUMBENT,
        SolverResultStatus.INFEASIBLE,
        SolverResultStatus.UNBOUNDED,
        SolverResultStatus.SOLVER_OR_CONFIGURATION_ERROR,
    ],
)
def test_nonincumbent_solver_statuses_fail_before_simulation(status):
    slot_input = _slot_input(MILPDimensions(flow_count=1, replicas_per_stage=(1, 1)))
    called = False

    class NeverAdapter:
        def execute(self, _slot_input, _placement):
            nonlocal called
            called = True
            raise AssertionError("simulation must not run")

    provenance = SolverRunProvenance(
        status=status,
        requested_cutoff_seconds=slot_input.problem.configuration.cutoff_seconds,
        model_build_seconds=0.0,
        solve_seconds=0.0,
        backend_name="failure-fixture",
        backend_version="1",
        termination_reason=status.value,
    )
    with pytest.raises(MILPSlotExecutionError, match="requires a validated"):
        run_milp_slot(
            slot_input,
            solver=lambda _problem: MILPSolverResult(provenance),
            simulation_adapter=NeverAdapter(),
        )
    assert not called


def test_incomplete_observation_or_pair_sets_fail_explicitly():
    slot_input = _slot_input(MILPDimensions(flow_count=1, replicas_per_stage=(1, 1)))
    delegate = InProcessMILPSimulationAdapter()

    class IncompleteAdapter:
        def __init__(self, remove_pair):
            self.remove_pair = remove_pair

        def execute(self, supplied, placement):
            complete = delegate.execute(supplied, placement)
            if self.remove_pair:
                return MILPSimulationResult(complete.observations, ())
            return MILPSimulationResult(complete.observations[:-1], complete.measured_pairs)

    for adapter in (IncompleteAdapter(False), IncompleteAdapter(True)):
        with pytest.raises(MILPSlotExecutionError, match="simulation"):
            run_milp_slot(
                slot_input,
                solver=_fake_solver,
                simulation_adapter=adapter,
            )


def test_default_15x3x10_runner_boundary_has_exact_counts_without_oracle_or_scale_claim():
    dimensions = MILPDimensions()
    result = run_milp_slot(_slot_input(dimensions), solver=_fake_solver)

    assert len(result.placement.actions) == 15
    assert len(result.observations) == 30
    assert len(result.measured_pairs) == 15
    assert sum(load for _key, load in result.final_replica_loads) == 30
    assert all(len(stages) == 1 for _flow, stages in result.bypassed_stages_by_flow)


def test_pure_runner_is_silent_and_explicit_wrapper_prints_exactly_one_line(capsys):
    slot_input = _slot_input(MILPDimensions(flow_count=1, replicas_per_stage=(1, 1)))

    run_milp_slot(slot_input, solver=_fake_solver)
    assert capsys.readouterr().out == ""
    run_and_print_milp_slot(slot_input, solver=_fake_solver)
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    assert lines[0].startswith("MILP slot=7 status=proven-optimal")


def test_phase3_imports_are_silent_file_safe_and_rng_neutral(tmp_path):
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT)
    code = (
        "import importlib, random, numpy as np; "
        "random.seed(31); np.random.seed(32); "
        "p=random.getstate(); n=np.random.get_state(); "
        "[importlib.import_module(x) for x in "
        "('MILP.slot_contracts','MILP.simulation','MILP.runner','MILP')]; "
        "assert random.getstate()==p; a=np.random.get_state(); "
        "assert a[0]==n[0] and np.array_equal(a[1],n[1]) and a[2:]==n[2:]"
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
