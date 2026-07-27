import copy
import random

import numpy as np
import pytest

from header import Replica
from solver_resource import (
    SolverResourceMeter,
    validate_solver_resource_snapshot,
)
from runner import run_decoupled_slot


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
                gamma=0.2,
                state=((stage + replica_id - 2) % 4) + 1,
                capacity=2000,
            )
    return replicas


def sequence_reader(values):
    remaining = iter(values)
    return lambda: next(remaining)


def test_meter_records_current_rss_and_per_stage_cache_boundaries():
    meter = SolverResourceMeter(
        rss_reader=sequence_reader([100, 160, 140, 120]),
        sample_interval_seconds=None,
    )

    meter.begin_slot()
    meter.observe_rss()
    meter.record_stage_cache(1, 10, 0)
    meter.finish_slot()
    snapshot = meter.snapshot(expected_stages=1)

    assert snapshot["rss_bytes"] == {
        "before_admission": 100,
        "peak_during_slot": 160,
        "after_feedback": 120,
        "peak_incremental_working_memory": 60,
    }
    assert snapshot["exact_policy"] == {
        "peak_memo_entries": 10,
        "post_embedding_residual_entries": 0,
        "stages": [
            {
                "stage": 1,
                "peak_memo_entries": 10,
                "post_embedding_residual_entries": 0,
            }
        ],
    }


def test_validation_rejects_inconsistent_incremental_memory():
    snapshot = {
        "schema": "solver_resource_v1",
        "rss_bytes": {
            "before_admission": 100,
            "peak_during_slot": 150,
            "after_feedback": 120,
            "peak_incremental_working_memory": 49,
        },
        "exact_policy": {
            "peak_memo_entries": 10,
            "post_embedding_residual_entries": 0,
            "stages": [
                {
                    "stage": 1,
                    "peak_memo_entries": 10,
                    "post_embedding_residual_entries": 0,
                }
            ],
        },
    }

    with pytest.raises(ValueError, match="incremental working memory"):
        validate_solver_resource_snapshot(snapshot, expected_stages=1)


def test_opt_in_meter_records_exact_cache_without_changing_slot_results():
    seed = 3105
    baseline_replicas = make_replicas()
    measured_replicas = copy.deepcopy(baseline_replicas)
    random.seed(seed)
    np.random.seed(seed)
    baseline = run_decoupled_slot([1, 2, 3], baseline_replicas, 3, 2)
    assert baseline.solver_resource is None

    random.seed(seed)
    np.random.seed(seed)
    meter = SolverResourceMeter(
        rss_reader=lambda: 1000,
        sample_interval_seconds=None,
    )
    measured = run_decoupled_slot(
        [1, 2, 3],
        measured_replicas,
        3,
        2,
        solver_resource_diagnostics=True,
        solver_resource_meter=meter,
    )

    assert measured.assignments_by_stage == baseline.assignments_by_stage
    assert measured.aggregate_utility_total == baseline.aggregate_utility_total
    assert measured.sla_violations == baseline.sla_violations
    assert measured.solver_resource["rss_bytes"][
        "peak_incremental_working_memory"
    ] == 0
    assert [
        record["peak_memo_entries"]
        for record in measured.solver_resource["exact_policy"]["stages"]
    ] == [10, 10, 10]
    assert measured.solver_resource["exact_policy"][
        "post_embedding_residual_entries"
    ] == 0
