import copy
import random
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from header import Replica
from learning import apply_observations
from ports import AdapterBundle, Observation
from result_sinks import CsvResultSink
from runner import run_decoupled_slot
from simulation_adapters import (
    MemoryResultSink,
    NullResultSink,
    SimulationObservationCollector,
    SimulationReplicaDiscovery,
    SimulationTrafficExecutor,
    make_simulation_adapters,
)


def make_replicas():
    replicas = {}
    for stage in range(1, 4):
        for replica_id in range(1, 3):
            replicas[(stage, replica_id)] = Replica(
                stage=stage,
                replica=replica_id,
                belief=[0.25, 0.25, 0.25, 0.25],
                delay=25,
                cost=1,
                gamma=0.2 if replica_id == 1 else 0.3,
                state=4 if replica_id == 1 else 2,
                capacity=2000 if replica_id == 1 else 5000,
            )
    return replicas


def assert_slot_results_match(left, right):
    assert left.datapath_mode == right.datapath_mode
    assert left.embed_dict == right.embed_dict
    assert left.assignments_by_stage == right.assignments_by_stage
    assert left.aggregate_utility_total == right.aggregate_utility_total
    assert left.aggregate_utility_per_flow == right.aggregate_utility_per_flow
    assert left.sla_violations == right.sla_violations
    assert left.jain_fairness == right.jain_fairness
    assert left.equilibrium == right.equilibrium

    for stage in range(1, 4):
        np.testing.assert_allclose(
            left.utility_grids[stage].to_numpy(),
            right.utility_grids[stage].to_numpy(),
        )


def test_explicit_simulation_adapters_match_default_runner():
    default_replicas = make_replicas()
    random.seed(2050)
    np.random.seed(2050)
    default_result = run_decoupled_slot(
        [1, 2, 3],
        default_replicas,
        num_of_stages=3,
        num_of_replicas=2,
    )

    adapted_replicas = make_replicas()
    result_sink = MemoryResultSink()
    random.seed(2050)
    np.random.seed(2050)
    adapted_result = run_decoupled_slot(
        [1, 2, 3],
        adapted_replicas,
        num_of_stages=3,
        num_of_replicas=2,
        adapters=make_simulation_adapters(result_sink),
    )

    assert_slot_results_match(adapted_result, default_result)
    assert result_sink.results == [adapted_result]
    for key in adapted_replicas:
        np.testing.assert_allclose(
            adapted_replicas[key].belief,
            default_replicas[key].belief,
        )


def test_collected_latency_observations_drive_belief_update():
    assignments = {1: 1, 2: 1, 3: 2}
    adapted_replicas = make_replicas()
    beliefs_before = {
        key: replica.belief.copy() for key, replica in adapted_replicas.items()
    }

    np.random.seed(99)
    observations = SimulationObservationCollector().collect(
        1,
        assignments,
        adapted_replicas,
    )
    apply_observations(observations, adapted_replicas)

    assert [observation.flow_id for observation in observations] == [1, 2, 3]
    assert all(
        observation.signal
        == pytest.approx(
            observation.measured_latency_ms
            + observation.observation_jitter_ms
        )
        for observation in observations
    )
    assert all(
        observation.observation_jitter_ms >= 0
        for observation in observations
    )
    assert adapted_replicas[(1, 1)].belief != beliefs_before[(1, 1)]
    assert adapted_replicas[(1, 2)].belief != beliefs_before[(1, 2)]
    assert adapted_replicas[(2, 1)].belief == beliefs_before[(2, 1)]


def test_discovery_is_stage_scoped_and_preserves_stable_ids():
    discovered = SimulationReplicaDiscovery().discover(2, make_replicas())

    assert list(discovered) == [(2, 1), (2, 2)]


def test_observation_correlates_latency_and_estimated_state():
    observation = Observation(
        stage=1,
        flow_id=7,
        replica_id=2,
        congestion=3,
        signal=12.5,
        likelihood=(0.1, 0.2, 0.3, 0.4),
        measured_latency_ms=12.5,
        estimated_state=4,
    )

    assert observation.signal == 12.5
    assert observation.measured_latency_ms == 12.5
    assert observation.estimated_state == 4


def test_runner_fails_clearly_when_discovery_returns_no_replicas():
    class EmptyDiscovery:
        def discover(self, stage, replica_list):
            return {}

    adapters = AdapterBundle(
        replica_discovery=EmptyDiscovery(),
        traffic_executor=SimulationTrafficExecutor(),
        observation_collector=SimulationObservationCollector(),
        result_sink=NullResultSink(),
    )

    with pytest.raises(RuntimeError, match="no replicas discovered for stage 1"):
        run_decoupled_slot(
            [1, 2, 3],
            make_replicas(),
            num_of_stages=3,
            num_of_replicas=2,
            adapters=adapters,
        )


def test_csv_result_sink_uses_reference_report_layout(tmp_path):
    replicas = make_replicas()
    sink = CsvResultSink("phase2", replicas, output_dir=tmp_path)
    result = SimpleNamespace(
        elapsed_seconds=0.125,
        sla_violations=2,
        aggregate_utility_total=19.5,
        jain_fairness=0.99,
    )

    sink.record_slot(result)

    expected_values = {
        "time.csv": 0.125,
        "sla_violations.csv": 2,
        "aggregate_utility.csv": 19.5,
        "jain_index.csv": 0.99,
    }
    for filename, value in expected_values.items():
        frame = pd.read_csv(tmp_path / filename)
        assert frame.columns.tolist() == ["phase2"]
        assert frame.loc[0, "phase2"] == pytest.approx(value)

    beliefs = pd.read_csv(tmp_path / "replica_results.csv")
    assert len(beliefs) == 1
    assert len(beliefs.columns) == len(replicas)


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"stage": 0}, "stage"),
        ({"replica_id": 0}, "replica_id"),
        ({"congestion": 0}, "congestion"),
        ({"likelihood": (0.5, 0.5)}, "four IBG states"),
    ],
)
def test_observation_rejects_invalid_contract_values(changes, message):
    values = {
        "stage": 1,
        "flow_id": 1,
        "replica_id": 1,
        "congestion": 1,
        "signal": 4,
        "likelihood": (0.1, 0.2, 0.3, 0.4),
    }
    values.update(changes)

    with pytest.raises(ValueError, match=message):
        Observation(**values)
