"""Stateful side-effect-free pure-Python Greedy slot and experiment runner."""

from __future__ import annotations

import time
from numbers import Integral
from typing import Callable

from .learning import apply_selected_learning
from .metrics import compute_slot_metrics
from .policy import GreedyPolicy
from .simulation import (
    GreedySlotSimulationAdapter,
    InProcessGreedySimulationAdapter,
    resolve_flow_order,
)
from .slot_contracts import (
    GREEDY_EXPERIMENT_STOP_EQUILIBRIUM,
    GREEDY_EXPERIMENT_STOP_MAX_ITERATIONS,
    GREEDY_SLOT_CONTRACT_VERSION,
    GreedyExperimentResult,
    GreedyPlacement,
    GreedySimulationResult,
    GreedySlotInput,
    GreedySlotResult,
    GreedySlotTimings,
)


MonotonicClock = Callable[[], float]


def _validate_simulation_result(
    *,
    result: GreedySimulationResult,
    actions_by_flow,
    final_loads,
) -> None:
    expected_observations = {
        (flow_id, identity)
        for flow_id, action in actions_by_flow.items()
        for identity in action.choices
    }
    actual_observations = {
        (observation.flow_id, observation.identity)
        for observation in result.observations
    }
    if len(result.observations) != len(expected_observations):
        raise RuntimeError(
            "simulation returned an incomplete or duplicate selected observation set"
        )
    if actual_observations != expected_observations:
        raise RuntimeError(
            "simulation observations do not exactly match committed selections"
        )
    for observation in result.observations:
        if observation.assigned_load != final_loads.load_for(observation.identity):
            raise RuntimeError(
                "simulation observation does not use final assigned load"
            )

    expected_flows = set(actions_by_flow)
    actual_pair_flows = {pair.flow_id for pair in result.measured_pairs}
    if len(result.measured_pairs) != len(expected_flows):
        raise RuntimeError(
            "simulation must return exactly one measured pair per committed flow"
        )
    if actual_pair_flows != expected_flows:
        raise RuntimeError(
            "simulation measured-pair records do not cover committed flows"
        )
    for pair in result.measured_pairs:
        try:
            action = actions_by_flow[pair.flow_id]
        except KeyError as error:
            raise RuntimeError("simulation pair refers to an uncommitted flow") from error
        if (pair.source, pair.target) != action.choices:
            raise RuntimeError(
                "simulation measured pair does not match the committed action"
            )


def run_greedy_slot(
    slot_input: GreedySlotInput,
    *,
    policy: GreedyPolicy | None = None,
    simulation_adapter: GreedySlotSimulationAdapter | None = None,
    clock: MonotonicClock = time.perf_counter,
    use_cache: bool = True,
) -> GreedySlotResult:
    """Calculate one slot once: place, observe, learn, validate, and measure."""

    if not isinstance(slot_input, GreedySlotInput):
        raise TypeError("slot_input must be GreedySlotInput")
    policy = policy or GreedyPolicy(slot_input.configuration)
    if not isinstance(policy, GreedyPolicy):
        raise TypeError("policy must be GreedyPolicy")
    if policy.configuration != slot_input.configuration:
        raise ValueError("policy configuration does not match the slot input")
    adapter = simulation_adapter or InProcessGreedySimulationAdapter()

    started_at = float(clock())
    flow_order, flow_order_scheme, flow_order_seed = resolve_flow_order(
        num_flows=slot_input.configuration.num_flows,
        root_seed=slot_input.root_seed,
        slot_id=slot_input.slot_id,
        explicit_flow_order=slot_input.flow_order,
    )
    policy_result = policy.place(
        flow_order=flow_order,
        replica_states=slot_input.public_replicas,
        use_cache=use_cache,
    )
    placements = tuple(
        GreedyPlacement(position, decision)
        for position, decision in enumerate(policy_result.decisions, start=1)
    )
    placed_at = float(clock())

    actions_by_flow = {
        placement.flow_id: placement.action
        for placement in placements
    }
    simulation_result = adapter.execute(
        experiment_id=slot_input.experiment_id,
        root_seed=slot_input.root_seed,
        slot_id=slot_input.slot_id,
        actions_by_flow=actions_by_flow,
        final_loads=policy_result.final_loads,
        replica_profiles=slot_input.replica_profile_by_identity,
        measured_pair_latency_ms=slot_input.measured_pair_latency_ms,
    )
    if not isinstance(simulation_result, GreedySimulationResult):
        raise TypeError("simulation adapter must return GreedySimulationResult")
    _validate_simulation_result(
        result=simulation_result,
        actions_by_flow=actions_by_flow,
        final_loads=policy_result.final_loads,
    )
    beliefs_before, beliefs_after = apply_selected_learning(
        slot_input.public_replicas,
        simulation_result.observations,
    )
    metrics = compute_slot_metrics(
        policy_result=policy_result,
        beliefs_before=beliefs_before.mapping,
        beliefs_after=beliefs_after.mapping,
        observations=simulation_result.observations,
        measured_pairs=simulation_result.measured_pairs,
    )
    finished_at = float(clock())
    if not started_at <= placed_at <= finished_at:
        raise ValueError("injected clock must be monotonic within a slot")
    timings = GreedySlotTimings(
        placement_seconds=placed_at - started_at,
        feedback_validation_seconds=finished_at - placed_at,
        total_seconds=finished_at - started_at,
    )
    return GreedySlotResult(
        contract_version=GREEDY_SLOT_CONTRACT_VERSION,
        configuration=slot_input.configuration,
        experiment_id=slot_input.experiment_id,
        slot_id=slot_input.slot_id,
        root_seed=slot_input.root_seed,
        profile_seed=slot_input.profile_seed,
        profile_fingerprint=slot_input.profile_fingerprint,
        flow_order_seed_scheme=flow_order_scheme,
        flow_order_seed=flow_order_seed,
        flow_order=flow_order,
        policy_result=policy_result,
        placements=placements,
        observations=simulation_result.observations,
        measured_pairs=simulation_result.measured_pairs,
        beliefs_before=beliefs_before,
        beliefs_after=beliefs_after,
        metrics=metrics,
        timings=timings,
    )


def run_greedy_experiment(
    initial_slot_input: GreedySlotInput,
    *,
    max_iterations: int,
    policy: GreedyPolicy | None = None,
    simulation_adapter: GreedySlotSimulationAdapter | None = None,
    clock: MonotonicClock = time.perf_counter,
    use_cache: bool = True,
) -> GreedyExperimentResult:
    """Run exactly one finite experiment, retaining beliefs between slots."""

    if isinstance(max_iterations, bool) or not isinstance(max_iterations, Integral):
        raise TypeError("max_iterations must be an integer")
    if max_iterations < 1:
        raise ValueError("max_iterations must be positive")
    if not isinstance(initial_slot_input, GreedySlotInput):
        raise TypeError("initial_slot_input must be GreedySlotInput")
    policy = policy or GreedyPolicy(initial_slot_input.configuration)
    if policy.configuration != initial_slot_input.configuration:
        raise ValueError("policy configuration does not match the experiment input")
    adapter = simulation_adapter or InProcessGreedySimulationAdapter()

    slots = []
    current = initial_slot_input
    for _iteration in range(1, int(max_iterations) + 1):
        slot = run_greedy_slot(
            current,
            policy=policy,
            simulation_adapter=adapter,
            clock=clock,
            use_cache=use_cache,
        )
        slots.append(slot)
        if slot.metrics.equilibrium:
            return GreedyExperimentResult(
                experiment_id=initial_slot_input.experiment_id,
                max_iterations=int(max_iterations),
                slots=tuple(slots),
                stop_reason=GREEDY_EXPERIMENT_STOP_EQUILIBRIUM,
            )
        current = current.with_beliefs(slot.beliefs_after.mapping)

    return GreedyExperimentResult(
        experiment_id=initial_slot_input.experiment_id,
        max_iterations=int(max_iterations),
        slots=tuple(slots),
        stop_reason=GREEDY_EXPERIMENT_STOP_MAX_ITERATIONS,
    )
