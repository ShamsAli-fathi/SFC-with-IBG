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
from latency_model import (
    DEFAULT_LINK_LATENCY_WEIGHT,
    DEFAULT_SLA_LATENCY_MS,
)
from learning_signal import build_learning_signal_snapshot
from outcome_latency import (
    DEFAULT_OUTCOME_LATENCY_MODE,
    PHYSICAL_PLUS_PAIR_OUTCOME_LATENCY_MODE,
    outcome_latency_ms_per_flow,
    require_outcome_latency_mode,
)
from solver_resource import SolverResourceMeter


@dataclass
class SlotResult:
    datapath_mode: str
    learning_signal_mode: str
    outcome_latency_mode: str
    embed_dict: dict
    flow_order_by_stage: dict
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
    processing_latency_ms_per_flow: dict | None = None
    link_latency_ms_per_flow: dict | None = None
    end_to_end_latency_ms_per_flow: dict | None = None
    outcome_latency_ms_per_flow: dict | None = None
    realized_utility_total: float | None = None
    realized_utility_per_flow: dict | None = None
    physical_utility_total: float | None = None
    physical_utility_per_flow: dict | None = None
    end_to_end_utility_total: float | None = None
    end_to_end_utility_per_flow: dict | None = None
    control_plane: dict | None = None
    learning_signal: dict | None = None
    solver_resource: dict | None = None


def _run_decoupled_slot_impl(
    flow_list,
    replica_list,
    num_of_stages,
    num_of_replicas,
    likelihood=0.8,
    random_source=random,
    adapters: AdapterBundle | None = None,
    slot_id=1,
    link_latency_weight=DEFAULT_LINK_LATENCY_WEIGHT,
    sla_latency_threshold_ms=DEFAULT_SLA_LATENCY_MS,
    outcome_latency_mode=DEFAULT_OUTCOME_LATENCY_MODE,
    solver_resource_meter=None,
):
    """Run one reference decoupled IBG iteration without writing reports.

    The input flow list is shuffled in place for each stage, matching the
    original orchestration in ``main.py``. Solver, utility, learning, metric,
    and equilibrium functions are delegated to the existing implementation.
    """
    if num_of_stages < 1:
        raise ValueError("num_of_stages must be at least 1")
    if link_latency_weight < 0:
        raise ValueError("link_latency_weight must not be negative")
    if sla_latency_threshold_ms <= 0:
        raise ValueError("sla_latency_threshold_ms must be positive")
    outcome_latency_mode = require_outcome_latency_mode(outcome_latency_mode)
    if adapters is None:
        adapters = make_simulation_adapters()

    started_at = time.perf_counter()
    embed_dict = {f"f_{flow}": [] for flow in flow_list}
    aggregate_total = 0
    aggregate_per_flow = {flow: [] for flow in flow_list}
    flow_order_by_stage = {}
    assignments_by_stage = {}
    utility_grids = {}
    observations_by_stage = {}
    discovered_by_stage = {}
    traffic_telemetry = None
    previous_beliefs = [
        copy.deepcopy(replica.belief) for replica in replica_list.values()
    ]
    control_plane_meter = adapters.control_plane_meter
    if control_plane_meter is not None:
        control_plane_meter.begin_slot()

    for stage in range(1, num_of_stages + 1):
        random_source.shuffle(flow_list)
        flow_order_by_stage[stage] = tuple(flow_list)
        if control_plane_meter is not None:
            control_plane_meter.begin_discovery()
        try:
            discovered_replicas = adapters.replica_discovery.discover(
                stage,
                replica_list,
            )
        finally:
            if control_plane_meter is not None:
                control_plane_meter.end_discovery()
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
        try:
            execution = adapters.traffic_executor.execute_stage(
                policy,
                num_of_replicas,
                embed_dict,
                flow_list,
            )
        finally:
            # The policy's exhaustive memo table is only needed while the
            # current stage is embedded.  Clear it promptly so a multi-slot
            # controller run cannot retain complete exact state spaces until
            # cyclic garbage collection happens to run.
            if solver_resource_meter is not None:
                solver_resource_meter.observe_rss()
                peak_memo_entries = policy.cache_info().currsize
            policy.clear_cache()
            if solver_resource_meter is not None:
                solver_resource_meter.record_stage_cache(
                    stage,
                    peak_memo_entries,
                    policy.cache_info().currsize,
                )
        embed_dict = execution.embed_dict
        last_embed = execution.assignments
        ended_at = time.perf_counter()
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
        ended_at = time.perf_counter()

    processing_latency_by_flow = {flow: 0.0 for flow in flow_list}
    physical_utility_per_flow = {flow: 0.0 for flow in flow_list}
    for observations in observations_by_stage.values():
        for observation in observations:
            processing_latency = (
                observation.measured_latency_ms
                if observation.measured_latency_ms is not None
                else observation.signal
            )
            processing_latency_by_flow[observation.flow_id] += processing_latency
            replica = replica_list[(observation.stage, observation.replica_id)]
            physical_utility_per_flow[observation.flow_id] += replica.utility_kernel(
                observation.congestion,
                processing_latency,
            )

    link_latency_by_flow = {flow: 0.0 for flow in flow_list}
    if adapters.link_latency_collector is not None:
        collected_link_latency = adapters.link_latency_collector.collect(
            traffic_telemetry
        )
        for flow in flow_list:
            link_latency_by_flow[flow] = float(
                collected_link_latency.get(flow, 0.0)
            )

    end_to_end_utility_per_flow = {
        flow: physical_utility_per_flow[flow]
        - (link_latency_weight * link_latency_by_flow[flow])
        for flow in flow_list
    }
    if outcome_latency_mode == PHYSICAL_PLUS_PAIR_OUTCOME_LATENCY_MODE:
        for flow in flow_list:
            penalty = link_latency_weight * link_latency_by_flow[flow]
            aggregate_per_flow[flow].append(-penalty)
            aggregate_total -= penalty
        realized_per_flow = end_to_end_utility_per_flow
    else:
        realized_per_flow = physical_utility_per_flow

    end_to_end_latency_by_flow = {
        flow: processing_latency_by_flow[flow] + link_latency_by_flow[flow]
        for flow in flow_list
    }
    outcome_latency_by_flow = outcome_latency_ms_per_flow(
        processing_latency_by_flow,
        link_latency_by_flow,
        outcome_latency_mode,
    )
    realized_total = sum(realized_per_flow.values())
    elapsed_seconds = ended_at - started_at
    violations = SLA_v(
        outcome_latency_by_flow,
        sla_latency_threshold_ms,
    )
    fairness = jain_index(aggregate_per_flow, aggregate_total)
    equilibrium = is_equilibrium(replica_list, previous_beliefs)
    control_plane = None
    learning_signal = None
    if control_plane_meter is not None:
        learning_signal = build_learning_signal_snapshot(
            observation
            for stage in sorted(observations_by_stage)
            for observation in observations_by_stage[stage]
        )
        control_plane_meter.finish_slot()
        control_plane = control_plane_meter.snapshot()

    result = SlotResult(
        datapath_mode=adapters.datapath_mode,
        learning_signal_mode=adapters.learning_signal_mode,
        outcome_latency_mode=outcome_latency_mode,
        embed_dict=embed_dict,
        flow_order_by_stage=flow_order_by_stage,
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
        processing_latency_ms_per_flow=processing_latency_by_flow,
        link_latency_ms_per_flow=link_latency_by_flow,
        end_to_end_latency_ms_per_flow=end_to_end_latency_by_flow,
        outcome_latency_ms_per_flow=outcome_latency_by_flow,
        realized_utility_total=realized_total,
        realized_utility_per_flow=realized_per_flow,
        physical_utility_total=sum(physical_utility_per_flow.values()),
        physical_utility_per_flow=physical_utility_per_flow,
        end_to_end_utility_total=sum(end_to_end_utility_per_flow.values()),
        end_to_end_utility_per_flow=end_to_end_utility_per_flow,
        control_plane=control_plane,
        learning_signal=learning_signal,
        solver_resource=None,
    )
    return result


def run_decoupled_slot(
    flow_list,
    replica_list,
    num_of_stages,
    num_of_replicas,
    likelihood=0.8,
    random_source=random,
    adapters: AdapterBundle | None = None,
    slot_id=1,
    link_latency_weight=DEFAULT_LINK_LATENCY_WEIGHT,
    sla_latency_threshold_ms=DEFAULT_SLA_LATENCY_MS,
    outcome_latency_mode=DEFAULT_OUTCOME_LATENCY_MODE,
    solver_resource_diagnostics=False,
    solver_resource_meter=None,
):
    """Run one slot, optionally measuring controller/solver memory resources."""
    if not isinstance(solver_resource_diagnostics, bool):
        raise ValueError("solver_resource_diagnostics must be a boolean")
    if solver_resource_meter is not None and not solver_resource_diagnostics:
        raise ValueError(
            "solver_resource_meter requires solver_resource_diagnostics"
        )
    if adapters is None:
        adapters = make_simulation_adapters()
    meter = solver_resource_meter
    if solver_resource_diagnostics and meter is None:
        meter = SolverResourceMeter()
    if meter is not None:
        meter.begin_slot()
    try:
        result = _run_decoupled_slot_impl(
            flow_list,
            replica_list,
            num_of_stages,
            num_of_replicas,
            likelihood=likelihood,
            random_source=random_source,
            adapters=adapters,
            slot_id=slot_id,
            link_latency_weight=link_latency_weight,
            sla_latency_threshold_ms=sla_latency_threshold_ms,
            outcome_latency_mode=outcome_latency_mode,
            solver_resource_meter=meter,
        )
    except BaseException:
        if meter is not None:
            meter.abort_slot()
        raise
    if meter is not None:
        meter.finish_slot()
        result.solver_resource = meter.snapshot(
            expected_stages=num_of_stages,
        )
    adapters.result_sink.record_slot(result)
    return result
