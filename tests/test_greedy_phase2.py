from __future__ import annotations

import inspect
import itertools
import random
import subprocess
import sys
from dataclasses import replace
from itertools import combinations, product
from pathlib import Path

import numpy as np
import pytest

from Greedy.contracts import (
    GreedyConfiguration,
    NoFeasibleActionError,
    PublicReplicaState,
    ReplicaIdentity,
)
from Greedy.expected_utility import expected_stage_utility_from_belief
from Greedy.learning import apply_selected_learning, maximum_belief_change
from Greedy.metrics import compute_slot_metrics, jain_fairness
from Greedy.oracle import capture_greedy_slot, replay_captured_slot
from Greedy.policy import GreedyPolicy
from Greedy.runner import run_greedy_experiment, run_greedy_slot
from Greedy.simulation import (
    GREEDY_FLOW_ORDER_SEED_SCHEME,
    GREEDY_OBSERVATION_COMPONENT,
    GREEDY_PHYSICAL_COMPONENT,
    GreedyStochasticInputKey,
    InProcessGreedySimulationAdapter,
    derive_flow_order_seed,
    derive_stochastic_input_seed,
)
from Greedy.slot_contracts import (
    GREEDY_EXPERIMENT_STOP_EQUILIBRIUM,
    GREEDY_EXPERIMENT_STOP_MAX_ITERATIONS,
    GreedyMeasuredPair,
    GreedyPairLatency,
    GreedyReplicaProfile,
    GreedySelectedObservation,
    GreedySimulationResult,
    GreedySlotInput,
    materialized_profile_fingerprint,
)
from IBG import latency_model
from IBG_Hybrid.phase0_contract import derive_flow_order_seed as hybrid_flow_seed


ROOT = Path(__file__).resolve().parents[1]
UNIFORM = (0.25, 0.25, 0.25, 0.25)
PEAKED = (0.01, 0.01, 0.01, 0.97)


def identities(configuration):
    return tuple(
        ReplicaIdentity(stage, replica)
        for stage in configuration.stages
        for replica in configuration.replica_ids
    )


def all_pair_latencies(configuration, latency_ms):
    return tuple(
        GreedyPairLatency(
            ReplicaIdentity(stage_a, replica_a),
            ReplicaIdentity(stage_b, replica_b),
            latency_ms,
        )
        for stage_a, stage_b in combinations(configuration.stages, 2)
        for replica_a, replica_b in product(configuration.replica_ids, repeat=2)
    )


def make_input(
    *,
    flows=3,
    stages=3,
    replicas=2,
    belief=PEAKED,
    hidden_state=None,
    flow_order=None,
    root_seed=2050,
    profile_seed=17,
    experiment_id=1,
    slot_id=1,
    pair_latency=3.5,
    not_ready=(),
):
    configuration = GreedyConfiguration(flows, stages, replicas)
    unavailable = set(not_ready)
    all_identities = identities(configuration)
    public = tuple(
        PublicReplicaState(
            identity=identity,
            ready=identity not in unavailable,
            max_assigned_flows=configuration.admission_capacity_per_replica,
            belief=belief,
        )
        for identity in all_identities
    )
    profiles = tuple(
        GreedyReplicaProfile(
            identity=identity,
            hidden_state=(
                hidden_state
                if hidden_state is not None
                else ((identity.stage + identity.replica - 2) % 4) + 1
            ),
            observation_seed=10_000 + identity.stage * 100 + identity.replica,
        )
        for identity in all_identities
    )
    return GreedySlotInput(
        configuration=configuration,
        experiment_id=experiment_id,
        slot_id=slot_id,
        root_seed=root_seed,
        profile_seed=profile_seed,
        public_replicas=public,
        replica_profiles=profiles,
        measured_pair_latencies=all_pair_latencies(configuration, pair_latency),
        flow_order=None if flow_order is None else tuple(flow_order),
    )


def counting_clock(start=0.0, step=1.0):
    values = itertools.count()
    return lambda: start + step * next(values)


def semantic_slot(result):
    return (
        result.configuration,
        result.experiment_id,
        result.slot_id,
        result.root_seed,
        result.profile_fingerprint,
        result.flow_order,
        result.policy_result,
        result.placements,
        result.observations,
        result.measured_pairs,
        result.beliefs_before,
        result.beliefs_after,
        result.metrics,
    )


class TransformAdapter:
    def __init__(self, transform):
        self.delegate = InProcessGreedySimulationAdapter()
        self.transform = transform
        self.calls = 0

    def execute(self, **kwargs):
        self.calls += 1
        return self.transform(self.delegate.execute(**kwargs))


def replace_likelihood(result, likelihood):
    observations = tuple(
        replace(
            observation,
            likelihood=likelihood,
            estimated_state=int(np.argmax(likelihood)) + 1,
        )
        for observation in result.observations
    )
    return replace(result, observations=observations)


def test_complete_arbitrary_k_slot_preserves_explicit_order_and_l2_shape():
    slot_input = make_input(flows=4, stages=5, replicas=3, flow_order=(4, 1, 3, 2))
    result = run_greedy_slot(slot_input, clock=counting_clock())

    assert result.flow_order == (4, 1, 3, 2)
    assert tuple(placement.flow_id for placement in result.placements) == result.flow_order
    assert len(result.placements) == 4
    assert len(result.observations) == 8
    assert len(result.measured_pairs) == 4
    assert result.final_loads.total_assignments == 8
    assert all(len(placement.action.choices) == 2 for placement in result.placements)
    assert all(len(placement.bypassed_stages) == 3 for placement in result.placements)
    assert result.timings.placement_seconds == 1.0
    assert result.timings.feedback_validation_seconds == 1.0
    assert result.timings.total_seconds == 2.0


def test_seeded_flow_order_is_hybrid_compatible_and_exactly_retained():
    slot_input = make_input(flows=6, stages=2, replicas=2, root_seed=3105, slot_id=7)
    result = run_greedy_slot(slot_input, clock=lambda: 0.0)

    assert result.flow_order_seed_scheme == GREEDY_FLOW_ORDER_SEED_SCHEME
    assert result.flow_order_seed == derive_flow_order_seed(3105, 7)
    assert result.flow_order_seed == hybrid_flow_seed(3105, 7)
    assert sorted(result.flow_order) == list(range(1, 7))
    assert result.policy_result.flow_order == result.flow_order


def test_observations_are_selected_only_final_load_conditioned_and_do_not_leak():
    result = run_greedy_slot(make_input(flows=3, stages=4, replicas=3), clock=lambda: 0.0)
    selected = {
        (placement.flow_id, identity)
        for placement in result.placements
        for identity in placement.action.choices
    }
    observed = {
        (observation.flow_id, observation.identity)
        for observation in result.observations
    }
    assert observed == selected
    assert all(
        observation.assigned_load == result.final_loads.load_for(observation.identity)
        for observation in result.observations
    )
    assert all(
        observation.identity.stage not in placement.bypassed_stages
        for placement in result.placements
        for observation in result.observations
        if observation.flow_id == placement.flow_id
    )
    before = result.beliefs_before.mapping
    after = result.beliefs_after.mapping
    selected_identities = {identity for _flow, identity in selected}
    assert all(
        after[identity] == before[identity]
        for identity in before
        if identity not in selected_identities
    )


def test_predicted_metrics_use_final_slot_load_not_commit_time_load():
    slot_input = make_input(flows=3, stages=2, replicas=1, flow_order=(1, 2, 3))
    result = run_greedy_slot(slot_input, clock=lambda: 0.0)
    expected_stage = expected_stage_utility_from_belief(PEAKED, 3)

    assert dict(result.metrics.predicted_utility_per_flow) == pytest.approx(
        {1: 2 * expected_stage, 2: 2 * expected_stage, 3: 2 * expected_stage}
    )
    assert result.policy_result.decisions[0].stage_utilities[0] == pytest.approx(
        expected_stage_utility_from_belief(PEAKED, 1)
    )


def test_beliefs_carry_forward_without_mutating_the_prior_slot_input():
    first_input = make_input(flows=2, stages=3, replicas=2, root_seed=889)
    original_public = first_input.public_replicas
    first = run_greedy_slot(first_input, clock=lambda: 0.0)
    second_input = first_input.with_beliefs(first.beliefs_after.mapping)
    second = run_greedy_slot(second_input, clock=lambda: 0.0)

    assert first_input.public_replicas == original_public
    assert second.beliefs_before == first.beliefs_after
    assert second.slot_id == first.slot_id + 1
    assert second.profile_fingerprint == first.profile_fingerprint


def test_physical_and_observation_streams_are_separate_and_exact_convolved():
    slot_input = make_input(flows=1, stages=2, replicas=1)
    result = run_greedy_slot(slot_input, clock=lambda: 0.0)
    profiles = slot_input.replica_profile_by_identity

    for observation in result.observations:
        profile = profiles[observation.identity]
        physical = latency_model.sample_latency_ms(
            observation.assigned_load,
            latency_model.require_state_parameters(profile.hidden_state),
            np.random.default_rng(observation.physical_seed),
        )
        signal, jitter = latency_model.sample_learning_signal_ms(
            physical,
            profile.hidden_state,
            np.random.default_rng(observation.observation_seed),
        )
        assert observation.physical_seed != observation.observation_seed
        assert observation.physical_processing_latency_ms == physical
        assert observation.observation_jitter_ms == jitter
        assert observation.learning_signal_ms == signal
        assert observation.likelihood == latency_model.learning_signal_likelihood(
            signal,
            observation.assigned_load,
        )


def test_physical_realized_utility_and_raw_pair_reference_remain_separate():
    no_pair = run_greedy_slot(
        make_input(flows=2, stages=2, replicas=2, pair_latency=0.0),
        clock=lambda: 0.0,
    )
    with_pair = run_greedy_slot(
        make_input(flows=2, stages=2, replicas=2, pair_latency=9.5),
        clock=lambda: 0.0,
    )
    expected_physical = sum(
        latency_model.DEFAULT_REWARD
        - observation.physical_processing_latency_ms
        - latency_model.DEFAULT_COST
        for observation in with_pair.observations
    )

    assert no_pair.policy_result == with_pair.policy_result
    assert no_pair.metrics.physical_realized_aggregate_utility == pytest.approx(
        with_pair.metrics.physical_realized_aggregate_utility
    )
    assert with_pair.metrics.physical_realized_aggregate_utility == pytest.approx(
        expected_physical
    )
    assert with_pair.metrics.raw_end_to_end_reference_utility == pytest.approx(
        expected_physical - 2 * 9.5
    )


def test_raw_end_to_end_sla_is_strict_at_80_and_excess_is_unrounded():
    baseline_input = make_input(
        flows=1,
        stages=2,
        replicas=1,
        hidden_state=4,
        pair_latency=0.0,
    )
    baseline = run_greedy_slot(baseline_input, clock=lambda: 0.0)
    physical = dict(baseline.metrics.physical_processing_latency_ms_per_flow)[1]
    pair_to_boundary = 80.0 - physical
    boundary = run_greedy_slot(
        replace(
            baseline_input,
            measured_pair_latencies=all_pair_latencies(
                baseline_input.configuration,
                pair_to_boundary,
            ),
        ),
        clock=lambda: 0.0,
    )
    above = run_greedy_slot(
        replace(
            baseline_input,
            measured_pair_latencies=all_pair_latencies(
                baseline_input.configuration,
                pair_to_boundary + 1e-6,
            ),
        ),
        clock=lambda: 0.0,
    )

    assert dict(boundary.metrics.raw_end_to_end_latency_ms_per_flow)[1] == pytest.approx(80.0)
    assert boundary.metrics.end_to_end_sla_violations == 0
    assert boundary.metrics.end_to_end_sla_excess_ms == pytest.approx(0.0)
    assert above.metrics.end_to_end_sla_violations == 1
    assert above.metrics.end_to_end_sla_excess_ms == pytest.approx(1e-6)


def test_jain_fairness_matches_hand_calculation_without_input_mutation():
    import header as exact_header

    values = {1: 2.0, 2: 4.0, 3: 6.0}
    before = dict(values)
    assert jain_fairness(values, 12.0) == pytest.approx(144.0 / (3 * 56.0))
    assert jain_fairness(values, 12.0) == exact_header.jain_index(
        {flow_id: [value] for flow_id, value in values.items()},
        12.0,
    )
    assert values == before


def test_learning_adapter_matches_frozen_exact_replica_update_and_aggregation():
    import header as exact_header
    from IBG.learning import apply_observations

    slot_input = make_input(flows=2, stages=2, replicas=2)
    simulation = run_greedy_slot(slot_input, clock=lambda: 0.0)
    before, after = apply_selected_learning(
        slot_input.public_replicas,
        simulation.observations,
    )
    exact_replicas = {
        (state.identity.stage, state.identity.replica): exact_header.Replica(
            stage=state.identity.stage,
            replica=state.identity.replica,
            belief=list(state.belief),
            delay=25,
            cost=latency_model.DEFAULT_COST,
            gamma=0.0,
            state=1,
            capacity=state.max_assigned_flows,
        )
        for state in slot_input.public_replicas
    }
    apply_observations(simulation.observations, exact_replicas)
    exact_after = {
        ReplicaIdentity(stage, replica): tuple(value.belief)
        for (stage, replica), value in exact_replicas.items()
    }

    assert before == simulation.beliefs_before
    assert after.mapping == exact_after


def test_strict_equilibrium_uses_every_entry_below_point_zero_four():
    baseline = run_greedy_slot(make_input(flows=1, stages=2, replicas=1), clock=lambda: 0.0)
    before = baseline.beliefs_before.mapping
    identity = next(iter(before))
    exact_boundary = dict(before)
    just_below = dict(before)
    values = list(before[identity])
    values[0] += 0.04
    exact_boundary[identity] = tuple(values)
    values = list(before[identity])
    values[0] += 0.039999
    just_below[identity] = tuple(values)

    boundary_metrics = compute_slot_metrics(
        policy_result=baseline.policy_result,
        beliefs_before=before,
        beliefs_after=exact_boundary,
        observations=baseline.observations,
        measured_pairs=baseline.measured_pairs,
    )
    below_metrics = compute_slot_metrics(
        policy_result=baseline.policy_result,
        beliefs_before=before,
        beliefs_after=just_below,
        observations=baseline.observations,
        measured_pairs=baseline.measured_pairs,
    )
    assert maximum_belief_change(before, exact_boundary) == pytest.approx(0.04)
    assert not boundary_metrics.equilibrium
    assert below_metrics.equilibrium


def test_experiment_stops_early_on_equilibrium_and_is_exactly_one_experiment():
    adapter = TransformAdapter(lambda result: replace_likelihood(result, UNIFORM))
    result = run_greedy_experiment(
        make_input(flows=2, stages=2, replicas=2, belief=UNIFORM, experiment_id=19),
        max_iterations=5,
        simulation_adapter=adapter,
        clock=counting_clock(),
    )

    assert result.experiment_id == 19
    assert result.iterations_completed == 1
    assert result.stop_reason == GREEDY_EXPERIMENT_STOP_EQUILIBRIUM
    assert result.reached_equilibrium
    assert adapter.calls == 1


def test_experiment_stops_after_exact_explicit_maximum_iterations():
    adapter = TransformAdapter(
        lambda result: replace_likelihood(result, (1.0, 0.0, 0.0, 0.0))
    )
    result = run_greedy_experiment(
        make_input(flows=1, stages=2, replicas=1, belief=UNIFORM),
        max_iterations=2,
        simulation_adapter=adapter,
        clock=counting_clock(),
    )

    assert result.iterations_completed == 2
    assert result.stop_reason == GREEDY_EXPERIMENT_STOP_MAX_ITERATIONS
    assert not result.reached_equilibrium
    assert adapter.calls == 2
    assert result.slots[1].beliefs_before == result.slots[0].beliefs_after
    with pytest.raises(ValueError, match="positive"):
        run_greedy_experiment(make_input(), max_iterations=0)


def test_keyed_input_schedule_covers_all_identity_fields_and_components():
    from IBG_Hybrid.contracts import ReplicaChoice
    from IBG_Hybrid.simulation import _derive_observation_seed

    identity = ReplicaIdentity(2, 3)
    base = GreedyStochasticInputKey(1, 2, 3, identity, 4, GREEDY_PHYSICAL_COMPONENT)
    seed = derive_stochastic_input_seed(99, base)
    assert seed == derive_stochastic_input_seed(99, base)
    variants = (
        replace(base, experiment_id=2),
        replace(base, slot_id=3),
        replace(base, flow_id=4),
        replace(base, identity=ReplicaIdentity(2, 4)),
        replace(base, assigned_load=5),
        replace(base, component=GREEDY_OBSERVATION_COMPONENT),
    )
    assert all(derive_stochastic_input_seed(99, variant) != seed for variant in variants)
    assert derive_stochastic_input_seed(100, base) != seed
    assert seed == _derive_observation_seed(
        scheme="blake2b-hybrid-physical-v1",
        root_seed=99,
        slot_id=2,
        flow_id=3,
        choice=ReplicaChoice(2, 3),
        assigned_load=4,
    )


def test_profile_seed_isolated_from_policy_flow_order_and_component_draws():
    first_input = make_input(profile_seed=1)
    second_input = replace(first_input, profile_seed=999)
    first = run_greedy_slot(first_input, clock=lambda: 0.0)
    second = run_greedy_slot(second_input, clock=lambda: 0.0)

    assert first_input.profile_fingerprint == second_input.profile_fingerprint
    assert first.flow_order == second.flow_order
    assert first.policy_result == second.policy_result
    assert first.observations == second.observations
    changed_profiles = tuple(
        replace(profile, observation_seed=profile.observation_seed + 1)
        for profile in first_input.replica_profiles
    )
    assert materialized_profile_fingerprint(changed_profiles) != first_input.profile_fingerprint


def test_no_global_python_or_numpy_rng_is_consumed_by_a_slot():
    random.seed(812)
    np.random.seed(813)
    python_before = random.getstate()
    numpy_before = np.random.get_state()
    run_greedy_slot(make_input(), clock=lambda: 0.0)
    python_after = random.getstate()
    numpy_after = np.random.get_state()

    assert python_after == python_before
    assert numpy_after[0] == numpy_before[0]
    assert np.array_equal(numpy_after[1], numpy_before[1])
    assert numpy_after[2:] == numpy_before[2:]


def test_slot_is_deterministic_caller_immutable_and_cached_uncached_equal():
    slot_input = make_input(flows=4, stages=3, replicas=3, flow_order=(3, 1, 4, 2))
    before = slot_input
    cached = run_greedy_slot(slot_input, clock=lambda: 0.0, use_cache=True)
    repeated = run_greedy_slot(slot_input, clock=lambda: 0.0, use_cache=True)
    uncached = run_greedy_slot(slot_input, clock=lambda: 0.0, use_cache=False)

    assert semantic_slot(cached) == semantic_slot(repeated) == semantic_slot(uncached)
    assert slot_input == before


def test_captured_replay_matches_without_redrawing_or_default_duplicate_solve():
    adapter = TransformAdapter(lambda result: result)
    slot_input = make_input(flows=3, stages=3, replicas=2)
    result = run_greedy_slot(
        slot_input,
        simulation_adapter=adapter,
        clock=lambda: 0.0,
    )
    assert adapter.calls == 1
    validation = replay_captured_slot(capture_greedy_slot(slot_input, result))

    assert validation.matched
    assert validation.reference_policy_result == result.policy_result
    assert "oracle" not in inspect.getsource(run_greedy_slot)


@pytest.mark.parametrize("drop", ("observation", "pair"))
def test_incomplete_observation_or_pair_set_fails_before_learning(drop):
    def transform(result):
        if drop == "observation":
            return replace(result, observations=result.observations[:-1])
        return replace(result, measured_pairs=result.measured_pairs[:-1])

    with pytest.raises(RuntimeError, match=drop):
        run_greedy_slot(
            make_input(flows=2, stages=2, replicas=2),
            simulation_adapter=TransformAdapter(transform),
            clock=lambda: 0.0,
        )


def test_missing_selected_pair_input_and_no_feasible_action_propagate_explicitly():
    missing_pair = replace(make_input(flows=1, stages=2, replicas=1), measured_pair_latencies=())
    with pytest.raises(RuntimeError, match="measured-pair"):
        run_greedy_slot(missing_pair, clock=lambda: 0.0)

    blocked = make_input(
        flows=1,
        stages=2,
        replicas=1,
        not_ready=(ReplicaIdentity(1, 1),),
    )
    with pytest.raises(NoFeasibleActionError):
        run_greedy_slot(blocked, clock=lambda: 0.0)


def test_policy_boundary_never_receives_hidden_profile_seed_pair_or_runtime_values():
    class InspectingPolicy(GreedyPolicy):
        def place(self, **kwargs):
            assert all(type(state) is PublicReplicaState for state in kwargs["replica_states"])
            assert set(PublicReplicaState.__dataclass_fields__) == {
                "identity",
                "ready",
                "max_assigned_flows",
                "belief",
            }
            return super().place(**kwargs)

    slot_input = make_input()
    run_greedy_slot(
        slot_input,
        policy=InspectingPolicy(slot_input.configuration),
        clock=lambda: 0.0,
    )
    assert "profile_seed" not in inspect.signature(GreedyPolicy.place).parameters
    assert "measured_pair_latency_ms" not in inspect.signature(GreedyPolicy.place).parameters


def test_phase2_modules_import_silently_without_file_creation(tmp_path):
    modules = (
        "Greedy.slot_contracts",
        "Greedy.simulation",
        "Greedy.learning",
        "Greedy.metrics",
        "Greedy.runner",
        "Greedy.oracle",
    )
    completed = subprocess.run(
        [sys.executable, "-c", "; ".join(f"import {name}" for name in modules)],
        cwd=tmp_path,
        env={"PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert completed.stderr == ""
    assert list(tmp_path.iterdir()) == []


def test_phase2_source_has_no_hybrid_policy_or_parallel_decision_dependency():
    source = "\n".join(
        (ROOT / "Greedy" / name).read_text()
        for name in (
            "slot_contracts.py",
            "simulation.py",
            "learning.py",
            "metrics.py",
            "runner.py",
        )
    )
    for forbidden in (
        "IBG_Hybrid.policy",
        "ProcessPoolExecutor",
        "candidate_pruning",
        "lookahead",
        "monte_carlo",
        "planning_link",
        "mc_workers",
        "--policy",
        "--runs",
        "jsonl",
        "csv.writer",
        "kubectl",
    ):
        assert forbidden not in source
