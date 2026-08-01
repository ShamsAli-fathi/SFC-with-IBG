"""Pure in-process execution adapter for selected IBG-Hybrid two-hop routes."""

from __future__ import annotations

from hashlib import blake2b
from typing import Mapping, Protocol

import numpy as np

from IBG import latency_model as exact_latency

from .contracts import GlobalLoadState, ReplicaChoice, TwoStageAction
from .slot_contracts import (
    HybridMeasuredPair,
    HybridReplica,
    HybridSelectedObservation,
    HybridSimulationResult,
)


HYBRID_PHYSICAL_SEED_SCHEME = "blake2b-hybrid-physical-v1"
HYBRID_OBSERVATION_SEED_SCHEME = "blake2b-hybrid-observation-v1"


def _derive_observation_seed(
    *,
    scheme: str,
    root_seed: int,
    slot_id: int,
    flow_id: int,
    choice: ReplicaChoice,
    assigned_load: int,
) -> int:
    payload = (
        f"{scheme}|{root_seed}|{slot_id}|{flow_id}|"
        f"{choice.stage}:{choice.replica}|{assigned_load}"
    ).encode("ascii")
    return int.from_bytes(blake2b(payload, digest_size=8).digest(), "big")


class HybridSlotSimulationAdapter(Protocol):
    """Execute only the committed selected actions after placement completes."""

    def execute(
        self,
        *,
        root_seed: int,
        slot_id: int,
        actions_by_flow: Mapping[int, TwoStageAction],
        final_loads: GlobalLoadState,
        replicas: Mapping[ReplicaChoice, HybridReplica],
        measured_pair_latency_ms: Mapping[
            tuple[ReplicaChoice, ReplicaChoice],
            float,
        ],
    ) -> HybridSimulationResult:
        """Return complete selected observations and one pair outcome per flow."""


class InProcessHybridSimulationAdapter:
    """Generate deterministic physical and observation streams in memory."""

    def execute(
        self,
        *,
        root_seed: int,
        slot_id: int,
        actions_by_flow: Mapping[int, TwoStageAction],
        final_loads: GlobalLoadState,
        replicas: Mapping[ReplicaChoice, HybridReplica],
        measured_pair_latency_ms: Mapping[
            tuple[ReplicaChoice, ReplicaChoice],
            float,
        ],
    ) -> HybridSimulationResult:
        observations = []
        pairs = []
        for flow_id in sorted(actions_by_flow):
            action = actions_by_flow[flow_id]
            for choice in action.choices:
                try:
                    profile = replicas[choice]
                except KeyError as error:
                    raise RuntimeError(
                        "selected replica has no simulation profile: "
                        f"{choice.stage}:{choice.replica}"
                    ) from error
                assigned_load = final_loads.load_for(choice)
                physical_seed = _derive_observation_seed(
                    scheme=HYBRID_PHYSICAL_SEED_SCHEME,
                    root_seed=root_seed,
                    slot_id=slot_id,
                    flow_id=flow_id,
                    choice=choice,
                    assigned_load=assigned_load,
                )
                observation_seed = _derive_observation_seed(
                    scheme=HYBRID_OBSERVATION_SEED_SCHEME,
                    root_seed=root_seed,
                    slot_id=slot_id,
                    flow_id=flow_id,
                    choice=choice,
                    assigned_load=assigned_load,
                )
                physical_rng = np.random.default_rng(physical_seed)
                observation_rng = np.random.default_rng(observation_seed)
                physical_latency = exact_latency.sample_latency_ms(
                    assigned_load,
                    exact_latency.require_state_parameters(profile.hidden_state),
                    physical_rng,
                )
                signal, observation_jitter = (
                    exact_latency.sample_learning_signal_ms(
                        physical_latency,
                        profile.hidden_state,
                        observation_rng,
                    )
                )
                likelihood = exact_latency.learning_signal_likelihood(
                    signal,
                    assigned_load,
                )
                observations.append(
                    HybridSelectedObservation(
                        flow_id=flow_id,
                        choice=choice,
                        assigned_load=assigned_load,
                        physical_processing_latency_ms=physical_latency,
                        observation_jitter_ms=observation_jitter,
                        learning_signal_ms=signal,
                        likelihood=likelihood,
                        estimated_state=exact_latency.estimate_state(likelihood),
                        physical_seed=physical_seed,
                        observation_seed=observation_seed,
                    )
                )

            pair = action.choices
            try:
                pair_latency = measured_pair_latency_ms[pair]
            except KeyError as error:
                raise RuntimeError(
                    "selected action has no simulated measured-pair outcome: "
                    f"{pair[0].stage}:{pair[0].replica}->"
                    f"{pair[1].stage}:{pair[1].replica}"
                ) from error
            pairs.append(
                HybridMeasuredPair(
                    flow_id=flow_id,
                    source=pair[0],
                    target=pair[1],
                    latency_ms=pair_latency,
                )
            )

        return HybridSimulationResult(
            observations=tuple(observations),
            measured_pairs=tuple(pairs),
        )
