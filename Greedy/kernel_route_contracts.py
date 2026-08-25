"""Immutable arbitrary-K, exactly-two-hop Greedy Kernel route contracts."""

from __future__ import annotations

from collections import Counter
from math import isclose
from numbers import Integral
from typing import Mapping

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, model_validator

from IBG.datapath import KERNEL_DATAPATH_MODE, require_datapath_mode

from .contracts import GreedyConfiguration, ReplicaIdentity, TwoStageAction
from .kernel_contracts import (
    GreedyKernelContractError,
    GreedyKernelDiscoverySnapshot,
)


GREEDY_KERNEL_ROUTE_CONTRACT_VERSION = "greedy-two-selected-stage-route-v1"
GREEDY_KERNEL_ROUTE_EXECUTION_VERSION = "greedy-kernel-route-execution-v1"


class _FrozenContractModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class GreedyKernelHopTarget(_FrozenContractModel):
    stage: int = Field(ge=1)
    replica_id: int = Field(ge=1)
    url: AnyHttpUrl
    assigned_load: int = Field(ge=1)
    route_position: int = Field(ge=1, le=2)
    next_stage: int | None = Field(default=None, ge=1)
    next_replica_id: int | None = Field(default=None, ge=1)
    next_url: AnyHttpUrl | None = None

    @model_validator(mode="after")
    def validate_next_hop_shape(self):
        next_values = (self.next_stage, self.next_replica_id, self.next_url)
        if self.route_position == 1:
            if any(value is None for value in next_values):
                raise ValueError("first route position requires a complete next hop")
            if self.next_stage <= self.stage:
                raise ValueError("next hop must use a strictly later stage")
        elif any(value is not None for value in next_values):
            raise ValueError("final route position cannot declare a next hop")
        return self

    @property
    def identity(self) -> ReplicaIdentity:
        return ReplicaIdentity(self.stage, self.replica_id)

    @property
    def next_identity(self) -> ReplicaIdentity | None:
        if self.next_stage is None:
            return None
        return ReplicaIdentity(self.next_stage, self.next_replica_id)


class GreedyKernelFlowRoute(_FrozenContractModel):
    flow_id: int = Field(ge=1)
    hops: tuple[GreedyKernelHopTarget, GreedyKernelHopTarget]
    bypassed_stages: tuple[int, ...]

    @model_validator(mode="after")
    def validate_two_selected_hops(self):
        if len(self.hops) != 2:
            raise ValueError("a Greedy Kernel route must contain exactly two hops")
        first, second = self.hops
        if first.stage >= second.stage:
            raise ValueError("route stages must be distinct and increasing")
        if (first.route_position, second.route_position) != (1, 2):
            raise ValueError("route positions must be exactly 1 then 2")
        if (
            first.next_identity != second.identity
            or str(first.next_url).rstrip("/") != str(second.url).rstrip("/")
        ):
            raise ValueError("first-hop next-hop correlation is inconsistent")
        bypasses = tuple(self.bypassed_stages)
        if bypasses != tuple(sorted(set(bypasses))):
            raise ValueError("bypassed stages must be unique and increasing")
        return self

    @property
    def action(self) -> TwoStageAction:
        return TwoStageAction(tuple(hop.identity for hop in self.hops))


class GreedyKernelRunSlotRequest(_FrozenContractModel):
    contract_version: str = GREEDY_KERNEL_ROUTE_CONTRACT_VERSION
    datapath_mode: str = KERNEL_DATAPATH_MODE
    slot_id: int = Field(ge=1)
    num_flows: int = Field(ge=1)
    num_stages: int = Field(ge=2)
    num_replicas: int = Field(ge=1)
    routes: tuple[GreedyKernelFlowRoute, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_complete_slot(self):
        if self.contract_version != GREEDY_KERNEL_ROUTE_CONTRACT_VERSION:
            raise ValueError("unexpected Greedy route contract version")
        object.__setattr__(
            self,
            "datapath_mode",
            require_datapath_mode(self.datapath_mode, runtime=True),
        )
        configuration = self.configuration
        flow_ids = tuple(route.flow_id for route in self.routes)
        if flow_ids != tuple(range(1, self.num_flows + 1)):
            raise ValueError("routes must cover configured flows in canonical order")
        final_loads = Counter(
            hop.identity for route in self.routes for hop in route.hops
        )
        endpoint_by_identity: dict[ReplicaIdentity, str] = {}
        for route in self.routes:
            route.action.validate_for(configuration)
            expected_bypasses = route.action.bypassed_stages(configuration)
            if route.bypassed_stages != expected_bypasses:
                raise ValueError("route bypasses must cover exactly K-2 stages")
            for hop in route.hops:
                if hop.assigned_load != final_loads[hop.identity]:
                    raise ValueError("assigned_load must equal complete-slot final load")
                endpoint = str(hop.url).rstrip("/")
                previous = endpoint_by_identity.setdefault(hop.identity, endpoint)
                if previous != endpoint:
                    raise ValueError("one selected replica has inconsistent endpoints")
        return self

    @property
    def configuration(self) -> GreedyConfiguration:
        return GreedyConfiguration(self.num_flows, self.num_stages, self.num_replicas)

    @property
    def selected_assignment_count(self) -> int:
        return 2 * len(self.routes)


class GreedyKernelHopTelemetry(_FrozenContractModel):
    datapath_mode: str = KERNEL_DATAPATH_MODE
    slot_id: int = Field(ge=1)
    flow_id: int = Field(ge=1)
    stage: int = Field(ge=1)
    replica_id: int = Field(ge=1)
    route_position: int = Field(ge=1, le=2)
    next_stage: int | None = Field(default=None, ge=1)
    next_replica_id: int | None = Field(default=None, ge=1)
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
            raise ValueError("learning signal must equal physical plus observation jitter")
        if any(value < 0 for value in self.likelihood) or not isclose(
            sum(self.likelihood),
            1.0,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ValueError("likelihood must contain four normalized values")
        if self.route_position == 1:
            if self.next_stage is None or self.next_replica_id is None:
                raise ValueError("first telemetry hop requires next-hop identity")
            if self.next_stage <= self.stage:
                raise ValueError("telemetry next hop must use a later stage")
        elif self.next_stage is not None or self.next_replica_id is not None:
            raise ValueError("final telemetry hop cannot name a next hop")
        return self

    @property
    def identity(self) -> ReplicaIdentity:
        return ReplicaIdentity(self.stage, self.replica_id)

    @property
    def next_identity(self) -> ReplicaIdentity | None:
        if self.next_stage is None:
            return None
        return ReplicaIdentity(self.next_stage, self.next_replica_id)


class GreedyKernelMeasuredPairTelemetry(_FrozenContractModel):
    slot_id: int = Field(ge=1)
    flow_id: int = Field(ge=1)
    source_stage: int = Field(ge=1)
    source_replica_id: int = Field(ge=1)
    source_pod_name: str = Field(min_length=1)
    target_stage: int = Field(ge=1)
    target_replica_id: int = Field(ge=1)
    target_pod_name: str = Field(min_length=1)
    target_endpoint: str = Field(min_length=1)
    request_latency_ms: float = Field(ge=0)
    callee_elapsed_ms: float = Field(ge=0)
    measured_pair_latency_ms: float = Field(ge=0)

    @property
    def source(self) -> ReplicaIdentity:
        return ReplicaIdentity(self.source_stage, self.source_replica_id)

    @property
    def target(self) -> ReplicaIdentity:
        return ReplicaIdentity(self.target_stage, self.target_replica_id)


class GreedyKernelFlowTelemetry(_FrozenContractModel):
    flow_id: int = Field(ge=1)
    bypassed_stages: tuple[int, ...]
    hops: tuple[GreedyKernelHopTelemetry, GreedyKernelHopTelemetry]
    measured_pair: GreedyKernelMeasuredPairTelemetry
    ingress_request_latency_ms: float = Field(ge=0)
    ingress_overhead_ms: float = Field(ge=0)

    @model_validator(mode="after")
    def validate_complete_selected_route(self):
        if len(self.hops) != 2:
            raise ValueError("flow telemetry must contain exactly two hops")
        first, second = self.hops
        if first.flow_id != self.flow_id or second.flow_id != self.flow_id:
            raise ValueError("hop telemetry flow identity mismatch")
        if (first.route_position, second.route_position) != (1, 2):
            raise ValueError("hop telemetry route-position mismatch")
        if first.next_identity != second.identity:
            raise ValueError("hop telemetry next-hop mismatch")
        pair = self.measured_pair
        if (
            pair.flow_id != self.flow_id
            or pair.source != first.identity
            or pair.target != second.identity
            or pair.source_pod_name != first.pod_name
            or pair.target_pod_name != second.pod_name
            or pair.target_endpoint.rstrip("/") != second.endpoint.rstrip("/")
        ):
            raise ValueError("measured selected-pair telemetry identity mismatch")
        if set(self.bypassed_stages) & {first.stage, second.stage}:
            raise ValueError("bypassed stage appeared in selected telemetry")
        return self


class GreedyKernelRunSlotResponse(_FrozenContractModel):
    contract_version: str = GREEDY_KERNEL_ROUTE_CONTRACT_VERSION
    execution_version: str = GREEDY_KERNEL_ROUTE_EXECUTION_VERSION
    datapath_mode: str = KERNEL_DATAPATH_MODE
    slot_id: int = Field(ge=1)
    elapsed_ms: float = Field(ge=0)
    flows: tuple[GreedyKernelFlowTelemetry, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_complete_response(self):
        if self.contract_version != GREEDY_KERNEL_ROUTE_CONTRACT_VERSION:
            raise ValueError("unexpected Greedy response contract version")
        if self.execution_version != GREEDY_KERNEL_ROUTE_EXECUTION_VERSION:
            raise ValueError("unexpected Greedy route execution version")
        object.__setattr__(
            self,
            "datapath_mode",
            require_datapath_mode(self.datapath_mode, runtime=True),
        )
        flow_ids = tuple(flow.flow_id for flow in self.flows)
        if len(flow_ids) != len(set(flow_ids)) or flow_ids != tuple(sorted(flow_ids)):
            raise ValueError("response flows must be unique and canonical")
        if any(
            hop.slot_id != self.slot_id or hop.datapath_mode != self.datapath_mode
            for flow in self.flows
            for hop in flow.hops
        ):
            raise ValueError("response slot or datapath identity mismatch")
        return self

    @property
    def observation_count(self) -> int:
        return 2 * len(self.flows)

    @property
    def measured_pair_count(self) -> int:
        return len(self.flows)


def build_greedy_kernel_run_slot_request(
    *,
    slot_id: int,
    configuration: GreedyConfiguration,
    actions_by_flow: Mapping[int, TwoStageAction],
    discovery: GreedyKernelDiscoverySnapshot,
) -> GreedyKernelRunSlotRequest:
    """Build only complete routes after all sequential placements commit."""

    if isinstance(slot_id, bool) or not isinstance(slot_id, Integral) or slot_id < 1:
        raise GreedyKernelContractError("slot_id must be a positive integer")
    if discovery.configuration != configuration:
        raise GreedyKernelContractError("discovery and route configuration must match")
    if set(actions_by_flow) != set(range(1, configuration.num_flows + 1)):
        raise GreedyKernelContractError("placement must cover every configured flow")
    for action in actions_by_flow.values():
        if not isinstance(action, TwoStageAction):
            raise GreedyKernelContractError("placements must contain TwoStageAction values")
        action.validate_for(configuration)
    loads = Counter(
        identity for action in actions_by_flow.values() for identity in action.choices
    )
    discovered = discovery.replica_by_identity()
    routes = []
    for flow_id, action in sorted(actions_by_flow.items()):
        first_identity, second_identity = action.choices
        first_endpoint = discovered[first_identity].endpoint
        second_endpoint = discovered[second_identity].endpoint
        routes.append(
            GreedyKernelFlowRoute(
                flow_id=flow_id,
                hops=(
                    GreedyKernelHopTarget(
                        stage=first_identity.stage,
                        replica_id=first_identity.replica,
                        url=first_endpoint,
                        assigned_load=loads[first_identity],
                        route_position=1,
                        next_stage=second_identity.stage,
                        next_replica_id=second_identity.replica,
                        next_url=second_endpoint,
                    ),
                    GreedyKernelHopTarget(
                        stage=second_identity.stage,
                        replica_id=second_identity.replica,
                        url=second_endpoint,
                        assigned_load=loads[second_identity],
                        route_position=2,
                    ),
                ),
                bypassed_stages=action.bypassed_stages(configuration),
            )
        )
    return GreedyKernelRunSlotRequest(
        slot_id=slot_id,
        num_flows=configuration.num_flows,
        num_stages=configuration.num_stages,
        num_replicas=configuration.num_replicas,
        routes=tuple(routes),
    )
