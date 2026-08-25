"""Greedy-owned assembly for active prediction, outcome, and stopping metrics."""

from __future__ import annotations

from typing import Mapping, Sequence

from IBG import latency_model
from IBG.report import SLA_v

from .contracts import PolicyResult, ReplicaIdentity
from .expected_utility import expected_stage_utility_from_belief
from .learning import maximum_belief_change
from .phase0_contract import (
    GREEDY_EQUILIBRIUM_THRESHOLD,
    GREEDY_SLA_LATENCY_THRESHOLD_MS,
)
from .slot_contracts import (
    BeliefVector,
    GreedyMeasuredPair,
    GreedySelectedObservation,
    GreedySlotMetrics,
)


GREEDY_METRIC_ASSEMBLY_VERSION = "greedy-active-slot-metrics-v1"
GREEDY_RAW_PAIR_UTILITY_WEIGHT_PER_MS = 1.0


def _metric_pairs(values: Mapping[int, float]) -> tuple[tuple[int, float], ...]:
    return tuple((flow_id, float(values[flow_id])) for flow_id in sorted(values))


def jain_fairness(
    values_per_flow: Mapping[int, float],
    aggregate_value: float,
) -> float:
    """Match the active Exact helper while keeping caller mappings immutable."""

    if not values_per_flow:
        raise ValueError("Jain fairness requires at least one flow")
    rounded = tuple(round(float(value), 3) for value in values_per_flow.values())
    denominator = len(rounded) * sum(value * value for value in rounded)
    if denominator == 0:
        raise ValueError("Jain fairness is undefined when every flow value is zero")
    return float(aggregate_value) ** 2 / denominator


def _physical_stage_utility(latency_ms: float) -> float:
    return (
        latency_model.DEFAULT_REWARD
        - latency_model.DEFAULT_LATENCY_WEIGHT * latency_ms
        - latency_model.DEFAULT_COST
    )


def compute_slot_metrics(
    *,
    policy_result: PolicyResult,
    beliefs_before: Mapping[ReplicaIdentity, BeliefVector],
    beliefs_after: Mapping[ReplicaIdentity, BeliefVector],
    observations: Sequence[GreedySelectedObservation],
    measured_pairs: Sequence[GreedyMeasuredPair],
) -> GreedySlotMetrics:
    """Compute final-load predictions and separated physical/raw outcomes."""

    predicted_per_flow = {}
    for decision in policy_result.decisions:
        predicted_per_flow[decision.flow_id] = sum(
            expected_stage_utility_from_belief(
                beliefs_before[identity],
                policy_result.final_loads.load_for(identity),
            )
            for identity in decision.action.choices
        )
    predicted_aggregate = sum(predicted_per_flow.values())

    physical_latency = {flow_id: 0.0 for flow_id in policy_result.flow_order}
    physical_utility = {flow_id: 0.0 for flow_id in policy_result.flow_order}
    for observation in observations:
        physical_latency[observation.flow_id] += (
            observation.physical_processing_latency_ms
        )
        physical_utility[observation.flow_id] += _physical_stage_utility(
            observation.physical_processing_latency_ms
        )

    pair_latency = {pair.flow_id: pair.latency_ms for pair in measured_pairs}
    raw_latency = {
        flow_id: physical_latency[flow_id] + pair_latency[flow_id]
        for flow_id in physical_latency
    }
    raw_reference_utility = {
        flow_id: physical_utility[flow_id]
        - GREEDY_RAW_PAIR_UTILITY_WEIGHT_PER_MS * pair_latency[flow_id]
        for flow_id in physical_utility
    }
    sla_violations = SLA_v(
        raw_latency,
        GREEDY_SLA_LATENCY_THRESHOLD_MS,
    )
    sla_excess = sum(
        max(0.0, raw_latency[flow_id] - GREEDY_SLA_LATENCY_THRESHOLD_MS)
        for flow_id in sorted(raw_latency)
    )
    maximum_change = maximum_belief_change(beliefs_before, beliefs_after)

    return GreedySlotMetrics(
        predicted_aggregate_utility=predicted_aggregate,
        predicted_utility_per_flow=_metric_pairs(predicted_per_flow),
        physical_realized_aggregate_utility=sum(physical_utility.values()),
        physical_realized_utility_per_flow=_metric_pairs(physical_utility),
        physical_processing_latency_ms_per_flow=_metric_pairs(physical_latency),
        measured_pair_latency_ms_per_flow=_metric_pairs(pair_latency),
        raw_end_to_end_latency_ms_per_flow=_metric_pairs(raw_latency),
        raw_end_to_end_reference_utility=sum(raw_reference_utility.values()),
        raw_end_to_end_reference_utility_per_flow=_metric_pairs(
            raw_reference_utility
        ),
        sla_latency_threshold_ms=GREEDY_SLA_LATENCY_THRESHOLD_MS,
        end_to_end_sla_violations=sla_violations,
        end_to_end_sla_excess_ms=sla_excess,
        jain_fairness=jain_fairness(
            predicted_per_flow,
            predicted_aggregate,
        ),
        maximum_belief_change=maximum_change,
        equilibrium=maximum_change < GREEDY_EQUILIBRIUM_THRESHOLD,
    )
