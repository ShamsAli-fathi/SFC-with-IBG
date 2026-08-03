from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import random

import numpy as np
import pytest

from MILP.contracts import MILPConfiguration
from MILP.experiment import build_parser as build_pure_parser
from MILP.experiment import build_pure_experiment_profile
from MILP.experiment_profile import (
    MILP_ASSIGNED_FLOW_CAPACITY_UNIT,
    MILP_EXPLICIT_PLANNING_LINK_MODE,
    MILP_UNIFORM_PLANNING_LINK_MODE,
    MILP_PLANNING_LINK_PROFILE_VERSION,
    build_experiment_profile_from_runtime_states,
    experiment_profile_from_document,
)
from MILP.kernel_contracts import MILPKernelReplicaEndpoint
from MILP.kernel_profiles import build_kernel_problem_input
from MILP.phase0_contract import ReplicaKey, required_directed_pairs
from MILP.runtime_profiles import MILPRuntimeReplicaProfile
from MILP.solver import solve_coupled_milp
from MILP.scaling import build_scale_slot_input, make_scale_case


ROOT = Path(__file__).resolve().parents[1]


def _launcher_module():
    path = ROOT / "scripts/run_milp_kernel.py"
    spec = importlib.util.spec_from_file_location("milp_parity_launcher", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _common_argv(*, flow=2, stage=3, replica=2, cutoff=5, planning=2):
    return [
        "--flow",
        str(flow),
        "--stage",
        str(stage),
        "--replica",
        str(replica),
        "--cutoff",
        str(cutoff),
        "--planning-link-ms",
        str(planning),
    ]


def _runtime_profile(state, capacity):
    return MILPRuntimeReplicaProfile(
        state=state,
        capacity=capacity,
        delay=25,
        cost=1,
        gamma=0.2,
        base_delay_ms=10,
        congestion_delay_ms=2,
        observation_seed=100,
    )


def _endpoints(dimensions):
    return tuple(
        MILPKernelReplicaEndpoint(
            key=key,
            pod_name=f"stage-{key.stage}-{key.replica - 1}",
            node_name="worker",
            endpoint=f"http://stage-{key.stage}-{key.replica - 1}",
        )
        for key in dimensions.replica_keys
    )


def test_pure_and_kernel_commands_construct_identical_canonical_input():
    launcher = _launcher_module()
    argv = _common_argv(cutoff=7.5, planning=2.75)
    pure = build_pure_experiment_profile(build_pure_parser().parse_args(argv))
    kernel, _runtime = launcher.build_launcher_experiment_profile(
        launcher.build_parser().parse_args(argv)
    )

    assert pure == kernel
    assert pure.problem_input() == kernel.problem_input()
    assert pure.fingerprint == kernel.fingerprint
    assert pure.assigned_flow_capacity_unit == MILP_ASSIGNED_FLOW_CAPACITY_UNIT
    assert {item.assigned_flow_capacity for item in pure.replicas} == {2}
    assert pure.planning_link_contract_version == MILP_PLANNING_LINK_PROFILE_VERSION
    assert pure.planning_link_source == "cli-uniform"


def test_pure_and_kernel_explicit_profile_commands_construct_identical_input(tmp_path):
    launcher = _launcher_module()
    uniform_arguments = build_pure_parser().parse_args(_common_argv())
    dimensions = build_pure_experiment_profile(uniform_arguments).configuration.dimensions
    links = [
        {
            "source_stage": source.stage,
            "source_replica": source.replica,
            "target_stage": target.stage,
            "target_replica": target.replica,
            "cost_ms": 1.0 + index / 10.0,
        }
        for index, (source, target) in enumerate(required_directed_pairs(dimensions))
    ]
    path = tmp_path / "explicit-links.json"
    path.write_text(
        json.dumps(
            {
                "contract_version": MILP_PLANNING_LINK_PROFILE_VERSION,
                "source": "explicit-parity-fixture-v1",
                "dimensions": {
                    "stage_count": dimensions.stage_count,
                    "replicas_per_stage": list(dimensions.replicas_per_stage),
                },
                "links": links,
            }
        ),
        encoding="utf-8",
    )
    argv = _common_argv()
    argv[-2:] = ["--planning-links", str(path)]

    pure = build_pure_experiment_profile(build_pure_parser().parse_args(argv))
    kernel, _runtime = launcher.build_launcher_experiment_profile(
        launcher.build_parser().parse_args(argv)
    )

    assert pure == kernel
    assert pure.problem_input() == kernel.problem_input()
    assert pure.fingerprint == kernel.fingerprint
    assert pure.planning_link_source == "explicit-parity-fixture-v1"
    assert pure.planning_link_mode == MILP_EXPLICIT_PLANNING_LINK_MODE


def test_large_construction_only_parity_does_not_solve_or_contact_kubernetes():
    launcher = _launcher_module()
    argv = _common_argv(flow=14, stage=3, replica=7, cutoff=80)
    pure = build_pure_experiment_profile(build_pure_parser().parse_args(argv))
    kernel, _runtime = launcher.build_launcher_experiment_profile(
        launcher.build_parser().parse_args(argv)
    )

    assert pure.problem_input() == kernel.problem_input()
    assert pure.fingerprint == kernel.fingerprint
    assert len(pure.replicas) == 21
    assert len(pure.planning_links) == 147


def test_synthetic_scale_mode_reuses_the_benchmark_input_for_pure_and_kernel():
    launcher = _launcher_module()
    argv = [
        "--flow", "2", "--stage", "3", "--replica", "2", "--cutoff", "5",
        "--planner-profile", "synthetic-scale", "--profile-seed", "55",
    ]
    pure = build_pure_experiment_profile(build_pure_parser().parse_args(argv))
    kernel, runtime_profiles = launcher.build_launcher_experiment_profile(
        launcher.build_parser().parse_args(argv)
    )
    benchmark_slot = build_scale_slot_input(
        make_scale_case(
            flow_count=2,
            stage_count=3,
            replicas_per_stage=2,
            cutoff_seconds=5,
            profile_seed=55,
        )
    )

    assert pure == kernel
    assert pure.problem_input() == benchmark_slot.problem
    assert pure.measured_pair_profiles == benchmark_slot.measured_pair_profiles
    assert pure.fingerprint == kernel.fingerprint
    assert pure.source_identity.startswith("phase4-synthetic-scale:")
    assert {
        key: runtime_profiles[(key.stage, key.replica)].state
        for key in pure.configuration.dimensions.replica_keys
    } == benchmark_slot.problem.true_state_by_replica()


def test_synthetic_scale_mode_rejects_an_extra_planning_link_input():
    arguments = build_pure_parser().parse_args(
        [
            "--flow", "2", "--stage", "3", "--replica", "2", "--cutoff", "5",
            "--planner-profile", "synthetic-scale", "--planning-link-ms", "2",
        ]
    )
    with pytest.raises(ValueError, match="already supplies"):
        build_pure_experiment_profile(arguments)


def test_legacy_runtime_capacity_is_never_mapped_to_milp_admission():
    configuration = MILPConfiguration.uniform(
        flow_count=3, stage_count=2, replicas_per_stage=1, cutoff_seconds=2
    )
    low = {(1, 1): _runtime_profile(1, 2_000), (2, 1): _runtime_profile(4, 3_000)}
    high = {(1, 1): _runtime_profile(1, 99_000), (2, 1): _runtime_profile(4, 88_000)}
    link_document = {
        "contract_version": "milp-planning-links-v1",
        "uniform_cost_ms": 2,
    }

    first = build_experiment_profile_from_runtime_states(
        configuration,
        runtime_profiles=low,
        assigned_flow_capacity_per_replica=None,
        planning_link_document=link_document,
        source_identity="test-state-only",
    )
    second = build_experiment_profile_from_runtime_states(
        configuration,
        runtime_profiles=high,
        assigned_flow_capacity_per_replica=None,
        planning_link_document=link_document,
        source_identity="test-state-only",
    )

    assert first == second
    assert {item.assigned_flow_capacity for item in first.replicas} == {3}
    assert 2_000 not in {item.assigned_flow_capacity for item in first.replicas}


def test_state_capacity_readiness_and_link_changes_are_fingerprinted():
    profile = build_pure_experiment_profile(
        build_pure_parser().parse_args(_common_argv(flow=1, replica=1))
    )
    replica = profile.replicas[0]
    changed_state = replace(
        profile,
        replicas=(replace(replica, true_state=(replica.true_state % 4) + 1),)
        + profile.replicas[1:],
    )
    changed_capacity = replace(
        profile,
        replicas=(replace(replica, assigned_flow_capacity=2),) + profile.replicas[1:],
    )
    changed_ready = replace(
        profile,
        replicas=(replace(replica, ready=False),) + profile.replicas[1:],
    )
    link = profile.planning_links[0]
    changed_link = replace(
        profile,
        planning_links=(replace(link, cost_ms=link.cost_ms + 1),)
        + profile.planning_links[1:],
        planning_link_mode=MILP_EXPLICIT_PLANNING_LINK_MODE,
    )

    assert len(
        {
            profile.fingerprint,
            changed_state.fingerprint,
            changed_capacity.fingerprint,
            changed_ready.fingerprint,
            changed_link.fingerprint,
        }
    ) == 5


def test_uniform_links_are_faithful_and_explicitly_objective_constant(tmp_path):
    profile = build_pure_experiment_profile(
        build_pure_parser().parse_args(_common_argv(flow=3, planning=4.5))
    )

    assert profile.planning_link_mode == MILP_UNIFORM_PLANNING_LINK_MODE
    assert profile.uniform_planning_link_is_objective_constant
    assert {item.cost_ms for item in profile.planning_links} == {4.5}
    assert profile.to_document()["uniform_planning_link_is_objective_constant"] is True

    links = []
    for index, (source, target) in enumerate(
        required_directed_pairs(profile.configuration.dimensions)
    ):
        links.append(
            {
                "source_stage": source.stage,
                "source_replica": source.replica,
                "target_stage": target.stage,
                "target_replica": target.replica,
                "cost_ms": 1 + index / 10,
            }
        )
    path = tmp_path / "links.json"
    path.write_text(
        json.dumps({"contract_version": "milp-planning-links-v1", "links": links}),
        encoding="utf-8",
    )
    argv = _common_argv(flow=3)
    argv[-2:] = ["--planning-links", str(path)]
    explicit = build_pure_experiment_profile(build_pure_parser().parse_args(argv))
    assert explicit.planning_link_mode == MILP_EXPLICIT_PLANNING_LINK_MODE
    assert not explicit.uniform_planning_link_is_objective_constant
    assert len({item.cost_ms for item in explicit.planning_links}) > 1


def test_profile_json_round_trip_preserves_problem_and_fingerprint():
    profile = build_pure_experiment_profile(
        build_pure_parser().parse_args(_common_argv(cutoff=6.25))
    )
    restored = experiment_profile_from_document(profile.to_document())
    assert restored == profile
    assert restored.problem_input() == profile.problem_input()
    assert restored.fingerprint == profile.fingerprint


def test_small_real_solver_planner_parity_before_traffic():
    profile = build_pure_experiment_profile(
        build_pure_parser().parse_args(
            _common_argv(flow=1, stage=3, replica=2, cutoff=5, planning=2)
        )
    )
    configuration = profile.configuration
    pure_problem = profile.problem_input()
    kernel_problem = build_kernel_problem_input(
        configuration,
        endpoints=_endpoints(configuration.dimensions),
        experiment_profile=profile,
    )

    pure = solve_coupled_milp(pure_problem)
    kernel = solve_coupled_milp(kernel_problem)
    assert pure_problem == kernel_problem
    assert pure.provenance.status == kernel.provenance.status
    assert pure.provenance.incumbent_objective_utility == pytest.approx(
        kernel.provenance.incumbent_objective_utility
    )
    assert pure.provenance.best_bound_utility == pytest.approx(
        kernel.provenance.best_bound_utility
    )
    assert pure.provenance.relative_gap == pytest.approx(kernel.provenance.relative_gap)
    assert pure.placement == kernel.placement
    assert pure.objective == kernel.objective


def test_profile_construction_is_global_rng_neutral():
    random.seed(900)
    np.random.seed(901)
    python_before = random.getstate()
    numpy_before = np.random.get_state()
    build_pure_experiment_profile(build_pure_parser().parse_args(_common_argv()))
    assert random.getstate() == python_before
    numpy_after = np.random.get_state()
    assert numpy_after[0] == numpy_before[0]
    assert np.array_equal(numpy_after[1], numpy_before[1])
    assert numpy_after[2:] == numpy_before[2:]
