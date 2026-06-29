from collections import Counter

from header import embedding
from ports import AdapterBundle, Observation, StageExecution


class SimulationReplicaDiscovery:
    def discover(self, stage, replica_list):
        return {
            key: replica
            for key, replica in replica_list.items()
            if replica.stage == stage
        }


class SimulationTrafficExecutor:
    def execute_stage(self, policy, num_of_replicas, embed_dict, flow_list):
        updated_embed, assignments = embedding(
            policy,
            num_of_replicas,
            embed_dict,
            flow_list,
        )
        return StageExecution(updated_embed, assignments)


class SimulationObservationCollector:
    def collect(self, stage, assignments, replica_list):
        congestion_by_replica = Counter(assignments.values())
        observations = []

        for flow_id, replica_id in assignments.items():
            if replica_id == 0:
                continue
            congestion = congestion_by_replica[replica_id]
            signal, likelihood = replica_list[(stage, replica_id)].tasting(congestion)
            observations.append(
                Observation(
                    stage=stage,
                    flow_id=flow_id,
                    replica_id=replica_id,
                    congestion=congestion,
                    signal=signal,
                    likelihood=tuple(likelihood),
                    measured_latency_ms=None,
                )
            )

        return observations


class NullResultSink:
    def record_slot(self, result):
        return None


class MemoryResultSink:
    def __init__(self):
        self.results = []

    def record_slot(self, result):
        self.results.append(result)


def make_simulation_adapters(result_sink=None):
    return AdapterBundle(
        replica_discovery=SimulationReplicaDiscovery(),
        traffic_executor=SimulationTrafficExecutor(),
        observation_collector=SimulationObservationCollector(),
        result_sink=result_sink or NullResultSink(),
    )
