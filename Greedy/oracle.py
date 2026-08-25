"""Captured-input serial replay and transparent tiny/reference Greedy placement."""

from __future__ import annotations

from dataclasses import dataclass, replace
from itertools import combinations, product
from math import fsum
from typing import Sequence

from .contracts import (
    DecisionResult,
    GlobalLoadState,
    NoFeasibleActionError,
    PolicyResult,
    ReplicaIdentity,
    TwoStageAction,
)
from .expected_utility import expected_stage_utility_from_belief
from .runner import run_greedy_slot
from .slot_contracts import (
    GreedySimulationResult,
    GreedySlotInput,
    GreedySlotResult,
)


def solve_reference_policy(
    slot_input: GreedySlotInput,
    flow_order: Sequence[int],
) -> PolicyResult:
    """Transparent exhaustive immediate reference independent of GreedyPolicy."""

    configuration = slot_input.configuration
    order = tuple(flow_order)
    expected_flows = set(range(1, configuration.num_flows + 1))
    if len(order) != configuration.num_flows or set(order) != expected_flows:
        raise ValueError("flow_order must be a permutation of configured flows 1..N")
    states = slot_input.public_replica_by_identity
    identities = tuple(sorted(states))
    actions = tuple(
        sorted(
            TwoStageAction(
                (
                    ReplicaIdentity(stage_a, replica_a),
                    ReplicaIdentity(stage_b, replica_b),
                )
            )
            for stage_a, stage_b in combinations(configuration.stages, 2)
            for replica_a, replica_b in product(configuration.replica_ids, repeat=2)
        )
    )
    state = GlobalLoadState.empty(configuration, identities)
    decisions = []
    for flow_id in order:
        best_action = None
        best_utilities = None
        best_score = None
        feasible_actions = 0
        for action in actions:
            if not all(
                states[identity].ready
                and state.load_for(identity) + 1
                <= states[identity].max_assigned_flows
                for identity in action.choices
            ):
                continue
            feasible_actions += 1
            utilities = tuple(
                expected_stage_utility_from_belief(
                    states[identity].belief,
                    state.load_for(identity) + 1,
                )
                for identity in action.choices
            )
            score = fsum(utilities)
            if best_action is None or score > best_score:
                best_action = action
                best_utilities = utilities
                best_score = score
        if best_action is None:
            raise NoFeasibleActionError(flow_id, state, len(actions))
        next_state = state.apply(best_action)
        decisions.append(
            DecisionResult(
                flow_id=flow_id,
                action=best_action,
                bypassed_stages=best_action.bypassed_stages(configuration),
                stage_utilities=best_utilities,
                objective_value=best_score,
                state_before=state,
                state_after=next_state,
                evaluated_actions=len(actions),
                feasible_actions=feasible_actions,
            )
        )
        state = next_state
    return PolicyResult(configuration, order, tuple(decisions), state)


@dataclass(frozen=True)
class CapturedGreedySlot:
    slot_input: GreedySlotInput
    expected_result: GreedySlotResult
    simulation_result: GreedySimulationResult


@dataclass(frozen=True)
class GreedyReplayValidation:
    replayed_result: GreedySlotResult
    reference_policy_result: PolicyResult
    semantic_match: bool
    reference_policy_match: bool

    @property
    def matched(self) -> bool:
        return self.semantic_match and self.reference_policy_match


def capture_greedy_slot(
    slot_input: GreedySlotInput,
    result: GreedySlotResult,
) -> CapturedGreedySlot:
    if (
        result.configuration != slot_input.configuration
        or result.experiment_id != slot_input.experiment_id
        or result.slot_id != slot_input.slot_id
        or result.profile_fingerprint != slot_input.profile_fingerprint
    ):
        raise ValueError("result does not belong to the supplied slot input")
    return CapturedGreedySlot(
        slot_input=slot_input,
        expected_result=result,
        simulation_result=GreedySimulationResult(
            observations=result.observations,
            measured_pairs=result.measured_pairs,
        ),
    )


class _CapturedSimulationAdapter:
    def __init__(self, captured: GreedySimulationResult) -> None:
        self._captured = captured
        self.calls = 0

    def execute(self, **_kwargs) -> GreedySimulationResult:
        self.calls += 1
        return self._captured


def _semantic_projection(result: GreedySlotResult):
    return (
        result.configuration,
        result.experiment_id,
        result.slot_id,
        result.root_seed,
        result.profile_seed,
        result.profile_fingerprint,
        result.flow_order,
        result.policy_result,
        result.placements,
        result.observations,
        result.measured_pairs,
        result.beliefs_before,
        result.beliefs_after,
        result.metrics,
    )


def replay_captured_slot(capture: CapturedGreedySlot) -> GreedyReplayValidation:
    """Explicitly replay one captured slot without drawing stochastic inputs."""

    replay_input = replace(
        capture.slot_input,
        flow_order=capture.expected_result.flow_order,
    )
    reference = solve_reference_policy(
        replay_input,
        capture.expected_result.flow_order,
    )
    adapter = _CapturedSimulationAdapter(capture.simulation_result)
    replayed = run_greedy_slot(
        replay_input,
        simulation_adapter=adapter,
        clock=lambda: 0.0,
        use_cache=False,
    )
    if adapter.calls != 1:
        raise AssertionError("captured replay must consume the captured result once")
    validation = GreedyReplayValidation(
        replayed_result=replayed,
        reference_policy_result=reference,
        semantic_match=(
            _semantic_projection(replayed)
            == _semantic_projection(capture.expected_result)
        ),
        reference_policy_match=(replayed.policy_result == reference),
    )
    if not validation.matched:
        raise AssertionError("captured Greedy replay diverged from the slot result")
    return validation
