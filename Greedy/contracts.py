"""Immutable contracts for the pure budgeted Greedy policy."""

from __future__ import annotations

from dataclasses import dataclass
from math import fsum, isfinite
from numbers import Integral
from typing import ClassVar, Iterable, Mapping, Sequence


LEGACY_GREEDY_POLICY_VERSION = "pure-greedy-budgeted-l2-v1"
GREEDY_POLICY_VERSION = "pure-greedy-budgeted-l2-v2"
GREEDY_STAGE_BUDGET = 2


def _positive_integer(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise TypeError(f"{name} must be an integer")
    if value < 1:
        raise ValueError(f"{name} must be positive")
    return int(value)


def _nonnegative_integer(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must not be negative")
    return int(value)


def _belief_tuple(values: Sequence[float]) -> tuple[float, float, float, float]:
    belief = tuple(float(value) for value in values)
    if len(belief) != 4:
        raise ValueError("belief must contain the four IBG states")
    if any(not isfinite(value) or value < 0 for value in belief):
        raise ValueError("belief probabilities must be finite and nonnegative")
    if sum(belief) <= 0:
        raise ValueError("belief probabilities must have positive mass")
    return belief


@dataclass(frozen=True)
class GreedyConfiguration:
    """Required explicit dimensions for a uniform contiguous topology."""

    num_flows: int
    num_stages: int
    num_replicas: int

    stage_budget: ClassVar[int] = GREEDY_STAGE_BUDGET

    def __post_init__(self) -> None:
        for name in ("num_flows", "num_stages", "num_replicas"):
            object.__setattr__(
                self,
                name,
                _positive_integer(name, getattr(self, name)),
            )
        if self.num_stages < GREEDY_STAGE_BUDGET:
            raise ValueError("num_stages must be at least 2 for the fixed L=2 budget")

    @property
    def stages(self) -> tuple[int, ...]:
        return tuple(range(1, self.num_stages + 1))

    @property
    def replica_ids(self) -> tuple[int, ...]:
        return tuple(range(1, self.num_replicas + 1))

@dataclass(frozen=True, order=True)
class ReplicaIdentity:
    stage: int
    replica: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "stage", _positive_integer("stage", self.stage))
        object.__setattr__(
            self,
            "replica",
            _positive_integer("replica", self.replica),
        )

    def validate_for(self, configuration: GreedyConfiguration) -> None:
        if self.stage > configuration.num_stages:
            raise ValueError(f"stage {self.stage} exceeds configured stage count")
        if self.replica > configuration.num_replicas:
            raise ValueError(
                f"replica {self.replica} exceeds configured per-stage replica count"
            )


@dataclass(frozen=True)
class PublicReplicaState:
    """All and only the public replica values visible to policy selection."""

    identity: ReplicaIdentity
    ready: bool
    belief: tuple[float, float, float, float]

    def __post_init__(self) -> None:
        if not isinstance(self.identity, ReplicaIdentity):
            raise TypeError("identity must be ReplicaIdentity")
        if not isinstance(self.ready, bool):
            raise TypeError("ready must be a boolean")
        object.__setattr__(self, "belief", _belief_tuple(self.belief))

    def validate_for(self, configuration: GreedyConfiguration) -> None:
        self.identity.validate_for(configuration)


@dataclass(frozen=True, order=True)
class TwoStageAction:
    """One replica from each of exactly two distinct increasing stages."""

    choices: tuple[ReplicaIdentity, ReplicaIdentity]

    def __post_init__(self) -> None:
        choices = tuple(self.choices)
        object.__setattr__(self, "choices", choices)
        if len(choices) != GREEDY_STAGE_BUDGET:
            raise ValueError("a Greedy action must contain exactly two choices")
        if not all(isinstance(choice, ReplicaIdentity) for choice in choices):
            raise TypeError("action choices must be ReplicaIdentity values")
        if choices[0].stage >= choices[1].stage:
            raise ValueError(
                "action choices must use distinct stages in increasing stage order"
            )

    @property
    def stages(self) -> tuple[int, int]:
        return tuple(choice.stage for choice in self.choices)

    def validate_for(self, configuration: GreedyConfiguration) -> None:
        for choice in self.choices:
            choice.validate_for(configuration)

    def bypassed_stages(self, configuration: GreedyConfiguration) -> tuple[int, ...]:
        self.validate_for(configuration)
        selected = set(self.stages)
        return tuple(stage for stage in configuration.stages if stage not in selected)


@dataclass(frozen=True)
class GlobalLoadState:
    """Canonical immutable loads indexed by Greedy replica identity."""

    entries: tuple[tuple[ReplicaIdentity, int], ...]

    def __post_init__(self) -> None:
        entries = tuple(
            (identity, _nonnegative_integer("replica load", load))
            for identity, load in self.entries
        )
        object.__setattr__(self, "entries", entries)
        identities = tuple(identity for identity, _load in entries)
        if not entries:
            raise ValueError("global load state must not be empty")
        if not all(isinstance(identity, ReplicaIdentity) for identity in identities):
            raise TypeError("load identities must be ReplicaIdentity values")
        if identities != tuple(sorted(set(identities))):
            raise ValueError("global loads must use unique canonical identities")

    @classmethod
    def empty(
        cls,
        configuration: GreedyConfiguration,
        identities: Iterable[ReplicaIdentity] | None = None,
    ) -> GlobalLoadState:
        if identities is None:
            identities = (
                ReplicaIdentity(stage, replica)
                for stage in configuration.stages
                for replica in configuration.replica_ids
            )
        return cls(tuple((identity, 0) for identity in identities))

    @classmethod
    def from_mapping(
        cls,
        loads: Mapping[ReplicaIdentity, int],
    ) -> GlobalLoadState:
        return cls(tuple(sorted(loads.items())))

    def validate_for(
        self,
        configuration: GreedyConfiguration,
        identities: Sequence[ReplicaIdentity] | None = None,
    ) -> None:
        expected = tuple(identities) if identities is not None else tuple(
            ReplicaIdentity(stage, replica)
            for stage in configuration.stages
            for replica in configuration.replica_ids
        )
        if tuple(identity for identity, _load in self.entries) != expected:
            raise ValueError("global loads do not cover the configured canonical identities")

    def load_for(self, identity: ReplicaIdentity) -> int:
        try:
            return dict(self.entries)[identity]
        except KeyError as error:
            raise ValueError(f"identity {identity} is absent from global loads") from error

    @property
    def total_assignments(self) -> int:
        return sum(load for _identity, load in self.entries)

    def apply(self, action: TwoStageAction) -> GlobalLoadState:
        updated = dict(self.entries)
        for identity in action.choices:
            if identity not in updated:
                raise ValueError(f"identity {identity} is absent from global loads")
            updated[identity] += 1
        return GlobalLoadState.from_mapping(updated)


@dataclass(frozen=True)
class AdmissionFeasibility:
    feasible: bool
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        reasons = tuple(str(reason) for reason in self.reasons)
        object.__setattr__(self, "reasons", reasons)
        if self.feasible and reasons:
            raise ValueError("a feasible result cannot contain rejection reasons")
        if not self.feasible and not reasons:
            raise ValueError("an infeasible result must contain a rejection reason")

    @classmethod
    def accepted(cls) -> AdmissionFeasibility:
        return cls(True)

    @classmethod
    def rejected(cls, *reasons: str) -> AdmissionFeasibility:
        return cls(False, tuple(reasons))


@dataclass(frozen=True)
class DecisionResult:
    flow_id: int
    action: TwoStageAction
    bypassed_stages: tuple[int, ...]
    stage_utilities: tuple[float, float]
    objective_value: float
    state_before: GlobalLoadState
    state_after: GlobalLoadState
    evaluated_actions: int
    feasible_actions: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "flow_id", _positive_integer("flow_id", self.flow_id))
        if not isinstance(self.action, TwoStageAction):
            raise TypeError("action must be TwoStageAction")
        bypassed = tuple(self.bypassed_stages)
        object.__setattr__(self, "bypassed_stages", bypassed)
        if bypassed != tuple(sorted(set(bypassed))):
            raise ValueError("bypassed stages must be unique and increasing")
        utilities = tuple(float(value) for value in self.stage_utilities)
        object.__setattr__(self, "stage_utilities", utilities)
        if len(utilities) != GREEDY_STAGE_BUDGET or any(
            not isfinite(value) for value in utilities
        ):
            raise ValueError("stage utilities must contain two finite values")
        objective = float(self.objective_value)
        object.__setattr__(self, "objective_value", objective)
        if not isfinite(objective) or objective != fsum(utilities):
            raise ValueError("objective_value must equal the two stage utilities")
        if self.state_after != self.state_before.apply(self.action):
            raise ValueError("state_after must increment exactly the selected replicas")
        evaluated = _positive_integer("evaluated_actions", self.evaluated_actions)
        feasible = _positive_integer("feasible_actions", self.feasible_actions)
        object.__setattr__(self, "evaluated_actions", evaluated)
        object.__setattr__(self, "feasible_actions", feasible)
        if feasible > evaluated:
            raise ValueError("feasible_actions cannot exceed evaluated_actions")


@dataclass(frozen=True)
class PolicyResult:
    configuration: GreedyConfiguration
    flow_order: tuple[int, ...]
    decisions: tuple[DecisionResult, ...]
    final_loads: GlobalLoadState

    def __post_init__(self) -> None:
        if not isinstance(self.configuration, GreedyConfiguration):
            raise TypeError("configuration must be GreedyConfiguration")
        flow_order = tuple(self.flow_order)
        decisions = tuple(self.decisions)
        object.__setattr__(self, "flow_order", flow_order)
        object.__setattr__(self, "decisions", decisions)
        expected_flows = set(range(1, self.configuration.num_flows + 1))
        if len(flow_order) != self.configuration.num_flows or set(flow_order) != expected_flows:
            raise ValueError("flow_order must be a permutation of configured flows 1..N")
        if tuple(decision.flow_id for decision in decisions) != flow_order:
            raise ValueError("decisions must exactly retain the supplied flow order")
        if decisions and decisions[-1].state_after != self.final_loads:
            raise ValueError("final_loads must equal the final sequential decision state")
        if not decisions:
            raise ValueError("a complete policy result must contain all configured flows")
        for previous, current in zip(decisions, decisions[1:]):
            if previous.state_after != current.state_before:
                raise ValueError("policy decisions must form one sequential load chain")
        expected_bypasses = self.configuration.num_stages - GREEDY_STAGE_BUDGET
        if any(len(decision.bypassed_stages) != expected_bypasses for decision in decisions):
            raise ValueError("every decision must bypass exactly K-2 stages")

    @property
    def actions(self) -> tuple[TwoStageAction, ...]:
        return tuple(decision.action for decision in self.decisions)


class NoFeasibleActionError(RuntimeError):
    """Raised when a real flow has no complete feasible L=2 action."""

    def __init__(
        self,
        flow_id: int,
        state: GlobalLoadState,
        evaluated_actions: int,
    ) -> None:
        self.flow_id = flow_id
        self.state = state
        self.evaluated_actions = evaluated_actions
        super().__init__(
            f"flow {flow_id} has no feasible complete L=2 Greedy action "
            f"among {evaluated_actions} canonical actions"
        )
