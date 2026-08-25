"""Greedy-owned pure adapter for the active selected-only IBG learner."""

from __future__ import annotations

from typing import Mapping, Sequence

from IBG.learning import apply_observations

from .contracts import PublicReplicaState, ReplicaIdentity
from .slot_contracts import (
    BeliefVector,
    GreedyBeliefSnapshot,
    GreedySelectedObservation,
)


GREEDY_LEARNING_ADAPTER_VERSION = "greedy-selected-only-learning-v1"
GREEDY_BELIEF_RETENTION = 0.8


class _LearningReplica:
    """Minimal mutable target with the frozen Exact posterior/aggregation API."""

    def __init__(self, belief: Sequence[float]) -> None:
        self.belief = [float(value) for value in belief]

    def local_update(
        self,
        likelihood: Sequence[float],
        _signal: float,
    ) -> list[float]:
        values = tuple(float(value) for value in likelihood)
        denominator = sum(
            prior * likelihood_value
            for prior, likelihood_value in zip(self.belief, values)
        )
        if denominator <= 0:
            raise RuntimeError("selected observation has zero posterior mass")
        return [
            round(prior * likelihood_value / denominator, 3)
            for prior, likelihood_value in zip(self.belief, values)
        ]

    def aggregation(self, local_beliefs: Sequence[Sequence[float]]) -> None:
        for index in range(4):
            mean_local = sum(belief[index] for belief in local_beliefs) / len(
                local_beliefs
            )
            self.belief[index] = round(
                GREEDY_BELIEF_RETENTION * self.belief[index]
                + (1.0 - GREEDY_BELIEF_RETENTION) * mean_local,
                3,
            )


def apply_selected_learning(
    public_replicas: Sequence[PublicReplicaState],
    observations: Sequence[GreedySelectedObservation],
) -> tuple[GreedyBeliefSnapshot, GreedyBeliefSnapshot]:
    """Apply only supplied selected observations without mutating caller inputs."""

    replicas: dict[tuple[int, int], _LearningReplica] = {}
    identities: dict[tuple[int, int], ReplicaIdentity] = {}
    for state in sorted(public_replicas, key=lambda value: value.identity):
        key = (state.identity.stage, state.identity.replica)
        replicas[key] = _LearningReplica(state.belief)
        identities[key] = state.identity
    before = GreedyBeliefSnapshot.from_mapping(
        {
            identities[key]: tuple(replica.belief)
            for key, replica in replicas.items()
        }
    )
    apply_observations(tuple(observations), replicas)
    after = GreedyBeliefSnapshot.from_mapping(
        {
            identities[key]: tuple(replica.belief)
            for key, replica in replicas.items()
        }
    )
    return before, after


def maximum_belief_change(
    before: Mapping[ReplicaIdentity, BeliefVector],
    after: Mapping[ReplicaIdentity, BeliefVector],
) -> float:
    if set(before) != set(after) or not before:
        raise ValueError("belief snapshots must cover the same nonempty identities")
    return max(
        abs(after_value - before_value)
        for identity in before
        for before_value, after_value in zip(before[identity], after[identity])
    )
