import copy
import os
import random
import subprocess
import sys

import numpy as np

from claude import br_eibg_exact
from header import (
    Replica,
    aggregate_utility_per_flow,
    aggregate_utility_total,
    embedding,
    is_equilibrium,
    jain_index,
    update,
)
from main import DEFAULT_EXPERIMENT_RUNS
from report import SLA_v
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


def run_legacy_slot(flow_list, replica_list):
    embed_dict = {f"f_{flow}": [] for flow in flow_list}
    aggregate_total = 0
    aggregate_per_flow = {flow: [] for flow in flow_list}
    assignments_by_stage = {}
    utility_grids = {}
    previous_beliefs = [
        copy.deepcopy(replica.belief) for replica in replica_list.values()
    ]

    for stage in range(1, 4):
        random.shuffle(flow_list)
        policy, utility_grid = br_eibg_exact(
            flow_list,
            replica_list,
            0.8,
            stage,
            2,
        )
        embed_dict, last_embed = embedding(
            policy,
            2,
            embed_dict,
            flow_list,
        )
        assignments_by_stage[stage] = last_embed
        utility_grids[stage] = utility_grid
        aggregate_total = aggregate_utility_total(
            utility_grid,
            last_embed,
            aggregate_total,
        )
        aggregate_per_flow = aggregate_utility_per_flow(
            last_embed,
            utility_grid,
            aggregate_per_flow,
        )
        update(last_embed, 2, stage, replica_list, 0.8)

    return {
        "embed_dict": embed_dict,
        "assignments_by_stage": assignments_by_stage,
        "utility_grids": utility_grids,
        "aggregate_total": aggregate_total,
        "aggregate_per_flow": aggregate_per_flow,
        "sla": SLA_v(embed_dict, replica_list),
        "jain": jain_index(aggregate_per_flow, aggregate_total),
        "equilibrium": is_equilibrium(replica_list, previous_beliefs),
    }


def test_extracted_slot_matches_legacy_orchestration():
    legacy_flows = [1, 2, 3]
    legacy_replicas = make_replicas()
    random.seed(2026)
    np.random.seed(2026)
    legacy = run_legacy_slot(legacy_flows, legacy_replicas)

    extracted_flows = [1, 2, 3]
    extracted_replicas = make_replicas()
    random.seed(2026)
    np.random.seed(2026)
    extracted = run_decoupled_slot(
        extracted_flows,
        extracted_replicas,
        num_of_stages=3,
        num_of_replicas=2,
        likelihood=0.8,
    )

    assert extracted_flows == legacy_flows
    assert extracted.embed_dict == legacy["embed_dict"]
    assert extracted.assignments_by_stage == legacy["assignments_by_stage"]
    assert extracted.aggregate_utility_total == legacy["aggregate_total"]
    assert extracted.aggregate_utility_per_flow == legacy["aggregate_per_flow"]
    assert extracted.sla_violations == legacy["sla"]
    assert extracted.jain_fairness == legacy["jain"]
    assert extracted.equilibrium == legacy["equilibrium"]

    for stage in range(1, 4):
        np.testing.assert_allclose(
            extracted.utility_grids[stage].to_numpy(),
            legacy["utility_grids"][stage].to_numpy(),
        )
    for key in extracted_replicas:
        np.testing.assert_allclose(
            extracted_replicas[key].belief,
            legacy_replicas[key].belief,
        )


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
