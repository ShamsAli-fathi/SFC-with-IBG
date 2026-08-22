"""Human-readable, presentation-only output for completed Hybrid slots."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from IBG.outcome_latency import DEFAULT_OUTCOME_LATENCY_MODE

from .contracts import ReplicaChoice
from .slot_contracts import HybridSlotResult


HYBRID_SLOT_EVIDENCE_PREFIX = "HYBRID_SLOT_EVIDENCE="


def _belief_text(values: Sequence[float]) -> str:
    belief = tuple(float(value) for value in values)
    if len(belief) != 4:
        raise ValueError("Hybrid belief vectors must contain exactly four values")
    return "[" + ", ".join(f"{value:.3f}" for value in belief) + "]"


def format_hybrid_replica_beliefs(
    title: str,
    beliefs: Mapping[ReplicaChoice, Sequence[float]],
) -> str:
    """Match Exact's replica-table style without exposing hidden state."""

    if not isinstance(title, str) or not title:
        raise ValueError("belief snapshot title must be nonempty")
    if not isinstance(beliefs, Mapping) or not beliefs:
        raise ValueError("belief snapshot must contain at least one replica")
    rows = []
    for choice in sorted(beliefs):
        if not isinstance(choice, ReplicaChoice):
            raise TypeError("belief snapshot keys must be ReplicaChoice values")
        rows.append(
            f"{choice.stage:>5}  {choice.replica:>7}  "
            f"{_belief_text(beliefs[choice])}"
        )
    return "\n".join((title, "Stage  Replica  Belief", *rows))


def _metric_mapping(
    values: tuple[tuple[int, float], ...],
    *,
    field: str,
) -> dict[int, float]:
    result = {flow_id: float(value) for flow_id, value in values}
    if len(result) != len(values):
        raise ValueError(f"{field} contains duplicate flow identities")
    return result


def _per_flow_text(values: Mapping[int, float]) -> str:
    return ", ".join(
        f"f{flow_id}={values[flow_id]:.6f}" for flow_id in sorted(values)
    )


def format_hybrid_slot_metrics(
    result: HybridSlotResult,
    *,
    iteration: int = 1,
) -> str:
    """Format one completed pure or Kernel Hybrid slot without trace detail."""

    if not isinstance(result, HybridSlotResult):
        raise TypeError("result must be HybridSlotResult")
    if isinstance(iteration, bool) or not isinstance(iteration, int) or iteration < 1:
        raise ValueError("iteration must be a positive integer")

    metrics = result.metrics
    predicted = _metric_mapping(
        metrics.aggregate_expected_utility_per_flow,
        field="predicted utility",
    )
    physical = _metric_mapping(
        metrics.physical_realized_utility_per_flow,
        field="physical utility",
    )
    raw_utility = _metric_mapping(
        metrics.raw_end_to_end_reference_utility_per_flow,
        field="raw end-to-end utility",
    )
    expected_flows = set(range(1, result.configuration.num_flows + 1))
    for field, values in (
        ("predicted utility", predicted),
        ("physical utility", physical),
        ("raw end-to-end utility", raw_utility),
    ):
        if set(values) != expected_flows:
            raise ValueError(f"{field} does not cover every configured flow")

    outcome_mode = DEFAULT_OUTCOME_LATENCY_MODE
    realized_total = metrics.physical_realized_utility
    realized_per_flow = physical

    lines = [
        f"Iteration {iteration} (slot {result.slot_id})",
        f"  Outcome mode: {outcome_mode}",
        "  Predicted utility:",
        f"    total={metrics.aggregate_expected_utility:.6f}",
        f"    per flow: {_per_flow_text(predicted)}",
        "  Realized utility:",
        f"    total={realized_total:.6f}",
        f"    per flow: {_per_flow_text(realized_per_flow)}",
        "  Physical utility:",
        f"    total={metrics.physical_realized_utility:.6f}",
        f"    per flow: {_per_flow_text(physical)}",
        "  Raw end-to-end utility:",
        f"    total={metrics.raw_end_to_end_reference_utility:.6f}",
        f"    per flow: {_per_flow_text(raw_utility)}",
        "  Metrics:",
        "    "
        f"End-to-end SLA violations={metrics.end_to_end_sla_violations}, "
        f"end-to-end SLA excess={metrics.end_to_end_sla_excess_ms:.6f} ms, "
        f"fairness={metrics.jain_fairness:.6f}, "
        f"time={metrics.elapsed_seconds:.3f}s, "
        f"equilibrium={'yes' if metrics.equilibrium else 'no'}",
    ]
    return "\n".join(lines)
