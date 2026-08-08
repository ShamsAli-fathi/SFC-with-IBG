import contextlib
import io
import os
import subprocess
import sys
from dataclasses import replace
from itertools import combinations, product

import numpy as np
import pytest

from IBG import latency_model as exact_latency
from IBG.outcome_latency import outcome_latency_ms_per_flow
from IBG.report import SLA_v
from IBG_Hybrid import (
    DEFAULT_HYBRID_POLICY_PARAMETERS,
    GlobalLoadState,
    HybridConfiguration,
    HybridFlow,
    HybridMonteCarloDecision,
    HybridPairValue,
    HybridPolicyParameters,
    HybridReplica,
    HybridSimulationResult,
    HybridSlotInput,
    PipelinePath,
    ReplicaChoice,
    format_hybrid_slot_metrics,
    make_default_hybrid_slot_input,
    run_and_print_hybrid_slot,
    run_hybrid_slot,
)
from IBG_Hybrid.policy import MonteCarloRootMode
from IBG_Hybrid.phase0_contract import (
    HYBRID_FLOW_ORDER_SEED_SCHEME,
    derive_flow_order_seed,
)


PEAKED_BELIEF = (0.01, 0.01, 0.01, 0.97)
UNIFORM_BELIEF = (0.25, 0.25, 0.25, 0.25)


def all_choices(configuration):
    return tuple(
        ReplicaChoice(stage, replica)
        for stage in range(1, configuration.num_stages + 1)
        for replica in range(1, configuration.num_replicas + 1)
    )


def all_pair_values(configuration, value):
    return tuple(
        HybridPairValue(
            ReplicaChoice(stage_a, replica_a),
            ReplicaChoice(stage_b, replica_b),
            value,
        )
        for stage_a, stage_b in combinations(
            range(1, configuration.num_stages + 1),
            2,
        )
        for replica_a, replica_b in product(
            range(1, configuration.num_replicas + 1),
            repeat=2,
        )
    )


def make_input(
    *,
    flows=2,
    replicas=2,
    belief=PEAKED_BELIEF,
    parameters=None,
    priorities=(),
    ready=None,
    capacity=20,
    planning_link=0.25,
    measured_pair=3.5,
    root_seed=2050,
    slot_id=1,
):
    configuration = HybridConfiguration(
        num_flows=flows,
        num_replicas=replicas,
    )
    ready = ready or {
        choice: True
        for choice in all_choices(configuration)
    }
    replica_inputs = tuple(
        HybridReplica(
            choice=choice,
            belief=belief,
            ready=ready.get(choice, False),
            max_assigned_flows=capacity,
            hidden_state=((choice.stage + choice.replica - 2) % 4) + 1,
        )
        for choice in all_choices(configuration)
    )
    return HybridSlotInput(
        configuration=configuration,
        parameters=parameters
        or HybridPolicyParameters(
            candidates_per_stage=min(5, replicas),
            lookahead_future_flows=2,
            monte_carlo_samples=3,
            rollout_epsilon=0.10,
        ),
        root_seed=root_seed,
        slot_id=slot_id,
        flows=tuple(
            HybridFlow(flow_id, flow_id in priorities)
            for flow_id in range(1, flows + 1)
        ),
        replicas=replica_inputs,
        planning_pair_links=all_pair_values(configuration, planning_link),
        simulated_pair_outcomes=all_pair_values(
            configuration,
            measured_pair,
        ),
        initial_loads=GlobalLoadState.empty(configuration),
    )


def deterministic_projection(result):
    metrics = replace(result.metrics, elapsed_seconds=0.0)
    return replace(result, metrics=metrics)


def test_one_slot_wide_flow_order_has_stable_seed_provenance():
    slot_input = make_input(flows=5, root_seed=3105, slot_id=7)
    result = run_hybrid_slot(slot_input)

    assert result.flow_order_seed_scheme == HYBRID_FLOW_ORDER_SEED_SCHEME
    assert result.flow_order_seed == derive_flow_order_seed(3105, 7)
    assert sorted(result.flow_order) == [1, 2, 3, 4, 5]
    assert tuple(
        placement.flow.flow_id for placement in result.placements
    ) == result.flow_order


def test_flow_order_isolated_from_policy_and_observation_rng_streams():
    greedy = make_input(flows=4, root_seed=4001)
    monte_carlo = make_input(
        flows=4,
        root_seed=4001,
        belief=UNIFORM_BELIEF,
    )

    greedy_result = run_hybrid_slot(greedy)
    mc_result = run_hybrid_slot(monte_carlo)

    assert greedy_result.flow_order_seed == mc_result.flow_order_seed
    assert greedy_result.flow_order == mc_result.flow_order


def test_each_real_commit_changes_only_two_selected_replicas():
    result = run_hybrid_slot(make_input(flows=4))

    assert len(result.placements) == 4
    assert result.final_loads.total_assignments == 8
    for placement in result.placements:
        assert len(set(placement.action.stages)) == 2
        assert placement.skipped_stage not in placement.action.stages
        assert placement.state_after == placement.state_before.apply(
            placement.action,
            result.configuration,
        )
        assert (
            placement.state_after.total_assignments
            - placement.state_before.total_assignments
            == 2
        )


def test_projected_lookahead_continuations_never_enter_real_slot_loads():
    slot_input = make_input(flows=3)
    result = run_hybrid_slot(slot_input)

    assert all(
        placement.path is PipelinePath.LOOKAHEAD
        for placement in result.placements
    )
    assert result.final_loads.total_assignments == 6
    assert any(
        placement.policy_detail.selected_evaluation.effective_depth > 0
        for placement in result.placements[:-1]
    )


def test_uniform_entropy_and_high_priority_still_use_core_lookahead():
    result = run_hybrid_slot(
        make_input(
            flows=1,
            replicas=1,
            belief=UNIFORM_BELIEF,
            priorities=(1,),
            parameters=HybridPolicyParameters(
                candidates_per_stage=1,
                lookahead_future_flows=2,
                monte_carlo_samples=2,
                rollout_epsilon=0.10,
            ),
        )
    )

    placement = result.placements[0]
    assert placement.path is PipelinePath.LOOKAHEAD
    assert placement.activation.high_priority is True
    assert placement.activation.maximum_normalized_belief_entropy == 1.0
    assert placement.activation_reason == "default-pruned-lookahead-d2"


def test_priority_and_ordinary_flows_both_use_core_lookahead():
    priority = run_hybrid_slot(make_input(flows=1, priorities=(1,)))
    ordinary = run_hybrid_slot(make_input(flows=1))

    assert priority.placements[0].path is PipelinePath.LOOKAHEAD
    assert ordinary.placements[0].path is PipelinePath.LOOKAHEAD
    assert {
        priority.placements[0].activation_reason,
        ordinary.placements[0].activation_reason,
    } == {"default-pruned-lookahead-d2"}


def test_explicit_mc_runs_a_complete_slot_with_only_focal_commits():
    parameters = HybridPolicyParameters(
        candidates_per_stage=2,
        lookahead_future_flows=2,
        monte_carlo_noisy_future_flows=1,
        monte_carlo_samples=1,
        rollout_epsilon=0.10,
    )
    result = run_hybrid_slot(
        make_input(flows=4, replicas=2, parameters=parameters),
        policy_mode="mc",
    )

    assert len(result.placements) == 4
    assert result.final_loads.total_assignments == 8
    assert len(result.observations) == 8
    assert len(result.measured_pairs) == 4
    for position, placement in enumerate(result.placements, start=1):
        assert placement.path is PipelinePath.MONTE_CARLO
        assert placement.activation_reason == "explicit-production-monte-carlo-v5"
        assert isinstance(placement.policy_detail, HybridMonteCarloDecision)
        assert placement.policy_detail.root_mode is MonteCarloRootMode.PRODUCTION_TOP_FIVE
        assert placement.policy_detail.decision_position == position
        assert placement.policy_detail.flow_id == placement.flow.flow_id
        assert placement.state_after == placement.state_before.apply(
            placement.action,
            result.configuration,
        )
        assert placement.state_after.total_assignments == 2 * position


def test_explicit_mc_carries_beliefs_across_slots():
    parameters = HybridPolicyParameters(
        candidates_per_stage=2,
        monte_carlo_noisy_future_flows=1,
        monte_carlo_samples=1,
    )
    first_input = make_input(
        flows=3,
        replicas=2,
        parameters=parameters,
        root_seed=9876,
    )
    first = run_hybrid_slot(first_input, policy_mode="mc")
    second = run_hybrid_slot(
        first_input.with_beliefs(first.beliefs_after_mapping),
        policy_mode="mc",
    )

    assert second.beliefs_before == first.beliefs_after
    assert second.slot_id == first.slot_id + 1
    assert all(
        placement.path is PipelinePath.MONTE_CARLO
        for placement in second.placements
    )


def test_full_slot_parallel_mc_matches_one_worker_fixed_seed():
    parameters = HybridPolicyParameters(
        candidates_per_stage=2,
        monte_carlo_noisy_future_flows=1,
        monte_carlo_samples=2,
    )
    slot_input = make_input(
        flows=3,
        replicas=2,
        parameters=parameters,
        root_seed=2468,
    )

    sequential = run_hybrid_slot(
        slot_input,
        policy_mode="mc",
        mc_workers=1,
    )
    parallel = run_hybrid_slot(
        slot_input,
        policy_mode="mc",
        mc_workers=3,
    )

    assert deterministic_projection(parallel) == deterministic_projection(
        sequential
    )


def test_full_slot_mc_reuses_one_worker_pool_then_shuts_it_down(monkeypatch):
    parameters = HybridPolicyParameters(
        candidates_per_stage=2,
        monte_carlo_noisy_future_flows=1,
        monte_carlo_samples=1,
    )
    slot_input = make_input(flows=3, replicas=2, parameters=parameters)
    from IBG_Hybrid import IBGHybridPolicy

    policy = IBGHybridPolicy(slot_input.configuration, slot_input.parameters)
    original = policy.select_monte_carlo
    executors = []

    def record_executor(**kwargs):
        executors.append(kwargs["rollout_executor"])
        return original(**kwargs)

    monkeypatch.setattr(policy, "select_monte_carlo", record_executor)
    run_hybrid_slot(slot_input, policy=policy, policy_mode="mc", mc_workers=3)

    assert len(executors) == 3
    assert all(executor is executors[0] for executor in executors)
    with pytest.raises(RuntimeError):
        executors[0].submit(int, 1)


def test_unknown_explicit_slot_policy_is_rejected():
    with pytest.raises(ValueError, match="policy_mode"):
        run_hybrid_slot(make_input(flows=1), policy_mode="automatic-mc")


def test_authoritative_contention_threshold_activates_lookahead():
    configuration = HybridConfiguration(num_flows=8, num_replicas=1)
    only_two_ready = {
        ReplicaChoice(1, 1): True,
        ReplicaChoice(2, 1): True,
        ReplicaChoice(3, 1): False,
    }
    slot_input = make_input(
        flows=8,
        replicas=1,
        ready=only_two_ready,
        capacity=10,
        parameters=DEFAULT_HYBRID_POLICY_PARAMETERS,
    )
    result = run_hybrid_slot(slot_input)

    assert result.placements[-1].activation.contention_ratio == pytest.approx(0.7)
    assert result.placements[-1].path is PipelinePath.LOOKAHEAD
    assert (
        result.placements[-1].activation_reason
        == "default-pruned-lookahead-d2"
    )


def test_simulation_returns_only_selected_final_load_observations():
    result = run_hybrid_slot(make_input(flows=5, replicas=3))
    selected = {
        (placement.flow.flow_id, choice)
        for placement in result.placements
        for choice in placement.action.choices
    }

    assert len(result.observations) == 10
    assert {
        (observation.flow_id, observation.choice)
        for observation in result.observations
    } == selected
    assert all(
        observation.assigned_load
        == result.final_loads.load_for(observation.choice)
        for observation in result.observations
    )
    assert all(
        (observation.flow_id, observation.choice.stage)
        not in {
            (placement.flow.flow_id, placement.skipped_stage)
            for placement in result.placements
        }
        for observation in result.observations
    )


def test_physical_and_observation_jitter_use_exact_separate_helpers():
    slot_input = make_input(flows=1, replicas=1)
    result = run_hybrid_slot(slot_input)
    profile_by_choice = slot_input.replica_by_choice

    for observation in result.observations:
        profile = profile_by_choice[observation.choice]
        expected_physical = exact_latency.sample_latency_ms(
            observation.assigned_load,
            exact_latency.require_state_parameters(profile.hidden_state),
            np.random.default_rng(observation.physical_seed),
        )
        expected_signal, expected_jitter = (
            exact_latency.sample_learning_signal_ms(
                expected_physical,
                profile.hidden_state,
                np.random.default_rng(observation.observation_seed),
            )
        )
        assert observation.physical_processing_latency_ms == expected_physical
        assert observation.observation_jitter_ms == expected_jitter
        assert observation.learning_signal_ms == expected_signal
        assert observation.likelihood == (
            exact_latency.learning_signal_likelihood(
                expected_signal,
                observation.assigned_load,
            )
        )


def test_observation_jitter_is_excluded_from_physical_utility_and_sla():
    result = run_hybrid_slot(make_input(flows=2, measured_pair=200.0))
    physical_latency = dict(
        result.metrics.physical_processing_latency_ms_per_flow
    )
    pair_latency = dict(result.metrics.measured_pair_latency_ms_per_flow)

    assert result.metrics.physical_only_sla_violations == SLA_v(
        outcome_latency_ms_per_flow(physical_latency, pair_latency),
        exact_latency.DEFAULT_SLA_LATENCY_MS,
    )
    assert dict(result.metrics.raw_end_to_end_latency_ms_per_flow) == {
        flow: physical_latency[flow] + pair_latency[flow]
        for flow in physical_latency
    }


def test_learning_is_selected_only_uses_retention_point_eight_and_strict_equilibrium():
    slot_input = make_input(flows=1, replicas=2)
    result = run_hybrid_slot(slot_input)
    selected = {choice for placement in result.placements for choice in placement.action.choices}
    before = dict(result.beliefs_before)
    after = dict(result.beliefs_after)

    assert any(after[choice] != before[choice] for choice in selected)
    assert all(
        after[choice] == before[choice]
        for choice in before
        if choice not in selected
    )
    assert result.metrics.equilibrium == (
        result.metrics.maximum_belief_change < 0.033
    )
    observation = result.observations[0]
    prior = before[observation.choice]
    denominator = sum(
        prior_value * likelihood
        for prior_value, likelihood in zip(prior, observation.likelihood)
    )
    local_posterior = tuple(
        round(prior_value * likelihood / denominator, 3)
        for prior_value, likelihood in zip(prior, observation.likelihood)
    )
    assert after[observation.choice] == tuple(
        round(0.8 * prior_value + 0.2 * posterior_value, 3)
        for prior_value, posterior_value in zip(prior, local_posterior)
    )


def test_planning_link_and_measured_pair_outcome_remain_separate():
    low_planning = run_hybrid_slot(
        make_input(flows=1, planning_link=0.25, measured_pair=9.5)
    )
    high_planning = run_hybrid_slot(
        make_input(flows=1, planning_link=1.25, measured_pair=9.5)
    )
    placement = low_planning.placements[0]

    assert dict(
        low_planning.metrics.measured_pair_latency_ms_per_flow
    ) == {1: 9.5}
    assert placement.objective_value == pytest.approx(
        high_planning.placements[0].objective_value + 1.0
    )
    physical_utility = dict(
        low_planning.metrics.physical_realized_utility_per_flow
    )[1]
    assert dict(
        low_planning.metrics.raw_end_to_end_reference_utility_per_flow
    )[1] == (
        pytest.approx(physical_utility - 9.5)
    )


def test_physical_utility_fairness_and_sla_match_exact_helpers():
    import header as exact_header

    result = run_hybrid_slot(make_input(flows=3))
    physical_by_flow = dict(
        result.metrics.physical_realized_utility_per_flow
    )
    expected_by_flow = dict(
        result.metrics.aggregate_expected_utility_per_flow
    )
    fairness_input = {
        flow_id: [value]
        for flow_id, value in expected_by_flow.items()
    }

    assert result.metrics.physical_realized_utility == pytest.approx(
        sum(
            exact_latency.DEFAULT_REWARD
            - observation.physical_processing_latency_ms
            - exact_latency.DEFAULT_COST
            for observation in result.observations
        )
    )
    assert result.metrics.physical_realized_utility == pytest.approx(
        sum(physical_by_flow.values())
    )
    assert result.metrics.jain_fairness == exact_header.jain_index(
        fairness_input,
        sum(expected_by_flow.values()),
    )
    assert result.metrics.physical_only_sla_violations == SLA_v(
        dict(result.metrics.physical_processing_latency_ms_per_flow),
        110.0,
    )


def test_repeated_slots_are_deterministic_and_beliefs_carry_forward():
    slot_input = make_input(flows=3, root_seed=9876)
    first = run_hybrid_slot(slot_input)
    repeat = run_hybrid_slot(slot_input)
    next_input = slot_input.with_beliefs(first.beliefs_after_mapping)
    second = run_hybrid_slot(next_input)

    assert deterministic_projection(first) == deterministic_projection(repeat)
    assert second.beliefs_before == first.beliefs_after
    assert second.slot_id == first.slot_id + 1


class IncompleteAdapter:
    def __init__(self, delegate):
        self.delegate = delegate

    def execute(self, **kwargs):
        complete = self.delegate.execute(**kwargs)
        return HybridSimulationResult(
            observations=complete.observations[:-1],
            measured_pairs=complete.measured_pairs,
        )


def test_incomplete_observation_set_fails_before_learning():
    from IBG_Hybrid.simulation import InProcessHybridSimulationAdapter

    with pytest.raises(RuntimeError, match="observation"):
        run_hybrid_slot(
            make_input(flows=1),
            simulation_adapter=IncompleteAdapter(
                InProcessHybridSimulationAdapter()
            ),
        )


def test_no_ready_complete_action_fails_explicitly():
    configuration = HybridConfiguration(num_flows=1, num_replicas=1)
    ready = {choice: False for choice in all_choices(configuration)}

    with pytest.raises(RuntimeError, match="no feasible"):
        run_hybrid_slot(make_input(flows=1, replicas=1, ready=ready))


def test_missing_admission_or_planning_link_metadata_fails_explicitly():
    slot_input = make_input(flows=1, replicas=1)
    missing_replica = replace(
        slot_input,
        replicas=tuple(
            replica
            for replica in slot_input.replicas
            if replica.choice.stage == 1
        ),
    )
    missing_links = replace(slot_input, planning_pair_links=())

    with pytest.raises(RuntimeError, match="no feasible"):
        run_hybrid_slot(missing_replica)
    with pytest.raises(RuntimeError, match="no feasible"):
        run_hybrid_slot(missing_links)


def test_missing_selected_pair_outcome_fails_explicitly():
    slot_input = make_input(flows=1, replicas=1)
    slot_input = replace(slot_input, simulated_pair_outcomes=())

    with pytest.raises(RuntimeError, match="measured-pair"):
        run_hybrid_slot(slot_input)


def test_compact_output_is_one_line_and_slot_has_no_file_side_effects(tmp_path):
    slot_input = make_input(flows=1)
    before = set(tmp_path.iterdir())
    output = io.StringIO()
    previous = os.getcwd()
    os.chdir(tmp_path)
    try:
        with contextlib.redirect_stdout(output):
            result = run_and_print_hybrid_slot(slot_input)
    finally:
        os.chdir(previous)

    assert output.getvalue() == format_hybrid_slot_metrics(result) + "\n"
    assert len(output.getvalue().splitlines()) == 1
    assert set(tmp_path.iterdir()) == before


def test_importing_phase5_is_silent_and_does_not_run_a_slot(tmp_path):
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import IBG_Hybrid; import IBG_Hybrid.runner; import IBG_Hybrid.main",
        ],
        cwd=tmp_path,
        env={
            **os.environ,
            "PYTHONPATH": str(
                os.path.join(os.path.dirname(__file__), "..")
            ),
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert list(tmp_path.iterdir()) == []


def test_physical_only_110ms_sla_uses_two_selected_stages():
    configuration = HybridConfiguration(num_flows=8, num_replicas=1)
    ready = {
        ReplicaChoice(1, 1): True,
        ReplicaChoice(2, 1): True,
        ReplicaChoice(3, 1): False,
    }
    result = run_hybrid_slot(
        make_input(
            flows=8,
            replicas=1,
            ready=ready,
            capacity=20,
            measured_pair=0.0,
        )
    )
    physical = dict(
        result.metrics.physical_processing_latency_ms_per_flow
    )

    assert all(
        len(placement.action.choices) == 2
        for placement in result.placements
    )
    assert result.metrics.physical_only_sla_violations == sum(
        latency > 110.0 for latency in physical.values()
    )
    assert result.metrics.physical_only_sla_violations > 0


def test_seeded_default_20x3x10_slot_keeps_production_parameters():
    configuration = HybridConfiguration()
    peaked = {
        choice: PEAKED_BELIEF
        for choice in all_choices(configuration)
    }
    slot_input = make_default_hybrid_slot_input(beliefs=peaked)
    result = run_hybrid_slot(slot_input)

    assert result.configuration == configuration
    assert result.parameters == DEFAULT_HYBRID_POLICY_PARAMETERS
    assert len(result.placements) == 20
    assert result.final_loads.total_assignments == 40
    assert len(result.observations) == 40
    assert len(result.measured_pairs) == 20
    assert all(
        placement.candidate_accounting.pruned_actions <= 75
        for placement in result.placements
    )
    assert all(
        placement.path is PipelinePath.LOOKAHEAD
        for placement in result.placements
    )
    assert [
        placement.policy_detail.selected_evaluation.effective_depth
        for placement in result.placements
    ] == [2] * 18 + [1, 0]
