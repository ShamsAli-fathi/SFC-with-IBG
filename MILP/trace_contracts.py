"""Immutable JSON-safe trace boundary for MILP Phase 6 replay.

The trace keeps the clairvoyant true-state data inside the deliberately named
``private_planner_input`` section.  Observations never contain true state.
Serialization is explicit and in-memory; this module performs no file I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from math import isfinite
from numbers import Integral
from typing import Any

from .contracts import DirectedPlanningLink, MILPPlacement, MILPProblemInput, MILPSolverResult
from .kernel_contracts import (
    MILP_PHASE5_KERNEL_CONTRACT_VERSION,
    MILP_TWO_HOP_ROUTE_CONTRACT_VERSION,
    MILPKernelMeasuredPairOutcome,
    MILPKernelReplicaEndpoint,
    MILPKernelSelectedObservation,
    MILPKernelSlotResult,
)
from .model import MILP_PHASE2_MODEL_VERSION
from .phase0_contract import MILP_PHASE0_CONTRACT_VERSION, MILPContractError
from .scaling import MILP_PHASE4_SCALE_CONTRACT_VERSION
from .slot_contracts import (
    MILP_PHASE3_SLOT_CONTRACT_VERSION,
    MILPMeasuredPairOutcome,
    MILPSelectedObservation,
    MILPSlotMetrics,
    MILPSlotResult,
)
from .solver import MILP_PHASE2_SOLVER_VERSION
from .contracts import MILP_PHASE1_CONTRACT_VERSION


MILP_PHASE6_TRACE_CONTRACT_VERSION = "milp-coupled-phase6-trace-v1"


class MILPTraceSource(str, Enum):
    PURE = "pure-simulation"
    KERNEL = "kernel"


JSONScalar = str | int | float | bool | None
JSONValue = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]


def _json_safe(value: Any) -> JSONValue:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _json_safe(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise MILPContractError("JSON-safe mappings require string keys")
        return {key: _json_safe(item) for key, item in value.items()}
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise MILPContractError("JSON-safe trace cannot contain nonfinite values")
        return value
    raise MILPContractError(f"unsupported JSON-safe trace value: {type(value).__name__}")


@dataclass(frozen=True)
class MILPTraceVersions:
    phase0: str = MILP_PHASE0_CONTRACT_VERSION
    phase1: str = MILP_PHASE1_CONTRACT_VERSION
    phase2_model: str = MILP_PHASE2_MODEL_VERSION
    phase2_solver: str = MILP_PHASE2_SOLVER_VERSION
    phase3_slot: str = MILP_PHASE3_SLOT_CONTRACT_VERSION
    phase4_scale: str = MILP_PHASE4_SCALE_CONTRACT_VERSION
    phase5_kernel: str | None = None
    route: str | None = None
    phase6_trace: str = MILP_PHASE6_TRACE_CONTRACT_VERSION


@dataclass(frozen=True, order=True)
class MILPSelectedPlanningLink:
    flow_id: int
    link: DirectedPlanningLink

    def __post_init__(self) -> None:
        if isinstance(self.flow_id, bool) or not isinstance(self.flow_id, Integral) or self.flow_id < 1:
            raise MILPContractError("selected planning-link flow_id must be positive")
        if not isinstance(self.link, DirectedPlanningLink):
            raise MILPContractError("selected planning link must be DirectedPlanningLink")


@dataclass(frozen=True, order=True)
class MILPTraceDiagnostic:
    name: str
    disposition: str
    reason: str
    values: tuple[tuple[str, JSONScalar], ...] = ()

    def __post_init__(self) -> None:
        if not self.name or not self.disposition or not self.reason:
            raise MILPContractError("diagnostic name, disposition, and reason are required")
        if self.values != tuple(sorted(self.values)):
            raise MILPContractError("diagnostic values must use canonical key order")
        for key, value in self.values:
            if not key or not isinstance(key, str):
                raise MILPContractError("diagnostic keys must be nonempty strings")
            if isinstance(value, float) and not isfinite(value):
                raise MILPContractError("diagnostic values must be finite")
            if value is not None and not isinstance(value, (str, bool, int, float)):
                raise MILPContractError("diagnostic values must be JSON scalars")


TraceObservation = MILPSelectedObservation | MILPKernelSelectedObservation
TraceMeasuredPair = MILPMeasuredPairOutcome | MILPKernelMeasuredPairOutcome


@dataclass(frozen=True)
class MILPTrace:
    """Complete Phase 6 replay input.

    ``private_planner_input`` is the only trace section authorized to contain
    replica true states.  It is private planner/replay provenance, not
    observation telemetry.
    """

    source: MILPTraceSource
    versions: MILPTraceVersions
    private_planner_input: MILPProblemInput
    slot_id: int
    root_seed: int | None
    solver_result: MILPSolverResult
    placement: MILPPlacement
    bypassed_stages_by_flow: tuple[tuple[int, tuple[int, ...]], ...]
    final_replica_loads: tuple
    selected_planning_links: tuple[MILPSelectedPlanningLink, ...]
    kernel_endpoints: tuple[MILPKernelReplicaEndpoint, ...]
    observations: tuple[TraceObservation, ...]
    measured_pairs: tuple[TraceMeasuredPair, ...]
    metrics: MILPSlotMetrics
    diagnostics: tuple[MILPTraceDiagnostic, ...] = ()
    contract_version: str = MILP_PHASE6_TRACE_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.source, MILPTraceSource):
            raise MILPContractError("trace source must be MILPTraceSource")
        if not isinstance(self.versions, MILPTraceVersions):
            raise MILPContractError("trace versions must be MILPTraceVersions")
        if not isinstance(self.private_planner_input, MILPProblemInput):
            raise MILPContractError("private planner input must be MILPProblemInput")
        if isinstance(self.slot_id, bool) or not isinstance(self.slot_id, Integral) or self.slot_id < 1:
            raise MILPContractError("trace slot_id must be positive")
        if self.root_seed is not None and (
            isinstance(self.root_seed, bool)
            or not isinstance(self.root_seed, Integral)
            or self.root_seed < 0
        ):
            raise MILPContractError("trace root_seed must be nonnegative when present")
        if self.contract_version != MILP_PHASE6_TRACE_CONTRACT_VERSION:
            raise MILPContractError("unexpected Phase 6 trace contract version")
        if self.source is MILPTraceSource.PURE and self.root_seed is None:
            raise MILPContractError("pure traces require root-seed provenance")
        if self.source is MILPTraceSource.KERNEL and self.root_seed is not None:
            raise MILPContractError("Kernel traces must not fabricate simulation root seeds")
        for field_name in (
            "bypassed_stages_by_flow",
            "final_replica_loads",
            "selected_planning_links",
            "kernel_endpoints",
            "observations",
            "measured_pairs",
            "diagnostics",
        ):
            if not isinstance(getattr(self, field_name), tuple):
                raise MILPContractError(f"{field_name} must be an immutable tuple")

    def to_json_safe(self) -> dict[str, JSONValue]:
        value = _json_safe(self)
        if not isinstance(value, dict):  # pragma: no cover - structural invariant
            raise MILPContractError("trace serialization did not produce an object")
        return value


def _selected_planning_links(problem: MILPProblemInput, placement: MILPPlacement) -> tuple[MILPSelectedPlanningLink, ...]:
    links = {item.pair: item for item in problem.planning_links}
    return tuple(
        MILPSelectedPlanningLink(flow_id, links[action.directed_pair])
        for flow_id, action in placement.actions
    )


def build_milp_trace(
    problem: MILPProblemInput,
    result: MILPSlotResult | MILPKernelSlotResult,
    *,
    diagnostics: tuple[MILPTraceDiagnostic, ...] = (),
) -> MILPTrace:
    """Project a completed pure or Kernel slot into one replay contract."""

    if result.configuration != problem.configuration:
        raise MILPContractError("trace problem and result configurations differ")
    if isinstance(result, MILPSlotResult):
        source = MILPTraceSource.PURE
        versions = MILPTraceVersions()
        root_seed: int | None = result.root_seed
        endpoints: tuple[MILPKernelReplicaEndpoint, ...] = ()
        metrics = result.metrics
    elif isinstance(result, MILPKernelSlotResult):
        source = MILPTraceSource.KERNEL
        versions = MILPTraceVersions(
            phase5_kernel=MILP_PHASE5_KERNEL_CONTRACT_VERSION,
            route=MILP_TWO_HOP_ROUTE_CONTRACT_VERSION,
        )
        root_seed = None
        endpoints = result.endpoints
        metrics = result.metrics.common
    else:
        raise MILPContractError("trace result must be a pure or Kernel MILP slot result")
    return MILPTrace(
        source=source,
        versions=versions,
        private_planner_input=problem,
        slot_id=result.slot_id,
        root_seed=root_seed,
        solver_result=result.solver_result,
        placement=result.placement,
        bypassed_stages_by_flow=result.bypassed_stages_by_flow,
        final_replica_loads=result.final_replica_loads,
        selected_planning_links=_selected_planning_links(problem, result.placement),
        kernel_endpoints=endpoints,
        observations=result.observations,
        measured_pairs=result.measured_pairs,
        metrics=metrics,
        diagnostics=diagnostics,
    )
