"""Append-only Hybrid Kernel profile validation for Infrastructure Phase 6."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .contracts import HybridConfiguration, ReplicaChoice
from .kernel_controller_config import (
    HybridKernelControllerInputDocument,
    controller_input_document_from_mapping,
)
from .kernel_infrastructure_contract import (
    HybridKernelRuntimeProfileDocument,
)
from .kernel_runtime_profiles import runtime_profile_document_from_mapping


HYBRID_KERNEL_PROFILE_EXPANSION_VERSION = (
    "ibg-hybrid-kernel-profile-expansion-v1"
)
HYBRID_KERNEL_FLOW_ONLY_EXPANSION_VERSION = (
    "ibg-hybrid-kernel-flow-only-expansion-v1"
)


class HybridKernelProfileExpansionError(ValueError):
    """Raised before mutation when a profile expansion is not append-only."""


@dataclass(frozen=True)
class HybridKernelProfileExpansion:
    """Validated additions between deployed and proposed complete documents."""

    existing_replica_count: int
    deployed_profile_count: int
    target_replica_count: int
    added_runtime_identities: tuple[ReplicaChoice, ...]
    added_admission_identities: tuple[ReplicaChoice, ...]
    added_planning_pairs: tuple[tuple[ReplicaChoice, ReplicaChoice], ...]
    contract_version: str = HYBRID_KERNEL_PROFILE_EXPANSION_VERSION


@dataclass(frozen=True)
class HybridKernelFlowOnlyExpansion:
    """Validated topology-only transition with no replica-owned data change."""

    deployed_configuration: HybridConfiguration
    target_configuration: HybridConfiguration
    runtime_profile_count: int
    admission_count: int
    planning_pair_count: int
    contract_version: str = HYBRID_KERNEL_FLOW_ONLY_EXPANSION_VERSION


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise HybridKernelProfileExpansionError(f"{field} must be a mapping")
    return value


def _list(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise HybridKernelProfileExpansionError(f"{field} must be a list")
    return value


def _exact_keys(
    value: Mapping[str, object], expected: frozenset[str], field: str
) -> None:
    actual = frozenset(value)
    if actual != expected:
        raise HybridKernelProfileExpansionError(
            f"{field} fields differ: expected={sorted(expected)}, "
            f"actual={sorted(actual)}"
        )


def _validate_runtime_shape(value: Mapping[str, object]) -> None:
    _exact_keys(
        value,
        frozenset(("contract_version", "source_identity", "configuration", "profiles")),
        "runtime-profile document",
    )
    configuration = _mapping(value.get("configuration"), "runtime configuration")
    _exact_keys(
        configuration,
        frozenset(("num_flows", "num_stages", "num_replicas", "stage_budget")),
        "runtime configuration",
    )
    for index, item in enumerate(_list(value.get("profiles"), "runtime profiles")):
        profile = _mapping(item, f"runtime profile {index}")
        _exact_keys(
            profile,
            frozenset(("stage", "replica", "hidden_state", "observation_seed")),
            f"runtime profile {index}",
        )


def _validate_controller_shape(value: Mapping[str, object]) -> None:
    _exact_keys(
        value,
        frozenset(
            (
                "contract_version",
                "source_identity",
                "configuration",
                "admission",
                "planning_pair_links",
            )
        ),
        "controller-input document",
    )
    configuration = _mapping(value.get("configuration"), "controller configuration")
    _exact_keys(
        configuration,
        frozenset(("num_flows", "num_stages", "num_replicas", "stage_budget")),
        "controller configuration",
    )
    for index, item in enumerate(_list(value.get("admission"), "controller admission")):
        admission = _mapping(item, f"controller admission {index}")
        _exact_keys(
            admission,
            frozenset(("stage", "replica", "max_assigned_flows")),
            f"controller admission {index}",
        )
    for index, item in enumerate(
        _list(value.get("planning_pair_links"), "controller planning links")
    ):
        link = _mapping(item, f"controller planning link {index}")
        _exact_keys(
            link,
            frozenset(
                (
                    "source_stage",
                    "source_replica",
                    "target_stage",
                    "target_replica",
                    "latency_ms",
                )
            ),
            f"controller planning link {index}",
        )


def _runtime_document(
    value: Mapping[str, object], field: str
) -> HybridKernelRuntimeProfileDocument:
    try:
        _validate_runtime_shape(value)
        return runtime_profile_document_from_mapping(value)
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, HybridKernelProfileExpansionError):
            raise
        raise HybridKernelProfileExpansionError(f"invalid {field}: {error}") from error


def _controller_document(
    value: Mapping[str, object], field: str
) -> HybridKernelControllerInputDocument:
    try:
        _validate_controller_shape(value)
        return controller_input_document_from_mapping(value)
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, HybridKernelProfileExpansionError):
            raise
        raise HybridKernelProfileExpansionError(f"invalid {field}: {error}") from error


def _require_preserved(old: Mapping[object, object], new: Mapping[object, object], field: str) -> None:
    missing = sorted(set(old) - set(new))
    drifted = sorted(key for key, value in old.items() if new.get(key) != value)
    if missing:
        raise HybridKernelProfileExpansionError(
            f"{field} dropped existing entries: {missing}"
        )
    if drifted:
        raise HybridKernelProfileExpansionError(
            f"{field} drifted for existing entries: {drifted}"
        )


def validate_append_only_profile_expansion(
    *,
    deployed_runtime: Mapping[str, object],
    deployed_controller: Mapping[str, object],
    proposed_runtime: Mapping[str, object],
    proposed_controller: Mapping[str, object],
    existing_replica_count: int,
    expected_configuration: HybridConfiguration,
    expected_source_identity: str,
) -> HybridKernelProfileExpansion:
    """Validate complete proposed documents before either ConfigMap is changed."""

    if existing_replica_count < 1:
        raise HybridKernelProfileExpansionError(
            "existing_replica_count must be positive"
        )
    if not isinstance(expected_configuration, HybridConfiguration):
        raise TypeError("expected_configuration must be HybridConfiguration")
    if not isinstance(expected_source_identity, str) or not expected_source_identity:
        raise HybridKernelProfileExpansionError(
            "expected_source_identity must be nonempty"
        )

    current_runtime = _runtime_document(deployed_runtime, "deployed runtime profile")
    current_controller = _controller_document(
        deployed_controller, "deployed controller input"
    )
    target_runtime = _runtime_document(proposed_runtime, "proposed runtime profile")
    target_controller = _controller_document(
        proposed_controller, "proposed controller input"
    )

    if current_runtime.configuration != current_controller.configuration:
        raise HybridKernelProfileExpansionError(
            "deployed runtime/controller configurations differ"
        )
    if target_runtime.configuration != target_controller.configuration:
        raise HybridKernelProfileExpansionError(
            "proposed runtime/controller configurations differ"
        )
    if target_runtime.configuration != expected_configuration:
        raise HybridKernelProfileExpansionError(
            "proposed documents do not match the exact target configuration"
        )
    if (
        target_runtime.source_identity != expected_source_identity
        or target_controller.source_identity != expected_source_identity
    ):
        raise HybridKernelProfileExpansionError(
            "proposed documents do not use the approved target source identity"
        )

    current_configuration = current_runtime.configuration
    if (
        current_configuration.num_stages != expected_configuration.num_stages
        or current_configuration.stage_budget != expected_configuration.stage_budget
        or current_configuration.num_flows > expected_configuration.num_flows
        or not (
            existing_replica_count
            <= current_configuration.num_replicas
            <= expected_configuration.num_replicas
        )
    ):
        raise HybridKernelProfileExpansionError(
            "deployed profile configuration is outside the append-only boundary"
        )

    old_runtime = {item.choice: item for item in current_runtime.profiles}
    new_runtime = {item.choice: item for item in target_runtime.profiles}
    _require_preserved(old_runtime, new_runtime, "runtime identity/state/seed")

    old_admission = {item.choice: item for item in current_controller.admission}
    new_admission = {item.choice: item for item in target_controller.admission}
    _require_preserved(old_admission, new_admission, "admission capacity")

    old_links = {item.pair: item for item in current_controller.planning_pair_links}
    new_links = {item.pair: item for item in target_controller.planning_pair_links}
    _require_preserved(old_links, new_links, "planning link")

    return HybridKernelProfileExpansion(
        existing_replica_count=existing_replica_count,
        deployed_profile_count=current_configuration.num_replicas,
        target_replica_count=expected_configuration.num_replicas,
        added_runtime_identities=tuple(sorted(set(new_runtime) - set(old_runtime))),
        added_admission_identities=tuple(
            sorted(set(new_admission) - set(old_admission))
        ),
        added_planning_pairs=tuple(sorted(set(new_links) - set(old_links))),
    )


def validate_flow_only_profile_expansion(
    *,
    deployed_runtime: Mapping[str, object],
    deployed_controller: Mapping[str, object],
    proposed_runtime: Mapping[str, object],
    proposed_controller: Mapping[str, object],
    deployed_configuration: HybridConfiguration,
    target_configuration: HybridConfiguration,
    deployed_source_identity: str,
    target_source_identity: str,
) -> HybridKernelFlowOnlyExpansion:
    """Require a flow-count/source transition and otherwise identical documents."""

    for value, field in (
        (deployed_configuration, "deployed_configuration"),
        (target_configuration, "target_configuration"),
    ):
        if not isinstance(value, HybridConfiguration):
            raise TypeError(f"{field} must be HybridConfiguration")
    for value, field in (
        (deployed_source_identity, "deployed_source_identity"),
        (target_source_identity, "target_source_identity"),
    ):
        if not isinstance(value, str) or not value:
            raise HybridKernelProfileExpansionError(f"{field} must be nonempty")
    if (
        target_configuration.num_flows <= deployed_configuration.num_flows
        or target_configuration.num_stages != deployed_configuration.num_stages
        or target_configuration.num_replicas
        != deployed_configuration.num_replicas
        or target_configuration.stage_budget != deployed_configuration.stage_budget
    ):
        raise HybridKernelProfileExpansionError(
            "flow-only expansion may increase only num_flows"
        )

    current_runtime = _runtime_document(deployed_runtime, "deployed runtime profile")
    current_controller = _controller_document(
        deployed_controller, "deployed controller input"
    )
    target_runtime = _runtime_document(proposed_runtime, "proposed runtime profile")
    target_controller = _controller_document(
        proposed_controller, "proposed controller input"
    )

    if (
        current_runtime.configuration != deployed_configuration
        or current_controller.configuration != deployed_configuration
    ):
        raise HybridKernelProfileExpansionError(
            "deployed documents do not match the approved source configuration"
        )
    if (
        target_runtime.configuration != target_configuration
        or target_controller.configuration != target_configuration
    ):
        raise HybridKernelProfileExpansionError(
            "proposed documents do not match the exact flow-only target"
        )
    if (
        current_runtime.source_identity != deployed_source_identity
        or current_controller.source_identity != deployed_source_identity
    ):
        raise HybridKernelProfileExpansionError(
            "deployed documents do not use the approved source identity"
        )
    if (
        target_runtime.source_identity != target_source_identity
        or target_controller.source_identity != target_source_identity
    ):
        raise HybridKernelProfileExpansionError(
            "proposed documents do not use the approved target source identity"
        )

    if target_runtime.profiles != current_runtime.profiles:
        raise HybridKernelProfileExpansionError(
            "flow-only expansion drifted runtime identity/state/seed"
        )
    if target_controller.admission != current_controller.admission:
        raise HybridKernelProfileExpansionError(
            "flow-only expansion drifted admission capacity"
        )
    if (
        target_controller.planning_pair_links
        != current_controller.planning_pair_links
    ):
        raise HybridKernelProfileExpansionError(
            "flow-only expansion drifted planning links"
        )

    return HybridKernelFlowOnlyExpansion(
        deployed_configuration=deployed_configuration,
        target_configuration=target_configuration,
        runtime_profile_count=len(target_runtime.profiles),
        admission_count=len(target_controller.admission),
        planning_pair_count=len(target_controller.planning_pair_links),
    )
