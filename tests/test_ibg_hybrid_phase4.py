import random
from itertools import combinations, product
from math import fsum
from random import Random

import pytest

import IBG_Hybrid.policy as policy_module
from IBG_Hybrid import (
    GlobalLoadState,
    HybridConfiguration,
    HybridPolicyParameters,
    IBGHybridPolicy,
    NoFeasibleMonteCarloAction,
    ReplicaChoice,
    RolloutChoiceMode,
    TwoStageAction,
)
from IBG_Hybrid.expected_utility import expected_stage_utility_from_belief
from IBG_Hybrid.oracle import solve_tiny_exhaustive
from IBG_Hybrid.phase0_contract import (
    HYBRID_ROLLOUT_SEED_SCHEME,
    ReplicaAdmission,
    derive_rollout_seed,
    evaluate_phase0_feasibility,
)


def action(*pairs):
    return TwoStageAction(
        tuple(ReplicaChoice(stage, replica) for stage, replica in pairs)
    )


def choices(configuration):
    return tuple(
        ReplicaChoice(stage, replica)
        for stage in range(1, configuration.num_stages + 1)
        for replica in range(1, configuration.num_replicas + 1)
    )


def full_admission(configuration, *, capacity=20):
    return {
        choice: ReplicaAdmission(
            choice=choice,
            ready=True,
            max_assigned_flows=capacity,
        )
        for choice in choices(configuration)
    }


def full_link_costs(configuration, *, cost=0.0):
    costs = {}
    for stage_a, stage_b in combinations(
        range(1, configuration.num_stages + 1),
        configuration.stage_budget,
    ):
        for replica_a, replica_b in product(
            range(1, configuration.num_replicas + 1),
            repeat=configuration.stage_budget,
        ):
            source = ReplicaChoice(stage_a, replica_a)
            target = ReplicaChoice(stage_b, replica_b)
            costs[(source, target)] = cost
    return costs


def uniform_beliefs(configuration, belief=(0.0, 0.0, 0.0, 1.0)):
    return {choice: belief for choice in choices(configuration)}


def select_monte_carlo(
    policy,
    configuration,
    *,
    state=None,
    admission=None,
    beliefs=None,
    link_costs=None,
    root_seed=2050,
):
    return policy.select_monte_carlo(
        state=state or GlobalLoadState.empty(configuration),
        admission=admission or full_admission(configuration),
        beliefs=beliefs or uniform_beliefs(configuration),
        known_pair_link_costs=link_costs or full_link_costs(configuration),
        root_seed=root_seed,
        slot_id=4,
        decision_position=2,
        flow_id=17,
    )


def test_phase4_attempts_exactly_s50_samples_for_every_focal_candidate():
    configuration = HybridConfiguration(num_flows=1, num_replicas=1)
    decision = select_monte_carlo(
        IBGHybridPolicy(configuration),
        configuration,
    )

    assert decision.requested_samples == 50
    assert decision.rollout_seed_scheme == HYBRID_ROLLOUT_SEED_SCHEME
    assert len(decision.evaluations) == 3
    assert decision.rejected_candidates == ()
    assert all(
        evaluation.requested_samples == 50
        and evaluation.completed_samples == 50
        and evaluation.failed_sample_count == 0
        and tuple(sample.sample_index for sample in evaluation.samples)
        == tuple(range(50))
        for evaluation in decision.evaluations
    )


@pytest.mark.parametrize(
    ("requested_depth", "expected_depth"),
    ((0, 0), (1, 1), (2, 2)),
)
def test_phase4_supports_d0_d1_and_d2(requested_depth, expected_depth):
    configuration = HybridConfiguration(num_flows=3, num_replicas=1)
    parameters = HybridPolicyParameters(
        lookahead_future_flows=requested_depth,
        monte_carlo_samples=2,
        rollout_epsilon=0.0,
    )
    decision = select_monte_carlo(
        IBGHybridPolicy(configuration, parameters),
        configuration,
    )

    assert all(
        evaluation.requested_depth == requested_depth
        and evaluation.effective_depth == expected_depth
        and all(
            len(sample.continuation_steps) == expected_depth
            for sample in evaluation.samples
        )
        for evaluation in decision.evaluations
    )


def test_phase4_clamps_depth_near_the_end_of_a_slot():
    configuration = HybridConfiguration(num_flows=4, num_replicas=1)
    previous = action((1, 1), (2, 1))
    near_end = GlobalLoadState.empty(configuration).apply(
        previous,
        configuration,
    ).apply(previous, configuration)
    parameters = HybridPolicyParameters(
        monte_carlo_samples=2,
        rollout_epsilon=0.0,
    )

    decision = select_monte_carlo(
        IBGHybridPolicy(configuration, parameters),
        configuration,
        state=near_end,
    )

    assert all(
        evaluation.requested_depth == 2
        and evaluation.effective_depth == 1
        and all(
            len(sample.continuation_steps) == 1
            for sample in evaluation.samples
        )
        for evaluation in decision.evaluations
    )


def test_phase4_uses_only_once_evaluated_focal_projected_value(monkeypatch):
    configuration = HybridConfiguration(num_flows=2, num_replicas=1)
    focal = action((1, 1), (2, 1))
    values = {
        (1, 1): (100.0, 30.0),
        (2, 1): (80.0, 20.0),
        (3, 1): (0.0, 0.0),
    }
    beliefs = {
        choice: (choice.stage, choice.replica)
        for choice in choices(configuration)
    }
    link_costs = full_link_costs(configuration, cost=1_000.0)
    link_costs[(focal.choices[0], focal.choices[1])] = 7.0
    parameters = HybridPolicyParameters(
        monte_carlo_samples=3,
        rollout_epsilon=0.0,
    )
    monkeypatch.setattr(
        policy_module,
        "expected_stage_utility_from_belief",
        lambda belief, load: values[tuple(belief)][load - 1],
    )

    decision = select_monte_carlo(
        IBGHybridPolicy(configuration, parameters),
        configuration,
        beliefs=beliefs,
        link_costs=link_costs,
    )
    selected = decision.selected_evaluation

    assert decision.result.action == focal
    assert decision.result.state_after.loads == ((1,), (1,), (0,))
    assert all(
        sample.state_after_focal.loads == ((1,), (1,), (0,))
        and sample.projected_final_state.loads == ((2,), (2,), (0,))
        and sample.continuation_actions == (focal,)
        and sample.focal_value == pytest.approx(30.0 + 20.0 - 7.0)
        for sample in selected.samples
    )
    assert selected.mean_focal_value == pytest.approx(43.0)
    assert selected.mean_focal_value != pytest.approx(173.0 + 43.0)
    assert selected.mean_focal_value != pytest.approx(43.0 + 43.0)


def test_phase4_epsilon_zero_is_always_phase2_greedy():
    configuration = HybridConfiguration(num_flows=3, num_replicas=2)
    parameters = HybridPolicyParameters(
        monte_carlo_samples=4,
        rollout_epsilon=0.0,
    )

    decision = select_monte_carlo(
        IBGHybridPolicy(configuration, parameters),
        configuration,
    )

    assert all(
        step.choice_mode is RolloutChoiceMode.GREEDY
        and step.chosen_action == step.greedy_action
        for evaluation in decision.evaluations
        for sample in evaluation.samples
        for step in sample.continuation_steps
    )


def test_phase4_epsilon_one_uses_seeded_uniform_feasible_draws():
    configuration = HybridConfiguration(num_flows=2, num_replicas=2)
    parameters = HybridPolicyParameters(
        lookahead_future_flows=1,
        monte_carlo_samples=8,
        rollout_epsilon=1.0,
    )

    decision = select_monte_carlo(
        IBGHybridPolicy(configuration, parameters),
        configuration,
    )

    for evaluation in decision.evaluations:
        for sample in evaluation.samples:
            step = sample.continuation_steps[0]
            expected_index = Random(sample.derived_seed).randrange(
                len(step.feasible_actions)
            )
            assert step.choice_mode is RolloutChoiceMode.EXPLORATION
            assert step.chosen_action == step.feasible_actions[expected_index]


def test_phase4_exploration_stays_inside_updated_feasible_pruned_pool():
    configuration = HybridConfiguration(num_flows=2, num_replicas=6)
    admission = full_admission(configuration)
    admission[ReplicaChoice(1, 6)] = ReplicaAdmission(
        ReplicaChoice(1, 6),
        ready=False,
        max_assigned_flows=20,
    )
    link_costs = full_link_costs(configuration)
    del link_costs[(ReplicaChoice(1, 1), ReplicaChoice(2, 1))]
    parameters = HybridPolicyParameters(
        lookahead_future_flows=1,
        monte_carlo_samples=5,
        rollout_epsilon=1.0,
    )

    decision = select_monte_carlo(
        IBGHybridPolicy(configuration, parameters),
        configuration,
        admission=admission,
        link_costs=link_costs,
    )

    for evaluation in decision.evaluations:
        for sample in evaluation.samples:
            step = sample.continuation_steps[0]
            selected = step.chosen_action
            assert selected in step.feasible_actions
            assert selected.stages[0] < selected.stages[1]
            assert all(
                choice in step.accounting.retained_by_stage[choice.stage - 1]
                for choice in selected.choices
            )
            assert evaluate_phase0_feasibility(
                selected,
                step.state_before,
                configuration,
                admission,
                link_costs,
            ).feasible


def test_phase4_seed_derivation_is_stable_isolated_and_local():
    configuration = HybridConfiguration(num_flows=2, num_replicas=2)
    parameters = HybridPolicyParameters(
        lookahead_future_flows=1,
        monte_carlo_samples=4,
        rollout_epsilon=1.0,
    )
    policy = IBGHybridPolicy(configuration, parameters)
    random.seed(991)
    global_state_before = random.getstate()

    first = select_monte_carlo(policy, configuration, root_seed=2050)
    second = select_monte_carlo(policy, configuration, root_seed=2050)
    other_seed = select_monte_carlo(policy, configuration, root_seed=2051)

    assert first == second
    assert random.getstate() == global_state_before
    first_seeds = {
        (evaluation.focal_action, sample.sample_index): sample.derived_seed
        for evaluation in first.evaluations
        for sample in evaluation.samples
    }
    other_seeds = {
        (evaluation.focal_action, sample.sample_index): sample.derived_seed
        for evaluation in other_seed.evaluations
        for sample in evaluation.samples
    }
    assert len(set(first_seeds.values())) == len(first_seeds)
    assert first_seeds != other_seeds
    assert all(
        sample.derived_seed == derive_rollout_seed(sample.seed_key)
        for evaluation in first.evaluations
        for sample in evaluation.samples
    )


def test_phase4_samples_and_inputs_do_not_leak_state():
    configuration = HybridConfiguration(num_flows=3, num_replicas=2)
    state = GlobalLoadState.empty(configuration)
    admission = full_admission(configuration)
    beliefs = uniform_beliefs(configuration)
    link_costs = full_link_costs(configuration)
    admission_before = dict(admission)
    beliefs_before = dict(beliefs)
    links_before = dict(link_costs)
    parameters = HybridPolicyParameters(
        monte_carlo_samples=4,
        rollout_epsilon=1.0,
    )

    decision = select_monte_carlo(
        IBGHybridPolicy(configuration, parameters),
        configuration,
        state=state,
        admission=admission,
        beliefs=beliefs,
        link_costs=link_costs,
    )

    assert state == GlobalLoadState.empty(configuration)
    assert admission == admission_before
    assert beliefs == beliefs_before
    assert link_costs == links_before
    for evaluation in decision.evaluations:
        expected_after_focal = state.apply(
            evaluation.focal_action,
            configuration,
        )
        for sample in evaluation.samples:
            assert sample.state_after_focal == expected_after_focal
            assert sample.projected_final_state.total_assignments == 6


def test_phase4_recomputes_phase2_at_every_updated_rollout_state():
    configuration = HybridConfiguration(num_flows=3, num_replicas=1)
    parameters = HybridPolicyParameters(
        monte_carlo_samples=2,
        rollout_epsilon=0.0,
    )
    policy = IBGHybridPolicy(configuration, parameters)
    admission = full_admission(configuration)
    beliefs = uniform_beliefs(configuration)
    link_costs = full_link_costs(configuration)

    decision = select_monte_carlo(
        policy,
        configuration,
        admission=admission,
        beliefs=beliefs,
        link_costs=link_costs,
    )

    for evaluation in decision.evaluations:
        for sample in evaluation.samples:
            for step in sample.continuation_steps:
                direct = policy.select_greedy(
                    state=step.state_before,
                    admission=admission,
                    beliefs=beliefs,
                    known_pair_link_costs=link_costs,
                )
                assert step.greedy_action == direct.result.action
                assert step.feasible_actions == tuple(
                    scored.action for scored in direct.scored_actions
                )
                assert step.accounting == direct.accounting


def test_phase4_canonical_ties_cover_greedy_steps_and_focal_mean(monkeypatch):
    configuration = HybridConfiguration(num_flows=2, num_replicas=1)
    canonical = action((1, 1), (2, 1))
    parameters = HybridPolicyParameters(
        lookahead_future_flows=1,
        monte_carlo_samples=3,
        rollout_epsilon=0.0,
    )
    monkeypatch.setattr(
        policy_module,
        "expected_stage_utility_from_belief",
        lambda _belief, _load: 1.0,
    )
    beliefs = {choice: (1.0,) for choice in choices(configuration)}

    decision = select_monte_carlo(
        IBGHybridPolicy(configuration, parameters),
        configuration,
        beliefs=beliefs,
    )

    assert decision.result.action == canonical
    assert all(
        sample.continuation_actions == (canonical,)
        for evaluation in decision.evaluations
        for sample in evaluation.samples
    )


def test_phase4_partial_failures_are_excluded_from_the_sample_mean():
    configuration = HybridConfiguration(num_flows=3, num_replicas=2)
    parameters = HybridPolicyParameters(
        monte_carlo_samples=20,
        rollout_epsilon=1.0,
    )

    decision = select_monte_carlo(
        IBGHybridPolicy(configuration, parameters),
        configuration,
        admission=full_admission(configuration, capacity=1),
        root_seed=2050,
    )
    partial = next(
        evaluation
        for evaluation in decision.evaluations
        if evaluation.failed_samples
    )

    assert 0 < partial.completed_samples < partial.requested_samples
    assert partial.failed_sample_count > 0
    assert partial.mean_focal_value == fsum(
        sample.focal_value for sample in partial.samples
    ) / partial.completed_samples


def test_phase4_all_dead_end_samples_reject_every_candidate():
    configuration = HybridConfiguration(num_flows=2, num_replicas=1)
    parameters = HybridPolicyParameters(monte_carlo_samples=4)

    with pytest.raises(NoFeasibleMonteCarloAction) as raised:
        select_monte_carlo(
            IBGHybridPolicy(configuration, parameters),
            configuration,
            admission=full_admission(configuration, capacity=1),
        )

    assert len(raised.value.rejected_candidates) == 3
    assert all(
        len(candidate.failed_samples) == 4
        and all(
            failure.completed_steps == ()
            and failure.failing_state == failure.state_after_focal
            for failure in candidate.failed_samples
        )
        for candidate in raised.value.rejected_candidates
    )


def test_phase4_epsilon_zero_agrees_with_phase3_lookahead():
    configuration = HybridConfiguration(num_flows=3, num_replicas=2)
    parameters = HybridPolicyParameters(
        monte_carlo_samples=4,
        rollout_epsilon=0.0,
    )
    policy = IBGHybridPolicy(configuration, parameters)
    admission = full_admission(configuration)
    beliefs = uniform_beliefs(configuration)
    link_costs = full_link_costs(configuration)
    state = GlobalLoadState.empty(configuration)

    lookahead = policy.select_lookahead(
        state=state,
        admission=admission,
        beliefs=beliefs,
        known_pair_link_costs=link_costs,
    )
    monte_carlo = select_monte_carlo(
        policy,
        configuration,
        state=state,
        admission=admission,
        beliefs=beliefs,
        link_costs=link_costs,
    )

    assert monte_carlo.result.action == lookahead.result.action
    assert monte_carlo.result.objective_value == pytest.approx(
        lookahead.result.objective_value
    )
    lookahead_by_action = {
        evaluation.focal_action: evaluation
        for evaluation in lookahead.evaluations
    }
    assert all(
        sample.continuation_actions
        == lookahead_by_action[evaluation.focal_action].continuation_actions
        and sample.focal_value
        == pytest.approx(
            lookahead_by_action[evaluation.focal_action].focal_value
        )
        for evaluation in monte_carlo.evaluations
        for sample in evaluation.samples
    )


def test_phase4_d0_matches_tiny_oracle_when_objectives_are_equivalent():
    configuration = HybridConfiguration(num_flows=1, num_replicas=2)
    parameters = HybridPolicyParameters(
        lookahead_future_flows=0,
        monte_carlo_samples=3,
    )
    state = GlobalLoadState.empty(configuration)
    admission = full_admission(configuration)
    beliefs = uniform_beliefs(
        configuration,
        belief=(0.0, 0.0, 1.0, 0.0),
    )
    beliefs[ReplicaChoice(1, 2)] = (0.0, 0.0, 0.0, 1.0)
    link_costs = full_link_costs(configuration, cost=4.0)
    link_costs[(ReplicaChoice(1, 2), ReplicaChoice(3, 1))] = 1.0

    decision = select_monte_carlo(
        IBGHybridPolicy(configuration, parameters),
        configuration,
        state=state,
        admission=admission,
        beliefs=beliefs,
        link_costs=link_costs,
    )

    def immediate_value(candidate, current_state):
        projected = current_state.apply(candidate, configuration)
        return (
            sum(
                expected_stage_utility_from_belief(
                    beliefs[choice],
                    projected.load_for(choice),
                )
                for choice in candidate.choices
            )
            - link_costs[(candidate.choices[0], candidate.choices[1])]
        )

    oracle = solve_tiny_exhaustive(
        configuration,
        state,
        remaining_flows=1,
        action_value=immediate_value,
        feasibility_check=lambda candidate, current_state: (
            evaluate_phase0_feasibility(
                candidate,
                current_state,
                configuration,
                admission,
                link_costs,
            )
        ),
    )

    assert decision.result.action == oracle.action
    assert decision.result.objective_value == pytest.approx(
        oracle.objective_value
    )


def test_phase4_20x3x10_s50_d2_boundary_completes_with_seeded_detail():
    configuration = HybridConfiguration()
    decision = select_monte_carlo(
        IBGHybridPolicy(configuration),
        configuration,
        admission=full_admission(configuration, capacity=20),
    )

    assert decision.requested_samples == 50
    assert decision.focal_accounting.available_actions == 300
    assert decision.focal_accounting.feasible_pruned_actions == 75
    assert len(decision.evaluations) == 75
    assert decision.rejected_candidates == ()
    assert all(
        evaluation.completed_samples == 50
        and evaluation.failed_sample_count == 0
        and evaluation.effective_depth == 2
        for evaluation in decision.evaluations
    )
