import random
import time
from itertools import combinations, product
from random import Random

import pytest

import IBG_Hybrid.policy as policy_module
from IBG_Hybrid import (
    D_LOOKAHEAD,
    D_MC,
    GlobalLoadState,
    HYBRID_MC_ROOT_SHORTLIST_SIZE,
    HybridConfiguration,
    HybridPolicyParameters,
    IBGHybridPolicy,
    MonteCarloRootMode,
    NoFeasibleMonteCarloAction,
    PipelinePath,
    ReplicaChoice,
    RolloutChoiceMode,
    RolloutPhase,
    TwoStageAction,
)
from IBG_Hybrid.expected_utility import expected_stage_utility_from_belief
from IBG_Hybrid.phase0_contract import (
    HYBRID_POLICY_CONTRACT_VERSION,
    HYBRID_ROLLOUT_SEED_SCHEME,
    HybridActivationContext,
    ReplicaAdmission,
    derive_rollout_seed,
    evaluate_phase0_feasibility,
    select_pipeline_path,
)


def action(*pairs):
    return TwoStageAction(
        tuple(ReplicaChoice(stage, replica) for stage, replica in pairs)
    )


def action_key(candidate):
    return tuple(
        (choice.stage, choice.replica) for choice in candidate.choices
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


def reference_monte_carlo(policy, configuration, **kwargs):
    return policy.select_monte_carlo_all_roots_reference(
        state=kwargs.get("state") or GlobalLoadState.empty(configuration),
        admission=kwargs.get("admission") or full_admission(configuration),
        beliefs=kwargs.get("beliefs") or uniform_beliefs(configuration),
        known_pair_link_costs=(
            kwargs.get("link_costs") or full_link_costs(configuration)
        ),
        root_seed=kwargs.get("root_seed", 2050),
        slot_id=4,
        decision_position=2,
        flow_id=17,
    )


def test_production_mc_ranks_full_pool_and_samples_exactly_top_five():
    configuration = HybridConfiguration(num_flows=1, num_replicas=2)
    policy = IBGHybridPolicy(
        configuration,
        HybridPolicyParameters(monte_carlo_samples=2),
    )
    state = GlobalLoadState.empty(configuration)
    admission = full_admission(configuration)
    beliefs = uniform_beliefs(configuration)
    links = full_link_costs(configuration)
    greedy = policy.select_greedy(
        state=state,
        admission=admission,
        beliefs=beliefs,
        known_pair_link_costs=links,
    )
    decision = select_monte_carlo(
        policy,
        configuration,
        state=state,
        admission=admission,
        beliefs=beliefs,
        link_costs=links,
    )

    expected_ranking = tuple(
        sorted(
            greedy.scored_actions,
            key=lambda scored: (-scored.objective_value, action_key(scored.action)),
        )
    )
    assert decision.policy_contract_version == "ibg-hybrid-policy-contract-v5"
    assert decision.policy_contract_version == HYBRID_POLICY_CONTRACT_VERSION
    assert decision.root_mode is MonteCarloRootMode.PRODUCTION_TOP_FIVE
    assert decision.root_shortlist_size == HYBRID_MC_ROOT_SHORTLIST_SIZE == 5
    assert decision.ranked_root_pool == expected_ranking
    assert decision.sampled_roots == expected_ranking[:5]
    assert decision.excluded_roots == expected_ranking[5:]
    assert len(decision.evaluations) == 5


def test_canonical_tie_at_fifth_root_boundary():
    configuration = HybridConfiguration(num_flows=1, num_replicas=2)
    decision = select_monte_carlo(
        IBGHybridPolicy(
            configuration,
            HybridPolicyParameters(monte_carlo_samples=1),
        ),
        configuration,
    )

    assert len({root.objective_value for root in decision.ranked_root_pool}) == 1
    expected = tuple(
        sorted(
            (root.action for root in decision.ranked_root_pool),
            key=action_key,
        )[:5]
    )
    assert tuple(root.action for root in decision.sampled_roots) == expected
    assert decision.result.action == expected[0]


def test_fewer_than_five_roots_retains_every_feasible_root():
    configuration = HybridConfiguration(num_flows=1, num_replicas=1)
    decision = select_monte_carlo(
        IBGHybridPolicy(configuration),
        configuration,
    )

    assert decision.full_root_count == 3
    assert len(decision.sampled_roots) == 3
    assert decision.excluded_roots == ()
    assert len(decision.evaluations) == 3


def test_outside_shortlist_roots_receive_no_samples_and_cannot_win():
    configuration = HybridConfiguration(num_flows=2, num_replicas=2)
    decision = select_monte_carlo(
        IBGHybridPolicy(
            configuration,
            HybridPolicyParameters(monte_carlo_samples=3),
        ),
        configuration,
    )

    attempted = {
        evaluation.focal_action for evaluation in decision.evaluations
    } | {
        rejected.focal_action for rejected in decision.rejected_candidates
    }
    excluded = {root.action for root in decision.excluded_roots}
    assert attempted == {root.action for root in decision.sampled_roots}
    assert attempted.isdisjoint(excluded)
    assert decision.result.action in attempted


def test_every_retained_root_receives_exactly_s50_independent_samples():
    configuration = HybridConfiguration(num_flows=1, num_replicas=2)
    decision = select_monte_carlo(IBGHybridPolicy(configuration), configuration)

    assert decision.requested_samples == 50
    assert decision.rollout_seed_scheme == HYBRID_ROLLOUT_SEED_SCHEME
    assert len(decision.evaluations) == 5
    assert all(
        evaluation.requested_samples == 50
        and evaluation.completed_samples == 50
        and evaluation.failed_sample_count == 0
        and tuple(sample.sample_index for sample in evaluation.samples)
        == tuple(range(50))
        for evaluation in decision.evaluations
    )
    seeds = {
        sample.derived_seed
        for evaluation in decision.evaluations
        for sample in evaluation.samples
    }
    assert len(seeds) == 5 * 50


def test_lookahead_and_mc_depths_are_independent():
    configuration = HybridConfiguration(num_flows=12, num_replicas=1)
    parameters = HybridPolicyParameters(
        lookahead_future_flows=D_LOOKAHEAD,
        monte_carlo_noisy_future_flows=D_MC,
        monte_carlo_samples=1,
        rollout_epsilon=0.0,
    )
    policy = IBGHybridPolicy(configuration, parameters)
    admission = full_admission(configuration)
    beliefs = uniform_beliefs(configuration)
    links = full_link_costs(configuration)

    lookahead = policy.select_lookahead(
        state=GlobalLoadState.empty(configuration),
        admission=admission,
        beliefs=beliefs,
        known_pair_link_costs=links,
    )
    monte_carlo = select_monte_carlo(
        policy,
        configuration,
        admission=admission,
        beliefs=beliefs,
        link_costs=links,
    )

    assert D_LOOKAHEAD == 2
    assert D_MC == 10
    assert {evaluation.requested_depth for evaluation in lookahead.evaluations} == {2}
    assert {evaluation.effective_depth for evaluation in lookahead.evaluations} == {2}
    assert monte_carlo.requested_mc_depth == 10
    assert monte_carlo.effective_mc_depth == 10
    assert monte_carlo.tail_length == 1


def test_mc_depth_clamps_near_slot_end():
    configuration = HybridConfiguration(num_flows=4, num_replicas=1)
    previous = action((1, 1), (2, 1))
    near_end = GlobalLoadState.empty(configuration).apply(
        previous, configuration
    ).apply(previous, configuration)
    decision = select_monte_carlo(
        IBGHybridPolicy(
            configuration,
            HybridPolicyParameters(monte_carlo_samples=2),
        ),
        configuration,
        state=near_end,
    )

    assert decision.requested_mc_depth == 10
    assert decision.effective_mc_depth == 1
    assert decision.tail_length == 0
    assert all(
        len(sample.noisy_window_steps) == 1
        and sample.pure_greedy_tail_steps == ()
        for evaluation in decision.evaluations
        for sample in evaluation.samples
    )


def test_noisy_window_uses_seeded_uniform_current_pool_at_epsilon_one():
    configuration = HybridConfiguration(num_flows=2, num_replicas=2)
    decision = select_monte_carlo(
        IBGHybridPolicy(
            configuration,
            HybridPolicyParameters(
                monte_carlo_noisy_future_flows=1,
                monte_carlo_samples=4,
                rollout_epsilon=1.0,
            ),
        ),
        configuration,
    )

    for evaluation in decision.evaluations:
        for sample in evaluation.samples:
            step = sample.noisy_window_steps[0]
            expected_index = Random(sample.derived_seed).randrange(
                len(step.feasible_actions)
            )
            assert step.rollout_phase is RolloutPhase.NOISY_WINDOW
            assert step.choice_mode is RolloutChoiceMode.EXPLORATION
            assert step.chosen_action == step.feasible_actions[expected_index]


def test_default_epsilon_window_contains_greedy_and_exploration_choices():
    configuration = HybridConfiguration(num_flows=3, num_replicas=2)
    decision = select_monte_carlo(IBGHybridPolicy(configuration), configuration)
    modes = {
        step.choice_mode
        for evaluation in decision.evaluations
        for sample in evaluation.samples
        for step in sample.noisy_window_steps
    }

    assert modes == {
        RolloutChoiceMode.GREEDY,
        RolloutChoiceMode.EXPLORATION,
    }


def test_after_mc_window_every_remaining_flow_is_pure_updated_state_greedy():
    configuration = HybridConfiguration(num_flows=4, num_replicas=2)
    policy = IBGHybridPolicy(
        configuration,
        HybridPolicyParameters(
            monte_carlo_noisy_future_flows=1,
            monte_carlo_samples=2,
            rollout_epsilon=1.0,
        ),
    )
    admission = full_admission(configuration)
    beliefs = uniform_beliefs(configuration)
    links = full_link_costs(configuration)
    decision = select_monte_carlo(
        policy,
        configuration,
        admission=admission,
        beliefs=beliefs,
        link_costs=links,
    )

    assert decision.effective_mc_depth == 1
    assert decision.tail_length == 2
    for evaluation in decision.evaluations:
        for sample in evaluation.samples:
            assert len(sample.noisy_window_steps) == 1
            assert len(sample.pure_greedy_tail_steps) == 2
            for step in sample.pure_greedy_tail_steps:
                direct = policy.select_greedy(
                    state=step.state_before,
                    admission=admission,
                    beliefs=beliefs,
                    known_pair_link_costs=links,
                )
                assert step.rollout_phase is RolloutPhase.PURE_GREEDY_TAIL
                assert step.choice_mode is RolloutChoiceMode.GREEDY
                assert step.chosen_action == step.greedy_action
                assert step.chosen_action == direct.result.action
                assert step.accounting == direct.accounting
            assert sample.projected_final_state.total_assignments == 8


def test_every_window_and_tail_step_rebuilds_phase2_at_updated_state():
    configuration = HybridConfiguration(num_flows=4, num_replicas=2)
    policy = IBGHybridPolicy(
        configuration,
        HybridPolicyParameters(
            monte_carlo_noisy_future_flows=2,
            monte_carlo_samples=1,
            rollout_epsilon=1.0,
        ),
    )
    admission = full_admission(configuration)
    beliefs = uniform_beliefs(configuration)
    links = full_link_costs(configuration)
    decision = select_monte_carlo(
        policy,
        configuration,
        admission=admission,
        beliefs=beliefs,
        link_costs=links,
    )

    for evaluation in decision.evaluations:
        for step in evaluation.samples[0].continuation_steps:
            direct = policy.select_greedy(
                state=step.state_before,
                admission=admission,
                beliefs=beliefs,
                known_pair_link_costs=links,
            )
            assert step.greedy_action == direct.result.action
            assert step.feasible_actions == tuple(
                scored.action for scored in direct.scored_actions
            )
            assert step.accounting == direct.accounting
            assert evaluate_phase0_feasibility(
                step.chosen_action,
                step.state_before,
                configuration,
                admission,
                links,
            ).feasible


def test_mc_never_calls_lookahead_or_recursively_calls_mc(monkeypatch):
    configuration = HybridConfiguration(num_flows=3, num_replicas=1)
    policy = IBGHybridPolicy(
        configuration,
        HybridPolicyParameters(monte_carlo_samples=1),
    )
    production_entry = policy.select_monte_carlo

    def forbidden(*_args, **_kwargs):
        raise AssertionError("MC invoked a forbidden strategic policy")

    monkeypatch.setattr(policy, "select_lookahead", forbidden)
    monkeypatch.setattr(policy, "select_monte_carlo", forbidden)
    decision = production_entry(
        state=GlobalLoadState.empty(configuration),
        admission=full_admission(configuration),
        beliefs=uniform_beliefs(configuration),
        known_pair_link_costs=full_link_costs(configuration),
        root_seed=2050,
        slot_id=1,
        decision_position=1,
        flow_id=1,
    )

    assert decision.evaluations


def test_branches_are_isolated_and_only_selected_focal_is_committed():
    configuration = HybridConfiguration(num_flows=4, num_replicas=2)
    state = GlobalLoadState.empty(configuration)
    admission = full_admission(configuration)
    beliefs = uniform_beliefs(configuration)
    links = full_link_costs(configuration)
    before = (dict(admission), dict(beliefs), dict(links))
    policy = IBGHybridPolicy(
        configuration,
        HybridPolicyParameters(monte_carlo_samples=2),
    )

    first = select_monte_carlo(
        policy,
        configuration,
        state=state,
        admission=admission,
        beliefs=beliefs,
        link_costs=links,
    )
    second = select_monte_carlo(
        policy,
        configuration,
        state=state,
        admission=admission,
        beliefs=beliefs,
        link_costs=links,
    )

    assert first == second
    assert state == GlobalLoadState.empty(configuration)
    assert (admission, beliefs, links) == before
    assert first.result.state_after == state.apply(
        first.result.action, configuration
    )
    assert first.result.state_after.total_assignments == 2
    assert all(
        sample.projected_final_state.total_assignments == 8
        for evaluation in first.evaluations
        for sample in evaluation.samples
    )


def test_focal_value_is_evaluated_once_at_final_projected_load(monkeypatch):
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
    links = full_link_costs(configuration, cost=1_000.0)
    links[(focal.choices[0], focal.choices[1])] = 7.0
    monkeypatch.setattr(
        policy_module,
        "expected_stage_utility_from_belief",
        lambda belief, load: values[tuple(belief)][load - 1],
    )
    decision = select_monte_carlo(
        IBGHybridPolicy(
            configuration,
            HybridPolicyParameters(monte_carlo_samples=3, rollout_epsilon=0.0),
        ),
        configuration,
        beliefs=beliefs,
        link_costs=links,
    )

    assert decision.result.action == focal
    assert decision.result.state_after.loads == ((1,), (1,), (0,))
    assert all(
        sample.projected_final_state.loads == ((2,), (2,), (0,))
        and sample.focal_value == pytest.approx(30.0 + 20.0 - 7.0)
        for sample in decision.selected_evaluation.samples
    )
    assert decision.result.objective_value == pytest.approx(43.0)


def test_seed_derivation_is_fixed_reproducible_local_and_isolated():
    configuration = HybridConfiguration(num_flows=3, num_replicas=2)
    policy = IBGHybridPolicy(
        configuration,
        HybridPolicyParameters(monte_carlo_samples=4, rollout_epsilon=1.0),
    )
    random.seed(991)
    global_state_before = random.getstate()

    first = select_monte_carlo(policy, configuration, root_seed=2050)
    second = select_monte_carlo(policy, configuration, root_seed=2050)
    other_seed = select_monte_carlo(policy, configuration, root_seed=2051)

    assert first == second
    assert first != other_seed
    assert random.getstate() == global_state_before
    assert all(
        sample.derived_seed == derive_rollout_seed(sample.seed_key)
        for evaluation in first.evaluations
        for sample in evaluation.samples
    )


def test_all_dead_end_samples_reject_every_shortlisted_candidate():
    configuration = HybridConfiguration(num_flows=2, num_replicas=1)
    policy = IBGHybridPolicy(
        configuration,
        HybridPolicyParameters(monte_carlo_samples=4),
    )

    with pytest.raises(NoFeasibleMonteCarloAction) as raised:
        select_monte_carlo(
            policy,
            configuration,
            admission=full_admission(configuration, capacity=1),
        )

    assert len(raised.value.rejected_candidates) == 3
    assert all(
        len(candidate.failed_samples) == 4
        for candidate in raised.value.rejected_candidates
    )


def test_historical_all_root_method_remains_explicit_reference_only():
    configuration = HybridConfiguration(num_flows=3, num_replicas=6)
    parameters = HybridPolicyParameters(
        lookahead_future_flows=2,
        monte_carlo_noisy_future_flows=10,
        monte_carlo_samples=1,
        rollout_epsilon=0.0,
    )
    policy = IBGHybridPolicy(configuration, parameters)

    production = select_monte_carlo(policy, configuration)
    historical = reference_monte_carlo(policy, configuration)

    assert production.root_mode is MonteCarloRootMode.PRODUCTION_TOP_FIVE
    assert len(production.sampled_roots) == 5
    assert production.requested_mc_depth == 10
    assert historical.root_mode is MonteCarloRootMode.HISTORICAL_ALL_FEASIBLE
    assert len(historical.sampled_roots) == 75
    assert historical.excluded_roots == ()
    assert historical.requested_mc_depth == 2
    assert historical.effective_mc_depth == 2
    assert historical.tail_length == 0


def test_automatic_slot_path_still_cannot_select_mc():
    selected = select_pipeline_path(
        HybridActivationContext(
            contention_ratio=1.0,
            maximum_normalized_belief_entropy=1.0,
            high_priority=True,
        )
    )

    assert selected is PipelinePath.LOOKAHEAD


def test_seeded_20x3x10_production_mc_boundary_reports_local_runtime():
    configuration = HybridConfiguration()
    started = time.perf_counter()
    decision = select_monte_carlo(
        IBGHybridPolicy(configuration),
        configuration,
        admission=full_admission(configuration, capacity=20),
    )
    elapsed_seconds = time.perf_counter() - started

    assert decision.focal_accounting.available_actions == 300
    assert decision.focal_accounting.feasible_pruned_actions == 75
    assert decision.full_root_count == 75
    assert len(decision.sampled_roots) == 5
    assert decision.excluded_root_count == 70
    assert decision.requested_samples == 50
    assert decision.requested_mc_depth == 10
    assert decision.effective_mc_depth == 10
    assert decision.tail_length == 9
    assert len(decision.evaluations) == 5
    assert all(
        evaluation.completed_samples == 50
        and evaluation.failed_sample_count == 0
        and all(
            len(sample.noisy_window_steps) == 10
            and len(sample.pure_greedy_tail_steps) == 9
            and sample.projected_final_state.total_assignments == 40
            for sample in evaluation.samples
        )
        for evaluation in decision.evaluations
    )
    assert elapsed_seconds >= 0.0
