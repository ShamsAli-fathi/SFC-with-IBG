from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence


@dataclass(frozen=True)
class Observation:
    """One selected-replica observation returned to the learning core."""

    stage: int
    flow_id: int
    replica_id: int
    congestion: int
    signal: int
    likelihood: tuple
    measured_latency_ms: float | None = None

    def __post_init__(self):
        if self.stage < 1:
            raise ValueError("stage must be at least 1")
        if self.replica_id < 1:
            raise ValueError("replica_id must be at least 1")
        if self.congestion < 1:
            raise ValueError("congestion must be at least 1")
        if len(self.likelihood) != 4:
            raise ValueError("likelihood must contain the four legacy IBG states")


@dataclass
class StageExecution:
    embed_dict: dict
    assignments: dict


class ReplicaDiscovery(Protocol):
    def discover(self, stage: int, replica_list: Mapping) -> Mapping:
        """Return the replicas available to the solver for one stage."""


class TrafficExecutor(Protocol):
    def execute_stage(
        self,
        policy: Any,
        num_of_replicas: int,
        embed_dict: dict,
        flow_list: list,
    ) -> StageExecution:
        """Execute the selected stage policy for the logical flows."""


class ObservationCollector(Protocol):
    def collect(
        self,
        stage: int,
        assignments: Mapping,
        replica_list: Mapping,
    ) -> Sequence[Observation]:
        """Collect observations only from selected replicas."""


class ResultSink(Protocol):
    def record_slot(self, result: Any) -> None:
        """Store or publish one completed slot result."""


@dataclass(frozen=True)
class AdapterBundle:
    replica_discovery: ReplicaDiscovery
    traffic_executor: TrafficExecutor
    observation_collector: ObservationCollector
    result_sink: ResultSink
