"""Versioned, bounded Phase 4 scale and optimality evidence boundary."""

from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import blake2b
from math import isclose, isfinite
from numbers import Integral
import resource
import sys
from time import monotonic
from typing import Callable

from .contracts import (
    MILPConfiguration,
    MILPProblemInput,
    MILPSolverResult,
    build_problem_input,
)
from .experiment_profile import (
    MILP_EXPLICIT_PLANNING_LINK_MODE,
    MILP_PLANNING_LINK_PROFILE_VERSION,
    MILPExperimentPlanningLink,
    MILPExperimentProfile,
    MILPExperimentReplica,
)
from .model import exact_known_state_expected_utility
from .oracle import solve_tiny_exhaustive
from .phase0_contract import (
    DEFAULT_MILP_DIMENSIONS,
    MILP_ACTION_CARDINALITY,
    MILPContractError,
    ReplicaAdmission,
    SolverResultStatus,
    required_directed_pairs,
)
from .runner import MILPSlotExecutionError, run_milp_slot
from .simulation import MILPSlotSimulationAdapter
from .slot_contracts import (
    MILPSlotInput,
    MILPSlotResult,
    MeasuredPairLatencyProfile,
)
from .runtime_profiles import MILPRuntimeReplicaProfile
from .solver import solve_coupled_milp


MILP_PHASE4_SCALE_CONTRACT_VERSION = "milp-coupled-phase4-scale-v1"
MILP_PHASE4_SYNTHETIC_PROFILE_V1 = "milp-scale-synthetic-profile-v1"
MILP_PHASE4_SYNTHETIC_PROFILE_VERSION = "milp-scale-synthetic-profile-v2"
MILP_SUPPORTED_SYNTHETIC_PROFILE_VERSIONS = frozenset(
    (MILP_PHASE4_SYNTHETIC_PROFILE_V1, MILP_PHASE4_SYNTHETIC_PROFILE_VERSION)
)
MILP_PHASE4_MEMORY_SCOPE = "current-process-ru_maxrss-high-water-mark-v1"
MILP_PHASE4_BACKEND_PARITY = "not-applicable-single-available-backend"
MILP_SYNTHETIC_SCALE_EXPERIMENT_IDENTITY = "phase4-synthetic-scale"

# Increasing development cases terminating at the initial paper-scale shape.
MILP_SCALE_LADDER = (
    (1, 2, 1),
    (2, 3, 2),
    (5, 3, 4),
    (10, 3, 6),
    (15, 3, 10),
)


def _nonnegative_integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 0:
        raise MILPContractError(f"{field} must be a nonnegative integer")
    return int(value)


def _positive_integer(value: object, field: str) -> int:
    result = _nonnegative_integer(value, field)
    if result < 1:
        raise MILPContractError(f"{field} must be a positive integer")
    return result


def _stable_u64(scheme: str, *values: object) -> int:
    payload = (scheme + "|" + "|".join(str(value) for value in values)).encode(
        "ascii"
    )
    return int.from_bytes(blake2b(payload, digest_size=8).digest(), "big")


@dataclass(frozen=True)
class MILPScaleCase:
    """One explicit deterministic scale run; cutoff is part of the case."""

    name: str
    configuration: MILPConfiguration
    profile_seed: int = 20260801
    root_seed: int = 20260802
    slot_id: int = 1
    profile_version: str = MILP_PHASE4_SYNTHETIC_PROFILE_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise MILPContractError("scale case name must be nonempty")
        if not isinstance(self.configuration, MILPConfiguration):
            raise MILPContractError("scale case configuration must be MILPConfiguration")
        object.__setattr__(
            self,
            "profile_seed",
            _nonnegative_integer(self.profile_seed, "profile_seed"),
        )
        object.__setattr__(
            self,
            "root_seed",
            _nonnegative_integer(self.root_seed, "root_seed"),
        )
        object.__setattr__(self, "slot_id", _positive_integer(self.slot_id, "slot_id"))
        if self.profile_version not in MILP_SUPPORTED_SYNTHETIC_PROFILE_VERSIONS:
            raise MILPContractError("unexpected Phase 4 synthetic profile version")


@dataclass(frozen=True)
class MILPScaleEvidence:
    """Compact reproducible evidence retained alongside the full run result."""

    case_name: str
    flow_count: int
    stage_count: int
    replicas_per_stage: tuple[int, ...]
    action_cardinality: int
    requested_cutoff_seconds: float
    profile_seed: int
    root_seed: int
    slot_id: int
    profile_version: str
    backend_name: str
    backend_version: str
    backend_parity: str
    solver_status: SolverResultStatus
    optimality_proven: bool
    incumbent_objective_utility: float | None
    best_bound_utility: float | None
    absolute_gap_utility: float | None
    relative_gap: float | None
    model_build_seconds: float
    solver_seconds: float
    simulation_seconds: float | None
    total_wall_seconds: float
    variable_count: int | None
    constraint_count: int | None
    peak_process_rss_before_bytes: int
    peak_process_rss_after_bytes: int
    peak_process_rss_growth_bytes: int
    memory_scope: str
    slot_executed: bool
    oracle_verified: bool
    oracle_objective_utility: float | None
    oracle_complete_placements: int | None
    contract_version: str = MILP_PHASE4_SCALE_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.action_cardinality != MILP_ACTION_CARDINALITY:
            raise MILPContractError("scale evidence must retain exact L=2")
        if self.optimality_proven != (
            self.solver_status is SolverResultStatus.PROVEN_OPTIMAL
        ):
            raise MILPContractError("scale optimality flag does not match status")
        if self.slot_executed != (
            self.solver_status
            in (
                SolverResultStatus.PROVEN_OPTIMAL,
                SolverResultStatus.TIME_LIMIT_WITH_INCUMBENT,
            )
        ):
            raise MILPContractError("slot execution does not match incumbent status")
        if self.contract_version != MILP_PHASE4_SCALE_CONTRACT_VERSION:
            raise MILPContractError("unexpected Phase 4 scale contract version")
        if self.profile_version not in MILP_SUPPORTED_SYNTHETIC_PROFILE_VERSIONS:
            raise MILPContractError("unexpected Phase 4 evidence profile version")
        if self.memory_scope != MILP_PHASE4_MEMORY_SCOPE:
            raise MILPContractError("unexpected Phase 4 memory scope")
        if self.backend_parity != MILP_PHASE4_BACKEND_PARITY:
            raise MILPContractError("unexpected backend parity statement")
        for field in (
            "model_build_seconds",
            "solver_seconds",
            "total_wall_seconds",
        ):
            value = float(getattr(self, field))
            if not isfinite(value) or value < 0.0:
                raise MILPContractError(f"{field} must be finite and nonnegative")
        if self.simulation_seconds is not None and (
            not isfinite(self.simulation_seconds) or self.simulation_seconds < 0.0
        ):
            raise MILPContractError("simulation_seconds must be finite and nonnegative")
        for field in (
            "peak_process_rss_before_bytes",
            "peak_process_rss_after_bytes",
            "peak_process_rss_growth_bytes",
        ):
            _nonnegative_integer(getattr(self, field), field)
        if self.peak_process_rss_after_bytes < self.peak_process_rss_before_bytes:
            raise MILPContractError("process peak RSS cannot decrease")
        if self.peak_process_rss_growth_bytes != (
            self.peak_process_rss_after_bytes - self.peak_process_rss_before_bytes
        ):
            raise MILPContractError("peak RSS growth does not reconstruct")
        if self.oracle_verified:
            if (
                not self.optimality_proven
                or self.oracle_objective_utility is None
                or self.oracle_complete_placements is None
            ):
                raise MILPContractError("oracle verification requires proven evidence")
        elif self.oracle_objective_utility is not None or (
            self.oracle_complete_placements is not None
        ):
            raise MILPContractError("unverified evidence cannot carry oracle values")


@dataclass(frozen=True)
class MILPScaleRunResult:
    case: MILPScaleCase
    problem: MILPProblemInput
    solver_result: MILPSolverResult
    slot_result: MILPSlotResult | None
    evidence: MILPScaleEvidence


def make_scale_case(
    *,
    flow_count: int = DEFAULT_MILP_DIMENSIONS.flow_count,
    stage_count: int = DEFAULT_MILP_DIMENSIONS.stage_count,
    replicas_per_stage: int = DEFAULT_MILP_DIMENSIONS.replicas_per_stage[0],
    cutoff_seconds: float,
    profile_seed: int = 20260801,
    root_seed: int = 20260802,
    slot_id: int = 1,
    profile_version: str = MILP_PHASE4_SYNTHETIC_PROFILE_VERSION,
) -> MILPScaleCase:
    configuration = MILPConfiguration.uniform(
        flow_count=flow_count,
        stage_count=stage_count,
        replicas_per_stage=replicas_per_stage,
        cutoff_seconds=cutoff_seconds,
    )
    return MILPScaleCase(
        name=f"{flow_count}x{stage_count}x{replicas_per_stage}",
        configuration=configuration,
        profile_seed=profile_seed,
        root_seed=root_seed,
        slot_id=slot_id,
        profile_version=profile_version,
    )


def make_scale_ladder(*, cutoff_seconds: float) -> tuple[MILPScaleCase, ...]:
    return tuple(
        make_scale_case(
            flow_count=flows,
            stage_count=stages,
            replicas_per_stage=replicas,
            cutoff_seconds=cutoff_seconds,
        )
        for flows, stages, replicas in MILP_SCALE_LADDER
    )


def build_scale_slot_input(case: MILPScaleCase) -> MILPSlotInput:
    """Build the declared synthetic profile without consuming an RNG."""

    dimensions = case.configuration.dimensions
    true_states = {
        key: 1
        + _stable_u64(
            "milp-scale-true-state-v1",
            case.profile_seed,
            key.stage,
            key.replica,
        )
        % 4
        for key in dimensions.replica_keys
    }
    admission = {
        key: ReplicaAdmission(True, dimensions.flow_count)
        for key in dimensions.replica_keys
    }
    pairs = required_directed_pairs(dimensions)
    planning_base_ms, planning_span_millis, planning_scheme = (
        (0.5, 5_000, "milp-scale-planning-link-v1")
        if case.profile_version == MILP_PHASE4_SYNTHETIC_PROFILE_V1
        else (65.0, 10_000, "milp-scale-planning-link-v2")
    )
    planning_links = {
        pair: planning_base_ms
        + _stable_u64(
            planning_scheme,
            case.profile_seed,
            pair[0].stage,
            pair[0].replica,
            pair[1].stage,
            pair[1].replica,
        )
        % planning_span_millis
        / 1000.0
        for pair in pairs
    }
    problem = build_problem_input(
        case.configuration,
        true_states=true_states,
        admission=admission,
        planning_link_cost_ms=planning_links,
    )
    measured_profiles = tuple(
        MeasuredPairLatencyProfile(
            source,
            target,
            base_ms=(
                5.0
                + _stable_u64(
                    "milp-scale-measured-pair-v1",
                    case.profile_seed,
                    source.stage,
                    source.replica,
                    target.stage,
                    target.replica,
                )
                % 10000
                / 1000.0
            ),
            jitter_ms=0.75,
        )
        for source, target in pairs
    )
    return MILPSlotInput(
        problem=problem,
        root_seed=case.root_seed,
        slot_id=case.slot_id,
        measured_pair_profiles=measured_profiles,
    )


def build_synthetic_scale_experiment_profile(
    case: MILPScaleCase,
) -> MILPExperimentProfile:
    """Expose the Phase 4 synthetic planner input through the common profile.

    This is an explicit comparison mode, not a replacement for the deployed
    runtime-state profile or an assertion that the synthetic coefficients are
    measured network latency.
    """

    slot_input = build_scale_slot_input(case)
    problem = slot_input.problem
    return MILPExperimentProfile(
        configuration=case.configuration,
        replicas=tuple(
            MILPExperimentReplica(
                key=item.key,
                true_state=item.true_state,
                ready=item.admission.ready,
                assigned_flow_capacity=item.admission.assigned_flow_capacity,
            )
            for item in problem.replicas
        ),
        planning_links=tuple(
            MILPExperimentPlanningLink(item.source, item.target, item.cost_ms)
            for item in problem.planning_links
        ),
        measured_pair_profiles=slot_input.measured_pair_profiles,
        source_identity=(
            f"{MILP_SYNTHETIC_SCALE_EXPERIMENT_IDENTITY}:"
            f"version={case.profile_version}:profile-seed={case.profile_seed}"
        ),
        planning_link_mode=MILP_EXPLICIT_PLANNING_LINK_MODE,
        planning_link_source=(
            f"{case.profile_version}:"
            f"profile-seed={case.profile_seed}"
        ),
        planning_link_contract_version=MILP_PLANNING_LINK_PROFILE_VERSION,
    )


def synthetic_scale_runtime_profiles(
    case: MILPScaleCase,
    base_profiles: dict[tuple[int, int], MILPRuntimeReplicaProfile],
) -> dict[tuple[int, int], MILPRuntimeReplicaProfile]:
    """Return Pod profiles whose hidden states match a synthetic scale case.

    Only the state is replaced.  Legacy processor metadata remains service
    configuration and is not repurposed as MILP admission capacity.
    """

    profile = build_synthetic_scale_experiment_profile(case)
    expected = {(item.key.stage, item.key.replica) for item in profile.replicas}
    if set(base_profiles) != expected:
        raise MILPContractError(
            "synthetic-scale runtime profiles must cover every configured replica"
        )
    return {
        (item.key.stage, item.key.replica): replace(
            base_profiles[(item.key.stage, item.key.replica)],
            state=item.true_state,
        )
        for item in profile.replicas
    }


def _peak_process_rss_bytes() -> int:
    raw = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    # Linux reports KiB; macOS reports bytes. The active testbed is Linux,
    # but keep the helper unit-correct for local development on both.
    return raw if sys.platform == "darwin" else raw * 1024


def run_scale_case(
    case: MILPScaleCase,
    *,
    verify_oracle: bool = False,
    solver: Callable[[MILPProblemInput], MILPSolverResult] = solve_coupled_milp,
    simulation_adapter: MILPSlotSimulationAdapter | None = None,
) -> MILPScaleRunResult:
    """Run one bounded case and retain honest success or failure evidence."""

    if not isinstance(case, MILPScaleCase):
        raise MILPContractError("case must be MILPScaleCase")
    slot_input = build_scale_slot_input(case)
    captured: list[MILPSolverResult] = []

    def capturing_solver(problem: MILPProblemInput) -> MILPSolverResult:
        result = solver(problem)
        captured.append(result)
        return result

    rss_before = _peak_process_rss_bytes()
    started = monotonic()
    slot_result = None
    try:
        slot_result = run_milp_slot(
            slot_input,
            solver=capturing_solver,
            simulation_adapter=simulation_adapter,
        )
    except MILPSlotExecutionError:
        # Non-incumbent statuses are valid scale evidence, not executable
        # slots. The complete solver result is retained below.
        pass
    total_seconds = monotonic() - started
    rss_after = _peak_process_rss_bytes()
    if len(captured) != 1:
        raise MILPContractError("scale runner must invoke the MILP solver exactly once")
    solver_result = captured[0]

    oracle_verified = False
    oracle_objective = None
    oracle_placements = None
    if verify_oracle:
        oracle = solve_tiny_exhaustive(
            slot_input.problem,
            exact_known_state_expected_utility(slot_input.problem),
        )
        if (
            solver_result.provenance.status is not SolverResultStatus.PROVEN_OPTIMAL
            or solver_result.placement != oracle.placement
            or solver_result.objective is None
            or not isclose(
                solver_result.objective.total_social_welfare_utility,
                oracle.objective.total_social_welfare_utility,
                rel_tol=1e-12,
                abs_tol=1e-9,
            )
        ):
            raise MILPContractError("scale solver does not agree with tiny oracle")
        oracle_verified = True
        oracle_objective = oracle.objective.total_social_welfare_utility
        oracle_placements = oracle.complete_placements_considered

    provenance = solver_result.provenance
    evidence = MILPScaleEvidence(
        case_name=case.name,
        flow_count=case.configuration.dimensions.flow_count,
        stage_count=case.configuration.dimensions.stage_count,
        replicas_per_stage=case.configuration.dimensions.replicas_per_stage,
        action_cardinality=case.configuration.action_cardinality,
        requested_cutoff_seconds=case.configuration.cutoff_seconds,
        profile_seed=case.profile_seed,
        root_seed=case.root_seed,
        slot_id=case.slot_id,
        profile_version=case.profile_version,
        backend_name=provenance.backend_name,
        backend_version=provenance.backend_version,
        backend_parity=MILP_PHASE4_BACKEND_PARITY,
        solver_status=provenance.status,
        optimality_proven=provenance.optimality_proven,
        incumbent_objective_utility=provenance.incumbent_objective_utility,
        best_bound_utility=provenance.best_bound_utility,
        absolute_gap_utility=provenance.absolute_gap_utility,
        relative_gap=provenance.relative_gap,
        model_build_seconds=provenance.model_build_seconds,
        solver_seconds=provenance.solve_seconds,
        simulation_seconds=(
            None if slot_result is None else slot_result.metrics.simulation_seconds
        ),
        total_wall_seconds=total_seconds,
        variable_count=provenance.variable_count,
        constraint_count=provenance.constraint_count,
        peak_process_rss_before_bytes=rss_before,
        peak_process_rss_after_bytes=rss_after,
        peak_process_rss_growth_bytes=rss_after - rss_before,
        memory_scope=MILP_PHASE4_MEMORY_SCOPE,
        slot_executed=slot_result is not None,
        oracle_verified=oracle_verified,
        oracle_objective_utility=oracle_objective,
        oracle_complete_placements=oracle_placements,
    )
    return MILPScaleRunResult(
        case=case,
        problem=slot_input.problem,
        solver_result=solver_result,
        slot_result=slot_result,
        evidence=evidence,
    )


def format_scale_evidence(evidence: MILPScaleEvidence) -> str:
    def value(item: float | None) -> str:
        return "none" if item is None else f"{item:.6g}"

    rss_mib = evidence.peak_process_rss_after_bytes / (1024.0 * 1024.0)
    return (
        f"MILP scale={evidence.case_name} cutoff={evidence.requested_cutoff_seconds:g}s "
        f"status={evidence.solver_status.value} "
        f"optimal={int(evidence.optimality_proven)} "
        f"incumbent={value(evidence.incumbent_objective_utility)} "
        f"bound={value(evidence.best_bound_utility)} "
        f"gap={value(evidence.relative_gap)} "
        f"build={evidence.model_build_seconds:.6f}s "
        f"solve={evidence.solver_seconds:.6f}s "
        f"total={evidence.total_wall_seconds:.6f}s "
        f"vars={evidence.variable_count} constraints={evidence.constraint_count} "
        f"peak-rss={rss_mib:.3f}MiB"
    )
