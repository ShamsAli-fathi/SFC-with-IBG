import pytest

from IBG_Hybrid import (
    GlobalLoadState,
    HybridConfiguration,
    ReplicaChoice,
    TwoStageAction,
)
from IBG_Hybrid.phase0_contract import (
    DEFAULT_HYBRID_POLICY_PARAMETERS,
    D_LOOKAHEAD,
    D_MC,
    HYBRID_BUDGET_MODE,
    HYBRID_COMPLETE_ACTION_MODE,
    HYBRID_FLOW_ORDER_SEED_SCHEME,
    HYBRID_LINK_WEIGHT_UTILITY_PER_MS,
    HYBRID_LOOKAHEAD_VALUE_MODE,
    HYBRID_MC_ROOT_SHORTLIST_SIZE,
    HYBRID_NODE_RESOURCE_MODE,
    HYBRID_PAIR_LINK_MODE,
    HYBRID_PLANNING_LINK_UNIT,
    HYBRID_POLICY_CONTRACT_VERSION,
    HYBRID_PRUNING_SCORE_MODE,
    HYBRID_REPLICA_CAPACITY_UNIT,
    HYBRID_ROLLOUT_KERNEL,
    HYBRID_ROLLOUT_SEED_SCHEME,
    HybridActivationContext,
    HybridPolicyParameters,
    PipelinePath,
    ReplicaAdmission,
    RolloutSeedKey,
    derive_flow_order_seed,
    derive_rollout_seed,
    evaluate_phase0_feasibility,
    focal_utility_at_projected_loads,
    lookahead_flows_to_simulate,
    monte_carlo_continuation_lengths,
    maximum_contention_ratio,
    maximum_normalized_belief_entropy,
    project_focal_and_continuation,
    prune_stage_candidates,
    pruned_action_count,
    select_pipeline_path,
)


def action(*pairs):
    return TwoStageAction(
        tuple(ReplicaChoice(stage, replica) for stage, replica in pairs)
    )


def test_phase0_defaults_and_units_are_frozen():
    parameters = DEFAULT_HYBRID_POLICY_PARAMETERS

    assert HYBRID_POLICY_CONTRACT_VERSION == "ibg-hybrid-policy-contract-v5"
    assert HYBRID_BUDGET_MODE == "exact-stage-cardinality-v1"
    assert HYBRID_REPLICA_CAPACITY_UNIT == "assigned-flows-per-slot"
    assert HYBRID_NODE_RESOURCE_MODE == "deferred-versioned-per-flow-demands"
    assert HYBRID_PLANNING_LINK_UNIT == "milliseconds"
    assert HYBRID_LINK_WEIGHT_UTILITY_PER_MS == pytest.approx(1.0)
    assert HYBRID_FLOW_ORDER_SEED_SCHEME == "blake2b-hybrid-flow-order-v1"
    assert HYBRID_ROLLOUT_SEED_SCHEME == "blake2b-hybrid-rollout-v1"
    assert HYBRID_PRUNING_SCORE_MODE == "belief-load-aware-stage-utility-v1"
    assert HYBRID_COMPLETE_ACTION_MODE == "enumerate-all-pruned-l2-actions-v1"
    assert HYBRID_LOOKAHEAD_VALUE_MODE == "focal-final-load-once-v1"
    assert (
        HYBRID_ROLLOUT_KERNEL
        == "epsilon-greedy-window-pure-greedy-tail-v2"
    )
    assert HYBRID_PAIR_LINK_MODE == "known-directed-selected-pair-v1"
    assert parameters.candidates_per_stage == 5
    assert D_LOOKAHEAD == parameters.lookahead_future_flows == 2
    assert D_MC == parameters.monte_carlo_noisy_future_flows == 10
    assert HYBRID_MC_ROOT_SHORTLIST_SIZE == 5
    assert parameters.monte_carlo_samples == 50
    assert parameters.rollout_epsilon == pytest.approx(0.10)
    assert parameters.lookahead_contention_threshold == pytest.approx(0.70)
    assert parameters.monte_carlo_entropy_threshold == pytest.approx(0.75)


def test_c_counts_replicas_per_stage_and_produces_75_l2_actions():
    configuration = HybridConfiguration()
    scores = {
        ReplicaChoice(1, replica): 100.0 - replica
        for replica in range(1, configuration.num_replicas + 1)
    }

    retained = prune_stage_candidates(stage=1, scores=scores)

    assert tuple(choice.replica for choice in retained) == (1, 2, 3, 4, 5)
    assert pruned_action_count(configuration) == 3 * 5**2 == 75


def test_pruning_ties_use_lowest_replica_id():
    retained = prune_stage_candidates(
        stage=2,
        scores={
            ReplicaChoice(2, 3): 10.0,
            ReplicaChoice(2, 1): 10.0,
            ReplicaChoice(2, 2): 10.0,
        },
    )

    assert tuple(choice.replica for choice in retained) == (1, 2, 3)


def test_d_counts_future_flows_after_the_focal_action():
    assert lookahead_flows_to_simulate(0) == 0
    assert lookahead_flows_to_simulate(1) == 1
    assert lookahead_flows_to_simulate(2) == 2
    assert lookahead_flows_to_simulate(8) == 2
    assert monte_carlo_continuation_lengths(8) == (8, 0)
    assert monte_carlo_continuation_lengths(15) == (10, 5)


def test_mc_depth_validation_is_independent_from_lookahead_depth():
    with pytest.raises(ValueError, match="monte_carlo_noisy_future_flows"):
        HybridPolicyParameters(monte_carlo_noisy_future_flows=-1)

    parameters = HybridPolicyParameters(
        lookahead_future_flows=1,
        monte_carlo_noisy_future_flows=7,
    )
    assert lookahead_flows_to_simulate(20, parameters) == 1
    assert monte_carlo_continuation_lengths(20, parameters) == (7, 13)


def test_core_pipeline_always_selects_pruned_lookahead():
    contexts = (
        HybridActivationContext(
            contention_ratio=0.90,
            maximum_normalized_belief_entropy=0.75,
            high_priority=True,
        ),
        HybridActivationContext(
            contention_ratio=0.70,
            maximum_normalized_belief_entropy=0.74,
        ),
        HybridActivationContext(
            contention_ratio=0.20,
            maximum_normalized_belief_entropy=0.10,
            high_priority=True,
        ),
        HybridActivationContext(
            contention_ratio=0.00,
            maximum_normalized_belief_entropy=1.00,
        ),
        HybridActivationContext(
            contention_ratio=0.69,
            maximum_normalized_belief_entropy=0.10,
        ),
    )

    assert all(
        select_pipeline_path(context) is PipelinePath.LOOKAHEAD
        for context in contexts
    )


def test_activation_inputs_have_fixed_units_and_aggregation():
    configuration = HybridConfiguration(num_flows=2, num_replicas=1)
    state = GlobalLoadState.empty(configuration).apply(
        action((1, 1), (2, 1)),
        configuration,
    )
    admission = {
        ReplicaChoice(1, 1): ReplicaAdmission(
            ReplicaChoice(1, 1),
            ready=True,
            max_assigned_flows=2,
        ),
        ReplicaChoice(2, 1): ReplicaAdmission(
            ReplicaChoice(2, 1),
            ready=True,
            max_assigned_flows=4,
        ),
        ReplicaChoice(3, 1): ReplicaAdmission(
            ReplicaChoice(3, 1),
            ready=False,
            max_assigned_flows=1,
        ),
    }

    assert maximum_contention_ratio(
        state,
        configuration,
        admission,
    ) == pytest.approx(0.5)
    assert maximum_normalized_belief_entropy(
        {
            ReplicaChoice(1, 1): (1.0, 0.0, 0.0, 0.0),
            ReplicaChoice(2, 1): (0.25, 0.25, 0.25, 0.25),
        }
    ) == pytest.approx(1.0)


def test_feasibility_uses_ready_and_declared_flow_capacity_only():
    configuration = HybridConfiguration(num_flows=3, num_replicas=1)
    previous = action((1, 1), (2, 1))
    state = GlobalLoadState.empty(configuration).apply(previous, configuration)
    candidate = action((1, 1), (3, 1))
    admission = {
        ReplicaChoice(1, 1): ReplicaAdmission(
            ReplicaChoice(1, 1),
            ready=True,
            max_assigned_flows=1,
        ),
        ReplicaChoice(3, 1): ReplicaAdmission(
            ReplicaChoice(3, 1),
            ready=False,
            max_assigned_flows=3,
        ),
    }

    result = evaluate_phase0_feasibility(
        candidate,
        state,
        configuration,
        admission,
        {
            (ReplicaChoice(1, 1), ReplicaChoice(3, 1)): 7.0,
        },
    )

    assert not result.feasible
    assert result.reasons == (
        "replica-flow-capacity:1:1",
        "not-ready:3:1",
    )

    accepted = evaluate_phase0_feasibility(
        candidate,
        state,
        configuration,
        {
            ReplicaChoice(1, 1): ReplicaAdmission(
                ReplicaChoice(1, 1),
                ready=True,
                max_assigned_flows=2,
            ),
            ReplicaChoice(3, 1): ReplicaAdmission(
                ReplicaChoice(3, 1),
                ready=True,
                max_assigned_flows=3,
            ),
        },
        {
            (ReplicaChoice(1, 1), ReplicaChoice(3, 1)): 7.0,
        },
    )
    assert accepted.feasible

    missing_link = evaluate_phase0_feasibility(
        candidate,
        state,
        configuration,
        {
            ReplicaChoice(1, 1): ReplicaAdmission(
                ReplicaChoice(1, 1),
                ready=True,
                max_assigned_flows=2,
            ),
            ReplicaChoice(3, 1): ReplicaAdmission(
                ReplicaChoice(3, 1),
                ready=True,
                max_assigned_flows=3,
            ),
        },
        {},
    )
    assert missing_link.reasons == ("missing-pair-link-cost:1:1->3:1",)


def test_focal_value_is_evaluated_once_at_projected_future_loads():
    configuration = HybridConfiguration(num_flows=2, num_replicas=1)
    initial = GlobalLoadState.empty(configuration)
    focal = action((1, 1), (3, 1))
    future = action((1, 1), (2, 1))
    calls = []

    projected = project_focal_and_continuation(
        focal,
        (future,),
        initial,
        configuration,
    )
    value = focal_utility_at_projected_loads(
        focal,
        projected,
        configuration,
        stage_expected_utility=lambda choice, load: calls.append(
            (choice, load)
        )
        or 100.0
        - 10.0 * load,
        known_pair_link_cost=lambda first, second: (
            calls.append((first, second)) or 7.0
        ),
    )

    assert projected.loads == ((2,), (1,), (1,))
    assert value == pytest.approx((80.0 + 90.0) - 7.0)
    assert calls == [
        (ReplicaChoice(1, 1), 2),
        (ReplicaChoice(3, 1), 1),
        (ReplicaChoice(1, 1), ReplicaChoice(3, 1)),
    ]


def test_rollout_seed_is_stable_and_candidate_sample_specific():
    base = RolloutSeedKey(
        root_seed=2050,
        slot_id=4,
        decision_position=3,
        flow_id=17,
        action=action((1, 2), (3, 4)),
        sample_index=0,
    )
    same = RolloutSeedKey(
        root_seed=2050,
        slot_id=4,
        decision_position=3,
        flow_id=17,
        action=action((1, 2), (3, 4)),
        sample_index=0,
    )
    next_sample = RolloutSeedKey(
        root_seed=2050,
        slot_id=4,
        decision_position=3,
        flow_id=17,
        action=action((1, 2), (3, 4)),
        sample_index=1,
    )
    other_candidate = RolloutSeedKey(
        root_seed=2050,
        slot_id=4,
        decision_position=3,
        flow_id=17,
        action=action((1, 2), (3, 5)),
        sample_index=0,
    )

    assert derive_rollout_seed(base) == derive_rollout_seed(same)
    assert derive_rollout_seed(base) != derive_rollout_seed(next_sample)
    assert derive_rollout_seed(base) != derive_rollout_seed(other_candidate)
    assert derive_flow_order_seed(2050, 4) == derive_flow_order_seed(2050, 4)
    assert derive_flow_order_seed(2050, 4) != derive_flow_order_seed(2050, 5)
