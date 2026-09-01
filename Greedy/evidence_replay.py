"""Captured-input Phase 6 replay without HTTP, randomness, or runner imports."""

from __future__ import annotations

from dataclasses import dataclass

from .kernel_contracts import GreedyKernelControllerSlotResult
from .learning import apply_selected_learning
from .metrics import compute_slot_metrics
from .policy import GreedyPolicy


@dataclass(frozen=True)
class GreedyEvidenceReplayValidation:
    policy_match: bool
    beliefs_match: bool
    metrics_match: bool
    http_requests: int = 0
    stochastic_redraws: int = 0

    @property
    def matched(self) -> bool:
        return (
            self.policy_match
            and self.beliefs_match
            and self.metrics_match
            and self.http_requests == 0
            and self.stochastic_redraws == 0
        )


def replay_greedy_evidence_slot(
    outcome: GreedyKernelControllerSlotResult,
) -> GreedyEvidenceReplayValidation:
    """Recompute policy, selected learning, and metrics from captured inputs."""

    if not isinstance(outcome, GreedyKernelControllerSlotResult):
        raise TypeError("outcome must be GreedyKernelControllerSlotResult")
    slot = outcome.slot
    replayed_policy = GreedyPolicy(slot.configuration).place(
        flow_order=slot.flow_order,
        replica_states=outcome.public_replicas,
        use_cache=False,
    )
    before, after = apply_selected_learning(
        outcome.public_replicas,
        slot.observations,
    )
    metrics = compute_slot_metrics(
        policy_result=replayed_policy,
        beliefs_before=before.mapping,
        beliefs_after=after.mapping,
        observations=slot.observations,
        measured_pairs=slot.measured_pairs,
    )
    validation = GreedyEvidenceReplayValidation(
        policy_match=replayed_policy == slot.policy_result,
        beliefs_match=(before == slot.beliefs_before and after == slot.beliefs_after),
        metrics_match=metrics == slot.metrics,
    )
    if not validation.matched:
        raise AssertionError("captured Greedy evidence replay diverged")
    return validation
