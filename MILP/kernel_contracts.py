"""Versioned contracts for the coupled-MILP Kernel execution path.

The frozen Exact processor and public forwarder are reused unchanged.  These
contracts deliberately replace only Exact's contiguous, stage-1-first flow
generator boundary: every MILP route contains exactly two selected replicas
in increasing (but not necessarily contiguous) stage order.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isclose, isfinite
from numbers import Integral, Real

from pydantic import AnyHttpUrl, BaseModel, Field, model_validator

from IBG.datapath import KERNEL_DATAPATH_MODE, require_datapath_mode
from testbed.route_forwarder import PairwiseLinkTelemetry

from .contracts import MILPConfiguration, MILPPlacement, MILPProblemInput, MILPSolverResult
from .phase0_contract import MILPContractError, ReplicaKey
from .slot_contracts import MILPSlotMetrics


MILP_PHASE5_KERNEL_CONTRACT_VERSION = "milp-coupled-phase5-kernel-v1"
MILP_TWO_HOP_ROUTE_CONTRACT_VERSION = "milp-two-selected-stage-route-v1"
MILP_KERNEL_FLOW_GENERATOR_VERSION = "milp-kernel-flow-generator-v1"
MILP_KERNEL_TRAFFIC_ADAPTER_VERSION = "milp-kubernetes-traffic-adapter-v1"
MILP_KERNEL_CONTROLLER_VERSION = "milp-kubernetes-controller-v1"
MILP_KERNEL_PLANNING_LINK_DOCUMENT_VERSION = "milp-planning-links-v1"


def _positive_integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 1:
        raise MILPContractError(f"{field} must be a positive integer")
    return int(value)


def _nonnegative_integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 0:
        raise MILPContractError(f"{field} must be a nonnegative integer")
    return int(value)


def _finite(value: object, field: str, *, nonnegative: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise MILPContractError(f"{field} must be a finite real number")
    result = float(value)
    if not isfinite(result) or (nonnegative and result < 0.0):
        qualifier = "finite and nonnegative" if nonnegative else "finite"
        raise MILPContractError(f"{field} must be {qualifier}")
    return result


class MILPKernelHopTarget(BaseModel):
    stage: int = Field(ge=1)
    replica_id: int = Field(ge=1)
    url: AnyHttpUrl
    assigned_load: int = Field(ge=1)


class MILPKernelFlowRoute(BaseModel):
    flow_id: int = Field(ge=1)
    hops: tuple[MILPKernelHopTarget, MILPKernelHopTarget]

    @model_validator(mode="after")
    def validate_two_selected_stages(self):
        if len(self.hops) != 2:
            raise ValueError("a MILP Kernel route must contain exactly two hops")
        first, second = self.hops
        if first.stage >= second.stage:
            raise ValueError(
                "MILP Kernel route stages must be distinct and increasing"
            )
        return self


class MILPKernelRunSlotRequest(BaseModel):
    contract_version: str = MILP_TWO_HOP_ROUTE_CONTRACT_VERSION
    datapath_mode: str = KERNEL_DATAPATH_MODE
    slot_id: int = Field(ge=1)
    routes: tuple[MILPKernelFlowRoute, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_slot(self):
        if self.contract_version != MILP_TWO_HOP_ROUTE_CONTRACT_VERSION:
            raise ValueError("unexpected MILP two-hop route contract version")
        self.datapath_mode = require_datapath_mode(self.datapath_mode, runtime=True)
        flow_ids = tuple(route.flow_id for route in self.routes)
        if len(flow_ids) != len(set(flow_ids)):
            raise ValueError("flow IDs must be unique within a MILP slot")
        assigned_counts: dict[tuple[int, int], int] = {}
        for route in self.routes:
            for hop in route.hops:
                key = (hop.stage, hop.replica_id)
                assigned_counts[key] = assigned_counts.get(key, 0) + 1
        for route in self.routes:
            for hop in route.hops:
                if hop.assigned_load != assigned_counts[(hop.stage, hop.replica_id)]:
                    raise ValueError(
                        "route assigned_load values must equal complete-slot final loads"
                    )
        return self


class MILPKernelHealthResponse(BaseModel):
    status: str
    datapath_mode: str
    route_contract_version: str
    flow_generator_version: str


class MILPKernelHopTelemetry(BaseModel):
    datapath_mode: str
    slot_id: int
    flow_id: int
    stage: int
    replica_id: int
    pod_name: str
    endpoint: str
    concurrency: int
    assigned_load: int
    modeled_processing_latency_ms: float
    processing_latency_ms: float
    observation_jitter_ms: float = Field(ge=0)
    signal_latency_ms: float
    request_latency_ms: float = Field(ge=0)
    transport_overhead_ms: float = Field(ge=0)
    state_estimate: int
    state_likelihood: tuple[float, float, float, float]


class MILPKernelFlowTelemetry(BaseModel):
    flow_id: int
    hops: tuple[MILPKernelHopTelemetry, MILPKernelHopTelemetry]
    measured_pair: PairwiseLinkTelemetry
    ingress_request_latency_ms: float = Field(ge=0)
    ingress_overhead_ms: float = Field(ge=0)


class MILPKernelRunSlotResponse(BaseModel):
    contract_version: str
    datapath_mode: str
    slot_id: int
    elapsed_ms: float = Field(ge=0)
    flows: tuple[MILPKernelFlowTelemetry, ...]

    @model_validator(mode="after")
    def validate_response_contract(self):
        if self.contract_version != MILP_TWO_HOP_ROUTE_CONTRACT_VERSION:
            raise ValueError("unexpected MILP two-hop response contract version")
        self.datapath_mode = require_datapath_mode(self.datapath_mode, runtime=True)
        flow_ids = tuple(flow.flow_id for flow in self.flows)
        if len(flow_ids) != len(set(flow_ids)):
            raise ValueError("MILP telemetry flow IDs must be unique")
        return self


@dataclass(frozen=True, order=True)
class MILPKernelReplicaEndpoint:
    key: ReplicaKey
    pod_name: str
    node_name: str | None
    endpoint: str
    ready: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.key, ReplicaKey):
            raise MILPContractError("endpoint key must be ReplicaKey")
        if not self.pod_name or not self.endpoint:
            raise MILPContractError("endpoint pod_name and endpoint must be nonempty")
        if not isinstance(self.ready, bool) or not self.ready:
            raise MILPContractError("MILP Kernel endpoints must be Ready")


@dataclass(frozen=True, order=True)
class MILPKernelSelectedObservation:
    flow_id: int
    key: ReplicaKey
    assigned_load: int
    physical_processing_latency_ms: float
    observation_jitter_ms: float
    noisy_signal_ms: float
    likelihood: tuple[float, float, float, float]
    estimated_state: int
    pod_name: str
    endpoint: str
    admitted_concurrency: int
    modeled_processing_latency_ms: float
    request_latency_ms: float
    transport_overhead_ms: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "flow_id", _positive_integer(self.flow_id, "flow_id"))
        object.__setattr__(
            self, "assigned_load", _positive_integer(self.assigned_load, "assigned_load")
        )
        object.__setattr__(
            self,
            "admitted_concurrency",
            _positive_integer(self.admitted_concurrency, "admitted_concurrency"),
        )
        for field in (
            "physical_processing_latency_ms",
            "observation_jitter_ms",
            "noisy_signal_ms",
            "modeled_processing_latency_ms",
            "request_latency_ms",
            "transport_overhead_ms",
        ):
            object.__setattr__(self, field, _finite(getattr(self, field), field, nonnegative=True))
        if self.physical_processing_latency_ms <= 0.0:
            raise MILPContractError("physical processing latency must be positive")
        if not isclose(
            self.noisy_signal_ms,
            self.physical_processing_latency_ms + self.observation_jitter_ms,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise MILPContractError(
                "noisy signal must equal physical latency plus observation jitter"
            )
        if len(self.likelihood) != 4 or any(
            not isfinite(float(value)) or value < 0.0 for value in self.likelihood
        ) or not isclose(sum(self.likelihood), 1.0, abs_tol=1e-9):
            raise MILPContractError("likelihood must contain four normalized values")
        if self.estimated_state not in (1, 2, 3, 4):
            raise MILPContractError("estimated_state must be one of 1, 2, 3, or 4")
        if not self.pod_name or not self.endpoint:
            raise MILPContractError("observation identity metadata must be nonempty")


@dataclass(frozen=True, order=True)
class MILPKernelMeasuredPairOutcome:
    flow_id: int
    source: ReplicaKey
    target: ReplicaKey
    latency_ms: float
    source_pod_name: str
    target_pod_name: str
    target_endpoint: str
    request_latency_ms: float
    callee_elapsed_ms: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "flow_id", _positive_integer(self.flow_id, "flow_id"))
        if self.source.stage >= self.target.stage:
            raise MILPContractError("measured pair must follow increasing stages")
        for field in ("latency_ms", "request_latency_ms", "callee_elapsed_ms"):
            object.__setattr__(self, field, _finite(getattr(self, field), field, nonnegative=True))
        if not self.source_pod_name or not self.target_pod_name or not self.target_endpoint:
            raise MILPContractError("measured-pair identity metadata must be nonempty")


@dataclass(frozen=True)
class MILPKernelTrafficResult:
    observations: tuple[MILPKernelSelectedObservation, ...]
    measured_pairs: tuple[MILPKernelMeasuredPairOutcome, ...]
    flow_generator_elapsed_ms: float

    def __post_init__(self) -> None:
        if not isinstance(self.observations, tuple) or any(
            not isinstance(item, MILPKernelSelectedObservation) for item in self.observations
        ):
            raise MILPContractError("Kernel observations must be an immutable tuple")
        if not isinstance(self.measured_pairs, tuple) or any(
            not isinstance(item, MILPKernelMeasuredPairOutcome) for item in self.measured_pairs
        ):
            raise MILPContractError("Kernel measured pairs must be an immutable tuple")
        object.__setattr__(
            self,
            "flow_generator_elapsed_ms",
            _finite(self.flow_generator_elapsed_ms, "flow_generator_elapsed_ms", nonnegative=True),
        )


@dataclass(frozen=True)
class MILPKernelSlotInput:
    problem: MILPProblemInput
    slot_id: int
    endpoints: tuple[MILPKernelReplicaEndpoint, ...]
    contract_version: str = MILP_PHASE5_KERNEL_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.problem, MILPProblemInput):
            raise MILPContractError("problem must be MILPProblemInput")
        object.__setattr__(self, "slot_id", _positive_integer(self.slot_id, "slot_id"))
        if self.contract_version != MILP_PHASE5_KERNEL_CONTRACT_VERSION:
            raise MILPContractError("unexpected Phase 5 Kernel contract version")
        if self.endpoints != tuple(sorted(self.endpoints, key=lambda item: item.key)):
            raise MILPContractError("endpoints must use canonical replica order")
        expected = set(self.problem.configuration.dimensions.replica_keys)
        actual = {item.key for item in self.endpoints}
        if len(actual) != len(self.endpoints) or actual != expected:
            raise MILPContractError("Ready endpoint coverage must match every configured replica")

    def endpoint_by_key(self) -> dict[ReplicaKey, MILPKernelReplicaEndpoint]:
        return {item.key: item for item in self.endpoints}


@dataclass(frozen=True)
class MILPKernelSlotMetrics:
    """Phase 3 metric policy projected onto real Kernel traffic timing."""

    common: MILPSlotMetrics
    traffic_seconds: float
    total_slot_seconds: float

    def __post_init__(self) -> None:
        if not isinstance(self.common, MILPSlotMetrics):
            raise MILPContractError("common must be MILPSlotMetrics")
        object.__setattr__(self, "traffic_seconds", _finite(self.traffic_seconds, "traffic_seconds", nonnegative=True))
        object.__setattr__(self, "total_slot_seconds", _finite(self.total_slot_seconds, "total_slot_seconds", nonnegative=True))
        if not isclose(self.common.simulation_seconds, self.traffic_seconds, abs_tol=1e-9):
            raise MILPContractError("common execution time must match Kernel traffic time")
        if not isclose(self.common.total_slot_seconds, self.total_slot_seconds, abs_tol=1e-9):
            raise MILPContractError("common total time must match Kernel total time")


@dataclass(frozen=True)
class MILPKernelSlotResult:
    configuration: MILPConfiguration
    slot_id: int
    solver_result: MILPSolverResult
    placement: MILPPlacement
    bypassed_stages_by_flow: tuple[tuple[int, tuple[int, ...]], ...]
    final_replica_loads: tuple[tuple[ReplicaKey, int], ...]
    endpoints: tuple[MILPKernelReplicaEndpoint, ...]
    observations: tuple[MILPKernelSelectedObservation, ...]
    measured_pairs: tuple[MILPKernelMeasuredPairOutcome, ...]
    metrics: MILPKernelSlotMetrics
    contract_version: str = MILP_PHASE5_KERNEL_CONTRACT_VERSION
    route_contract_version: str = MILP_TWO_HOP_ROUTE_CONTRACT_VERSION
    traffic_adapter_version: str = MILP_KERNEL_TRAFFIC_ADAPTER_VERSION
    controller_version: str = MILP_KERNEL_CONTROLLER_VERSION

    def __post_init__(self) -> None:
        dimensions = self.configuration.dimensions
        if self.contract_version != MILP_PHASE5_KERNEL_CONTRACT_VERSION:
            raise MILPContractError("unexpected Kernel result contract version")
        if self.route_contract_version != MILP_TWO_HOP_ROUTE_CONTRACT_VERSION:
            raise MILPContractError("unexpected route contract version")
        if self.solver_result.placement != self.placement:
            raise MILPContractError("Kernel placement must match the solver incumbent")
        if self.final_replica_loads != self.placement.final_loads:
            raise MILPContractError("Kernel final loads must match the placement")
        if len(self.placement.actions) != dimensions.flow_count:
            raise MILPContractError("Kernel result must retain one route per flow")
        if len(self.observations) != dimensions.flow_count * 2:
            raise MILPContractError("Kernel result must retain two observations per flow")
        if len(self.measured_pairs) != dimensions.flow_count:
            raise MILPContractError("Kernel result must retain one measured pair per flow")
        if sum(load for _key, load in self.final_replica_loads) != dimensions.flow_count * 2:
            raise MILPContractError("Kernel result has an incomplete assignment count")
