from concurrent.futures import Executor, ProcessPoolExecutor
from itertools import combinations, product
import multiprocessing
import os

import pytest

import IBG_Hybrid.policy as policy_module
from IBG_Hybrid import (
    GlobalLoadState,
    HybridConfiguration,
    HybridLookaheadBranchTask,
    HybridLookaheadBranchWorkerError,
    HybridPolicyParameters,
    IBGHybridPolicy,
    NoFeasibleLookaheadAction,
    ReplicaChoice,
    TwoStageAction,
    evaluate_hybrid_lookahead_branch,
)
from IBG_Hybrid.phase0_contract import ReplicaAdmission


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


def full_admission(configuration, *, capacity=None):
    if capacity is None:
        capacity = configuration.num_flows
    return {
        choice: ReplicaAdmission(
            choice=choice,
            ready=True,
            max_assigned_flows=capacity,
        )
        for choice in choices(configuration)
    }


def varied_beliefs(configuration):
    states = (
        (0.55, 0.20, 0.15, 0.10),
        (0.10, 0.45, 0.25, 0.20),
        (0.05, 0.15, 0.30, 0.50),
    )
    return {
        choice: states[(choice.stage + choice.replica) % len(states)]
        for choice in choices(configuration)
    }


def uniform_beliefs(configuration):
    return {
        choice: (0.25, 0.25, 0.25, 0.25)
        for choice in choices(configuration)
    }


def full_link_costs(configuration, *, constant=None):
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
            costs[(source, target)] = (
                float(constant)
                if constant is not None
                else float(stage_a + stage_b + replica_a + replica_b) / 10.0
            )
    return costs


def parallel_decision(
    policy,
    executor,
    *,
    state,
    admission,
    beliefs,
    links,
):
    return policy._select_lookahead_with_executor_for_validation(
        state=state,
        admission=admission,
        beliefs=beliefs,
        known_pair_link_costs=links,
        branch_executor=executor,
    )


@pytest.mark.parametrize(
    ("num_flows", "num_replicas", "lookahead_depth", "precommitted"),
    (
        (1, 1, 2, False),
        (3, 2, 2, False),
        (4, 3, 2, True),
    ),
)
def test_two_process_boundary_matches_full_serial_decision_across_topologies(
    num_flows,
    num_replicas,
    lookahead_depth,
    precommitted,
):
    configuration = HybridConfiguration(
        num_flows=num_flows,
        num_replicas=num_replicas,
    )
    policy = IBGHybridPolicy(
        configuration,
        HybridPolicyParameters(lookahead_future_flows=lookahead_depth),
    )
    state = GlobalLoadState.empty(configuration)
    if precommitted:
        state = state.apply(action((1, 1), (3, 1)), configuration)
    admission = full_admission(configuration)
    beliefs = varied_beliefs(configuration)
    links = full_link_costs(configuration)
    state_before = state.loads
    admission_before = dict(admission)
    beliefs_before = dict(beliefs)
    links_before = dict(links)

    serial = policy.select_lookahead(
        state=state,
        admission=admission,
        beliefs=beliefs,
        known_pair_link_costs=links,
    )
    baseline_children = {child.pid for child in multiprocessing.active_children()}
    with ProcessPoolExecutor(max_workers=2) as executor:
        first = parallel_decision(
            policy,
            executor,
            state=state,
            admission=admission,
            beliefs=beliefs,
            links=links,
        )
        second = parallel_decision(
            policy,
            executor,
            state=state,
            admission=admission,
            beliefs=beliefs,
            links=links,
        )

    assert first == serial
    assert second == serial
    assert tuple(
        evaluation.focal_action for evaluation in first.evaluations
    ) == tuple(
        evaluation.focal_action for evaluation in serial.evaluations
    )
    assert tuple(
        failure.focal_action for failure in first.rejected_branches
    ) == tuple(
        failure.focal_action for failure in serial.rejected_branches
    )
    assert state.loads == state_before
    assert admission == admission_before
    assert beliefs == beliefs_before
    assert links == links_before
    assert {
        child.pid for child in multiprocessing.active_children()
    } <= baseline_children


class ReverseMapExecutor(Executor):
    """Return complete outcomes in reverse order to exercise restoration."""

    def map(self, function, *iterables, timeout=None, chunksize=1):
        del timeout, chunksize
        outcomes = tuple(function(*values) for values in zip(*iterables))
        return iter(reversed(outcomes))


def test_out_of_order_branch_completion_is_restored_to_canonical_order():
    configuration = HybridConfiguration(num_flows=3, num_replicas=2)
    policy = IBGHybridPolicy(configuration)
    state = GlobalLoadState.empty(configuration)
    admission = full_admission(configuration)
    beliefs = varied_beliefs(configuration)
    links = full_link_costs(configuration)

    serial = policy.select_lookahead(
        state=state,
        admission=admission,
        beliefs=beliefs,
        known_pair_link_costs=links,
    )
    restored = parallel_decision(
        policy,
        ReverseMapExecutor(),
        state=state,
        admission=admission,
        beliefs=beliefs,
        links=links,
    )

    assert restored == serial


def test_two_process_dead_end_failures_retain_complete_canonical_accounting():
    configuration = HybridConfiguration(num_flows=2, num_replicas=1)
    policy = IBGHybridPolicy(configuration)
    arguments = {
        "state": GlobalLoadState.empty(configuration),
        "admission": full_admission(configuration, capacity=1),
        "beliefs": varied_beliefs(configuration),
        "known_pair_link_costs": full_link_costs(configuration),
    }

    with pytest.raises(NoFeasibleLookaheadAction) as serial_raised:
        policy.select_lookahead(**arguments)
    with ProcessPoolExecutor(max_workers=2) as executor:
        with pytest.raises(NoFeasibleLookaheadAction) as parallel_raised:
            policy._select_lookahead_with_executor_for_validation(
                **arguments,
                branch_executor=executor,
            )

    assert (
        parallel_raised.value.focal_accounting
        == serial_raised.value.focal_accounting
    )
    assert (
        parallel_raised.value.rejected_branches
        == serial_raised.value.rejected_branches
    )


def test_exact_score_ties_keep_first_canonical_candidate_in_two_process_mode():
    configuration = HybridConfiguration(num_flows=1, num_replicas=2)
    policy = IBGHybridPolicy(
        configuration,
        HybridPolicyParameters(lookahead_future_flows=0),
    )
    state = GlobalLoadState.empty(configuration)
    admission = full_admission(configuration)
    beliefs = uniform_beliefs(configuration)
    links = full_link_costs(configuration, constant=0.0)

    serial = policy.select_lookahead(
        state=state,
        admission=admission,
        beliefs=beliefs,
        known_pair_link_costs=links,
    )
    with ProcessPoolExecutor(max_workers=2) as executor:
        parallel = parallel_decision(
            policy,
            executor,
            state=state,
            admission=admission,
            beliefs=beliefs,
            links=links,
        )

    assert parallel == serial
    assert parallel.result.action == action((1, 1), (2, 1))
    assert parallel.result.action == parallel.evaluations[0].focal_action


def test_unexpected_worker_error_reports_canonical_candidate_and_action():
    configuration = HybridConfiguration(num_flows=2, num_replicas=1)
    policy = IBGHybridPolicy(configuration)
    state = GlobalLoadState.empty(configuration)
    admission = full_admission(configuration)
    links = full_link_costs(configuration)
    focal = policy.select_greedy(
        state=state,
        admission=admission,
        beliefs=uniform_beliefs(configuration),
        known_pair_link_costs=links,
    ).scored_actions[0]
    task = HybridLookaheadBranchTask(
        configuration=configuration,
        parameters=policy.parameters,
        current_state=state,
        focal_candidate=focal,
        admission=tuple(sorted(admission.items())),
        beliefs=(),
        planning_pair_links=tuple(sorted(links.items())),
        requested_depth=2,
        effective_depth=1,
        canonical_index=7,
    )

    with ProcessPoolExecutor(max_workers=2) as executor:
        with pytest.raises(HybridLookaheadBranchWorkerError) as raised:
            executor.submit(evaluate_hybrid_lookahead_branch, task).result()

    assert raised.value.canonical_index == 7
    assert raised.value.focal_action == focal.action
    assert "missing belief" in raised.value.detail


def test_production_lookahead_calls_worker_boundary_serially(monkeypatch):
    configuration = HybridConfiguration(num_flows=2, num_replicas=2)
    policy = IBGHybridPolicy(configuration)
    observed_processes = []
    original = policy_module.evaluate_hybrid_lookahead_branch

    def recording_evaluator(task):
        observed_processes.append(os.getpid())
        return original(task)

    monkeypatch.setattr(
        policy_module,
        "evaluate_hybrid_lookahead_branch",
        recording_evaluator,
    )
    decision = policy.select_lookahead(
        state=GlobalLoadState.empty(configuration),
        admission=full_admission(configuration),
        beliefs=varied_beliefs(configuration),
        known_pair_link_costs=full_link_costs(configuration),
    )

    assert len(observed_processes) == (
        decision.focal_accounting.feasible_pruned_actions
    )
    assert set(observed_processes) == {os.getpid()}


def test_new_lookahead_boundary_does_not_intercept_existing_monte_carlo(
    monkeypatch,
):
    configuration = HybridConfiguration(num_flows=1, num_replicas=1)
    policy = IBGHybridPolicy(
        configuration,
        HybridPolicyParameters(
            monte_carlo_samples=1,
            monte_carlo_noisy_future_flows=0,
        ),
    )

    def forbidden_lookahead_branch(_task):
        raise AssertionError("MC used deterministic lookahead worker boundary")

    monkeypatch.setattr(
        policy_module,
        "evaluate_hybrid_lookahead_branch",
        forbidden_lookahead_branch,
    )
    decision = policy.select_monte_carlo(
        state=GlobalLoadState.empty(configuration),
        admission=full_admission(configuration),
        beliefs=varied_beliefs(configuration),
        known_pair_link_costs=full_link_costs(configuration),
        root_seed=2050,
        slot_id=1,
        decision_position=1,
        flow_id=1,
        rollout_workers=1,
    )

    assert decision.result.feasible_actions == len(decision.evaluations)
