from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path
import random
import subprocess
import sys

import numpy as np
import pytest

from IBG import latency_model as exact_latency
from MILP.contracts import (
    DirectedPlanningLink,
    MILPConfiguration,
    MILPPlacement,
    MILPSolverResult,
    build_problem_input,
)
from MILP.diagnostics import (
    DiagnosticDisposition,
    MILPDiagnosticOptions,
    collect_milp_diagnostics,
    diagnostic_compatibility_manifest,
)
from MILP.kernel_contracts import (
    MILPKernelMeasuredPairOutcome,
    MILPKernelReplicaEndpoint,
    MILPKernelSelectedObservation,
    MILPKernelSlotInput,
    MILPKernelTrafficResult,
)
from MILP.kernel_runner import run_milp_kernel_slot
from MILP.model import exact_known_state_expected_utility
from MILP.phase0_contract import (
    MILPDimensions,
    ReplicaAdmission,
    ReplicaKey,
    SolverResultStatus,
    SolverRunProvenance,
    TwoStageAction,
    reconstruct_social_welfare,
    required_directed_pairs,
)
from MILP.replay import MILPReplayError, replay_milp_solver, replay_milp_trace
from MILP.runner import run_milp_slot
from MILP.slot_contracts import (
    MILPMeasuredPairOutcome,
    MILPSelectedObservation,
    MILPSimulationResult,
    MILPSlotInput,
    MeasuredPairLatencyProfile,
)
from MILP.trace_contracts import (
    MILP_PHASE6_TRACE_CONTRACT_VERSION,
    MILPSelectedPlanningLink,
    MILPTraceSource,
    build_milp_trace,
)


ROOT = Path(__file__).resolve().parents[1]


def _problem(*, cutoff=2.0):
    dimensions = MILPDimensions(flow_count=2, replicas_per_stage=(2, 2, 2))
    configuration = MILPConfiguration(dimensions, cutoff)
    return build_problem_input(
        configuration,
        true_states={key: ((key.stage + key.replica) % 4) + 1 for key in dimensions.replica_keys},
        admission={key: ReplicaAdmission(True, 2) for key in dimensions.replica_keys},
        planning_link_cost_ms={pair: 2.0 for pair in required_directed_pairs(dimensions)},
    )


def _actions():
    return {
        1: TwoStageAction.canonical(ReplicaKey(1, 1), ReplicaKey(3, 1)),
        2: TwoStageAction.canonical(ReplicaKey(2, 1), ReplicaKey(3, 2)),
    }


def _solver_result(problem, *, status=SolverResultStatus.PROVEN_OPTIMAL, bound_delta=0.0):
    placement = MILPPlacement.from_actions(problem.configuration.dimensions, _actions())
    objective = reconstruct_social_welfare(
        problem.configuration.dimensions,
        placement.action_by_flow(),
        exact_known_state_expected_utility(problem),
        problem.planning_link_costs_ms(),
    )
    incumbent = objective.total_social_welfare_utility
    bound = incumbent + bound_delta
    absolute = abs(bound - incumbent)
    provenance = SolverRunProvenance(
        status=status,
        requested_cutoff_seconds=problem.configuration.cutoff_seconds,
        model_build_seconds=0.01,
        solve_seconds=0.02,
        backend_name="phase6-fixture",
        backend_version="1",
        termination_reason=status.value,
        incumbent_objective_utility=incumbent,
        best_bound_utility=bound,
        absolute_gap_utility=absolute,
        relative_gap=absolute / max(1.0, abs(incumbent)),
        variable_count=42,
        constraint_count=84,
    )
    return MILPSolverResult(provenance, placement, objective)


def _solver(problem):
    return _solver_result(problem)


def _fixed_observation(flow_id, key, load, *, kernel=False, jitter=8.0):
    physical = 40.0 + flow_id + key.stage
    signal = physical + jitter
    likelihood = exact_latency.learning_signal_likelihood(signal, load)
    common = dict(
        flow_id=flow_id,
        key=key,
        assigned_load=load,
        physical_processing_latency_ms=physical,
        observation_jitter_ms=jitter,
        noisy_signal_ms=signal,
        likelihood=likelihood,
        estimated_state=exact_latency.estimate_state(likelihood),
    )
    if kernel:
        return MILPKernelSelectedObservation(
            **common,
            pod_name=f"stage-{key.stage}-{key.replica - 1}",
            endpoint=f"http://stage-{key.stage}-{key.replica - 1}",
            admitted_concurrency=1,
            modeled_processing_latency_ms=physical - 0.5,
            request_latency_ms=physical + 3.0,
            transport_overhead_ms=3.0,
        )
    return MILPSelectedObservation(
        **common,
        physical_seed=1000 + flow_id * 10 + key.stage,
        observation_seed=2000 + flow_id * 10 + key.stage,
    )


class FixedPureAdapter:
    def __init__(self, *, jitter=8.0, pair_ms=7.0):
        self.jitter = jitter
        self.pair_ms = pair_ms

    def execute(self, slot_input, placement):
        loads = dict(placement.final_loads)
        observations = tuple(
            _fixed_observation(flow_id, key, loads[key], jitter=self.jitter)
            for flow_id, action in placement.actions
            for key in action.selections
        )
        pairs = tuple(
            MILPMeasuredPairOutcome(
                flow_id,
                action.directed_pair[0],
                action.directed_pair[1],
                self.pair_ms,
                3000 + flow_id,
                self.pair_ms,
                0.0,
            )
            for flow_id, action in placement.actions
        )
        return MILPSimulationResult(observations, pairs)


class FixedKernelAdapter:
    def __init__(self, *, jitter=8.0, pair_ms=7.0):
        self.jitter = jitter
        self.pair_ms = pair_ms

    def execute(self, slot_input, placement):
        loads = dict(placement.final_loads)
        observations = tuple(
            _fixed_observation(flow_id, key, loads[key], kernel=True, jitter=self.jitter)
            for flow_id, action in placement.actions
            for key in action.selections
        )
        pairs = tuple(
            MILPKernelMeasuredPairOutcome(
                flow_id=flow_id,
                source=action.directed_pair[0],
                target=action.directed_pair[1],
                latency_ms=self.pair_ms,
                source_pod_name=(
                    f"stage-{action.directed_pair[0].stage}-"
                    f"{action.directed_pair[0].replica - 1}"
                ),
                target_pod_name=(
                    f"stage-{action.directed_pair[1].stage}-"
                    f"{action.directed_pair[1].replica - 1}"
                ),
                target_endpoint=(
                    f"http://stage-{action.directed_pair[1].stage}-"
                    f"{action.directed_pair[1].replica - 1}"
                ),
                request_latency_ms=self.pair_ms + 10.0,
                callee_elapsed_ms=10.0,
            )
            for flow_id, action in placement.actions
        )
        return MILPKernelTrafficResult(observations, pairs, 1.0)


def _pure_result(problem=None, *, adapter=None, solver=_solver):
    problem = problem or _problem()
    slot_input = MILPSlotInput(
        problem=problem,
        root_seed=123,
        slot_id=4,
        measured_pair_profiles=tuple(
            MeasuredPairLatencyProfile(source, target, 7.0, 0.0)
            for source, target in required_directed_pairs(problem.configuration.dimensions)
        ),
    )
    return problem, run_milp_slot(
        slot_input,
        solver=solver,
        simulation_adapter=adapter or FixedPureAdapter(),
    )


def _kernel_result(problem=None, *, adapter=None, solver=_solver):
    problem = problem or _problem()
    endpoints = tuple(
        MILPKernelReplicaEndpoint(
            key=key,
            pod_name=f"stage-{key.stage}-{key.replica - 1}",
            node_name=f"worker-{key.replica}",
            endpoint=f"http://stage-{key.stage}-{key.replica - 1}",
        )
        for key in problem.configuration.dimensions.replica_keys
    )
    slot_input = MILPKernelSlotInput(problem, 4, endpoints)
    return problem, run_milp_kernel_slot(
        slot_input,
        solver=solver,
        traffic_adapter=adapter or FixedKernelAdapter(),
    )


def _pure_trace(**kwargs):
    problem, result = _pure_result(**kwargs)
    return build_milp_trace(problem, result)


def test_pure_and_kernel_traces_replay_without_solver_calls():
    pure = _pure_trace()
    problem, kernel_result = _kernel_result()
    kernel = build_milp_trace(problem, kernel_result)

    pure_report = replay_milp_trace(pure)
    kernel_report = replay_milp_trace(kernel)

    assert pure_report.source is MILPTraceSource.PURE
    assert kernel_report.source is MILPTraceSource.KERNEL
    assert pure_report.reconstructed_total_social_welfare_utility == pytest.approx(
        kernel_report.reconstructed_total_social_welfare_utility
    )
    assert pure_report.reconstructed_physical_realized_utility == pytest.approx(
        kernel_report.reconstructed_physical_realized_utility
    )
    assert pure_report.reconstructed_physical_only_sla_violations == (
        kernel_report.reconstructed_physical_only_sla_violations
    )


def test_kernel_replay_accepts_live_anyhttpurl_root_slash_normalization():
    problem, result = _kernel_result()
    live_result = replace(
        result,
        observations=tuple(
            replace(item, endpoint=f"{item.endpoint}/")
            for item in result.observations
        ),
        measured_pairs=tuple(
            replace(item, target_endpoint=f"{item.target_endpoint}/")
            for item in result.measured_pairs
        ),
    )

    report = replay_milp_trace(build_milp_trace(problem, live_result))

    assert report.source is MILPTraceSource.KERNEL


def test_trace_is_immutable_json_safe_and_true_state_is_private():
    trace = _pure_trace()
    document = trace.to_json_safe()
    encoded = json.dumps(document, sort_keys=True, allow_nan=False)

    assert MILP_PHASE6_TRACE_CONTRACT_VERSION in encoded
    assert "true_state" in json.dumps(document["private_planner_input"])
    public = dict(document)
    public.pop("private_planner_input")
    assert "true_state" not in json.dumps(public)
    assert all(not hasattr(observation, "true_state") for observation in trace.observations)
    with pytest.raises(FrozenInstanceError):
        trace.slot_id = 9


def test_replay_detects_action_and_final_load_corruption():
    trace = _pure_trace()
    changed_actions = dict(trace.placement.actions)
    changed_actions[1] = TwoStageAction.canonical(ReplicaKey(1, 2), ReplicaKey(2, 2))
    changed_placement = MILPPlacement.from_actions(
        trace.private_planner_input.configuration.dimensions,
        changed_actions,
    )
    with pytest.raises(MILPReplayError, match="placement-drift"):
        replay_milp_trace(replace(trace, placement=changed_placement))

    loads = list(trace.final_replica_loads)
    loads[0] = (loads[0][0], loads[0][1] + 1)
    with pytest.raises(MILPReplayError, match="load-drift"):
        replay_milp_trace(replace(trace, final_replica_loads=tuple(loads)))


def test_replay_detects_selected_planning_coefficient_and_objective_corruption():
    trace = _pure_trace()
    selected = list(trace.selected_planning_links)
    original = selected[0]
    selected[0] = MILPSelectedPlanningLink(
        original.flow_id,
        DirectedPlanningLink(original.link.source, original.link.target, original.link.cost_ms + 1),
    )
    with pytest.raises(MILPReplayError, match="coefficient-drift"):
        replay_milp_trace(replace(trace, selected_planning_links=tuple(selected)))

    bad_metrics = replace(
        trace.metrics,
        solver_total_social_welfare_utility=trace.metrics.solver_total_social_welfare_utility + 1,
    )
    with pytest.raises(MILPReplayError, match="objective-drift"):
        replay_milp_trace(replace(trace, metrics=bad_metrics))


def test_replay_detects_solver_status_observation_and_pair_count_corruption():
    trace = _pure_trace()
    with pytest.raises(MILPReplayError, match="solver-status-drift"):
        replay_milp_trace(
            replace(
                trace,
                metrics=replace(
                    trace.metrics,
                    solver_status=SolverResultStatus.TIME_LIMIT_WITH_INCUMBENT,
                ),
            )
        )
    with pytest.raises(MILPReplayError, match="observation-count-drift"):
        replay_milp_trace(replace(trace, observations=trace.observations[:-1]))
    with pytest.raises(MILPReplayError, match="pair-count-drift"):
        replay_milp_trace(replace(trace, measured_pairs=trace.measured_pairs[:-1]))


@pytest.mark.parametrize(
    ("field", "delta", "category"),
    (
        ("physical_realized_utility", 1.0, "metric-drift"),
        ("physical_only_sla_violations", 1, "sla-drift"),
        ("jain_fairness", 0.01, "fairness-drift"),
    ),
)
def test_replay_detects_utility_sla_and_fairness_corruption(field, delta, category):
    trace = _pure_trace()
    bad = replace(trace.metrics, **{field: getattr(trace.metrics, field) + delta})
    with pytest.raises(MILPReplayError, match=category):
        replay_milp_trace(replace(trace, metrics=bad))


def test_observation_jitter_is_excluded_from_realized_utility_and_sla():
    baseline = _pure_trace(adapter=FixedPureAdapter(jitter=0.0))
    noisy = _pure_trace(adapter=FixedPureAdapter(jitter=10_000.0))

    replay_milp_trace(baseline)
    replay_milp_trace(noisy)
    assert noisy.metrics.physical_realized_utility == baseline.metrics.physical_realized_utility
    assert noisy.metrics.physical_only_sla_violations == baseline.metrics.physical_only_sla_violations
    assert tuple(item.noisy_signal_ms for item in noisy.observations) != tuple(
        item.noisy_signal_ms for item in baseline.observations
    )


def test_measured_pair_never_substitutes_for_configured_planning_link():
    low_pair = _pure_trace(adapter=FixedPureAdapter(pair_ms=1.0))
    high_pair = _pure_trace(adapter=FixedPureAdapter(pair_ms=100.0))

    replay_milp_trace(low_pair)
    replay_milp_trace(high_pair)
    assert high_pair.metrics.solver_configured_planning_link_cost_ms == 4.0
    assert high_pair.metrics.solver_total_social_welfare_utility == (
        low_pair.metrics.solver_total_social_welfare_utility
    )
    assert high_pair.metrics.measured_pair_latency_ms == 200.0
    assert high_pair.metrics.physical_plus_pair_reference_utility < (
        low_pair.metrics.physical_plus_pair_reference_utility
    )


def test_optional_solver_replay_requires_canonical_equality_only_for_proven_optima():
    proven = _pure_trace()
    report = replay_milp_solver(proven, solver=_solver)
    assert report.canonical_comparison_required
    assert report.objective_matches and report.placement_matches

    problem = _problem()
    timed_solver = lambda supplied: _solver_result(
        supplied,
        status=SolverResultStatus.TIME_LIMIT_WITH_INCUMBENT,
        bound_delta=5.0,
    )
    timed = _pure_trace(problem=problem, solver=timed_solver)
    report = replay_milp_solver(timed, solver=_solver)
    assert not report.canonical_comparison_required
    assert report.objective_matches is None
    assert report.placement_matches is None
    assert timed.solver_result.provenance.status is SolverResultStatus.TIME_LIMIT_WITH_INCUMBENT


def test_diagnostic_audit_is_explicit_and_default_collection_is_empty():
    manifest = {item.name: item for item in diagnostic_compatibility_manifest()}
    assert manifest["forwarding-path"].disposition is DiagnosticDisposition.COMPATIBLE
    assert manifest["solver-resource"].disposition is DiagnosticDisposition.ADAPTED
    assert manifest["exact-memo-cache"].disposition is DiagnosticDisposition.INAPPLICABLE
    assert manifest["learning-footprint"].disposition is DiagnosticDisposition.INAPPLICABLE
    assert manifest["hybrid-candidates-rollouts-samples"].disposition is DiagnosticDisposition.INAPPLICABLE

    _problem_value, result = _pure_result()
    assert collect_milp_diagnostics(result, MILPDiagnosticOptions()) == ()


def test_opt_in_diagnostics_are_behavior_neutral_and_json_safe():
    problem, result = _kernel_result()
    before = (result.placement, result.metrics, result.observations, result.measured_pairs)
    records = collect_milp_diagnostics(
        result,
        MILPDiagnosticOptions(True, True, True, True),
        peak_rss_bytes=123456,
    )
    trace = build_milp_trace(problem, result, diagnostics=records)

    assert {record.name for record in records} == {
        "controller-timing",
        "http-route-timing",
        "payload",
        "solver-resource",
    }
    json.dumps(trace.to_json_safe(), allow_nan=False)
    assert before == (result.placement, result.metrics, result.observations, result.measured_pairs)
    replay_milp_trace(trace)


def test_phase6_imports_and_script_are_silent_rng_neutral_and_file_safe(tmp_path):
    code = """
import json, random
import numpy as np
random.seed(101); np.random.seed(202)
py = random.getstate(); np_state = np.random.get_state()
import MILP.trace_contracts, MILP.replay, MILP.diagnostics
assert random.getstate() == py
after = np.random.get_state()
assert np_state[0] == after[0] and np.array_equal(np_state[1], after[1])
assert np_state[2:] == after[2:]
print(json.dumps(sorted(__import__('os').listdir('.'))))
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env={"PYTHONPATH": str(ROOT)},
        text=True,
        capture_output=True,
        check=True,
    )
    assert json.loads(completed.stdout) == []
    assert completed.stderr == ""

    script = subprocess.run(
        [sys.executable, str(ROOT / "scripts/milp_diagnostic_compatibility.py")],
        cwd=tmp_path,
        env={"PYTHONPATH": str(ROOT)},
        text=True,
        capture_output=True,
        check=True,
    )
    assert script.stdout.count("MILP_DIAGNOSTIC_COMPATIBILITY=") == 1
    assert list(tmp_path.iterdir()) == []


def test_replay_does_not_consume_process_global_rng():
    trace = _pure_trace()
    random.seed(303)
    np.random.seed(404)
    py_before = random.getstate()
    np_before = np.random.get_state()

    replay_milp_trace(trace)

    assert random.getstate() == py_before
    np_after = np.random.get_state()
    assert np_before[0] == np_after[0]
    assert np.array_equal(np_before[1], np_after[1])
    assert np_before[2:] == np_after[2:]
