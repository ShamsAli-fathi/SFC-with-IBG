from dataclasses import dataclass
import copy
import random
import time

from claude import backward_d_memoized_simple
from header import (
    aggregate_utility_per_flow,
    aggregate_utility_total,
    embedding,
    is_equilibrium,
    jain_index,
    update,
)
from report import SLA_v


@dataclass
class SlotResult:
    embed_dict: dict
    assignments_by_stage: dict
    utility_grids: dict
    aggregate_utility_total: float
    aggregate_utility_per_flow: dict
    sla_violations: int
    jain_fairness: float
    equilibrium: int
    elapsed_seconds: float


def run_decoupled_slot(
    flow_list,
    replica_list,
    num_of_stages,
    num_of_replicas,
    likelihood=0.8,
    random_source=random,
):
    """Run one reference decoupled IBG iteration without writing reports.

    The input flow list is shuffled in place for each stage, matching the
    original orchestration in ``main.py``. Solver, utility, learning, metric,
    and equilibrium functions are delegated to the existing implementation.
    """
    if num_of_stages < 1:
        raise ValueError("num_of_stages must be at least 1")

    started_at = time.time()
    embed_dict = {f"f_{flow}": [] for flow in flow_list}
    aggregate_total = 0
    aggregate_per_flow = {flow: [] for flow in flow_list}
    assignments_by_stage = {}
    utility_grids = {}
    previous_beliefs = [
        copy.deepcopy(replica.belief) for replica in replica_list.values()
    ]

    for stage in range(1, num_of_stages + 1):
        random_source.shuffle(flow_list)
        policy, utility_grid = backward_d_memoized_simple(
            flow_list,
            replica_list,
            likelihood,
            stage,
            num_of_replicas,
        )
        embed_dict, last_embed = embedding(
            policy,
            num_of_replicas,
            embed_dict,
            flow_list,
        )
        ended_at = time.time()
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
        update(
            last_embed,
            num_of_replicas,
            stage,
            replica_list,
            likelihood,
        )

    elapsed_seconds = ended_at - started_at
    violations = SLA_v(embed_dict, replica_list)
    fairness = jain_index(aggregate_per_flow, aggregate_total)
    equilibrium = is_equilibrium(replica_list, previous_beliefs)

    return SlotResult(
        embed_dict=embed_dict,
        assignments_by_stage=assignments_by_stage,
        utility_grids=utility_grids,
        aggregate_utility_total=aggregate_total,
        aggregate_utility_per_flow=aggregate_per_flow,
        sla_violations=violations,
        jain_fairness=fairness,
        equilibrium=equilibrium,
        elapsed_seconds=elapsed_seconds,
    )
