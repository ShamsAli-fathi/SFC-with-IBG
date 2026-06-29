from dataclasses import dataclass
import copy
import random
import time

from claude import br_eibg_exact
from learning import apply_observations
from header import (
    aggregate_utility_per_flow,
    aggregate_utility_total,
    is_equilibrium,
    jain_index,
)
from ports import AdapterBundle
from report import SLA_v
from simulation_adapters import make_simulation_adapters


@dataclass
class SlotResult:
    embed_dict: dict
    assignments_by_stage: dict
    utility_grids: dict
    observations_by_stage: dict
    aggregate_utility_total: float
    aggregate_utility_per_flow: dict
    sla_violations: int
    jain_fairness: float
    equilibrium: int
    elapsed_seconds: float
    traffic_telemetry: object | None = None


def run_decoupled_slot(
    flow_list,
    replica_list,
    num_of_stages,
    num_of_replicas,
    likelihood=0.8,
    random_source=random,
    adapters: AdapterBundle | None = None,
    slot_id=1,
):
    """Run one reference decoupled IBG iteration without writing reports.

    The input flow list is shuffled in place for each stage, matching the
    original orchestration in ``main.py``. Solver, utility, learning, metric,
    and equilibrium functions are delegated to the existing implementation.
    """
    if num_of_stages < 1:
        raise ValueError("num_of_stages must be at least 1")
    if adapters is None:
        adapters = make_simulation_adapters()

    started_at = time.time()
    embed_dict = {f"f_{flow}": [] for flow in flow_list}
    aggregate_total = 0
    aggregate_per_flow = {flow: [] for flow in flow_list}
    assignments_by_stage = {}
    utility_grids = {}
    observations_by_stage = {}
    discovered_by_stage = {}
    traffic_telemetry = None
    previous_beliefs = [
        copy.deepcopy(replica.belief) for replica in replica_list.values()
    ]

    for stage in range(1, num_of_stages + 1):
        random_source.shuffle(flow_list)
        discovered_replicas = adapters.replica_discovery.discover(
            stage,
            replica_list,
        )
        if not discovered_replicas:
            raise RuntimeError(f"no replicas discovered for stage {stage}")
        discovered_by_stage[stage] = discovered_replicas
        policy, utility_grid = br_eibg_exact(
            flow_list,
            discovered_replicas,
            likelihood,
            stage,
            num_of_replicas,
        )
        execution = adapters.traffic_executor.execute_stage(
            policy,
            num_of_replicas,
            embed_dict,
            flow_list,
        )
        embed_dict = execution.embed_dict
        last_embed = execution.assignments
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
        if adapters.slot_traffic_executor is None:
            observations = adapters.observation_collector.collect(
                stage,
                last_embed,
                replica_list,
            )
            observations_by_stage[stage] = tuple(observations)
            apply_observations(observations, replica_list)

    if adapters.slot_traffic_executor is not None:
        traffic_telemetry = adapters.slot_traffic_executor.execute_slot(
            slot_id,
            assignments_by_stage,
            discovered_by_stage,
        )
        for stage in range(1, num_of_stages + 1):
            observations = adapters.observation_collector.collect(
                stage,
                assignments_by_stage[stage],
                replica_list,
            )
            observations_by_stage[stage] = tuple(observations)
            apply_observations(observations, replica_list)
        ended_at = time.time()

    elapsed_seconds = ended_at - started_at
    violations = SLA_v(embed_dict, replica_list)
    fairness = jain_index(aggregate_per_flow, aggregate_total)
    equilibrium = is_equilibrium(replica_list, previous_beliefs)

    result = SlotResult(
        embed_dict=embed_dict,
        assignments_by_stage=assignments_by_stage,
        utility_grids=utility_grids,
        observations_by_stage=observations_by_stage,
        aggregate_utility_total=aggregate_total,
        aggregate_utility_per_flow=aggregate_per_flow,
        sla_violations=violations,
        jain_fairness=fairness,
        equilibrium=equilibrium,
        elapsed_seconds=elapsed_seconds,
        traffic_telemetry=traffic_telemetry,
    )
    adapters.result_sink.record_slot(result)
    return result
