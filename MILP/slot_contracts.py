"""Immutable contracts for one pure coupled-MILP simulation slot."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from numbers import Integral, Real

from .contracts import (
    MILP_PHASE1_CONTRACT_VERSION,
    MILPConfiguration,
    MILPPlacement,
    MILPProblemInput,
    MILPSolverResult,
)
from .model import MILP_PHASE2_MODEL_VERSION
from .phase0_contract import (
    MILP_PHASE0_CONTRACT_VERSION,
    MILPContractError,
    ReplicaKey,
    SolverResultStatus,
    required_directed_pairs,
)
from .solver import MILP_PHASE2_SOLVER_VERSION


MILP_PHASE3_SLOT_CONTRACT_VERSION = "milp-coupled-phase3-slot-v1"
MILP_PHASE3_SIMULATION_ADAPTER_VERSION = "milp-in-process-simulation-v1"
MILP_PHYSICAL_SEED_SCHEME = "blake2b-milp-physical-v1"
MILP_OBSERVATION_SEED_SCHEME = "blake2b-milp-observation-v1"
MILP_MEASURED_PAIR_SEED_SCHEME = "blake2b-milp-measured-pair-v1"


def _finite_number(value: object, field: str, *, nonnegative: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise MILPContractError(f"{field} must be a finite real number")
    result = float(value)
    if not isfinite(result):
        raise MILPContractError(f"{field} must be a finite real number")
    if nonnegative and result < 0.0:
        raise MILPContractError(f"{field} must be nonnegative")
    return result


def _positive_integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 1:
        raise MILPContractError(f"{field} must be a positive integer")
    return int(value)


def _seed(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 0:
        raise MILPContractError(f"{field} must be a nonnegative integer")
    return int(value)


@dataclass(frozen=True, order=True)
class MeasuredPairLatencyProfile:
    """Outcome-only model for one directed selected-pair measurement.

    This profile is never passed to the MILP solver. The in-process adapter
    samples ``base_ms + |Normal(0, jitter_ms)|`` from its dedicated stream.
    """

    source: ReplicaKey
    target: ReplicaKey
    base_ms: float
    jitter_ms: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.source, ReplicaKey) or not isinstance(
            self.target, ReplicaKey
        ):
            raise MILPContractError("measured-pair endpoints must be ReplicaKey")
        if self.source.stage >= self.target.stage:
            raise MILPContractError(
                "measured-pair profile must follow increasing selected stages"
            )
        object.__setattr__(
            self,
            "base_ms",
            _finite_number(self.base_ms, "measured-pair base_ms", nonnegative=True),
        )
        object.__setattr__(
            self,
            "jitter_ms",
            _finite_number(
                self.jitter_ms,
                "measured-pair jitter_ms",
                nonnegative=True,
            ),
        )

    @property
    def pair(self) -> tuple[ReplicaKey, ReplicaKey]:
        return self.source, self.target


@dataclass(frozen=True)
class MILPSlotInput:
    """Complete planner and outcome-model input for one centralized slot."""

    problem: MILPProblemInput
    root_seed: int
    slot_id: int
    measured_pair_profiles: tuple[MeasuredPairLatencyProfile, ...]
    contract_version: str = MILP_PHASE3_SLOT_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.problem, MILPProblemInput):
            raise MILPContractError("problem must be MILPProblemInput")
        object.__setattr__(self, "root_seed", _seed(self.root_seed, "root_seed"))
        object.__setattr__(self, "slot_id", _positive_integer(self.slot_id, "slot_id"))
        if not isinstance(self.measured_pair_profiles, tuple) or any(
            not isinstance(item, MeasuredPairLatencyProfile)
            for item in self.measured_pair_profiles
        ):
            raise MILPContractError(
                "measured_pair_profiles must be an immutable profile tuple"
            )
        if self.contract_version != MILP_PHASE3_SLOT_CONTRACT_VERSION:
            raise MILPContractError("unexpected MILP Phase 3 slot contract version")
        expected_pairs = required_directed_pairs(
            self.problem.configuration.dimensions
        )
        actual_pairs = tuple(item.pair for item in self.measured_pair_profiles)
        if actual_pairs != expected_pairs:
            missing = tuple(sorted(set(expected_pairs) - set(actual_pairs)))
            extra = tuple(sorted(set(actual_pairs) - set(expected_pairs)))
            raise MILPContractError(
                "measured-pair profile mismatch or noncanonical order: "
                f"missing={missing}, extra={extra}"
            )

    def measured_pair_profile_by_pair(
        self,
    ) -> dict[tuple[ReplicaKey, ReplicaKey], MeasuredPairLatencyProfile]:
        return {item.pair: item for item in self.measured_pair_profiles}


@dataclass(frozen=True, order=True)
class MILPSelectedObservation:
    """One selected physical sample and separate noisy telemetry signal."""

    flow_id: int
    key: ReplicaKey
    assigned_load: int
    physical_processing_latency_ms: float
    observation_jitter_ms: float
    noisy_signal_ms: float
    likelihood: tuple[float, float, float, float]
    estimated_state: int
    physical_seed: int
    observation_seed: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "flow_id", _positive_integer(self.flow_id, "flow_id"))
        if not isinstance(self.key, ReplicaKey):
            raise MILPContractError("observation key must be ReplicaKey")
        object.__setattr__(
            self,
            "assigned_load",
            _positive_integer(self.assigned_load, "assigned_load"),
        )
        for field in (
            "physical_processing_latency_ms",
            "observation_jitter_ms",
            "noisy_signal_ms",
        ):
            object.__setattr__(
                self,
                field,
                _finite_number(getattr(self, field), field, nonnegative=True),
            )
        if self.physical_processing_latency_ms <= 0.0:
            raise MILPContractError("physical processing latency must be positive")
        if abs(
            self.noisy_signal_ms
            - self.physical_processing_latency_ms
            - self.observation_jitter_ms
        ) > 1e-9:
            raise MILPContractError(
                "noisy signal must equal physical latency plus observation jitter"
            )
        likelihood = tuple(float(value) for value in self.likelihood)
        if len(likelihood) != 4 or any(
            not isfinite(value) or value < 0.0 for value in likelihood
        ) or abs(sum(likelihood) - 1.0) > 1e-9:
            raise MILPContractError(
                "likelihood must contain four normalized nonnegative values"
            )
        object.__setattr__(self, "likelihood", likelihood)
        if self.estimated_state not in (1, 2, 3, 4):
            raise MILPContractError("estimated_state must be one of 1, 2, 3, or 4")
        object.__setattr__(
            self,
            "physical_seed",
            _seed(self.physical_seed, "physical_seed"),
        )
        object.__setattr__(
            self,
            "observation_seed",
            _seed(self.observation_seed, "observation_seed"),
        )


@dataclass(frozen=True, order=True)
class MILPMeasuredPairOutcome:
    """One sampled outcome for the selected directed pair of a flow."""

    flow_id: int
    source: ReplicaKey
    target: ReplicaKey
    latency_ms: float
    pair_seed: int
    profile_base_ms: float
    profile_jitter_ms: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "flow_id", _positive_integer(self.flow_id, "flow_id"))
        if not isinstance(self.source, ReplicaKey) or not isinstance(
            self.target, ReplicaKey
        ):
            raise MILPContractError("measured-pair endpoints must be ReplicaKey")
        if self.source.stage >= self.target.stage:
            raise MILPContractError("measured pair must follow increasing stages")
        for field in ("latency_ms", "profile_base_ms", "profile_jitter_ms"):
            object.__setattr__(
                self,
                field,
                _finite_number(getattr(self, field), field, nonnegative=True),
            )
        object.__setattr__(self, "pair_seed", _seed(self.pair_seed, "pair_seed"))

    @property
    def pair(self) -> tuple[ReplicaKey, ReplicaKey]:
        return self.source, self.target


@dataclass(frozen=True)
class MILPSimulationResult:
    observations: tuple[MILPSelectedObservation, ...]
    measured_pairs: tuple[MILPMeasuredPairOutcome, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.observations, tuple) or any(
            not isinstance(item, MILPSelectedObservation)
            for item in self.observations
        ):
            raise MILPContractError("observations must be an immutable tuple")
        if not isinstance(self.measured_pairs, tuple) or any(
            not isinstance(item, MILPMeasuredPairOutcome)
            for item in self.measured_pairs
        ):
            raise MILPContractError("measured_pairs must be an immutable tuple")


@dataclass(frozen=True)
class MILPSlotMetrics:
    solver_expected_stage_welfare_utility: float
    solver_configured_planning_link_cost_ms: float
    solver_configured_planning_link_deduction_utility: float
    solver_total_social_welfare_utility: float
    physical_realized_utility: float
    physical_realized_utility_per_flow: tuple[tuple[int, float], ...]
    physical_processing_latency_ms: float
    physical_processing_latency_ms_per_flow: tuple[tuple[int, float], ...]
    measured_pair_latency_ms: float
    measured_pair_latency_ms_per_flow: tuple[tuple[int, float], ...]
    raw_end_to_end_latency_ms: float
    raw_end_to_end_latency_ms_per_flow: tuple[tuple[int, float], ...]
    physical_plus_pair_reference_utility: float
    physical_plus_pair_reference_utility_per_flow: tuple[tuple[int, float], ...]
    physical_only_sla_violations: int
    jain_fairness: float
    model_build_seconds: float
    solver_seconds: float
    simulation_seconds: float
    total_slot_seconds: float
    solver_status: SolverResultStatus
    incumbent_objective_utility: float
    best_bound_utility: float
    absolute_gap_utility: float
    relative_gap: float

    def __post_init__(self) -> None:
        scalar_fields = (
            "solver_expected_stage_welfare_utility",
            "solver_configured_planning_link_cost_ms",
            "solver_configured_planning_link_deduction_utility",
            "solver_total_social_welfare_utility",
            "physical_realized_utility",
            "physical_processing_latency_ms",
            "measured_pair_latency_ms",
            "raw_end_to_end_latency_ms",
            "physical_plus_pair_reference_utility",
            "jain_fairness",
            "model_build_seconds",
            "solver_seconds",
            "simulation_seconds",
            "total_slot_seconds",
            "incumbent_objective_utility",
            "best_bound_utility",
            "absolute_gap_utility",
            "relative_gap",
        )
        for field in scalar_fields:
            object.__setattr__(self, field, _finite_number(getattr(self, field), field))
        for field in (
            "solver_configured_planning_link_cost_ms",
            "solver_configured_planning_link_deduction_utility",
            "physical_processing_latency_ms",
            "measured_pair_latency_ms",
            "raw_end_to_end_latency_ms",
            "model_build_seconds",
            "solver_seconds",
            "simulation_seconds",
            "total_slot_seconds",
            "absolute_gap_utility",
            "relative_gap",
        ):
            if getattr(self, field) < 0.0:
                raise MILPContractError(f"{field} must be nonnegative")
        # The frozen Exact helper rounds per-flow values to three decimals
        # while retaining the unrounded aggregate numerator, so its reported
        # value can exceed the mathematical upper bound by a tiny amount.
        if self.jain_fairness < 0.0:
            raise MILPContractError("jain_fairness must be nonnegative")
        if (
            isinstance(self.physical_only_sla_violations, bool)
            or not isinstance(self.physical_only_sla_violations, Integral)
            or self.physical_only_sla_violations < 0
        ):
            raise MILPContractError(
                "physical_only_sla_violations must be a nonnegative integer"
            )
        if self.solver_status not in (
            SolverResultStatus.PROVEN_OPTIMAL,
            SolverResultStatus.TIME_LIMIT_WITH_INCUMBENT,
        ):
            raise MILPContractError("slot metrics require an executable incumbent")
        for field in (
            "physical_realized_utility_per_flow",
            "physical_processing_latency_ms_per_flow",
            "measured_pair_latency_ms_per_flow",
            "raw_end_to_end_latency_ms_per_flow",
            "physical_plus_pair_reference_utility_per_flow",
        ):
            values = getattr(self, field)
            if not isinstance(values, tuple):
                raise MILPContractError(f"{field} must be an immutable tuple")
            flow_ids = tuple(flow_id for flow_id, _value in values)
            if flow_ids != tuple(sorted(flow_ids)) or len(flow_ids) != len(set(flow_ids)):
                raise MILPContractError(f"{field} must use unique canonical flow order")
            if any(
                isinstance(flow_id, bool)
                or not isinstance(flow_id, Integral)
                or flow_id < 1
                or not isfinite(float(value))
                for flow_id, value in values
            ):
                raise MILPContractError(f"{field} contains an invalid value")


@dataclass(frozen=True)
class MILPSlotResult:
    """Complete in-memory record for one executed centralized placement."""

    configuration: MILPConfiguration
    root_seed: int
    slot_id: int
    solver_result: MILPSolverResult
    placement: MILPPlacement
    bypassed_stages_by_flow: tuple[tuple[int, tuple[int, ...]], ...]
    final_replica_loads: tuple[tuple[ReplicaKey, int], ...]
    observations: tuple[MILPSelectedObservation, ...]
    measured_pairs: tuple[MILPMeasuredPairOutcome, ...]
    metrics: MILPSlotMetrics
    phase0_contract_version: str = MILP_PHASE0_CONTRACT_VERSION
    phase1_contract_version: str = MILP_PHASE1_CONTRACT_VERSION
    phase2_model_version: str = MILP_PHASE2_MODEL_VERSION
    phase2_solver_version: str = MILP_PHASE2_SOLVER_VERSION
    phase3_slot_contract_version: str = MILP_PHASE3_SLOT_CONTRACT_VERSION
    simulation_adapter_version: str = MILP_PHASE3_SIMULATION_ADAPTER_VERSION
    physical_seed_scheme: str = MILP_PHYSICAL_SEED_SCHEME
    observation_seed_scheme: str = MILP_OBSERVATION_SEED_SCHEME
    measured_pair_seed_scheme: str = MILP_MEASURED_PAIR_SEED_SCHEME

    def __post_init__(self) -> None:
        if not isinstance(self.configuration, MILPConfiguration):
            raise MILPContractError("slot configuration must be MILPConfiguration")
        object.__setattr__(self, "root_seed", _seed(self.root_seed, "root_seed"))
        object.__setattr__(self, "slot_id", _positive_integer(self.slot_id, "slot_id"))
        if not isinstance(self.solver_result, MILPSolverResult):
            raise MILPContractError("solver_result must be MILPSolverResult")
        if not isinstance(self.placement, MILPPlacement):
            raise MILPContractError("placement must be MILPPlacement")
        if self.solver_result.placement != self.placement:
            raise MILPContractError("slot placement must match solver incumbent")
        if self.final_replica_loads != self.placement.final_loads:
            raise MILPContractError("slot final loads must match solver placement")
        if not isinstance(self.metrics, MILPSlotMetrics):
            raise MILPContractError("metrics must be MILPSlotMetrics")
        dimensions = self.configuration.dimensions
        if len(self.observations) != dimensions.flow_count * 2:
            raise MILPContractError("slot must retain exactly two observations per flow")
        if len(self.measured_pairs) != dimensions.flow_count:
            raise MILPContractError("slot must retain exactly one measured pair per flow")
        expected_versions = (
            (self.phase0_contract_version, MILP_PHASE0_CONTRACT_VERSION),
            (self.phase1_contract_version, MILP_PHASE1_CONTRACT_VERSION),
            (self.phase2_model_version, MILP_PHASE2_MODEL_VERSION),
            (self.phase2_solver_version, MILP_PHASE2_SOLVER_VERSION),
            (self.phase3_slot_contract_version, MILP_PHASE3_SLOT_CONTRACT_VERSION),
            (
                self.simulation_adapter_version,
                MILP_PHASE3_SIMULATION_ADAPTER_VERSION,
            ),
            (self.physical_seed_scheme, MILP_PHYSICAL_SEED_SCHEME),
            (self.observation_seed_scheme, MILP_OBSERVATION_SEED_SCHEME),
            (self.measured_pair_seed_scheme, MILP_MEASURED_PAIR_SEED_SCHEME),
        )
        if any(actual != expected for actual, expected in expected_versions):
            raise MILPContractError("slot result contains an unexpected contract version")
