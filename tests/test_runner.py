import os
import random
import subprocess
import sys

import numpy as np

from header import Replica
from main import DEFAULT_EXPERIMENT_RUNS
from outcome_latency import (
    PHYSICAL_ONLY_OUTCOME_LATENCY_MODE,
    PHYSICAL_PLUS_PAIR_OUTCOME_LATENCY_MODE,
    outcome_latency_ms_per_flow,
)
import runner as runner_module
from runner import run_decoupled_slot


def make_replicas():
    replicas = {}
    states = {
        (1, 1): 4,
        (1, 2): 2,
        (2, 1): 3,
        (2, 2): 1,
        (3, 1): 4,
        (3, 2): 3,
    }
    for stage in range(1, 4):
        for replica in range(1, 3):
            replicas[(stage, replica)] = Replica(
                stage=stage,
                replica=replica,
                belief=[0.25, 0.25, 0.25, 0.25],
                delay=25,
                cost=1,
                gamma=0.2 if replica == 1 else 0.3,
                state=states[(stage, replica)],
                capacity=2000 if replica == 1 else 5000,
            )
    return replicas


def test_seeded_latency_slot_is_repeatable():
    first_flows = [1, 2, 3]
    first_replicas = make_replicas()
    random.seed(2026)
    np.random.seed(2026)
    first = run_decoupled_slot(first_flows, first_replicas, 3, 2)

    second_flows = [1, 2, 3]
    second_replicas = make_replicas()
    random.seed(2026)
    np.random.seed(2026)
    second = run_decoupled_slot(second_flows, second_replicas, 3, 2)

    assert first_flows == second_flows
    assert first.datapath_mode == second.datapath_mode == "simulation"
    assert first.embed_dict == second.embed_dict
    assert first.assignments_by_stage == second.assignments_by_stage
    assert first.aggregate_utility_total == second.aggregate_utility_total
    assert first.aggregate_utility_per_flow == second.aggregate_utility_per_flow
    assert first.end_to_end_latency_ms_per_flow == second.end_to_end_latency_ms_per_flow
    assert first.sla_violations == second.sla_violations
    assert first.jain_fairness == second.jain_fairness
    assert first.equilibrium == second.equilibrium

    for stage in range(1, 4):
        np.testing.assert_allclose(
            first.utility_grids[stage].to_numpy(),
            second.utility_grids[stage].to_numpy(),
        )
    for key in first_replicas:
        np.testing.assert_allclose(
            first_replicas[key].belief,
            second_replicas[key].belief,
        )


def test_outcome_latency_mode_keeps_physical_and_pair_views_switchable():
    physical = {1: 80.0, 2: 95.0}
    pair = {1: 12.0, 2: 7.0}

    assert outcome_latency_ms_per_flow(
        physical,
        pair,
        PHYSICAL_ONLY_OUTCOME_LATENCY_MODE,
    ) == physical
    assert outcome_latency_ms_per_flow(
        physical,
        pair,
        PHYSICAL_PLUS_PAIR_OUTCOME_LATENCY_MODE,
    ) == {1: 92.0, 2: 102.0}


def test_main_is_import_safe_and_defaults_to_one_experiment(tmp_path):
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(
        os.path.join(os.path.dirname(__file__), "..", "IBG")
    )

    completed = subprocess.run(
        [sys.executable, "-c", "import main"],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert list(tmp_path.iterdir()) == []
    assert DEFAULT_EXPERIMENT_RUNS == 1


def test_exact_solver_completes_three_stages_with_three_flows_and_five_replicas():
    replicas = {}
    for stage in range(1, 4):
        for replica_id in range(1, 6):
            replicas[(stage, replica_id)] = Replica(
                stage=stage,
                replica=replica_id,
                belief=[0.25, 0.25, 0.25, 0.25],
                delay=25,
                cost=1,
                gamma=0.18 + replica_id * 0.02,
                state=((stage + replica_id - 2) % 4) + 1,
                capacity=2000 if replica_id % 2 else 5000,
            )

    random.seed(3105)
    np.random.seed(3105)
    result = run_decoupled_slot(
        [1, 2, 3],
        replicas,
        num_of_stages=3,
        num_of_replicas=5,
    )

    assert set(result.assignments_by_stage) == {1, 2, 3}
    assert all(
        set(assignments) == {1, 2, 3}
        and set(assignments.values()).issubset({1, 2, 3, 4, 5})
        for assignments in result.assignments_by_stage.values()
    )
    assert all(len(route) == 3 for route in result.embed_dict.values())
    assert all(
        len(observations) == 3
        for observations in result.observations_by_stage.values()
    )


def test_runner_releases_each_exact_stage_cache_after_embedding(monkeypatch):
    policies = []
    original = runner_module.br_eibg_exact

    def track_policy(*args, **kwargs):
        policy, utility_grid = original(*args, **kwargs)
        policies.append(policy)
        return policy, utility_grid

    monkeypatch.setattr(runner_module, "br_eibg_exact", track_policy)

    run_decoupled_slot(
        [1, 2, 3],
        make_replicas(),
        num_of_stages=3,
        num_of_replicas=2,
    )

    assert len(policies) == 3
    assert all(policy.cache_info().currsize == 0 for policy in policies)
