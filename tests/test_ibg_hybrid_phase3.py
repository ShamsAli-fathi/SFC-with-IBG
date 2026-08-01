from itertools import combinations, product

import pytest

import IBG_Hybrid.policy as policy_module
from IBG_Hybrid import (
    GlobalLoadState,
    HybridConfiguration,
    HybridPolicyParameters,
    IBGHybridPolicy,
    NoFeasibleLookaheadAction,
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


@pytest.mark.parametrize(
    ("requested_depth", "expected_depth"),
    ((0, 0), (1, 1), (2, 2)),
)
def test_phase3_supports_d0_d1_and_d2(requested_depth, expected_depth):
    configuration = HybridConfiguration(num_flows=3, num_replicas=1)
    policy = IBGHybridPolicy(
        configuration,
        HybridPolicyParameters(lookahead_future_flows=requested_depth),
    )

    decision = policy.select_lookahead(
        state=GlobalLoadState.empty(configuration),
        admission=full_admission(configuration),
        beliefs=uniform_beliefs(configuration),
        known_pair_link_costs=full_link_costs(configuration),
    )

    assert {
        (evaluation.requested_depth, evaluation.effective_depth)
        for evaluation in decision.evaluations
    } == {(requested_depth, expected_depth)}
    assert all(
        len(evaluation.continuation_actions) == expected_depth
        for evaluation in decision.evaluations
    )


def test_phase3_clamps_depth_to_later_flows_near_slot_end():
    configuration = HybridConfiguration(num_flows=4, num_replicas=1)
    initial = GlobalLoadState.empty(configuration)
    previous = action((1, 1), (2, 1))
    near_end = initial.apply(previous, configuration).apply(
        previous,
        configuration,
    )

    decision = IBGHybridPolicy(configuration).select_lookahead(
        state=near_end,
        admission=full_admission(configuration),
        beliefs=uniform_beliefs(configuration),
        known_pair_link_costs=full_link_costs(configuration),
    )

    assert near_end.total_assignments == 4
    assert all(
        evaluation.requested_depth == 2
        and evaluation.effective_depth == 1
        and len(evaluation.continuation_steps) == 1
        for evaluation in decision.evaluations
    )


def test_phase3_uses_focal_value_only_without_immediate_or_future_welfare(
    monkeypatch,
):
    configuration = HybridConfiguration(num_flows=2, num_replicas=2)
    focal = action((1, 1), (2, 1))
    future = action((2, 2), (3, 1))
    values = {
        (1, 1): (10.0, 0.0),
        (1, 2): (0.0, 0.0),
        (2, 1): (10.0, 0.0),
        (2, 2): (10.0, 0.0),
        (3, 1): (9.0, 0.0),
        (3, 2): (0.0, 0.0),
    }
    beliefs = {
        choice: (choice.stage, choice.replica)
        for choice in choices(configuration)
    }
    link_costs = full_link_costs(configuration, cost=1_000.0)
    link_costs[(focal.choices[0], focal.choices[1])] = 0.0
    link_costs[(future.choices[0], future.choices[1])] = 0.0

    def fixture_utility(belief, load):
        return values[tuple(belief)][load - 1]

    monkeypatch.setattr(
        policy_module,
        "expected_stage_utility_from_belief",
        fixture_utility,
    )
    decision = IBGHybridPolicy(configuration).select_lookahead(
        state=GlobalLoadState.empty(configuration),
        admission=full_admission(configuration),
        beliefs=beliefs,
        known_pair_link_costs=link_costs,
    )
    selected = decision.selected_evaluation

    assert decision.result.action == focal
    assert selected.continuation_actions == (future,)
    assert selected.focal_value == pytest.approx(20.0)
    assert decision.result.objective_value == pytest.approx(20.0)
    assert decision.result.objective_value != pytest.approx(20.0 + 20.0)
    assert decision.result.objective_value != pytest.approx(20.0 + 19.0)


def test_phase3_commits_focal_once_and_values_final_projected_load(
    monkeypatch,
):
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

    monkeypatch.setattr(
        policy_module,
        "expected_stage_utility_from_belief",
        lambda belief, load: values[tuple(belief)][load - 1],
    )
    initial = GlobalLoadState.empty(configuration)
    decision = IBGHybridPolicy(configuration).select_lookahead(
        state=initial,
        admission=full_admission(configuration),
        beliefs=beliefs,
        known_pair_link_costs=link_costs,
    )
    selected = decision.selected_evaluation

    assert decision.result.action == focal
    assert selected.continuation_actions == (focal,)
    assert selected.state_after_focal.loads == ((1,), (1,), (0,))
    assert selected.projected_final_state.loads == ((2,), (2,), (0,))
    assert decision.result.state_after == selected.state_after_focal
    assert selected.focal_value == pytest.approx(30.0 + 20.0 - 7.0)
    assert selected.focal_value != pytest.approx(
        (100.0 + 80.0 - 7.0) + (30.0 + 20.0 - 7.0)
    )


def test_phase3_branches_are_independent_and_inputs_remain_unchanged():
    configuration = HybridConfiguration(num_flows=2, num_replicas=1)
    state = GlobalLoadState.empty(configuration)
    admission = full_admission(configuration)
    beliefs = uniform_beliefs(configuration)
    link_costs = full_link_costs(configuration)
    admission_before = dict(admission)
    beliefs_before = dict(beliefs)
    link_costs_before = dict(link_costs)
    policy = IBGHybridPolicy(configuration)

    first = policy.select_lookahead(
        state=state,
        admission=admission,
        beliefs=beliefs,
        known_pair_link_costs=link_costs,
    )
    second = policy.select_lookahead(
        state=state,
        admission=admission,
        beliefs=beliefs,
        known_pair_link_costs=link_costs,
    )

    assert first == second
    assert state == GlobalLoadState.empty(configuration)
    assert admission == admission_before
    assert beliefs == beliefs_before
    assert link_costs == link_costs_before
    for evaluation in first.evaluations:
        assert evaluation.state_after_focal == state.apply(
            evaluation.focal_action,
            configuration,
        )
        assert evaluation.state_after_focal.total_assignments == 2
        assert evaluation.projected_final_state.total_assignments == 4


def test_phase3_continuations_reuse_phase2_at_each_updated_state(monkeypatch):
    configuration = HybridConfiguration(num_flows=2, num_replicas=1)
    state = GlobalLoadState.empty(configuration)
    admission = full_admission(configuration)
    beliefs = uniform_beliefs(configuration)
    link_costs = full_link_costs(configuration)
    policy = IBGHybridPolicy(configuration)
    original_select_greedy = IBGHybridPolicy.select_greedy
    observed_states = []

    def recording_select_greedy(self, **kwargs):
        observed_states.append(kwargs["state"])
        return original_select_greedy(self, **kwargs)

    monkeypatch.setattr(
        IBGHybridPolicy,
        "select_greedy",
        recording_select_greedy,
    )
    decision = policy.select_lookahead(
        state=state,
        admission=admission,
        beliefs=beliefs,
        known_pair_link_costs=link_costs,
    )

    assert observed_states[0] == state
    assert tuple(observed_states[1:]) == tuple(
        evaluation.state_after_focal
        for evaluation in decision.evaluations
    )
    for evaluation in decision.evaluations:
        step = evaluation.continuation_steps[0]
        direct = original_select_greedy(
            policy,
            state=step.state_before,
            admission=admission,
            beliefs=beliefs,
            known_pair_link_costs=link_costs,
        )
        assert step.decision == direct
        assert step.accounting == direct.accounting


def test_phase3_canonical_ties_cover_focal_and_continuations(monkeypatch):
    configuration = HybridConfiguration(num_flows=3, num_replicas=1)
    canonical = action((1, 1), (2, 1))
    beliefs = {
        choice: (1.0,)
        for choice in choices(configuration)
    }
    monkeypatch.setattr(
        policy_module,
        "expected_stage_utility_from_belief",
        lambda _belief, _load: 1.0,
    )

    decision = IBGHybridPolicy(configuration).select_lookahead(
        state=GlobalLoadState.empty(configuration),
        admission=full_admission(configuration),
        beliefs=beliefs,
        known_pair_link_costs=full_link_costs(configuration),
    )

    assert decision.result.action == canonical
    assert all(
        evaluation.continuation_actions == (canonical, canonical)
        for evaluation in decision.evaluations
    )


def test_phase3_lookahead_deliberately_avoids_myopic_congestion():
    configuration = HybridConfiguration(num_flows=3, num_replicas=2)
    state = GlobalLoadState.empty(configuration)
    beliefs = uniform_beliefs(
        configuration,
        belief=(1.0, 0.0, 0.0, 0.0),
    )
    beliefs[ReplicaChoice(1, 1)] = (0.0, 0.0, 0.0, 1.0)
    beliefs[ReplicaChoice(3, 1)] = (0.0, 0.0, 1.0, 0.0)
    beliefs[ReplicaChoice(3, 2)] = (0.0, 0.0, 1.0, 0.0)
    myopic = action((1, 1), (3, 2))
    congestion_avoiding = action((1, 1), (3, 1))
    link_costs = full_link_costs(configuration, cost=1_000.0)
    link_costs[(ReplicaChoice(1, 1), ReplicaChoice(3, 1))] = 3.0
    link_costs[(ReplicaChoice(1, 1), ReplicaChoice(3, 2))] = 2.0
    policy = IBGHybridPolicy(configuration)

    greedy = policy.select_greedy(
        state=state,
        admission=full_admission(configuration),
        beliefs=beliefs,
        known_pair_link_costs=link_costs,
    )
    lookahead = policy.select_lookahead(
        state=state,
        admission=full_admission(configuration),
        beliefs=beliefs,
        known_pair_link_costs=link_costs,
    )

    assert greedy.result.action == myopic
    assert lookahead.result.action == congestion_avoiding
    assert lookahead.selected_evaluation.continuation_actions == (
        myopic,
        myopic,
    )
    myopic_evaluation = next(
        evaluation
        for evaluation in lookahead.evaluations
        if evaluation.focal_action == myopic
    )
    assert lookahead.result.objective_value > myopic_evaluation.focal_value


def test_phase3_d0_matches_tiny_oracle_when_objectives_are_equivalent():
    configuration = HybridConfiguration(num_flows=1, num_replicas=2)
    parameters = HybridPolicyParameters(lookahead_future_flows=0)
    state = GlobalLoadState.empty(configuration)
    admission = full_admission(configuration)
    beliefs = uniform_beliefs(
        configuration,
        belief=(0.0, 0.0, 1.0, 0.0),
    )
    beliefs[ReplicaChoice(1, 2)] = (0.0, 0.0, 0.0, 1.0)
    link_costs = full_link_costs(configuration, cost=4.0)
    link_costs[(ReplicaChoice(1, 2), ReplicaChoice(3, 1))] = 1.0

    decision = IBGHybridPolicy(
        configuration,
        parameters,
    ).select_lookahead(
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


def test_phase3_dead_end_focal_branches_are_not_selected():
    configuration = HybridConfiguration(num_flows=2, num_replicas=1)
    admission = full_admission(configuration, capacity=1)

    with pytest.raises(NoFeasibleLookaheadAction) as raised:
        IBGHybridPolicy(configuration).select_lookahead(
            state=GlobalLoadState.empty(configuration),
            admission=admission,
            beliefs=uniform_beliefs(configuration),
            known_pair_link_costs=full_link_costs(configuration),
        )

    assert len(raised.value.rejected_branches) == 3
    assert all(
        failure.completed_steps == ()
        and failure.failing_state == failure.state_after_focal
        for failure in raised.value.rejected_branches
    )


def test_phase3_20x3x10_boundary_completes_deterministically():
    configuration = HybridConfiguration()
    state = GlobalLoadState.empty(configuration)
    admission = full_admission(configuration, capacity=20)
    beliefs = uniform_beliefs(configuration)
    link_costs = full_link_costs(configuration)
    policy = IBGHybridPolicy(configuration)

    first = policy.select_lookahead(
        state=state,
        admission=admission,
        beliefs=beliefs,
        known_pair_link_costs=link_costs,
    )
    second = policy.select_lookahead(
        state=state,
        admission=admission,
        beliefs=beliefs,
        known_pair_link_costs=link_costs,
    )

    assert first == second
    assert first.focal_accounting.available_actions == 300
    assert first.focal_accounting.feasible_pruned_actions == 75
    assert len(first.evaluations) == 75
    assert all(
        len(evaluation.continuation_steps) == 2
        for evaluation in first.evaluations
    )
