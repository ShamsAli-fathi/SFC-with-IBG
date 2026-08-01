"""Pure Phase 2--4 greedy, lookahead, and Monte Carlo Hybrid policy."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum
from itertools import combinations, product
from math import fsum, isfinite
from numbers import Integral
from random import Random
from typing import Iterator, Mapping, Sequence

from .contracts import (
    GlobalLoadState,
    HybridConfiguration,
    HybridSolverResult,
    ReplicaChoice,
    TwoStageAction,
)
from .expected_utility import expected_stage_utility_from_belief
from .phase0_contract import (
    DEFAULT_HYBRID_POLICY_PARAMETERS,
    HYBRID_LINK_WEIGHT_UTILITY_PER_MS,
    HYBRID_ROLLOUT_SEED_SCHEME,
    HybridPolicyParameters,
    ReplicaAdmission,
    RolloutSeedKey,
    derive_rollout_seed,
    evaluate_phase0_feasibility,
    evaluate_replica_admission_feasibility,
    focal_utility_at_projected_loads,
    future_flows_to_simulate,
    prune_stage_candidates,
    pruned_action_count,
)


@dataclass(frozen=True)
class CandidateAccounting:
    """Deterministic Phase 2 candidate counts and retained identities."""

    available_replicas_by_stage: tuple[int, ...]
    locally_feasible_replicas_by_stage: tuple[int, ...]
    available_actions: int
    feasible_actions_before_pruning: int
    retained_by_stage: tuple[tuple[ReplicaChoice, ...], ...]
    pruned_actions: int
    feasible_pruned_actions: int
    rejection_reason_counts: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        stage_count = len(self.available_replicas_by_stage)
        if stage_count < 1:
            raise ValueError("candidate accounting requires at least one stage")
        if len(self.locally_feasible_replicas_by_stage) != stage_count:
            raise ValueError("local-feasibility counts must cover every stage")
        if len(self.retained_by_stage) != stage_count:
            raise ValueError("retained candidates must cover every stage")
        for values in (
            self.available_replicas_by_stage,
            self.locally_feasible_replicas_by_stage,
        ):
            if any(value < 0 for value in values):
                raise ValueError("replica candidate counts must not be negative")
        for name in (
            "available_actions",
            "feasible_actions_before_pruning",
            "pruned_actions",
            "feasible_pruned_actions",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must not be negative")
        if self.feasible_actions_before_pruning > self.available_actions:
            raise ValueError(
                "pre-pruning feasible actions cannot exceed available actions"
            )
        if self.feasible_pruned_actions > self.pruned_actions:
            raise ValueError(
                "feasible pruned actions cannot exceed pruned actions"
            )
        for stage, retained in enumerate(self.retained_by_stage, start=1):
            if any(choice.stage != stage for choice in retained):
                raise ValueError(
                    "retained candidates must be recorded under their stage"
                )
        if any(
            feasible > available
            for feasible, available in zip(
                self.locally_feasible_replicas_by_stage,
                self.available_replicas_by_stage,
            )
        ):
            raise ValueError(
                "locally feasible replicas cannot exceed available replicas"
            )
        if any(
            len(retained) > feasible
            for retained, feasible in zip(
                self.retained_by_stage,
                self.locally_feasible_replicas_by_stage,
            )
        ):
            raise ValueError(
                "retained replicas cannot exceed locally feasible replicas"
            )
        if self.pruned_actions > self.available_actions:
            raise ValueError("pruned actions cannot exceed available actions")
        if (
            self.feasible_pruned_actions
            > self.feasible_actions_before_pruning
        ):
            raise ValueError(
                "feasible pruned actions cannot exceed pre-pruning feasibility"
            )
        if any(
            not reason or count < 1
            for reason, count in self.rejection_reason_counts
        ):
            raise ValueError("rejection reason counts must be positive")

    @property
    def retained_counts_by_stage(self) -> tuple[int, ...]:
        return tuple(len(retained) for retained in self.retained_by_stage)


@dataclass(frozen=True)
class ScoredHybridAction:
    """One feasible complete L=2 action and its belief/link score."""

    action: TwoStageAction
    stage_utilities: tuple[float, float]
    planning_pair_link_cost_ms: float
    objective_value: float

    def __post_init__(self) -> None:
        if len(self.stage_utilities) != 2:
            raise ValueError("a scored Hybrid action needs two stage utilities")
        values = (
            *self.stage_utilities,
            self.planning_pair_link_cost_ms,
            self.objective_value,
        )
        if any(not isfinite(float(value)) for value in values):
            raise ValueError("scored action values must be finite")
        if self.planning_pair_link_cost_ms < 0:
            raise ValueError("planning pair-link cost must not be negative")


@dataclass(frozen=True)
class HybridGreedyDecision:
    """Selected greedy result plus every feasible pruned action and accounting."""

    result: HybridSolverResult
    scored_actions: tuple[ScoredHybridAction, ...]
    accounting: CandidateAccounting

    def __post_init__(self) -> None:
        if len(self.scored_actions) != self.accounting.feasible_pruned_actions:
            raise ValueError(
                "scored-action count must match feasible pruned accounting"
            )
        if self.result.feasible_actions != len(self.scored_actions):
            raise ValueError(
                "solver feasible-action count must match scored actions"
            )
        if self.result.evaluated_actions != self.accounting.pruned_actions:
            raise ValueError(
                "solver evaluated-action count must match pruned actions"
            )
        if not any(
            scored.action == self.result.action
            and scored.objective_value == self.result.objective_value
            for scored in self.scored_actions
        ):
            raise ValueError("selected result must be present in scored actions")


@dataclass(frozen=True)
class HybridLookaheadStep:
    """One Phase 2 greedy continuation decision at its branch-local state."""

    state_before: GlobalLoadState
    decision: HybridGreedyDecision

    def __post_init__(self) -> None:
        updated = [list(row) for row in self.state_before.loads]
        for choice in self.decision.result.action.choices:
            updated[choice.stage - 1][choice.replica - 1] += 1
        expected_state_after = GlobalLoadState(
            tuple(tuple(row) for row in updated)
        )
        if self.decision.result.state_after != expected_state_after:
            raise ValueError(
                "continuation decision state must apply its action exactly once"
            )

    @property
    def action(self) -> TwoStageAction:
        return self.decision.result.action

    @property
    def state_after(self) -> GlobalLoadState:
        return self.decision.result.state_after

    @property
    def accounting(self) -> CandidateAccounting:
        return self.decision.accounting


@dataclass(frozen=True)
class HybridLookaheadEvaluation:
    """Completed deterministic continuation and focal-only branch value."""

    focal_action: TwoStageAction
    state_after_focal: GlobalLoadState
    projected_final_state: GlobalLoadState
    continuation_steps: tuple[HybridLookaheadStep, ...]
    focal_value: float
    requested_depth: int
    effective_depth: int

    def __post_init__(self) -> None:
        steps = tuple(self.continuation_steps)
        object.__setattr__(self, "continuation_steps", steps)
        if self.requested_depth < 0:
            raise ValueError("requested lookahead depth must not be negative")
        if not 0 <= self.effective_depth <= self.requested_depth:
            raise ValueError(
                "effective lookahead depth must be within requested depth"
            )
        if len(steps) != self.effective_depth:
            raise ValueError(
                "continuation step count must match effective lookahead depth"
            )
        expected_state = self.state_after_focal
        for step in steps:
            if step.state_before != expected_state:
                raise ValueError("continuation steps must form one ordered branch")
            expected_state = step.state_after
        if self.projected_final_state != expected_state:
            raise ValueError(
                "projected final state must follow every continuation action"
            )
        if not isfinite(float(self.focal_value)):
            raise ValueError("focal lookahead value must be finite")

    @property
    def continuation_actions(self) -> tuple[TwoStageAction, ...]:
        return tuple(step.action for step in self.continuation_steps)

    @property
    def continuation_accounting(self) -> tuple[CandidateAccounting, ...]:
        return tuple(step.accounting for step in self.continuation_steps)


@dataclass(frozen=True)
class HybridLookaheadBranchFailure:
    """A root-feasible focal action whose continuation cannot be completed."""

    focal_action: TwoStageAction
    state_after_focal: GlobalLoadState
    completed_steps: tuple[HybridLookaheadStep, ...]
    failing_state: GlobalLoadState
    failure_accounting: CandidateAccounting
    requested_depth: int
    effective_depth: int

    def __post_init__(self) -> None:
        steps = tuple(self.completed_steps)
        object.__setattr__(self, "completed_steps", steps)
        if self.requested_depth < 0:
            raise ValueError("requested lookahead depth must not be negative")
        if not 0 < self.effective_depth <= self.requested_depth:
            raise ValueError(
                "a failed continuation requires a positive effective depth"
            )
        if len(steps) >= self.effective_depth:
            raise ValueError(
                "failed branch must stop before its effective lookahead depth"
            )
        expected_state = self.state_after_focal
        for step in steps:
            if step.state_before != expected_state:
                raise ValueError("completed steps must form one ordered branch")
            expected_state = step.state_after
        if self.failing_state != expected_state:
            raise ValueError(
                "failing state must follow every completed continuation action"
            )


@dataclass(frozen=True)
class HybridLookaheadDecision:
    """Selected focal result plus deterministic Phase 3 branch details."""

    result: HybridSolverResult
    evaluations: tuple[HybridLookaheadEvaluation, ...]
    focal_accounting: CandidateAccounting
    rejected_branches: tuple[HybridLookaheadBranchFailure, ...] = ()

    def __post_init__(self) -> None:
        evaluations = tuple(self.evaluations)
        rejected = tuple(self.rejected_branches)
        object.__setattr__(self, "evaluations", evaluations)
        object.__setattr__(self, "rejected_branches", rejected)
        if not evaluations:
            raise ValueError("lookahead requires a completed focal evaluation")
        if self.result.evaluated_actions != self.focal_accounting.pruned_actions:
            raise ValueError(
                "lookahead evaluated-action count must match focal accounting"
            )
        if self.result.feasible_actions != len(evaluations):
            raise ValueError(
                "lookahead feasible-action count must match completed branches"
            )
        selected = [
            evaluation
            for evaluation in evaluations
            if evaluation.focal_action == self.result.action
            and evaluation.focal_value == self.result.objective_value
        ]
        if len(selected) != 1:
            raise ValueError(
                "selected result must identify one completed focal evaluation"
            )

    @property
    def selected_evaluation(self) -> HybridLookaheadEvaluation:
        return next(
            evaluation
            for evaluation in self.evaluations
            if evaluation.focal_action == self.result.action
        )


class RolloutChoiceMode(str, Enum):
    """How one seeded Monte Carlo continuation action was selected."""

    GREEDY = "greedy"
    EXPLORATION = "uniform-exploration"


@dataclass(frozen=True)
class HybridMonteCarloStep:
    """One epsilon-greedy continuation at an updated branch-local state."""

    state_before: GlobalLoadState
    chosen_action: TwoStageAction
    greedy_action: TwoStageAction
    choice_mode: RolloutChoiceMode
    feasible_actions: tuple[TwoStageAction, ...]
    accounting: CandidateAccounting
    state_after: GlobalLoadState

    def __post_init__(self) -> None:
        feasible_actions = tuple(self.feasible_actions)
        object.__setattr__(self, "feasible_actions", feasible_actions)
        if not isinstance(self.choice_mode, RolloutChoiceMode):
            raise TypeError("choice_mode must be RolloutChoiceMode")
        if not feasible_actions:
            raise ValueError("a Monte Carlo step requires feasible actions")
        if self.chosen_action not in feasible_actions:
            raise ValueError("chosen rollout action must be currently feasible")
        if self.greedy_action not in feasible_actions:
            raise ValueError("greedy rollout action must be currently feasible")
        if (
            self.choice_mode is RolloutChoiceMode.GREEDY
            and self.chosen_action != self.greedy_action
        ):
            raise ValueError("a greedy rollout step must choose the greedy action")
        if len(feasible_actions) != self.accounting.feasible_pruned_actions:
            raise ValueError(
                "rollout feasible-action set must match Phase 2 accounting"
            )

        updated = [list(row) for row in self.state_before.loads]
        for choice in self.chosen_action.choices:
            updated[choice.stage - 1][choice.replica - 1] += 1
        expected_state_after = GlobalLoadState(
            tuple(tuple(row) for row in updated)
        )
        if self.state_after != expected_state_after:
            raise ValueError(
                "rollout state must apply the chosen action exactly once"
            )


@dataclass(frozen=True)
class HybridMonteCarloSample:
    """One completed candidate-specific seeded rollout sample."""

    seed_key: RolloutSeedKey
    derived_seed: int
    state_after_focal: GlobalLoadState
    projected_final_state: GlobalLoadState
    continuation_steps: tuple[HybridMonteCarloStep, ...]
    focal_value: float
    requested_depth: int
    effective_depth: int

    def __post_init__(self) -> None:
        steps = tuple(self.continuation_steps)
        object.__setattr__(self, "continuation_steps", steps)
        if self.derived_seed != derive_rollout_seed(self.seed_key):
            raise ValueError("derived rollout seed does not match its key")
        if self.requested_depth < 0:
            raise ValueError("requested rollout depth must not be negative")
        if not 0 <= self.effective_depth <= self.requested_depth:
            raise ValueError(
                "effective rollout depth must be within requested depth"
            )
        if len(steps) != self.effective_depth:
            raise ValueError(
                "completed rollout step count must match effective depth"
            )
        expected_state = self.state_after_focal
        for step in steps:
            if step.state_before != expected_state:
                raise ValueError("rollout steps must form one ordered branch")
            expected_state = step.state_after
        if self.projected_final_state != expected_state:
            raise ValueError(
                "sample final state must follow every continuation action"
            )
        if not isfinite(float(self.focal_value)):
            raise ValueError("sample focal value must be finite")

    @property
    def focal_action(self) -> TwoStageAction:
        return self.seed_key.action

    @property
    def sample_index(self) -> int:
        return self.seed_key.sample_index

    @property
    def continuation_actions(self) -> tuple[TwoStageAction, ...]:
        return tuple(step.chosen_action for step in self.continuation_steps)


@dataclass(frozen=True)
class HybridMonteCarloSampleFailure:
    """One seeded rollout that cannot complete its required continuation."""

    seed_key: RolloutSeedKey
    derived_seed: int
    state_after_focal: GlobalLoadState
    completed_steps: tuple[HybridMonteCarloStep, ...]
    failing_state: GlobalLoadState
    failure_accounting: CandidateAccounting
    requested_depth: int
    effective_depth: int

    def __post_init__(self) -> None:
        steps = tuple(self.completed_steps)
        object.__setattr__(self, "completed_steps", steps)
        if self.derived_seed != derive_rollout_seed(self.seed_key):
            raise ValueError("derived rollout seed does not match its key")
        if self.requested_depth < 0:
            raise ValueError("requested rollout depth must not be negative")
        if not 0 < self.effective_depth <= self.requested_depth:
            raise ValueError(
                "a failed rollout requires a positive effective depth"
            )
        if len(steps) >= self.effective_depth:
            raise ValueError(
                "failed rollout must stop before its effective depth"
            )
        expected_state = self.state_after_focal
        for step in steps:
            if step.state_before != expected_state:
                raise ValueError("completed rollout steps must be ordered")
            expected_state = step.state_after
        if self.failing_state != expected_state:
            raise ValueError(
                "failing state must follow all completed rollout actions"
            )

    @property
    def focal_action(self) -> TwoStageAction:
        return self.seed_key.action

    @property
    def sample_index(self) -> int:
        return self.seed_key.sample_index


@dataclass(frozen=True)
class HybridMonteCarloEvaluation:
    """Completed samples and their mean focal value for one candidate."""

    focal_action: TwoStageAction
    samples: tuple[HybridMonteCarloSample, ...]
    failed_samples: tuple[HybridMonteCarloSampleFailure, ...]
    mean_focal_value: float
    requested_samples: int
    requested_depth: int
    effective_depth: int

    def __post_init__(self) -> None:
        samples = tuple(self.samples)
        failures = tuple(self.failed_samples)
        object.__setattr__(self, "samples", samples)
        object.__setattr__(self, "failed_samples", failures)
        if (
            isinstance(self.requested_samples, bool)
            or not isinstance(self.requested_samples, Integral)
            or self.requested_samples < 1
        ):
            raise ValueError("requested_samples must be a positive integer")
        if not samples:
            raise ValueError(
                "a Monte Carlo evaluation requires a completed sample"
            )
        if len(samples) + len(failures) != self.requested_samples:
            raise ValueError(
                "completed and failed samples must cover every request"
            )
        attempted_indices = sorted(
            sample.sample_index for sample in (*samples, *failures)
        )
        if attempted_indices != list(range(self.requested_samples)):
            raise ValueError("sample indices must cover the requested range")
        if any(
            sample.focal_action != self.focal_action
            or sample.requested_depth != self.requested_depth
            or sample.effective_depth != self.effective_depth
            for sample in (*samples, *failures)
        ):
            raise ValueError(
                "candidate samples must share focal action and depth"
            )
        expected_mean = fsum(
            sample.focal_value for sample in samples
        ) / len(samples)
        if not isfinite(float(self.mean_focal_value)):
            raise ValueError("mean focal value must be finite")
        if self.mean_focal_value != expected_mean:
            raise ValueError(
                "mean focal value must use completed samples only"
            )

    @property
    def completed_samples(self) -> int:
        return len(self.samples)

    @property
    def failed_sample_count(self) -> int:
        return len(self.failed_samples)


@dataclass(frozen=True)
class HybridMonteCarloRejectedCandidate:
    """A root-feasible focal candidate whose every sample dead-ends."""

    focal_action: TwoStageAction
    failed_samples: tuple[HybridMonteCarloSampleFailure, ...]
    requested_samples: int
    requested_depth: int
    effective_depth: int

    def __post_init__(self) -> None:
        failures = tuple(self.failed_samples)
        object.__setattr__(self, "failed_samples", failures)
        if (
            isinstance(self.requested_samples, bool)
            or not isinstance(self.requested_samples, Integral)
            or self.requested_samples < 1
        ):
            raise ValueError("requested_samples must be a positive integer")
        if len(failures) != self.requested_samples:
            raise ValueError(
                "a rejected candidate must fail every requested sample"
            )
        if sorted(failure.sample_index for failure in failures) != list(
            range(self.requested_samples)
        ):
            raise ValueError("failed sample indices must cover every request")
        if any(
            failure.focal_action != self.focal_action
            or failure.requested_depth != self.requested_depth
            or failure.effective_depth != self.effective_depth
            for failure in failures
        ):
            raise ValueError(
                "rejected samples must share focal action and depth"
            )


@dataclass(frozen=True)
class HybridMonteCarloDecision:
    """Selected mean-value result and complete seeded Phase 4 detail."""

    result: HybridSolverResult
    evaluations: tuple[HybridMonteCarloEvaluation, ...]
    rejected_candidates: tuple[HybridMonteCarloRejectedCandidate, ...]
    focal_accounting: CandidateAccounting
    root_seed: int
    slot_id: int
    decision_position: int
    flow_id: int
    rollout_seed_scheme: str
    requested_samples: int

    def __post_init__(self) -> None:
        evaluations = tuple(self.evaluations)
        rejected = tuple(self.rejected_candidates)
        object.__setattr__(self, "evaluations", evaluations)
        object.__setattr__(self, "rejected_candidates", rejected)
        if not evaluations:
            raise ValueError(
                "Monte Carlo requires a completed candidate evaluation"
            )
        if self.rollout_seed_scheme != HYBRID_ROLLOUT_SEED_SCHEME:
            raise ValueError("unexpected rollout seed scheme")
        if self.result.evaluated_actions != self.focal_accounting.pruned_actions:
            raise ValueError(
                "Monte Carlo evaluated actions must match focal accounting"
            )
        if self.result.feasible_actions != len(evaluations):
            raise ValueError(
                "Monte Carlo feasible actions must match completed candidates"
            )
        if (
            len(evaluations) + len(rejected)
            != self.focal_accounting.feasible_pruned_actions
        ):
            raise ValueError(
                "completed and rejected candidates must cover the focal pool"
            )
        if any(
            evaluation.requested_samples != self.requested_samples
            for evaluation in evaluations
        ) or any(
            candidate.requested_samples != self.requested_samples
            for candidate in rejected
        ):
            raise ValueError("all candidates must use the requested sample count")
        seed_keys = tuple(
            sample.seed_key
            for evaluation in evaluations
            for sample in (*evaluation.samples, *evaluation.failed_samples)
        ) + tuple(
            failure.seed_key
            for candidate in rejected
            for failure in candidate.failed_samples
        )
        if any(
            key.root_seed != self.root_seed
            or key.slot_id != self.slot_id
            or key.decision_position != self.decision_position
            or key.flow_id != self.flow_id
            for key in seed_keys
        ):
            raise ValueError(
                "sample seed provenance must match the Monte Carlo decision"
            )
        selected = [
            evaluation
            for evaluation in evaluations
            if evaluation.focal_action == self.result.action
            and evaluation.mean_focal_value == self.result.objective_value
        ]
        if len(selected) != 1:
            raise ValueError(
                "selected result must identify one Monte Carlo evaluation"
            )

    @property
    def selected_evaluation(self) -> HybridMonteCarloEvaluation:
        return next(
            evaluation
            for evaluation in self.evaluations
            if evaluation.focal_action == self.result.action
        )


class NoFeasiblePrunedAction(RuntimeError):
    """Raised when Phase 2 cannot retain a feasible complete action."""

    def __init__(
        self,
        message: str,
        accounting: CandidateAccounting,
    ) -> None:
        super().__init__(message)
        self.accounting = accounting


class NoFeasibleLookaheadAction(RuntimeError):
    """Raised when every root-feasible focal branch dead-ends."""

    def __init__(
        self,
        message: str,
        focal_accounting: CandidateAccounting,
        rejected_branches: tuple[HybridLookaheadBranchFailure, ...],
    ) -> None:
        super().__init__(message)
        self.focal_accounting = focal_accounting
        self.rejected_branches = rejected_branches


class NoFeasibleMonteCarloAction(RuntimeError):
    """Raised when all root-feasible candidates fail every rollout sample."""

    def __init__(
        self,
        message: str,
        focal_accounting: CandidateAccounting,
        rejected_candidates: tuple[HybridMonteCarloRejectedCandidate, ...],
    ) -> None:
        super().__init__(message)
        self.focal_accounting = focal_accounting
        self.rejected_candidates = rejected_candidates


def _all_configured_actions(
    configuration: HybridConfiguration,
) -> Iterator[TwoStageAction]:
    for stage_a, stage_b in combinations(
        range(1, configuration.num_stages + 1),
        configuration.stage_budget,
    ):
        for replica_a, replica_b in product(
            range(1, configuration.num_replicas + 1),
            repeat=configuration.stage_budget,
        ):
            yield TwoStageAction(
                (
                    ReplicaChoice(stage_a, replica_a),
                    ReplicaChoice(stage_b, replica_b),
                )
            )


class IBGHybridPolicy:
    """Production boundary for Phase 2--4 greedy, lookahead, and rollout.

    This policy deliberately accepts beliefs rather than runtime replica
    objects, so hidden true state, legacy replica cost, and measured pair
    residuals are absent from its decision input.
    """

    def __init__(
        self,
        configuration: HybridConfiguration,
        parameters: HybridPolicyParameters = DEFAULT_HYBRID_POLICY_PARAMETERS,
    ) -> None:
        if not isinstance(configuration, HybridConfiguration):
            raise TypeError("configuration must be HybridConfiguration")
        if not isinstance(parameters, HybridPolicyParameters):
            raise TypeError("parameters must be HybridPolicyParameters")
        self.configuration = configuration
        self.parameters = parameters
        # Structural identities do not change between decisions. Reusing
        # these immutable values avoids rebuilding the 20x3x10 action space
        # thousands of times during D=2 lookahead.
        self._all_choices = tuple(
            ReplicaChoice(stage, replica)
            for stage in range(1, configuration.num_stages + 1)
            for replica in range(1, configuration.num_replicas + 1)
        )
        self._all_actions = tuple(_all_configured_actions(configuration))
        self._action_index_by_choices = {
            action.choices: index
            for index, action in enumerate(self._all_actions)
        }
        self._action_choice_indices = tuple(
            tuple(
                (choice.stage - 1) * configuration.num_replicas
                + choice.replica
                - 1
                for choice in action.choices
            )
            for action in self._all_actions
        )
        self._expected_stage_utility_cache: dict[
            tuple[tuple[float, ...], int],
            float,
        ] = {}

    def _expected_stage_utility(
        self,
        belief: Sequence[float],
        load: int,
    ) -> float:
        """Memoize the pure shared utility law by belief value and load."""

        belief_key = tuple(float(value) for value in belief)
        key = (belief_key, load)
        if key not in self._expected_stage_utility_cache:
            self._expected_stage_utility_cache[key] = float(
                expected_stage_utility_from_belief(belief_key, load)
            )
        return self._expected_stage_utility_cache[key]

    def select_greedy(
        self,
        *,
        state: GlobalLoadState,
        admission: Mapping[ReplicaChoice, ReplicaAdmission],
        beliefs: Mapping[ReplicaChoice, Sequence[float]],
        known_pair_link_costs: Mapping[
            tuple[ReplicaChoice, ReplicaChoice],
            float,
        ],
    ) -> HybridGreedyDecision:
        """Prune, enumerate, score, and select one complete feasible action."""

        configuration = self.configuration
        state.validate_for(configuration)

        all_choices = self._all_choices
        available_replicas_by_stage = tuple(
            sum(
                ReplicaChoice(stage, replica) in admission
                for replica in range(1, configuration.num_replicas + 1)
            )
            for stage in range(1, configuration.num_stages + 1)
        )

        locally_feasible = []
        local_feasibility = []
        local_stage_scores: list[float | None] = [
            None for _choice in all_choices
        ]

        def choice_index(choice: ReplicaChoice) -> int:
            return (
                (choice.stage - 1) * configuration.num_replicas
                + choice.replica
                - 1
            )

        for stage in range(1, configuration.num_stages + 1):
            stage_candidates = []
            for choice in (
                candidate for candidate in all_choices if candidate.stage == stage
            ):
                feasibility = evaluate_replica_admission_feasibility(
                    choice,
                    state,
                    configuration,
                    admission,
                )
                local_feasibility.append(feasibility)
                if not feasibility.feasible:
                    continue
                if choice not in beliefs:
                    raise ValueError(
                        "missing belief for locally feasible replica "
                        f"{choice.stage}:{choice.replica}"
                    )
                projected_load = state.load_for(choice) + 1
                score = float(
                    self._expected_stage_utility(
                        beliefs[choice],
                        projected_load,
                    )
                )
                if not isfinite(score):
                    raise ValueError("stage expected utility must be finite")
                stage_candidates.append(choice)
                local_stage_scores[choice_index(choice)] = score
            locally_feasible.append(tuple(stage_candidates))

        retained_by_stage = []
        for stage, stage_candidates in enumerate(locally_feasible, start=1):
            if not stage_candidates:
                retained_by_stage.append(())
                continue
            retained_by_stage.append(
                prune_stage_candidates(
                    stage,
                    {
                        choice: local_stage_scores[choice_index(choice)]
                        for choice in stage_candidates
                    },
                    self.parameters,
                )
            )
        retained = tuple(retained_by_stage)

        all_actions = self._all_actions
        pre_pruning_feasible = 0
        rejection_counts: Counter[str] = Counter()
        feasibility_reasons = []
        pair_costs: list[float | None] = []
        for action_index, action in enumerate(all_actions):
            pair = action.choices
            local_reasons = tuple(
                reason
                for index in self._action_choice_indices[action_index]
                for reason in local_feasibility[index].reasons
            )
            valid_pair_cost = None
            pair_reason = None
            if pair not in known_pair_link_costs:
                pair_reason_prefix = "missing-pair-link-cost"
            else:
                pair_cost = float(known_pair_link_costs[pair])
                if not isfinite(pair_cost) or pair_cost < 0:
                    pair_reason_prefix = "invalid-pair-link-cost"
                else:
                    valid_pair_cost = pair_cost
                    pair_reason_prefix = None
            if pair_reason_prefix is not None:
                pair_identity = (
                    f"{pair[0].stage}:{pair[0].replica}->"
                    f"{pair[1].stage}:{pair[1].replica}"
                )
                pair_reason = f"{pair_reason_prefix}:{pair_identity}"
            action_reasons = (
                local_reasons
                if pair_reason is None
                else (*local_reasons, pair_reason)
            )
            feasibility_reasons.append(action_reasons)
            pair_costs.append(
                valid_pair_cost
                if not action_reasons
                else None
            )
            if not action_reasons:
                pre_pruning_feasible += 1
            else:
                rejection_counts.update(action_reasons)

        pruned_action_indices = tuple(
            self._action_index_by_choices[(choice_a, choice_b)]
            for stage_a, stage_b in combinations(
                range(1, configuration.num_stages + 1),
                configuration.stage_budget,
            )
            for choice_a, choice_b in product(
                sorted(
                    retained[stage_a - 1],
                    key=lambda choice: choice.replica,
                ),
                sorted(
                    retained[stage_b - 1],
                    key=lambda choice: choice.replica,
                ),
            )
        )
        pruned_actions = tuple(
            all_actions[index]
            for index in pruned_action_indices
        )
        maximum_pruned = pruned_action_count(configuration, self.parameters)
        if len(pruned_actions) > maximum_pruned:
            raise AssertionError(
                "Phase 2 pruned action enumeration exceeded the Phase 0 bound"
            )

        scored_actions = []
        for action_index, action in zip(pruned_action_indices, pruned_actions):
            if feasibility_reasons[action_index]:
                continue
            pair_cost = pair_costs[action_index]
            if pair_cost is None:
                raise AssertionError(
                    "a feasible pruned action must have a valid pair cost"
                )
            stage_utilities = tuple(
                local_stage_scores[choice_index(choice)]
                for choice in action.choices
            )
            if any(value is None for value in stage_utilities):
                raise AssertionError(
                    "a feasible pruned action must have stage utility values"
                )
            objective_value = (
                sum(stage_utilities)
                - HYBRID_LINK_WEIGHT_UTILITY_PER_MS * pair_cost
            )
            scored_actions.append(
                ScoredHybridAction(
                    action=action,
                    stage_utilities=stage_utilities,
                    planning_pair_link_cost_ms=pair_cost,
                    objective_value=objective_value,
                )
            )

        accounting = CandidateAccounting(
            available_replicas_by_stage=available_replicas_by_stage,
            locally_feasible_replicas_by_stage=tuple(
                len(stage_candidates)
                for stage_candidates in locally_feasible
            ),
            available_actions=len(all_actions),
            feasible_actions_before_pruning=pre_pruning_feasible,
            retained_by_stage=retained,
            pruned_actions=len(pruned_actions),
            feasible_pruned_actions=len(scored_actions),
            rejection_reason_counts=tuple(sorted(rejection_counts.items())),
        )
        if not scored_actions:
            raise NoFeasiblePrunedAction(
                "no feasible complete L=2 action remains after pruning",
                accounting,
            )

        # ``_pruned_actions`` is canonical. Strict improvement therefore keeps
        # the lexicographically first action on an exact score tie.
        best = scored_actions[0]
        for candidate in scored_actions[1:]:
            if candidate.objective_value > best.objective_value:
                best = candidate

        result = HybridSolverResult(
            action=best.action,
            objective_value=best.objective_value,
            state_after=state.apply(best.action, configuration),
            feasibility=evaluate_phase0_feasibility(
                best.action,
                state,
                configuration,
                admission,
                known_pair_link_costs,
            ),
            evaluated_actions=len(pruned_actions),
            feasible_actions=len(scored_actions),
        )
        return HybridGreedyDecision(
            result=result,
            scored_actions=tuple(scored_actions),
            accounting=accounting,
        )

    def select_lookahead(
        self,
        *,
        state: GlobalLoadState,
        admission: Mapping[ReplicaChoice, ReplicaAdmission],
        beliefs: Mapping[ReplicaChoice, Sequence[float]],
        known_pair_link_costs: Mapping[
            tuple[ReplicaChoice, ReplicaChoice],
            float,
        ],
    ) -> HybridLookaheadDecision:
        """Select one focal action through deterministic limited lookahead.

        Root focal candidates and every continuation decision use the
        unchanged :meth:`select_greedy` Phase 2 boundary. Each candidate owns
        an immutable branch state. The returned solver state commits only the
        selected focal action; projected continuation states are diagnostic
        evaluations rather than real placements.
        """

        configuration = self.configuration
        state.validate_for(configuration)
        committed_flows = (
            state.total_assignments // configuration.stage_budget
        )
        if committed_flows >= configuration.num_flows:
            raise ValueError("no Hybrid flow remains to place in this slot")
        remaining_flows_after_focal = (
            configuration.num_flows - committed_flows - 1
        )
        requested_depth = self.parameters.lookahead_future_flows
        effective_depth = future_flows_to_simulate(
            remaining_flows_after_focal,
            self.parameters,
        )

        focal_decision = self.select_greedy(
            state=state,
            admission=admission,
            beliefs=beliefs,
            known_pair_link_costs=known_pair_link_costs,
        )
        evaluations = []
        rejected_branches = []
        for scored_focal in focal_decision.scored_actions:
            focal_action = scored_focal.action
            branch_state = state.apply(focal_action, configuration)
            state_after_focal = branch_state
            continuation_steps = []
            failed_accounting = None
            for _future_index in range(effective_depth):
                try:
                    continuation = self.select_greedy(
                        state=branch_state,
                        admission=admission,
                        beliefs=beliefs,
                        known_pair_link_costs=known_pair_link_costs,
                    )
                except NoFeasiblePrunedAction as error:
                    failed_accounting = error.accounting
                    break
                step = HybridLookaheadStep(
                    state_before=branch_state,
                    decision=continuation,
                )
                continuation_steps.append(step)
                branch_state = step.state_after

            if failed_accounting is not None:
                rejected_branches.append(
                    HybridLookaheadBranchFailure(
                        focal_action=focal_action,
                        state_after_focal=state_after_focal,
                        completed_steps=tuple(continuation_steps),
                        failing_state=branch_state,
                        failure_accounting=failed_accounting,
                        requested_depth=requested_depth,
                        effective_depth=effective_depth,
                    )
                )
                continue

            focal_value = focal_utility_at_projected_loads(
                focal_action,
                branch_state,
                configuration,
                lambda choice, load: expected_stage_utility_from_belief(
                    beliefs[choice],
                    load,
                ),
                lambda source, target: known_pair_link_costs[(source, target)],
                link_weight=HYBRID_LINK_WEIGHT_UTILITY_PER_MS,
            )
            evaluations.append(
                HybridLookaheadEvaluation(
                    focal_action=focal_action,
                    state_after_focal=state_after_focal,
                    projected_final_state=branch_state,
                    continuation_steps=tuple(continuation_steps),
                    focal_value=focal_value,
                    requested_depth=requested_depth,
                    effective_depth=effective_depth,
                )
            )

        if not evaluations:
            raise NoFeasibleLookaheadAction(
                "no root-feasible focal action has a complete greedy continuation",
                focal_decision.accounting,
                tuple(rejected_branches),
            )

        # Root candidates are in canonical order. Strict improvement therefore
        # retains the first canonical focal action on an exact lookahead tie.
        best = evaluations[0]
        for candidate in evaluations[1:]:
            if candidate.focal_value > best.focal_value:
                best = candidate

        result = HybridSolverResult(
            action=best.focal_action,
            objective_value=best.focal_value,
            state_after=state.apply(best.focal_action, configuration),
            feasibility=evaluate_phase0_feasibility(
                best.focal_action,
                state,
                configuration,
                admission,
                known_pair_link_costs,
            ),
            evaluated_actions=focal_decision.accounting.pruned_actions,
            feasible_actions=len(evaluations),
        )
        return HybridLookaheadDecision(
            result=result,
            evaluations=tuple(evaluations),
            focal_accounting=focal_decision.accounting,
            rejected_branches=tuple(rejected_branches),
        )

    def select_monte_carlo(
        self,
        *,
        state: GlobalLoadState,
        admission: Mapping[ReplicaChoice, ReplicaAdmission],
        beliefs: Mapping[ReplicaChoice, Sequence[float]],
        known_pair_link_costs: Mapping[
            tuple[ReplicaChoice, ReplicaChoice],
            float,
        ],
        root_seed: int,
        slot_id: int,
        decision_position: int,
        flow_id: int,
    ) -> HybridMonteCarloDecision:
        """Select a focal action by seeded epsilon-greedy continuations."""

        configuration = self.configuration
        state.validate_for(configuration)
        committed_flows = (
            state.total_assignments // configuration.stage_budget
        )
        if committed_flows >= configuration.num_flows:
            raise ValueError("no Hybrid flow remains to place in this slot")
        remaining_flows_after_focal = (
            configuration.num_flows - committed_flows - 1
        )
        requested_depth = self.parameters.lookahead_future_flows
        effective_depth = future_flows_to_simulate(
            remaining_flows_after_focal,
            self.parameters,
        )
        requested_samples = self.parameters.monte_carlo_samples
        epsilon = float(self.parameters.rollout_epsilon)

        focal_decision = self.select_greedy(
            state=state,
            admission=admission,
            beliefs=beliefs,
            known_pair_link_costs=known_pair_link_costs,
        )
        evaluations = []
        rejected_candidates = []
        for scored_focal in focal_decision.scored_actions:
            focal_action = scored_focal.action
            state_after_focal = state.apply(focal_action, configuration)
            completed_samples = []
            failed_samples = []
            for sample_index in range(requested_samples):
                seed_key = RolloutSeedKey(
                    root_seed=root_seed,
                    slot_id=slot_id,
                    decision_position=decision_position,
                    flow_id=flow_id,
                    action=focal_action,
                    sample_index=sample_index,
                )
                derived_seed = derive_rollout_seed(seed_key)
                generator = Random(derived_seed)
                branch_state = state_after_focal
                continuation_steps = []
                failed_accounting = None

                for _future_index in range(effective_depth):
                    try:
                        continuation = self.select_greedy(
                            state=branch_state,
                            admission=admission,
                            beliefs=beliefs,
                            known_pair_link_costs=known_pair_link_costs,
                        )
                    except NoFeasiblePrunedAction as error:
                        failed_accounting = error.accounting
                        break

                    feasible_actions = tuple(
                        scored.action
                        for scored in continuation.scored_actions
                    )
                    if epsilon <= 0.0:
                        choice_mode = RolloutChoiceMode.GREEDY
                        chosen_action = continuation.result.action
                    elif epsilon >= 1.0:
                        choice_mode = RolloutChoiceMode.EXPLORATION
                        chosen_action = feasible_actions[
                            generator.randrange(len(feasible_actions))
                        ]
                    elif generator.random() < epsilon:
                        choice_mode = RolloutChoiceMode.EXPLORATION
                        chosen_action = feasible_actions[
                            generator.randrange(len(feasible_actions))
                        ]
                    else:
                        choice_mode = RolloutChoiceMode.GREEDY
                        chosen_action = continuation.result.action

                    state_after_step = branch_state.apply(
                        chosen_action,
                        configuration,
                    )
                    step = HybridMonteCarloStep(
                        state_before=branch_state,
                        chosen_action=chosen_action,
                        greedy_action=continuation.result.action,
                        choice_mode=choice_mode,
                        feasible_actions=feasible_actions,
                        accounting=continuation.accounting,
                        state_after=state_after_step,
                    )
                    continuation_steps.append(step)
                    branch_state = state_after_step

                if failed_accounting is not None:
                    failed_samples.append(
                        HybridMonteCarloSampleFailure(
                            seed_key=seed_key,
                            derived_seed=derived_seed,
                            state_after_focal=state_after_focal,
                            completed_steps=tuple(continuation_steps),
                            failing_state=branch_state,
                            failure_accounting=failed_accounting,
                            requested_depth=requested_depth,
                            effective_depth=effective_depth,
                        )
                    )
                    continue

                focal_value = focal_utility_at_projected_loads(
                    focal_action,
                    branch_state,
                    configuration,
                    lambda choice, load: expected_stage_utility_from_belief(
                        beliefs[choice],
                        load,
                    ),
                    lambda source, target: known_pair_link_costs[
                        (source, target)
                    ],
                    link_weight=HYBRID_LINK_WEIGHT_UTILITY_PER_MS,
                )
                completed_samples.append(
                    HybridMonteCarloSample(
                        seed_key=seed_key,
                        derived_seed=derived_seed,
                        state_after_focal=state_after_focal,
                        projected_final_state=branch_state,
                        continuation_steps=tuple(continuation_steps),
                        focal_value=focal_value,
                        requested_depth=requested_depth,
                        effective_depth=effective_depth,
                    )
                )

            if not completed_samples:
                rejected_candidates.append(
                    HybridMonteCarloRejectedCandidate(
                        focal_action=focal_action,
                        failed_samples=tuple(failed_samples),
                        requested_samples=requested_samples,
                        requested_depth=requested_depth,
                        effective_depth=effective_depth,
                    )
                )
                continue

            mean_focal_value = fsum(
                sample.focal_value for sample in completed_samples
            ) / len(completed_samples)
            evaluations.append(
                HybridMonteCarloEvaluation(
                    focal_action=focal_action,
                    samples=tuple(completed_samples),
                    failed_samples=tuple(failed_samples),
                    mean_focal_value=mean_focal_value,
                    requested_samples=requested_samples,
                    requested_depth=requested_depth,
                    effective_depth=effective_depth,
                )
            )

        if not evaluations:
            raise NoFeasibleMonteCarloAction(
                "no focal action has a completed Monte Carlo sample",
                focal_decision.accounting,
                tuple(rejected_candidates),
            )

        # Root candidates are canonical. Strict improvement retains the first
        # canonical focal action on an exact mean-value tie.
        best = evaluations[0]
        for candidate in evaluations[1:]:
            if candidate.mean_focal_value > best.mean_focal_value:
                best = candidate

        result = HybridSolverResult(
            action=best.focal_action,
            objective_value=best.mean_focal_value,
            state_after=state.apply(best.focal_action, configuration),
            feasibility=evaluate_phase0_feasibility(
                best.focal_action,
                state,
                configuration,
                admission,
                known_pair_link_costs,
            ),
            evaluated_actions=focal_decision.accounting.pruned_actions,
            feasible_actions=len(evaluations),
        )
        return HybridMonteCarloDecision(
            result=result,
            evaluations=tuple(evaluations),
            rejected_candidates=tuple(rejected_candidates),
            focal_accounting=focal_decision.accounting,
            root_seed=root_seed,
            slot_id=slot_id,
            decision_position=decision_position,
            flow_id=flow_id,
            rollout_seed_scheme=HYBRID_ROLLOUT_SEED_SCHEME,
            requested_samples=requested_samples,
        )
