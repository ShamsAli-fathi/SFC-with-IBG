"""Opt-in, behavior-neutral MILP diagnostic compatibility boundary."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from numbers import Integral

from .kernel_contracts import MILPKernelSlotResult
from .phase0_contract import MILPContractError
from .slot_contracts import MILPSlotResult
from .trace_contracts import MILPTraceDiagnostic


MILP_PHASE6_DIAGNOSTIC_VERSION = "milp-coupled-phase6-diagnostics-v1"


class DiagnosticDisposition(str, Enum):
    COMPATIBLE = "compatible"
    ADAPTED = "adapted"
    INAPPLICABLE = "inapplicable"


@dataclass(frozen=True, order=True)
class MILPDiagnosticCompatibility:
    name: str
    disposition: DiagnosticDisposition
    reason: str


MILP_DIAGNOSTIC_COMPATIBILITY = (
    MILPDiagnosticCompatibility(
        "controller-timing",
        DiagnosticDisposition.ADAPTED,
        "retain model-build, solve, traffic/simulation, and total time without Exact admission/feedback phases",
    ),
    MILPDiagnosticCompatibility(
        "http-route-timing",
        DiagnosticDisposition.COMPATIBLE,
        "selected Kernel request and transport timing is algorithm-neutral supplemental telemetry",
    ),
    MILPDiagnosticCompatibility(
        "forwarding-path",
        DiagnosticDisposition.COMPATIBLE,
        "opt-in same-clock selected-forwarder timing may be attached without entering the objective",
    ),
    MILPDiagnosticCompatibility(
        "forwarder-cgroup",
        DiagnosticDisposition.COMPATIBLE,
        "opt-in selected-forwarder CPU counters remain transport/runtime telemetry",
    ),
    MILPDiagnosticCompatibility(
        "payload",
        DiagnosticDisposition.ADAPTED,
        "MILP counts selected route records; wire-byte accounting requires explicit Kernel capture",
    ),
    MILPDiagnosticCompatibility(
        "solver-resource",
        DiagnosticDisposition.ADAPTED,
        "record model variables, constraints, backend timing, and optional process RSS; memo-cache entries do not apply",
    ),
    MILPDiagnosticCompatibility(
        "exact-memo-cache",
        DiagnosticDisposition.INAPPLICABLE,
        "MILP uses a centralized mathematical program and has no Exact recursive memo table",
    ),
    MILPDiagnosticCompatibility(
        "learning-footprint",
        DiagnosticDisposition.INAPPLICABLE,
        "MILP observations are telemetry only and there is no belief-update payload",
    ),
    MILPDiagnosticCompatibility(
        "belief-and-equilibrium",
        DiagnosticDisposition.INAPPLICABLE,
        "clairvoyant MILP performs neither posterior learning nor equilibrium iteration",
    ),
    MILPDiagnosticCompatibility(
        "hybrid-candidates-rollouts-samples",
        DiagnosticDisposition.INAPPLICABLE,
        "MILP has no pruning, lookahead, Monte Carlo, or bandit policy state",
    ),
)


@dataclass(frozen=True)
class MILPDiagnosticOptions:
    controller_timing: bool = False
    http_route_timing: bool = False
    payload_counts: bool = False
    solver_resource: bool = False

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, bool)
            for value in (
                self.controller_timing,
                self.http_route_timing,
                self.payload_counts,
                self.solver_resource,
            )
        ):
            raise MILPContractError("diagnostic options must be boolean")


def diagnostic_compatibility_manifest() -> tuple[MILPDiagnosticCompatibility, ...]:
    return MILP_DIAGNOSTIC_COMPATIBILITY


def _record(name: str, disposition: DiagnosticDisposition, reason: str, **values):
    return MILPTraceDiagnostic(
        name=name,
        disposition=disposition.value,
        reason=reason,
        values=tuple(sorted(values.items())),
    )


def collect_milp_diagnostics(
    result: MILPSlotResult | MILPKernelSlotResult,
    options: MILPDiagnosticOptions,
    *,
    peak_rss_bytes: int | None = None,
) -> tuple[MILPTraceDiagnostic, ...]:
    """Collect only explicitly enabled diagnostics from an already completed slot.

    The collector cannot change placement, traffic, RNG state, or metrics.  An
    external process-RSS sample may be supplied because the slot result does
    not pretend to own a solver-only memory measurement.
    """

    if not isinstance(options, MILPDiagnosticOptions):
        raise MILPContractError("options must be MILPDiagnosticOptions")
    if peak_rss_bytes is not None and (
        isinstance(peak_rss_bytes, bool)
        or not isinstance(peak_rss_bytes, Integral)
        or peak_rss_bytes < 0
    ):
        raise MILPContractError("peak_rss_bytes must be a nonnegative integer")
    kernel = isinstance(result, MILPKernelSlotResult)
    metrics = result.metrics.common if kernel else result.metrics
    records: list[MILPTraceDiagnostic] = []
    if options.controller_timing:
        records.append(
            _record(
                "controller-timing",
                DiagnosticDisposition.ADAPTED,
                "MILP centralized timing phases",
                model_build_seconds=metrics.model_build_seconds,
                solve_seconds=metrics.solver_seconds,
                execution_seconds=metrics.simulation_seconds,
                total_seconds=metrics.total_slot_seconds,
            )
        )
    if options.http_route_timing:
        if not kernel:
            raise MILPContractError("HTTP route diagnostics require a Kernel result")
        request_total = sum(item.request_latency_ms for item in result.observations)
        transport_total = sum(item.transport_overhead_ms for item in result.observations)
        records.append(
            _record(
                "http-route-timing",
                DiagnosticDisposition.COMPATIBLE,
                "selected Kernel observation timing only",
                observation_request_latency_ms=request_total,
                observation_transport_overhead_ms=transport_total,
                measured_pair_request_latency_ms=sum(
                    item.request_latency_ms for item in result.measured_pairs
                ),
            )
        )
    if options.payload_counts:
        records.append(
            _record(
                "payload",
                DiagnosticDisposition.ADAPTED,
                "logical selected-record counts; not HTTP or wire bytes",
                observations=len(result.observations),
                measured_pairs=len(result.measured_pairs),
                routes=len(result.placement.actions),
            )
        )
    if options.solver_resource:
        provenance = result.solver_result.provenance
        values = {
            "constraint_count": provenance.constraint_count,
            "peak_rss_bytes": peak_rss_bytes,
            "variable_count": provenance.variable_count,
        }
        records.append(
            _record(
                "solver-resource",
                DiagnosticDisposition.ADAPTED,
                "MILP model counts and optional process RSS; no memo-cache count",
                **values,
            )
        )
    return tuple(records)
