from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import random

import numpy as np
import pytest

from Greedy.comparison import (
    CANONICAL_MATCHED_COMPARISON,
    GREEDY_HYBRID_MATCHED_COMPARISON_VERSION,
    GREEDY_PHASE81_HYBRID_AUDIT_HEAD,
    GREEDY_PHASE81_HYBRID_SOURCE_AUDIT,
)
from Greedy.contracts import (
    GREEDY_POLICY_VERSION,
    GlobalLoadState,
    GreedyConfiguration,
    NoFeasibleActionError,
    PublicReplicaState,
    ReplicaIdentity,
    TwoStageAction,
)
from Greedy.expected_utility import expected_stage_utility_from_belief
from Greedy.kernel_infrastructure import (
    GREEDY_CONTROLLER_INPUT_CONFIG_MAP,
    GreedyStaticDeploymentInput,
    parse_resource_documents,
    render_long_running_resources,
    render_resource_documents,
)
from Greedy.kernel_profile_reconciliation import materialize_runtime_profiles
from Greedy.policy import GreedyPolicy


ROOT = Path(__file__).resolve().parents[1]
GOOD = (0.0, 0.0, 0.0, 1.0)
BAD = (1.0, 0.0, 0.0, 0.0)


def _states(
    configuration: GreedyConfiguration,
    *,
    not_ready: tuple[ReplicaIdentity, ...] = (),
) -> tuple[PublicReplicaState, ...]:
    unavailable = set(not_ready)
    return tuple(
        PublicReplicaState(
            identity=ReplicaIdentity(stage, replica),
            ready=ReplicaIdentity(stage, replica) not in unavailable,
            belief=GOOD if replica == 1 else BAD,
        )
        for stage in configuration.stages
        for replica in configuration.replica_ids
    )


def _deployment(configuration: GreedyConfiguration) -> GreedyStaticDeploymentInput:
    return GreedyStaticDeploymentInput(
        runtime_profiles=materialize_runtime_profiles(
            configuration,
            profile_seed=17,
        ),
        experiment_id=1,
        root_seed=2050,
        profile_seed=17,
        max_iterations=5,
        first_slot_id=1,
        source_identity="greedy-phase81-offline",
    )


def test_v2_ready_only_hotspot_exceeds_former_ceiling_and_uses_true_current_load():
    configuration = GreedyConfiguration(5, 2, 2)
    states = _states(configuration)
    states_before = deepcopy(states)
    former_ceiling = (configuration.num_flows + configuration.num_replicas - 1) // configuration.num_replicas
    cached_policy = GreedyPolicy(configuration)
    cached = cached_policy.place(
        flow_order=(1, 2, 3, 4, 5),
        replica_states=states,
    )
    uncached = GreedyPolicy(configuration).place(
        flow_order=(1, 2, 3, 4, 5),
        replica_states=states,
        use_cache=False,
    )

    assert GREEDY_POLICY_VERSION == "pure-greedy-budgeted-l2-v2"
    assert cached == uncached
    assert states == states_before
    selected = (ReplicaIdentity(1, 1), ReplicaIdentity(2, 1))
    assert all(decision.action.choices == selected for decision in cached.decisions)
    assert all(
        cached.final_loads.load_for(identity) == configuration.num_flows
        > former_ceiling
        for identity in selected
    )
    for projected_load, decision in enumerate(cached.decisions, start=1):
        assert tuple(
            decision.state_before.load_for(identity) for identity in selected
        ) == (projected_load - 1, projected_load - 1)
        assert decision.stage_utilities == pytest.approx(
            (expected_stage_utility_from_belief(GOOD, projected_load),) * 2
        )
    assert cached.decisions[0].stage_utilities == pytest.approx(
        (expected_stage_utility_from_belief(GOOD, 1),) * 2
    )
    assert cached.decisions[0].stage_utilities != pytest.approx(
        (expected_stage_utility_from_belief(GOOD, configuration.num_flows),) * 2
    )
    assert cached_policy.utility_cache_info.size > 0


def test_v2_feasibility_is_ready_only_but_exact_identity_coverage_is_mandatory():
    configuration = GreedyConfiguration(3, 2, 1)
    policy = GreedyPolicy(configuration)
    states = _states(configuration)
    loaded = GlobalLoadState.from_mapping(
        {identity: configuration.num_flows for identity in policy.identities}
    )
    by_identity = {state.identity: state for state in states}
    assert all(
        policy.evaluate_admission(identity, loaded, by_identity).feasible
        for identity in policy.identities
    )
    with pytest.raises(ValueError, match="cover every configured identity"):
        policy.place(flow_order=(1, 2, 3), replica_states=states[:-1])
    blocked = _states(
        configuration,
        not_ready=(ReplicaIdentity(1, 1),),
    )
    with pytest.raises(NoFeasibleActionError):
        policy.place(flow_order=(1, 2, 3), replica_states=blocked)
    with pytest.raises(TypeError, match="unexpected keyword"):
        PublicReplicaState(
            identity=ReplicaIdentity(1, 1),
            ready=True,
            belief=GOOD,
            max_assigned_flows=99,
        )


def test_v2_preserves_canonical_ties_nonpositive_completion_and_k_minus_two_bypasses():
    configuration = GreedyConfiguration(2, 4, 1)
    policy = GreedyPolicy(configuration)
    states = tuple(
        PublicReplicaState(identity=identity, ready=True, belief=BAD)
        for identity in policy.identities
    )
    high_load = GlobalLoadState.from_mapping(
        {identity: 20 for identity in policy.identities}
    )
    decision = policy.select_action(
        flow_id=1,
        state=high_load,
        replica_states=states,
        use_cache=False,
    )
    assert decision.action == TwoStageAction(
        (ReplicaIdentity(1, 1), ReplicaIdentity(2, 1))
    )
    assert decision.objective_value < 0
    assert decision.bypassed_stages == (3, 4)
    assert decision.state_after.total_assignments == high_load.total_assignments + 2


def test_v2_render_and_controller_inputs_have_no_synthetic_capacity_field_or_label():
    configuration = GreedyConfiguration(7, 4, 3)
    resources = render_long_running_resources(_deployment(configuration))
    rendered = render_resource_documents(resources)
    assert parse_resource_documents(rendered) == resources
    assert "greedy.max-assigned-flows" not in rendered
    assert "max_assigned_flows" not in rendered
    assert "admission_capacity_per_replica" not in rendered
    controller = next(
        item
        for item in resources
        if item["kind"] == "ConfigMap"
        and item["metadata"]["name"] == GREEDY_CONTROLLER_INPUT_CONFIG_MAP
    )
    controller_inputs = json.loads(controller["data"]["controller-inputs.json"])
    assert set(controller_inputs["configuration"]) == {
        "num_flows", "num_stages", "num_replicas",
    }


def test_v2_comparison_records_hybrid_admission_as_unresolved_not_matched():
    comparison = CANONICAL_MATCHED_COMPARISON
    assert comparison.version == GREEDY_HYBRID_MATCHED_COMPARISON_VERSION
    assert comparison.version == "greedy-hybrid-matched-comparison-v2"
    assert "admission_capacity_per_replica" not in {
        item.name for item in comparison.required_matches
    }
    mismatch = comparison.unresolved_mismatches
    assert len(mismatch) == 1
    assert mismatch[0].name == "assigned_flow_admission"
    assert mismatch[0].greedy_value == "none-ready-only"
    assert mismatch[0].hybrid_value == "ceil-N-over-M-declared-capacity"
    assert GREEDY_PHASE81_HYBRID_AUDIT_HEAD == (
        "ae95e74497339b6ce49d96a709409489ef287fd5"
    )
    assert {item.disposition for item in GREEDY_PHASE81_HYBRID_SOURCE_AUDIT} == {
        "exclude"
    }


def test_v2_policy_is_repeatable_rng_neutral_and_has_no_hybrid_policy_dependency():
    configuration = GreedyConfiguration(5, 3, 2)
    states = _states(configuration)
    random.seed(8101)
    np.random.seed(8102)
    python_before = random.getstate()
    numpy_before = np.random.get_state()
    first = GreedyPolicy(configuration).place(
        flow_order=(5, 4, 3, 2, 1),
        replica_states=states,
    )
    second = GreedyPolicy(configuration).place(
        flow_order=(5, 4, 3, 2, 1),
        replica_states=states,
    )
    assert first == second
    assert random.getstate() == python_before
    numpy_after = np.random.get_state()
    assert numpy_after[0] == numpy_before[0]
    assert np.array_equal(numpy_after[1], numpy_before[1])
    assert numpy_after[2:] == numpy_before[2:]
    source = (ROOT / "Greedy" / "policy.py").read_text(encoding="utf-8")
    for forbidden in (
        "IBG_Hybrid", "lookahead", "monte_carlo", "ProcessPoolExecutor",
        "planning_link", "future_flow",
    ):
        assert forbidden not in source
