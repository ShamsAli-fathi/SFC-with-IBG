"""Pure contracts for the active two-stage IBG-Hybrid action model."""

from __future__ import annotations

from dataclasses import dataclass, field
from numbers import Integral
from typing import Iterable


def _active_stage_budget() -> int:
    # Imported lazily so budgeted.py remains the one code-level source of truth.
    from .budgeted import HYBRID_STAGE_BUDGET

    return HYBRID_STAGE_BUDGET


@dataclass(frozen=True, order=True)
class ReplicaChoice:
    """One selected replica in one selected stage."""

    stage: int
    replica: int

    def __post_init__(self) -> None:
        if isinstance(self.stage, bool) or not isinstance(self.stage, Integral):
            raise TypeError("stage must be an integer")
        if isinstance(self.replica, bool) or not isinstance(self.replica, Integral):
            raise TypeError("replica must be an integer")
        if self.stage < 1:
            raise ValueError("stage must be at least 1")
        if self.replica < 1:
            raise ValueError("replica must be at least 1")


@dataclass(frozen=True, order=True)
class TwoStageAction:
    """Exactly two stage/replica choices in canonical stage order."""

    choices: tuple[ReplicaChoice, ReplicaChoice]

    def __post_init__(self) -> None:
        choices = tuple(self.choices)
        object.__setattr__(self, "choices", choices)
        if len(choices) != _active_stage_budget():
            raise ValueError(
                "a Hybrid action must contain exactly "
                f"{_active_stage_budget()} choices"
            )
        if not all(isinstance(choice, ReplicaChoice) for choice in choices):
            raise TypeError("action choices must be ReplicaChoice values")
        if choices[0].stage >= choices[1].stage:
            raise ValueError(
                "Hybrid choices must use distinct stages in increasing stage order"
            )

    @property
    def stages(self) -> tuple[int, int]:
        return tuple(choice.stage for choice in self.choices)

    def validate_for(self, configuration: HybridConfiguration) -> None:
        for choice in self.choices:
            if choice.stage > configuration.num_stages:
                raise ValueError(
                    f"stage {choice.stage} exceeds configured stage count "
                    f"{configuration.num_stages}"
                )
            if choice.replica > configuration.num_replicas:
                raise ValueError(
                    f"replica {choice.replica} exceeds configured per-stage "
                    f"replica count {configuration.num_replicas}"
                )

    def skipped_stage(self, configuration: HybridConfiguration) -> int:
        self.validate_for(configuration)
        skipped = set(range(1, configuration.num_stages + 1)) - set(self.stages)
        if len(skipped) != 1:
            raise ValueError("the active Hybrid action must bypass exactly one stage")
        return skipped.pop()


@dataclass(frozen=True)
class HybridConfiguration:
    """Dimensions of the active L=2, two-of-three-stage Hybrid problem."""

    num_flows: int = 20
    num_stages: int = 3
    num_replicas: int = 10
    stage_budget: int = field(default_factory=_active_stage_budget)

    def __post_init__(self) -> None:
        from .budgeted import require_hybrid_stage_budget

        for name in ("num_flows", "num_stages", "num_replicas", "stage_budget"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, Integral):
                raise TypeError(f"{name} must be an integer")
        if self.num_flows < 1:
            raise ValueError("num_flows must be at least 1")
        if self.num_stages != 3:
            raise ValueError("the active Hybrid action model requires 3 stages")
        if self.num_replicas < 1:
            raise ValueError("num_replicas must be at least 1")
        require_hybrid_stage_budget(self.stage_budget)


@dataclass(frozen=True)
class GlobalLoadState:
    """Immutable stage-major replica loads before one Hybrid decision."""

    loads: tuple[tuple[int, ...], ...]

    def __post_init__(self) -> None:
        loads = tuple(tuple(row) for row in self.loads)
        object.__setattr__(self, "loads", loads)
        if not loads:
            raise ValueError("global load state must contain at least one stage")
        row_size = len(loads[0])
        if row_size < 1 or any(len(row) != row_size for row in loads):
            raise ValueError("global load state must be a nonempty rectangular matrix")
        for row in loads:
            for value in row:
                if isinstance(value, bool) or not isinstance(value, Integral):
                    raise TypeError("replica loads must be integers")
                if value < 0:
                    raise ValueError("replica loads must not be negative")

    @classmethod
    def empty(cls, configuration: HybridConfiguration) -> GlobalLoadState:
        return cls(
            tuple(
                tuple(0 for _ in range(configuration.num_replicas))
                for _ in range(configuration.num_stages)
            )
        )

    @property
    def total_assignments(self) -> int:
        return sum(sum(row) for row in self.loads)

    def validate_for(self, configuration: HybridConfiguration) -> None:
        expected = (configuration.num_stages, configuration.num_replicas)
        actual = (len(self.loads), len(self.loads[0]))
        if actual != expected:
            raise ValueError(
                f"global load shape {actual} does not match configuration {expected}"
            )
        if self.total_assignments % configuration.stage_budget != 0:
            raise ValueError(
                "pre-decision global loads must contain complete L=2 assignments"
            )

    def load_for(self, choice: ReplicaChoice) -> int:
        if choice.stage > len(self.loads):
            raise ValueError(f"stage {choice.stage} is absent from global loads")
        if choice.replica > len(self.loads[choice.stage - 1]):
            raise ValueError(
                f"replica {choice.replica} is absent from stage {choice.stage}"
            )
        return self.loads[choice.stage - 1][choice.replica - 1]

    def apply(
        self,
        action: TwoStageAction,
        configuration: HybridConfiguration,
    ) -> GlobalLoadState:
        self.validate_for(configuration)
        action.validate_for(configuration)
        updated = [list(row) for row in self.loads]
        for choice in action.choices:
            updated[choice.stage - 1][choice.replica - 1] += 1
        return GlobalLoadState(tuple(tuple(row) for row in updated))


@dataclass(frozen=True)
class FeasibilityResult:
    """A behavior-neutral feasibility decision and its rejection reasons."""

    feasible: bool
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        reasons = tuple(str(reason) for reason in self.reasons)
        object.__setattr__(self, "reasons", reasons)
        if self.feasible and reasons:
            raise ValueError("a feasible action cannot carry rejection reasons")
        if not self.feasible and not reasons:
            raise ValueError("an infeasible action must carry a rejection reason")

    @classmethod
    def accepted(cls) -> FeasibilityResult:
        return cls(feasible=True)

    @classmethod
    def rejected(cls, *reasons: str) -> FeasibilityResult:
        return cls(feasible=False, reasons=tuple(reasons))


@dataclass(frozen=True)
class HybridSolverResult:
    """Result of selecting one action from one pre-decision global state."""

    action: TwoStageAction
    objective_value: float
    state_after: GlobalLoadState
    feasibility: FeasibilityResult
    evaluated_actions: int
    feasible_actions: int

    def __post_init__(self) -> None:
        if not self.feasibility.feasible:
            raise ValueError("a solver result must contain a feasible selected action")
        if self.evaluated_actions < 1:
            raise ValueError("evaluated_actions must be positive")
        if not 1 <= self.feasible_actions <= self.evaluated_actions:
            raise ValueError(
                "feasible_actions must be positive and no greater than evaluated_actions"
            )


def action_from_pairs(pairs: Iterable[tuple[int, int]]) -> TwoStageAction:
    """Construct a typed action from canonical ``(stage, replica)`` pairs."""

    return TwoStageAction(
        tuple(ReplicaChoice(stage, replica) for stage, replica in pairs)
    )
