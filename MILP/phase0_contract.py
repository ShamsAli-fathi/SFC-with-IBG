"""Versioned mathematical contract for the coupled MILP baseline.

This module intentionally contains no solver integration.  It freezes the
indices, information boundary, objective reconstruction, feasibility rules,
time-limit semantics, and result provenance that later MILP phases must
implement.  Importing it performs no experiment, logging, random seeding, or
filesystem I/O.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum
from math import isclose, isfinite
from numbers import Integral, Real
from typing import Callable, Mapping


MILP_PHASE0_CONTRACT_VERSION = "milp-coupled-phase0-contract-v1"
MILP_ACTION_CARDINALITY = 2
MILP_PLANNING_LINK_WEIGHT_UTILITY_PER_MS = 1.0
MILP_DIMENSION_CONFIGURATION_MODE = "runtime-configurable-dimensions-v1"
MILP_DIMENSION_CLI_OPTIONS = ("--flow", "--stage", "--replica")

MILLISECONDS_UNIT = "milliseconds"
UTILITY_UNIT = "utility-units"
ASSIGNED_FLOW_CAPACITY_UNIT = "assigned-flows-per-slot"
CUTOFF_UNIT = "wall-clock-seconds"
GAP_UNIT = "dimensionless"
MILP_GAP_NORMALIZATION = (
    "absolute=abs(best_bound-incumbent); "
    "relative=absolute/max(1,abs(incumbent))"
)

PAPER_MILP_BACKEND = "Gurobi"
PAPER_MILP_BACKEND_VERSION = "10.0"
DEVELOPMENT_BACKEND_FAMILY = "scipy.optimize.milp/HiGHS"


class MILPContractError(ValueError):
    """Raised when data violates the Phase 0 MILP contract."""


def _positive_integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value <= 0:
        raise MILPContractError(f"{field} must be a positive integer")
    return int(value)


def _finite_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise MILPContractError(f"{field} must be a finite real number")
    result = float(value)
    if not isfinite(result):
        raise MILPContractError(f"{field} must be a finite real number")
    return result


def validate_cutoff_seconds(value: object) -> float:
    """Validate the per-run solver cutoff without rounding or clamping it."""

    cutoff = _finite_number(value, "cutoff seconds")
    if cutoff <= 0.0:
        raise MILPContractError("cutoff seconds must be strictly positive")
    return cutoff


def normalized_solver_gaps(incumbent: object, best_bound: object) -> tuple[float, float]:
    """Normalize maximization gaps independently of backend conventions."""

    incumbent_value = _finite_number(incumbent, "incumbent objective")
    bound_value = _finite_number(best_bound, "best bound")
    absolute = abs(bound_value - incumbent_value)
    relative = absolute / max(1.0, abs(incumbent_value))
    return absolute, relative


@dataclass(frozen=True, order=True)
class ReplicaKey:
    """One-based stage/replica identity with canonical tuple ordering."""

    stage: int
    replica: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "stage", _positive_integer(self.stage, "stage"))
        object.__setattr__(
            self,
            "replica",
            _positive_integer(self.replica, "replica"),
        )


@dataclass(frozen=True)
class MILPDimensions:
    """One-based runtime dimensions for the whole-slot formulation."""

    flow_count: int = 15
    replicas_per_stage: tuple[int, ...] = (10, 10, 10)
    selected_stage_count: int = MILP_ACTION_CARDINALITY

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "flow_count",
            _positive_integer(self.flow_count, "flow_count"),
        )
        if not isinstance(self.replicas_per_stage, tuple):
            raise MILPContractError("replicas_per_stage must be an immutable tuple")
        if len(self.replicas_per_stage) < MILP_ACTION_CARDINALITY:
            raise MILPContractError("at least two stages are required")
        normalized = tuple(
            _positive_integer(value, f"replicas_per_stage[{index}]")
            for index, value in enumerate(self.replicas_per_stage, start=1)
        )
        object.__setattr__(self, "replicas_per_stage", normalized)
        selected = _positive_integer(
            self.selected_stage_count,
            "selected_stage_count",
        )
        if selected != MILP_ACTION_CARDINALITY:
            raise MILPContractError(
                f"only exact L={MILP_ACTION_CARDINALITY} is supported"
            )
        if selected > len(normalized):
            raise MILPContractError("selected_stage_count exceeds stage count")
        object.__setattr__(self, "selected_stage_count", selected)

    @property
    def stage_count(self) -> int:
        return len(self.replicas_per_stage)

    @property
    def total_replica_count(self) -> int:
        return sum(self.replicas_per_stage)

    @property
    def flow_ids(self) -> tuple[int, ...]:
        return tuple(range(1, self.flow_count + 1))

    @property
    def stage_ids(self) -> tuple[int, ...]:
        return tuple(range(1, self.stage_count + 1))

    @property
    def replica_keys(self) -> tuple[ReplicaKey, ...]:
        return tuple(
            ReplicaKey(stage, replica)
            for stage, count in enumerate(self.replicas_per_stage, start=1)
            for replica in range(1, count + 1)
        )

    def validate_replica_key(self, key: ReplicaKey) -> None:
        if key.stage > self.stage_count:
            raise MILPContractError(f"stage {key.stage} is out of range")
        maximum = self.replicas_per_stage[key.stage - 1]
        if key.replica > maximum:
            raise MILPContractError(
                f"replica {key.replica} is out of range for stage {key.stage}"
            )


DEFAULT_MILP_DIMENSIONS = MILPDimensions()
"""Initial 15-flow/3-stage/10-replica-per-stage run profile, not a limit."""


@dataclass(frozen=True)
class TwoStageAction:
    """Canonical exact-L=2 action for one flow."""

    selections: tuple[ReplicaKey, ReplicaKey]

    def __post_init__(self) -> None:
        if not isinstance(self.selections, tuple) or len(self.selections) != 2:
            raise MILPContractError("an action must contain exactly two selections")
        first, second = self.selections
        if not isinstance(first, ReplicaKey) or not isinstance(second, ReplicaKey):
            raise MILPContractError("action selections must be ReplicaKey values")
        if first.stage == second.stage:
            raise MILPContractError("selected stages must be distinct")
        if not first < second:
            raise MILPContractError(
                "action selections must use canonical stage/replica ordering"
            )

    @classmethod
    def canonical(cls, first: ReplicaKey, second: ReplicaKey) -> TwoStageAction:
        return cls(tuple(sorted((first, second))))  # type: ignore[arg-type]

    @property
    def directed_pair(self) -> tuple[ReplicaKey, ReplicaKey]:
        return self.selections

    def validate(self, dimensions: MILPDimensions) -> None:
        for key in self.selections:
            dimensions.validate_replica_key(key)

    def bypassed_stages(self, dimensions: MILPDimensions) -> tuple[int, ...]:
        self.validate(dimensions)
        selected = {key.stage for key in self.selections}
        return tuple(stage for stage in dimensions.stage_ids if stage not in selected)


@dataclass(frozen=True)
class ReplicaAdmission:
    ready: bool
    assigned_flow_capacity: int

    def __post_init__(self) -> None:
        if not isinstance(self.ready, bool):
            raise MILPContractError("ready must be boolean")
        if (
            isinstance(self.assigned_flow_capacity, bool)
            or not isinstance(self.assigned_flow_capacity, Integral)
            or self.assigned_flow_capacity < 0
        ):
            raise MILPContractError(
                "assigned_flow_capacity must be a nonnegative integer"
            )
        object.__setattr__(
            self,
            "assigned_flow_capacity",
            int(self.assigned_flow_capacity),
        )


DirectedPair = tuple[ReplicaKey, ReplicaKey]


def required_directed_pairs(dimensions: MILPDimensions) -> tuple[DirectedPair, ...]:
    """Return every possible lower-stage to higher-stage planning pair."""

    keys_by_stage = {
        stage: tuple(key for key in dimensions.replica_keys if key.stage == stage)
        for stage in dimensions.stage_ids
    }
    return tuple(
        (source, target)
        for source_stage in dimensions.stage_ids
        for source in keys_by_stage[source_stage]
        for target_stage in dimensions.stage_ids
        if source_stage < target_stage
        for target in keys_by_stage[target_stage]
    )


def validate_admission_metadata(
    dimensions: MILPDimensions,
    admission: Mapping[ReplicaKey, ReplicaAdmission],
) -> None:
    expected = set(dimensions.replica_keys)
    actual = set(admission)
    missing = tuple(sorted(expected - actual))
    extra = tuple(sorted(actual - expected))
    if missing or extra:
        raise MILPContractError(
            f"admission metadata mismatch: missing={missing}, extra={extra}"
        )
    for key in dimensions.replica_keys:
        if not isinstance(admission[key], ReplicaAdmission):
            raise MILPContractError(f"invalid admission metadata for {key}")


def validate_planning_link_metadata(
    dimensions: MILPDimensions,
    planning_link_cost_ms: Mapping[DirectedPair, float],
) -> None:
    expected = set(required_directed_pairs(dimensions))
    actual = set(planning_link_cost_ms)
    missing = tuple(sorted(expected - actual))
    extra = tuple(sorted(actual - expected))
    if missing or extra:
        raise MILPContractError(
            f"planning-link metadata mismatch: missing={missing}, extra={extra}"
        )
    for pair in sorted(expected):
        value = _finite_number(planning_link_cost_ms[pair], f"link cost {pair}")
        if value < 0.0:
            raise MILPContractError(f"link cost {pair} must be nonnegative")


def _validate_placement_flow_ids(
    dimensions: MILPDimensions,
    actions: Mapping[int, TwoStageAction],
) -> None:
    expected = set(dimensions.flow_ids)
    actual = set(actions)
    if any(isinstance(flow_id, bool) or not isinstance(flow_id, Integral) for flow_id in actual):
        raise MILPContractError("flow IDs must be integers")
    missing = tuple(sorted(expected - actual))
    extra = tuple(sorted(actual - expected))
    if missing or extra:
        raise MILPContractError(
            f"placement flow IDs mismatch: missing={missing}, extra={extra}"
        )


def final_replica_loads(
    dimensions: MILPDimensions,
    actions: Mapping[int, TwoStageAction],
) -> tuple[tuple[ReplicaKey, int], ...]:
    """Reconstruct final whole-slot loads in canonical replica order."""

    _validate_placement_flow_ids(dimensions, actions)
    counts: Counter[ReplicaKey] = Counter()
    for flow_id in dimensions.flow_ids:
        action = actions[flow_id]
        if not isinstance(action, TwoStageAction):
            raise MILPContractError(f"flow {flow_id} has an invalid action")
        action.validate(dimensions)
        counts.update(action.selections)
    return tuple((key, counts[key]) for key in dimensions.replica_keys)


@dataclass(frozen=True)
class FeasibilityResult:
    feasible: bool
    reasons: tuple[str, ...]
    final_loads: tuple[tuple[ReplicaKey, int], ...]

    def __post_init__(self) -> None:
        if self.feasible != (not self.reasons):
            raise MILPContractError("feasible must be equivalent to no rejection reasons")


def evaluate_placement_feasibility(
    dimensions: MILPDimensions,
    actions: Mapping[int, TwoStageAction],
    admission: Mapping[ReplicaKey, ReplicaAdmission],
    planning_link_cost_ms: Mapping[DirectedPair, float],
) -> FeasibilityResult:
    """Evaluate the complete whole-slot placement against Phase 0 rules."""

    validate_admission_metadata(dimensions, admission)
    validate_planning_link_metadata(dimensions, planning_link_cost_ms)
    loads = final_replica_loads(dimensions, actions)
    load_by_key = dict(loads)
    reasons: list[str] = []
    for key in dimensions.replica_keys:
        metadata = admission[key]
        load = load_by_key[key]
        if load and not metadata.ready:
            reasons.append(f"not-ready:{key.stage}:{key.replica}")
        if load > metadata.assigned_flow_capacity:
            reasons.append(f"assigned-flow-capacity:{key.stage}:{key.replica}")
    return FeasibilityResult(not reasons, tuple(reasons), loads)


KnownStateExpectedUtility = Callable[[ReplicaKey, int], float]


@dataclass(frozen=True)
class FlowObjectiveContribution:
    flow_id: int
    action: TwoStageAction
    stage_utility: float
    planning_link_cost_ms: float
    total_utility: float


@dataclass(frozen=True)
class SocialWelfareBreakdown:
    final_loads: tuple[tuple[ReplicaKey, int], ...]
    flows: tuple[FlowObjectiveContribution, ...]
    stage_welfare_utility: float
    planning_link_cost_ms: float
    total_social_welfare_utility: float


def reconstruct_social_welfare(
    dimensions: MILPDimensions,
    actions: Mapping[int, TwoStageAction],
    known_state_expected_utility: KnownStateExpectedUtility,
    planning_link_cost_ms: Mapping[DirectedPair, float],
) -> SocialWelfareBreakdown:
    """Evaluate all selected stages at final loads and deduct one link/flow.

    The utility callback represents deterministic expected physical utility
    under the MILP planner's authorized true replica state.  Observation-only
    jitter and measured pair outcomes are deliberately absent from this API.
    """

    validate_planning_link_metadata(dimensions, planning_link_cost_ms)
    loads = final_replica_loads(dimensions, actions)
    load_by_key = dict(loads)
    contributions: list[FlowObjectiveContribution] = []
    for flow_id in dimensions.flow_ids:
        action = actions[flow_id]
        stage_utility = sum(
            _finite_number(
                known_state_expected_utility(key, load_by_key[key]),
                f"known-state utility for {key} at load {load_by_key[key]}",
            )
            for key in action.selections
        )
        link_cost = _finite_number(
            planning_link_cost_ms[action.directed_pair],
            f"link cost for flow {flow_id}",
        )
        total = stage_utility - (
            MILP_PLANNING_LINK_WEIGHT_UTILITY_PER_MS * link_cost
        )
        contributions.append(
            FlowObjectiveContribution(
                flow_id=flow_id,
                action=action,
                stage_utility=stage_utility,
                planning_link_cost_ms=link_cost,
                total_utility=total,
            )
        )
    stage_total = sum(item.stage_utility for item in contributions)
    link_total = sum(item.planning_link_cost_ms for item in contributions)
    return SocialWelfareBreakdown(
        final_loads=loads,
        flows=tuple(contributions),
        stage_welfare_utility=stage_total,
        planning_link_cost_ms=link_total,
        total_social_welfare_utility=(
            stage_total
            - MILP_PLANNING_LINK_WEIGHT_UTILITY_PER_MS * link_total
        ),
    )


@dataclass(frozen=True)
class InformationBoundary:
    planner_inputs: tuple[str, ...]
    prohibited_planner_inputs: tuple[str, ...]
    outcome_only_values: tuple[str, ...]


MILP_INFORMATION_BOUNDARY = InformationBoundary(
    planner_inputs=(
        "complete-slot-flow-set",
        "replica-true-performance-state",
        "state-load-conditioned-expected-physical-utility",
        "replica-ready-availability",
        "replica-assigned-flow-capacity",
        "configured-directed-planning-link-cost-ms",
        "per-run-cutoff-seconds",
    ),
    prohibited_planner_inputs=(
        "belief-vectors",
        "private-learning-signals",
        "posterior-or-aggregated-beliefs",
        "sequential-flow-order",
        "lookahead-or-rollout-state",
        "bandit-state",
        "observation-only-jitter",
        "measured-pair-latency",
        "raw-http-or-kubernetes-telemetry",
    ),
    outcome_only_values=(
        "physical-processing-samples",
        "observation-only-jitter",
        "measured-selected-pair-latency",
        "raw-end-to-end-latency",
        "physical-only-sla-outcome",
    ),
)


@dataclass(frozen=True)
class VariableFamily:
    symbol: str
    domain: str
    indices: str
    meaning: str


MILP_VARIABLE_FAMILIES = (
    VariableFamily(
        "x[i,k,j]",
        "binary",
        "i=1..N, k=1..K, j=1..M_k",
        "flow i is assigned to replica (k,j)",
    ),
    VariableFamily(
        "y[i,k]",
        "binary",
        "i=1..N, k=1..K",
        "flow i selects stage k",
    ),
    VariableFamily(
        "z[k,j,n]",
        "binary",
        "k=1..K, j=1..M_k, n=0..N",
        "replica (k,j) has final assigned load n",
    ),
    VariableFamily(
        "p[i,k,j,k2,j2]",
        "binary",
        "i=1..N, 1<=k<k2<=K, j=1..M_k, j2=1..M_k2",
        "flow i selects the directed lower-stage/higher-stage replica pair",
    ),
)


@dataclass(frozen=True)
class ConstraintFamily:
    name: str
    mathematical_contract: str


MILP_CONSTRAINT_FAMILIES = (
    ConstraintFamily(
        "exact-stage-cardinality",
        "sum_k y[i,k] = L = 2 for every flow i",
    ),
    ConstraintFamily(
        "one-replica-per-selected-stage",
        "sum_j x[i,k,j] = y[i,k] for every flow i and stage k",
    ),
    ConstraintFamily(
        "ready-availability",
        "x[i,k,j] <= ready[k,j] for every placement variable",
    ),
    ConstraintFamily(
        "declared-assigned-flow-capacity",
        "sum_i x[i,k,j] <= capacity[k,j] in assigned-flows-per-slot",
    ),
    ConstraintFamily(
        "one-final-load-indicator",
        "sum_n z[k,j,n] = 1 for every replica, including n=0",
    ),
    ConstraintFamily(
        "final-load-reconstruction",
        "sum_i x[i,k,j] = sum_n n*z[k,j,n] for every replica",
    ),
    ConstraintFamily(
        "directed-pair-linearization",
        "p<=x_left, p<=x_right, p>=x_left+x_right-1 for every pair",
    ),
    ConstraintFamily(
        "one-selected-directed-pair",
        "sum_{k<k2,j,j2} p[i,k,j,k2,j2] = 1 for every flow i",
    ),
    ConstraintFamily(
        "planning-link-input-completeness",
        "every structurally possible directed pair has one finite nonnegative configured cost",
    ),
)


MILP_OBJECTIVE_CONTRACT = (
    "maximize sum_{k,j,n} n*U_true_state[k,j,n]*z[k,j,n] "
    "minus sum_{i,k<k2,j,j2} link_ms[k,j,k2,j2]*p[i,k,j,k2,j2]"
)

MILP_DETERMINISM_CONTRACT = (
    "Indices and extracted records are ordered lexicographically by flow, stage, "
    "and replica. A backend's arbitrary choice among symmetric optimal placements "
    "is not canonical evidence; later extraction must use a documented deterministic "
    "secondary solve or canonicalization that preserves the primary objective, never "
    "an unversioned epsilon perturbation."
)


class SolverResultStatus(str, Enum):
    PROVEN_OPTIMAL = "proven-optimal"
    TIME_LIMIT_WITH_INCUMBENT = "time-limit-with-feasible-incumbent"
    TIME_LIMIT_WITHOUT_INCUMBENT = "time-limit-without-incumbent"
    INFEASIBLE = "infeasible"
    UNBOUNDED = "unbounded"
    SOLVER_OR_CONFIGURATION_ERROR = "solver-or-configuration-error"


@dataclass(frozen=True)
class SolverRunProvenance:
    status: SolverResultStatus
    requested_cutoff_seconds: float
    model_build_seconds: float
    solve_seconds: float
    backend_name: str
    backend_version: str
    termination_reason: str
    incumbent_objective_utility: float | None = None
    best_bound_utility: float | None = None
    absolute_gap_utility: float | None = None
    relative_gap: float | None = None
    variable_count: int | None = None
    constraint_count: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, SolverResultStatus):
            raise MILPContractError("status must be a SolverResultStatus")
        object.__setattr__(
            self,
            "requested_cutoff_seconds",
            validate_cutoff_seconds(self.requested_cutoff_seconds),
        )
        for field in ("model_build_seconds", "solve_seconds"):
            value = _finite_number(getattr(self, field), field)
            if value < 0.0:
                raise MILPContractError(f"{field} must be nonnegative")
            object.__setattr__(self, field, value)
        for field in ("backend_name", "backend_version", "termination_reason"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise MILPContractError(f"{field} must be a nonempty string")
        for field in ("variable_count", "constraint_count"):
            value = getattr(self, field)
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, Integral)
                or value < 0
            ):
                raise MILPContractError(f"{field} must be a nonnegative integer")
            if value is not None:
                object.__setattr__(self, field, int(value))
        for field in (
            "incumbent_objective_utility",
            "best_bound_utility",
            "absolute_gap_utility",
            "relative_gap",
        ):
            value = getattr(self, field)
            if value is not None:
                value = _finite_number(value, field)
                if field in ("absolute_gap_utility", "relative_gap") and value < 0.0:
                    raise MILPContractError(f"{field} must be nonnegative")
                object.__setattr__(self, field, value)
        self._validate_status_payload()

    @property
    def optimality_proven(self) -> bool:
        return self.status is SolverResultStatus.PROVEN_OPTIMAL

    def _validate_status_payload(self) -> None:
        has_incumbent = self.incumbent_objective_utility is not None
        has_bound = self.best_bound_utility is not None
        has_gaps = (
            self.absolute_gap_utility is not None and self.relative_gap is not None
        )
        partial_gaps = (self.absolute_gap_utility is None) != (self.relative_gap is None)
        if partial_gaps:
            raise MILPContractError("absolute and relative gaps must appear together")

        if self.status is SolverResultStatus.PROVEN_OPTIMAL:
            if not (has_incumbent and has_bound and has_gaps):
                raise MILPContractError(
                    "proven optimal requires incumbent, bound, and both gaps"
                )
            if not isclose(
                self.incumbent_objective_utility,
                self.best_bound_utility,
                rel_tol=1e-12,
                abs_tol=1e-9,
            ):
                raise MILPContractError("proven optimal incumbent and bound must agree")
            if self.absolute_gap_utility != 0.0 or self.relative_gap != 0.0:
                raise MILPContractError("proven optimal gaps must be zero")
            return

        if self.status is SolverResultStatus.TIME_LIMIT_WITH_INCUMBENT:
            if not (has_incumbent and has_bound and has_gaps):
                raise MILPContractError(
                    "timed incumbent requires incumbent, bound, and both gaps"
                )
            if self.best_bound_utility + 1e-9 < self.incumbent_objective_utility:
                raise MILPContractError(
                    "a maximization best bound cannot be below its incumbent"
                )
            expected_absolute, expected_relative = normalized_solver_gaps(
                self.incumbent_objective_utility,
                self.best_bound_utility,
            )
            if not isclose(
                self.absolute_gap_utility,
                expected_absolute,
                rel_tol=1e-12,
                abs_tol=1e-9,
            ) or not isclose(
                self.relative_gap,
                expected_relative,
                rel_tol=1e-12,
                abs_tol=1e-12,
            ):
                raise MILPContractError(
                    "timed-incumbent gaps do not match the normalized contract"
                )
            return

        if self.status is SolverResultStatus.TIME_LIMIT_WITHOUT_INCUMBENT:
            if has_incumbent or has_gaps:
                raise MILPContractError(
                    "time limit without incumbent cannot report incumbent or gaps"
                )
            return

        if has_incumbent or has_gaps:
            raise MILPContractError(
                f"status {self.status.value} cannot carry an incumbent or gaps"
            )


@dataclass(frozen=True)
class PrototypeMismatch:
    identifier: str
    summary: str
    evidence_files: tuple[str, ...]
    replacement_contract: str


LEGACY_PROTOTYPE_MISMATCHES = (
    PrototypeMismatch(
        "import-time-side-effects",
        "The legacy entry point executes experiments, prints, and calls file writers at import time.",
        ("MILP/milp_main.py", "MILP/report.py"),
        "All replacement modules are import-safe; execution and sinks are explicit later adapters.",
    ),
    PrototypeMismatch(
        "default-decoupled-path",
        "The legacy entry point sets is_budgeted=0 and runs independent per-stage solves.",
        ("MILP/milp_main.py",),
        "The active baseline is one coupled whole-slot optimization.",
    ),
    PrototypeMismatch(
        "replica-dimension",
        "The legacy entry point creates 30 replicas per stage (90 total).",
        ("MILP/milp_main.py",),
        "The initial target has 10 replicas per stage and 30 total.",
    ),
    PrototypeMismatch(
        "ignored-budget-hard-coded-b20",
        "The caller budget is not passed and the budgeted solver hard-codes B=20.",
        ("MILP/milp_main.py", "MILP/milp_header_b.py"),
        "L=2 is the exact selected-stage cardinality and has one source of truth.",
    ),
    PrototypeMismatch(
        "random-cost-budget",
        "The legacy budget sums random replica costs in {1,2}.",
        ("MILP/milp_main.py", "MILP/milp_header_b.py"),
        "Replica monetary cost is absent; exact L=2 cardinality defines the action budget.",
    ),
    PrototypeMismatch(
        "arbitrary-stage-skipping",
        "allow_skip defaults true and no constraint selects exactly two stages.",
        ("MILP/milp_header_b.py",),
        "Every flow selects exactly two distinct stages and one replica in each.",
    ),
    PrototypeMismatch(
        "missing-admission-and-link-constraints",
        "Ready status, assigned-flow capacity, and directed planning links are absent.",
        ("MILP/milp_header.py", "MILP/milp_header_b.py"),
        "All three are explicit feasibility/model inputs.",
    ),
    PrototypeMismatch(
        "obsolete-utility-and-learning",
        "The legacy model uses two states, inverse utility, beliefs, retention 0.7, and iterative learning.",
        ("MILP/milp_header.py", "MILP/milp_main.py"),
        "MILP uses known true state and active final-load expected physical/linear utility with no learning loop.",
    ),
    PrototypeMismatch(
        "global-rng-mutation",
        "Legacy solves shuffle and seed the process-global random module.",
        ("MILP/milp_header.py", "MILP/milp_header_b.py", "MILP/milp_main.py"),
        "The centralized deterministic model has no flow-order RNG input.",
    ),
    PrototypeMismatch(
        "incomplete-solver-provenance",
        "Legacy code accepts FEASIBLE alongside OPTIMAL without bound or gap provenance.",
        ("MILP/milp_header.py", "MILP/milp_header_b.py"),
        "Result status distinguishes proof, timed incumbent, timeout without incumbent, and failures.",
    ),
    PrototypeMismatch(
        "broken-budgeted-result-shape",
        "The budgeted solver returns (assignment, counts), but the caller passes the tuple to the old update path.",
        ("MILP/milp_header_b.py", "MILP/milp_main.py"),
        "Later orchestration consumes one explicit immutable coupled result contract.",
    ),
    PrototypeMismatch(
        "undeclared-ortools-dependency",
        "Legacy modules import OR-Tools although requirements.txt does not declare it.",
        ("MILP/milp_header.py", "requirements.txt"),
        "Phase 1 will gate a declared backend dependency with an explicit configuration error.",
    ),
)
