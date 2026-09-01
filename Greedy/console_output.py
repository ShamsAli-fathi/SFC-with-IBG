"""Human-only Greedy presentation for committed controller results."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from .contracts import ReplicaIdentity
from .slot_contracts import GreedySlotResult


GREEDY_OUTCOME_MODE = "physical-only-v1"


def _belief_text(values: Sequence[float]) -> str:
    belief = tuple(float(value) for value in values)
    if len(belief) != 4:
        raise ValueError("Greedy belief vectors must contain four entries")
    return "[" + ", ".join(f"{value:.3f}" for value in belief) + "]"


def format_greedy_replica_beliefs(
    title: str,
    beliefs: Mapping[ReplicaIdentity, Sequence[float]],
) -> str:
    if not isinstance(title, str) or not title:
        raise ValueError("belief snapshot title must be nonempty")
    if not isinstance(beliefs, Mapping) or not beliefs:
        raise ValueError("belief snapshot must contain replicas")
    rows = []
    for identity in sorted(beliefs):
        if not isinstance(identity, ReplicaIdentity):
            raise TypeError("belief snapshot keys must be ReplicaIdentity values")
        rows.append(
            f"{identity.stage:>5}  {identity.replica:>7}  "
            f"{_belief_text(beliefs[identity])}"
        )
    return "\n".join((title, "Stage  Replica  Belief", *rows))


def _pairs(values: tuple[tuple[int, float], ...], field: str) -> dict[int, float]:
    result = {flow_id: float(value) for flow_id, value in values}
    if len(result) != len(values):
        raise ValueError(f"{field} contains duplicate flows")
    return result


def _per_flow(values: Mapping[int, float]) -> str:
    return ", ".join(
        f"f{flow_id}={values[flow_id]:.6f}" for flow_id in sorted(values)
    )


def format_greedy_slot_metrics(
    result: GreedySlotResult,
    *,
    iteration: int = 1,
) -> str:
    if not isinstance(result, GreedySlotResult):
        raise TypeError("result must be GreedySlotResult")
    if isinstance(iteration, bool) or not isinstance(iteration, int) or iteration < 1:
        raise ValueError("iteration must be positive")
    metrics = result.metrics
    predicted = _pairs(metrics.predicted_utility_per_flow, "predicted utility")
    physical = _pairs(
        metrics.physical_realized_utility_per_flow, "physical utility"
    )
    raw = _pairs(
        metrics.raw_end_to_end_reference_utility_per_flow,
        "raw end-to-end utility",
    )
    expected = set(range(1, result.configuration.num_flows + 1))
    if any(set(values) != expected for values in (predicted, physical, raw)):
        raise ValueError("Greedy console metrics must cover every flow")
    return "\n".join(
        (
            f"Iteration {iteration} (slot {result.slot_id})",
            f"  Outcome mode: {GREEDY_OUTCOME_MODE}",
            "  Predicted utility:",
            f"    total={metrics.predicted_aggregate_utility:.6f}",
            f"    per flow: {_per_flow(predicted)}",
            "  Realized utility:",
            f"    total={metrics.physical_realized_aggregate_utility:.6f}",
            f"    per flow: {_per_flow(physical)}",
            "  Physical utility:",
            f"    total={metrics.physical_realized_aggregate_utility:.6f}",
            f"    per flow: {_per_flow(physical)}",
            "  Raw end-to-end utility:",
            f"    total={metrics.raw_end_to_end_reference_utility:.6f}",
            f"    per flow: {_per_flow(raw)}",
            "  Metrics:",
            "    "
            f"End-to-end SLA violations={metrics.end_to_end_sla_violations}, "
            f"end-to-end SLA excess={metrics.end_to_end_sla_excess_ms:.6f} ms, "
            f"end-to-end fairness={metrics.jain_fairness:.6f}"
            f"{'' if metrics.fairness_domain_valid else ' (clamped)'}, "
            f"time={result.timings.total_seconds:.3f}s, "
            f"equilibrium={'yes' if metrics.equilibrium else 'no'}",
        )
    )
