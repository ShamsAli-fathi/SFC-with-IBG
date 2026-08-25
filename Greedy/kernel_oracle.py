"""Explicit captured Pure/Kernel semantic replay without HTTP or redraws."""

from __future__ import annotations

from dataclasses import dataclass

from .kernel_contracts import GreedyKernelControllerSlotResult
from .oracle import solve_reference_policy
from .runner import run_greedy_slot
from .slot_contracts import (
    GreedyReplicaProfile,
    GreedySimulationResult,
    GreedySlotInput,
    GreedySlotResult,
)


@dataclass(frozen=True)
class CapturedGreedyKernelSlot:
    outcome: GreedyKernelControllerSlotResult


@dataclass(frozen=True)
class GreedyPureKernelReplayValidation:
    replayed_pure_slot: GreedySlotResult
    reference_policy_result: object
    semantic_match: bool
    reference_policy_match: bool
    http_requests: int
    stochastic_redraws: int

    @property
    def matched(self) -> bool:
        return (
            self.semantic_match
            and self.reference_policy_match
            and self.http_requests == 0
            and self.stochastic_redraws == 0
        )


class _CapturedKernelSimulationAdapter:
    def __init__(self, captured: GreedySimulationResult) -> None:
        self.captured = captured
        self.calls = 0

    def execute(self, **_kwargs) -> GreedySimulationResult:
        self.calls += 1
        return self.captured


def capture_greedy_kernel_slot(
    outcome: GreedyKernelControllerSlotResult,
) -> CapturedGreedyKernelSlot:
    return CapturedGreedyKernelSlot(outcome)


def _semantic_projection(result: GreedySlotResult):
    return (
        result.configuration,
        result.experiment_id,
        result.slot_id,
        result.root_seed,
        result.profile_seed,
        result.flow_order,
        result.policy_result,
        result.placements,
        result.observations,
        result.measured_pairs,
        result.beliefs_before,
        result.beliefs_after,
        result.metrics,
    )


def replay_captured_kernel_slot(
    capture: CapturedGreedyKernelSlot,
) -> GreedyPureKernelReplayValidation:
    """Replay captured observations/pairs once; exclude runtime provenance/timing."""

    expected = capture.outcome.slot
    public = capture.outcome.public_replicas
    profiles = tuple(
        GreedyReplicaProfile(
            identity=state.identity,
            hidden_state=1,
            observation_seed=0,
        )
        for state in public
    )
    replay_input = GreedySlotInput(
        configuration=expected.configuration,
        experiment_id=expected.experiment_id,
        slot_id=expected.slot_id,
        root_seed=expected.root_seed,
        profile_seed=expected.profile_seed,
        public_replicas=public,
        replica_profiles=profiles,
        measured_pair_latencies=(),
        flow_order=expected.flow_order,
    )
    reference = solve_reference_policy(replay_input, expected.flow_order)
    adapter = _CapturedKernelSimulationAdapter(
        GreedySimulationResult(
            observations=expected.observations,
            measured_pairs=expected.measured_pairs,
        )
    )
    replayed = run_greedy_slot(
        replay_input,
        simulation_adapter=adapter,
        clock=lambda: 0.0,
        use_cache=False,
    )
    validation = GreedyPureKernelReplayValidation(
        replayed_pure_slot=replayed,
        reference_policy_result=reference,
        semantic_match=_semantic_projection(replayed) == _semantic_projection(expected),
        reference_policy_match=replayed.policy_result == reference,
        http_requests=0,
        stochastic_redraws=0,
    )
    if adapter.calls != 1 or not validation.matched:
        raise AssertionError("captured Greedy Pure/Kernel replay diverged")
    return validation
