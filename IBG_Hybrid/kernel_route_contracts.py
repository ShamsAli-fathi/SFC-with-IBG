"""Immutable L=2 route contracts for Hybrid Kernel Infrastructure Phase 1.

The active Hybrid problem has three stages and selects exactly two of them.
These contracts describe only those two selected processor/forwarder hops and
their one measured directed pair.  The skipped stage has no representation in
the executable hop list or telemetry list.
"""

from __future__ import annotations

from collections import Counter
from math import isclose
from numbers import Integral
from typing import Mapping

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, model_validator

from IBG.datapath import KERNEL_DATAPATH_MODE, require_datapath_mode
from testbed.route_forwarder import PairwiseLinkTelemetry

from .contracts import HybridConfiguration, ReplicaChoice, TwoStageAction
from .kernel_infrastructure_contract import (
    HybridKernelContractError,
    HybridKernelDiscoverySnapshot,
)


HYBRID_KERNEL_ROUTE_CONTRACT_VERSION = "ibg-hybrid-two-selected-stage-route-v1"
HYBRID_KERNEL_ROUTE_EXECUTION_VERSION = "ibg-hybrid-kernel-route-execution-v1"


class _FrozenContractModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class HybridKernelHopTarget(_FrozenContractModel):
    stage: int = Field(ge=1, le=3)
    replica_id: int = Field(ge=1)
    url: AnyHttpUrl
    assigned_load: int = Field(ge=1)

    @property
    def choice(self) -> ReplicaChoice:
        return ReplicaChoice(self.stage, self.replica_id)


class HybridKernelFlowRoute(_FrozenContractModel):
    flow_id: int = Field(ge=1)
    hops: tuple[HybridKernelHopTarget, HybridKernelHopTarget]
    skipped_stage: int = Field(ge=1, le=3)

    @model_validator(mode="after")
    def validate_two_selected_stages(self):
        if len(self.hops) != 2:
            raise ValueError("a Hybrid Kernel route must contain exactly two hops")
        first, second = self.hops
        if first.stage >= second.stage:
            raise ValueError(
                "Hybrid Kernel route stages must be distinct and increasing"
            )
        skipped = {1, 2, 3} - {first.stage, second.stage}
        if skipped != {self.skipped_stage}:
            raise ValueError(
                "skipped_stage must be the stage absent from the two-hop route"
            )
        return self

    @property
    def action(self) -> TwoStageAction:
        return TwoStageAction(tuple(hop.choice for hop in self.hops))


class HybridKernelRunSlotRequest(_FrozenContractModel):
    contract_version: str = HYBRID_KERNEL_ROUTE_CONTRACT_VERSION
    datapath_mode: str = KERNEL_DATAPATH_MODE
    slot_id: int = Field(ge=1)
    routes: tuple[HybridKernelFlowRoute, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_complete_slot(self):
        if self.contract_version != HYBRID_KERNEL_ROUTE_CONTRACT_VERSION:
            raise ValueError("unexpected Hybrid two-hop route contract version")
        object.__setattr__(
            self,
            "datapath_mode",
            require_datapath_mode(self.datapath_mode, runtime=True),
        )
        flow_ids = tuple(route.flow_id for route in self.routes)
        if len(flow_ids) != len(set(flow_ids)):
            raise ValueError("Hybrid Kernel route flow IDs must be unique")
        if flow_ids != tuple(sorted(flow_ids)):
            raise ValueError("Hybrid Kernel routes must use canonical flow-ID order")

        load_by_choice = Counter(
            hop.choice for route in self.routes for hop in route.hops
        )
        endpoint_by_choice: dict[ReplicaChoice, str] = {}
        for route in self.routes:
            for hop in route.hops:
                if hop.assigned_load != load_by_choice[hop.choice]:
                    raise ValueError(
                        "route assigned_load values must equal complete-slot final loads"
                    )
                endpoint = str(hop.url)
                previous = endpoint_by_choice.setdefault(hop.choice, endpoint)
                if previous != endpoint:
                    raise ValueError(
                        "one selected Hybrid replica has inconsistent endpoints"
                    )
        return self

    @property
    def selected_assignment_count(self) -> int:
        return sum(len(route.hops) for route in self.routes)


class HybridKernelHopTelemetry(_FrozenContractModel):
    datapath_mode: str = KERNEL_DATAPATH_MODE
    slot_id: int = Field(ge=1)
    flow_id: int = Field(ge=1)
    stage: int = Field(ge=1, le=3)
    replica_id: int = Field(ge=1)
    pod_name: str = Field(min_length=1)
    endpoint: str = Field(min_length=1)
    concurrency: int = Field(ge=1)
    assigned_load: int = Field(ge=1)
    modeled_processing_latency_ms: float = Field(gt=0)
    physical_processing_latency_ms: float = Field(gt=0)
    observation_jitter_ms: float = Field(ge=0)
    learning_signal_ms: float = Field(gt=0)
    request_latency_ms: float = Field(ge=0)
    transport_overhead_ms: float = Field(ge=0)
    estimated_state: int = Field(ge=1, le=4)
    likelihood: tuple[float, float, float, float]

    @model_validator(mode="after")
    def validate_selected_observation(self):
        if not isclose(
            self.learning_signal_ms,
            self.physical_processing_latency_ms + self.observation_jitter_ms,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ValueError(
                "learning signal must equal physical latency plus observation jitter"
            )
        if any(value < 0 for value in self.likelihood) or not isclose(
            sum(self.likelihood),
            1.0,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ValueError("likelihood must contain four normalized values")
        return self

    @property
    def choice(self) -> ReplicaChoice:
        return ReplicaChoice(self.stage, self.replica_id)


class HybridKernelFlowTelemetry(_FrozenContractModel):
    flow_id: int = Field(ge=1)
    skipped_stage: int = Field(ge=1, le=3)
    hops: tuple[HybridKernelHopTelemetry, HybridKernelHopTelemetry]
    measured_pair: PairwiseLinkTelemetry
    ingress_request_latency_ms: float = Field(ge=0)
    ingress_overhead_ms: float = Field(ge=0)

    @model_validator(mode="after")
    def validate_selected_only_telemetry(self):
        if len(self.hops) != 2:
            raise ValueError("Hybrid flow telemetry must contain exactly two hops")
        first, second = self.hops
        if first.flow_id != self.flow_id or second.flow_id != self.flow_id:
            raise ValueError("Hybrid hop telemetry flow identity mismatch")
        if first.stage >= second.stage:
            raise ValueError("Hybrid telemetry stages must be distinct and increasing")
        if {1, 2, 3} - {first.stage, second.stage} != {self.skipped_stage}:
            raise ValueError("Hybrid telemetry skipped stage mismatch")
        pair = self.measured_pair
        if (
            pair.flow_id != self.flow_id
            or pair.source_stage != first.stage
            or pair.source_replica_id != first.replica_id
            or pair.source_pod_name != first.pod_name
            or pair.target_stage != second.stage
            or pair.target_replica_id != second.replica_id
            or pair.target_pod_name != second.pod_name
            or pair.target_endpoint != second.endpoint
        ):
            raise ValueError("Hybrid measured-pair telemetry identity mismatch")
        return self

    @property
    def selected_choices(self) -> tuple[ReplicaChoice, ReplicaChoice]:
        return tuple(hop.choice for hop in self.hops)

    @property
    def selected_learning_signals_ms(self) -> tuple[float, float]:
        return tuple(hop.learning_signal_ms for hop in self.hops)

    @property
    def selected_physical_processing_latency_ms(self) -> float:
        return sum(hop.physical_processing_latency_ms for hop in self.hops)


class HybridKernelRunSlotResponse(_FrozenContractModel):
    contract_version: str = HYBRID_KERNEL_ROUTE_CONTRACT_VERSION
    execution_version: str = HYBRID_KERNEL_ROUTE_EXECUTION_VERSION
    datapath_mode: str = KERNEL_DATAPATH_MODE
    slot_id: int = Field(ge=1)
    elapsed_ms: float = Field(ge=0)
    flows: tuple[HybridKernelFlowTelemetry, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_complete_response(self):
        if self.contract_version != HYBRID_KERNEL_ROUTE_CONTRACT_VERSION:
            raise ValueError("unexpected Hybrid two-hop response contract version")
        if self.execution_version != HYBRID_KERNEL_ROUTE_EXECUTION_VERSION:
            raise ValueError("unexpected Hybrid route-execution version")
        object.__setattr__(
            self,
            "datapath_mode",
            require_datapath_mode(self.datapath_mode, runtime=True),
        )
        flow_ids = tuple(flow.flow_id for flow in self.flows)
        if len(flow_ids) != len(set(flow_ids)):
            raise ValueError("Hybrid response flow IDs must be unique")
        if flow_ids != tuple(sorted(flow_ids)):
            raise ValueError("Hybrid response flows must use canonical flow-ID order")
        if any(
            hop.slot_id != self.slot_id or hop.datapath_mode != self.datapath_mode
            for flow in self.flows
            for hop in flow.hops
        ):
            raise ValueError("Hybrid response slot or datapath identity mismatch")
        return self

    @property
    def observation_count(self) -> int:
        return sum(len(flow.hops) for flow in self.flows)

    @property
    def measured_pair_count(self) -> int:
        return len(self.flows)


def build_hybrid_kernel_run_slot_request(
    *,
    slot_id: int,
    configuration: HybridConfiguration,
    actions_by_flow: Mapping[int, TwoStageAction],
    discovery: HybridKernelDiscoverySnapshot,
) -> HybridKernelRunSlotRequest:
    """Build executable routes only after a complete Hybrid placement exists."""

    if isinstance(slot_id, bool) or not isinstance(slot_id, Integral) or slot_id < 1:
        raise HybridKernelContractError("slot_id must be a positive integer")
    if not isinstance(configuration, HybridConfiguration):
        raise HybridKernelContractError("configuration must be HybridConfiguration")
    if discovery.configuration != configuration:
        raise HybridKernelContractError(
            "Ready discovery configuration must match route configuration"
        )
    if len(actions_by_flow) != configuration.num_flows:
        raise HybridKernelContractError(
            "complete Hybrid placement must contain every configured flow"
        )
    if any(
        isinstance(flow_id, bool)
        or not isinstance(flow_id, Integral)
        or flow_id < 1
        for flow_id in actions_by_flow
    ):
        raise HybridKernelContractError("flow IDs must be positive integers")
    for action in actions_by_flow.values():
        if not isinstance(action, TwoStageAction):
            raise HybridKernelContractError("placements must contain TwoStageAction values")
        action.validate_for(configuration)

    loads = Counter(
        choice
        for action in actions_by_flow.values()
        for choice in action.choices
    )
    endpoint_by_choice = discovery.replica_by_choice()
    routes = []
    for flow_id, action in sorted(actions_by_flow.items()):
        routes.append(
            HybridKernelFlowRoute(
                flow_id=int(flow_id),
                hops=tuple(
                    HybridKernelHopTarget(
                        stage=choice.stage,
                        replica_id=choice.replica,
                        url=endpoint_by_choice[choice].endpoint,
                        assigned_load=loads[choice],
                    )
                    for choice in action.choices
                ),
                skipped_stage=action.skipped_stage(configuration),
            )
        )
    return HybridKernelRunSlotRequest(slot_id=slot_id, routes=tuple(routes))
