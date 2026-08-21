from concurrent.futures import Executor, ProcessPoolExecutor
from dataclasses import replace
from itertools import combinations, product
import multiprocessing
import os
import random
import time
from types import SimpleNamespace

import pytest

import IBG_Hybrid.kernel_controller as controller_module
from IBG_Hybrid import (
    GlobalLoadState,
    HYBRID_KERNEL_LOOKAHEAD_POOL_LIFECYCLE_VERSION,
    HYBRID_KERNEL_LOOKAHEAD_WORKERS,
    HybridConfiguration,
    HybridFlow,
    HybridPairValue,
    HybridPolicyParameters,
    HybridReplica,
    HybridSlotInput,
    ReplicaChoice,
    run_hybrid_slot,
)
from IBG_Hybrid.kernel_controller import HybridKernelControllerAdapter
from IBG_Hybrid.kernel_controller_config import (
    controller_input_document_from_mapping,
)


def _worker_pid(_value):
    time.sleep(0.03)
    return os.getpid()


def _choices(configuration):
    return tuple(
        ReplicaChoice(stage, replica)
        for stage in range(1, configuration.num_stages + 1)
        for replica in range(1, configuration.num_replicas + 1)
    )


def _pair_values(configuration, value):
    return tuple(
        HybridPairValue(
            ReplicaChoice(stage_a, replica_a),
            ReplicaChoice(stage_b, replica_b),
            value,
        )
        for stage_a, stage_b in combinations(
            range(1, configuration.num_stages + 1),
            2,
        )
        for replica_a, replica_b in product(
            range(1, configuration.num_replicas + 1),
            repeat=2,
        )
    )


def _slot_input(*, slot_id=1):
    configuration = HybridConfiguration(num_flows=4, num_replicas=2)
    beliefs = (
        (0.55, 0.20, 0.15, 0.10),
        (0.10, 0.45, 0.25, 0.20),
        (0.05, 0.15, 0.30, 0.50),
    )
    return HybridSlotInput(
        configuration=configuration,
        parameters=HybridPolicyParameters(
            candidates_per_stage=2,
            lookahead_future_flows=2,
        ),
        root_seed=2050,
        slot_id=slot_id,
        flows=tuple(HybridFlow(flow_id) for flow_id in range(1, 5)),
        replicas=tuple(
            HybridReplica(
                choice=choice,
                belief=beliefs[(choice.stage + choice.replica) % 3],
                ready=True,
                max_assigned_flows=4,
                hidden_state=((choice.stage + choice.replica - 2) % 4) + 1,
            )
            for choice in _choices(configuration)
        ),
        planning_pair_links=_pair_values(configuration, 0.25),
        simulated_pair_outcomes=_pair_values(configuration, 3.5),
        initial_loads=GlobalLoadState.empty(configuration),
    )


def _semantic_projection(result):
    return replace(
        result,
        metrics=replace(result.metrics, elapsed_seconds=0.0),
    )


def _controller_inputs():
    return controller_input_document_from_mapping(
        {
            "contract_version": "ibg-hybrid-kernel-controller-inputs-v1",
            "source_identity": "lookahead-pool-lifecycle-test-v1",
            "configuration": {
                "num_flows": 2,
                "num_stages": 3,
                "num_replicas": 1,
                "stage_budget": 2,
            },
            "admission": [
                {"stage": stage, "replica": 1, "max_assigned_flows": 2}
                for stage in (1, 2, 3)
            ],
            "planning_pair_links": [
                {
                    "source_stage": source,
                    "source_replica": 1,
                    "target_stage": target,
                    "target_replica": 1,
                    "latency_ms": 0.25,
                }
                for source, target in ((1, 2), (1, 3), (2, 3))
            ],
        }
    )


class FakeDiscovery:
    def __init__(self, configuration):
        self.snapshot = SimpleNamespace(
            configuration=configuration,
            replicas=tuple(
                SimpleNamespace(choice=choice)
                for choice in _choices(configuration)
            ),
        )
        self.close_calls = 0

    def wait_for_complete_ready(self, **kwargs):
        assert kwargs == {}
        return self.snapshot

    def close(self):
        self.close_calls += 1


class FakeFlowGenerator:
    def __init__(self):
        self.requests = []
        self.close_calls = 0

    def run_slot(self, request):
        self.requests.append(request)
        raise AssertionError("flow generator should not run in this test")

    def close(self):
        self.close_calls += 1


class FailingExecutor(Executor):
    def __init__(self):
        self.map_calls = 0
        self.shutdown_calls = []

    def map(self, function, *iterables, timeout=None, chunksize=1):
        del function, iterables, timeout, chunksize
        self.map_calls += 1
        raise RuntimeError("synthetic lookahead worker failure")

    def shutdown(self, wait=True, *, cancel_futures=False):
        self.shutdown_calls.append((wait, cancel_futures))


class RecordingExecutor(Executor):
    def __init__(self, delegate):
        self.delegate = delegate
        self.map_calls = 0

    def map(self, function, *iterables, timeout=None, chunksize=1):
        self.map_calls += 1
        return self.delegate.map(
            function,
            *iterables,
            timeout=timeout,
            chunksize=chunksize,
        )


def test_full_slot_two_process_lookahead_matches_serial_oracle_exactly():
    slot_input = _slot_input()
    global_random_state = random.getstate()
    serial = run_hybrid_slot(slot_input)
    baseline_children = {child.pid for child in multiprocessing.active_children()}

    with ProcessPoolExecutor(
        max_workers=HYBRID_KERNEL_LOOKAHEAD_WORKERS,
        mp_context=multiprocessing.get_context("spawn"),
    ) as process_executor:
        executor = RecordingExecutor(process_executor)
        parallel = run_hybrid_slot(
            slot_input,
            lookahead_executor=executor,
        )

    assert _semantic_projection(parallel) == _semantic_projection(serial)
    assert executor.map_calls == slot_input.configuration.num_flows
    assert random.getstate() == global_random_state
    assert {
        child.pid for child in multiprocessing.active_children()
    } <= baseline_children


def test_controller_reuses_same_spawn_workers_across_flows_and_slots(
    monkeypatch,
):
    inputs = _controller_inputs()
    discovery = FakeDiscovery(inputs.configuration)
    generator = FakeFlowGenerator()
    uniform = {
        item.choice: (0.25, 0.25, 0.25, 0.25)
        for item in inputs.admission
    }
    executor_ids = []
    worker_pid_sets = []
    observed_beliefs = []

    def fake_run(slot_input, **kwargs):
        executor = kwargs["lookahead_executor"]
        executor_ids.append(id(executor))
        worker_pid_sets.append(
            tuple(sorted(set(executor.map(_worker_pid, range(8)))))
        )
        observed_beliefs.append(slot_input.beliefs)
        kwargs["simulation_adapter"].requests_submitted = 1
        next_belief = (
            (0.40, 0.30, 0.20, 0.10)
            if slot_input.slot_id == 1
            else (0.45, 0.25, 0.20, 0.10)
        )
        return SimpleNamespace(
            beliefs_after={choice: next_belief for choice in slot_input.beliefs}
        )

    monkeypatch.setattr(controller_module, "run_hybrid_slot", fake_run)
    baseline_children = {child.pid for child in multiprocessing.active_children()}
    controller = HybridKernelControllerAdapter(
        controller_inputs=inputs,
        discovery=discovery,
        flow_generator=generator,
        initial_beliefs=uniform,
    )
    owned_executor = controller.lookahead_executor
    try:
        first = controller.run_slot(1)
        children_after_first = {
            child.pid for child in multiprocessing.active_children()
        } - baseline_children
        second = controller.run_slot(2)
        children_after_second = {
            child.pid for child in multiprocessing.active_children()
        } - baseline_children

        assert first.lookahead_process_workers == 2
        assert second.lookahead_process_workers == 2
        assert (
            first.lookahead_pool_lifecycle_version
            == second.lookahead_pool_lifecycle_version
            == HYBRID_KERNEL_LOOKAHEAD_POOL_LIFECYCLE_VERSION
        )
        assert executor_ids == [id(owned_executor), id(owned_executor)]
        assert len(worker_pid_sets[0]) == len(worker_pid_sets[1]) == 2
        assert worker_pid_sets[0] == worker_pid_sets[1]
        assert children_after_first == children_after_second == set(
            worker_pid_sets[0]
        )
        assert observed_beliefs[0] == uniform
        assert observed_beliefs[1] == first.slot.beliefs_after
        assert generator.requests == []
    finally:
        controller.close()

    assert controller.lookahead_executor is None
    assert discovery.close_calls == generator.close_calls == 1
    assert {
        child.pid for child in multiprocessing.active_children()
    } <= baseline_children


def test_worker_failure_reaches_caller_and_controller_shutdown_closes_pool():
    inputs = _controller_inputs()
    discovery = FakeDiscovery(inputs.configuration)
    generator = FakeFlowGenerator()
    executor = FailingExecutor()
    uniform = {
        item.choice: (0.25, 0.25, 0.25, 0.25)
        for item in inputs.admission
    }
    controller = HybridKernelControllerAdapter(
        controller_inputs=inputs,
        discovery=discovery,
        flow_generator=generator,
        initial_beliefs=uniform,
        lookahead_executor=executor,
    )

    try:
        with pytest.raises(
            RuntimeError,
            match="synthetic lookahead worker failure",
        ):
            controller.run_slot(1)
    finally:
        controller.close()

    assert executor.map_calls == 1
    assert executor.shutdown_calls == [(True, True)]
    assert generator.requests == []
    assert controller.beliefs == uniform
    assert discovery.close_calls == generator.close_calls == 1


def test_manual_monte_carlo_controller_owns_no_lookahead_pool(monkeypatch):
    inputs = _controller_inputs()
    discovery = FakeDiscovery(inputs.configuration)
    generator = FakeFlowGenerator()
    uniform = {
        item.choice: (0.25, 0.25, 0.25, 0.25)
        for item in inputs.admission
    }
    captured = {}

    def fake_run(slot_input, **kwargs):
        captured.update(kwargs)
        kwargs["simulation_adapter"].requests_submitted = 1
        return SimpleNamespace(beliefs_after=slot_input.beliefs)

    monkeypatch.setattr(controller_module, "run_hybrid_slot", fake_run)
    controller = HybridKernelControllerAdapter(
        controller_inputs=inputs,
        discovery=discovery,
        flow_generator=generator,
        initial_beliefs=uniform,
        policy_mode="mc",
        mc_workers=2,
    )
    try:
        outcome = controller.run_slot(1)
    finally:
        controller.close()

    assert captured["lookahead_executor"] is None
    assert controller.lookahead_process_workers == 0
    assert outcome.lookahead_process_workers == 0
    assert outcome.lookahead_pool_lifecycle_version is None
