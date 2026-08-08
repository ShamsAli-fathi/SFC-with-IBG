"""Load and render the versioned Hybrid Kernel processor profile document."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from .contracts import HybridConfiguration, ReplicaChoice
from .kernel_infrastructure_contract import (
    HYBRID_KERNEL_RUNTIME_PROFILE_CONTRACT_VERSION,
    HybridKernelContractError,
    HybridKernelRuntimeProfileDocument,
    HybridKernelRuntimeReplicaProfile,
)


def runtime_profile_document_from_mapping(
    value: Mapping[str, object],
) -> HybridKernelRuntimeProfileDocument:
    """Validate one JSON-compatible Phase 0 runtime-profile document."""

    if not isinstance(value, Mapping):
        raise HybridKernelContractError("runtime-profile document must be a mapping")
    configuration_value = value.get("configuration")
    profiles_value = value.get("profiles")
    if not isinstance(configuration_value, Mapping):
        raise HybridKernelContractError("runtime-profile configuration is required")
    if not isinstance(profiles_value, list):
        raise HybridKernelContractError("runtime-profile profiles must be a list")
    try:
        configuration = HybridConfiguration(
            num_flows=configuration_value["num_flows"],
            num_stages=configuration_value["num_stages"],
            num_replicas=configuration_value["num_replicas"],
            stage_budget=configuration_value["stage_budget"],
        )
        profiles = tuple(
            HybridKernelRuntimeReplicaProfile(
                choice=ReplicaChoice(item["stage"], item["replica"]),
                hidden_state=item["hidden_state"],
                observation_seed=item["observation_seed"],
            )
            for item in profiles_value
        )
        return HybridKernelRuntimeProfileDocument(
            configuration=configuration,
            profiles=profiles,
            source_identity=value["source_identity"],
            contract_version=value["contract_version"],
        )
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, HybridKernelContractError):
            raise
        raise HybridKernelContractError(
            f"invalid Hybrid runtime-profile document: {error}"
        ) from error


def runtime_profile_document_to_mapping(
    document: HybridKernelRuntimeProfileDocument,
) -> dict[str, object]:
    """Render the stable JSON shape mounted into processor Pods."""

    if not isinstance(document, HybridKernelRuntimeProfileDocument):
        raise TypeError("document must be HybridKernelRuntimeProfileDocument")
    configuration = document.configuration
    return {
        "contract_version": HYBRID_KERNEL_RUNTIME_PROFILE_CONTRACT_VERSION,
        "source_identity": document.source_identity,
        "configuration": {
            "num_flows": configuration.num_flows,
            "num_stages": configuration.num_stages,
            "num_replicas": configuration.num_replicas,
            "stage_budget": configuration.stage_budget,
        },
        "profiles": [
            {
                "stage": profile.choice.stage,
                "replica": profile.choice.replica,
                "hidden_state": profile.hidden_state,
                "observation_seed": profile.observation_seed,
            }
            for profile in document.profiles
        ],
    }


def load_runtime_profile_document(
    path: str | Path,
) -> HybridKernelRuntimeProfileDocument:
    """Read a profile only when a processor runtime explicitly starts."""

    document = json.loads(Path(path).read_text(encoding="utf-8"))
    return runtime_profile_document_from_mapping(document)

