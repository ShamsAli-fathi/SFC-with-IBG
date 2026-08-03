"""Pure in-process outcome adapter for selected coupled-MILP routes."""

from __future__ import annotations

from hashlib import blake2b
from typing import Protocol

import numpy as np

from IBG import latency_model as exact_latency

from .contracts import MILPPlacement
from .slot_contracts import (
    MILP_MEASURED_PAIR_SEED_SCHEME,
    MILP_OBSERVATION_SEED_SCHEME,
    MILP_PHYSICAL_SEED_SCHEME,
    MILPMeasuredPairOutcome,
    MILPSelectedObservation,
    MILPSimulationResult,
    MILPSlotInput,
)


def derive_milp_sample_seed(*, scheme: str, values: tuple[object, ...]) -> int:
    """Derive one stable local RNG seed without touching process-global RNGs."""

    payload = (scheme + "|" + "|".join(str(value) for value in values)).encode(
        "ascii"
    )
    return int.from_bytes(blake2b(payload, digest_size=8).digest(), "big")


class MILPSlotSimulationAdapter(Protocol):
    def execute(
        self,
        slot_input: MILPSlotInput,
        placement: MILPPlacement,
    ) -> MILPSimulationResult:
        """Execute only the complete selected placement in memory."""


class InProcessMILPSimulationAdapter:
    """Generate independent physical, observation, and pair samples."""

    def execute(
        self,
        slot_input: MILPSlotInput,
        placement: MILPPlacement,
    ) -> MILPSimulationResult:
        actions = placement.action_by_flow()
        final_loads = dict(placement.final_loads)
        true_states = slot_input.problem.true_state_by_replica()
        pair_profiles = slot_input.measured_pair_profile_by_pair()
        observations: list[MILPSelectedObservation] = []
        measured_pairs: list[MILPMeasuredPairOutcome] = []

        for flow_id in sorted(actions):
            action = actions[flow_id]
            for key in action.selections:
                assigned_load = final_loads[key]
                physical_seed = derive_milp_sample_seed(
                    scheme=MILP_PHYSICAL_SEED_SCHEME,
                    values=(
                        slot_input.root_seed,
                        slot_input.slot_id,
                        flow_id,
                        key.stage,
                        key.replica,
                        assigned_load,
                    ),
                )
                observation_seed = derive_milp_sample_seed(
                    scheme=MILP_OBSERVATION_SEED_SCHEME,
                    values=(
                        slot_input.root_seed,
                        slot_input.slot_id,
                        flow_id,
                        key.stage,
                        key.replica,
                        assigned_load,
                    ),
                )
                physical_rng = np.random.default_rng(physical_seed)
                observation_rng = np.random.default_rng(observation_seed)
                state = true_states[key]
                physical_latency = exact_latency.sample_latency_ms(
                    assigned_load,
                    exact_latency.require_state_parameters(state),
                    physical_rng,
                )
                observation_jitter = exact_latency.sample_observation_jitter_ms(
                    state,
                    observation_rng,
                )
                noisy_signal = physical_latency + observation_jitter
                likelihood = exact_latency.learning_signal_likelihood(
                    noisy_signal,
                    assigned_load,
                )
                observations.append(
                    MILPSelectedObservation(
                        flow_id=flow_id,
                        key=key,
                        assigned_load=assigned_load,
                        physical_processing_latency_ms=physical_latency,
                        observation_jitter_ms=observation_jitter,
                        noisy_signal_ms=noisy_signal,
                        likelihood=likelihood,
                        estimated_state=exact_latency.estimate_state(likelihood),
                        physical_seed=physical_seed,
                        observation_seed=observation_seed,
                    )
                )

            source, target = action.directed_pair
            profile = pair_profiles[(source, target)]
            pair_seed = derive_milp_sample_seed(
                scheme=MILP_MEASURED_PAIR_SEED_SCHEME,
                values=(
                    slot_input.root_seed,
                    slot_input.slot_id,
                    flow_id,
                    source.stage,
                    source.replica,
                    final_loads[source],
                    target.stage,
                    target.replica,
                    final_loads[target],
                ),
            )
            pair_rng = np.random.default_rng(pair_seed)
            pair_jitter = (
                0.0
                if profile.jitter_ms == 0.0
                else abs(float(pair_rng.normal(0.0, profile.jitter_ms)))
            )
            measured_pairs.append(
                MILPMeasuredPairOutcome(
                    flow_id=flow_id,
                    source=source,
                    target=target,
                    latency_ms=profile.base_ms + pair_jitter,
                    pair_seed=pair_seed,
                    profile_base_ms=profile.base_ms,
                    profile_jitter_ms=profile.jitter_ms,
                )
            )

        return MILPSimulationResult(
            observations=tuple(observations),
            measured_pairs=tuple(measured_pairs),
        )
