"""Executable Greedy Phase 0 contract fixtures.

This module freezes the baseline boundary without implementing the production
policy or a slot runner.  Phase 1 may consume these fixtures as a small oracle,
but it must provide the actual typed policy implementation separately.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import ceil, isfinite
from numbers import Integral
from typing import Mapping


GREEDY_POLICY_CONTRACT_VERSION = "pure-greedy-budgeted-l2-v1"
GREEDY_SELECTION_BUDGET = 2
GREEDY_ACTION_SCORE_MODE = "sum-immediate-expected-stage-utility-v1"
GREEDY_REQUIRES_EXPLICIT_DIMENSIONS = True
GREEDY_REQUIRED_DIMENSION_OPTIONS = ("--flow", "--stage", "--replica")
GREEDY_CANONICAL_COMPARISON_FLOW_COUNT = 10
GREEDY_CANONICAL_COMPARISON_STAGE_COUNT = 3
GREEDY_CANONICAL_COMPARISON_REPLICAS_PER_STAGE = 5
GREEDY_RUNS_PER_INVOCATION = 1
GREEDY_SUPPORTS_RUNS_OPTION = False
GREEDY_SLA_LATENCY_THRESHOLD_MS = 80.0
GREEDY_EQUILIBRIUM_THRESHOLD = 0.04
GREEDY_OUTCOME_LATENCY_MODE = "physical-only-v1"
GREEDY_PHYSICAL_JITTER_MODE = "half-normal-additive-v1"
GREEDY_OBSERVATION_JITTER_MODE = "half-normal-observation-v1"
GREEDY_PAIR_TELEMETRY_MODE = "measured-consecutive-pairs-raw-v1"
GREEDY_LEARNING_SCOPE = "selected-hops-only"

PHYSICAL_JITTER_MS_BY_STATE = (6.0, 5.25, 4.0, 3.25)
OBSERVATION_JITTER_MS_BY_STATE = (7.2, 6.3, 4.8, 3.9)

POLICY_VISIBLE_INPUT_FIELDS = frozenset(
    {
        "flow_id",
        "stage",
        "replica_id",
        "ready",
        "max_assigned_flows",
        "belief",
        "current_load",
    }
)
POLICY_FORBIDDEN_INPUT_FIELDS = frozenset(
    {
        "hidden_state",
        "profile_seed",
        "physical_seed",
        "observation_seed",
        "planning_link_cost_ms",
        "measured_pair_latency_ms",
    }
)

EXCLUDED_SELECTION_FEATURES = frozenset(
    {
        "recursion",
        "future-flow-simulation",
        "candidate-pruning",
        "local-search",
        "lookahead",
        "monte-carlo",
        "bandit",
        "milp",
        "link-cost-selection-term",
    }
)


def _require_positive_int(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise TypeError(f"{name} must be an integer")
    if value < 1:
        raise ValueError(f"{name} must be positive")
    return int(value)


@dataclass(frozen=True)
class GreedyTopologyFixture:
    """A uniform, contiguous topology with a fixed two-stage action budget."""

    flow_count: int
    stage_count: int
    replicas_per_stage: int

    def __post_init__(self) -> None:
        for name in ("flow_count", "stage_count", "replicas_per_stage"):
            object.__setattr__(self, name, _require_positive_int(name, getattr(self, name)))
        if self.stage_count < GREEDY_SELECTION_BUDGET:
            raise ValueError("stage_count must be at least the two-stage selection budget")

    @property
    def stages(self) -> tuple[int, ...]:
        return tuple(range(1, self.stage_count + 1))

    @property
    def replicas(self) -> tuple[int, ...]:
        return tuple(range(1, self.replicas_per_stage + 1))

    @property
    def identities(self) -> tuple[tuple[int, int], ...]:
        return tuple(
            (stage, replica)
            for stage in self.stages
            for replica in self.replicas
        )

    @property
    def admission_capacity_per_replica(self) -> int:
        return ceil(self.flow_count / self.replicas_per_stage)

    @property
    def expected_route_count(self) -> int:
        return self.flow_count

    @property
    def expected_selected_observation_count(self) -> int:
        return self.flow_count * GREEDY_SELECTION_BUDGET

    @property
    def expected_consecutive_pair_count(self) -> int:
        return self.flow_count * (GREEDY_SELECTION_BUDGET - 1)

    @property
    def bypassed_stages_per_action(self) -> int:
        return self.stage_count - GREEDY_SELECTION_BUDGET


ReplicaIdentity = tuple[int, int]
BudgetedAction = tuple[ReplicaIdentity, ReplicaIdentity]


def _require_canonical_action(action: BudgetedAction) -> BudgetedAction:
    if len(action) != GREEDY_SELECTION_BUDGET:
        raise ValueError("an action must select exactly two replicas")
    first, second = action
    if first[0] >= second[0]:
        raise ValueError("selected stages must be distinct and increasing")
    if any(stage < 1 or replica < 1 for stage, replica in action):
        raise ValueError("action identities must be positive")
    return action


@dataclass(frozen=True)
class GreedyDecisionFixture:
    """One already-scored joint L=2 action decision."""

    name: str
    current_loads: tuple[tuple[ReplicaIdentity, int], ...]
    scores_at_projected_load: tuple[tuple[BudgetedAction, float], ...]
    feasible_actions: tuple[BudgetedAction, ...]
    expected_action: BudgetedAction | None
    expected_failure: str | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("fixture name must not be empty")
        identities = tuple(identity for identity, _load in self.current_loads)
        actions = tuple(action for action, _score in self.scores_at_projected_load)
        if identities != tuple(sorted(set(identities))):
            raise ValueError("loads must cover unique canonical replica identities")
        if actions != tuple(sorted(set(actions))):
            raise ValueError("scores must cover unique canonical actions")
        for action in actions:
            _require_canonical_action(action)
            if not set(action).issubset(identities):
                raise ValueError("scored action contains an unknown replica identity")
        if any(load < 0 for _identity, load in self.current_loads):
            raise ValueError("current loads must be nonnegative")
        if any(not isfinite(float(score)) for _action, score in self.scores_at_projected_load):
            raise ValueError("scores must be finite")
        if tuple(sorted(set(self.feasible_actions))) != self.feasible_actions:
            raise ValueError("feasible actions must be unique and canonical")
        if not set(self.feasible_actions).issubset(actions):
            raise ValueError("feasible actions must have scores")
        if self.feasible_actions:
            if self.expected_failure is not None:
                raise ValueError("a feasible fixture cannot expect failure")
            if self.expected_action not in self.feasible_actions:
                raise ValueError("expected action must be feasible")
        elif self.expected_action is not None or self.expected_failure is None:
            raise ValueError("an empty feasible set must expect explicit failure")

    def projected_loads_for(
        self,
        action: BudgetedAction,
    ) -> tuple[tuple[ReplicaIdentity, int], ...]:
        _require_canonical_action(action)
        loads = dict(self.current_loads)
        return tuple((identity, loads[identity] + 1) for identity in action)

    def assert_contract_winner(self) -> None:
        """Validate the frozen expected result without serving as production policy."""
        if not self.feasible_actions:
            if self.expected_failure != "no-feasible-action":
                raise AssertionError("empty feasibility must fail the decision")
            return
        scores = dict(self.scores_at_projected_load)
        expected = min(
            self.feasible_actions,
            key=lambda action: (-scores[action], action),
        )
        if self.expected_action != expected:
            raise AssertionError(
                f"{self.name}: expected action {self.expected_action}, contract chooses {expected}"
            )


@dataclass(frozen=True)
class GreedySelectionStepFixture:
    flow_id: int
    before_loads: tuple[tuple[ReplicaIdentity, int], ...]
    selected_action: BudgetedAction
    after_loads: tuple[tuple[ReplicaIdentity, int], ...]

    def assert_single_sequential_action_mutation(self) -> None:
        _require_positive_int("flow_id", self.flow_id)
        _require_canonical_action(self.selected_action)
        before = dict(self.before_loads)
        after = dict(self.after_loads)
        if tuple(before) != tuple(after):
            raise AssertionError("load vectors must cover the same canonical identities")
        expected = dict(before)
        for identity in self.selected_action:
            expected[identity] += 1
        if expected != after:
            raise AssertionError("a step must increment exactly its two selected replicas")


@dataclass(frozen=True)
class GreedySlotShapeFixture:
    topology: GreedyTopologyFixture
    flow_order: tuple[int, ...]
    routes: tuple[tuple[int, tuple[tuple[int, int], ...]], ...]
    bypassed_stages: tuple[tuple[int, tuple[int, ...]], ...]
    observation_identities: tuple[tuple[int, int, int], ...]
    pair_identities: tuple[tuple[int, tuple[int, int], tuple[int, int]], ...]

    def assert_complete(self) -> None:
        expected_flows = set(range(1, self.topology.flow_count + 1))
        if set(self.flow_order) != expected_flows or len(self.flow_order) != len(expected_flows):
            raise AssertionError("flow order must be a permutation of every configured flow")
        if tuple(flow for flow, _route in self.routes) != self.flow_order:
            raise AssertionError("routes must retain deterministic flow order")
        if tuple(flow for flow, _stages in self.bypassed_stages) != self.flow_order:
            raise AssertionError("bypass records must retain deterministic flow order")
        if len(self.routes) != self.topology.expected_route_count:
            raise AssertionError("a slot must contain N routes")

        selected = set()
        expected_pairs = set()
        bypass_by_flow = dict(self.bypassed_stages)
        for flow, route in self.routes:
            stages = tuple(stage for stage, _replica in route)
            if len(route) != GREEDY_SELECTION_BUDGET:
                raise AssertionError("every route must select exactly two stages")
            if stages != tuple(sorted(set(stages))):
                raise AssertionError("selected stages must be distinct and increasing")
            if any(identity not in self.topology.identities for identity in route):
                raise AssertionError("route contains an unknown replica identity")
            expected_bypasses = tuple(
                stage for stage in self.topology.stages if stage not in stages
            )
            if bypass_by_flow[flow] != expected_bypasses:
                raise AssertionError("bypasses must cover every unselected stage")
            if len(expected_bypasses) != self.topology.bypassed_stages_per_action:
                raise AssertionError("every action must bypass exactly K-L stages")
            selected.update((flow, stage, replica) for stage, replica in route)
            expected_pairs.update(
                (flow, route[index], route[index + 1])
                for index in range(len(route) - 1)
            )

        if len(self.observation_identities) != self.topology.expected_selected_observation_count:
            raise AssertionError("a slot must contain N*L selected observations")
        if set(self.observation_identities) != selected:
            raise AssertionError("observations must cover selected hops exactly")
        if len(self.pair_identities) != self.topology.expected_consecutive_pair_count:
            raise AssertionError("a slot must contain N*(L-1) selected pairs")
        if set(self.pair_identities) != expected_pairs:
            raise AssertionError("pair telemetry must cover consecutive selected hops exactly")


class CompatibilityDisposition(str, Enum):
    REUSE = "reuse"
    ADAPT = "adapt-behind-greedy-boundary"
    EXCLUDE = "exclude"


@dataclass(frozen=True)
class CompatibilityEntry:
    component: str
    source: str
    disposition: CompatibilityDisposition
    greedy_boundary: str
    reason: str


GREEDY_HYBRID_COMPATIBILITY_MATRIX = (
    CompatibilityEntry(
        "physical and observation latency laws",
        "IBG.latency_model",
        CompatibilityDisposition.REUSE,
        "shared pure latency functions",
        "The active separated half-normal laws and exact convolved likelihood are policy-neutral.",
    ),
    CompatibilityEntry(
        "belief-driven expected stage utility",
        "IBG_Hybrid.expected_utility",
        CompatibilityDisposition.ADAPT,
        "Greedy-owned thin expected-utility adapter over IBG.latency_model",
        "The formula is policy-neutral, but Greedy must not depend on a Hybrid policy namespace.",
    ),
    CompatibilityEntry(
        "selected-only posterior aggregation",
        "IBG.learning and frozen IBG Replica updates",
        CompatibilityDisposition.REUSE,
        "shared learning port",
        "Only selected observations enter the active learner.",
    ),
    CompatibilityEntry(
        "outcome latency mode",
        "IBG.outcome_latency",
        CompatibilityDisposition.REUSE,
        "shared physical-only outcome selector",
        "Observation-only jitter remains excluded from realized utility.",
    ),
    CompatibilityEntry(
        "SLA count and excess",
        "IBG.report.SLA_v and IBG_Hybrid.runner metric assembly",
        CompatibilityDisposition.ADAPT,
        "Greedy-owned metric assembly",
        "Count is reusable; 80-ms raw-chain composition and unrounded excess need a Greedy-owned K-stage boundary.",
    ),
    CompatibilityEntry(
        "Jain fairness",
        "IBG.header.jain_index",
        CompatibilityDisposition.REUSE,
        "shared metric helper with compatibility test",
        "The formula is independent of policy choice.",
    ),
    CompatibilityEntry(
        "equilibrium predicate",
        "IBG.header.is_equilibrium",
        CompatibilityDisposition.ADAPT,
        "Greedy-owned call with threshold 0.04",
        "The strict predicate is reusable only with the Hybrid-compatible threshold override.",
    ),
    CompatibilityEntry(
        "route, observation, and pair schemas",
        "IBG_Hybrid.slot_contracts",
        CompatibilityDisposition.ADAPT,
        "Greedy-owned budgeted L=2 schemas",
        "The action shape matches Hybrid, but Greedy omits Hybrid activation and policy-specific fields.",
    ),
    CompatibilityEntry(
        "flow-order isolation",
        "IBG_Hybrid.runner",
        CompatibilityDisposition.ADAPT,
        "Greedy-owned explicit flow-order input",
        "Flow order must be deterministic and independent from policy and profile RNG streams.",
    ),
    CompatibilityEntry(
        "Hybrid pruning, lookahead, Monte Carlo, and pair-aware selection",
        "IBG_Hybrid.policy",
        CompatibilityDisposition.EXCLUDE,
        "none",
        "These mechanisms contradict the pure immediate joint-action baseline.",
    ),
    CompatibilityEntry(
        "legacy Greedy budgeted and stochastic grid solvers",
        "Greedy.budgeted and Greedy.claude",
        CompatibilityDisposition.EXCLUDE,
        "Phase 0 characterization only",
        "Their L=2 shape is reference material, but stochastic grids and stale semantics are excluded.",
    ),
)


CANONICAL_COMPARISON_TOPOLOGY_FIXTURE = GreedyTopologyFixture(
    flow_count=GREEDY_CANONICAL_COMPARISON_FLOW_COUNT,
    stage_count=GREEDY_CANONICAL_COMPARISON_STAGE_COUNT,
    replicas_per_stage=GREEDY_CANONICAL_COMPARISON_REPLICAS_PER_STAGE,
)

# This deliberately smaller topology keeps the hand-checked route fixture
# reviewable. It is neither a runtime default nor the comparison topology.
SMALL_HAND_CHECKED_TOPOLOGY_FIXTURE = GreedyTopologyFixture(
    flow_count=3,
    stage_count=3,
    replicas_per_stage=2,
)

_A = ((1, 1), (2, 1))
_B = ((1, 1), (3, 1))
_C = ((2, 1), (3, 2))
_CANONICAL_LOADS = (
    ((1, 1), 0),
    ((1, 2), 0),
    ((2, 1), 0),
    ((2, 2), 0),
    ((3, 1), 0),
    ((3, 2), 0),
)

CANONICAL_DECISION_FIXTURES = (
    GreedyDecisionFixture(
        name="lowest-canonical-action-exact-tie",
        current_loads=_CANONICAL_LOADS,
        scores_at_projected_load=((_A, 5.0), (_B, 5.0), (_C, 4.0)),
        feasible_actions=(_A, _B, _C),
        expected_action=_A,
    ),
    GreedyDecisionFixture(
        name="best-non-positive-is-still-selected",
        current_loads=_CANONICAL_LOADS,
        scores_at_projected_load=((_A, -4.0), (_B, -1.0), (_C, -2.0)),
        feasible_actions=(_A, _B, _C),
        expected_action=_B,
    ),
    GreedyDecisionFixture(
        name="capacity-removes-higher-scoring-action",
        current_loads=(
            ((1, 1), 2),
            ((1, 2), 0),
            ((2, 1), 1),
            ((2, 2), 0),
            ((3, 1), 0),
            ((3, 2), 1),
        ),
        scores_at_projected_load=((_A, 100.0), (_B, 90.0), (_C, 1.0)),
        feasible_actions=(_C,),
        expected_action=_C,
    ),
    GreedyDecisionFixture(
        name="empty-feasible-set-fails",
        current_loads=tuple((identity, 2) for identity, _load in _CANONICAL_LOADS),
        scores_at_projected_load=((_A, 100.0), (_B, 90.0), (_C, 80.0)),
        feasible_actions=(),
        expected_action=None,
        expected_failure="no-feasible-action",
    ),
)

_ZERO_LOADS = _CANONICAL_LOADS
_AFTER_FIRST = (
    ((1, 1), 1),
    ((1, 2), 0),
    ((2, 1), 0),
    ((2, 2), 0),
    ((3, 1), 0),
    ((3, 2), 1),
)
_AFTER_SECOND = (
    ((1, 1), 1),
    ((1, 2), 1),
    ((2, 1), 1),
    ((2, 2), 0),
    ((3, 1), 0),
    ((3, 2), 1),
)
_AFTER_THIRD = (
    ((1, 1), 1),
    ((1, 2), 1),
    ((2, 1), 1),
    ((2, 2), 1),
    ((3, 1), 1),
    ((3, 2), 1),
)

SEQUENTIAL_LOAD_FIXTURE = (
    GreedySelectionStepFixture(2, _ZERO_LOADS, ((1, 1), (3, 2)), _AFTER_FIRST),
    GreedySelectionStepFixture(1, _AFTER_FIRST, ((1, 2), (2, 1)), _AFTER_SECOND),
    GreedySelectionStepFixture(3, _AFTER_SECOND, ((2, 2), (3, 1)), _AFTER_THIRD),
)

CANONICAL_SLOT_FIXTURE = GreedySlotShapeFixture(
    topology=SMALL_HAND_CHECKED_TOPOLOGY_FIXTURE,
    flow_order=(2, 1, 3),
    routes=(
        (2, ((1, 1), (3, 2))),
        (1, ((1, 2), (2, 1))),
        (3, ((2, 2), (3, 1))),
    ),
    bypassed_stages=((2, (2,)), (1, (3,)), (3, (1,))),
    observation_identities=(
        (2, 1, 1),
        (2, 3, 2),
        (1, 1, 2),
        (1, 2, 1),
        (3, 2, 2),
        (3, 3, 1),
    ),
    pair_identities=(
        (2, (1, 1), (3, 2)),
        (1, (1, 2), (2, 1)),
        (3, (2, 2), (3, 1)),
    ),
)


def raw_end_to_end_sla_fixture(
    raw_latency_ms_per_flow: Mapping[int, float],
) -> tuple[int, float]:
    """Tiny fixture for strict 80-ms count and unrounded excess semantics."""
    values = tuple(float(raw_latency_ms_per_flow[flow]) for flow in sorted(raw_latency_ms_per_flow))
    if any(not isfinite(value) or value < 0 for value in values):
        raise ValueError("raw latency values must be finite and nonnegative")
    return (
        sum(value > GREEDY_SLA_LATENCY_THRESHOLD_MS for value in values),
        sum(max(0.0, value - GREEDY_SLA_LATENCY_THRESHOLD_MS) for value in values),
    )


def strict_equilibrium_fixture(maximum_belief_change: float) -> bool:
    value = float(maximum_belief_change)
    if not isfinite(value) or value < 0:
        raise ValueError("maximum belief change must be finite and nonnegative")
    return value < GREEDY_EQUILIBRIUM_THRESHOLD
