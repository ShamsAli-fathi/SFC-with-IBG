from __future__ import annotations

from dataclasses import replace
import json

import pytest

from MILP.contracts import MILPConfiguration
from MILP.experiment import run_experiment_profile
from MILP.experiment_profile import (
    MILP_EXPLICIT_PLANNING_LINK_MODE,
    MILP_PLANNING_LINK_PROFILE_VERSION,
    MILP_UNIFORM_PLANNING_LINK_MODE,
    build_experiment_profile,
    planning_link_costs_from_document,
)
from MILP.phase0_contract import (
    MILPContractError,
    ReplicaKey,
    required_directed_pairs,
)
from MILP.planning_links import (
    MILP_DETERMINISTIC_PLANNING_LINK_SOURCE,
    build_deterministic_planning_link_document,
)
from MILP.solver import solve_coupled_milp


def _configuration() -> MILPConfiguration:
    return MILPConfiguration.uniform(
        flow_count=1,
        stage_count=3,
        replicas_per_stage=2,
        cutoff_seconds=5,
    )


def _explicit_document(configuration, *, selected_costs=None):
    selected_costs = selected_costs or {}
    return {
        "contract_version": MILP_PLANNING_LINK_PROFILE_VERSION,
        "source": "focused-explicit-fixture-v1",
        "dimensions": {
            "stage_count": configuration.dimensions.stage_count,
            "replicas_per_stage": list(
                configuration.dimensions.replicas_per_stage
            ),
        },
        "links": [
            {
                "source_stage": source.stage,
                "source_replica": source.replica,
                "target_stage": target.stage,
                "target_replica": target.replica,
                "cost_ms": selected_costs.get((source, target), 10.0),
            }
            for source, target in required_directed_pairs(
                configuration.dimensions
            )
        ],
    }


def _profile(planning_document):
    configuration = _configuration()
    keys = configuration.dimensions.replica_keys
    return build_experiment_profile(
        configuration,
        true_states={key: 4 for key in keys},
        ready={key: True for key in keys},
        assigned_flow_capacity={key: 1 for key in keys},
        planning_link_document=planning_document,
        source_identity="planning-link-focused-fixture-v1",
        measured_pair_base_ms=5.0,
        measured_pair_jitter_ms=0.0,
    )


def test_deterministic_example_is_complete_versioned_and_heterogeneous():
    document = build_deterministic_planning_link_document(
        stage_count=3,
        replicas_per_stage=2,
    )
    configuration = _configuration()
    costs, mode = planning_link_costs_from_document(document, configuration)

    assert document["contract_version"] == MILP_PLANNING_LINK_PROFILE_VERSION
    assert document["source"] == MILP_DETERMINISTIC_PLANNING_LINK_SOURCE
    assert tuple(costs) == required_directed_pairs(configuration.dimensions)
    assert len(set(costs.values())) > 1
    assert mode == MILP_EXPLICIT_PLANNING_LINK_MODE
    json.dumps(document, sort_keys=True, allow_nan=False)


def test_uniform_mode_remains_objective_constant():
    profile = _profile(
        {
            "contract_version": MILP_PLANNING_LINK_PROFILE_VERSION,
            "source": "cli-uniform",
            "uniform_cost_ms": 2.0,
        }
    )

    assert profile.planning_link_mode == MILP_UNIFORM_PLANNING_LINK_MODE
    assert profile.uniform_planning_link_is_objective_constant
    assert {link.cost_ms for link in profile.planning_links} == {2.0}


def test_heterogeneous_cost_changes_pair_choice_from_uniform_mode():
    uniform = _profile(
        {
            "contract_version": MILP_PLANNING_LINK_PROFILE_VERSION,
            "source": "cli-uniform",
            "uniform_cost_ms": 2.0,
        }
    )
    preferred = (ReplicaKey(2, 2), ReplicaKey(3, 2))
    explicit = _profile(
        _explicit_document(_configuration(), selected_costs={preferred: 0.0})
    )

    uniform_result = solve_coupled_milp(uniform.problem_input())
    explicit_result = solve_coupled_milp(explicit.problem_input())
    uniform_action = uniform_result.placement.actions[0][1]
    explicit_action = explicit_result.placement.actions[0][1]

    assert uniform_action.directed_pair == (
        ReplicaKey(1, 1),
        ReplicaKey(2, 1),
    )
    assert explicit_action.directed_pair == preferred
    assert explicit_action != uniform_action


def test_measured_pair_profile_cannot_change_planner_coefficients_or_choice():
    profile = _profile(_explicit_document(_configuration()))
    changed_outcomes = replace(
        profile,
        measured_pair_profiles=tuple(
            replace(item, base_ms=item.base_ms + 100.0)
            for item in profile.measured_pair_profiles
        ),
    )

    assert profile.problem_input() == changed_outcomes.problem_input()
    first = run_experiment_profile(profile, root_seed=7, slot_id=1)
    second = run_experiment_profile(changed_outcomes, root_seed=7, slot_id=1)
    assert first.slot_result.placement == second.slot_result.placement
    assert (
        first.slot_result.metrics.solver_configured_planning_link_cost_ms
        == second.slot_result.metrics.solver_configured_planning_link_cost_ms
    )
    assert (
        first.slot_result.metrics.measured_pair_latency_ms
        != second.slot_result.metrics.measured_pair_latency_ms
    )


def test_explicit_validation_rejects_version_dimensions_and_incomplete_data():
    configuration = _configuration()
    valid = _explicit_document(configuration)

    wrong_version = dict(valid, contract_version="wrong")
    with pytest.raises(MILPContractError, match="version"):
        planning_link_costs_from_document(wrong_version, configuration)

    wrong_dimensions = dict(
        valid,
        dimensions={"stage_count": 3, "replicas_per_stage": [2, 2, 3]},
    )
    with pytest.raises(MILPContractError, match="dimensions"):
        planning_link_costs_from_document(wrong_dimensions, configuration)

    incomplete = dict(valid, links=valid["links"][:-1])
    with pytest.raises(MILPContractError, match="mismatch"):
        planning_link_costs_from_document(incomplete, configuration)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_stage", True),
        ("source_stage", 1.5),
        ("source_replica", 0),
        ("target_stage", "2"),
        ("target_replica", -1),
    ],
)
def test_explicit_validation_rejects_noncanonical_ids(field, value):
    configuration = _configuration()
    document = _explicit_document(configuration)
    document["links"][0][field] = value
    with pytest.raises(MILPContractError, match="positive integer"):
        planning_link_costs_from_document(document, configuration)


@pytest.mark.parametrize(
    ("source_stage", "target_stage"),
    [(1, 1), (2, 1)],
)
def test_explicit_validation_rejects_same_stage_and_reverse_links(
    source_stage,
    target_stage,
):
    configuration = _configuration()
    document = _explicit_document(configuration)
    document["links"][0]["source_stage"] = source_stage
    document["links"][0]["target_stage"] = target_stage
    with pytest.raises(MILPContractError, match="lower to a higher stage"):
        planning_link_costs_from_document(document, configuration)


def test_explicit_validation_rejects_duplicate_conflict_and_bad_costs():
    configuration = _configuration()
    duplicate = _explicit_document(configuration)
    duplicate["links"].append(dict(duplicate["links"][0], cost_ms=99.0))
    with pytest.raises(MILPContractError, match="duplicate"):
        planning_link_costs_from_document(duplicate, configuration)

    for value in (-1.0, float("nan"), float("inf")):
        invalid = _explicit_document(configuration)
        invalid["links"][0]["cost_ms"] = value
        with pytest.raises(MILPContractError, match="finite and nonnegative"):
            planning_link_costs_from_document(invalid, configuration)


def test_explicit_validation_rejects_empty_source():
    configuration = _configuration()
    document = _explicit_document(configuration)
    document["source"] = " "
    with pytest.raises(MILPContractError, match="source"):
        planning_link_costs_from_document(document, configuration)
