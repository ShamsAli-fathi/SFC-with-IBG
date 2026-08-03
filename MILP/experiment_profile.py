"""Canonical same-input profile for pure and Kernel MILP experiments.

This boundary is intentionally separate from the Phase 4 synthetic scale
profile.  It captures every planner coefficient, plus the pure adapter's
outcome-only measured-pair profile, in one immutable JSON-safe document.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import blake2b
import json
from math import isfinite
from numbers import Integral, Real
from pathlib import Path
from typing import Mapping

from .contracts import MILPConfiguration, MILPProblemInput, build_problem_input
from .phase0_contract import (
    MILP_ACTION_CARDINALITY,
    MILPContractError,
    MILPDimensions,
    ReplicaAdmission,
    ReplicaKey,
    required_directed_pairs,
)
from .slot_contracts import MeasuredPairLatencyProfile


MILP_EXPERIMENT_PROFILE_VERSION = "milp-experiment-profile-v1"
MILP_EXPERIMENT_PROFILE_SOURCE = "milp-experiment"
MILP_ASSIGNED_FLOW_CAPACITY_UNIT = "assigned-flows-per-slot"
MILP_PLANNING_LINK_PROFILE_VERSION = "milp-planning-links-v1"
MILP_UNIFORM_PLANNING_LINK_MODE = "uniform-objective-constant"
MILP_EXPLICIT_PLANNING_LINK_MODE = "explicit-directed"
MILP_UNIFORM_PLANNING_LINK_SOURCE = "cli-uniform"
MILP_EXPLICIT_PLANNING_LINK_SOURCE = "user-explicit-json"


def _nonnegative_integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 0:
        raise MILPContractError(f"{field} must be a nonnegative integer")
    return int(value)


def _finite_nonnegative(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise MILPContractError(f"{field} must be finite and nonnegative")
    result = float(value)
    if not isfinite(result) or result < 0.0:
        raise MILPContractError(f"{field} must be finite and nonnegative")
    return result


@dataclass(frozen=True, order=True)
class MILPExperimentReplica:
    key: ReplicaKey
    true_state: int
    ready: bool
    assigned_flow_capacity: int

    def __post_init__(self) -> None:
        if not isinstance(self.key, ReplicaKey):
            raise MILPContractError("experiment replica key must be ReplicaKey")
        if self.true_state not in (1, 2, 3, 4):
            raise MILPContractError("experiment true_state must be one of 1, 2, 3, or 4")
        if not isinstance(self.ready, bool):
            raise MILPContractError("experiment Ready status must be boolean")
        object.__setattr__(
            self,
            "assigned_flow_capacity",
            _nonnegative_integer(
                self.assigned_flow_capacity,
                "assigned_flow_capacity",
            ),
        )


@dataclass(frozen=True, order=True)
class MILPExperimentPlanningLink:
    source: ReplicaKey
    target: ReplicaKey
    cost_ms: float

    def __post_init__(self) -> None:
        if not isinstance(self.source, ReplicaKey) or not isinstance(
            self.target, ReplicaKey
        ):
            raise MILPContractError("experiment planning endpoints must be ReplicaKey")
        if self.source.stage >= self.target.stage:
            raise MILPContractError("experiment planning link must follow increasing stages")
        object.__setattr__(
            self,
            "cost_ms",
            _finite_nonnegative(self.cost_ms, "planning-link cost_ms"),
        )

    @property
    def pair(self) -> tuple[ReplicaKey, ReplicaKey]:
        return self.source, self.target


@dataclass(frozen=True)
class MILPExperimentProfile:
    configuration: MILPConfiguration
    replicas: tuple[MILPExperimentReplica, ...]
    planning_links: tuple[MILPExperimentPlanningLink, ...]
    measured_pair_profiles: tuple[MeasuredPairLatencyProfile, ...]
    source_identity: str
    planning_link_mode: str
    planning_link_source: str
    planning_link_contract_version: str = MILP_PLANNING_LINK_PROFILE_VERSION
    assigned_flow_capacity_unit: str = MILP_ASSIGNED_FLOW_CAPACITY_UNIT
    source: str = MILP_EXPERIMENT_PROFILE_SOURCE
    contract_version: str = MILP_EXPERIMENT_PROFILE_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.configuration, MILPConfiguration):
            raise MILPContractError("experiment configuration must be MILPConfiguration")
        if self.contract_version != MILP_EXPERIMENT_PROFILE_VERSION:
            raise MILPContractError("unexpected MILP experiment-profile version")
        if self.source != MILP_EXPERIMENT_PROFILE_SOURCE:
            raise MILPContractError("unexpected MILP experiment-profile source")
        if not isinstance(self.source_identity, str) or not self.source_identity.strip():
            raise MILPContractError("experiment source_identity must be nonempty")
        if self.assigned_flow_capacity_unit != MILP_ASSIGNED_FLOW_CAPACITY_UNIT:
            raise MILPContractError("MILP capacity unit must be assigned flows per slot")
        if self.planning_link_mode not in (
            MILP_UNIFORM_PLANNING_LINK_MODE,
            MILP_EXPLICIT_PLANNING_LINK_MODE,
        ):
            raise MILPContractError("unexpected planning-link mode")
        if (
            self.planning_link_contract_version
            != MILP_PLANNING_LINK_PROFILE_VERSION
        ):
            raise MILPContractError("unexpected planning-link profile version")
        if not isinstance(self.planning_link_source, str) or not (
            self.planning_link_source.strip()
        ):
            raise MILPContractError("planning-link source must be nonempty")

        dimensions = self.configuration.dimensions
        expected_keys = dimensions.replica_keys
        actual_keys = tuple(item.key for item in self.replicas)
        if actual_keys != expected_keys:
            raise MILPContractError("experiment replicas must exactly cover canonical dimensions")
        expected_pairs = required_directed_pairs(dimensions)
        actual_pairs = tuple(item.pair for item in self.planning_links)
        measured_pairs = tuple(item.pair for item in self.measured_pair_profiles)
        if actual_pairs != expected_pairs:
            raise MILPContractError("experiment planning links must exactly cover canonical pairs")
        if measured_pairs != expected_pairs:
            raise MILPContractError("experiment measured-pair profiles must cover canonical pairs")
        if self.planning_link_mode == MILP_UNIFORM_PLANNING_LINK_MODE:
            values = {item.cost_ms for item in self.planning_links}
            if len(values) != 1:
                raise MILPContractError("uniform planning-link mode requires one common value")

        # Reuse the authoritative Phase 0/1 validators rather than duplicating
        # readiness, capacity, state, or directed-link semantics.
        self.problem_input()

    @property
    def uniform_planning_link_is_objective_constant(self) -> bool:
        return self.planning_link_mode == MILP_UNIFORM_PLANNING_LINK_MODE

    def problem_input(self) -> MILPProblemInput:
        return build_problem_input(
            self.configuration,
            true_states={item.key: item.true_state for item in self.replicas},
            admission={
                item.key: ReplicaAdmission(
                    ready=item.ready,
                    assigned_flow_capacity=item.assigned_flow_capacity,
                )
                for item in self.replicas
            },
            planning_link_cost_ms={item.pair: item.cost_ms for item in self.planning_links},
        )

    def to_document(self) -> dict[str, object]:
        dimensions = self.configuration.dimensions
        return {
            "contract_version": self.contract_version,
            "source": self.source,
            "source_identity": self.source_identity,
            "action_cardinality": MILP_ACTION_CARDINALITY,
            "dimensions": {
                "flow_count": dimensions.flow_count,
                "replicas_per_stage": list(dimensions.replicas_per_stage),
            },
            "cutoff_seconds": self.configuration.cutoff_seconds,
            "assigned_flow_capacity_unit": self.assigned_flow_capacity_unit,
            "planning_link_mode": self.planning_link_mode,
            "planning_link_contract_version": self.planning_link_contract_version,
            "planning_link_source": self.planning_link_source,
            "uniform_planning_link_is_objective_constant": (
                self.uniform_planning_link_is_objective_constant
            ),
            "replicas": [
                {
                    "stage": item.key.stage,
                    "replica": item.key.replica,
                    "true_state": item.true_state,
                    "ready": item.ready,
                    "assigned_flow_capacity": item.assigned_flow_capacity,
                }
                for item in self.replicas
            ],
            "planning_links": [
                {
                    "source_stage": item.source.stage,
                    "source_replica": item.source.replica,
                    "target_stage": item.target.stage,
                    "target_replica": item.target.replica,
                    "cost_ms": item.cost_ms,
                }
                for item in self.planning_links
            ],
            "measured_pair_profiles": [
                {
                    "source_stage": item.source.stage,
                    "source_replica": item.source.replica,
                    "target_stage": item.target.stage,
                    "target_replica": item.target.replica,
                    "base_ms": item.base_ms,
                    "jitter_ms": item.jitter_ms,
                }
                for item in self.measured_pair_profiles
            ],
        }

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(
            self.to_document(), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        return blake2b(payload, digest_size=16).hexdigest()


def planning_link_costs_from_document(
    document: object,
    configuration: MILPConfiguration,
) -> tuple[dict[tuple[ReplicaKey, ReplicaKey], float], str]:
    """Expand the existing versioned uniform/explicit link document."""

    if not isinstance(document, dict):
        raise MILPContractError("planning-link document must be a JSON object")
    if document.get("contract_version") != MILP_PLANNING_LINK_PROFILE_VERSION:
        raise MILPContractError("unexpected planning-link document version")
    source = document.get("source")
    if source is not None and (
        not isinstance(source, str) or not source.strip()
    ):
        raise MILPContractError("planning-link document source must be nonempty")
    dimensions_document = document.get("dimensions")
    if dimensions_document is not None:
        if not isinstance(dimensions_document, dict):
            raise MILPContractError("planning-link dimensions must be an object")
        expected_dimensions = {
            "stage_count": configuration.dimensions.stage_count,
            "replicas_per_stage": list(
                configuration.dimensions.replicas_per_stage
            ),
        }
        if dimensions_document != expected_dimensions:
            raise MILPContractError(
                "planning-link profile dimensions do not match the requested run"
            )
    expected = required_directed_pairs(configuration.dimensions)
    has_uniform = "uniform_cost_ms" in document
    has_explicit = "links" in document
    if has_uniform == has_explicit:
        raise MILPContractError(
            "planning-link document must contain exactly one of uniform_cost_ms or links"
        )
    if has_uniform:
        cost = _finite_nonnegative(document["uniform_cost_ms"], "uniform planning-link cost")
        return ({pair: cost for pair in expected}, MILP_UNIFORM_PLANNING_LINK_MODE)

    links = document["links"]
    if not isinstance(links, list):
        raise MILPContractError("explicit planning links must be a list")
    result: dict[tuple[ReplicaKey, ReplicaKey], float] = {}
    for item in links:
        if not isinstance(item, dict):
            raise MILPContractError("each explicit planning link must be an object")
        try:
            raw_source_stage = item["source_stage"]
            raw_source_replica = item["source_replica"]
            raw_target_stage = item["target_stage"]
            raw_target_replica = item["target_replica"]
            raw_cost = item["cost_ms"]
        except KeyError as error:
            raise MILPContractError("explicit planning link has invalid fields") from error
        for value, field in (
            (raw_source_stage, "source_stage"),
            (raw_source_replica, "source_replica"),
            (raw_target_stage, "target_stage"),
            (raw_target_replica, "target_replica"),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, Integral)
                or value < 1
            ):
                raise MILPContractError(
                    f"explicit planning-link {field} must be a positive integer"
                )
        pair = (
            ReplicaKey(int(raw_source_stage), int(raw_source_replica)),
            ReplicaKey(int(raw_target_stage), int(raw_target_replica)),
        )
        if pair[0].stage >= pair[1].stage:
            raise MILPContractError(
                "explicit planning link must point from a lower to a higher stage"
            )
        if pair in result:
            raise MILPContractError(f"duplicate explicit planning link: {pair}")
        result[pair] = _finite_nonnegative(raw_cost, "explicit planning-link cost")
    if set(result) != set(expected):
        missing = tuple(sorted(set(expected) - set(result)))
        extra = tuple(sorted(set(result) - set(expected)))
        raise MILPContractError(
            f"planning-link metadata mismatch: missing={missing}, extra={extra}"
        )
    return ({pair: result[pair] for pair in expected}, MILP_EXPLICIT_PLANNING_LINK_MODE)


def planning_link_source_from_document(document: object, mode: str) -> str:
    """Return stable semantic provenance without making fingerprints path-dependent."""

    if not isinstance(document, dict):
        raise MILPContractError("planning-link document must be a JSON object")
    source = document.get("source")
    if source is None:
        return (
            MILP_UNIFORM_PLANNING_LINK_SOURCE
            if mode == MILP_UNIFORM_PLANNING_LINK_MODE
            else MILP_EXPLICIT_PLANNING_LINK_SOURCE
        )
    if not isinstance(source, str) or not source.strip():
        raise MILPContractError("planning-link document source must be nonempty")
    return source.strip()


def build_experiment_profile(
    configuration: MILPConfiguration,
    *,
    true_states: Mapping[ReplicaKey, int],
    ready: Mapping[ReplicaKey, bool],
    assigned_flow_capacity: Mapping[ReplicaKey, int],
    planning_link_document: object,
    source_identity: str,
    measured_pair_base_ms: float = 5.0,
    measured_pair_jitter_ms: float = 0.75,
) -> MILPExperimentProfile:
    dimensions = configuration.dimensions
    expected_keys = set(dimensions.replica_keys)
    for field, values in (
        ("true state", true_states),
        ("Ready", ready),
        ("assigned-flow capacity", assigned_flow_capacity),
    ):
        if set(values) != expected_keys:
            raise MILPContractError(f"experiment {field} metadata must cover every replica")
    costs, mode = planning_link_costs_from_document(
        planning_link_document, configuration
    )
    planning_link_source = planning_link_source_from_document(
        planning_link_document, mode
    )
    pairs = required_directed_pairs(dimensions)
    return MILPExperimentProfile(
        configuration=configuration,
        replicas=tuple(
            MILPExperimentReplica(
                key=key,
                true_state=true_states[key],
                ready=ready[key],
                assigned_flow_capacity=assigned_flow_capacity[key],
            )
            for key in dimensions.replica_keys
        ),
        planning_links=tuple(
            MILPExperimentPlanningLink(source, target, costs[(source, target)])
            for source, target in pairs
        ),
        measured_pair_profiles=tuple(
            MeasuredPairLatencyProfile(
                source,
                target,
                base_ms=measured_pair_base_ms,
                jitter_ms=measured_pair_jitter_ms,
            )
            for source, target in pairs
        ),
        source_identity=source_identity,
        planning_link_mode=mode,
        planning_link_source=planning_link_source,
    )


def build_experiment_profile_from_runtime_states(
    configuration: MILPConfiguration,
    *,
    runtime_profiles: Mapping[tuple[int, int], object],
    assigned_flow_capacity_per_replica: int | None,
    planning_link_document: object,
    source_identity: str,
    measured_pair_base_ms: float = 5.0,
    measured_pair_jitter_ms: float = 0.75,
) -> MILPExperimentProfile:
    """Use runtime profile *state only*; legacy ``capacity`` is ignored."""

    dimensions = configuration.dimensions
    expected = {(key.stage, key.replica) for key in dimensions.replica_keys}
    if set(runtime_profiles) != expected:
        raise MILPContractError(
            "runtime state profile mismatch: profiles must cover every configured replica"
        )
    capacity = (
        dimensions.flow_count
        if assigned_flow_capacity_per_replica is None
        else _nonnegative_integer(
            assigned_flow_capacity_per_replica,
            "assigned_flow_capacity_per_replica",
        )
    )
    true_states = {
        key: int(getattr(runtime_profiles[(key.stage, key.replica)], "state"))
        for key in dimensions.replica_keys
    }
    return build_experiment_profile(
        configuration,
        true_states=true_states,
        ready={key: True for key in dimensions.replica_keys},
        assigned_flow_capacity={key: capacity for key in dimensions.replica_keys},
        planning_link_document=planning_link_document,
        source_identity=source_identity,
        measured_pair_base_ms=measured_pair_base_ms,
        measured_pair_jitter_ms=measured_pair_jitter_ms,
    )


def experiment_profile_from_document(document: object) -> MILPExperimentProfile:
    if not isinstance(document, dict):
        raise MILPContractError("experiment profile must be a JSON object")
    try:
        dimensions_doc = document["dimensions"]
        configuration = MILPConfiguration(
            dimensions=MILPDimensions(
                flow_count=int(dimensions_doc["flow_count"]),
                replicas_per_stage=tuple(
                    int(value) for value in dimensions_doc["replicas_per_stage"]
                ),
            ),
            cutoff_seconds=document["cutoff_seconds"],
        )
        replicas = tuple(
            MILPExperimentReplica(
                ReplicaKey(int(item["stage"]), int(item["replica"])),
                int(item["true_state"]),
                item["ready"],
                int(item["assigned_flow_capacity"]),
            )
            for item in document["replicas"]
        )
        links = tuple(
            MILPExperimentPlanningLink(
                ReplicaKey(int(item["source_stage"]), int(item["source_replica"])),
                ReplicaKey(int(item["target_stage"]), int(item["target_replica"])),
                item["cost_ms"],
            )
            for item in document["planning_links"]
        )
        measured = tuple(
            MeasuredPairLatencyProfile(
                ReplicaKey(int(item["source_stage"]), int(item["source_replica"])),
                ReplicaKey(int(item["target_stage"]), int(item["target_replica"])),
                item["base_ms"],
                item["jitter_ms"],
            )
            for item in document["measured_pair_profiles"]
        )
        if int(document["action_cardinality"]) != MILP_ACTION_CARDINALITY:
            raise MILPContractError("experiment profile must retain exact L=2")
        if bool(document["uniform_planning_link_is_objective_constant"]) != (
            document["planning_link_mode"] == MILP_UNIFORM_PLANNING_LINK_MODE
        ):
            raise MILPContractError("planning-link mode flag is inconsistent")
        return MILPExperimentProfile(
            configuration=configuration,
            replicas=replicas,
            planning_links=links,
            measured_pair_profiles=measured,
            source_identity=document["source_identity"],
            planning_link_mode=document["planning_link_mode"],
            planning_link_source=document.get(
                "planning_link_source",
                (
                    MILP_UNIFORM_PLANNING_LINK_SOURCE
                    if document["planning_link_mode"]
                    == MILP_UNIFORM_PLANNING_LINK_MODE
                    else MILP_EXPLICIT_PLANNING_LINK_SOURCE
                ),
            ),
            planning_link_contract_version=document.get(
                "planning_link_contract_version",
                MILP_PLANNING_LINK_PROFILE_VERSION,
            ),
            assigned_flow_capacity_unit=document["assigned_flow_capacity_unit"],
            source=document["source"],
            contract_version=document["contract_version"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise MILPContractError("invalid MILP experiment-profile document") from error


def load_experiment_profile(path: str | Path) -> MILPExperimentProfile:
    return experiment_profile_from_document(
        json.loads(Path(path).read_text(encoding="utf-8"))
    )


def experiment_profile_json(profile: MILPExperimentProfile) -> str:
    return json.dumps(
        profile.to_document(), sort_keys=True, separators=(",", ":"), allow_nan=False
    )
