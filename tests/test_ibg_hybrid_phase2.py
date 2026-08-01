from itertools import combinations, product

import pytest

from IBG.latency_model import expected_state_utility
from IBG_Hybrid import (
    GlobalLoadState,
    HybridConfiguration,
    IBGHybridPolicy,
    ReplicaChoice,
    TwoStageAction,
)
from IBG_Hybrid.expected_utility import expected_stage_utility_from_belief
from IBG_Hybrid.oracle import solve_tiny_exhaustive
from IBG_Hybrid.phase0_contract import (
    ReplicaAdmission,
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


def test_phase2_records_readiness_capacity_and_link_rejections():
    configuration = HybridConfiguration(num_flows=3, num_replicas=2)
    previous = action((2, 2), (3, 2))
    state = GlobalLoadState.empty(configuration).apply(
        previous,
        configuration,
    )
    admission = full_admission(configuration, capacity=5)
    admission[ReplicaChoice(1, 2)] = ReplicaAdmission(
        ReplicaChoice(1, 2),
        ready=False,
        max_assigned_flows=5,
    )
    admission[ReplicaChoice(2, 2)] = ReplicaAdmission(
        ReplicaChoice(2, 2),
        ready=True,
        max_assigned_flows=1,
    )
    del admission[ReplicaChoice(3, 1)]

    link_costs = full_link_costs(configuration, cost=1.0)
    del link_costs[(ReplicaChoice(1, 1), ReplicaChoice(2, 1))]
    link_costs[(ReplicaChoice(1, 1), ReplicaChoice(3, 2))] = -1.0

    decision = IBGHybridPolicy(configuration).select_greedy(
        state=state,
        admission=admission,
        beliefs=uniform_beliefs(configuration),
        known_pair_link_costs=link_costs,
    )

    accounting = decision.accounting
    reasons = dict(accounting.rejection_reason_counts)
    assert accounting.available_replicas_by_stage == (2, 2, 1)
    assert accounting.locally_feasible_replicas_by_stage == (1, 1, 1)
    assert accounting.feasible_actions_before_pruning == 1
    assert accounting.retained_counts_by_stage == (1, 1, 1)
    assert accounting.pruned_actions == 3
    assert accounting.feasible_pruned_actions == 1
    assert reasons["not-ready:1:2"] > 0
    assert reasons["replica-flow-capacity:2:2"] > 0
    assert reasons["missing-admission-metadata:3:1"] > 0
    assert reasons["missing-pair-link-cost:1:1->2:1"] == 1
    assert reasons["invalid-pair-link-cost:1:1->3:2"] == 1
    assert decision.result.action == action((2, 1), (3, 2))


def test_phase2_prunes_per_stage_by_belief_load_utility_and_lowest_id_ties():
    configuration = HybridConfiguration(num_flows=1, num_replicas=6)
    beliefs = uniform_beliefs(
        configuration,
        belief=(0.0, 0.0, 1.0, 0.0),
    )
    for replica in range(1, configuration.num_replicas + 1):
        beliefs[ReplicaChoice(1, replica)] = (0.0, 0.0, 0.0, 1.0)
    beliefs[ReplicaChoice(2, 6)] = (0.0, 0.0, 0.0, 1.0)

    decision = IBGHybridPolicy(configuration).select_greedy(
        state=GlobalLoadState.empty(configuration),
        admission=full_admission(configuration),
        beliefs=beliefs,
        known_pair_link_costs=full_link_costs(configuration),
    )

    retained = decision.accounting.retained_by_stage
    assert tuple(choice.replica for choice in retained[0]) == (1, 2, 3, 4, 5)
    assert tuple(choice.replica for choice in retained[1]) == (6, 1, 2, 3, 4)
    assert tuple(choice.replica for choice in retained[2]) == (1, 2, 3, 4, 5)
    assert decision.result.action == action((1, 1), (2, 6))


def test_phase2_default_target_enumerates_no_more_than_75_pruned_actions():
    configuration = HybridConfiguration()

    decision = IBGHybridPolicy(configuration).select_greedy(
        state=GlobalLoadState.empty(configuration),
        admission=full_admission(configuration),
        beliefs=uniform_beliefs(configuration),
        known_pair_link_costs=full_link_costs(configuration),
    )

    assert decision.accounting.available_actions == 300
    assert decision.accounting.feasible_actions_before_pruning == 300
    assert decision.accounting.retained_counts_by_stage == (5, 5, 5)
    assert decision.accounting.pruned_actions == 75
    assert decision.accounting.feasible_pruned_actions == 75
    assert len(decision.scored_actions) == 75


def test_phase2_joint_greedy_choice_is_link_aware():
    configuration = HybridConfiguration(num_flows=1, num_replicas=2)
    link_costs = full_link_costs(configuration, cost=10.0)
    preferred_pair = (ReplicaChoice(2, 2), ReplicaChoice(3, 2))
    link_costs[preferred_pair] = 0.0

    decision = IBGHybridPolicy(configuration).select_greedy(
        state=GlobalLoadState.empty(configuration),
        admission=full_admission(configuration),
        beliefs=uniform_beliefs(configuration),
        known_pair_link_costs=link_costs,
    )

    assert decision.result.action == TwoStageAction(preferred_pair)
    selected = next(
        scored
        for scored in decision.scored_actions
        if scored.action == decision.result.action
    )
    assert selected.planning_pair_link_cost_ms == pytest.approx(0.0)
    assert selected.objective_value == pytest.approx(sum(selected.stage_utilities))


def test_phase2_exact_joint_ties_choose_the_first_canonical_action():
    configuration = HybridConfiguration(num_flows=1, num_replicas=1)

    decision = IBGHybridPolicy(configuration).select_greedy(
        state=GlobalLoadState.empty(configuration),
        admission=full_admission(configuration),
        beliefs=uniform_beliefs(configuration),
        known_pair_link_costs=full_link_costs(configuration),
    )

    assert decision.result.action == action((1, 1), (2, 1))
    assert tuple(scored.action for scored in decision.scored_actions) == (
        action((1, 1), (2, 1)),
        action((1, 1), (3, 1)),
        action((2, 1), (3, 1)),
    )


def test_phase2_uses_beliefs_without_accessing_a_replica_true_state():
    class GuardedBelief(tuple):
        @property
        def state(self):
            raise AssertionError("the planner accessed hidden true state")

    configuration = HybridConfiguration(num_flows=1, num_replicas=1)
    guarded = GuardedBelief((0.1, 0.2, 0.3, 0.4))

    decision = IBGHybridPolicy(configuration).select_greedy(
        state=GlobalLoadState.empty(configuration),
        admission=full_admission(configuration),
        beliefs={choice: guarded for choice in choices(configuration)},
        known_pair_link_costs=full_link_costs(configuration),
    )

    assert decision.result.feasibility.feasible
    assert expected_stage_utility_from_belief(guarded, 1) == pytest.approx(
        sum(
            probability * expected_state_utility(state, 1)
            for state, probability in enumerate(guarded, start=1)
        )
    )


def test_phase2_utility_memoization_is_keyed_by_belief_value():
    configuration = HybridConfiguration(num_flows=1, num_replicas=2)
    policy = IBGHybridPolicy(configuration)
    state = GlobalLoadState.empty(configuration)
    admission = full_admission(configuration)
    links = full_link_costs(configuration)
    first_beliefs = uniform_beliefs(
        configuration,
        belief=(1.0, 0.0, 0.0, 0.0),
    )
    second_beliefs = dict(first_beliefs)
    for stage in range(1, configuration.num_stages + 1):
        first_beliefs[ReplicaChoice(stage, 1)] = (0.0, 0.0, 0.0, 1.0)
        second_beliefs[ReplicaChoice(stage, 2)] = (0.0, 0.0, 0.0, 1.0)

    first = policy.select_greedy(
        state=state,
        admission=admission,
        beliefs=first_beliefs,
        known_pair_link_costs=links,
    )
    second = policy.select_greedy(
        state=state,
        admission=admission,
        beliefs=second_beliefs,
        known_pair_link_costs=links,
    )

    assert first.result.action == action((1, 1), (2, 1))
    assert second.result.action == action((1, 2), (2, 2))


def test_phase2_greedy_matches_the_tiny_oracle_for_one_tractable_flow():
    configuration = HybridConfiguration(num_flows=1, num_replicas=2)
    state = GlobalLoadState.empty(configuration)
    admission = full_admission(configuration)
    beliefs = uniform_beliefs(
        configuration,
        belief=(0.0, 0.0, 1.0, 0.0),
    )
    beliefs[ReplicaChoice(1, 2)] = (0.0, 0.0, 0.0, 1.0)
    beliefs[ReplicaChoice(3, 1)] = (0.0, 0.0, 0.0, 1.0)
    link_costs = full_link_costs(configuration, cost=4.0)
    link_costs[(ReplicaChoice(1, 2), ReplicaChoice(3, 1))] = 1.0

    decision = IBGHybridPolicy(configuration).select_greedy(
        state=state,
        admission=admission,
        beliefs=beliefs,
        known_pair_link_costs=link_costs,
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
