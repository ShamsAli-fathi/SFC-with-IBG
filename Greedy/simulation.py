"""Pure deterministic stochastic-input and selected-route simulation boundary."""

from __future__ import annotations

import random
from dataclasses import dataclass
from hashlib import blake2b
from numbers import Integral
from typing import Mapping, Protocol, Sequence

import numpy as np

from IBG import latency_model

from .contracts import GlobalLoadState, ReplicaIdentity, TwoStageAction
from .slot_contracts import (
    GREEDY_EXPLICIT_FLOW_ORDER_SCHEME,
    GreedyMeasuredPair,
    GreedyReplicaProfile,
    GreedySelectedObservation,
    GreedySimulationResult,
)


# This value and payload are intentionally byte-for-byte compatible with the
# active Hybrid flow-order boundary. Greedy does not import a Hybrid namespace.
GREEDY_FLOW_ORDER_SEED_SCHEME = "blake2b-hybrid-flow-order-v1"
GREEDY_MATCHED_INPUT_SEED_SCHEME = (
    "hybrid-compatible-experiment-scoped-components-v1"
)
GREEDY_PHYSICAL_SEED_SCHEME = "blake2b-hybrid-physical-v1"
GREEDY_OBSERVATION_SEED_SCHEME = "blake2b-hybrid-observation-v1"
GREEDY_PHYSICAL_COMPONENT = "physical"
GREEDY_OBSERVATION_COMPONENT = "observation"
_STOCHASTIC_COMPONENTS = frozenset(
    (GREEDY_PHYSICAL_COMPONENT, GREEDY_OBSERVATION_COMPONENT)
)


def _integer(name: str, value: int, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise TypeError(f"{name} must be an integer")
    if value < minimum:
        raise ValueError(f"{name} is below its minimum {minimum}")
    return int(value)


def derive_flow_order_seed(root_seed: int, slot_id: int) -> int:
    """Derive the Hybrid-compatible slot-wide local flow-order seed."""

    root = _integer("root_seed", root_seed, minimum=0)
    slot = _integer("slot_id", slot_id, minimum=1)
    payload = f"{GREEDY_FLOW_ORDER_SEED_SCHEME}|{root}|{slot}".encode("ascii")
    return int.from_bytes(blake2b(payload, digest_size=8).digest(), "big")


def resolve_flow_order(
    *,
    num_flows: int,
    root_seed: int,
    slot_id: int,
    explicit_flow_order: Sequence[int] | None,
) -> tuple[tuple[int, ...], str, int | None]:
    """Return an explicit order unchanged or derive one with a local RNG."""

    count = _integer("num_flows", num_flows, minimum=1)
    expected = set(range(1, count + 1))
    if explicit_flow_order is not None:
        order = tuple(explicit_flow_order)
        if len(order) != count or set(order) != expected:
            raise ValueError("explicit flow order must be a permutation of flows 1..N")
        return order, GREEDY_EXPLICIT_FLOW_ORDER_SCHEME, None
    seed = derive_flow_order_seed(root_seed, slot_id)
    order = list(range(1, count + 1))
    random.Random(seed).shuffle(order)
    return tuple(order), GREEDY_FLOW_ORDER_SEED_SCHEME, seed


@dataclass(frozen=True)
class GreedyStochasticInputKey:
    """Complete immutable identity for one matched component draw."""

    experiment_id: int
    slot_id: int
    flow_id: int
    identity: ReplicaIdentity
    assigned_load: int
    component: str

    def __post_init__(self) -> None:
        for name in ("experiment_id", "slot_id", "flow_id", "assigned_load"):
            object.__setattr__(
                self,
                name,
                _integer(name, getattr(self, name), minimum=1),
            )
        if not isinstance(self.identity, ReplicaIdentity):
            raise TypeError("identity must be ReplicaIdentity")
        if self.component not in _STOCHASTIC_COMPONENTS:
            raise ValueError("component must be physical or observation")


def derive_stochastic_input_seed(
    root_seed: int,
    key: GreedyStochasticInputKey,
) -> int:
    """Derive a local seed without profile/global RNG coupling."""

    root = _integer("root_seed", root_seed, minimum=0)
    scheme = (
        GREEDY_PHYSICAL_SEED_SCHEME
        if key.component == GREEDY_PHYSICAL_COMPONENT
        else GREEDY_OBSERVATION_SEED_SCHEME
    )
    # Every launcher invocation owns exactly one experiment, canonically ID 1.
    # Preserve the active Hybrid bytes for that matched case. Noncanonical IDs
    # receive an explicit experiment namespace so independent pure fixtures do
    # not alias each other.
    experiment_scope = "" if key.experiment_id == 1 else f"experiment:{key.experiment_id}|"
    payload = (
        f"{scheme}|{experiment_scope}{root}|{key.slot_id}|{key.flow_id}|"
        f"{key.identity.stage}:{key.identity.replica}|{key.assigned_load}"
    ).encode("ascii")
    return int.from_bytes(blake2b(payload, digest_size=8).digest(), "big")


class GreedySlotSimulationAdapter(Protocol):
    """Execute only committed actions and return captured selected outcomes."""

    def execute(
        self,
        *,
        experiment_id: int,
        root_seed: int,
        slot_id: int,
        actions_by_flow: Mapping[int, TwoStageAction],
        final_loads: GlobalLoadState,
        replica_profiles: Mapping[ReplicaIdentity, GreedyReplicaProfile],
        measured_pair_latency_ms: Mapping[
            tuple[ReplicaIdentity, ReplicaIdentity],
            float,
        ],
    ) -> GreedySimulationResult:
        """Return exactly two selected observations and one pair per flow."""


class InProcessGreedySimulationAdapter:
    """Generate deterministic separated physical/observation draws in memory."""

    def execute(
        self,
        *,
        experiment_id: int,
        root_seed: int,
        slot_id: int,
        actions_by_flow: Mapping[int, TwoStageAction],
        final_loads: GlobalLoadState,
        replica_profiles: Mapping[ReplicaIdentity, GreedyReplicaProfile],
        measured_pair_latency_ms: Mapping[
            tuple[ReplicaIdentity, ReplicaIdentity],
            float,
        ],
    ) -> GreedySimulationResult:
        observations = []
        measured_pairs = []
        for flow_id in sorted(actions_by_flow):
            action = actions_by_flow[flow_id]
            for identity in action.choices:
                try:
                    profile = replica_profiles[identity]
                except KeyError as error:
                    raise RuntimeError(
                        "selected replica has no simulation profile: "
                        f"{identity.stage}:{identity.replica}"
                    ) from error
                assigned_load = final_loads.load_for(identity)
                physical_key = GreedyStochasticInputKey(
                    experiment_id,
                    slot_id,
                    flow_id,
                    identity,
                    assigned_load,
                    GREEDY_PHYSICAL_COMPONENT,
                )
                observation_key = GreedyStochasticInputKey(
                    experiment_id,
                    slot_id,
                    flow_id,
                    identity,
                    assigned_load,
                    GREEDY_OBSERVATION_COMPONENT,
                )
                physical_seed = derive_stochastic_input_seed(root_seed, physical_key)
                observation_seed = derive_stochastic_input_seed(
                    root_seed,
                    observation_key,
                )
                physical_latency = latency_model.sample_latency_ms(
                    assigned_load,
                    latency_model.require_state_parameters(profile.hidden_state),
                    np.random.default_rng(physical_seed),
                )
                learning_signal, observation_jitter = (
                    latency_model.sample_learning_signal_ms(
                        physical_latency,
                        profile.hidden_state,
                        np.random.default_rng(observation_seed),
                    )
                )
                likelihood = latency_model.learning_signal_likelihood(
                    learning_signal,
                    assigned_load,
                )
                observations.append(
                    GreedySelectedObservation(
                        flow_id=flow_id,
                        identity=identity,
                        assigned_load=assigned_load,
                        physical_processing_latency_ms=physical_latency,
                        observation_jitter_ms=observation_jitter,
                        learning_signal_ms=learning_signal,
                        likelihood=likelihood,
                        estimated_state=latency_model.estimate_state(likelihood),
                        physical_seed=physical_seed,
                        observation_seed=observation_seed,
                    )
                )

            try:
                pair_latency = measured_pair_latency_ms[action.choices]
            except KeyError as error:
                source, target = action.choices
                raise RuntimeError(
                    "selected action has no measured-pair outcome: "
                    f"{source.stage}:{source.replica}->"
                    f"{target.stage}:{target.replica}"
                ) from error
            measured_pairs.append(
                GreedyMeasuredPair(
                    flow_id=flow_id,
                    source=action.choices[0],
                    target=action.choices[1],
                    latency_ms=pair_latency,
                )
            )

        return GreedySimulationResult(
            observations=tuple(observations),
            measured_pairs=tuple(measured_pairs),
        )
