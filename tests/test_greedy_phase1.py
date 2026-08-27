from __future__ import annotations

import inspect
import random
import subprocess
import sys
from dataclasses import FrozenInstanceError
from itertools import combinations, product
from math import fsum
from pathlib import Path

import numpy as np
import pytest

from Greedy.comparison import (
    CANONICAL_MATCHED_COMPARISON,
    GREEDY_HYBRID_MATCHED_COMPARISON_VERSION,
    INTENTIONAL_POLICY_DIFFERENCE_FIELDS,
    REQUIRED_MATCHED_FIELDS,
    GreedyHybridMatchedComparison,
    IntentionalPolicyDifference,
    MatchedComparisonField,
    UNRESOLVED_COMPARISON_MISMATCH_FIELDS,
    UnresolvedComparisonMismatch,
)
from Greedy.contracts import (
    GREEDY_STAGE_BUDGET,
    GlobalLoadState,
    GreedyConfiguration,
    NoFeasibleActionError,
    PublicReplicaState,
    ReplicaIdentity,
    TwoStageAction,
)
from Greedy.expected_utility import (
    BoundedExpectedUtilityCache,
    expected_stage_utility_from_belief,
)
from Greedy.policy import GreedyPolicy
from IBG.latency_model import expected_state_utility


ROOT = Path(__file__).resolve().parents[1]


def public_states(
    configuration: GreedyConfiguration,
    *,
    belief=(0.0, 0.0, 0.0, 1.0),
    not_ready=(),
):
    not_ready = set(not_ready)
    return tuple(
        PublicReplicaState(
            identity=ReplicaIdentity(stage, replica),
            ready=ReplicaIdentity(stage, replica) not in not_ready,
            belief=belief,
        )
        for stage in configuration.stages
        for replica in configuration.replica_ids
    )


def replace_public_state(states, identity, **changes):
    updated = []
    for state in states:
        if state.identity != identity:
            updated.append(state)
            continue
        updated.append(
            PublicReplicaState(
                identity=state.identity,
                ready=changes.get("ready", state.ready),
                belief=changes.get("belief", state.belief),
            )
        )
    return tuple(updated)


def exhaustive_reference(configuration, flow_order, states):
    identities = tuple(state.identity for state in states)
    by_identity = {state.identity: state for state in states}
    loads = {identity: 0 for identity in identities}
    actions = tuple(
        sorted(
            TwoStageAction((ReplicaIdentity(sa, ra), ReplicaIdentity(sb, rb)))
            for sa, sb in combinations(configuration.stages, GREEDY_STAGE_BUDGET)
            for ra, rb in product(
                configuration.replica_ids,
                repeat=GREEDY_STAGE_BUDGET,
            )
        )
    )
    selected = []
    for _flow_id in flow_order:
        feasible = tuple(
            action
            for action in actions
            if all(
                by_identity[identity].ready
                for identity in action.choices
            )
        )
        winner = min(
            feasible,
            key=lambda action: (
                -fsum(
                    expected_stage_utility_from_belief(
                        by_identity[identity].belief,
                        loads[identity] + 1,
                    )
                    for identity in action.choices
                ),
                action,
            ),
        )
        selected.append(winner)
        for identity in winner.choices:
            loads[identity] += 1
    return tuple(selected), GlobalLoadState.from_mapping(loads)


def test_configuration_requires_explicit_dimensions_and_validates_each_value():
    signature = inspect.signature(GreedyConfiguration)
    assert all(
        signature.parameters[name].default is inspect.Parameter.empty
        for name in ("num_flows", "num_stages", "num_replicas")
    )
    with pytest.raises(TypeError):
        GreedyConfiguration()
    for values, message in (
        ((0, 2, 1), "num_flows"),
        ((1, 1, 1), "num_stages"),
        ((1, 2, 0), "num_replicas"),
    ):
        with pytest.raises(ValueError, match=message):
            GreedyConfiguration(*values)
    with pytest.raises(TypeError, match="num_flows"):
        GreedyConfiguration(True, 2, 1)


def test_arbitrary_dimensions_have_contiguous_uniform_immutable_identities():
    configuration = GreedyConfiguration(7, 4, 3)
    policy = GreedyPolicy(configuration)
    assert configuration.stages == (1, 2, 3, 4)
    assert configuration.replica_ids == (1, 2, 3)
    assert policy.identities == tuple(
        ReplicaIdentity(stage, replica)
        for stage in range(1, 5)
        for replica in range(1, 4)
    )
    assert policy.identities_by_stage[2] == (
        ReplicaIdentity(3, 1),
        ReplicaIdentity(3, 2),
        ReplicaIdentity(3, 3),
    )
    with pytest.raises(FrozenInstanceError):
        configuration.num_flows = 8


def test_actions_are_complete_l2_distinct_stage_and_globally_lexicographic():
    configuration = GreedyConfiguration(1, 4, 2)
    policy = GreedyPolicy(configuration)
    assert len(policy.actions) == 6 * 4
    assert policy.actions == tuple(sorted(policy.actions))
    assert policy.actions[:3] == (
        TwoStageAction((ReplicaIdentity(1, 1), ReplicaIdentity(2, 1))),
        TwoStageAction((ReplicaIdentity(1, 1), ReplicaIdentity(2, 2))),
        TwoStageAction((ReplicaIdentity(1, 1), ReplicaIdentity(3, 1))),
    )
    assert all(len(action.choices) == 2 for action in policy.actions)
    assert all(action.choices[0].stage < action.choices[1].stage for action in policy.actions)


def test_configuration_and_public_state_have_no_topology_derived_admission_fields():
    configuration = GreedyConfiguration(10, 3, 3)
    states = public_states(configuration)
    assert "admission_capacity_per_replica" not in dir(configuration)
    assert "max_assigned_flows" not in PublicReplicaState.__dataclass_fields__
    assert all(not hasattr(state, "max_assigned_flows") for state in states)


def test_feasibility_uses_only_ready_state_after_exact_identity_validation():
    configuration = GreedyConfiguration(2, 2, 2)
    policy = GreedyPolicy(configuration)
    unavailable = ReplicaIdentity(1, 1)
    states = public_states(configuration, not_ready=(unavailable,))
    state = GlobalLoadState.from_mapping(
        {
            identity: int(identity == ReplicaIdentity(2, 1))
            for identity in policy.identities
        }
    )
    by_identity = {item.identity: item for item in states}
    assert policy.evaluate_admission(unavailable, state, by_identity).reasons == (
        "not-ready:1:1",
    )
    assert policy.evaluate_admission(ReplicaIdentity(2, 1), state, by_identity).feasible
    assert policy.evaluate_admission(
        ReplicaIdentity(1, 2), state, by_identity
    ).feasible


def test_projected_load_scoring_uses_current_plus_one_and_active_math():
    configuration = GreedyConfiguration(4, 2, 2)
    policy = GreedyPolicy(configuration)
    first = ReplicaIdentity(1, 1)
    second = ReplicaIdentity(2, 1)
    states = public_states(configuration, belief=(1.0, 0.0, 0.0, 0.0))
    states = replace_public_state(states, first, belief=(0.0, 0.0, 0.0, 1.0))
    states = replace_public_state(states, second, belief=(0.0, 0.0, 0.0, 1.0))
    initial = GlobalLoadState.from_mapping(
        {identity: int(identity in (first, second)) for identity in policy.identities}
    )
    decision = policy.select_action(
        flow_id=1,
        state=initial,
        replica_states=states,
    )
    assert decision.action == TwoStageAction((first, second))
    assert decision.stage_utilities == pytest.approx(
        (
            expected_stage_utility_from_belief((0, 0, 0, 1), 2),
            expected_stage_utility_from_belief((0, 0, 0, 1), 2),
        )
    )


def test_sequential_policy_commits_both_loads_before_the_next_flow():
    configuration = GreedyConfiguration(2, 2, 2)
    policy = GreedyPolicy(configuration)
    result = policy.place(
        flow_order=(2, 1),
        replica_states=public_states(configuration),
    )
    first_action = TwoStageAction(
        (ReplicaIdentity(1, 1), ReplicaIdentity(2, 1))
    )
    second_action = TwoStageAction(
        (ReplicaIdentity(1, 2), ReplicaIdentity(2, 2))
    )
    assert result.actions == (first_action, second_action)
    assert result.decisions[0].state_after == result.decisions[1].state_before
    assert dict(result.final_loads.entries) == {
        identity: 1 for identity in policy.identities
    }


def test_exact_ties_choose_the_lexicographically_lowest_action_and_k_minus_two_bypasses():
    configuration = GreedyConfiguration(1, 4, 1)
    result = GreedyPolicy(configuration).place(
        flow_order=(1,),
        replica_states=public_states(configuration),
    )
    assert result.actions == (
        TwoStageAction((ReplicaIdentity(1, 1), ReplicaIdentity(2, 1))),
    )
    assert result.decisions[0].bypassed_stages == (3, 4)


def test_best_feasible_action_is_selected_when_all_scores_are_nonpositive():
    configuration = GreedyConfiguration(3, 3, 1)
    policy = GreedyPolicy(configuration)
    loads = GlobalLoadState.from_mapping({identity: 2 for identity in policy.identities})
    decision = policy.select_action(
        flow_id=1,
        state=loads,
        replica_states=public_states(configuration, belief=(1.0, 0.0, 0.0, 0.0)),
    )
    assert all(value < 0 for value in decision.stage_utilities)
    assert decision.action == TwoStageAction(
        (ReplicaIdentity(1, 1), ReplicaIdentity(2, 1))
    )


def test_no_complete_feasible_action_fails_explicitly():
    configuration = GreedyConfiguration(1, 2, 1)
    policy = GreedyPolicy(configuration)
    with pytest.raises(NoFeasibleActionError, match="no feasible complete L=2") as error:
        policy.place(
            flow_order=(1,),
            replica_states=public_states(
                configuration,
                not_ready=(ReplicaIdentity(1, 1),),
            ),
        )
    assert error.value.flow_id == 1
    assert error.value.evaluated_actions == 1


def test_policy_does_not_mutate_caller_owned_inputs():
    configuration = GreedyConfiguration(1, 3, 2)
    policy = GreedyPolicy(configuration)
    flow_order = [1]
    states = list(public_states(configuration))
    loads = {identity: 0 for identity in policy.identities}
    initial = GlobalLoadState.from_mapping(loads)
    before_states = list(states)
    before_loads = dict(loads)
    policy.place(
        flow_order=flow_order,
        replica_states=states,
        initial_loads=initial,
    )
    assert flow_order == [1]
    assert states == before_states
    assert loads == before_loads
    assert initial == GlobalLoadState.from_mapping(before_loads)


def test_repeated_cached_and_uncached_results_match_reference_exactly():
    configuration = GreedyConfiguration(3, 3, 2)
    states = public_states(configuration, belief=(0.1, 0.2, 0.3, 0.4))
    flow_order = (3, 1, 2)
    policy = GreedyPolicy(configuration)
    cached = policy.place(flow_order=flow_order, replica_states=states, use_cache=True)
    repeated = policy.place(flow_order=flow_order, replica_states=states, use_cache=True)
    uncached = GreedyPolicy(configuration).place(
        flow_order=flow_order,
        replica_states=states,
        use_cache=False,
    )
    reference_actions, reference_loads = exhaustive_reference(
        configuration,
        flow_order,
        states,
    )
    assert cached == repeated == uncached
    assert cached.actions == reference_actions
    assert cached.final_loads == reference_loads


def test_expected_utility_adapter_matches_policy_neutral_latency_model():
    belief = (0.1, 0.2, 0.3, 0.4)
    expected = sum(
        probability * expected_state_utility(state, 2)
        for state, probability in enumerate(belief, start=1)
    )
    assert expected_stage_utility_from_belief(belief, 2) == pytest.approx(expected)


def test_expected_utility_cache_is_exact_bounded_lru_and_clearable():
    cache = BoundedExpectedUtilityCache(max_entries=2)
    first = (1.0, 0.0, 0.0, 0.0)
    second = (0.0, 1.0, 0.0, 0.0)
    third = (0.0, 0.0, 1.0, 0.0)
    cache.value(first, 1)
    cache.value(second, 1)
    cache.value(first, 1)
    cache.value(third, 1)
    assert cache.info.max_entries == 2
    assert cache.info.size == 2
    assert cache.info.hits == 1
    assert cache.info.misses == 3
    assert cache.info.evictions == 1
    cache.clear()
    assert cache.info.size == 0


def test_policy_inputs_exclude_hidden_seed_runtime_and_link_fields():
    fields = set(PublicReplicaState.__dataclass_fields__)
    assert fields == {"identity", "ready", "belief"}
    assert {
        "hidden_state",
        "profile_seed",
        "physical_seed",
        "observation_seed",
        "measured_pair_latency_ms",
        "planning_link_cost_ms",
    }.isdisjoint(fields)
    with pytest.raises(TypeError, match="unexpected keyword"):
        PublicReplicaState(
            identity=ReplicaIdentity(1, 1),
            ready=True,
            belief=(0.25,) * 4,
            hidden_state=4,
        )
    assert set(inspect.signature(GreedyPolicy.select_action).parameters) == {
        "self",
        "flow_id",
        "state",
        "replica_states",
        "use_cache",
    }


def test_policy_consumes_no_global_python_or_numpy_rng_state():
    random.seed(741)
    np.random.seed(742)
    python_before = random.getstate()
    numpy_before = np.random.get_state()
    configuration = GreedyConfiguration(2, 3, 2)
    GreedyPolicy(configuration).place(
        flow_order=(2, 1),
        replica_states=public_states(configuration),
    )
    python_after = random.getstate()
    numpy_after = np.random.get_state()
    assert python_after == python_before
    assert numpy_after[0] == numpy_before[0]
    assert np.array_equal(numpy_after[1], numpy_before[1])
    assert numpy_after[2:] == numpy_before[2:]


def test_policy_source_has_no_hybrid_pruning_lookahead_mc_or_process_pool_dependency():
    source = (ROOT / "Greedy" / "policy.py").read_text()
    for forbidden in (
        "IBG_Hybrid",
        "ProcessPoolExecutor",
        "candidate_pruning",
        "lookahead",
        "monte_carlo",
        "known_pair_link_costs",
        "planning_link",
        "candidates_per_stage",
        "lookahead_future_flows",
        "monte_carlo_samples",
        "ProcessPool",
        "--policy",
        "--mc-workers",
        "import random",
        "import numpy",
    ):
        assert forbidden not in source


def test_modules_import_silently_in_clean_directory_without_creating_files(tmp_path):
    modules = (
        "Greedy",
        "Greedy.contracts",
        "Greedy.expected_utility",
        "Greedy.policy",
        "Greedy.comparison",
    )
    completed = subprocess.run(
        [sys.executable, "-c", "; ".join(f"import {name}" for name in modules)],
        cwd=tmp_path,
        env={
            "PYTHONPATH": str(ROOT),
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert completed.stderr == ""
    assert list(tmp_path.iterdir()) == []


def test_canonical_10x3x5_comparison_fixture_is_complete_and_not_a_default():
    fixture = CANONICAL_MATCHED_COMPARISON
    assert fixture.version == GREEDY_HYBRID_MATCHED_COMPARISON_VERSION
    assert tuple(item.name for item in fixture.required_matches) == REQUIRED_MATCHED_FIELDS
    assert tuple(
        item.name for item in fixture.intentional_policy_differences
    ) == INTENTIONAL_POLICY_DIFFERENCE_FIELDS
    assert tuple(item.name for item in fixture.unresolved_mismatches) == (
        UNRESOLVED_COMPARISON_MISMATCH_FIELDS
    )
    assert fixture.canonical_configuration == GreedyConfiguration(10, 3, 5)
    assert fixture.unresolved_mismatches[0].greedy_value == "none-ready-only"
    assert fixture.unresolved_mismatches[0].hybrid_value == (
        "ceil-N-over-M-declared-capacity"
    )
    assert fixture.matched_value("private_processor_request") == "50m/128Mi"
    assert fixture.matched_value("private_processor_limit") == "1CPU/768Mi"
    assert fixture.matched_value("public_forwarder_request") == "25m/128Mi"
    assert fixture.matched_value("public_forwarder_limit") == "1CPU/256Mi"
    assert fixture.matched_value("flow_generator_request") == "50m/128Mi"
    assert fixture.matched_value("flow_generator_limit") == "1CPU/768Mi"
    assert fixture.matched_value("controller_request") == "2CPU/256Mi"
    assert fixture.matched_value("controller_limit") == "4CPU/1Gi"
    assert fixture.matched_value("private_processor_workers") == 1
    assert fixture.matched_value("public_forwarder_workers") == 2
    assert fixture.matched_value("private_processor_port") == 8081
    assert fixture.matched_value("public_forwarder_port") == 8080
    assert fixture.matched_value("downstream_server_keepalive_seconds") == 30
    assert fixture.matched_value("materialized_runtime_profile_map") == (
        "same-identity-aligned-hidden-state-and-observation-seed-map"
    )
    assert fixture.matched_value("root_seed") == "same-explicit-root-seed"
    assert fixture.matched_value("rollout_batch_size") == (
        "same-explicit-positive-value"
    )
    assert fixture.matched_value("parity_replay_setting") == (
        "same-explicit-zero-or-one-setting"
    )


def test_comparison_rejects_mismatch_missing_fields_and_fake_differences():
    with pytest.raises(ValueError, match="mismatched"):
        MatchedComparisonField("num_flows", 10, 11, "source.py:1")
    with pytest.raises(ValueError, match="incomplete"):
        GreedyHybridMatchedComparison(
            version=GREEDY_HYBRID_MATCHED_COMPARISON_VERSION,
            required_matches=CANONICAL_MATCHED_COMPARISON.required_matches[:-1],
            intentional_policy_differences=(
                CANONICAL_MATCHED_COMPARISON.intentional_policy_differences
            ),
            unresolved_mismatches=CANONICAL_MATCHED_COMPARISON.unresolved_mismatches,
        )
    with pytest.raises(ValueError, match="must actually differ"):
        IntentionalPolicyDifference("same", "value", "value", "not different")
    with pytest.raises(ValueError, match="must actually differ"):
        UnresolvedComparisonMismatch(
            "same", "value", "value", "not different", "source.py:1"
        )


def test_incomplete_or_duplicate_public_state_and_flow_order_are_rejected():
    configuration = GreedyConfiguration(2, 2, 2)
    policy = GreedyPolicy(configuration)
    states = public_states(configuration)
    with pytest.raises(ValueError, match="every configured identity"):
        policy.place(flow_order=(1, 2), replica_states=states[:-1])
    with pytest.raises(ValueError, match="explicit permutation"):
        policy.place(flow_order=(1, 1), replica_states=states)
