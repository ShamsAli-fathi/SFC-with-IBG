"""Configuration adapters for the MILP Kernel controller."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from .contracts import MILPConfiguration, MILPProblemInput
from .experiment_profile import (
    MILPExperimentProfile,
    planning_link_costs_from_document as _profile_planning_link_costs,
)
from .kernel_contracts import (
    MILP_KERNEL_PLANNING_LINK_DOCUMENT_VERSION,
    MILPKernelReplicaEndpoint,
)
from .phase0_contract import MILPContractError, ReplicaKey
from .runtime_profiles import MILPRuntimeReplicaProfile


def planning_link_costs_from_document(
    document: object,
    configuration: MILPConfiguration,
) -> dict[tuple[ReplicaKey, ReplicaKey], float]:
    """Compatibility wrapper over the canonical experiment-profile parser."""

    costs, _mode = _profile_planning_link_costs(document, configuration)
    return costs


def load_planning_link_document(path: str | Path) -> object:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_kernel_problem_input(
    configuration: MILPConfiguration,
    *,
    endpoints: tuple[MILPKernelReplicaEndpoint, ...],
    experiment_profile: MILPExperimentProfile | None = None,
    profiles: Mapping[tuple[int, int], MILPRuntimeReplicaProfile] | None = None,
    planning_link_document: object | None = None,
    assigned_flow_capacity_per_replica: int | None = None,
) -> MILPProblemInput:
    """Build the planner input after Ready discovery.

    New callers must supply the canonical experiment profile.  The explicit
    compatibility path accepts runtime profiles for state only and uses a
    dimension-aware MILP capacity; it never reads ``ReplicaProfile.capacity``.
    """

    dimensions = configuration.dimensions
    endpoint_keys = {endpoint.key for endpoint in endpoints}
    expected_keys = set(dimensions.replica_keys)
    if len(endpoint_keys) != len(endpoints) or endpoint_keys != expected_keys:
        raise MILPContractError("Ready discovery must cover every configured replica")
    if experiment_profile is not None:
        if profiles is not None or planning_link_document is not None:
            raise MILPContractError(
                "canonical experiment profile cannot be combined with legacy adapters"
            )
        if experiment_profile.configuration != configuration:
            raise MILPContractError(
                "experiment profile configuration/cutoff does not match controller"
            )
        return experiment_profile.problem_input()

    if profiles is None or planning_link_document is None:
        raise MILPContractError("canonical experiment profile is required")
    from .experiment_profile import build_experiment_profile_from_runtime_states

    profile = build_experiment_profile_from_runtime_states(
        configuration,
        runtime_profiles=profiles,
        assigned_flow_capacity_per_replica=assigned_flow_capacity_per_replica,
        planning_link_document=planning_link_document,
        source_identity="legacy-kernel-adapter-state-only",
    )
    return profile.problem_input()
