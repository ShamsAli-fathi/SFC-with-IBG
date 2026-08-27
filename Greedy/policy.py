"""Pure exhaustive immediate Greedy placement for real sequential flows."""

from __future__ import annotations

from itertools import combinations, product
from math import fsum, isfinite
from typing import Mapping, Sequence

from .contracts import (
    AdmissionFeasibility,
    DecisionResult,
    GlobalLoadState,
    GreedyConfiguration,
    NoFeasibleActionError,
    PolicyResult,
    PublicReplicaState,
    ReplicaIdentity,
    TwoStageAction,
)
from .expected_utility import (
    BoundedExpectedUtilityCache,
    DEFAULT_EXPECTED_UTILITY_CACHE_MAX_ENTRIES,
    ExpectedUtilityCacheInfo,
)


class GreedyPolicy:
    """One import-safe policy object with precomputed topology and action order."""

    def __init__(
        self,
        configuration: GreedyConfiguration,
        *,
        utility_cache_max_entries: int = DEFAULT_EXPECTED_UTILITY_CACHE_MAX_ENTRIES,
    ) -> None:
        if not isinstance(configuration, GreedyConfiguration):
            raise TypeError("configuration must be GreedyConfiguration")
        self.configuration = configuration
        self._identities_by_stage = tuple(
            tuple(
                ReplicaIdentity(stage, replica)
                for replica in configuration.replica_ids
            )
            for stage in configuration.stages
        )
        self._identities = tuple(
            identity
            for stage_identities in self._identities_by_stage
            for identity in stage_identities
        )
        actions = (
            TwoStageAction((first, second))
            for stage_a, stage_b in combinations(configuration.stages, 2)
            for first, second in product(
                self._identities_by_stage[stage_a - 1],
                self._identities_by_stage[stage_b - 1],
            )
        )
        self._actions = tuple(sorted(actions))
        self._utility_cache = BoundedExpectedUtilityCache(
            utility_cache_max_entries
        )

    @property
    def identities(self) -> tuple[ReplicaIdentity, ...]:
        return self._identities

    @property
    def identities_by_stage(self) -> tuple[tuple[ReplicaIdentity, ...], ...]:
        return self._identities_by_stage

    @property
    def actions(self) -> tuple[TwoStageAction, ...]:
        return self._actions

    @property
    def utility_cache_info(self) -> ExpectedUtilityCacheInfo:
        return self._utility_cache.info

    def clear_utility_cache(self) -> None:
        self._utility_cache.clear()

    def _public_state_map(
        self,
        replica_states: Sequence[PublicReplicaState],
    ) -> dict[ReplicaIdentity, PublicReplicaState]:
        states = tuple(replica_states)
        if not all(type(state) is PublicReplicaState for state in states):
            raise TypeError("replica_states must contain exact PublicReplicaState values")
        by_identity = {state.identity: state for state in states}
        if len(by_identity) != len(states):
            raise ValueError("replica_states must contain unique identities")
        if tuple(sorted(by_identity)) != self._identities:
            raise ValueError("replica_states must cover every configured identity")
        for state in states:
            state.validate_for(self.configuration)
        return by_identity

    def evaluate_admission(
        self,
        identity: ReplicaIdentity,
        state: GlobalLoadState,
        public_states: Mapping[ReplicaIdentity, PublicReplicaState],
    ) -> AdmissionFeasibility:
        """Use only canonical public identity coverage and Ready state."""

        state.validate_for(self.configuration, self._identities)
        identity.validate_for(self.configuration)
        public = public_states.get(identity)
        if public is None:
            return AdmissionFeasibility.rejected(
                f"missing-public-replica:{identity.stage}:{identity.replica}"
            )
        public.validate_for(self.configuration)
        if public.identity != identity:
            return AdmissionFeasibility.rejected(
                f"mismatched-public-replica:{identity.stage}:{identity.replica}"
            )
        reasons = []
        if not public.ready:
            reasons.append(f"not-ready:{identity.stage}:{identity.replica}")
        if reasons:
            return AdmissionFeasibility.rejected(*reasons)
        return AdmissionFeasibility.accepted()

    def select_action(
        self,
        *,
        flow_id: int,
        state: GlobalLoadState,
        replica_states: Sequence[PublicReplicaState],
        use_cache: bool = True,
    ) -> DecisionResult:
        public_states = self._public_state_map(replica_states)
        return self._select_action(
            flow_id=flow_id,
            state=state,
            public_states=public_states,
            use_cache=use_cache,
        )

    def _select_action(
        self,
        *,
        flow_id: int,
        state: GlobalLoadState,
        public_states: Mapping[ReplicaIdentity, PublicReplicaState],
        use_cache: bool,
    ) -> DecisionResult:
        state.validate_for(self.configuration, self._identities)

        local_feasibility = {
            identity: self.evaluate_admission(identity, state, public_states)
            for identity in self._identities
        }
        local_utility = {}
        for identity, feasibility in local_feasibility.items():
            if not feasibility.feasible:
                continue
            projected_load = state.load_for(identity) + 1
            value = float(
                self._utility_cache.value(
                    public_states[identity].belief,
                    projected_load,
                    use_cache=use_cache,
                )
            )
            if not isfinite(value):
                raise ValueError("expected stage utility must be finite")
            local_utility[identity] = value

        best_action = None
        best_utilities = None
        best_score = None
        feasible_actions = 0
        for action in self._actions:
            if not all(local_feasibility[identity].feasible for identity in action.choices):
                continue
            feasible_actions += 1
            stage_utilities = tuple(local_utility[identity] for identity in action.choices)
            score = fsum(stage_utilities)
            if best_action is None or score > best_score:
                best_action = action
                best_utilities = stage_utilities
                best_score = score

        if best_action is None:
            raise NoFeasibleActionError(flow_id, state, len(self._actions))
        state_after = state.apply(best_action)
        return DecisionResult(
            flow_id=flow_id,
            action=best_action,
            bypassed_stages=best_action.bypassed_stages(self.configuration),
            stage_utilities=best_utilities,
            objective_value=best_score,
            state_before=state,
            state_after=state_after,
            evaluated_actions=len(self._actions),
            feasible_actions=feasible_actions,
        )

    def place(
        self,
        *,
        flow_order: Sequence[int],
        replica_states: Sequence[PublicReplicaState],
        initial_loads: GlobalLoadState | None = None,
        use_cache: bool = True,
    ) -> PolicyResult:
        order = tuple(flow_order)
        expected = set(range(1, self.configuration.num_flows + 1))
        if len(order) != self.configuration.num_flows or set(order) != expected:
            raise ValueError("flow_order must be an explicit permutation of flows 1..N")
        if any(isinstance(flow, bool) or not isinstance(flow, int) for flow in order):
            raise TypeError("flow_order values must be integers")
        public_states = tuple(replica_states)
        public_state_map = self._public_state_map(public_states)
        state = initial_loads or GlobalLoadState.empty(
            self.configuration,
            self._identities,
        )
        state.validate_for(self.configuration, self._identities)
        decisions = []
        for flow_id in order:
            decision = self._select_action(
                flow_id=flow_id,
                state=state,
                public_states=public_state_map,
                use_cache=use_cache,
            )
            decisions.append(decision)
            state = decision.state_after
        return PolicyResult(
            configuration=self.configuration,
            flow_order=order,
            decisions=tuple(decisions),
            final_loads=state,
        )
